"""Relatórios Gerenciais da Clínica-Escola (somente psicólogo técnico).

Módulo PURO: recebe os dados já lidos do banco (listas de dicionários) e devolve os indicadores
agregados. Não acessa o banco, não altera nenhum registro e não devolve texto clínico nem dados
pessoais de pacientes — só contagens, percentuais e nomes de estudantes/supervisores.

Regras de cálculo (todas explicadas ao usuário no próprio relatório):
- Atividade (atendimentos, faltas, evoluções, cadastros) usa a data do evento dentro do período.
- Posição atual (pacientes ativos, estudantes, pendências) é marcada como "referência atual".
- Taxa de comparecimento = realizados / (realizados + faltas). Só entram atendimentos com
  comparecimento registrado; cancelados, futuros e sem registro NÃO são faltas.
"""
import datetime
import re

CATEGORIAS = [
    ("panorama", "Panorama geral", [
        ("pan_casos", "Pacientes e casos (posição atual)"),
        ("pan_equipe", "Estudantes e supervisores (posição atual)"),
        ("pan_alocacao", "Alocação de pacientes (posição atual)"),
        ("pan_atividade", "Atividade total no período"),
    ]),
    ("agenda", "Atendimentos e agenda", [
        ("ag_resumo", "Atendimentos, faltas, cancelamentos e reagendamentos"),
        ("ag_periodo", "Distribuição dos atendimentos ao longo do período"),
        ("ag_dias", "Dias e horários com maior volume"),
    ]),
    ("estudantes", "Estudantes", [
        ("est_tabela", "Comparativo de atividade por estudante"),
    ]),
    ("pacientes", "Pacientes e acompanhamento", [
        ("pac_resumo", "Novos cadastros, vínculos e faltas consecutivas"),
        ("pac_atend", "Atendimentos realizados por paciente"),
    ]),
    ("evolucoes", "Evoluções e supervisão", [
        ("evo_resumo", "Evoluções registradas"),
        ("sup_tabela", "Atividade por supervisor"),
    ]),
    ("inscricoes", "Inscrições e triagens", [
        ("ins_resumo", "Inscrições recebidas e situação atual"),
        ("ins_tempo", "Triagens concluídas e tempo médio"),
    ]),
    ("pendencias", "Solicitações e pendências", [
        ("pen_resumo", "Reagendamentos e acessos ao prontuário (posição atual)"),
    ]),
    ("adicionais", "Indicadores de desempenho", [
        ("add_percent", "Percentuais de faltas e cancelamentos, média por estudante"),
    ]),
]
IDS_VALIDOS = [i for _, _, itens in CATEGORIAS for i, _ in itens]
TITULOS = {i: t for _, _, itens in CATEGORIAS for i, t in itens}
CAT_DE = {i: titulo for _, titulo, itens in CATEGORIAS for i, _ in itens}

PERIODOS = ("semana_atual", "semana_anterior", "mes_atual", "mes_anterior", "tres_meses", "personalizado")
MAX_DIAS = 366
MSG_VAZIO = "Não há registros disponíveis para este indicador no período selecionado."
DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


# ----------------------------------------------------------------- período
def _fim_do_mes(ano, mes):
    prox = ano * 12 + mes  # índice do mês seguinte (base 0)
    return datetime.date(prox // 12, prox % 12 + 1, 1) - datetime.timedelta(days=1)


def _subtrai_meses(d, n):
    idx = d.year * 12 + (d.month - 1) - n
    ano, mes = idx // 12, idx % 12 + 1
    return datetime.date(ano, mes, min(d.day, _fim_do_mes(ano, mes).day))


def resolver_periodo(periodo, hoje, inicio=None, fim=None):
    """(data_inicial, data_final, rótulo) ou levanta ValueError com a mensagem para o usuário."""
    if periodo not in PERIODOS:
        raise ValueError("período inválido")
    seg = hoje - datetime.timedelta(days=hoje.weekday())
    if periodo == "semana_atual":
        ini, fim_ = seg, seg + datetime.timedelta(days=6)
    elif periodo == "semana_anterior":
        ini = seg - datetime.timedelta(days=7)
        fim_ = ini + datetime.timedelta(days=6)
    elif periodo == "mes_atual":
        ini = hoje.replace(day=1)
        fim_ = _fim_do_mes(ini.year, ini.month)
    elif periodo == "mes_anterior":
        fim_ = hoje.replace(day=1) - datetime.timedelta(days=1)
        ini = fim_.replace(day=1)
    elif periodo == "tres_meses":
        ini, fim_ = _subtrai_meses(hoje, 3), hoje
    else:
        try:
            ini = datetime.date.fromisoformat(str(inicio or ""))
            fim_ = datetime.date.fromisoformat(str(fim or ""))
        except ValueError:
            raise ValueError("informe a data inicial e a data final do período")
        if fim_ < ini:
            raise ValueError("a data final não pode ser anterior à data inicial")
        if (fim_ - ini).days + 1 > MAX_DIAS:
            raise ValueError("o período personalizado pode ter no máximo %d dias" % MAX_DIAS)
    return ini, fim_, "%s a %s" % (ini.strftime("%d/%m/%Y"), fim_.strftime("%d/%m/%Y"))


# ----------------------------------------------------------------- utilitários
def _data(valor):
    """date de 'DD/MM/AAAA' (ou de um texto que COMEÇA assim, como '28/08/2026 14h00'); None se inválida."""
    if not isinstance(valor, str):
        return None
    m = re.match(r"^\s*(\d{2})/(\d{2})/(\d{4})", valor)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _data_hora(valor):
    if not isinstance(valor, str):
        return None
    m = re.match(r"^\s*(\d{2})/(\d{2})/(\d{4})(?:\D+(\d{1,2})[h:](\d{2}))?", valor)
    if not m:
        return None
    try:
        return datetime.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), int(m.group(4) or 0), int(m.group(5) or 0))
    except ValueError:
        return None


def _hora(valor):
    m = re.match(r"^(\d{1,2})[:h](\d{2})", str(valor or ""))
    return int(m.group(1)) if m else None


def _pct(a, b):
    return None if not b else round(100.0 * a / b, 1)


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return ("%.1f" % v).replace(".", ",")
    return str(v)


def _kpi(rotulo, valor, detalhe="", atual=False, pct=False):
    texto = _fmt(valor) + ("%" if pct and valor is not None else "")
    return {"rotulo": rotulo, "valor": texto, "detalhe": detalhe, "atual": bool(atual)}


def _secao(id_, kpis=None, tabela=None, grafico=None, aviso="", atual=False, vazio=False, notas=None):
    return {"id": id_, "categoria": CAT_DE[id_], "titulo": TITULOS[id_], "referencia_atual": atual,
            "kpis": kpis or [], "tabela": tabela, "grafico": grafico,
            "aviso": MSG_VAZIO if vazio else aviso, "vazio": bool(vazio), "notas": notas or []}


# ----------------------------------------------------------------- contexto de cálculo
class _Ctx:
    def __init__(self, dados, ini, fim, agora):
        self.ini, self.fim, self.agora = ini, fim, agora
        self.casos = dados.get("casos") or []
        self.estudantes = dados.get("estudantes") or []
        self.supervisores = dados.get("supervisores") or []
        self.inscricoes = dados.get("inscricoes") or []
        self.solicitacoes = dados.get("solicitacoes") or []
        self.reagendamentos = dados.get("reagendamentos") or []
        self.faltas_consecutivas = dados.get("faltas_consecutivas") or {}
        self.notas = dados.get("notas") or []
        self.ags = []  # (caso, ag, data, classe)
        for c in self.casos:
            for ag in c.get("agendamentos") or []:
                d = _data(ag.get("data"))
                if d is None:
                    continue
                self.ags.append((c, ag, d, self._classe(ag, d)))
        self.no_periodo = [x for x in self.ags if self.ini <= x[2] <= self.fim]

    def _classe(self, ag, d):
        if ag.get("status") == "Cancelada":
            return "cancelado"
        comp = (ag.get("comparecimento") or {}).get("situacao")
        if comp == "compareceu":
            return "realizado"
        if comp == "faltou":
            return "falta"
        h = _hora(ag.get("hora")) or 0
        inicio = datetime.datetime(d.year, d.month, d.day, h)
        return "futuro" if inicio > self.agora else "sem_registro"

    def contagem(self, lista=None):
        lista = self.no_periodo if lista is None else lista
        out = {"realizado": 0, "falta": 0, "cancelado": 0, "futuro": 0, "sem_registro": 0}
        for _, _, _, cl in lista:
            out[cl] += 1
        return out

    def evolucoes_periodo(self):
        out = []
        for c in self.casos:
            for e in c.get("evolucoes") or []:
                d = _data(e.get("data"))
                if d and self.ini <= d <= self.fim:
                    out.append((c, e))
        return out


# ----------------------------------------------------------------- seções
def _pan_casos(x):
    total = len(x.casos)
    at = sum(1 for c in x.casos if c.get("status") == "Ativo")
    enc = sum(1 for c in x.casos if c.get("status") == "Encerrado")
    return _secao("pan_casos", [
        _kpi("Pacientes cadastrados", total, "total de casos no sistema", True),
        _kpi("Pacientes ativos", at, "casos em acompanhamento", True),
        _kpi("Casos encerrados", enc, "total acumulado", True)], atual=True, vazio=(total == 0))


def _pan_equipe(x):
    ativos = sum(1 for e in x.estudantes if e.get("ativo"))
    return _secao("pan_equipe", [
        _kpi("Estudantes cadastrados", len(x.estudantes), "", True),
        _kpi("Estudantes ativos", ativos, "com conta ativa e RA ativo", True),
        _kpi("Supervisores cadastrados", len(x.supervisores), "contas de supervisor ativas", True)],
        atual=True, vazio=(not x.estudantes and not x.supervisores))


def _pan_alocacao(x):
    at = [c for c in x.casos if c.get("status") == "Ativo"]
    com = sum(1 for c in at if c.get("estudante"))
    sem = len(at) - com
    return _secao("pan_alocacao", [
        _kpi("Pacientes vinculados a estudantes", com, "casos ativos com estudante", True),
        _kpi("Aguardando alocação", sem, "casos ativos sem estudante", True)], atual=True, vazio=(not at))


def _pan_atividade(x):
    c = x.contagem()
    evo = len(x.evolucoes_periodo())
    vazio = not (c["realizado"] or evo)
    return _secao("pan_atividade", [
        _kpi("Atendimentos realizados", c["realizado"], "com presença registrada no período"),
        _kpi("Evoluções registradas", evo, "registros feitos no período")], vazio=vazio)


def _ag_resumo(x):
    c = x.contagem()
    marcados = c["realizado"] + c["falta"] + c["futuro"] + c["sem_registro"]
    reag = 0
    for _, ag, _, _ in x.ags:
        for r in ag.get("reagendamentos") or []:
            d = _data(r.get("quando"))
            if d and x.ini <= d <= x.fim:
                reag += 1
    reg = c["realizado"] + c["falta"]
    kp = [
        _kpi("Atendimentos agendados", marcados, "marcados para o período, sem os cancelados"),
        _kpi("Realizados", c["realizado"], "presença registrada"),
        _kpi("Faltas dos pacientes", c["falta"], "falta registrada"),
        _kpi("Cancelamentos", c["cancelado"], "atendimentos do período que foram cancelados"),
        _kpi("Reagendamentos", reag, "remarcações feitas no período"),
        _kpi("Taxa de comparecimento", _pct(c["realizado"], reg), "realizados ÷ (realizados + faltas)", pct=True),
    ]
    notas = ["Atendimentos futuros e os que ainda não tiveram o comparecimento registrado (%d) não entram como falta nem na taxa." % c["sem_registro"]
             if (c["sem_registro"] or c["futuro"]) else "Só entram na taxa os atendimentos com presença ou falta registrada."]
    return _secao("ag_resumo", kp, notas=notas, vazio=not (marcados or c["cancelado"] or reag))


def _buckets(x):
    dias = (x.fim - x.ini).days + 1
    if dias <= 62:
        def chave(d):
            seg = d - datetime.timedelta(days=d.weekday())
            return seg, "Sem. " + seg.strftime("%d/%m")
        tipo = "semana"
    else:
        def chave(d):
            p = d.replace(day=1)
            return p, p.strftime("%m/%Y")
        tipo = "mês"
    return chave, tipo


def _ag_periodo(x):
    if not x.no_periodo:
        return _secao("ag_periodo", vazio=True)
    chave, tipo = _buckets(x)
    ordem, rot = {}, {}
    for _, _, d, cl in x.no_periodo:
        k, r = chave(d)
        ordem.setdefault(k, {"realizado": 0, "falta": 0, "cancelado": 0, "futuro": 0, "sem_registro": 0})[cl] += 1
        rot[k] = r
    ks = sorted(ordem)
    return _secao("ag_periodo", grafico={
        "tipo": "barras", "titulo": "Atendimentos por %s" % tipo, "rotulos": [rot[k] for k in ks],
        "series": [{"nome": "Realizados", "valores": [ordem[k]["realizado"] for k in ks]},
                   {"nome": "Faltas", "valores": [ordem[k]["falta"] for k in ks]},
                   {"nome": "Cancelados", "valores": [ordem[k]["cancelado"] for k in ks]},
                   {"nome": "A realizar / sem registro", "valores": [ordem[k]["futuro"] + ordem[k]["sem_registro"] for k in ks]}]})


def _ag_dias(x):
    marc = [t for t in x.no_periodo if t[3] != "cancelado"]
    if not marc:
        return _secao("ag_dias", vazio=True)
    dias = [0] * 7
    horas = {}
    for _, ag, d, _ in marc:
        dias[d.weekday()] += 1
        h = _hora(ag.get("hora"))
        if h is not None:
            horas[h] = horas.get(h, 0) + 1
    linhas = [["%02dh" % h, n] for h, n in sorted(horas.items(), key=lambda t: (-t[1], t[0]))[:6]]
    return _secao("ag_dias", grafico={"tipo": "barras", "titulo": "Atendimentos por dia da semana", "rotulos": DIAS_SEMANA,
                                      "series": [{"nome": "Atendimentos", "valores": dias}]},
                  tabela={"titulo": "Horários com maior volume", "colunas": ["Horário de início", "Atendimentos"], "linhas": linhas})


def _est_tabela(x):
    nomes = {e["nome"]: e for e in x.estudantes}
    for c in x.casos:
        if c.get("estudante") and c["estudante"] not in nomes:
            nomes[c["estudante"]] = {"nome": c["estudante"], "ativo": True}
    if not nomes:
        return _secao("est_tabela", vazio=True)
    por_est = {}
    for n in nomes:
        por_est[n] = {"vinc": 0, "acomp": 0, "marc": 0, "real": 0, "falta": 0, "evo": 0, "sup": {}}
    for c in x.casos:
        n = c.get("estudante")
        if n in por_est:
            por_est[n]["vinc"] += 1
            por_est[n]["acomp"] += 1 if c.get("status") == "Ativo" else 0
            if c.get("supervisor"):
                por_est[n]["sup"][c["supervisor"]] = por_est[n]["sup"].get(c["supervisor"], 0) + 1
    for c, ag, d, cl in x.no_periodo:
        n = c.get("estudante")
        if n in por_est and cl != "cancelado":
            por_est[n]["marc"] += 1
            por_est[n]["real"] += cl == "realizado"
            por_est[n]["falta"] += cl == "falta"
    for c, e in x.evolucoes_periodo():
        n = e.get("autor")
        if n in por_est and str(e.get("papel", "")).lower().startswith("estud"):
            por_est[n]["evo"] += 1
    linhas = []
    for n, v in por_est.items():
        sup = nomes[n].get("supervisor") or (max(v["sup"], key=v["sup"].get) if v["sup"] else "—")
        linhas.append([n, sup, v["vinc"], v["acomp"], v["marc"], v["real"], v["falta"], v["evo"]])
    linhas.sort(key=lambda r: (-r[5], r[0].casefold()))
    atividade = sum(r[4] + r[7] for r in linhas)
    return _secao("est_tabela", tabela={
        "titulo": "Atividade registrada por estudante", "ordenavel": True,
        "colunas": ["Estudante", "Supervisor", "Pacientes vinculados", "Em acompanhamento", "Agendados no período",
                    "Atendimentos realizados", "Faltas dos pacientes", "Evoluções registradas"],
        "linhas": linhas},
        notas=["Os números mostram atividade registrada no sistema. Não medem a qualidade clínica nem a competência do estudante.",
               "Pacientes vinculados e em acompanhamento são a posição atual; os demais valores são do período."],
        vazio=(atividade == 0 and not any(r[2] for r in linhas)))


def _pac_resumo(x):
    ativos = [c for c in x.casos if c.get("status") == "Ativo"]
    novos = sum(1 for c in x.casos if (lambda d: d and x.ini <= d <= x.fim)(_data(c.get("abertura"))))
    com = sum(1 for c in ativos if c.get("estudante"))
    consec = sum(1 for c in ativos if x.faltas_consecutivas.get(c.get("_id"), 0) >= 2)
    faltas = x.contagem()["falta"]
    return _secao("pac_resumo", [
        _kpi("Pacientes ativos", len(ativos), "", True),
        _kpi("Novos pacientes no período", novos, "casos abertos no período"),
        _kpi("Vinculados a estudantes", com, "entre os ativos", True),
        _kpi("Sem estudante vinculado", len(ativos) - com, "entre os ativos", True),
        _kpi("Faltas no período", faltas, "histórico quantitativo, sem identificar pacientes"),
        _kpi("Pacientes com faltas consecutivas", consec, "2 ou mais faltas seguidas (regra já existente)", True)],
        notas=["Casos encerrados no período: indicador indisponível, o sistema ainda não registra a data de encerramento do caso."],
        vazio=(not x.casos))


def _pac_atend(x):
    ativos = [c for c in x.casos if c.get("status") == "Ativo"]
    if not ativos:
        return _secao("pac_atend", vazio=True)
    cont = {}
    for c, ag, d, cl in x.no_periodo:
        if cl == "realizado":
            cont[c["_id"]] = cont.get(c["_id"], 0) + 1
    faixas = [("Nenhum", 0), ("1 atendimento", 0), ("2 a 3", 0), ("4 ou mais", 0)]
    cnt = [0, 0, 0, 0]
    for c in ativos:
        n = cont.get(c["_id"], 0)
        cnt[0 if n == 0 else 1 if n == 1 else 2 if n <= 3 else 3] += 1
    return _secao("pac_atend", grafico={"tipo": "barras", "titulo": "Pacientes ativos por nº de atendimentos realizados no período",
                                        "rotulos": [f[0] for f in faixas], "series": [{"nome": "Pacientes", "valores": cnt}]},
                  kpis=[_kpi("Atendimentos realizados", sum(cont.values()), "no período")])


def _evo_resumo(x):
    evo = x.evolucoes_periodo()
    if not evo:
        return _secao("evo_resumo", vazio=True)
    por_papel, por_est = {}, {}
    for c, e in evo:
        p = str(e.get("papel") or "Não informado")
        por_papel[p] = por_papel.get(p, 0) + 1
        if p.lower().startswith("estud"):
            por_est[e.get("autor") or "—"] = por_est.get(e.get("autor") or "—", 0) + 1
    top = sorted(por_est.items(), key=lambda t: (-t[1], t[0].casefold()))
    kp = [_kpi("Evoluções registradas", len(evo), "no período")]
    kp += [_kpi("Registros de %s" % p.lower(), n, "") for p, n in sorted(por_papel.items())]
    notas_n = len([1 for n in x.notas if (lambda d: d and x.ini <= d <= x.fim)(_data(n.get("data")))])
    kp.append(_kpi("Notas de acompanhamento do técnico", notas_n, "feitas no período"))
    return _secao("evo_resumo", kp, grafico={"tipo": "barras", "titulo": "Evoluções por estudante", "rotulos": [n for n, _ in top],
                                             "series": [{"nome": "Evoluções", "valores": [v for _, v in top]}]} if top else None,
                  notas=["O relatório conta os registros. Nenhum texto de anamnese ou evolução é incluído."])


def _sup_tabela(x):
    nomes = {s["nome"] for s in x.supervisores} | {c["supervisor"] for c in x.casos if c.get("supervisor")}
    if not nomes:
        return _secao("sup_tabela", vazio=True)
    linhas = []
    evos = x.evolucoes_periodo()
    for n in sorted(nomes, key=str.casefold):
        meus = [c for c in x.casos if c.get("supervisor") == n]
        est = {c.get("estudante") for c in meus if c.get("estudante")}
        ativos = sum(1 for c in meus if c.get("status") == "Ativo")
        ids = {c["_id"] for c in meus}
        ev_est = sum(1 for c, e in evos if c["_id"] in ids and str(e.get("papel", "")).lower().startswith("estud"))
        ev_sup = sum(1 for c, e in evos if c["_id"] in ids and str(e.get("papel", "")).lower().startswith("superv"))
        marc = sum(1 for c, ag, d, cl in x.no_periodo if c["_id"] in ids and cl in ("realizado", "falta", "futuro", "sem_registro"))
        linhas.append([n, ativos, len(est), marc, ev_est, ev_sup])
    return _secao("sup_tabela", tabela={"titulo": "Casos e registros por supervisor", "ordenavel": True,
                  "colunas": ["Supervisor", "Casos ativos", "Estudantes supervisionados", "Atendimentos no período",
                              "Evoluções dos estudantes", "Registros do supervisor"], "linhas": linhas},
                  notas=["Casos ativos e estudantes são a posição atual. Registros de orientação aparecem apenas quando o supervisor lançou evolução no caso."])


def _data_epoch(t):
    try:
        return (datetime.datetime.utcfromtimestamp(float(t)) - datetime.timedelta(hours=3))
    except (TypeError, ValueError, OverflowError):
        return None


def _ins_resumo(x):
    rec = [i for i in x.inscricoes if (lambda d: d and x.ini <= d.date() <= x.fim)(_data_epoch(i.get("criado_em")))]
    if not rec:
        return _secao("ins_resumo", vazio=True)
    st = {}
    for i in rec:
        st[i.get("status") or "—"] = st.get(i.get("status") or "—", 0) + 1
    ordem = ["Recebido", "Analisado", "Aguardando triagem", "Aprovado para acompanhamento", "Não aprovado", "Cadastrado"]
    ks = [k for k in ordem if k in st] + [k for k in st if k not in ordem]
    return _secao("ins_resumo", [_kpi("Inscrições recebidas", len(rec), "no período")] + [_kpi(k, st[k], "situação atual") for k in ks],
                  grafico={"tipo": "barras", "titulo": "Situação atual das inscrições recebidas no período", "rotulos": ks,
                           "series": [{"nome": "Inscrições", "valores": [st[k] for k in ks]}]},
                  notas=["A situação é a atual de cada inscrição recebida no período, não o histórico de mudanças."])


def _ins_tempo(x):
    concl, tempos = 0, []
    for i in x.inscricoes:
        t = i.get("triagem") or {}
        if not t.get("resultado"):
            continue
        fim = _data_hora(t.get("resultado_em"))
        if fim is None or not (x.ini <= fim.date() <= x.fim):
            continue
        concl += 1
        ini = _data_epoch(i.get("criado_em"))
        if ini is not None and fim >= ini:
            tempos.append((fim - ini).total_seconds() / 86400.0)
    if not concl:
        return _secao("ins_tempo", vazio=True)
    media = round(sum(tempos) / len(tempos), 1) if tempos else None
    return _secao("ins_tempo", [_kpi("Triagens concluídas", concl, "resultado registrado no período"),
                                _kpi("Tempo médio até a triagem", media, "dias entre o recebimento da inscrição e o resultado" if media is not None else "datas insuficientes")])


def _pen_resumo(x):
    sol, reag = x.solicitacoes, x.reagendamentos
    s_p = sum(1 for s in sol if s.get("status") == "pendente")
    s_l = sum(1 for s in sol if s.get("status") == "liberado")
    r_p = sum(1 for r in reag if r.get("status") == "pendente")
    r_c = sum(1 for r in reag if r.get("status") == "confirmado")
    if not (sol or reag):
        return _secao("pen_resumo", atual=True, vazio=True)
    return _secao("pen_resumo", [
        _kpi("Reagendamentos pendentes", r_p, "", True), _kpi("Reagendamentos confirmados", r_c, "", True),
        _kpi("Acessos ao prontuário pendentes", s_p, "", True), _kpi("Acessos ao prontuário liberados", s_l, "", True)],
        grafico={"tipo": "barras", "titulo": "Solicitações por tipo e situação", "rotulos": ["Reagendamento", "Acesso ao prontuário"],
                 "series": [{"nome": "Pendentes", "valores": [r_p, s_p]}, {"nome": "Concluídas", "valores": [r_c, s_l]}]},
        atual=True, notas=["As solicitações não guardam data de criação no sistema, por isso aparecem como situação atual, sem filtro de período."])


def _add_percent(x):
    c = x.contagem()
    reg = c["realizado"] + c["falta"]
    tot = reg + c["cancelado"] + c["futuro"] + c["sem_registro"]
    ativos_est = {t[0].get("estudante") for t in x.ags if t[0].get("status") == "Ativo" and t[0].get("estudante")}
    media = round(c["realizado"] / len(ativos_est), 1) if ativos_est else None
    return _secao("add_percent", [
        _kpi("Percentual de faltas", _pct(c["falta"], reg), "faltas ÷ atendimentos com presença ou falta registrada", pct=True),
        _kpi("Percentual de cancelamentos", _pct(c["cancelado"], tot), "cancelados ÷ todos os atendimentos marcados para o período", pct=True),
        _kpi("Média de atendimentos por estudante", media, "realizados ÷ estudantes com casos ativos" if media is not None else "sem estudantes com casos ativos")],
        notas=["Conformidade com o CRP: indicador não calculado, pois o sistema não possui critério verificável para isso."],
        vazio=(tot == 0))


_FUNCS = {"pan_casos": _pan_casos, "pan_equipe": _pan_equipe, "pan_alocacao": _pan_alocacao, "pan_atividade": _pan_atividade,
          "ag_resumo": _ag_resumo, "ag_periodo": _ag_periodo, "ag_dias": _ag_dias, "est_tabela": _est_tabela,
          "pac_resumo": _pac_resumo, "pac_atend": _pac_atend, "evo_resumo": _evo_resumo, "sup_tabela": _sup_tabela,
          "ins_resumo": _ins_resumo, "ins_tempo": _ins_tempo, "pen_resumo": _pen_resumo, "add_percent": _add_percent}


def validar_indicadores(tipo, ids):
    """Lista final de indicadores (na ordem do relatório) ou ValueError."""
    if tipo == "completo":
        return list(IDS_VALIDOS)
    if tipo != "personalizado":
        raise ValueError("tipo de relatório inválido")
    if not isinstance(ids, list) or not ids:
        raise ValueError("selecione ao menos um indicador para gerar o relatório personalizado")
    if any(not isinstance(i, str) or i not in IDS_VALIDOS for i in ids):
        raise ValueError("indicador desconhecido na seleção")
    return [i for i in IDS_VALIDOS if i in set(ids)]


def gerar(dados, ids, ini, fim, agora):
    x = _Ctx(dados, ini, fim, agora)
    return [_FUNCS[i](x) for i in ids]


def catalogo():
    return [{"id": cid, "titulo": titulo, "indicadores": [{"id": i, "titulo": t} for i, t in itens]} for cid, titulo, itens in CATEGORIAS]
