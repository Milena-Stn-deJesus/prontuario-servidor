# -*- coding: utf-8 -*-
"""
Servidor do Prontuário Eletrônico (Serviço-Escola de Psicologia) — versão MongoDB.

O QUE ESSE ARQUIVO FAZ:
- Serve a página do site (psicare-site-v2.html).
- Guarda os dados de verdade no MongoDB (duas coleções: "casos" e "solicitacoes"),
  em vez de arquivos .json no disco. Isso permite que o banco de dados fique na
  nuvem (MongoDB Atlas) e seja acessado de qualquer lugar, não só deste computador.
- Expõe a mesma API HTTP de antes, para o navegador consultar e atualizar os dados:
    GET  /api/casos                -> devolve todos os casos
    POST /api/casos                -> cria um caso novo (técnico cadastra paciente)
    PUT  /api/casos/<id>            -> atualiza um caso (agenda, nova evolução, documento,
                                        primeira anamnese...); evoluções e anamnese já
                                        registradas são imutáveis no servidor, não só na tela
    GET  /api/inscricoes            -> DESCONTINUADA (410): inscrição e triagem são feitas fora do sistema
    POST /api/inscricoes            -> DESCONTINUADA (410)
    PUT  /api/inscricoes/<INS-...>  -> DESCONTINUADA (410); os dados antigos seguem no banco
    GET  /api/solicitacoes          -> devolve a fila de solicitações de prontuário
    POST /api/solicitacoes          -> cria uma nova solicitação (paciente pede o prontuário)
    PUT  /api/solicitacoes/<id>     -> atualiza uma solicitação (técnico libera o acesso)
    GET  /api/reagendamentos        -> devolve a fila de pedidos de reagendamento
    POST /api/reagendamentos        -> cria um novo pedido (paciente pede para reagendar)
    PUT  /api/reagendamentos/<id>   -> confirma uma nova data (equipe escolhe a data;
                                        dispara o e-mail de confirmação para o paciente)
    GET/PUT /api/notificacoes       -> avisos do usuário logado (o paciente só vê os do PRÓPRIO caso)
    GET  /api/meu-caso              -> (só paciente) status, próxima consulta e consultas futuras do PRÓPRIO
                                        caso, sem nenhum conteúdo clínico
    GET  /api/minhas-solicitacoes   -> (só paciente) as PRÓPRIAS solicitações de prontuário,
                                        com o status real (pendente/liberado)
    GET  /api/meu-prontuario        -> (só paciente) o prontuário completo do PRÓPRIO caso,
                                        só quando existe uma solicitação já liberada pela
                                        equipe (senão, 403 — a liberação é checada aqui,
                                        no servidor, não só escondendo o botão na tela)
    GET /api/relatorios/catalogo, POST /api/relatorios -> (só técnico) Relatórios Gerenciais: indicadores agregados por período, somente leitura
    GET/PUT /api/meu-perfil         -> (só estudante) corrige o PRÓPRIO nome/telefone (avisa o técnico) e informa a disponibilidade (dia x turno)
    POST /api/casos/<id>/agendamentos/<n>/comparecimento -> estudante registra presença/falta (PUT: técnico corrige, com justificativa)
    POST /api/casos/<id>/documentos          -> anexa documento (PDF/JPG/PNG/DOCX até 10 MB; arquivo real no GridFS)
    GET  /api/casos/<id>/documentos/<doc>/arquivo?modo=visualizar|baixar -> entrega o arquivo (auditado)
    GET  /api/casos/<id>/documentos/historico -> eventos dos documentos do caso (técnico, supervisor)
    POST /api/casos/<id>/documentos/<doc>/exclusao -> exclusão LÓGICA (desligada: DOCUMENTOS_EXCLUSAO_LOGICA=1 para ligar)
    POST /api/casos/<id>/exportacoes         -> gera o protocolo (#1001...) e audita a exportação do prontuário
    GET  /api/documentos/config              -> tipos, limite e se a exclusão lógica está habilitada
    (variável opcional DOCUMENTOS_QUOTA_MB: espaço máximo para documentos; padrão 300)
    POST /api/ativar-conta          -> (convite) cria a senha de uma conta profissional nova
    GET  /api/admin/resumo | profissionais | historico | minha-conta   -> (só admin_ti)
    POST /api/admin/profissionais   -> (só admin_ti) cria conta de técnico ou supervisor
    PUT  /api/admin/profissionais/<e-mail> | /api/admin/minha-conta     -> (só admin_ti)
    POST /api/login                 -> autentica e devolve um token de sessão
    POST /api/logout                -> invalida o token de sessão atual no servidor
    POST /api/recuperar-senha       -> recebe um e-mail, gera uma senha temporária
                                        de verdade e a envia por e-mail (nunca na
                                        resposta HTTP); resposta sempre genérica,
                                        exista ou não o e-mail na base

ENVIO DE E-MAIL (confirmação de reagendamento e recuperação de senha):
    Em ambos os casos, o servidor manda um e-mail de verdade — mas só se as
    variáveis de ambiente abaixo estiverem configuradas (senão, a ação em si
    é concluída normalmente no sistema — reagendamento confirmado, senha
    redefinida — só o e-mail não sai, e isso fica registrado no log do
    servidor):

        SMTP_HOST   -> endereço do servidor de e-mail (ex.: smtp.gmail.com)
        SMTP_PORT   -> porta (opcional, padrão 587)
        SMTP_USER   -> o e-mail que vai enviar (ex.: sua conta do Gmail)
        SMTP_PASS   -> a senha dessa conta — NUNCA a senha normal da conta, e
                       sim uma "senha de app" (no Gmail: Conta Google ->
                       Segurança -> Verificação em duas etapas -> Senhas de app)
        EMAIL_FROM  -> opcional; endereço que aparece como remetente (padrão: o
                       próprio SMTP_USER)

    ALTERNATIVA PARA O PLANO GRATUITO DO RENDER (que bloqueia SMTP): envio por
    API web, via Brevo. Configure no Render:
        BREVO_API_KEY   -> chave de API (v3) criada no painel do Brevo
        EMAIL_FROM      -> remetente já verificado no Brevo
        EMAIL_FROM_NOME -> opcional; nome exibido como remetente
    Se BREVO_API_KEY existir, ela é usada no lugar do SMTP.

    Assim como a MONGODB_URI, essas variáveis são configuradas no painel do
    Render (nunca escritas aqui no código).

COMO CONFIGURAR (antes de rodar pela primeira vez):
    1. Crie uma conta gratuita no MongoDB Atlas (https://www.mongodb.com/cloud/atlas)
       e um cluster gratuito (M0). No painel, clique em "Connect" -> "Drivers" e copie
       a "connection string" (algo como:
       mongodb+srv://usuario:senha@cluster0.xxxxx.mongodb.net/?retryWrites=true...)

    2. Essa connection string NUNCA deve ficar escrita dentro do código (é como uma
       senha). Em vez disso, ela é passada por uma "variável de ambiente" chamada
       MONGODB_URI. Para rodar no seu computador, no terminal, ANTES de rodar o
       server.py, defina a variável:

       No Windows (PowerShell):
           $env:MONGODB_URI = "sua-connection-string-aqui"
           python server.py

       No Windows (Prompt de Comando / cmd):
           set MONGODB_URI=sua-connection-string-aqui
           python server.py

       No Mac/Linux:
           export MONGODB_URI="sua-connection-string-aqui"
           python3 server.py

    3. Quando for hospedar no Render (ou outro serviço), a MONGODB_URI é configurada
       no painel do serviço, na seção de variáveis de ambiente — nunca no código.

    4. Instale a biblioteca que conversa com o MongoDB (só precisa fazer isso uma vez):
           pip install -r requirements.txt

COMO RODAR LOCALMENTE:
    1. Configure a variável de ambiente MONGODB_URI (passo acima).
    2. Rode:  python server.py
    3. Abra o navegador em: http://localhost:5000
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import sys
import time
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
import relatorios
import base64
import io
import zipfile

try:
    import certifi
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    from bson import ObjectId
    import gridfs
    from bson.errors import InvalidId
except ImportError:
    print("=" * 70)
    print(" ERRO: a biblioteca 'pymongo' não está instalada.")
    print(" Rode primeiro:  pip install -r requirements.txt")
    print("=" * 70)
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent
HTML_FILE = BASE_DIR / "psicare-site-v2.html"
# Narrações em áudio (Eleven Labs) das páginas Home e Inscrição. Só estes caminhos são servidos.
AUDIOS = {
    "/audio/ouvir-home.mp3": BASE_DIR / "audio" / "ouvir-home.mp3",
    "/audio/ouvir-inscricao.mp3": BASE_DIR / "audio" / "ouvir-inscricao.mp3",
}

PORT = int(os.environ.get("PORT", 5000))
MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME = os.environ.get("MONGODB_DB_NAME", "prontuario")

# Em quais sites (origens) o navegador pode chamar esta API via JavaScript.
# Antes, o servidor respondia "*" (qualquer site do mundo). Isso não afeta o
# próprio site (ele é servido por este mesmo servidor, então é "mesma origem"
# e nunca precisou de CORS liberado) — só impede que OUTRO site na internet
# use o navegador de alguém para ler/gravar nesta API escondido numa aba.
# Pode ser configurado pela variável de ambiente ALLOWED_ORIGIN se um dia o
# site for servido de outro domínio.
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://prontuario-servidor.onrender.com")

# Valores aceitos para o campo "status" de um caso e de uma solicitação.
# Antes não existia nenhuma validação: o servidor aceitava qualquer texto
# (incluindo nada), o que causava bugs como o painel mostrar "0 casos
# ativos" quando o status vinha gravado de um jeito ligeiramente diferente
# de "Ativo" (ex.: vazio, com espaço, ou outra palavra).
STATUS_CASO_VALIDOS = {"Ativo", "Encerrado"}
STATUS_SOLICITACAO_VALIDOS = {"pendente", "liberado"}
STATUS_REAGENDAMENTO_VALIDOS = {"pendente", "confirmado"}
EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# ---------------------------------------------------------------------------
# Envio de e-mail (confirmação de reagendamento)
#
# Só funciona se SMTP_HOST/SMTP_USER/SMTP_PASS estiverem configurados (veja as
# instruções no topo deste arquivo). Sem isso, a função abaixo não quebra nada
# — só avisa no log do servidor que o e-mail não foi enviado — porque confirmar
# a nova data no sistema não deve depender de o e-mail estar configurado.

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
try:
    sys.stdout.reconfigure(line_buffering=True)  # os logs aparecem na hora no painel do Render
except Exception:
    pass
EMAIL_FROM = os.environ.get("EMAIL_FROM", SMTP_USER)
ULTIMO_ERRO_EMAIL = {"motivo": ""}  # motivo (sem dados sigilosos) da última falha de envio, mostrado ao técnico
# Envio por API web (HTTPS) — funciona no plano gratuito do Render, que bloqueia SMTP.
# Serviço usado: Brevo (https://www.brevo.com). Precisa de BREVO_API_KEY e de EMAIL_FROM
# (um remetente já verificado no Brevo). Tem prioridade sobre o SMTP quando configurado.
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
EMAIL_API_URL = os.environ.get("EMAIL_API_URL", "https://api.brevo.com/v3/smtp/email")
EMAIL_FROM_NOME = os.environ.get("EMAIL_FROM_NOME", "Serviço-Escola de Psicologia FCMSCSP")


def _enviar_por_api(destinatario, assunto, corpo):
    """Envio via API HTTPS do Brevo. Nunca registra a chave nem o corpo do e-mail (que pode
    conter link de convite)."""
    import urllib.request, urllib.error
    if not EMAIL_FROM:
        print("[e-mail] EMAIL_FROM não configurado — e-mail NÃO enviado para %s" % destinatario)
        ULTIMO_ERRO_EMAIL["motivo"] = "A variável EMAIL_FROM não está configurada no servidor."
        return False
    dados = json.dumps({
        "sender": {"name": EMAIL_FROM_NOME, "email": EMAIL_FROM},
        "to": [{"email": destinatario}],
        "subject": assunto,
        "textContent": corpo,
    }).encode("utf-8")
    req = urllib.request.Request(EMAIL_API_URL, data=dados, method="POST", headers={
        "api-key": BREVO_API_KEY, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ULTIMO_ERRO_EMAIL["motivo"] = ""
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        dica = {400: "dados recusados — confira se EMAIL_FROM é um remetente verificado no Brevo",
                401: "chave de API inválida — gere outra no Brevo e cole em BREVO_API_KEY",
                403: "chave sem permissão de envio ou conta do Brevo ainda não liberada",
                429: "limite de envios do Brevo atingido"}.get(exc.code, "recusado pelo serviço de e-mail")
        try:
            detalhe = (json.loads(exc.read().decode("utf-8", "replace")) or {}).get("message", "")[:160]
        except Exception:
            detalhe = ""
        print("[e-mail] FALHA ao enviar para %s: a API de e-mail respondeu %s %s" % (destinatario, exc.code, detalhe))
        ULTIMO_ERRO_EMAIL["motivo"] = "O Brevo respondeu %s: %s%s." % (exc.code, dica, (" (" + detalhe + ")") if detalhe else "")
        return False
    except Exception as exc:
        print("[e-mail] FALHA ao enviar para %s: %s" % (destinatario, type(exc).__name__))
        ULTIMO_ERRO_EMAIL["motivo"] = "Não foi possível falar com o serviço de e-mail (%s)." % type(exc).__name__
        return False


def _enviar_email(destinatario, assunto, corpo):
    """Manda um e-mail de texto simples. Devolve True se enviou de verdade,
    False se não conseguiu (inclusive se o SMTP não estiver configurado)."""
    if BREVO_API_KEY:
        return _enviar_por_api(destinatario, assunto, corpo)
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        ULTIMO_ERRO_EMAIL["motivo"] = "O servidor não encontrou a variável BREVO_API_KEY (nem SMTP configurado)."
        print("[e-mail] SMTP não configurado — e-mail NÃO enviado para %s (assunto: %s)" % (destinatario, assunto))
        return False
    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = assunto
    msg["From"] = EMAIL_FROM
    msg["To"] = destinatario
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as servidor:
            servidor.starttls()
            servidor.login(SMTP_USER, SMTP_PASS)
            servidor.sendmail(EMAIL_FROM, [destinatario], msg.as_string())
        return True
    except Exception as exc:
        print("[e-mail] FALHA ao enviar para %s: %s" % (destinatario, exc))
        return False


def _enviar_confirmacao_reagendamento(destinatario, nome_paciente, nova_data):
    assunto = "Prontuário Eletrônico — sua consulta foi reagendada"
    corpo = (
        "Olá, %s!\n\n"
        "Sua consulta na Clínica-Escola de Psicologia foi reagendada.\n\n"
        "Nova data e horário: %s\n\n"
        "Em caso de dúvidas, entre em contato com a equipe pelo site.\n\n"
        "Este é um e-mail automático — não é necessário responder."
    ) % (nome_paciente or "paciente", nova_data)
    return _enviar_email(destinatario, assunto, corpo)


def _enviar_senha_temporaria(destinatario, nome, senha_temporaria):
    assunto = "Prontuário Eletrônico — nova senha de acesso"
    corpo = (
        "Olá, %s!\n\n"
        "Recebemos um pedido de redefinição de senha para sua conta.\n\n"
        "Sua nova senha temporária é: %s\n\n"
        "Use-a para entrar e, por segurança, recomendamos trocá-la depois do login.\n\n"
        "Se você não pediu essa redefinição, ignore este e-mail — sua senha "
        "antiga deixou de funcionar, então pode ser que outra pessoa tenha "
        "tentado acessar sua conta; avise a equipe da Clínica-Escola.\n\n"
        "Este é um e-mail automático — não é necessário responder."
    ) % (nome or "usuário(a)", senha_temporaria)
    return _enviar_email(destinatario, assunto, corpo)


def _gerar_senha_temporaria():
    """Gera uma senha temporária aleatória seguindo as mesmas regras exibidas
    na tela de 'criar nova senha' (maiúscula, número, caractere especial,
    pelo menos 6 caracteres) — para que, ao entrar, trocar a senha não seja
    obrigatório parecer "menos segura" que o próprio requisito do site."""
    alfabeto = "abcdefghjkmnpqrstuvwxyz23456789"
    especiais = "!@#$%*?"
    corpo = "".join(secrets.choice(alfabeto) for _ in range(6))
    return corpo[:3].upper() + corpo[3:] + str(secrets.randbelow(10)) + secrets.choice(especiais)

# ---------------------------------------------------------------------------
# Autenticação e autorização
#
# Antes, o servidor não tinha NENHUMA forma de login: a tela de login do site
# só verificava o e-mail/senha no próprio navegador (JavaScript), e qualquer
# pessoa podia chamar a API diretamente (sem passar pela tela) e ler ou
# alterar o prontuário de qualquer paciente. Esta seção implementa login de
# verdade no servidor: quem chama a API precisa mandar um token de sessão
# válido, obtido em POST /api/login, e cada rota só aceita os papéis
# (paciente/estudante/técnico/supervisor) que fazem sentido para ela.
#
# As contas abaixo são as mesmas contas fixas de demonstração que o site já
# usava (mesmos e-mails e senhas que apareciam no JavaScript do navegador) —
# a diferença é que agora elas são validadas aqui, no servidor, e a senha
# nunca é guardada nem comparada como texto puro (veja _hash_senha).
# Criar contas de verdade (um cadastro real de equipe/paciente) é a próxima
# etapa, já registrada na lista de pendências do projeto.

AVISO_PRIVACIDADE_VERSAO = "1.0"  # versão do Aviso de Privacidade exibida no site
SENHA_SALT = os.environ.get("SENHA_SALT", "prontuario-fcmscsp-salt-fixo-2026")


def _hash_senha(senha):
    """Deriva um hash da senha com PBKDF2 (não guarda nem compara a senha em
    texto puro). Usa só a biblioteca padrão do Python (hashlib), sem precisar
    instalar nada além do que já está em requirements.txt."""
    derivado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), SENHA_SALT.encode("utf-8"), 200_000)
    return derivado.hex()


def _conta(role, nome, senha, ra=None):
    conta = {"role": role, "nome": nome, "senha_hash": _hash_senha(senha)}
    if ra:
        # RA (registro acadêmico): identificador único do estudante.
        conta["ra"] = ra
    return conta


CONTAS = {
    # equipe
    "tecnico@exemplo.com": _conta("tecnico", "Fernando Ricci", "senha123"),
    "supervisor@exemplo.com": _conta("supervisor", "Dra. Patrícia Novaes", "senha123"),
    "estudante@exemplo.com": _conta("estudante", "Ana Beatriz Lima", "senha123", ra="202501117"),
    # primeiro acesso da equipe (senha temporária = RA/matrícula)
    "novo.tecnico@exemplo.com": _conta("tecnico", "Novo Técnico", "202601001"),
    "novo.supervisor@exemplo.com": _conta("supervisor", "Novo Supervisor", "202601002"),
    "novo.estudante@exemplo.com": _conta("estudante", "Novo Estudante", "202601234", ra="202601234"),
    # paciente
    "paciente@exemplo.com": _conta("paciente", "Maria Fernanda Alves", "senha123"),
    "carlos@exemplo.com": _conta("paciente", "Carlos Eduardo Mendes", "senha123"),
    # primeiro acesso do paciente (senha temporária = CPF)
    "novo@exemplo.com": _conta("paciente", "Pedro Henrique Souza", "11122233344"),
}

# Estudantes que aparecem nos casos de demonstração mas ainda não têm conta de
# acesso. O RA é o identificador único do estudante (nome -> RA).
ESTUDANTES_SEM_CONTA = {
    "Rafael Augusto Pires": "202501142",
}


def _lista_estudantes():
    """Cadastro de estudantes, em ordem alfabética: os de demonstração escritos no
    código (nome + RA) somados aos cadastrados pelo técnico na coleção "estudantes".
    Um documento em "estudantes" com o mesmo RA de um estudante de demonstração só
    sobrepõe telefone e situação (ativo/inativo)."""
    base = {}
    for email, conta in CONTAS.items():
        if conta.get("role") == "estudante" and conta.get("ra"):
            base[conta["ra"]] = {"nome": conta["nome"], "ra": conta["ra"], "email": email, "origem": "demonstração"}
    for nome, ra in ESTUDANTES_SEM_CONTA.items():
        base.setdefault(ra, {"nome": nome, "ra": ra, "email": "", "origem": "demonstração"})
    for d in estudantes_col.find({}):
        e = base.setdefault(d["_id"], {"nome": d.get("nome", ""), "ra": d["_id"], "email": d.get("email", ""), "origem": "cadastro"})
        e["telefone"] = d.get("telefone", "")
        e["ativo"] = d.get("ativo", True)
    for e in base.values():
        e.setdefault("telefone", "")
        e.setdefault("ativo", True)
    return sorted(base.values(), key=lambda e: e["nome"].casefold())


def _estudante_da_sessao(sessao):
    """Cadastro (nome, RA, e-mail, telefone) do estudante LOGADO — sempre ele mesmo, nunca outro RA."""
    email = (sessao.get("email") or "").strip().casefold()
    lista = _lista_estudantes()
    est = next((e for e in lista if email and (e.get("email") or "").strip().casefold() == email), None)
    if est is None:
        est = next((e for e in lista if e["nome"] == sessao.get("nome")), None)
    return est


def _perfil_do_estudante(est):
    d = disp_estudantes_col.find_one({"_id": est["ra"]}) or {}
    v = vinculos_col.find_one({"_id": est["ra"]}) or {}
    return {"nome": est["nome"], "ra": est["ra"], "email": est.get("email", ""), "telefone": est.get("telefone", ""),
            "supervisor": v.get("supervisor", "") if v.get("ativo") else "",
            "disponibilidade": d.get("disponibilidade") or [],
            "disponibilidade_atualizada_em": d.get("atualizado_em_br", ""),
            "dados_conferidos_em": d.get("dados_conferidos_em_br", ""),
            "primeiro_acesso_concluido": bool(d.get("dados_conferidos_em_br"))}


def _ra_inativo(ra):
    d = estudantes_col.find_one({"_id": ra}) if ra else None
    return bool(d and d.get("ativo") is False)


SITUACAO_CONTA = {"ativa": "ativada", "convite_pendente": "pendente de ativação", "desativada": "desativada"}


def _lista_estudantes_com_disponibilidade(gestao=False):
    """Estudantes + disponibilidade semanal. Para o técnico (gestao=True) inclui também
    e-mail, telefone, vínculo, situação da conta e nº de pacientes ativos; o supervisor
    continua vendo só nome, RA, situação e disponibilidade."""
    guardado = {d["_id"]: d for d in disp_estudantes_col.find({})}
    if gestao:
        vinc = {d["_id"]: d for d in vinculos_col.find({})}
        contas = {d["_id"]: d for d in contas_col.find({"role": "estudante"})}
        ativos = {}
        for c in casos_col.find({}):
            if c.get("status") == "Ativo" and c.get("estudante"):
                ativos[c["estudante"]] = ativos.get(c["estudante"], 0) + 1
    out = []
    for e in _lista_estudantes():
        d = guardado.get(e["ra"]) or {}
        item = {"nome": e["nome"], "ra": e["ra"], "ativo": e["ativo"],
                "disponibilidade": d.get("disponibilidade") or [],
                "disponibilidade_atualizada_em": d.get("atualizado_em_br", "")}
        if gestao:
            v = vinc.get(e["ra"]) or {}
            conta = contas.get(e["email"]) if e["email"] else None
            if conta:
                sit = SITUACAO_CONTA.get(conta.get("status"), conta.get("status", ""))
                expirado = bool(conta.get("status") == "convite_pendente" and (conta.get("convite") or {}).get("expira_em", 0) < time.time())
            else:
                sit, expirado = ("ativada" if e["email"] else "sem conta de acesso"), False
            if not e["ativo"] and sit == "ativada":
                sit = "desativada"
            item.update(email=e["email"], telefone=e["telefone"], origem=e["origem"],
                        supervisor=v.get("supervisor", "") if v.get("ativo") else "",
                        situacao_conta=sit, convite_expirado=expirado,
                        pacientes_ativos=ativos.get(e["nome"], 0))
        out.append(item)
    return out


def _gravar_estudante(ra, campos):
    """Grava campos do estudante (cria o documento se for a primeira vez, como nos
    estudantes de demonstração, que só ganham registro quando algo é alterado)."""
    if estudantes_col.update_one({"_id": ra}, {"$set": campos}).matched_count == 0:
        estudantes_col.insert_one({"_id": ra, **campos})


def _gravar_vinculo(ra, nome, sup, por):
    """Define (ou encerra, com sup="") o vínculo ativo do estudante, preservando o histórico."""
    doc = vinculos_col.find_one({"_id": ra})
    atual = doc.get("supervisor", "") if doc and doc.get("ativo") else ""
    if sup == atual:
        return atual
    hist = list((doc or {}).get("historico") or [])
    agora = _agora_br()
    if atual:
        hist.append({"supervisor": atual, "de": doc.get("desde", ""), "ate": agora, "por": por})
    novo = {"ra": ra, "estudante": nome, "supervisor": sup, "ativo": bool(sup), "desde": agora if sup else "", "historico": hist}
    if vinculos_col.update_one({"_id": ra}, {"$set": novo}).matched_count == 0:
        vinculos_col.insert_one({"_id": ra, **novo})
    return atual


def _validar_estudante(body, completo=True):
    """Devolve (dados, erro). completo=False valida só os campos enviados (edição)."""
    dados = {}
    if completo or "nome" in body:
        nome = " ".join(str(body.get("nome", "")).split())
        if not 5 <= len(nome) <= 120 or " " not in nome:
            return None, "informe o nome completo do estudante"
        dados["nome"] = nome
    if completo:
        email = str(body.get("email", "")).strip().lower()
        if not EMAIL_REGEX.match(email) or len(email) > 120:
            return None, "informe um e-mail válido"
        dados["email"] = email
        ra = str(body.get("ra", "")).strip()
        if not re.match(r"^\d{4,15}$", ra):
            return None, "informe a matrícula/RA (somente números, de 4 a 15 dígitos)"
        dados["ra"] = ra
    if completo or "telefone" in body:
        tel = str(body.get("telefone", "")).strip()
        digitos = re.sub(r"\D", "", tel)
        if tel and not 10 <= len(digitos) <= 11:
            return None, "telefone inválido (use DDD + número)"
        dados["telefone"] = tel
    return dados, None


def _resumo_estudante(ra):
    return next((x for x in _lista_estudantes_com_disponibilidade(True) if x["ra"] == ra), None)


NOTA_MAX = 2000


# ---------------------------------------------------------------------------
# Vínculos de supervisão, alocação de pacientes e agendamentos (painel do técnico)
#
# FONTE DE VERDADE dos vínculos ativos: a coleção "vinculos_supervisao" (um
# documento por estudante, chave = RA, com o supervisor ATUAL e o histórico dos
# anteriores). O campo "supervisor"/"estudante" de cada caso continua sendo o
# vínculo daquele paciente (usado por prontuário, agenda e permissões) e nunca é
# reescrito por causa de mudança de vínculo: casos históricos ficam como estão.
# Os casos antigos servem apenas de REFERÊNCIA para o técnico validar vínculos.
# ---------------------------------------------------------------------------
import datetime as _dt
import threading

# Uma operação de alocação/agenda por vez (o servidor é um processo único):
# impede que dois cliques simultâneos aloquem dois estudantes ou marquem o
# mesmo horário duas vezes.
TRAVA_OPERACOES = threading.Lock()
ALOC_AGUARDANDO = "Aguardando alocação"
ALOC_ALOCADO = "Alocado"
ST_AG_CANCELADA = "Cancelada"


def _lista_supervisores_ativos():
    nomes = {}
    for conta in CONTAS.values():
        if conta.get("role") == "supervisor":
            nomes[conta["nome"]] = ""
    for d in contas_col.find({"role": "supervisor"}):
        if d.get("status") == "desativada":
            nomes.pop(d.get("nome"), None)
        elif d.get("nome"):
            nomes[d["nome"]] = d.get("crp") or ""
    return [{"nome": n, "crp": nomes[n]} for n in sorted(nomes, key=lambda x: x.casefold())]


def _estudante_por_ra(ra):
    for e in _lista_estudantes():
        if e["ra"] == ra:
            return e
    return None


def _painel_vinculos():
    """Estudantes com o vínculo ativo + referências a validar (sem alterar nada)."""
    com_conta = {c["nome"] for c in CONTAS.values() if c.get("role") == "estudante"}
    com_conta |= {d["nome"] for d in contas_col.find({"role": "estudante"})}
    docs = {d["_id"]: d for d in vinculos_col.find({})}
    estudantes = []
    for e in _lista_estudantes():
        d = docs.get(e["ra"]) or {}
        ativo = bool(d.get("ativo"))
        estudantes.append({
            "ra": e["ra"], "nome": e["nome"], "ativo": e.get("ativo", True), "tem_conta": e["nome"] in com_conta,
            "supervisor": d.get("supervisor", "") if ativo else "",
            "desde": d.get("desde", "") if ativo else "",
            "historico": d.get("historico") or [],
        })
    por_nome = {e["nome"]: e for e in estudantes}
    pares, inconsistencias = {}, []
    for c in casos_col.find({}):
        if c.get("status") == "Encerrado":
            continue
        est, sup = (c.get("estudante") or "").strip(), (c.get("supervisor") or "").strip()
        base = {"caso_id": c["_id"], "paciente": c.get("paciente", ""), "estudante": est, "supervisor": sup}
        if not sup:
            inconsistencias.append({**base, "tipo": "caso_sem_supervisor", "mensagem": "caso ativo sem supervisor definido"})
            continue
        if not est:
            continue
        v = por_nome.get(est)
        if v is None:
            inconsistencias.append({**base, "tipo": "estudante_sem_cadastro", "mensagem": "estudante do caso não consta no cadastro de estudantes"})
        elif not v["supervisor"]:
            inconsistencias.append({**base, "tipo": "estudante_sem_vinculo", "mensagem": "estudante sem vínculo ativo com supervisor"})
            pares[(v["ra"], est, sup)] = pares.get((v["ra"], est, sup), 0) + 1
        elif v["supervisor"] != sup:
            inconsistencias.append({**base, "tipo": "vinculo_divergente", "vinculo_supervisor": v["supervisor"],
                                    "mensagem": "supervisor do caso difere do vínculo ativo do estudante"})
    sugestoes = [{"ra": ra, "estudante": est, "supervisor": sup, "casos": n} for (ra, est, sup), n in sorted(pares.items())]
    return {"estudantes": estudantes, "sugestoes": sugestoes, "inconsistencias": inconsistencias}


def _data_para_br(valor):
    """Aceita 'AAAA-MM-DD' ou 'DD/MM/AAAA'; devolve 'DD/MM/AAAA' válida ou None."""
    v = str(valor or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", v)
    if m:
        a, mm, d = (int(x) for x in m.groups())
    else:
        m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", v)
        if not m:
            return None
        d, mm, a = (int(x) for x in m.groups())
    try:
        _dt.date(a, mm, d)
    except ValueError:
        return None
    return "%02d/%02d/%04d" % (d, mm, a)


def _hora_para_br(valor):
    m = re.match(r"^([01]\d|2[0-3])[:h]([0-5]\d)$", str(valor or "").strip())
    return "%sh%s" % (m.group(1), m.group(2)) if m else None


def _norm_hora(h):
    return str(h or "").replace(":", "h")


def _avisar_estudante(caso, tipo, detalhe=""):
    """Aviso interno ao estudante responsável (sem nome de paciente nem dados clínicos)."""
    est = ((caso or {}).get("estudante") or "").strip()
    if not est:
        return
    notificacoes_col.insert_one({"_id": "nf-" + secrets.token_hex(6), "tipo": tipo, "destinatario": est,
                                 "caso_id": caso["_id"], "evolucao_idx": None, "detalhe": detalhe,
                                 "criada_em": time.time(), "criada_em_br": _agora_br(), "lida": False})


def _avisar_supervisor(nome, tipo, detalhe="", caso_id=""):
    """Aviso interno ao supervisor (pelo nome da conta). Nunca leva nome de paciente nem conteúdo clínico."""
    nome = (nome or "").strip()
    if not nome:
        return
    notificacoes_col.insert_one({"_id": "nf-" + secrets.token_hex(6), "tipo": tipo, "para": "supervisor", "destinatario": nome,
                                 "caso_id": caso_id or "", "evolucao_idx": None, "detalhe": detalhe,
                                 "criada_em": time.time(), "criada_em_br": _agora_br(), "lida": False})


# ---------------------------------------------------------------------------
# Comparecimento (presença/falta) — registrado no PRÓPRIO agendamento, para agenda e prontuário
# compartilharem o mesmo dado. Nunca cria evolução, nunca encerra caso nem retira vaga.
# ---------------------------------------------------------------------------
COMP_SITUACOES = ("compareceu", "faltou")
COMP_JUSTIFICATIVA_MIN, COMP_JUSTIFICATIVA_MAX = 5, 300
COMP_MSG_FALTAS = {
    2: "Paciente com duas faltas consecutivas. Recomenda-se entrar em contato para verificar a continuidade do acompanhamento. Uma nova falta consecutiva poderá resultar na perda da vaga.",
    3: "Paciente atingiu três faltas consecutivas. Verificar a aplicação da regra institucional de perda da vaga.",
}


def _chave_ag(ag):
    """((ano, mês, dia), (hora, minuto)) do agendamento, ou None se a data não for válida."""
    d = _parse_data_br(ag.get("data"))
    if not d:
        return None
    m = re.match(r"^(\d{1,2})[:h](\d{2})", str(ag.get("hora") or ""))
    return (d, (int(m.group(1)), int(m.group(2))) if m else (0, 0))


def _agora_chave():
    t = time.gmtime(time.time() - 3 * 3600)  # horário de Brasília
    return ((t.tm_year, t.tm_mon, t.tm_mday), (t.tm_hour, t.tm_min))


def _ag_iniciou(ag):
    k = _chave_ag(ag)
    return k is not None and k <= _agora_chave()


def _faltas_consecutivas(caso):
    """Agendamentos que formam a sequência atual de faltas (do mais recente para trás). Só contam atendimentos
    com comparecimento registrado: cancelados, futuros e pendentes são ignorados (não são falta); uma presença
    interrompe a sequência."""
    itens = []
    for ag in (caso.get("agendamentos") or []):
        if ag.get("status") == ST_AG_CANCELADA or not ag.get("comparecimento") or _chave_ag(ag) is None:
            continue
        itens.append((_chave_ag(ag), ag))
    itens.sort(key=lambda x: x[0])
    seq = []
    for _, ag in reversed(itens):
        if ag["comparecimento"].get("situacao") == "faltou":
            seq.append(ag)
        else:
            break
    return seq


def _avaliar_faltas(caso):
    """Gera (uma única vez por evento) o aviso de 2ª e de 3ª falta consecutiva ao técnico e ao supervisor do caso."""
    seq = _faltas_consecutivas(caso)
    n = len(seq)
    if n not in (2, 3):
        return 0
    cid = caso["_id"]
    tipo = "faltas_%d" % n
    chave = "%d:%s %s" % (n, seq[-1].get("data"), seq[-1].get("hora"))  # identifica a sequência pela 1ª falta dela
    base = {"tipo": tipo, "caso_id": cid, "evento": chave, "evolucao_idx": None, "detalhe": caso.get("paciente", ""),
            "prioridade": "alta" if n == 3 else "normal", "criada_em": time.time(), "criada_em_br": _agora_br(), "lida": False}
    if not notificacoes_col.find_one({"para": "tecnico", "tipo": tipo, "caso_id": cid, "evento": chave}):
        notificacoes_col.insert_one({"_id": "nf-" + secrets.token_hex(6), "para": "tecnico", "destinatario": "", **base})
    sup = (caso.get("supervisor") or "").strip()
    if sup and not notificacoes_col.find_one({"para": "supervisor", "destinatario": sup, "tipo": tipo, "caso_id": cid, "evento": chave}):
        notificacoes_col.insert_one({"_id": "nf-" + secrets.token_hex(6), "para": "supervisor", "destinatario": sup, **base})
    return n


def _avisar_documento_anexado(caso, meta, sessao):
    """Documento novo no prontuário: avisa as outras duas pessoas do trio (aluno responsável, supervisor do caso,
    psicólogo técnico) — nunca quem anexou. Falha de aviso não desfaz o envio."""
    try:
        papel = sessao["role"]
        base = {"tipo": "documento_anexado", "caso_id": caso["_id"], "evolucao_idx": None, "documento_id": meta["_id"],
                "criada_em": time.time(), "criada_em_br": _agora_br(), "lida": False}
        resumo = "%s, anexado por %s" % (meta["tipo_doc"], meta["enviado_por_nome"])
        est = (caso.get("estudante") or "").strip()
        if papel != "estudante" and est:
            notificacoes_col.insert_one({"_id": "nf-" + secrets.token_hex(6), "destinatario": est, "detalhe": resumo, **base})
        sup = (caso.get("supervisor") or "").strip()
        if papel != "supervisor" and sup:
            notificacoes_col.insert_one({"_id": "nf-" + secrets.token_hex(6), "para": "supervisor", "destinatario": sup,
                                         "detalhe": "%s (%s)" % (caso.get("paciente", ""), resumo), **base})
        if papel != "tecnico":
            notificacoes_col.insert_one({"_id": "nf-" + secrets.token_hex(6), "para": "tecnico", "destinatario": "",
                                         "detalhe": "%s (%s)" % (caso.get("paciente", ""), resumo), **base})
    except Exception as exc:
        print("ERRO (aviso de documento): %s" % exc)


def distribuicao_supervisor_ativa():
    """Distribuição de pacientes pelo supervisor: desligada, até a aprovação institucional.
    Só liga com DISTRIBUICAO_SUPERVISOR=1 no ambiente."""
    return os.environ.get("DISTRIBUICAO_SUPERVISOR", "").strip().lower() in ("1", "true", "sim", "on")


def _painel_do_supervisor(nome):
    """Dados do painel do supervisor logado: só os estudantes vinculados a ELE e os casos desses estudantes."""
    meus = [e for e in _painel_vinculos()["estudantes"] if e["supervisor"] == nome]
    nomes = {e["nome"] for e in meus}
    casos_por_est = {n: [] for n in nomes}
    for c in casos_col.find({}):
        est = (c.get("estudante") or "").strip()
        if est in casos_por_est and (c.get("supervisor") or "").strip() == nome:
            casos_por_est[est].append(c)
    out = []
    for e in meus:
        lista = casos_por_est.get(e["nome"], [])
        out.append({"ra": e["ra"], "nome": e["nome"], "ativo": e["ativo"], "desde": e["desde"],
                    "casos": [{"id": c["_id"], "paciente": c.get("paciente", ""), "status": c.get("status", ""),
                               "atendimentos": len(c.get("agendamentos") or [])} for c in lista],
                    "casos_ativos": sum(1 for c in lista if c.get("status") == "Ativo"),
                    "casos_encerrados": sum(1 for c in lista if c.get("status") == "Encerrado")})
    return {"supervisor": nome, "estudantes": out, "distribuicao_ativa": distribuicao_supervisor_ativa()}


def _avisar_supervisor_do_caso(caso, tipo, detalhe=""):
    _avisar_supervisor((caso or {}).get("supervisor"), tipo, detalhe, (caso or {}).get("_id", ""))


def _avisar_tecnico(tipo, detalhe):
    """Aviso interno para o psicólogo técnico (sem dados clínicos)."""
    notificacoes_col.insert_one({"_id": "nf-" + secrets.token_hex(6), "tipo": tipo, "para": "tecnico", "destinatario": "",
                                 "caso_id": "", "evolucao_idx": None, "detalhe": detalhe,
                                 "criada_em": time.time(), "criada_em_br": _agora_br(), "lida": False})


def _dados_para_relatorio():
    """Lê (sem alterar nada) o que o módulo de relatórios precisa. Só agregados saem daqui para o navegador."""
    casos = list(casos_col.find({}))
    for c in casos:
        c["_id"] = str(c["_id"])
    return {
        "casos": casos,
        "estudantes": _lista_estudantes_com_disponibilidade(True),
        "supervisores": _lista_supervisores_ativos(),
        "inscricoes": list(inscricoes_col.find({})),
        "solicitacoes": list(solicitacoes_col.find({})),
        "reagendamentos": list(reagendamentos_col.find({})),
        "notas": [{"data": n.get("criado_em_br", "")} for n in notas_col.find({})],
        "faltas_consecutivas": {c["_id"]: len(_faltas_consecutivas(c)) for c in casos},
    }


def _proxima_consulta_remarcavel(caso):
    """Índice da próxima consulta futura 'Confirmada' sem comparecimento, ou None."""
    hoje = _parse_data_br(_hoje_br())
    melhor = None
    for i, a in enumerate((caso or {}).get("agendamentos") or []):
        if a.get("status") != "Confirmada" or a.get("comparecimento"):
            continue
        d = _parse_data_br(a.get("data"))
        if not d or d < hoje:
            continue
        chave = (d, _norm_hora(a.get("hora")))
        if melhor is None or chave < melhor[0]:
            melhor = (chave, i)
    return melhor[1] if melhor else None


def _avisar_paciente(caso, tipo, detalhe="", chave=""):
    """Aviso interno ao PACIENTE, ligado ao id do caso (nunca ao nome). O conteúdo é só data/horário/
    local de um atendimento ou o andamento de uma solicitação — nenhum dado clínico. Não repete um aviso
    idêntico que o paciente ainda não leu. Uma falha aqui nunca desfaz a operação que já foi confirmada."""
    cid = (caso or {}).get("_id")
    if not cid:
        return
    evento = str(chave or detalhe)
    try:
        if notificacoes_col.find_one({"para": "paciente", "tipo": tipo, "caso_id": cid, "evento": evento, "lida": False}):
            return
        notificacoes_col.insert_one({"_id": "nf-" + secrets.token_hex(6), "tipo": tipo, "para": "paciente", "destinatario": "",
                                     "caso_id": cid, "evolucao_idx": None, "detalhe": detalhe, "evento": evento,
                                     "criada_em": time.time(), "criada_em_br": _agora_br(), "lida": False})
    except PyMongoError as exc:
        print("[aviso ao paciente] não foi possível gravar (%s): %s" % (tipo, exc), flush=True)


def _agendamentos_do_paciente(caso):
    """Consultas de hoje em diante, só com o que o paciente já vê (data, hora, local, situação)."""
    hoje = _parse_data_br(_hoje_br())
    itens = []
    for ag in (caso.get("agendamentos") or []):
        chave = _parse_data_br(ag.get("data", ""))
        if chave is None or (hoje is not None and chave < hoje):
            continue
        itens.append((chave, _norm_hora(ag.get("hora")), {"data": ag.get("data", ""), "hora": ag.get("hora", ""),
                                                          "local": ag.get("local", ""), "status": ag.get("status", "")}))
    itens.sort(key=lambda t: (t[0], t[1]))
    return [i[2] for i in itens]


def _avisos_convites_expirados():
    """Gera (uma única vez por convite) o aviso de convite vencido sem ativação."""
    agora = time.time()
    for d in contas_col.find({"status": "convite_pendente"}):
        cv = d.get("convite") or {}
        if cv.get("expira_em", agora + 1) < agora and not cv.get("aviso_expirado"):
            with TRAVA_OPERACOES:
                atual = contas_col.find_one({"_id": d["_id"]}) or {}
                if atual.get("status") != "convite_pendente" or (atual.get("convite") or {}).get("aviso_expirado"):
                    continue
                cv2 = dict(atual.get("convite") or {}); cv2["aviso_expirado"] = True
                contas_col.update_one({"_id": d["_id"], "status": "convite_pendente"}, {"$set": {"convite": cv2}})
            if True:
                funcao = FUNCOES_PROFISSIONAIS.get(d.get("role")) or (d.get("role") or "conta")
                _avisar_tecnico("convite_expirado", "%s (%s)" % (d.get("nome") or d["_id"], funcao))


def _conflito_agenda(data, hora, caso_id, estudante, ignorar=None):
    """Devolve a mensagem de conflito (mesmo paciente ou mesmo estudante no mesmo
    dia e horário) ou None. Não inventa duração nem intervalo: só coincidência exata."""
    for c in casos_col.find({}):
        for i, a in enumerate(c.get("agendamentos") or []):
            if ignorar == (c["_id"], i) or a.get("status") == ST_AG_CANCELADA:
                continue
            if a.get("data") != data or _norm_hora(a.get("hora")) != hora:
                continue
            if c["_id"] == caso_id:
                return "este paciente já tem um atendimento nesse dia e horário"
            if estudante and c.get("estudante") == estudante:
                return "o estudante já tem um atendimento nesse dia e horário (paciente %s)" % c.get("paciente", "")
    return None


def _futuros_ativos(caso):
    hoje = _parse_data_br(_hoje_br())
    return sum(1 for a in (caso.get("agendamentos") or [])
               if a.get("status") == "Confirmada" and (_parse_data_br(a.get("data")) or (0, 0, 0)) >= hoje)


# Sessões ativas: token -> {"email", "role", "nome", "criado_em"}. Guardadas só
# na memória do processo (zeram se o servidor reiniciar) — suficiente para um
# protótipo acadêmico; um sistema maior guardaria isso no próprio MongoDB.
SESSOES = {}
SESSAO_DURACAO_SEGUNDOS = 8 * 60 * 60  # 8 horas

# Limite de tentativas de login por e-mail, pra dificultar um ataque de força
# bruta (antes não existia nenhum limite: dava pra tentar senha infinitas
# vezes). email -> {"falhas": int, "bloqueado_ate": timestamp|None}
TENTATIVAS_LOGIN = {}
MAX_TENTATIVAS = 6
BLOQUEIO_SEGUNDOS = 5 * 60  # 5 minutos

# Limite de pedidos de recuperação de senha por e-mail, pra dificultar que
# alguém use essa rota pra descobrir quais e-mails têm conta ou pra floodar
# a caixa de entrada de alguém. email -> {"pedidos": int, "bloqueado_ate": timestamp|None}
TENTATIVAS_RECUPERACAO = {}
MAX_PEDIDOS_RECUPERACAO = 3
BLOQUEIO_RECUPERACAO_SEGUNDOS = 10 * 60  # 10 minutos

PAPEIS_CASOS = {"tecnico", "supervisor", "estudante"}
# Perfil da Administração de TI: só gerencia contas profissionais. Não está em
# NENHUM dos conjuntos de papéis acima nem em nenhum outro usado pelas rotas
# clínicas — como cada rota só aceita os papéis listados para ela, esse perfil
# é negado por padrão em tudo que é clínico (pacientes, estudantes, prontuários,
# inscrições, triagem, agendas, solicitações).
PAPEIS_ADMIN = {"admin_ti"}
PAPEIS_SOLICITACOES_LEITURA = {"tecnico", "supervisor"}
# Instruções, seção 9: o acesso do paciente ao prontuário é liberado SOMENTE pelo
# psicólogo técnico; e agendamentos/reagendamentos são do técnico (único perfil).
PAPEIS_SOLICITACOES_ESCRITA = {"tecnico"}

if not MONGODB_URI:
    print("=" * 70)
    print(" ERRO: a variável de ambiente MONGODB_URI não foi configurada.")
    print(" Veja as instruções no topo deste arquivo (server.py) sobre como")
    print(" definir a connection string do MongoDB Atlas antes de rodar.")
    print("=" * 70)
    sys.exit(1)

print("Conectando ao MongoDB...")
# tlsCAFile=certifi.where() -> usa uma lista de certificados de segurança
# atualizada (em vez da que já vem pronta em alguns servidores na nuvem,
# que às vezes está desatualizada e causa erro de handshake SSL/TLS).
client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000, tlsCAFile=certifi.where())
try:
    client.admin.command("ping")
except PyMongoError as exc:
    print("=" * 70)
    print(" ERRO: não foi possível conectar ao MongoDB com a MONGODB_URI fornecida.")
    print(" Verifique: usuário/senha corretos, IP liberado no Atlas (Network Access)")
    print(" e se a connection string foi copiada corretamente.")
    print(" Detalhe técnico: %s" % exc)
    print("=" * 70)
    sys.exit(1)

db = client[DB_NAME]
casos_col = db["casos"]
solicitacoes_col = db["solicitacoes"]
reagendamentos_col = db["reagendamentos"]
# Inscrições: o formulário de inscrição é um documento externo (tipo Google
# Forms); o psicólogo técnico registra aqui cada resposta que chegou, e a partir
# daí ela segue o fluxo Recebido -> Analisado -> Triagem -> Cadastro.
inscricoes_col = db["inscricoes"]
# Contas profissionais criadas pela Administração de TI (técnico e supervisor) e
# a própria conta de administração. As contas de demonstração continuam no
# dicionário CONTAS; o login consulta CONTAS primeiro e, se o e-mail não estiver
# lá, esta coleção — é o mesmo login, com mais uma fonte de contas.
contas_col = db["contas"]
# Histórico das operações administrativas (criar, corrigir, desativar...). Nunca
# guarda senha, token nem link de convite.
historico_admin_col = db["historico_admin"]
disp_estudantes_col = db["disponibilidade_estudantes"]
vinculos_col = db["vinculos_supervisao"]  # fonte de verdade dos vínculos ativos supervisor <-> estudante
estudantes_col = db["estudantes"]  # estudantes cadastrados pelo técnico (os de demonstração só ganham registro ao serem alterados)
notas_col = db["notas_acompanhamento"]  # notas do técnico sobre evoluções (só acréscimo; nunca editadas nem apagadas)
notificacoes_col = db["notificacoes"]  # avisos internos (sem dados clínicos)
# Trilha de auditoria (achado da auditoria de segurança — item pendente que
# havia sido esquecido no relatório anterior): registra quem fez o quê e
# quando, numa coleção própria, consultável depois. Antes, o servidor só
# imprimia algumas linhas soltas no log do processo (ex.: pedido de
# recuperação de senha) — nada era gravado de forma durável, e a maioria das
# ações (login, abrir a lista de casos, alterar um caso, tentar acessar caso
# de outra pessoa) não deixava rastro nenhum. Nunca grava senha nem conteúdo
# clínico (anamnese/evolução) — só metadados do acesso.
auditoria_col = db["auditoria"]
# Documentos anexados aos casos: o arquivo fica no GridFS (privado, no próprio MongoDB; só o servidor lê, depois de
# checar a permissão) e os metadados aqui. Nada é apagado fisicamente: a exclusão, quando habilitada, é lógica.
documentos_col = db["documentos"]
# Histórico de eventos dos documentos (envio, visualização, download, exclusão lógica). Só acréscimo: não existe rota
# para editar nem apagar. Nunca guarda conteúdo clínico nem o conteúdo do arquivo.
documentos_eventos_col = db["documentos_eventos"]
# Exportações do prontuário: o protocolo (#1001, #1002...) nasce aqui, no servidor, e cada exportação fica auditada.
exportacoes_col = db["exportacoes"]
documentos_fs = gridfs.GridFS(db, collection="documentos_arquivos")
print("Conectado ao MongoDB! Banco: %s" % DB_NAME)


def _registrar_auditoria(sessao, acao, caso_id=None, resultado="sucesso", detalhe=None):
    """Grava uma linha na trilha de auditoria. 'sessao' pode ser a sessão
    autenticada (dict com email/nome/role) ou, numa tentativa de login que
    falhou, um dict parcial só com o e-mail digitado."""
    doc = {
        "quando": time.time(),
        "usuario_email": (sessao or {}).get("email"),
        "usuario_nome": (sessao or {}).get("nome"),
        "papel": (sessao or {}).get("role"),
        "acao": acao,
        "caso_id": caso_id,
        "resultado": resultado,
    }
    if detalhe:
        doc["detalhe"] = detalhe
    try:
        auditoria_col.insert_one(doc)
    except PyMongoError as exc:
        # A auditoria nunca deve impedir a operação principal de continuar —
        # só registramos a falha no log do servidor.
        print("ERRO (auditoria): não foi possível gravar a trilha de auditoria: %s" % exc)


def novo_id_de_caso():
    import random
    n = casos_col.count_documents({}) + 1
    sufixo = random.randint(100, 999)
    candidato = "case-%d-%d" % (n, sufixo)
    while casos_col.find_one({"_id": candidato}):
        sufixo = random.randint(100, 999)
        candidato = "case-%d-%d" % (n, sufixo)
    return candidato


def novo_id_de_paciente():
    """ID legível do paciente, gerado pelo servidor no cadastro (nunca pela
    tela): PAC-<ano>-<sequência de 4 dígitos>. É o identificador que a equipe
    usa no dia a dia; o _id interno do caso continua existindo à parte."""
    ano = time.strftime("%Y")
    n = casos_col.count_documents({"cadastro.id": {"$regex": "^PAC-%s-" % ano}}) + 1
    candidato = "PAC-%s-%04d" % (ano, n)
    while casos_col.find_one({"cadastro.id": candidato}):
        n += 1
        candidato = "PAC-%s-%04d" % (ano, n)
    return candidato


def _so_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def _cpf_valido(valor):
    """Confere os dois dígitos verificadores do CPF. Isso só garante que o
    número é bem formado — não que ele pertence à pessoa informada."""
    d = _so_digitos(valor)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for tam in (9, 10):
        soma = sum(int(d[i]) * (tam + 1 - i) for i in range(tam))
        if (soma * 10) % 11 % 10 != int(d[tam]):
            return False
    return True


def _formatar_cpf(valor):
    d = _so_digitos(valor)
    return "%s.%s.%s-%s" % (d[0:3], d[3:6], d[6:9], d[9:11])


def _idade_em_anos(nascimento, hoje=None):
    """Idade em anos completos a partir de 'DD/MM/AAAA'. Devolve None se a
    data for inválida ou estiver no futuro."""
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", str(nascimento or "").strip())
    if not m:
        return None
    dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        import datetime
        nasc = datetime.date(ano, mes, dia)
    except ValueError:
        return None
    hoje = hoje or datetime.date.today()
    if nasc > hoje or ano < 1900:
        return None
    return hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))


def _validar_cadastro_paciente(body):
    """Valida os dados cadastrais mandados em POST /api/casos. Devolve
    (cadastro, None) com os dados já normalizados, ou (None, mensagem de erro).
    O ID do paciente não entra aqui: é gerado depois, pelo servidor."""
    nascimento = str(body.get("nascimento", "")).strip()
    idade = _idade_em_anos(nascimento)
    if idade is None:
        return None, "informe a data de nascimento do paciente no formato DD/MM/AAAA"
    if not _cpf_valido(body.get("cpf")):
        return None, "o CPF do paciente é inválido"
    email = str(body.get("email", "")).strip().lower()
    if not EMAIL_REGEX.match(email):
        return None, "informe um e-mail válido para o paciente"
    disp, erro_disp = _validar_disponibilidade(body.get("disponibilidade"))
    if erro_disp:
        return None, erro_disp
    telefone = str(body.get("telefone", "")).strip()
    if telefone and len(_so_digitos(telefone)) not in (10, 11):
        return None, "o telefone precisa ter DDD (10 ou 11 dígitos)"
    cadastro = {
        "nascimento": nascimento,
        "cpf": _formatar_cpf(body.get("cpf")),
        "email": email,
        "telefone": telefone[:20],
        "disponibilidade": disp,
        "motivo": str(body.get("motivo", body.get("observacoes", ""))).strip()[:600],
        "responsavel": None,
    }
    if idade < 18:
        resp = body.get("responsavel")
        if not isinstance(resp, dict):
            return None, "paciente menor de idade: os dados do responsável são obrigatórios"
        nome = str(resp.get("nome", "")).strip()
        parentesco = str(resp.get("parentesco", "")).strip()
        telefone = _so_digitos(resp.get("telefone"))
        if not nome:
            return None, "informe o nome completo do responsável"
        if not parentesco:
            return None, "informe o vínculo do responsável com o paciente"
        if not _cpf_valido(resp.get("cpf")):
            return None, "o CPF do responsável é inválido"
        if _so_digitos(resp.get("cpf")) == _so_digitos(body.get("cpf")):
            return None, "o CPF do responsável não pode ser o mesmo do paciente"
        if len(telefone) not in (10, 11):
            return None, "informe o telefone do responsável com DDD"
        cadastro["responsavel"] = {
            "nome": nome[:120],
            "parentesco": parentesco[:40],
            "cpf": _formatar_cpf(resp.get("cpf")),
            "telefone": str(resp.get("telefone", "")).strip()[:20],
        }
    return cadastro, None


# ---------- Inscrições e triagem ----------
ST_INS_RECEBIDO = "Recebido"
ST_INS_ANALISADO = "Analisado"
ST_INS_TRIAGEM = "Aguardando triagem"
ST_INS_APROVADO = "Aprovado para acompanhamento"
ST_INS_NAO_APROVADO = "Não aprovado"
ST_INS_CADASTRADO = "Cadastrado"
DIAS_DISP = ("seg", "ter", "qua", "qui", "sex")
TURNOS_DISP = ("manha", "tarde", "noite")


def _agora_br():
    return time.strftime("%d/%m/%Y às %Hh%M", time.gmtime(time.time() - 3 * 3600))


def novo_id_de_inscricao():
    ano = time.strftime("%Y")
    n = inscricoes_col.count_documents({"_id": {"$regex": "^INS-%s-" % ano}}) + 1
    candidato = "INS-%s-%04d" % (ano, n)
    while inscricoes_col.find_one({"_id": candidato}):
        n += 1
        candidato = "INS-%s-%04d" % (ano, n)
    return candidato


def _data_br_real(valor):
    """True só se 'DD/MM/AAAA' for uma data que existe no calendário."""
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", str(valor or "").strip())
    if not m:
        return False
    try:
        import datetime
        datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return False
    return True


def _validar_disponibilidade(valor):
    """Lista de 'dia-turno' (ex.: 'seg-manha'). Devolve (lista ordenada, None)
    ou (None, erro). Pode ser vazia: nem toda inscrição informa horários."""
    if valor in (None, ""):
        return [], None
    if not isinstance(valor, list):
        return None, "a disponibilidade precisa ser uma lista de dias e turnos"
    saida = []
    for item in valor:
        partes = str(item).split("-")
        if len(partes) != 2 or partes[0] not in DIAS_DISP or partes[1] not in TURNOS_DISP:
            return None, "disponibilidade inválida: '%s'" % item
        if item not in saida:
            saida.append(item)
    ordem = lambda it: (DIAS_DISP.index(it.split("-")[0]), TURNOS_DISP.index(it.split("-")[1]))
    return sorted(saida, key=ordem), None


def _validar_inscricao(body):
    """Valida o registro de uma inscrição (nome + dados cadastrais + telefone +
    disponibilidade). Devolve (doc parcial, None) ou (None, erro)."""
    nome = str(body.get("nome", "")).strip()
    if len(nome) < 3:
        return None, "informe o nome completo do candidato"
    if body.get("consentimento") is not True:
        return None, "confirme que o candidato deu o consentimento para o tratamento dos dados no formulário"
    cadastro, erro = _validar_cadastro_paciente(body)
    if erro:
        return None, erro
    return {
        "nome": nome[:120],
        "nascimento": cadastro["nascimento"],
        "cpf": cadastro["cpf"],
        "email": cadastro["email"],
        "telefone": cadastro["telefone"],
        "responsavel": cadastro["responsavel"],
        "disponibilidade": cadastro["disponibilidade"],
        "motivo": cadastro["motivo"],
        "consentimento": True,
    }, None


def inscricao_doc_to_json(doc):
    out = dict(doc)
    out["id"] = out.pop("_id")
    return out


def _evento_inscricao(sessao, acao, detalhe=None):
    ev = {"em": _agora_br(), "por": (sessao or {}).get("nome", ""), "acao": acao}
    if detalhe:
        ev["detalhe"] = detalhe
    return ev



# ---------- Contas profissionais e Administração de TI ----------
SITE_URL = os.environ.get("SITE_URL", "https://prontuario-servidor.onrender.com").rstrip("/")
CONVITE_VALIDADE_SEGUNDOS = int(os.environ.get("CONVITE_VALIDADE_SEGUNDOS", 72 * 60 * 60))  # 72 horas (a variável existe para testes)
FUNCOES_PROFISSIONAIS = {"tecnico": "Psicólogo técnico", "supervisor": "Supervisor"}
INSTITUICAO = "Faculdade de Ciências Médicas da Santa Casa de São Paulo"
FUNCAO_ADMIN = "Administradora de TI / Desenvolvedora da Plataforma"


def _hash_senha_salt(senha, salt_hex):
    """Hash PBKDF2 com sal PRÓPRIO da conta (as contas novas não usam o sal
    fixo das contas de demonstração)."""
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), bytes.fromhex(salt_hex), 200_000).hex()


def _validar_senha_nova(senha, role):
    """Mesmas regras exibidas na tela 'criar nova senha' (6+ caracteres,
    maiúscula, número e caractere especial). A conta de administração exige
    mais: 10+ caracteres, por ter poder sobre os acessos."""
    minimo = 10 if role == "admin_ti" else 6
    if not isinstance(senha, str) or len(senha) < minimo or len(senha) > 128:
        return "a senha precisa ter de %d a 128 caracteres" % minimo
    if not (re.search(r"[A-Z]", senha) and re.search(r"[0-9]", senha) and re.search(r"[^A-Za-z0-9]", senha)):
        return "a senha precisa ter uma letra maiúscula, um número e um caractere especial"
    return None


def _novo_convite():
    """Gera um convite de primeiro acesso de uso único. Devolve (token, dados
    para gravar). Só o HASH do token é guardado; o token em si existe apenas no
    link entregue à pessoa."""
    token = secrets.token_urlsafe(32)
    return token, {
        "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "expira_em": time.time() + CONVITE_VALIDADE_SEGUNDOS,
        "gerado_em_br": _agora_br(),
    }


def _link_convite(token, role=None):
    # O token vai no fragmento (#...), que o navegador nunca envia ao servidor:
    # assim ele não aparece em log de acesso nenhum. O link da paciente abre a
    # área da paciente; o dos demais perfis, a área da equipe.
    return "%s/#%s:%s" % (SITE_URL, "ativar-paciente" if role == "paciente" else "ativar", token)


def _enviar_convite(email, nome, role, token):
    funcao = FUNCOES_PROFISSIONAIS.get(role) or (FUNCAO_ADMIN if role == "admin_ti" else ("paciente" if role == "paciente" else ("estudante" if role == "estudante" else "profissional")))
    if role in ("tecnico", "supervisor"):
        assunto = "Ative seu acesso | Prontuário Eletrônico de Psicologia — FCMSCSP"
        corpo = (
            "Olá, %s!\n\n"
            "Seja bem-vindo(a) à plataforma de Prontuário Eletrônico de Psicologia da FCMSCSP.\n\n"
            "Sua conta foi criada com sucesso!\n\n"
            "Para acessar a plataforma e iniciar suas atividades, clique no link abaixo e crie sua senha:\n\n"
            "%s\n\n"
            "Por segurança, este link é pessoal e possui prazo de validade.\n\n"
            "Atenciosamente,\n"
            "Clínica-Escola de Psicologia — FCMSCSP\n\n"
            "Este é um e-mail automático. Por favor, não responda."
        ) % (nome or "profissional", _link_convite(token, role))
        return _enviar_email(email, assunto, corpo)
    if role == "paciente":
        assunto = "Ative seu acesso | Clínica-Escola de Psicologia — FCMSCSP"
        corpo = (
            "Olá, %s!\n\n"
            "Seja bem-vindo(a) à Clínica-Escola de Psicologia da Faculdade de Ciências Médicas da Santa Casa "
            "de São Paulo (FCMSCSP).\n\n"
            "Seu cadastro foi realizado com sucesso!\n\n"
            "Por meio da plataforma, você poderá consultar informações sobre seus atendimentos, acompanhar "
            "seus agendamentos e acessar os serviços disponibilizados pela Clínica-Escola.\n\n"
            "Para acessar nossa plataforma, clique no link abaixo e crie sua senha:\n\n"
            "%s\n\n"
            "Por segurança, este link é pessoal e possui prazo de validade.\n\n"
            "Atenciosamente,\n"
            "Clínica-Escola de Psicologia — FCMSCSP\n\n"
            "Este é um e-mail automático. Por favor, não responda."
        ) % (nome or "paciente", _link_convite(token, role))
        return _enviar_email(email, assunto, corpo)
    if role == "estudante":
        assunto = "Convite de acesso | Prontuário Eletrônico de Psicologia — FCMSCSP"
        corpo = (
            "Olá, %s!\n\n"
            "Você foi cadastrado(a) na plataforma Prontuário Eletrônico de Psicologia, utilizada pela "
            "Clínica-Escola de Psicologia da Faculdade de Ciências Médicas da Santa Casa de São Paulo (FCMSCSP).\n\n"
            "Por meio da plataforma, você poderá consultar seus atendimentos agendados, acompanhar os pacientes "
            "sob sua responsabilidade e realizar os registros clínicos necessários às atividades da Clínica-Escola.\n\n"
            "Para ativar sua conta e criar sua senha de acesso, clique no link abaixo:\n\n"
            "%s\n\n"
            "Por segurança, este link é pessoal, de uso único e possui prazo de validade.\n\n"
            "Após a ativação, você poderá acessar a plataforma utilizando seu e-mail e a senha cadastrada.\n\n"
            "Importante: suas credenciais são individuais e não devem ser compartilhadas. As informações "
            "disponíveis na plataforma são confidenciais e devem ser utilizadas exclusivamente para as "
            "atividades acadêmicas e clínicas autorizadas.\n\n"
            "Se você não reconhece este convite, entre em contato com a equipe responsável pela Clínica-Escola.\n\n"
            "Atenciosamente,\n"
            "Clínica-Escola de Psicologia\n"
            "Faculdade de Ciências Médicas da Santa Casa de São Paulo — FCMSCSP\n\n"
            "Esta é uma mensagem automática. Por favor, não responda a este e-mail."
        ) % (nome or "estudante", _link_convite(token, role))
        return _enviar_email(email, assunto, corpo)
    assunto = "Prontuário Eletrônico — convite para criar sua senha de acesso"
    corpo = (
        "Olá, %s!\n\n"
        "Uma conta de %s foi criada para você no Prontuário Eletrônico de Psicologia "
        "da Clínica-Escola (FCMSCSP).\n\n"
        "Para criar sua senha e ativar o acesso, abra o link abaixo (uso único, válido por 72 horas):\n\n"
        "%s\n\n"
        "Se você não esperava este convite, ignore este e-mail.\n\n"
        "Este é um e-mail automático — não é necessário responder."
    ) % (nome or ("paciente" if role == "paciente" else "profissional"), funcao, _link_convite(token, role))
    return _enviar_email(email, assunto, corpo)


def _encerrar_sessoes(email):
    for tok in [t for t, s_ in SESSOES.items() if s_.get("email") == email]:
        SESSOES.pop(tok, None)


def _registrar_historico_admin(sessao, acao, alvo_email=None, detalhe=None):
    try:
        historico_admin_col.insert_one({
            "quando": time.time(),
            "quando_br": _agora_br(),
            "por_email": (sessao or {}).get("email", ""),
            "por_nome": (sessao or {}).get("nome", ""),
            "acao": acao,
            "alvo_email": alvo_email or "",
            "detalhe": detalhe or "",
        })
    except PyMongoError as exc:
        print("ERRO (histórico administrativo): %s" % exc)


def conta_db_to_json(doc):
    """Dados administrativos de uma conta — nunca hash, sal nem token."""
    convite = doc.get("convite") or {}
    return {
        "email": doc["_id"],
        "nome": doc.get("nome", ""),
        "role": doc.get("role", ""),
        "funcao": FUNCOES_PROFISSIONAIS.get(doc.get("role"), doc.get("funcao", "")),
        "crp": doc.get("crp", ""),
        "status": doc.get("status", ""),
        "criado_em_br": doc.get("criado_em_br", ""),
        "convite_expirado": bool(doc.get("status") == "convite_pendente" and convite.get("expira_em", 0) < time.time()),
    }


def _validar_dados_profissional(body):
    nome = str(body.get("nome", "")).strip()
    if len(nome) < 3 or len(nome) > 120:
        return None, "informe o nome completo (de 3 a 120 caracteres)"
    crp = str(body.get("crp", "")).strip()
    if crp and not re.match(r"^\d{2}/\d{3,7}$", crp):
        return None, "o CRP deve ter o formato 06/123456 (região e número)"
    return {"nome": nome, "crp": crp}, None


def _resposta_convite(email_enviado, token, role=None):
    """O link só é devolvido ao painel quando o e-mail NÃO saiu (SMTP não
    configurado ou falhou): é a única forma de a pessoa receber o convite, e
    ele é mostrado uma única vez, na tela da administração — nunca no log."""
    return {"email_enviado": bool(email_enviado), "link": None if email_enviado else _link_convite(token, role),
            "motivo": "" if email_enviado else ULTIMO_ERRO_EMAIL.get("motivo", ""),
            "validade_horas": CONVITE_VALIDADE_SEGUNDOS // 3600}


MOTIVOS_CORRECAO = ("Informação incorreta", "Atualização de dados")
CAMPOS_CORRIGIVEIS = ("nome", "nascimento", "telefone", "responsavel_nome", "responsavel_parentesco", "responsavel_telefone")
ROTULOS_CAMPOS = {"nome": "Nome", "nascimento": "Data de nascimento", "telefone": "Telefone",
                  "responsavel_nome": "Nome do responsável", "responsavel_parentesco": "Vínculo do responsável",
                  "responsavel_telefone": "Telefone do responsável"}


def _dados_para_conferencia(caso):
    """O que a paciente vê para conferir: só os PRÓPRIOS dados cadastrais."""
    cad = caso.get("cadastro") or {}
    resp = cad.get("responsavel") or None
    idade = _idade_em_anos(cad.get("nascimento", ""))
    return {
        "status": (caso.get("confirmacao") or {}).get("status", "nao_aplicavel"),
        "dados": {
            "nome": caso.get("paciente", ""), "nascimento": cad.get("nascimento", ""), "cpf": cad.get("cpf", ""),
            "email": cad.get("email", ""), "telefone": cad.get("telefone", ""),
            "menor": bool(idade is not None and idade < 18),
            "responsavel": {"nome": resp.get("nome", ""), "parentesco": resp.get("parentesco", ""),
                            "telefone": resp.get("telefone", "")} if resp else None,
        },
    }


def _aplicar_correcoes(caso, alteracoes):
    """Valida as correções pedidas pela paciente. Devolve (novo_nome, novo_cadastro, lista_de_mudancas, None)
    ou (None, None, None, mensagem de erro). CPF e e-mail não são corrigíveis por aqui."""
    if not isinstance(alteracoes, list) or not alteracoes:
        return None, None, None, "informe o que precisa ser corrigido"
    cad = caso.get("cadastro") or {}
    nome = caso.get("paciente", "")
    corpo = {"nascimento": cad.get("nascimento", ""), "cpf": cad.get("cpf", ""), "email": cad.get("email", ""),
             "disponibilidade": cad.get("disponibilidade") or [], "telefone": cad.get("telefone", ""),
             "motivo": cad.get("motivo", ""), "responsavel": dict(cad["responsavel"]) if cad.get("responsavel") else None}
    pedidos = {}
    for a in alteracoes:
        if not isinstance(a, dict) or a.get("campo") not in CAMPOS_CORRIGIVEIS:
            return None, None, None, "campo não pode ser corrigido por aqui (CPF e e-mail só pela equipe)"
        if a.get("motivo") not in MOTIVOS_CORRECAO:
            return None, None, None, "informe o motivo de cada correção (Informação incorreta ou Atualização de dados)"
        pedidos[a["campo"]] = (str(a.get("valor", "")).strip(), a["motivo"])
    antes = {"nome": nome, "nascimento": cad.get("nascimento", ""), "telefone": cad.get("telefone", ""),
             "responsavel_nome": (cad.get("responsavel") or {}).get("nome", ""),
             "responsavel_parentesco": (cad.get("responsavel") or {}).get("parentesco", ""),
             "responsavel_telefone": (cad.get("responsavel") or {}).get("telefone", "")}
    for campo, (valor, _m) in pedidos.items():
        if campo == "nome":
            if len(valor) < 3 or len(valor) > 120:
                return None, None, None, "informe o nome completo (de 3 a 120 caracteres)"
            nome = valor
        elif campo in ("nascimento", "telefone"):
            corpo[campo] = valor
        else:
            if corpo["responsavel"] is None:
                return None, None, None, "este cadastro não tem responsável"
            corpo["responsavel"][campo.split("_", 1)[1]] = valor
    novo_cad, erro = _validar_cadastro_paciente(corpo)
    if erro:
        return None, None, None, erro
    depois = {"nome": nome, "nascimento": novo_cad["nascimento"], "telefone": novo_cad["telefone"],
              "responsavel_nome": (novo_cad["responsavel"] or {}).get("nome", ""),
              "responsavel_parentesco": (novo_cad["responsavel"] or {}).get("parentesco", ""),
              "responsavel_telefone": (novo_cad["responsavel"] or {}).get("telefone", "")}
    mudancas = [{"campo": ROTULOS_CAMPOS[c], "de": antes[c], "para": depois[c], "motivo": pedidos[c][1]}
                for c in pedidos if antes[c] != depois[c]]
    if not mudancas:
        return None, None, None, "nenhuma alteração em relação ao cadastro atual"
    cadastro_final = {**cad, "nascimento": novo_cad["nascimento"], "telefone": novo_cad["telefone"], "responsavel": novo_cad["responsavel"]}
    return nome, cadastro_final, mudancas, None


def _criar_acesso_da_paciente(email, nome, caso_id, paciente_id, sessao):
    """Cria (ou religa) a conta de acesso da paciente. A conta nasce sem senha; o link de uso
    único é enviado ao e-mail dela. Se o e-mail não puder ser enviado, o link volta uma única
    vez na resposta ao técnico, para ele repassar. Nunca vai para o log."""
    existente = contas_col.find_one({"_id": email})
    if existente:  # paciente que volta ao serviço: a mesma conta passa a apontar para o caso novo
        contas_col.update_one({"_id": email}, {"$set": {"caso_id": caso_id, "paciente_id": paciente_id}})
        return {"status": existente.get("status", ""), "reaproveitada": True, "convite": None}
    token, convite = _novo_convite()
    contas_col.insert_one({
        "_id": email, "nome": nome, "role": "paciente", "caso_id": caso_id, "paciente_id": paciente_id,
        "status": "convite_pendente", "salt": None, "senha_hash": None, "convite": convite,
        "criado_em": time.time(), "criado_em_br": _agora_br(), "criado_por": (sessao or {}).get("email", ""),
    })
    enviado = _enviar_convite(email, nome, "paciente", token)
    _registrar_auditoria(sessao, "criação de acesso da paciente", caso_id=caso_id)
    return {"status": "convite_pendente", "reaproveitada": False, "convite": _resposta_convite(enviado, token, "paciente")}


def caso_doc_to_json(doc):
    """Remove o campo interno _id do corpo do caso (o id já é a chave no dicionário
    devolvido por /api/casos, não precisa aparecer duplicado dentro do objeto)."""
    out = dict(doc)
    out.pop("_id", None)
    return out


def solicitacao_doc_to_json(doc):
    """Converte o _id do MongoDB (um ObjectId) para string, que é o formato que
    JSON e JavaScript entendem."""
    out = dict(doc)
    out["_id"] = str(doc["_id"])
    return out


def reagendamento_doc_to_json(doc):
    out = dict(doc)
    out["_id"] = str(doc["_id"])
    return out


# ---------------------------------------------------------------------------
# Isolamento de casos por papel (correção de segurança — IDOR/BOLA)
#
# Antes, qualquer papel em PAPEIS_CASOS (técnico, supervisor OU estudante)
# podia ler e alterar QUALQUER caso, de qualquer paciente, bastando estar
# autenticado — sem nenhuma checagem de que aquele caso específico era da
# responsabilidade de quem pedia. Isso foi comprovado em teste: um estudante
# conseguia ler e editar prontuário de paciente de outro estudante. As
# funções abaixo implementam a regra real do serviço-escola: um estudante só
# acessa os casos em que ele mesmo é "estudante" responsável; o supervisor
# e o técnico acessam todos os casos (matriz de permissões das Instruções para
# desenvolvimento do prontuário). Só o técnico cria/altera agendamentos,
# libera acesso ao prontuário e confirma reagendamentos.

def _filtro_visibilidade_casos(sessao):
    """Filtro do MongoDB a aplicar em GET /api/casos conforme o papel da
    sessão. Segundo as Instruções para desenvolvimento do prontuário (matriz de
    permissões, "Ver lista de casos"): técnico e supervisor veem todos os casos
    (visão do serviço) e o estudante só os seus. Devolve {} (sem filtro) para
    técnico e supervisor."""
    if sessao["role"] == "estudante":
        return {"estudante": sessao["nome"]}
    return {}


def _pode_acessar_caso(sessao, caso_doc):
    """Verifica se a sessão tem permissão para ler/alterar ESTE caso
    específico (não só o papel em geral). Usado em PUT /api/casos/<id>, onde
    uma checagem só de papel não bastaria — o próprio id do caso vem na URL
    e podia ser trocado para o de outro paciente."""
    if sessao["role"] == "tecnico":
        return True
    if sessao["role"] == "estudante":
        return caso_doc.get("estudante") == sessao["nome"]
    if sessao["role"] == "supervisor":
        return True  # matriz de permissões: supervisor acessa todos os casos
    return False


# ---------------------------------------------------------------------------
# Documentos anexados, histórico de acessos e exportação do prontuário
# ---------------------------------------------------------------------------
DOC_TIPOS = ["Laudo", "Teste", "Encaminhamento", "Documento do paciente", "Documento complementar"]
DOC_MAX_BYTES = 10 * 1024 * 1024
DOC_OBS_MAX = 1000
DOC_NOME_MAX = 150
DOC_MOTIVO_MIN, DOC_MOTIVO_MAX = 5, 500
DOC_EXTENSOES = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                 "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
try:
    DOC_QUOTA_BYTES = int(float(os.environ.get("DOCUMENTOS_QUOTA_MB", "300")) * 1024 * 1024)
except ValueError:
    DOC_QUOTA_BYTES = 300 * 1024 * 1024
# A exclusão lógica depende de aprovação institucional: desligada por padrão (rota responde 403).
DOC_EXCLUSAO_HABILITADA = os.environ.get("DOCUMENTOS_EXCLUSAO_LOGICA", "").strip() == "1"
PROTOCOLO_INICIAL = 1001
_UPLOADS_SIMULTANEOUS = threading.BoundedSemaphore(3)


class AuditoriaFalhou(Exception):
    pass


def _supervisor_do_caso(sessao, caso_doc):
    return sessao["role"] == "supervisor" and bool(caso_doc.get("supervisor")) and caso_doc.get("supervisor") == sessao["nome"]


def _pode_anexar_documento(sessao, caso_doc):
    """Estudante: só nos próprios casos. Supervisor: só nos casos sob sua supervisão. Técnico: casos do serviço."""
    if sessao["role"] == "tecnico":
        return True
    if sessao["role"] == "estudante":
        return caso_doc.get("estudante") == sessao["nome"]
    return _supervisor_do_caso(sessao, caso_doc)


def _pode_excluir_documento(sessao, caso_doc):
    """Estudante nunca exclui. Supervisor só nos casos sob sua supervisão. Técnico nos casos do serviço."""
    if sessao["role"] == "tecnico":
        return True
    return _supervisor_do_caso(sessao, caso_doc)


def _tipo_real_do_arquivo(dados):
    """Tipo detectado pelo conteúdo (não pelo nome): 'pdf', 'jpg', 'png', 'docx' ou None."""
    if dados[:5] == b"%PDF-":
        return "pdf"
    if dados[:3] == b"\xff\xd8\xff":
        return "jpg"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if dados[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                nomes = set(z.namelist())
                if "word/document.xml" not in nomes or "[Content_Types].xml" not in nomes:
                    return None
                if sum(i.file_size for i in z.infolist()) > 200 * 1024 * 1024:  # descompactado absurdo (zip bomb)
                    return None
            return "docx"
        except (zipfile.BadZipFile, OSError, ValueError, RuntimeError):
            return None
    return None


def _limpar_nome_arquivo(nome):
    nome = str(nome or "").replace("\\", "/").split("/")[-1]
    nome = re.sub(r"[\x00-\x1f\x7f\"<>|:*?]", "", nome).strip().strip(".")
    return nome


def _validar_upload(nome, dados):
    """Devolve (erro, nome_limpo, content_type)."""
    limpo = _limpar_nome_arquivo(nome)
    if not limpo or len(limpo) > DOC_NOME_MAX:
        return "nome de arquivo inválido (até %d caracteres)" % DOC_NOME_MAX, None, None
    ext = limpo.rsplit(".", 1)[-1].lower() if "." in limpo else ""
    if ext not in DOC_EXTENSOES:
        return "formato não permitido — envie PDF, JPG, PNG ou DOCX", None, None
    if len(dados) == 0:
        return "o arquivo está vazio", None, None
    if len(dados) > DOC_MAX_BYTES:
        return "o arquivo ultrapassa o limite de 10 MB", None, None
    real = _tipo_real_do_arquivo(dados)
    esperado = "jpg" if ext in ("jpg", "jpeg") else ext
    if real is None or real != esperado:
        return "o conteúdo do arquivo não corresponde ao formato %s (arquivo inválido ou renomeado)" % ext.upper(), None, None
    return None, limpo, DOC_EXTENSOES[ext]


def _evento_documento(sessao, operacao, caso_id, documento_id=None, resultado="sucesso", motivo=None, obrigatorio=True):
    """Grava o evento no histórico do documento e espelha na auditoria geral. Se 'obrigatorio' e a gravação
    falhar, levanta AuditoriaFalhou — quem chamou NÃO pode entregar o arquivo nem concluir a operação."""
    ev = {"_id": "ev-" + secrets.token_hex(8), "documento_id": documento_id, "caso_id": caso_id, "operacao": operacao,
          "usuario_email": sessao.get("email"), "usuario_nome": sessao.get("nome"), "papel": sessao.get("role"),
          "quando": time.time(), "quando_br": _agora_br(), "resultado": resultado}
    if motivo:
        ev["motivo"] = motivo
    try:
        documentos_eventos_col.insert_one(ev)
        auditoria_col.insert_one({"quando": ev["quando"], "usuario_email": ev["usuario_email"], "usuario_nome": ev["usuario_nome"],
                                  "papel": ev["papel"], "acao": "documento: " + operacao, "caso_id": caso_id, "resultado": resultado,
                                  "detalhe": ("documento " + documento_id) if documento_id else None})
    except PyMongoError as exc:
        print("ERRO (auditoria de documento): %s" % exc)
        if obrigatorio:
            raise AuditoriaFalhou()
    return ev


def _doc_publico(d):
    """Metadados do documento que a tela pode ver (nunca o id interno do GridFS)."""
    return {"id": d["_id"], "nome": d["nome_original"], "autor": d["enviado_por_nome"], "data": d["enviado_em_data"],
            "tipo": d["tipo_doc"], "observacao": d.get("observacao", ""), "tamanho": d["tamanho"], "status": d.get("status", "ativo"),
            "disponivel": True, "content_type": d["content_type"]}


def _proximo_protocolo(sessao, caso_id):
    """Reserva o próximo protocolo (sequencial, único, a partir de #1001). A unicidade vem do _id da coleção."""
    n = exportacoes_col.count_documents({}) + PROTOCOLO_INICIAL
    for _ in range(25):
        reg = {"_id": n, "caso_id": caso_id, "usuario_email": sessao.get("email"), "usuario_nome": sessao.get("nome"),
               "papel": sessao.get("role"), "quando": time.time(), "quando_br": _agora_br()}
        try:
            exportacoes_col.insert_one(reg)
            return reg
        except PyMongoError:
            n += 1
    raise AuditoriaFalhou()


# ---------------------------------------------------------------------------
# Imutabilidade de registros clínicos (correção de segurança — a regra já
# existia nas instruções do projeto e já era respeitada pela tela, que não
# tem botão de editar uma evolução antiga: quem quer corrigir registra uma
# nova evolução de retificação. Mas essa regra só existia no front-end — o
# servidor aceitava, via PUT /api/casos/<id>, qualquer corpo de requisição
# que sobrescrevesse uma evolução já gravada ou substituísse a anamnese já
# registrada, bastando que quem mandasse a requisição tivesse permissão
# sobre aquele caso. Isso não é um problema de controle de acesso (o
# acesso ao caso já é checado por _pode_acessar_caso) — é uma falta de
# integridade do próprio registro clínico, que esta função passa a impor
# diretamente no servidor, independentemente do que a tela mande.

def _validar_imutabilidade_clinica(caso_atual, body):
    """Devolve None se o corpo da requisição respeita a regra de que uma
    evolução já registrada nunca é editada ou removida (só apensada) e que
    a anamnese, uma vez preenchida, não é substituída. Devolve uma mensagem
    de erro (string) quando o corpo tenta violar a regra."""
    evolucoes_atuais = caso_atual.get("evolucoes") or []
    if "evolucoes" in body:
        evolucoes_novas = body["evolucoes"]
        if not isinstance(evolucoes_novas, list):
            return "o campo 'evolucoes' precisa ser uma lista"
        if len(evolucoes_novas) < len(evolucoes_atuais):
            return "não é permitido remover uma evolução já registrada"
        if evolucoes_novas[: len(evolucoes_atuais)] != evolucoes_atuais:
            return (
                "não é permitido alterar uma evolução já registrada — "
                "registre uma nova evolução de retificação em vez de editar a antiga"
            )

    anamnese_atual = caso_atual.get("anamnese")
    if "anamnese" in body and anamnese_atual not in (None, ""):
        if body["anamnese"] != anamnese_atual:
            return "a anamnese já foi registrada para este caso e não pode ser alterada"

    return None


def _hoje_br():
    # Horário de Brasília (UTC-3, sem horário de verão desde 2019). O servidor
    # hospedado roda em UTC: sem isso, um cadastro feito depois das 21h sairia
    # com a data do dia seguinte.
    return time.strftime("%d/%m/%Y", time.gmtime(time.time() - 3 * 3600))


def _parse_data_br(valor):
    """Converte 'DD/MM/AAAA' em (ano, mes, dia) para poder ordenar/comparar
    datas. Devolve None se o valor não bater com esse formato (ex.: vazio ou
    mal formatado) — quem usa isso deve tratar o None, nunca presumir uma
    data que o campo não tem de verdade."""
    if not valor or not isinstance(valor, str):
        return None
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", valor.strip())
    if not m:
        return None
    dia, mes, ano = (int(x) for x in m.groups())
    return (ano, mes, dia)


def _proxima_consulta(caso):
    """Escolhe, entre os agendamentos do caso, o próximo a acontecer (o de
    data mais próxima que ainda não passou; se nenhum estiver no futuro,
    devolve o mais recente, para não esconder informação de quem já tem
    caso encerrado). Devolve só os campos que o paciente já vê hoje na
    própria tela (data, hora, local, status) — nenhum dado clínico."""
    agendamentos = caso.get("agendamentos") or []
    hoje = _parse_data_br(_hoje_br())
    futuros = []
    for ag in agendamentos:
        chave = _parse_data_br(ag.get("data", ""))
        if chave is not None:
            futuros.append((chave, ag))
    if not futuros:
        return None
    futuros.sort(key=lambda par: par[0])
    proximos = [ag for chave, ag in futuros if hoje is None or chave >= hoje]
    escolhido = proximos[0] if proximos else futuros[-1][1]
    return {
        "data": escolhido.get("data", ""),
        "hora": escolhido.get("hora", ""),
        "local": escolhido.get("local", ""),
        "status": escolhido.get("status", ""),
    }


def _encontrar_caso_do_paciente(nome_paciente, caso_id=None):
    """Acha o caso deste paciente (pelo nome da própria sessão, nunca por um
    id que o navegador possa mandar). Se houver mais de um, prioriza um caso
    'Ativo'; não deveria haver mais de um caso ativo por paciente no
    serviço-escola, mas se houver, pega o primeiro encontrado."""
    if caso_id:
        # Conta criada pelo cadastro: o vínculo é pelo id do caso, não pelo nome.
        caso = casos_col.find_one({"_id": caso_id})
        if caso:
            return caso
    candidatos = list(casos_col.find({"paciente": nome_paciente}))
    if not candidatos:
        return None
    for c in candidatos:
        if c.get("status") == "Ativo":
            return c
    return candidatos[0]


class Handler(BaseHTTPRequestHandler):
    server_version = "ProntuarioServerMongo/1.0"

    # ---------- utilidades de resposta ----------
    def _security_headers(self):
        """Cabeçalhos de segurança ausentes antes (achado da auditoria):
        protegem contra clickjacking (X-Frame-Options), contra o navegador
        tentando "adivinhar" um tipo de arquivo diferente do declarado
        (X-Content-Type-Options), vazamento de URL completa para outros
        sites via o cabeçalho Referer (Referrer-Policy), e reforçam que o
        site só deve ser acessado por HTTPS (Strict-Transport-Security). A
        política de Content-Security-Policy abaixo permite script inline
        porque a página atual é construída assim (um CSP mais restrito, com
        nonces, exigiria reescrever todos os <script> do arquivo — mudança
        maior, fora do escopo desta auditoria); mesmo assim, ela já bloqueia
        o carregamento de scripts, iframes e conexões de qualquer domínio
        não explicitamente listado, o que limita bastante o que um ataque de
        XSS conseguiria fazer mesmo que um dia aparecesse um."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://vlibras.gov.br; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https://vlibras.gov.br; "
            "object-src 'self' blob:; "
            "media-src 'self' https://vlibras.gov.br; "
            "frame-src https://vlibras.gov.br; "
            "connect-src 'self' https://vlibras.gov.br; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status, mensagem):
        self._send_json({"erro": mensagem}, status)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        # "Authorization" precisa estar aqui porque agora o front-end manda o token
        # de sessão nesse cabeçalho em toda chamada autenticada (Bearer <token>);
        # sem isso o navegador bloqueia a chamada no pre-flight do CORS antes
        # mesmo dela chegar nas rotas abaixo.
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _erro_servidor(self, exc, contexto):
        """Loga o detalhe técnico só no console do servidor (visível pra nós nos
        logs do Render) e devolve ao navegador uma mensagem genérica — antes, a
        mensagem de erro completa do MongoDB (que pode conter detalhes internos
        do banco) era enviada direto para quem fez a requisição."""
        print("ERRO (%s): %s" % (contexto, exc))
        self._send_error_json(503, "não foi possível completar a operação agora. Tente novamente em instantes.")

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _modulo_descontinuado(self):
        """Inscrição e triagem passaram a ser feitas fora do sistema (formulário
        institucional). As rotas antigas respondem 410 e nada é lido nem gravado."""
        self._send_error_json(410, "recurso descontinuado: a inscrição e a triagem são feitas fora do sistema")

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.log_date_time_string(), fmt % args))

    # ---------- autenticação ----------
    def _sessao_atual(self):
        """Lê o cabeçalho 'Authorization: Bearer <token>' e devolve a sessão
        correspondente (dict com email/role/nome) se o token for válido e
        ainda não tiver expirado, ou None caso contrário."""
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[len("Bearer "):].strip()
        sessao = SESSOES.get(token)
        if not sessao:
            return None
        if time.time() - sessao["criado_em"] > SESSAO_DURACAO_SEGUNDOS:
            SESSOES.pop(token, None)
            return None
        return sessao

    def _exigir_papel(self, papeis_permitidos):
        """Verifica se há uma sessão válida com um papel autorizado para a rota.
        Se não houver, já envia a resposta de erro (401/403) e devolve None;
        quem chamou deve checar 'if sessao is None: return' logo em seguida."""
        sessao = self._sessao_atual()
        if sessao is None:
            self._send_error_json(401, "é necessário estar autenticado (faça login novamente)")
            return None
        if sessao["role"] not in papeis_permitidos:
            _registrar_auditoria(
                sessao,
                "tentativa de acesso a rota sem permissão de papel: " + self.path.split("?", 1)[0],
                resultado="negado",
            )
            self._send_error_json(403, "seu perfil não tem permissão para esta operação")
            return None
        return sessao

    def _tratar_comparecimento(self, case_id, idx, corrigir):
        """POST: o estudante responsável registra presença/falta (uma única vez por atendimento).
        PUT: só o psicólogo técnico corrige, com justificativa; o valor anterior fica preservado. Não existe exclusão."""
        sessao = self._exigir_papel({"tecnico"} if corrigir else {"estudante"})
        if sessao is None:
            return
        try:
            body = self._read_json_body()
        except Exception:
            self._send_error_json(400, "corpo da requisição não é um JSON válido"); return
        situacao = body.get("situacao")
        if situacao not in COMP_SITUACOES:
            self._send_error_json(400, "informe se o paciente compareceu ou faltou"); return
        justificativa = str(body.get("justificativa", "") or "").strip()
        if corrigir and not (COMP_JUSTIFICATIVA_MIN <= len(justificativa) <= COMP_JUSTIFICATIVA_MAX):
            self._send_error_json(400, "informe a justificativa da correção (de %d a %d caracteres)" % (COMP_JUSTIFICATIVA_MIN, COMP_JUSTIFICATIVA_MAX)); return
        with TRAVA_OPERACOES:
            try:
                caso = casos_col.find_one({"_id": case_id})
                if caso is None:
                    self._send_error_json(404, "caso não encontrado"); return
                if not corrigir and caso.get("estudante") != sessao["nome"]:
                    _registrar_auditoria(sessao, "tentativa de registrar comparecimento de paciente de outro estudante", caso_id=case_id, resultado="negado")
                    self._send_error_json(403, "só o estudante responsável pelo caso registra o comparecimento"); return
                ags = list(caso.get("agendamentos") or [])
                if idx >= len(ags):
                    self._send_error_json(404, "agendamento não encontrado"); return
                ag = dict(ags[idx])
                if ag.get("status") == ST_AG_CANCELADA:
                    self._send_error_json(409, "este atendimento foi cancelado"); return
                if not _ag_iniciou(ag):
                    self._send_error_json(409, "o comparecimento só pode ser registrado depois do início do horário agendado"); return
                atual = ag.get("comparecimento")
                agora, agora_br = time.time(), _agora_br()
                if corrigir:
                    if not atual:
                        self._send_error_json(409, "este atendimento ainda não tem comparecimento registrado"); return
                    if atual.get("situacao") == situacao:
                        self._send_error_json(409, "o registro já está com essa situação"); return
                    comp = dict(atual)
                    comp.setdefault("correcoes", []).append({"de": atual.get("situacao"), "para": situacao, "justificativa": justificativa,
                                                              "por": sessao["nome"], "por_email": sessao["email"], "quando": agora, "quando_br": agora_br})
                    comp["situacao"] = situacao
                else:
                    if atual:
                        self._send_error_json(409, "o comparecimento deste atendimento já foi registrado"); return
                    comp = {"situacao": situacao, "por": sessao["nome"], "por_email": sessao["email"], "quando": agora, "quando_br": agora_br}
                ag["comparecimento"] = comp
                ags[idx] = ag
                casos_col.update_one({"_id": case_id}, {"$set": {"agendamentos": ags}})
                novo = casos_col.find_one({"_id": case_id})
                alerta = _avaliar_faltas(novo)
            except PyMongoError as exc:
                self._erro_servidor(exc, "comparecimento")
                return
        _registrar_auditoria(sessao, "comparecimento corrigido" if corrigir else "comparecimento registrado", caso_id=case_id,
                             detalhe="atendimento %s %s: %s%s" % (ag.get("data"), ag.get("hora"), ((atual or {}).get("situacao") + " -> ") if corrigir else "", situacao)
                                     + ((" | justificativa: " + justificativa) if corrigir else ""))
        self._send_json({"ok": True, "agendamento": ag, "alerta_faltas": alerta})

    # ---------- OPTIONS (pre-flight de CORS) ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ---------- GET ----------
    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in AUDIOS:
            self._serve_audio(AUDIOS[path])
            return

        if path in ("/", "/index.html"):
            self._serve_html()
            return

        if path == "/api/casos":
            sessao = self._exigir_papel(PAPEIS_CASOS)
            if sessao is None:
                return
            try:
                filtro = _filtro_visibilidade_casos(sessao)
                casos = {doc["_id"]: caso_doc_to_json(doc) for doc in casos_col.find(filtro)}
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/casos")
                return
            _registrar_auditoria(sessao, "listagem de casos", detalhe="retornou %d caso(s)" % len(casos))
            self._send_json(casos)
            return

        if path == "/api/solicitacoes":
            if self._exigir_papel(PAPEIS_SOLICITACOES_LEITURA) is None:
                return
            try:
                fila = [solicitacao_doc_to_json(doc) for doc in solicitacoes_col.find({}).sort("_id", 1)]
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/solicitacoes")
                return
            self._send_json(fila)
            return

        if path == "/api/documentos/config":
            sessao = self._exigir_papel(PAPEIS_CASOS)
            if sessao is None:
                return
            self._send_json({"tipos": DOC_TIPOS, "max_bytes": DOC_MAX_BYTES, "formatos": ["PDF", "JPG", "PNG", "DOCX"],
                             "exclusao_habilitada": DOC_EXCLUSAO_HABILITADA})
            return

        m = re.match(r"^/api/casos/([^/]+)/documentos/historico$", path)
        if m:
            sessao = self._exigir_papel({"tecnico", "supervisor"})
            if sessao is None:
                return
            case_id = unquote(m.group(1))
            try:
                caso = casos_col.find_one({"_id": case_id})
                if caso is None or not _pode_acessar_caso(sessao, caso):
                    self._send_error_json(404 if caso is None else 403, "caso não encontrado" if caso is None else "sem permissão para este caso")
                    return
                evs = list(documentos_eventos_col.find({"caso_id": case_id}).sort("quando", -1))[:300]
                nomes = {d["_id"]: d["nome_original"] for d in documentos_col.find({"caso_id": case_id})}
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/casos/<id>/documentos/historico")
                return
            self._send_json([{"id": e["_id"], "documento_id": e.get("documento_id"), "documento": nomes.get(e.get("documento_id"), ""),
                              "operacao": e["operacao"], "usuario": e.get("usuario_nome"), "papel": e.get("papel"),
                              "quando_br": e.get("quando_br"), "resultado": e.get("resultado"), "motivo": e.get("motivo", "")} for e in evs])
            return

        m = re.match(r"^/api/casos/([^/]+)/documentos/([^/]+)/arquivo$", path)
        if m:
            sessao = self._exigir_papel(PAPEIS_CASOS)
            if sessao is None:
                return
            case_id, doc_id = unquote(m.group(1)), unquote(m.group(2))
            modo = "download" if "modo=baixar" in (self.path.split("?", 1)[1] if "?" in self.path else "") else "visualizacao"
            try:
                caso = casos_col.find_one({"_id": case_id})
                if caso is None:
                    self._send_error_json(404, "caso não encontrado"); return
                if not _pode_acessar_caso(sessao, caso):
                    _registrar_auditoria(sessao, "tentativa de abrir documento de caso sem acesso", caso_id=case_id, resultado="negado")
                    self._send_error_json(403, "sem permissão para este caso"); return
                d = documentos_col.find_one({"_id": doc_id, "caso_id": case_id})
                if d is None or d.get("status") == "excluido":
                    self._send_error_json(404, "documento não encontrado"); return
                try:
                    dados = documentos_fs.get(ObjectId(d["gridfs_id"])).read()
                except Exception as exc:
                    print("ERRO (GridFS leitura): %s" % exc)
                    _evento_documento(sessao, modo, case_id, doc_id, resultado="falha", obrigatorio=False)
                    self._send_error_json(503, "não foi possível abrir o arquivo agora. Tente novamente em instantes.")
                    return
                _evento_documento(sessao, modo, case_id, doc_id)  # sem registro, sem arquivo
            except AuditoriaFalhou:
                self._send_error_json(503, "não foi possível registrar o acesso ao documento; por segurança o arquivo não foi entregue")
                return
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/casos/<id>/documentos/<doc>/arquivo")
                return
            from urllib.parse import quote as _q
            self.send_response(200)
            self.send_header("Content-Type", d["content_type"])
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Content-Disposition", "%s; filename*=UTF-8''%s" % ("attachment" if modo == "download" else "inline", _q(d["nome_original"])))
            self.send_header("Cache-Control", "private, no-store")
            self._cors_headers()
            self._security_headers()
            self.end_headers()
            self.wfile.write(dados)
            return

        m = re.match(r"^/api/casos/([^/]+)/notas$", path)
        if m:
            # Notas de acompanhamento de um caso: técnico e supervisor leem todas; o estudante,
            # só as dos casos sob sua responsabilidade; demais perfis não leem.
            sessao = self._exigir_papel({"tecnico", "supervisor", "estudante"})
            if sessao is None:
                return
            case_id = unquote(m.group(1))
            try:
                caso = casos_col.find_one({"_id": case_id})
                if caso is None or not _pode_acessar_caso(sessao, caso):
                    _registrar_auditoria(sessao, "tentativa de ler notas de caso sem acesso", caso_id=case_id, resultado="negado")
                    self._send_error_json(404 if caso is None else 403, "caso não encontrado" if caso is None else "sem permissão para este caso")
                    return
                notas = list(notas_col.find({"caso_id": case_id}).sort("criado_em", 1))
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/casos/<id>/notas")
                return
            self._send_json([{"id": n["_id"], "evolucao": n["evolucao_idx"], "autor": n["autor"], "criado_em_br": n["criado_em_br"],
                              "texto": n["texto"], "lida_em_br": n.get("lida_em_br", ""), "papel": n.get("autor_papel", "tecnico")} for n in notas])
            return

        if path == "/api/notificacoes":
            sessao = self._exigir_papel({"estudante", "tecnico", "supervisor", "paciente"})
            if sessao is None:
                return
            try:
                if sessao["role"] == "paciente":
                    # Só os avisos do PRÓPRIO caso (achado pela sessão, não por um id enviado pelo navegador).
                    caso = _encontrar_caso_do_paciente(sessao["nome"], sessao.get("caso_id"))
                    docs = [] if caso is None else sorted(notificacoes_col.find({"para": "paciente", "caso_id": caso["_id"]}),
                                                         key=lambda d: d.get("criada_em", 0), reverse=True)[:30]
                    self._send_json([{"id": d["_id"], "tipo": d["tipo"], "detalhe": d.get("detalhe", ""),
                                      "criada_em_br": d["criada_em_br"], "lida": bool(d.get("lida"))} for d in docs])
                    return
                if sessao["role"] == "supervisor":
                    docs = [d for d in notificacoes_col.find({"destinatario": sessao["nome"]}) if d.get("para") == "supervisor"]
                    docs.sort(key=lambda d: d.get("criada_em", 0), reverse=True)
                    self._send_json([{"id": d["_id"], "tipo": d["tipo"], "caso_id": d.get("caso_id", ""), "detalhe": d.get("detalhe", ""),
                                      "prioridade": d.get("prioridade", ""), "criada_em_br": d["criada_em_br"], "lida": bool(d.get("lida"))} for d in docs[:50]])
                    return
                if sessao["role"] == "tecnico":
                    _avisos_convites_expirados()
                    docs = list(notificacoes_col.find({"para": "tecnico"}).sort("criada_em", -1))[:50]
                    self._send_json([{"id": d["_id"], "tipo": d["tipo"], "caso_id": d.get("caso_id", ""), "detalhe": d.get("detalhe", ""),
                                      "prioridade": d.get("prioridade", ""), "criada_em_br": d["criada_em_br"], "lida": bool(d.get("lida"))} for d in docs])
                    return
                docs = [d for d in notificacoes_col.find({"destinatario": sessao["nome"]}).sort("criada_em", -1) if not d.get("para")][:50]
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/notificacoes")
                return
            # Sem nome de paciente nem conteúdo: só a referência ao registro.
            self._send_json([{"id": d["_id"], "tipo": d["tipo"], "caso_id": d["caso_id"], "evolucao": d.get("evolucao_idx"),
                              "detalhe": d.get("detalhe", ""), "criada_em_br": d["criada_em_br"], "lida": bool(d.get("lida")),
                              "papel": d.get("autor_papel", "")} for d in docs])
            return

        if path == "/api/supervisor/painel":
            sessao = self._exigir_papel({"supervisor"})
            if sessao is None:
                return
            try:
                self._send_json(_painel_do_supervisor(sessao["nome"]))
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/supervisor/painel")
            return

        if path in ("/api/supervisores", "/api/vinculos"):
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            try:
                dados = _lista_supervisores_ativos() if path == "/api/supervisores" else _painel_vinculos()
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET " + path)
                return
            self._send_json(dados)
            return

        if path == "/api/meu-perfil":
            # Perfil do próprio estudante: dados cadastrais (só leitura) e disponibilidade.
            sessao = self._exigir_papel({"estudante"})
            if sessao is None:
                return
            try:
                est = _estudante_da_sessao(sessao)
                if est is None:
                    self._send_error_json(404, "cadastro do estudante não encontrado")
                    return
                self._send_json(_perfil_do_estudante(est))
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/meu-perfil")
            return

        if path == "/api/relatorios/catalogo":
            if self._exigir_papel({"tecnico"}) is None:
                return
            self._send_json({"categorias": relatorios.catalogo(), "periodos": list(relatorios.PERIODOS)})
            return
        if path == "/api/estudantes":
            # Só técnico e supervisor consultam o cadastro de estudantes (nome + RA).
            sessao = self._exigir_papel({"tecnico", "supervisor"})
            if sessao is None:
                return
            _registrar_auditoria(sessao, "listagem de estudantes")
            try:
                self._send_json(_lista_estudantes_com_disponibilidade(sessao["role"] == "tecnico"))
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/estudantes")
            return

        if path.startswith("/api/admin/"):
            sessao = self._exigir_papel(PAPEIS_ADMIN)
            if sessao is None:
                return
            try:
                if path == "/api/admin/resumo":
                    docs = list(contas_col.find({"role": {"$in": list(FUNCOES_PROFISSIONAIS)}}))
                    self._send_json({
                        "tecnicos": sum(1 for d in docs if d["role"] == "tecnico"),
                        "supervisores": sum(1 for d in docs if d["role"] == "supervisor"),
                        "ativas": sum(1 for d in docs if d.get("status") == "ativa"),
                        "convites_pendentes": sum(1 for d in docs if d.get("status") == "convite_pendente"),
                    })
                    return
                if path == "/api/admin/profissionais":
                    docs = list(contas_col.find({"role": {"$in": list(FUNCOES_PROFISSIONAIS)}}).sort("criado_em", -1))
                    self._send_json([conta_db_to_json(d) for d in docs])
                    return
                if path == "/api/admin/historico":
                    docs = list(historico_admin_col.find({}).sort("quando", -1))[:300]
                    for d in docs:
                        d.pop("_id", None)
                    self._send_json(docs)
                    return
                if path == "/api/admin/minha-conta":
                    doc = contas_col.find_one({"_id": sessao["email"]})
                    if not doc:
                        self._send_error_json(404, "conta não encontrada")
                        return
                    self._send_json({"nome": doc.get("nome", ""), "email": doc["_id"], "funcao": doc.get("funcao", FUNCAO_ADMIN),
                                     "instituicao": doc.get("instituicao", INSTITUICAO), "status": doc.get("status", "")})
                    return
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET " + path)
                return
            self._send_error_json(404, "rota não encontrada")
            return

        if path == "/api/inscricoes":
            self._modulo_descontinuado()
            return
        if False:  # módulo de inscrição/triagem desativado (dados preservados no banco)
            # Dados pessoais de candidatos: só o psicólogo técnico acessa.
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            try:
                lista = [inscricao_doc_to_json(d) for d in inscricoes_col.find({}).sort("criado_em", -1)]
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/inscricoes")
                return
            _registrar_auditoria(sessao, "listagem de inscrições")
            self._send_json(lista)
            return

        if path == "/api/reagendamentos":
            if self._exigir_papel(PAPEIS_SOLICITACOES_LEITURA) is None:
                return
            try:
                fila = [reagendamento_doc_to_json(doc) for doc in reagendamentos_col.find({}).sort("_id", 1)]
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/reagendamentos")
                return
            self._send_json(fila)
            return

        if path == "/api/meu-cadastro":
            sessao = self._exigir_papel({"paciente"})
            if sessao is None:
                return
            try:
                caso = _encontrar_caso_do_paciente(sessao["nome"], sessao.get("caso_id"))
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/meu-cadastro")
                return
            if caso is None or not caso.get("cadastro"):
                self._send_json({"status": "nao_aplicavel"})
                return
            self._send_json(_dados_para_conferencia(caso))
            return

        if path == "/api/pacientes-acesso":
            # Só o técnico: situação do acesso de cada paciente (sem e-mail, sem hash, sem token).
            if self._exigir_papel({"tecnico"}) is None:
                return
            try:
                docs = list(contas_col.find({"role": "paciente"}))
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/pacientes-acesso")
                return
            self._send_json({d["caso_id"]: {"status": d.get("status", ""),
                                            "convite_expirado": bool(d.get("status") == "convite_pendente" and (d.get("convite") or {}).get("expira_em", 0) < time.time())}
                             for d in docs if d.get("caso_id")})
            return

        if path == "/api/meu-caso":
            # Correção de bug: a tela do paciente decidia "Ativo"/"Encerrado"
            # fixo pelo e-mail de login (resquício de dado de exemplo), em
            # vez de consultar o status real do caso no banco. Esta rota
            # devolve só o que o paciente precisa ver sobre o PRÓPRIO caso —
            # status, quando mudou pela última vez, e a próxima consulta —
            # nunca anamnese, evolução ou documento.
            sessao = self._exigir_papel({"paciente"})
            if sessao is None:
                return
            try:
                caso = _encontrar_caso_do_paciente(sessao["nome"], sessao.get("caso_id"))
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/meu-caso")
                return
            if caso is None:
                self._send_json({"tem_caso": False})
                return
            resposta = {
                "tem_caso": True,
                "status": caso.get("status", ""),
                "status_atualizado_em": caso.get("status_atualizado_em", ""),
                "proxima_consulta": _proxima_consulta(caso) if caso.get("status") == "Ativo" else None,
                "agendamentos": _agendamentos_do_paciente(caso) if caso.get("status") == "Ativo" else [],
            }
            _registrar_auditoria(sessao, "consulta do próprio status de caso", caso_id=caso.get("_id"))
            self._send_json(resposta)
            return

        if path == "/api/minhas-solicitacoes":
            # O paciente só vê as PRÓPRIAS solicitações (filtrado pelo nome da
            # sessão autenticada, não por um id que o navegador possa mandar)
            # — antes, não existia nenhuma forma de o paciente consultar o
            # status real de um pedido já feito; a tela só mostrava o que
            # tinha ficado salvo localmente no próprio navegador no momento
            # do pedido, e nunca atualizava depois.
            sessao = self._exigir_papel({"paciente"})
            if sessao is None:
                return
            try:
                fila = [
                    solicitacao_doc_to_json(doc)
                    for doc in solicitacoes_col.find({"paciente": sessao["nome"]}).sort("_id", 1)
                ]
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/minhas-solicitacoes")
                return
            self._send_json(fila)
            return

        if path == "/api/meu-prontuario":
            # Correção de segurança (não só uma conveniência de tela): o
            # acesso do paciente ao PRÓPRIO prontuário completo só é
            # concedido aqui, no servidor, quando existe de verdade uma
            # solicitação liberada pela equipe para este paciente — nunca
            # só porque a tela escondeu ou mostrou um botão. Sem isso,
            # qualquer paciente autenticado poderia chamar esta rota
            # diretamente e baixar o próprio prontuário sem nunca ter sido
            # liberado por ninguém.
            sessao = self._exigir_papel({"paciente"})
            if sessao is None:
                return
            try:
                liberada = solicitacoes_col.find_one(
                    {"paciente": sessao["nome"], "status": "liberado"}
                )
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/meu-prontuario (solicitação)")
                return
            if not liberada:
                _registrar_auditoria(
                    sessao, "tentativa de baixar prontuário sem liberação", resultado="negado"
                )
                self._send_error_json(403, "seu prontuário ainda não foi liberado pela equipe")
                return
            try:
                caso = _encontrar_caso_do_paciente(sessao["nome"], sessao.get("caso_id"))
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/meu-prontuario (caso)")
                return
            if caso is None:
                self._send_error_json(404, "nenhum caso encontrado para este paciente")
                return
            _registrar_auditoria(
                sessao,
                "download do próprio prontuário",
                caso_id=caso.get("_id"),
                detalhe="protocolo " + str(liberada.get("protocolo", "")),
            )
            resposta = caso_doc_to_json(caso)
            resposta["protocolo"] = liberada.get("protocolo", "")
            # Documentos excluídos logicamente não aparecem no prontuário entregue ao paciente.
            resposta["documentos"] = [d for d in (resposta.get("documentos") or []) if d.get("status") != "excluido"]
            self._send_json(resposta)
            return

        self._send_error_json(404, "rota não encontrada: " + path)

    def _serve_audio(self, arquivo):
        """Entrega um MP3 com suporte a 'Range' (necessário para tocar e pular no Safari/iPhone)."""
        if not arquivo.exists():
            self._send_error_json(404, "áudio não encontrado")
            return
        dados = arquivo.read_bytes()
        total = len(dados)
        inicio, fim, status = 0, total - 1, 200
        faixa = self.headers.get("Range", "")
        m = re.match(r"^bytes=(\d*)-(\d*)$", faixa.strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                inicio = int(m.group(1))
                fim = int(m.group(2)) if m.group(2) else total - 1
            else:  # últimos N bytes
                inicio = max(0, total - int(m.group(2)))
            fim = min(fim, total - 1)
            if inicio > fim or inicio >= total:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % total)
                self.send_header("Content-Length", "0")
                self._security_headers()
                self.end_headers()
                return
            status = 206
        corpo = dados[inicio:fim + 1]
        self.send_response(status)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (inicio, fim, total))
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self._cors_headers()
        self._security_headers()
        self.end_headers()
        try:
            self.wfile.write(corpo)
        except (BrokenPipeError, ConnectionResetError):
            pass  # o navegador cancelou (ex.: trocou de página)

    def _serve_html(self):
        if not HTML_FILE.exists():
            self._send_error_json(404, "psicare-site-v2.html não encontrado nesta pasta")
            return
        with open(HTML_FILE, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self._cors_headers()
        self._security_headers()
        self.end_headers()
        self.wfile.write(content)

    # ---------- POST ----------
    def do_POST(self):
        path = self.path.split("?", 1)[0]

        if path == "/api/login":
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return

            email = str(body.get("email", "")).strip().lower()
            senha = str(body.get("senha", ""))

            agora = time.time()
            tentativa = TENTATIVAS_LOGIN.get(email)
            if tentativa and tentativa.get("bloqueado_ate") and agora < tentativa["bloqueado_ate"]:
                espera_min = int((tentativa["bloqueado_ate"] - agora) // 60) + 1
                self._send_error_json(
                    429,
                    "muitas tentativas de login com este e-mail. Tente novamente em cerca de %d minuto(s)." % espera_min,
                )
                return

            conta = CONTAS.get(email)
            if conta is not None:
                senha_ok = conta["senha_hash"] == _hash_senha(senha)
                if senha_ok and conta.get("role") == "estudante" and _ra_inativo(conta.get("ra")):
                    senha_ok = False  # estudante desativado pelo técnico
            else:
                # Não é conta de demonstração: procura nas contas gravadas no
                # banco. Só entra quem está "ativa" e já criou a senha pelo
                # convite; convite pendente e conta desativada recebem a mesma
                # resposta genérica de credenciais incorretas.
                try:
                    doc_conta = contas_col.find_one({"_id": email}) if EMAIL_REGEX.match(email) else None
                except PyMongoError as exc:
                    self._erro_servidor(exc, "POST /api/login")
                    return
                senha_ok = False
                if doc_conta and doc_conta.get("status") == "ativa" and doc_conta.get("senha_hash") and doc_conta.get("salt"):
                    senha_ok = hmac.compare_digest(doc_conta["senha_hash"], _hash_senha_salt(senha, doc_conta["salt"]))
                    if senha_ok:
                        conta = {"role": doc_conta["role"], "nome": doc_conta["nome"], "caso_id": doc_conta.get("caso_id")}
                else:
                    _hash_senha_salt(senha, "00" * 16)  # custo parecido, para não revelar se o e-mail existe
                if not senha_ok:
                    conta = None
            if not conta or not senha_ok:
                t = TENTATIVAS_LOGIN.setdefault(email, {"falhas": 0, "bloqueado_ate": None})
                t["falhas"] += 1
                if t["falhas"] >= MAX_TENTATIVAS:
                    t["bloqueado_ate"] = agora + BLOQUEIO_SEGUNDOS
                    t["falhas"] = 0
                _registrar_auditoria({"email": email}, "login", resultado="negado", detalhe="credenciais inválidas")
                # Mensagem genérica de propósito: não diz se o e-mail existe ou
                # não, nem qual dos dois campos está errado (evita que alguém
                # descubra, por tentativa e erro, quais e-mails têm conta).
                self._send_error_json(401, "e-mail ou senha incorretos")
                return

            TENTATIVAS_LOGIN.pop(email, None)
            token = secrets.token_urlsafe(32)
            SESSOES[token] = {
                "email": email,
                "role": conta["role"],
                "nome": conta["nome"],
                "caso_id": conta.get("caso_id"),
                "criado_em": agora,
            }
            _registrar_auditoria(SESSOES[token], "login", resultado="sucesso")
            self._send_json({"token": token, "role": conta["role"], "nome": conta["nome"]})
            return

        if path == "/api/logout":
            # Correção de segurança: antes não existia NENHUMA rota de
            # logout — "sair" só apagava o token guardado no navegador
            # (sessionStorage), mas o token continuava válido no servidor até
            # expirar sozinho (até 8h depois). Se alguém roubasse esse token
            # (por exemplo, um computador compartilhado esquecido logado),
            # clicar em "sair" não adiantava nada contra esse roubo. Agora o
            # token é removido de verdade da lista de sessões no servidor.
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[len("Bearer "):].strip()
                sessao = SESSOES.pop(token, None)
                if sessao:
                    _registrar_auditoria(sessao, "logout", resultado="sucesso")
            self._send_json({"ok": True})
            return

        if path == "/api/relatorios":
            sessao_rl = self._exigir_papel({"tecnico"})
            if sessao_rl is None:
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido"); return
            agora_br = _dt.datetime.utcnow() - _dt.timedelta(hours=3)
            try:
                ids = relatorios.validar_indicadores(body.get("tipo"), body.get("indicadores"))
                ini, fim, rotulo = relatorios.resolver_periodo(body.get("periodo"), agora_br.date(), body.get("inicio"), body.get("fim"))
            except ValueError as exc:
                self._send_error_json(400, str(exc)); return
            try:
                secoes = relatorios.gerar(_dados_para_relatorio(), ids, ini, fim, agora_br)
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/relatorios"); return
            _registrar_auditoria(sessao_rl, "relatório gerencial gerado (%s, %s)" % (body.get("tipo"), rotulo))
            self._send_json({"tipo": body.get("tipo"), "periodo": body.get("periodo"), "periodo_rotulo": rotulo,
                             "inicio": ini.isoformat(), "fim": fim.isoformat(),
                             "gerado_em": agora_br.strftime("%d/%m/%Y às %Hh%M"), "gerado_por": sessao_rl.get("nome", ""),
                             "indicadores": ids, "secoes": secoes})
            return

        if path == "/api/recuperar-senha":
            # Recuperação de senha de verdade: antes, a tela de "esqueci minha
            # senha" só verificava CPF/RA + data de nascimento no navegador
            # (nenhuma chamada ao servidor) e revelava, no próprio site, qual
            # era a senha "redefinida" (o CPF ou o RA) — e a dica de CPF/RA de
            # demonstração ficava exposta na tela de login para qualquer
            # visitante ver. Esta rota substitui isso por uma redefinição
            # real no servidor: recebe só o e-mail, gera uma senha temporária
            # aleatória, grava o novo hash em CONTAS e manda a senha por
            # e-mail (nunca na resposta HTTP). A resposta é sempre a mesma
            # (200, {"ok": true}), exista ou não o e-mail, para não revelar
            # quais contas existem.
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return

            email = str(body.get("email", "")).strip().lower()
            if not email or not EMAIL_REGEX.match(email):
                self._send_error_json(400, "informe um e-mail válido")
                return

            agora = time.time()
            tentativa = TENTATIVAS_RECUPERACAO.get(email)
            if tentativa and tentativa.get("bloqueado_ate") and agora < tentativa["bloqueado_ate"]:
                # Mesmo bloqueada, a resposta não diz isso ao navegador — só
                # registramos no servidor e respondemos como sempre, para não
                # dar pista de que esse e-mail existe e está sendo testado.
                print("[recuperar-senha] %s bloqueado por excesso de pedidos" % email)
                self._send_json({"ok": True, "email_enviado": False})
                return

            t = TENTATIVAS_RECUPERACAO.setdefault(email, {"pedidos": 0, "bloqueado_ate": None})
            t["pedidos"] += 1
            if t["pedidos"] >= MAX_PEDIDOS_RECUPERACAO:
                t["bloqueado_ate"] = agora + BLOQUEIO_RECUPERACAO_SEGUNDOS
                t["pedidos"] = 0

            conta = CONTAS.get(email)
            email_enviado = False
            if not conta:
                # Contas reais (convite ativado) ficam no banco, não em CONTAS: só as que estão
                # "ativa" e já criaram a senha recebem a redefinição.
                try:
                    doc_rec = contas_col.find_one({"_id": email})
                except PyMongoError as exc:
                    self._erro_servidor(exc, "POST /api/recuperar-senha")
                    return
                if doc_rec and doc_rec.get("status") == "ativa" and doc_rec.get("senha_hash") and doc_rec.get("salt"):
                    nova_senha = _gerar_senha_temporaria()
                    novo_salt = secrets.token_hex(16)
                    try:
                        contas_col.update_one({"_id": email}, {"$set": {"salt": novo_salt, "senha_hash": _hash_senha_salt(nova_senha, novo_salt)}})
                    except PyMongoError as exc:
                        self._erro_servidor(exc, "POST /api/recuperar-senha (gravação)")
                        return
                    for tok in [t_ for t_, s_ in SESSOES.items() if s_.get("email") == email]:
                        SESSOES.pop(tok, None)
                    TENTATIVAS_LOGIN.pop(email, None)
                    email_enviado = _enviar_senha_temporaria(email, doc_rec.get("nome"), nova_senha)
                    print("[recuperar-senha] senha redefinida para %s (conta do banco; e-mail %s)"
                          % (email, "enviado" if email_enviado else "NÃO enviado — veja o motivo acima"))
                    self._send_json({"ok": True, "email_enviado": email_enviado})
                    return
            if conta:
                nova_senha = _gerar_senha_temporaria()
                conta["senha_hash"] = _hash_senha(nova_senha)
                SESSOES_PARA_REMOVER = [tok for tok, s in SESSOES.items() if s.get("email") == email]
                for tok in SESSOES_PARA_REMOVER:
                    SESSOES.pop(tok, None)
                email_enviado = _enviar_senha_temporaria(email, conta["nome"], nova_senha)
                print(
                    "[recuperar-senha] senha redefinida para %s (e-mail %s)"
                    % (email, "enviado" if email_enviado else "NÃO enviado — SMTP não configurado")
                )
            else:
                print("[recuperar-senha] pedido para e-mail não cadastrado: %s" % email)

            self._send_json({"ok": True, "email_enviado": email_enviado})
            return

        if path == "/api/meu-cadastro":
            sessao = self._exigir_papel({"paciente"})
            if sessao is None:
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            try:
                caso = _encontrar_caso_do_paciente(sessao["nome"], sessao.get("caso_id"))
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/meu-cadastro")
                return
            if caso is None or (caso.get("confirmacao") or {}).get("status") != "pendente":
                self._send_error_json(409, "não há conferência de dados pendente para esta conta")
                return
            acao = body.get("acao")
            agora = _agora_br()
            conf = {"status": "confirmado", "confirmado_em_br": agora, "houve_correcao": False,
                    "atualizacao_nao_vista": False, "correcoes": []}
            set_campos = {"confirmacao": conf}
            nome_antigo = caso.get("paciente", "")
            nome_novo = nome_antigo
            if acao == "corrigir":
                nome_novo, cadastro_novo, mudancas, erro = _aplicar_correcoes(caso, body.get("alteracoes"))
                if erro:
                    self._send_error_json(400, erro)
                    return
                conf["houve_correcao"] = True
                conf["atualizacao_nao_vista"] = True
                conf["correcoes"] = [{"em_br": agora, "alteracoes": mudancas}]
                set_campos["cadastro"] = cadastro_novo
                set_campos["paciente"] = nome_novo
            elif acao != "confirmar":
                self._send_error_json(400, "ação inválida")
                return
            try:
                # Só grava se ainda estiver pendente (duplo clique não confirma duas vezes).
                r = casos_col.update_one({"_id": caso["_id"], "confirmacao.status": "pendente"}, {"$set": set_campos})
                if r.matched_count == 0:
                    self._send_error_json(409, "estes dados já foram conferidos")
                    return
                if nome_novo != nome_antigo:
                    # O nome é a chave que liga as solicitações e reagendamentos desta paciente.
                    solicitacoes_col.update_many({"paciente": nome_antigo}, {"$set": {"paciente": nome_novo}})
                    reagendamentos_col.update_many({"paciente": nome_antigo}, {"$set": {"paciente": nome_novo}})
                    contas_col.update_one({"_id": sessao["email"]}, {"$set": {"nome": nome_novo}})
                    for s_ in SESSOES.values():
                        if s_.get("email") == sessao["email"]:
                            s_["nome"] = nome_novo
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/meu-cadastro")
                return
            _registrar_auditoria(sessao, "conferência dos dados cadastrais (%s)" % ("com correção" if conf["houve_correcao"] else "confirmados"), caso_id=caso["_id"])
            self._send_json({"ok": True, "status": "confirmado", "houve_correcao": conf["houve_correcao"]})
            return

        if path == "/api/ativar-conta":
            # Primeiro acesso por convite: a pessoa abre o link, escolhe a senha
            # e a conta passa a "ativa". Rota pública de propósito (quem ainda
            # não tem senha não pode estar logado), mas só funciona com um token
            # de convite válido, de uso único e dentro do prazo.
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            token = str(body.get("token", "")).strip()
            senha = body.get("senha", "")
            invalido = "link de ativação inválido ou expirado — peça um novo convite à Administração de TI"
            if not (20 <= len(token) <= 100):
                self._send_error_json(400, invalido)
                return
            h = hashlib.sha256(token.encode("utf-8")).hexdigest()
            try:
                doc = contas_col.find_one({"convite.token_hash": h, "status": "convite_pendente"})
                if not doc or (doc.get("convite") or {}).get("expira_em", 0) < time.time():
                    self._send_error_json(400, invalido)
                    return
                erro_senha = _validar_senha_nova(senha, doc.get("role"))
                if erro_senha:
                    self._send_error_json(400, erro_senha)
                    return
                salt = secrets.token_hex(16)
                r = contas_col.update_one(
                    {"_id": doc["_id"], "status": "convite_pendente", "convite.token_hash": h},
                    {"$set": {"salt": salt, "senha_hash": _hash_senha_salt(senha, salt), "status": "ativa",
                              "ativada_em_br": _agora_br(), "convite": None}},
                )
                if r.matched_count == 0:
                    self._send_error_json(400, invalido)
                    return
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/ativar-conta")
                return
            try:
                funcao_a = FUNCOES_PROFISSIONAIS.get(doc.get("role")) or doc.get("role") or "conta"
                if doc.get("role") != "admin_ti":
                    _avisar_tecnico("conta_ativada", "%s (%s)" % (doc.get("nome") or doc["_id"], funcao_a))
            except PyMongoError:
                pass
            if doc.get("role") != "paciente":
                # O histórico administrativo não recebe nada de pacientes.
                _registrar_historico_admin({"email": doc["_id"], "nome": doc.get("nome", "")}, "Primeiro acesso concluído (senha criada)", doc["_id"])
            _registrar_auditoria({"email": doc["_id"], "nome": doc.get("nome", ""), "role": doc.get("role")}, "ativação de conta por convite")
            self._send_json({"ok": True, "email": doc["_id"], "nome": doc.get("nome", ""), "role": doc.get("role", "")})
            return

        if path == "/api/admin/profissionais":
            sessao = self._exigir_papel(PAPEIS_ADMIN)
            if sessao is None:
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            email = str(body.get("email", "")).strip().lower()
            tipo = str(body.get("tipo", ""))
            situacao = str(body.get("situacao_inicial", "ativa"))
            if not EMAIL_REGEX.match(email):
                self._send_error_json(400, "informe um e-mail profissional válido")
                return
            if tipo not in FUNCOES_PROFISSIONAIS:
                # Só técnico e supervisor: não cria paciente, estudante nem outro administrador.
                self._send_error_json(400, "o tipo de perfil precisa ser Psicólogo técnico ou Supervisor")
                return
            if situacao not in ("ativa", "desativada"):
                self._send_error_json(400, "situação inicial inválida")
                return
            dados, erro = _validar_dados_profissional(body)
            if erro:
                self._send_error_json(400, erro)
                return
            try:
                if email in CONTAS or contas_col.find_one({"_id": email}):
                    self._send_error_json(409, "já existe uma conta com este e-mail")
                    return
                doc = {"_id": email, "nome": dados["nome"], "role": tipo, "crp": dados["crp"], "salt": None, "senha_hash": None,
                       "criado_em": time.time(), "criado_em_br": _agora_br(), "criado_por": sessao["email"]}
                token = None
                if situacao == "ativa":
                    token, convite = _novo_convite()
                    doc.update(status="convite_pendente", convite=convite)
                else:
                    doc.update(status="desativada", convite=None)
                contas_col.insert_one(dict(doc))
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/admin/profissionais")
                return
            convite_resp = None
            if token:
                convite_resp = _resposta_convite(_enviar_convite(email, dados["nome"], tipo, token), token)
            _registrar_historico_admin(sessao, "Conta de %s criada (%s)" % (FUNCOES_PROFISSIONAIS[tipo].lower(), "convite gerado" if token else "criada desativada"), email)
            self._send_json({"profissional": conta_db_to_json(doc), "convite": convite_resp}, 201)
            return

        if path == "/api/inscricoes":
            self._modulo_descontinuado()
            return
        if False:  # módulo de inscrição/triagem desativado (dados preservados no banco)
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            dados, erro = _validar_inscricao(body)
            if erro:
                self._send_error_json(400, erro)
                return
            try:
                aberta = inscricoes_col.find_one(
                    {"cpf": dados["cpf"], "status": {"$in": [ST_INS_RECEBIDO, ST_INS_ANALISADO, ST_INS_TRIAGEM, ST_INS_APROVADO]}}
                )
                if aberta:
                    self._send_error_json(409, "já existe uma inscrição em andamento com este CPF (%s)" % aberta["_id"])
                    return
                doc = {
                    "_id": novo_id_de_inscricao(),
                    **dados,
                    "status": ST_INS_RECEBIDO,
                    "criado_em": time.time(),
                    "criado_em_br": _agora_br(),
                    "triagem": {"agendamento": None, "resultado": None, "resultado_em": "", "observacao": "", "comunicacao_pendente": False},
                    "caso_id": None,
                    "historico": [_evento_inscricao(sessao, "Inscrição registrada no sistema")],
                }
                inscricoes_col.insert_one(dict(doc))
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/inscricoes")
                return
            _registrar_auditoria(sessao, "registro de inscrição", detalhe=doc["_id"])
            self._send_json(inscricao_doc_to_json(doc), 201)
            return

        if path == "/api/estudantes":
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            dados, erro = _validar_estudante(body)
            if erro:
                self._send_error_json(400, erro); return
            situacao = str(body.get("situacao_inicial", "ativa"))
            sup = str(body.get("supervisor", "")).strip()
            if situacao not in ("ativa", "desativada"):
                self._send_error_json(400, "situação inicial inválida"); return
            token = None
            with TRAVA_OPERACOES:
                try:
                    if sup not in {x["nome"] for x in _lista_supervisores_ativos()}:
                        self._send_error_json(400, "selecione o supervisor responsável (um supervisor ativo)"); return
                    existentes = _lista_estudantes()
                    if dados["email"] in CONTAS or contas_col.find_one({"_id": dados["email"]}) or any(e["email"] == dados["email"] for e in existentes):
                        self._send_error_json(409, "já existe uma conta com este e-mail"); return
                    if any(e["ra"] == dados["ra"] for e in existentes):
                        self._send_error_json(409, "já existe um estudante com esta matrícula/RA"); return
                    if any(e["nome"].casefold() == dados["nome"].casefold() for e in existentes):
                        self._send_error_json(409, "já existe um estudante com este nome: acrescente um sobrenome para diferenciá-los"); return
                    agora = _agora_br()
                    estudantes_col.insert_one({"_id": dados["ra"], "nome": dados["nome"], "email": dados["email"], "telefone": dados["telefone"],
                                               "ativo": situacao == "ativa", "criado_em_br": agora, "criado_por": sessao["email"]})
                    conta = {"_id": dados["email"], "nome": dados["nome"], "role": "estudante", "ra": dados["ra"], "salt": None, "senha_hash": None,
                             "criado_em": time.time(), "criado_em_br": agora, "criado_por": sessao["email"]}
                    if situacao == "ativa":
                        token, convite = _novo_convite()
                        conta.update(status="convite_pendente", convite=convite)
                    else:
                        conta.update(status="desativada", convite=None)
                    contas_col.insert_one(conta)
                    _gravar_vinculo(dados["ra"], dados["nome"], sup, sessao["nome"])
                    resumo = _resumo_estudante(dados["ra"])
                except PyMongoError as exc:
                    self._erro_servidor(exc, "POST /api/estudantes")
                    return
            convite_resp = _resposta_convite(_enviar_convite(dados["email"], dados["nome"], "estudante", token), token) if token else None
            _registrar_auditoria(sessao, "estudante cadastrado", detalhe="%s (RA %s), supervisor %s" % (dados["nome"], dados["ra"], sup))
            self._send_json({"estudante": resumo, "convite": convite_resp}, 201)
            return

        m = re.match(r"^/api/estudantes/([^/]+)/convite$", path)
        if m:
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            ra = unquote(m.group(1))
            try:
                est = _estudante_por_ra(ra)
                conta = contas_col.find_one({"_id": est["email"]}) if est and est["email"] else None
                if conta is None:
                    self._send_error_json(404, "este estudante não tem conta de acesso cadastrada"); return
                if conta.get("status") != "convite_pendente":
                    self._send_error_json(409, "o convite só pode ser reenviado enquanto a conta está pendente de ativação"); return
                token, convite = _novo_convite()
                contas_col.update_one({"_id": conta["_id"], "status": "convite_pendente"}, {"$set": {"convite": convite}})
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/estudantes/<ra>/convite")
                return
            convite_resp = _resposta_convite(_enviar_convite(est["email"], est["nome"], "estudante", token), token)
            _registrar_auditoria(sessao, "convite de estudante reenviado", detalhe="%s (RA %s)" % (est["nome"], ra))
            self._send_json({"ok": True, "convite": convite_resp})
            return

        m = re.match(r"^/api/casos/([^/]+)/agendamentos/(\d+)/comparecimento$", path)
        if m:
            self._tratar_comparecimento(unquote(m.group(1)), int(m.group(2)), False)
            return

        m = re.match(r"^/api/casos/([^/]+)/documentos$", path)
        if m:
            sessao = self._exigir_papel(PAPEIS_CASOS)
            if sessao is None:
                return
            case_id = unquote(m.group(1))
            tamanho_req = int(self.headers.get("Content-Length", 0) or 0)
            if tamanho_req > int(DOC_MAX_BYTES * 1.4) + 4096:
                # Não guarda o corpo (nada de memória): só descarta o que chegou, para o navegador receber a resposta 413.
                restante = min(tamanho_req, 64 * 1024 * 1024)
                try:
                    while restante > 0:
                        pedaco = self.rfile.read(min(65536, restante))
                        if not pedaco:
                            break
                        restante -= len(pedaco)
                except Exception:
                    pass
                self.close_connection = True
                self._send_error_json(413, "o arquivo ultrapassa o limite de 10 MB")
                return
            if not _UPLOADS_SIMULTANEOUS.acquire(blocking=False):
                self._send_error_json(503, "muitos envios ao mesmo tempo; tente novamente em instantes")
                return
            gfs_id = None
            doc_gravado = False
            try:
                try:
                    body = self._read_json_body()
                    dados = base64.b64decode(str(body.get("conteudo", "")), validate=True)
                except Exception:
                    self._send_error_json(400, "envio inválido"); return
                try:
                    caso = casos_col.find_one({"_id": case_id})
                except PyMongoError as exc:
                    self._erro_servidor(exc, "POST /api/casos/<id>/documentos"); return
                if caso is None:
                    self._send_error_json(404, "caso não encontrado"); return
                if not _pode_anexar_documento(sessao, caso):
                    _registrar_auditoria(sessao, "tentativa de anexar documento sem permissão", caso_id=case_id, resultado="negado")
                    self._send_error_json(403, "seu perfil não pode anexar documentos a este caso"); return
                tipo_doc = str(body.get("tipo", "")).strip()
                if tipo_doc not in DOC_TIPOS:
                    self._send_error_json(400, "escolha o tipo do documento"); return
                obs = str(body.get("observacao", "") or "").strip()
                if len(obs) > DOC_OBS_MAX:
                    self._send_error_json(400, "a observação pode ter até %d caracteres" % DOC_OBS_MAX); return
                erro, nome_limpo, ctype = _validar_upload(body.get("nome", ""), dados)
                if erro:
                    _registrar_auditoria(sessao, "envio de documento recusado", caso_id=case_id, resultado="negado", detalhe=erro[:120])
                    self._send_error_json(400, erro); return
                try:
                    usado = sum(int(x.get("tamanho", 0)) for x in documentos_col.find({}))
                except PyMongoError as exc:
                    self._erro_servidor(exc, "POST /api/casos/<id>/documentos (cota)"); return
                if usado + len(dados) > DOC_QUOTA_BYTES:
                    self._send_error_json(507, "o espaço de armazenamento de documentos está cheio; avise a equipe técnica")
                    return
                doc_id = "doc-" + secrets.token_hex(8)
                try:
                    gfs_id = str(documentos_fs.put(dados, filename=doc_id, content_type=ctype))
                    meta = {"_id": doc_id, "caso_id": case_id, "nome_original": nome_limpo, "tipo_doc": tipo_doc, "observacao": obs,
                            "content_type": ctype, "tamanho": len(dados), "sha256": hashlib.sha256(dados).hexdigest(), "gridfs_id": gfs_id,
                            "enviado_por_email": sessao["email"], "enviado_por_nome": sessao["nome"], "enviado_por_papel": sessao["role"],
                            "enviado_em": time.time(), "enviado_em_data": _agora_br().split(" às ")[0], "status": "ativo"}
                    documentos_col.insert_one(meta)
                    doc_gravado = True
                    casos_col.update_one({"_id": case_id}, {"$push": {"documentos": _doc_publico(meta)}})
                    _evento_documento(sessao, "envio", case_id, doc_id)
                except (PyMongoError, AuditoriaFalhou, Exception) as exc:
                    # Desfaz o que acabou de ser gravado: o envio não terminou, então nada fica órfão.
                    print("ERRO (envio de documento): %s" % exc)
                    try:
                        casos_col.update_one({"_id": case_id}, {"$pull": {"documentos": {"id": doc_id}}})
                    except Exception:
                        pass
                    if doc_gravado:
                        try:
                            documentos_col.delete_one({"_id": doc_id})
                        except Exception:
                            pass
                    if gfs_id:
                        try:
                            documentos_fs.delete(ObjectId(gfs_id))
                        except Exception:
                            pass
                    self._send_error_json(503, "não foi possível salvar o documento agora. Tente novamente em instantes.")
                    return
            finally:
                _UPLOADS_SIMULTANEOUS.release()
            _avisar_documento_anexado(caso, meta, sessao)
            self._send_json(_doc_publico(meta), 201)
            return

        m = re.match(r"^/api/casos/([^/]+)/documentos/([^/]+)/exclusao$", path)
        if m:
            sessao = self._exigir_papel(PAPEIS_CASOS)
            if sessao is None:
                return
            case_id, doc_id = unquote(m.group(1)), unquote(m.group(2))
            if not DOC_EXCLUSAO_HABILITADA:
                _registrar_auditoria(sessao, "tentativa de excluir documento (recurso desabilitado)", caso_id=case_id, resultado="negado")
                self._send_error_json(403, "a exclusão de documentos ainda não foi habilitada (depende de aprovação institucional)")
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido"); return
            motivo = str(body.get("motivo", "")).strip()
            if body.get("confirmar") is not True:
                self._send_error_json(400, "confirme a exclusão"); return
            if not (DOC_MOTIVO_MIN <= len(motivo) <= DOC_MOTIVO_MAX):
                self._send_error_json(400, "informe o motivo da exclusão (de %d a %d caracteres)" % (DOC_MOTIVO_MIN, DOC_MOTIVO_MAX)); return
            try:
                caso = casos_col.find_one({"_id": case_id})
                if caso is None:
                    self._send_error_json(404, "caso não encontrado"); return
                if not _pode_excluir_documento(sessao, caso):
                    _registrar_auditoria(sessao, "tentativa de excluir documento sem permissão", caso_id=case_id, resultado="negado")
                    self._send_error_json(403, "seu perfil não pode excluir documentos deste caso"); return
                d = documentos_col.find_one({"_id": doc_id, "caso_id": case_id})
                if d is None or d.get("status") == "excluido":
                    self._send_error_json(404, "documento não encontrado"); return
                marca = {"status": "excluido", "excluido_por_nome": sessao["nome"], "excluido_por_email": sessao["email"],
                         "excluido_em": time.time(), "excluido_em_br": _agora_br(), "motivo_exclusao": motivo}
                _evento_documento(sessao, "exclusao_logica", case_id, doc_id, motivo=motivo)  # auditoria primeiro
                documentos_col.update_one({"_id": doc_id}, {"$set": marca})
                casos_col.update_one({"_id": case_id, "documentos.id": doc_id}, {"$set": {"documentos.$.status": "excluido"}})
            except AuditoriaFalhou:
                self._send_error_json(503, "não foi possível registrar a exclusão; nada foi alterado"); return
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/casos/<id>/documentos/<doc>/exclusao"); return
            self._send_json({"ok": True, "id": doc_id})
            return

        m = re.match(r"^/api/casos/([^/]+)/exportacoes$", path)
        if m:
            sessao = self._exigir_papel(PAPEIS_CASOS)
            if sessao is None:
                return
            case_id = unquote(m.group(1))
            try:
                caso = casos_col.find_one({"_id": case_id})
                if caso is None:
                    self._send_error_json(404, "caso não encontrado"); return
                if not _pode_acessar_caso(sessao, caso):
                    _registrar_auditoria(sessao, "tentativa de exportar prontuário sem acesso", caso_id=case_id, resultado="negado")
                    self._send_error_json(403, "sem permissão para este caso"); return
                reg = _proximo_protocolo(sessao, case_id)
                try:
                    auditoria_col.insert_one({"quando": reg["quando"], "usuario_email": sessao["email"], "usuario_nome": sessao["nome"],
                                              "papel": sessao["role"], "acao": "exportação do prontuário", "caso_id": case_id,
                                              "resultado": "sucesso", "detalhe": "protocolo #%s" % reg["_id"]})
                except PyMongoError:
                    raise AuditoriaFalhou()
            except AuditoriaFalhou:
                self._send_error_json(503, "não foi possível registrar a exportação; o PDF não foi gerado"); return
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/casos/<id>/exportacoes"); return
            self._send_json({"protocolo": str(reg["_id"]), "quando_br": reg["quando_br"]}, 201)
            return

        m = re.match(r"^/api/casos/([^/]+)/evolucoes/(\d+)/notas$", path)
        if m:
            # Nota de acompanhamento (técnico ou supervisor). Registro adicional e separado: a evolução
            # original não é tocada e a nota nunca é editada nem apagada.
            sessao = self._exigir_papel({"tecnico", "supervisor"})
            if sessao is None:
                return
            case_id, idx = unquote(m.group(1)), int(m.group(2))
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            texto = str(body.get("texto", "")).strip()
            if not texto or len(texto) > NOTA_MAX:
                self._send_error_json(400, "escreva a nota (até %d caracteres)" % NOTA_MAX); return
            try:
                caso = casos_col.find_one({"_id": case_id})
                if caso is None:
                    self._send_error_json(404, "caso não encontrado"); return
                if not _pode_acessar_caso(sessao, caso):
                    _registrar_auditoria(sessao, "tentativa de criar nota em caso sem acesso", caso_id=case_id, resultado="negado")
                    self._send_error_json(403, "sem permissão para este caso"); return
                if idx >= len(caso.get("evolucoes") or []):
                    self._send_error_json(404, "evolução não encontrada"); return
                agora_ts = time.time()
                nota = {"_id": "nt-" + secrets.token_hex(6), "caso_id": case_id, "evolucao_idx": idx, "autor": sessao["nome"],
                        "autor_email": sessao["email"], "autor_papel": sessao["role"], "criado_em": agora_ts, "criado_em_br": _agora_br(), "texto": texto,
                        "destinatario": caso.get("estudante") or ""}
                notas_col.insert_one(nota)
                if nota["destinatario"]:
                    notificacoes_col.insert_one({"_id": "nf-" + secrets.token_hex(6), "tipo": "nota_acompanhamento", "destinatario": nota["destinatario"],
                                                 "caso_id": case_id, "evolucao_idx": idx, "nota_id": nota["_id"], "autor_papel": sessao["role"], "criada_em": agora_ts,
                                                 "criada_em_br": nota["criado_em_br"], "lida": False})
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/casos/<id>/evolucoes/<n>/notas")
                return
            _registrar_auditoria(sessao, "nota de acompanhamento adicionada", caso_id=case_id, detalhe="evolução %d" % (idx + 1))
            self._send_json({"id": nota["_id"], "evolucao": idx, "autor": nota["autor"], "criado_em_br": nota["criado_em_br"],
                             "texto": nota["texto"], "lida_em_br": "", "papel": nota["autor_papel"], "notificado": bool(nota["destinatario"])}, 201)
            return

        m = re.match(r"^/api/casos/([^/]+)/agendamentos$", path)
        if m:
            # Novo agendamento (Agenda principal ou atalho no prontuário): só o técnico.
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            case_id = unquote(m.group(1))
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            data, hora = _data_para_br(body.get("data")), _hora_para_br(body.get("hora"))
            local = str(body.get("local", "")).strip()
            if not data:
                self._send_error_json(400, "data inválida"); return
            if not hora:
                self._send_error_json(400, "horário inválido"); return
            if not local or len(local) > 200:
                self._send_error_json(400, "informe o local do atendimento (até 200 caracteres)"); return
            if _parse_data_br(data) < _parse_data_br(_hoje_br()):
                self._send_error_json(400, "não é possível agendar em uma data que já passou"); return
            with TRAVA_OPERACOES:
                try:
                    caso = casos_col.find_one({"_id": case_id})
                    if caso is None:
                        self._send_error_json(404, "caso não encontrado"); return
                    if caso.get("status") != "Ativo":
                        self._send_error_json(409, "o caso está encerrado: reabra-o antes de agendar"); return
                    if not (caso.get("estudante") or "").strip():
                        self._send_error_json(409, "o paciente ainda não tem estudante responsável: faça a alocação antes de agendar"); return
                    conflito = _conflito_agenda(data, hora, case_id, caso.get("estudante"))
                    if conflito:
                        self._send_error_json(409, conflito); return
                    ags = list(caso.get("agendamentos") or [])
                    ags.append({"data": data, "hora": hora, "local": local, "status": "Confirmada",
                                "criado_por": sessao["nome"], "criado_em": _agora_br()})
                    casos_col.update_one({"_id": case_id}, {"$set": {"agendamentos": ags}})
                    novo = casos_col.find_one({"_id": case_id})
                    _avisar_estudante(caso, "novo_agendamento", "%s às %s" % (data, hora))
                    _avisar_paciente(caso, "novo_agendamento", "%s às %s · %s" % (data, hora, local), "%s %s" % (data, hora))
                    _avisar_supervisor_do_caso(caso, "novo_agendamento", "%s às %s · %s" % (data, hora, caso.get("estudante", "")))
                except PyMongoError as exc:
                    self._erro_servidor(exc, "POST /api/casos/<id>/agendamentos")
                    return
            _registrar_auditoria(sessao, "agendamento criado", caso_id=case_id, detalhe="%s %s" % (data, hora))
            self._send_json({"ok": True, "indice": len(ags) - 1, "caso": caso_doc_to_json(novo)})
            return

        if path == "/api/casos":
            # Correção de segurança: cadastrar um paciente novo é uma ação
            # administrativa — a própria tela só mostra esse formulário para o
            # técnico (estudante e supervisor nunca veem esse botão). O
            # servidor não garantia isso: qualquer um dos três papéis podia
            # criar um caso novo chamando a API diretamente.
            sessao_cadastro = self._exigir_papel({"tecnico"})
            if sessao_cadastro is None:
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return

            nome_paciente = str(body.get("paciente", "")).strip()
            if not nome_paciente:
                self._send_error_json(400, "o campo 'paciente' é obrigatório para cadastrar um caso")
                return

            status_val = body.get("status", "Ativo")
            if status_val not in STATUS_CASO_VALIDOS:
                self._send_error_json(
                    400,
                    "status inválido: '%s' (valores aceitos: %s)" % (status_val, ", ".join(sorted(STATUS_CASO_VALIDOS))),
                )
                return

            supervisor_resp = str(body.get("supervisor", "")).strip()
            try:
                supervisores_ok = {x["nome"] for x in _lista_supervisores_ativos()}
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/casos (supervisores)")
                return
            if supervisor_resp not in supervisores_ok:
                self._send_error_json(400, "selecione o supervisor responsável (um supervisor ativo)")
                return
            cadastro, erro_cadastro = _validar_cadastro_paciente(body)
            if erro_cadastro:
                self._send_error_json(400, erro_cadastro)
                return
            email_acesso = str(cadastro.get("email", "")).strip().lower()
            try:
                if casos_col.find_one({"cadastro.cpf": cadastro["cpf"], "status": "Ativo"}):
                    self._send_error_json(409, "já existe um caso ativo cadastrado com este CPF")
                    return
                # O e-mail do cadastro vira o login da paciente: não pode já ser de uma conta
                # de outro tipo (equipe, administração, demonstração). Se já é de uma paciente,
                # a conta existente passa a apontar para o caso novo (retorno ao serviço).
                conta_existente = contas_col.find_one({"_id": email_acesso}) if email_acesso else None
                if email_acesso and (email_acesso in CONTAS or (conta_existente and conta_existente.get("role") != "paciente")):
                    self._send_error_json(409, "este e-mail já pertence a outra conta de acesso — informe outro e-mail para a paciente")
                    return
                cadastro = {"id": novo_id_de_paciente(), **cadastro}
                if body.get("ciencia_aviso") is True:
                    # Registro de que a equipe apresentou o aviso (e qual versão). Só em cadastros novos.
                    cadastro["privacidade"] = {"versao_aviso": AVISO_PRIVACIDADE_VERSAO, "confirmado_em": _agora_br(), "confirmado_por": (sessao_cadastro or {}).get("nome", ""), "tipo": "equipe confirmou que o titular foi informado"}
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/casos (cadastro)")
                return

            # Cadastro a partir de uma inscrição aprovada: só é aceito se a
            # triagem foi 'Aprovado para acompanhamento' e a inscrição ainda não
            # virou paciente. A inscrição é "reservada" antes de criar o caso,
            # para que dois cliques não gerem dois pacientes.
            # Módulo de inscrição/triagem descontinuado: o cadastro nunca mais
            # lê nem altera inscrições (os dados antigos continuam no banco).
            inscricao_id = ""
            if inscricao_id:
                try:
                    reserva = inscricoes_col.update_one(
                        {"_id": inscricao_id, "status": ST_INS_APROVADO, "caso_id": None},
                        {"$set": {"status": ST_INS_CADASTRADO}},
                    )
                except PyMongoError as exc:
                    self._erro_servidor(exc, "POST /api/casos (inscrição)")
                    return
                if reserva.matched_count == 0:
                    self._send_error_json(409, "esta inscrição não está aprovada para cadastro ou já foi usada em um cadastro")
                    return
                cadastro["inscricao_id"] = inscricao_id

            caso = {
                "_id": novo_id_de_caso(),
                "cadastro": cadastro,
                "paciente": nome_paciente,
                # O estudante é escolhido depois, em "Alocação de Pacientes".
                "estudante": "",
                "supervisor": supervisor_resp,
                "alocacao": ALOC_AGUARDANDO,
                "status": status_val,
                # A data de abertura é a do dia do cadastro, definida pelo
                # servidor — não é um campo que o profissional escolhe.
                "abertura": _hoje_br(),
                "anamnese": None,
                "evolucoes": [],
                "documentos": [],
                "agendamentos": [],
            }
            if email_acesso:
                # A paciente confere os próprios dados no primeiro acesso.
                caso["confirmacao"] = {"status": "pendente"}
            try:
                casos_col.insert_one(dict(caso))
            except PyMongoError as exc:
                if inscricao_id:
                    try:
                        inscricoes_col.update_one({"_id": inscricao_id}, {"$set": {"status": ST_INS_APROVADO}})
                    except PyMongoError:
                        pass
                self._erro_servidor(exc, "POST /api/casos")
                return
            if inscricao_id:
                try:
                    inscricoes_col.update_one(
                        {"_id": inscricao_id},
                        {"$set": {"caso_id": caso["_id"], "paciente_id": cadastro["id"]},
                         "$push": {"historico": _evento_inscricao(self._sessao_atual(), "Paciente cadastrado", cadastro["id"])}},
                    )
                except PyMongoError as exc:
                    print("ERRO: não foi possível vincular a inscrição %s ao caso: %s" % (inscricao_id, exc))
            sessao_login = self._sessao_atual()
            try:
                _avisar_supervisor_do_caso(caso, "novo_paciente", "Novo caso sob sua supervisão")
            except PyMongoError:
                pass
            _registrar_auditoria(sessao_login, "criação de caso", caso_id=caso["_id"])
            resposta = {"id": caso["_id"], "caso": caso_doc_to_json(caso)}
            if email_acesso:
                try:
                    resposta["acesso"] = _criar_acesso_da_paciente(email_acesso, nome_paciente, caso["_id"], cadastro["id"], sessao_login)
                except Exception as exc:
                    # O caso já foi criado; sem a conta, o técnico pode gerar o convite depois.
                    print("[acesso] não foi possível criar o acesso da paciente: %s" % type(exc).__name__)
                    resposta["acesso"] = {"status": "erro"}
            self._send_json(resposta, 201)
            return

        if path == "/api/solicitacoes":
            # Qualquer papel autenticado pode criar uma solicitação (é assim que
            # o paciente pede acesso ao próprio prontuário); só a leitura da
            # fila inteira e a liberação é que ficam restritas à equipe.
            sessao = self._exigir_papel({"paciente", "tecnico", "supervisor", "estudante"})
            if sessao is None:
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return

            doc = dict(body)
            doc.pop("_id", None)

            # Correção de segurança: antes, o nome do paciente vinha do que o
            # próprio navegador mandava no corpo da requisição — um paciente
            # autenticado podia, chamando a API diretamente, registrar uma
            # solicitação em nome de OUTRO paciente. Agora o nome é sempre o
            # da própria sessão autenticada (exatamente o valor que a tela já
            # usa hoje; nenhuma solicitação legítima muda de comportamento).
            doc["paciente"] = sessao["nome"]

            protocolo_val = str(doc.get("protocolo", "")).strip()
            if not doc["paciente"] or not protocolo_val:
                self._send_error_json(
                    400,
                    "os campos 'paciente' e 'protocolo' são obrigatórios para registrar uma solicitação",
                )
                return

            # Se o status vier vazio ou com um valor inesperado, assume "pendente"
            # em vez de gravar algo que depois nenhuma tela saberia interpretar
            # (essa inconsistência era a causa de solicitações "somem" da lista
            # de pendentes sem nunca aparecer como liberadas).
            if doc.get("status") not in STATUS_SOLICITACAO_VALIDOS:
                doc["status"] = "pendente"
            doc["protocolo"] = protocolo_val

            try:
                result = solicitacoes_col.insert_one(doc)
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/solicitacoes")
                return
            doc["_id"] = str(result.inserted_id)
            if sessao["role"] == "paciente":
                try:
                    _avisar_paciente(_encontrar_caso_do_paciente(sessao["nome"], sessao.get("caso_id")), "solicitacao_recebida",
                                     "protocolo " + protocolo_val, protocolo_val)
                except PyMongoError as exc:
                    print("[aviso ao paciente] caso não encontrado: %s" % exc, flush=True)
            self._send_json(doc, 201)
            return

        if path == "/api/reagendamentos":
            # Mesma regra da solicitação de prontuário: qualquer papel
            # autenticado pode criar um pedido (é o paciente pedindo para
            # reagendar a própria consulta); só a leitura da fila inteira e a
            # confirmação ficam restritas à equipe.
            sessao = self._exigir_papel({"paciente", "tecnico", "supervisor", "estudante"})
            if sessao is None:
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return

            doc = dict(body)
            doc.pop("_id", None)

            # Correção de segurança: "paciente" e "email" agora vêm sempre da
            # própria sessão autenticada, não do que o navegador mandou no
            # corpo da requisição — mesmo motivo do /api/solicitacoes acima:
            # evita que alguém peça reagendamento (e o e-mail de confirmação
            # que isso dispara) em nome de outra pessoa. O valor é idêntico ao
            # que a tela já envia hoje, então nenhum uso legítimo muda.
            doc["paciente"] = sessao["nome"]
            doc["email"] = sessao["email"]
            if not doc["paciente"] or not doc["email"]:
                self._send_error_json(
                    400,
                    "os campos 'paciente' e 'email' são obrigatórios para pedir um reagendamento",
                )
                return
            if not EMAIL_REGEX.match(doc["email"]):
                self._send_error_json(400, "e-mail inválido: '%s'" % doc["email"])
                return

            doc["status"] = "pendente"
            doc["nova_data"] = ""
            try:
                caso_ped = _encontrar_caso_do_paciente(sessao["nome"], sessao.get("caso_id")) if sessao["role"] == "paciente" else None
            except PyMongoError:
                caso_ped = None
            doc["caso_id"] = (caso_ped or {}).get("_id", "")

            try:
                result = reagendamentos_col.insert_one(doc)
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/reagendamentos")
                return
            doc["_id"] = str(result.inserted_id)
            self._send_json(doc, 201)
            return

        self._send_error_json(404, "rota não encontrada: " + path)

    # ---------- PUT ----------
    def do_PUT(self):
        path = self.path.split("?", 1)[0]

        if path == "/api/meu-perfil":
            # O estudante confere os próprios dados e informa SUA disponibilidade (dias e turnos).
            # Não altera nome, RA, supervisor, casos nem agendamentos — só estes dois campos.
            sessao = self._exigir_papel({"estudante"})
            if sessao is None:
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            if not isinstance(body, dict):
                self._send_error_json(400, "corpo da requisição inválido")
                return
            disp, erro = _validar_disponibilidade(body.get("disponibilidade"))
            if erro:
                self._send_error_json(400, erro)
                return
            # Cadastro: o estudante pode corrigir o PRÓPRIO nome e telefone. RA e e-mail (chave de
            # login) continuam só com o técnico. Nome/telefone não enviados não são alterados.
            novos, erro = _validar_estudante({k: v for k, v in body.items() if k in ("nome", "telefone")}, completo=False)
            if erro:
                self._send_error_json(400, erro)
                return
            try:
                with TRAVA_OPERACOES:
                    est = _estudante_da_sessao(sessao)
                    if est is None:
                        self._send_error_json(404, "cadastro do estudante não encontrado")
                        return
                    mudou_campos = []
                    nome_antigo = est["nome"]
                    if "nome" in novos and novos["nome"] != est["nome"]:
                        if (sessao.get("email") or "") in CONTAS:
                            self._send_error_json(409, "conta de demonstração: o nome só pode ser alterado pelo psicólogo técnico")
                            return
                        mudou_campos.append("nome")
                    if "telefone" in novos and novos["telefone"] != est.get("telefone", ""):
                        mudou_campos.append("telefone")
                    nome_final = novos.get("nome", est["nome"]) if "nome" in mudou_campos else est["nome"]
                    campos = {"nome": nome_final, "disponibilidade": disp, "atualizado_em_br": _agora_br(),
                              "atualizado_por": nome_final}
                    if body.get("dados_conferidos") is True:
                        campos["dados_conferidos_em_br"] = _agora_br()
                    if mudou_campos:
                        grava = {"nome": nome_final}
                        if "telefone" in novos:
                            grava["telefone"] = novos["telefone"]
                        _gravar_estudante(est["ra"], grava)
                    if "nome" in mudou_campos:
                        # O nome liga o estudante aos casos, ao vínculo, à conta e aos avisos: acompanha a correção.
                        # Evoluções já assinadas continuam com o nome da época (imutáveis).
                        contas_col.update_one({"_id": sessao["email"]}, {"$set": {"nome": nome_final}})
                        casos_col.update_many({"estudante": nome_antigo}, {"$set": {"estudante": nome_final}})
                        vinculos_col.update_one({"_id": est["ra"]}, {"$set": {"estudante": nome_final}})
                        for n_ in list(notificacoes_col.find({"destinatario": nome_antigo})):
                            if not n_.get("para"):
                                notificacoes_col.update_one({"_id": n_["_id"]}, {"$set": {"destinatario": nome_final}})
                        for s_ in SESSOES.values():
                            if s_.get("email") == sessao["email"]:
                                s_["nome"] = nome_final
                    if disp_estudantes_col.update_one({"_id": est["ra"]}, {"$set": campos}).matched_count == 0:
                        disp_estudantes_col.insert_one({"_id": est["ra"], **campos})
                    est = _estudante_por_ra(est["ra"]) or est
                if mudou_campos:
                    _avisar_tecnico("estudante_alterou_cadastro", "%s (RA %s) alterou: %s" % (nome_final, est["ra"], " e ".join(mudou_campos)))
                _registrar_auditoria(sessao, "perfil do estudante atualizado (disponibilidade%s%s)" % (
                    ", dados conferidos" if "dados_conferidos_em_br" in campos else "",
                    ", cadastro: " + ", ".join(mudou_campos) if mudou_campos else ""))
                perfil = _perfil_do_estudante(est)
                perfil["campos_alterados"] = mudou_campos
                self._send_json(perfil)
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/meu-perfil")
            return

        m = re.match(r"^/api/estudantes/([^/]+)/disponibilidade$", path)
        if m:
            # O técnico informa os dias e turnos em que o estudante pode atender (usado só para
            # sugerir horários compatíveis na alocação; ninguém é alocado automaticamente).
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            ra = unquote(m.group(1))
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            estudante = next((e for e in _lista_estudantes() if e["ra"] == ra), None)
            if estudante is None:
                self._send_error_json(404, "estudante não encontrado")
                return
            disp, erro = _validar_disponibilidade(body.get("disponibilidade"))
            if erro:
                self._send_error_json(400, erro)
                return
            doc = {"_id": ra, "nome": estudante["nome"], "disponibilidade": disp,
                   "atualizado_em_br": _agora_br(), "atualizado_por": sessao.get("nome", "")}
            try:
                if disp_estudantes_col.update_one({"_id": ra}, {"$set": {k: v for k, v in doc.items() if k != "_id"}}).matched_count == 0:
                    disp_estudantes_col.insert_one(doc)
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/estudantes/<ra>/disponibilidade")
                return
            _registrar_auditoria(sessao, "disponibilidade do estudante atualizada (RA %s)" % ra)
            self._send_json({"ok": True, "disponibilidade": disp, "disponibilidade_atualizada_em": doc["atualizado_em_br"]})
            return

        m = re.match(r"^/api/estudantes/([^/]+)$", path)
        if m:
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            ra = unquote(m.group(1))
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            campos, erro = _validar_estudante({k: v for k, v in body.items() if k == "telefone"}, completo=False)
            if erro:
                self._send_error_json(400, erro); return
            quer_ativo = body.get("ativo")
            if quer_ativo is not None and not isinstance(quer_ativo, bool):
                self._send_error_json(400, "o campo 'ativo' precisa ser verdadeiro ou falso"); return
            token, aviso, mudou = None, "", False
            with TRAVA_OPERACOES:
                try:
                    est = _estudante_por_ra(ra)
                    if est is None:
                        self._send_error_json(404, "estudante não encontrado"); return
                    conta = contas_col.find_one({"_id": est["email"]}) if est["email"] else None
                    if "telefone" in campos and campos["telefone"] != est["telefone"]:
                        _gravar_estudante(ra, {"nome": est["nome"], "telefone": campos["telefone"]}); mudou = True
                    if quer_ativo is not None and quer_ativo != est["ativo"]:
                        _gravar_estudante(ra, {"nome": est["nome"], "ativo": quer_ativo}); mudou = True
                        if not quer_ativo:
                            if conta:
                                contas_col.update_one({"_id": conta["_id"]}, {"$set": {"status": "desativada", "convite": None}})
                            if est["email"]:
                                _encerrar_sessoes(est["email"])
                            n = sum(1 for c in casos_col.find({}) if c.get("status") == "Ativo" and c.get("estudante") == est["nome"])
                            if n:
                                aviso = "O estudante tem %d paciente(s) ativo(s). Avalie a redistribuição em Alocação de Pacientes: nada foi realocado automaticamente." % n
                        elif conta:
                            if conta.get("senha_hash"):
                                contas_col.update_one({"_id": conta["_id"]}, {"$set": {"status": "ativa", "convite": None}})
                            else:
                                token, convite = _novo_convite()
                                contas_col.update_one({"_id": conta["_id"]}, {"$set": {"status": "convite_pendente", "convite": convite}})
                    resumo = _resumo_estudante(ra)
                except PyMongoError as exc:
                    self._erro_servidor(exc, "PUT /api/estudantes/<ra>")
                    return
            convite_resp = _resposta_convite(_enviar_convite(est["email"], est["nome"], "estudante", token), token) if token else None
            if mudou:
                _registrar_auditoria(sessao, "cadastro de estudante alterado", detalhe="%s (RA %s)%s" % (est["nome"], ra, "" if quer_ativo is None else (", reativado" if quer_ativo else ", desativado")))
            self._send_json({"estudante": resumo, "aviso": aviso, "convite": convite_resp})
            return

        m = re.match(r"^/api/notificacoes/([^/]+)/lida$", path)
        if m:
            sessao = self._exigir_papel({"estudante", "tecnico", "supervisor", "paciente"})
            if sessao is None:
                return
            nid = unquote(m.group(1))
            try:
                d = notificacoes_col.find_one({"_id": nid})
                if d is None:
                    dono = False
                elif sessao["role"] == "paciente":
                    meu = _encontrar_caso_do_paciente(sessao["nome"], sessao.get("caso_id"))
                    dono = bool(meu) and d.get("para") == "paciente" and d.get("caso_id") == meu["_id"]
                elif sessao["role"] == "tecnico":
                    dono = d.get("para") == "tecnico"
                elif sessao["role"] == "supervisor":
                    dono = d.get("para") == "supervisor" and d.get("destinatario") == sessao["nome"]
                else:
                    dono = not d.get("para") and d.get("destinatario") == sessao["nome"]
                if not dono:
                    self._send_error_json(404, "notificação não encontrada"); return
                if not d.get("lida"):
                    notificacoes_col.update_one({"_id": nid}, {"$set": {"lida": True, "lida_em_br": _agora_br()}})
                    if d.get("nota_id"):
                        notas_col.update_one({"_id": d["nota_id"]}, {"$set": {"lida_em_br": _agora_br()}})
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/notificacoes/<id>/lida")
                return
            self._send_json({"ok": True})
            return

        m = re.match(r"^/api/vinculos/([^/]+)$", path)
        if m:
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            ra = unquote(m.group(1))
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            sup = str(body.get("supervisor", "")).strip()
            with TRAVA_OPERACOES:
                try:
                    est = _estudante_por_ra(ra)
                    if est is None:
                        self._send_error_json(404, "estudante não encontrado"); return
                    if sup and sup not in {s["nome"] for s in _lista_supervisores_ativos()}:
                        self._send_error_json(400, "supervisor inexistente ou inativo"); return
                    doc = vinculos_col.find_one({"_id": ra})
                    atual = doc.get("supervisor", "") if doc and doc.get("ativo") else ""
                    if sup == atual:
                        self._send_error_json(409, "nenhuma alteração no vínculo"); return
                    hist = list((doc or {}).get("historico") or [])
                    agora = _agora_br()
                    if atual:
                        hist.append({"supervisor": atual, "de": doc.get("desde", ""), "ate": agora, "por": sessao["nome"]})
                    novo = {"ra": ra, "estudante": est["nome"], "supervisor": sup, "ativo": bool(sup),
                            "desde": agora if sup else "", "historico": hist}
                    if vinculos_col.update_one({"_id": ra}, {"$set": novo}).matched_count == 0:
                        vinculos_col.insert_one({"_id": ra, **novo})
                except PyMongoError as exc:
                    self._erro_servidor(exc, "PUT /api/vinculos/<ra>")
                    return
            if sup:
                try:
                    _avisar_supervisor(sup, "novo_estudante", est["nome"])
                except PyMongoError:
                    pass
            _registrar_auditoria(sessao, "vínculo de supervisão alterado", detalhe="%s: %s -> %s" % (est["nome"], atual or "(sem vínculo)", sup or "(encerrado)"))
            self._send_json({"ok": True, "vinculo": novo})
            return

        m = re.match(r"^/api/supervisor/casos/([^/]+)/distribuicao$", path)
        if m:
            # Preparado, mas DESLIGADO por padrão: depende de aprovação institucional.
            sessao = self._exigir_papel({"supervisor"})
            if sessao is None:
                return
            case_id = unquote(m.group(1))
            if not distribuicao_supervisor_ativa():
                _registrar_auditoria(sessao, "tentativa de distribuição de paciente (recurso desativado)", caso_id=case_id, resultado="negado")
                self._send_error_json(403, "a distribuição de pacientes pelo supervisor ainda não foi habilitada pela instituição")
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            ra = str(body.get("ra", "")).strip()
            motivo = str(body.get("motivo", "")).strip()[:300]
            with TRAVA_OPERACOES:
                try:
                    caso = casos_col.find_one({"_id": case_id})
                    if caso is None:
                        self._send_error_json(404, "caso não encontrado"); return
                    if (caso.get("supervisor") or "").strip() != sessao["nome"]:
                        _registrar_auditoria(sessao, "tentativa de distribuir paciente de outro supervisor", caso_id=case_id, resultado="negado")
                        self._send_error_json(403, "só é possível distribuir pacientes sob a sua responsabilidade"); return
                    if caso.get("status") != "Ativo":
                        self._send_error_json(409, "o caso está encerrado"); return
                    est = _estudante_por_ra(ra)
                    if est is None:
                        self._send_error_json(404, "estudante não encontrado"); return
                    v = vinculos_col.find_one({"_id": ra})
                    if not est.get("ativo", True) or not v or not v.get("ativo") or v.get("supervisor") != sessao["nome"]:
                        _registrar_auditoria(sessao, "tentativa de distribuir a estudante fora da equipe", caso_id=case_id, resultado="negado")
                        self._send_error_json(403, "o estudante precisa estar ativo e vinculado à sua supervisão"); return
                    anterior = (caso.get("estudante") or "").strip()
                    if anterior == est["nome"]:
                        self._send_error_json(409, "este estudante já é o responsável pelo caso"); return
                    if anterior and not motivo:
                        self._send_error_json(409, "informe o motivo da redistribuição"); return
                    hist = list(caso.get("historico_vinculos") or [])
                    hist.append({"tipo": "redistribuição pelo supervisor" if anterior else "distribuição pelo supervisor",
                                 "estudante_de": anterior, "estudante_para": est["nome"], "supervisor": sessao["nome"],
                                 "quando": _agora_br(), "por": sessao["nome"], "motivo": motivo})
                    # Não cria nem mexe em agendamentos; não altera vínculos administrativos.
                    casos_col.update_one({"_id": case_id}, {"$set": {"estudante": est["nome"], "alocacao": ALOC_ALOCADO, "historico_vinculos": hist}})
                    novo = casos_col.find_one({"_id": case_id})
                    _avisar_estudante(novo, "novo_paciente", "")
                except PyMongoError as exc:
                    self._erro_servidor(exc, "PUT /api/supervisor/casos/<id>/distribuicao")
                    return
            _registrar_auditoria(sessao, "paciente distribuído pelo supervisor", caso_id=case_id,
                                 detalhe="%s -> %s" % (anterior or "(ninguém)", est["nome"]))
            self._send_json({"ok": True, "caso": caso_doc_to_json(novo), "agendamentos_futuros": _futuros_ativos(novo) if anterior else 0})
            return

        m = re.match(r"^/api/casos/([^/]+)/alocacao$", path)
        if m:
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            case_id = unquote(m.group(1))
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            ra = str(body.get("ra", "")).strip()
            motivo = str(body.get("motivo", "")).strip()[:300]
            with TRAVA_OPERACOES:
                try:
                    caso = casos_col.find_one({"_id": case_id})
                    if caso is None:
                        self._send_error_json(404, "caso não encontrado"); return
                    if caso.get("status") != "Ativo":
                        self._send_error_json(409, "o caso está encerrado"); return
                    sup = (caso.get("supervisor") or "").strip()
                    if not sup:
                        self._send_error_json(409, "o caso não tem supervisor responsável: defina o supervisor antes de alocar"); return
                    est = _estudante_por_ra(ra)
                    if est is None:
                        self._send_error_json(404, "estudante não encontrado"); return
                    if not est.get("ativo", True):
                        self._send_error_json(409, "o estudante está inativo e não pode receber pacientes"); return
                    v = vinculos_col.find_one({"_id": ra})
                    if not v or not v.get("ativo"):
                        self._send_error_json(409, "o estudante não tem vínculo ativo com supervisor"); return
                    if v.get("supervisor") != sup:
                        self._send_error_json(409, "o estudante é vinculado a outro supervisor; altere formalmente o supervisor do caso antes de alocar"); return
                    anterior = (caso.get("estudante") or "").strip()
                    if anterior == est["nome"]:
                        self._send_error_json(409, "este estudante já é o responsável pelo caso"); return
                    if anterior and (not body.get("realocar") or not motivo):
                        self._send_error_json(409, "o caso já tem estudante: a realocação exige confirmação explícita e um motivo"); return
                    hist = list(caso.get("historico_vinculos") or [])
                    hist.append({"tipo": "realocação" if anterior else "alocação", "estudante_de": anterior,
                                 "estudante_para": est["nome"], "supervisor": sup, "quando": _agora_br(),
                                 "por": sessao["nome"], "motivo": motivo})
                    casos_col.update_one({"_id": case_id}, {"$set": {"estudante": est["nome"], "alocacao": ALOC_ALOCADO, "historico_vinculos": hist}})
                    novo = casos_col.find_one({"_id": case_id})
                    # Aviso ao estudante que passa a ser responsável (sem nome de paciente nem dados clínicos).
                    _agora_ts = time.time()
                    notificacoes_col.insert_one({"_id": "nf-" + secrets.token_hex(6), "tipo": "novo_paciente", "destinatario": est["nome"],
                                                 "caso_id": case_id, "evolucao_idx": None, "criada_em": _agora_ts,
                                                 "criada_em_br": _agora_br(), "lida": False})
                    _avisar_supervisor(sup, "paciente_alocado", est["nome"], case_id)
                except PyMongoError as exc:
                    self._erro_servidor(exc, "PUT /api/casos/<id>/alocacao")
                    return
            _registrar_auditoria(sessao, "paciente alocado a estudante" if not anterior else "paciente realocado",
                                 caso_id=case_id, detalhe="%s -> %s (supervisor %s)" % (anterior or "(ninguém)", est["nome"], sup))
            self._send_json({"ok": True, "caso": caso_doc_to_json(novo), "agendamentos_futuros": _futuros_ativos(novo) if anterior else 0})
            return

        m = re.match(r"^/api/casos/([^/]+)/supervisor$", path)
        if m:
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            case_id = unquote(m.group(1))
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            novo_sup = str(body.get("supervisor", "")).strip()
            motivo = str(body.get("motivo", "")).strip()[:300]
            with TRAVA_OPERACOES:
                try:
                    caso = casos_col.find_one({"_id": case_id})
                    if caso is None:
                        self._send_error_json(404, "caso não encontrado"); return
                    if caso.get("status") != "Ativo":
                        self._send_error_json(409, "o caso está encerrado"); return
                    if novo_sup not in {s["nome"] for s in _lista_supervisores_ativos()}:
                        self._send_error_json(400, "selecione um supervisor ativo"); return
                    atual = (caso.get("supervisor") or "").strip()
                    if novo_sup == atual:
                        self._send_error_json(409, "este já é o supervisor responsável"); return
                    est_atual = (caso.get("estudante") or "").strip()
                    mudanca = {"supervisor": novo_sup}
                    liberou = False
                    if est_atual:
                        if not body.get("confirmar_transferencia") or not motivo:
                            self._send_error_json(409, "o caso já tem estudante: a troca de supervisor é uma transferência e exige confirmação explícita e um motivo"); return
                        # O estudante só continua se for vinculado ao novo supervisor; senão o caso
                        # volta para "Aguardando alocação" (nunca fica estudante de um supervisor e caso de outro).
                        vinc = next((e for e in _painel_vinculos()["estudantes"] if e["nome"] == est_atual), None)
                        if not vinc or vinc["supervisor"] != novo_sup:
                            mudanca.update(estudante="", alocacao=ALOC_AGUARDANDO)
                            liberou = True
                    elif not caso.get("alocacao"):
                        mudanca["alocacao"] = ALOC_AGUARDANDO
                    hist = list(caso.get("historico_vinculos") or [])
                    hist.append({"tipo": "troca de supervisor", "supervisor_de": atual, "supervisor_para": novo_sup,
                                 "estudante_de": est_atual, "estudante_para": "" if liberou else est_atual,
                                 "quando": _agora_br(), "por": sessao["nome"], "motivo": motivo})
                    mudanca["historico_vinculos"] = hist
                    casos_col.update_one({"_id": case_id}, {"$set": mudanca})
                    novo = casos_col.find_one({"_id": case_id})
                    _avisar_supervisor(novo_sup, "novo_paciente", "Caso transferido para a sua supervisão", case_id)
                except PyMongoError as exc:
                    self._erro_servidor(exc, "PUT /api/casos/<id>/supervisor")
                    return
            _registrar_auditoria(sessao, "supervisor do caso alterado", caso_id=case_id,
                                 detalhe="%s -> %s%s" % (atual or "(nenhum)", novo_sup, "; estudante liberado" if liberou else ""))
            self._send_json({"ok": True, "caso": caso_doc_to_json(novo), "estudante_liberado": liberou,
                             "agendamentos_futuros": _futuros_ativos(novo) if liberou else 0})
            return

        m = re.match(r"^/api/casos/([^/]+)/agendamentos/(\d+)/comparecimento$", path)
        if m:
            self._tratar_comparecimento(unquote(m.group(1)), int(m.group(2)), True)
            return

        m = re.match(r"^/api/casos/([^/]+)/agendamentos/(\d+)$", path)
        if m:
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            case_id, idx = unquote(m.group(1)), int(m.group(2))
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            acao = body.get("acao")
            if acao not in ("editar", "reagendar", "cancelar"):
                self._send_error_json(400, "ação inválida (editar, reagendar ou cancelar)"); return
            with TRAVA_OPERACOES:
                try:
                    caso = casos_col.find_one({"_id": case_id})
                    ags = list((caso or {}).get("agendamentos") or [])
                    if caso is None or idx >= len(ags):
                        self._send_error_json(404, "agendamento não encontrado"); return
                    ag = dict(ags[idx])
                    if ag.get("status") != "Confirmada":
                        self._send_error_json(409, "só atendimentos com status Confirmada podem ser alterados"); return
                    if ag.get("comparecimento"):
                        self._send_error_json(409, "este atendimento já tem comparecimento registrado e não pode mais ser alterado"); return
                    if acao == "cancelar":
                        ag.update(status=ST_AG_CANCELADA, cancelado_em=_agora_br(), cancelado_por=sessao["nome"],
                                  motivo_cancelamento=str(body.get("motivo", "")).strip()[:300])
                    else:
                        if acao == "editar":
                            local = str(body.get("local", "")).strip()
                            if not local or len(local) > 200:
                                self._send_error_json(400, "informe o local do atendimento (até 200 caracteres)"); return
                            ag["local"] = local
                        else:
                            data, hora = _data_para_br(body.get("data")), _hora_para_br(body.get("hora"))
                            if not data or not hora:
                                self._send_error_json(400, "data ou horário inválido"); return
                            if _parse_data_br(data) < _parse_data_br(_hoje_br()):
                                self._send_error_json(400, "não é possível reagendar para uma data que já passou"); return
                            if (data, hora) == (ag.get("data"), _norm_hora(ag.get("hora"))):
                                self._send_error_json(409, "informe uma data ou horário diferente do atual"); return
                            conflito = _conflito_agenda(data, hora, case_id, caso.get("estudante"), ignorar=(case_id, idx))
                            if conflito:
                                self._send_error_json(409, conflito); return
                            ag.setdefault("reagendamentos", []).append({"de": "%s %s" % (ag.get("data"), ag.get("hora")), "quando": _agora_br(), "por": sessao["nome"]})
                            ag["data"], ag["hora"] = data, hora
                    ags[idx] = ag
                    casos_col.update_one({"_id": case_id}, {"$set": {"agendamentos": ags}})
                    novo = casos_col.find_one({"_id": case_id})
                    _avisar_estudante(caso, {"editar": "agendamento_alterado", "reagendar": "agendamento_alterado", "cancelar": "agendamento_cancelado"}[acao],
                                      "%s às %s" % (ag.get("data"), ag.get("hora")))
                    _avisar_supervisor_do_caso(caso, {"editar": "agendamento_alterado", "reagendar": "agendamento_alterado", "cancelar": "agendamento_cancelado"}[acao],
                                               "%s às %s · %s" % (ag.get("data"), ag.get("hora"), caso.get("estudante", "")))
                    _avisar_paciente(caso, "agendamento_cancelado" if acao == "cancelar" else "agendamento_alterado",
                                     "%s às %s · %s" % (ag.get("data"), ag.get("hora"), ag.get("local", "")),
                                     "%s %s %s %s" % (acao, ag.get("data"), ag.get("hora"), ag.get("local", "")))
                except PyMongoError as exc:
                    self._erro_servidor(exc, "PUT /api/casos/<id>/agendamentos/<n>")
                    return
            _registrar_auditoria(sessao, {"editar": "agendamento editado", "reagendar": "agendamento reagendado", "cancelar": "agendamento cancelado"}[acao],
                                 caso_id=case_id, detalhe="%s %s" % (ag.get("data"), ag.get("hora")))
            self._send_json({"ok": True, "caso": caso_doc_to_json(novo)})
            return

        m = re.match(r"^/api/casos/([^/]+)/cadastro-visto$", path)
        if m:
            # O técnico viu a atualização cadastral feita pela paciente: o aviso some.
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            case_id = unquote(m.group(1))
            try:
                caso = casos_col.find_one({"_id": case_id})
                if not caso or not (caso.get("confirmacao") or {}).get("atualizacao_nao_vista"):
                    self._send_json({"ok": True})
                    return
                conf = dict(caso["confirmacao"]); conf["atualizacao_nao_vista"] = False
                casos_col.update_one({"_id": case_id}, {"$set": {"confirmacao": conf}})
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/casos/<id>/cadastro-visto")
                return
            self._send_json({"ok": True})
            return

        m = re.match(r"^/api/casos/([^/]+)/convite$", path)
        if m:
            # Reenvio do convite de primeiro acesso da paciente (só técnico). O convite anterior
            # deixa de valer; só é possível enquanto a paciente ainda não criou a senha.
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            case_id = unquote(m.group(1))
            try:
                doc = contas_col.find_one({"role": "paciente", "caso_id": case_id})
                if not doc:
                    self._send_error_json(404, "esta paciente não tem acesso cadastrado")
                    return
                if doc.get("status") != "convite_pendente":
                    self._send_error_json(409, "a paciente já criou a senha; não há convite pendente")
                    return
                token, convite = _novo_convite()
                contas_col.update_one({"_id": doc["_id"]}, {"$set": {"convite": convite}})
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/casos/<id>/convite")
                return
            enviado = _enviar_convite(doc["_id"], doc.get("nome"), "paciente", token)
            _registrar_auditoria(sessao, "reenvio de convite da paciente", caso_id=case_id)
            self._send_json({"convite": _resposta_convite(enviado, token, "paciente")})
            return

        m = re.match(r"^/api/casos/(.+)$", path)
        if m:
            sessao = self._exigir_papel(PAPEIS_CASOS)
            if sessao is None:
                return
            case_id = unquote(m.group(1))

            # Correção de segurança (IDOR/BOLA): antes, qualquer papel em
            # PAPEIS_CASOS podia alterar QUALQUER caso só trocando o id na
            # URL. Agora buscamos o caso primeiro e checamos se esta sessão
            # específica tem permissão para ele (_pode_acessar_caso), não só
            # se o papel em geral tem permissão para a rota.
            try:
                caso_atual = casos_col.find_one({"_id": case_id})
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/casos/" + case_id + " (busca)")
                return
            if caso_atual is None:
                self._send_error_json(404, "caso não encontrado: " + case_id)
                return
            if not _pode_acessar_caso(sessao, caso_atual):
                _registrar_auditoria(
                    sessao, "tentativa de alterar caso sem vínculo", caso_id=case_id, resultado="negado"
                )
                self._send_error_json(403, "seu perfil não tem permissão para alterar este caso")
                return

            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            body = dict(body)
            body.pop("_id", None)
            if "status" in body and body["status"] not in STATUS_CASO_VALIDOS:
                self._send_error_json(
                    400,
                    "status inválido: '%s' (valores aceitos: %s)" % (body["status"], ", ".join(sorted(STATUS_CASO_VALIDOS))),
                )
                return

            # Correção de segurança: "estudante" e "supervisor" definem A QUEM
            # pertence o caso — não são campos que a própria tela deixa editar,
            # então o servidor não aceita mudá-los por aqui (evita que o caso
            # seja "transferido" para outra pessoa por uma chamada direta à
            # API). Preservamos sempre o valor que já estava gravado.
            body["estudante"] = caso_atual.get("estudante", "")
            body["supervisor"] = caso_atual.get("supervisor", "")
            # Os dados cadastrais (ID do paciente, nascimento, CPF, e-mail,
            # responsável) são gravados só no cadastro: esta rota nunca os
            # altera, mande a tela o que mandar.
            if "cadastro" in caso_atual:
                body["cadastro"] = caso_atual["cadastro"]
            else:
                body.pop("cadastro", None)
            # A conferência cadastral e o nome do paciente só mudam pela própria paciente
            # (/api/meu-cadastro): uma tela desatualizada não pode desfazer uma correção.
            if "confirmacao" in caso_atual:
                body["confirmacao"] = caso_atual["confirmacao"]
            else:
                body.pop("confirmacao", None)
            body["paciente"] = caso_atual.get("paciente", body.get("paciente", ""))

            # Matriz de permissões ("Criar/editar agendamentos": técnico, único perfil;
            # supervisor e estudante só veem). Qualquer mudança na agenda do caso
            # vinda de outro papel é recusada e fica na auditoria.
            if sessao["role"] != "tecnico" and (body.get("agendamentos") or []) != (caso_atual.get("agendamentos") or []):
                _registrar_auditoria(
                    sessao, "tentativa de alterar agendamentos sem permissão", caso_id=case_id, resultado="negado"
                )
                self._send_error_json(403, "apenas o psicólogo técnico cria ou altera agendamentos")
                return

            # Alocação, histórico de vínculos e agenda só mudam pelas rotas próprias
            # (com trava, validação e auditoria): uma tela desatualizada não os desfaz.
            for campo in ("alocacao", "historico_vinculos"):
                if campo in caso_atual:
                    body[campo] = caso_atual[campo]
                else:
                    body.pop(campo, None)
            body["agendamentos"] = caso_atual.get("agendamentos") or []

            # Só técnico e supervisor podem encerrar/reabrir um caso — a
            # própria tela já impede isso para o estudante (canCloseCase()),
            # mas essa regra não era garantida pelo servidor.
            if sessao["role"] == "estudante" and body.get("status") != caso_atual.get("status"):
                _registrar_auditoria(
                    sessao, "tentativa de encerrar/reabrir caso sem permissão", caso_id=case_id, resultado="negado"
                )
                self._send_error_json(403, "apenas técnico ou supervisor podem encerrar ou reabrir um caso")
                return

            # Correção de bug (achado pela usuária): a tela do paciente não
            # lia o status real do caso — ela decidia "Ativo"/"Encerrado"
            # fixo pelo e-mail de login, resquício de quando o painel do
            # paciente ainda usava dado de exemplo. Para a tela do paciente
            # (GET /api/meu-caso, abaixo) poder mostrar a data real do
            # encerramento, gravamos aqui QUANDO o status muda de verdade —
            # este campo é controlado só pelo servidor, nunca pelo que a
            # tela mandar (mesmo padrão já usado para "estudante"/"supervisor").
            if body.get("status") != caso_atual.get("status"):
                body["status_atualizado_em"] = _hoje_br()
            else:
                body["status_atualizado_em"] = caso_atual.get("status_atualizado_em", "")

            # Correção de segurança: antes, quem tinha permissão sobre o caso
            # podia, mandando o PUT diretamente (sem passar pela tela),
            # sobrescrever uma evolução já registrada ou substituir a
            # anamnese já preenchida — a regra de que esses registros são
            # imutáveis só existia no front-end. Agora o servidor também a
            # garante (_validar_imutabilidade_clinica), nunca aceita um corpo
            # que viole essa regra, e registra a tentativa na auditoria.
            # Documentos só se acrescentam: se a tela que enviou este PUT ainda não conhecia um documento
            # anexado por outra pessoa (estudante, técnico) depois do login, ele não pode ser perdido.
            # Agora os documentos têm rota própria (envio com arquivo real, auditoria e permissões): o PUT do caso
            # nunca os altera — sempre mantém exatamente o que o servidor tem.
            body["documentos"] = list(caso_atual.get("documentos") or [])

            erro_imutabilidade = _validar_imutabilidade_clinica(caso_atual, body)
            if erro_imutabilidade:
                _registrar_auditoria(
                    sessao,
                    "tentativa de alterar registro clínico imutável",
                    caso_id=case_id,
                    resultado="negado",
                    detalhe=erro_imutabilidade,
                )
                self._send_error_json(403, erro_imutabilidade)
                return

            try:
                result = casos_col.replace_one({"_id": case_id}, {"_id": case_id, **body})
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/casos/" + case_id)
                return
            if result.matched_count == 0:
                self._send_error_json(404, "caso não encontrado: " + case_id)
                return
            _registrar_auditoria(sessao, "alteração de caso", caso_id=case_id)
            self._send_json(body)
            return

        if path == "/api/admin/minha-conta":
            sessao = self._exigir_papel(PAPEIS_ADMIN)
            if sessao is None:
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            nome = str(body.get("nome", "")).strip()
            if len(nome) < 3 or len(nome) > 120:
                self._send_error_json(400, "informe o nome completo (de 3 a 120 caracteres)")
                return
            try:
                # Só o nome é editável: perfil, e-mail e função não mudam por aqui.
                r = contas_col.update_one({"_id": sessao["email"], "role": "admin_ti"}, {"$set": {"nome": nome}})
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/admin/minha-conta")
                return
            if r.matched_count == 0:
                self._send_error_json(404, "conta não encontrada")
                return
            for sess in SESSOES.values():
                if sess.get("email") == sessao["email"]:
                    sess["nome"] = nome
            _registrar_historico_admin(sessao, "Dados da própria conta atualizados", sessao["email"])
            self._send_json({"ok": True, "nome": nome})
            return

        mp = re.match(r"^/api/admin/profissionais/(.+)$", path)
        if mp:
            sessao = self._exigir_papel(PAPEIS_ADMIN)
            if sessao is None:
                return
            email = unquote(mp.group(1)).strip().lower()
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            acao = str(body.get("acao", ""))
            try:
                doc = contas_col.find_one({"_id": email})
                # Só contas de técnico e supervisor: a administração não altera
                # a si mesma nem outros administradores por esta rota.
                if not doc or doc.get("role") not in FUNCOES_PROFISSIONAIS:
                    self._send_error_json(404, "conta profissional não encontrada")
                    return
                status = doc.get("status")
                token = None
                if acao == "atualizar":
                    dados, erro = _validar_dados_profissional(body)
                    if erro:
                        self._send_error_json(400, erro)
                        return
                    mudou = [rot for rot, k in (("nome", "nome"), ("CRP", "crp")) if dados[k] != doc.get(k, "")]
                    if not mudou:
                        self._send_error_json(400, "nenhuma alteração informada")
                        return
                    contas_col.update_one({"_id": email}, {"$set": dados})
                    for sess in SESSOES.values():
                        if sess.get("email") == email:
                            sess["nome"] = dados["nome"]
                    historico = ("Dados corrigidos", "campos: " + ", ".join(mudou))
                elif acao == "desativar":
                    if status == "desativada":
                        self._send_error_json(409, "a conta já está desativada")
                        return
                    # Mantém tudo o que a pessoa produziu; só impede novos acessos,
                    # derruba as sessões abertas e invalida convites pendentes.
                    contas_col.update_one({"_id": email}, {"$set": {"status": "desativada", "convite": None, "desativada_em_br": _agora_br()}})
                    _encerrar_sessoes(email)
                    historico = ("Conta desativada", "")
                elif acao == "reativar":
                    if status != "desativada":
                        self._send_error_json(409, "só uma conta desativada pode ser reativada")
                        return
                    if doc.get("senha_hash"):
                        contas_col.update_one({"_id": email}, {"$set": {"status": "ativa", "convite": None}})
                        historico = ("Conta reativada", "")
                    else:
                        token, convite = _novo_convite()
                        contas_col.update_one({"_id": email}, {"$set": {"status": "convite_pendente", "convite": convite}})
                        historico = ("Conta reativada (novo convite de primeiro acesso)", "")
                elif acao == "reenviar_convite":
                    if status != "convite_pendente":
                        self._send_error_json(409, "só é possível reenviar convite de uma conta com primeiro acesso pendente")
                        return
                    token, convite = _novo_convite()  # o convite anterior deixa de valer
                    contas_col.update_one({"_id": email}, {"$set": {"convite": convite}})
                    historico = ("Convite de primeiro acesso reenviado", "")
                else:
                    self._send_error_json(400, "ação inválida")
                    return
                atualizado = contas_col.find_one({"_id": email})
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/admin/profissionais")
                return
            convite_resp = _resposta_convite(_enviar_convite(email, atualizado.get("nome"), atualizado["role"], token), token) if token else None
            _registrar_historico_admin(sessao, historico[0], email, historico[1])
            self._send_json({"profissional": conta_db_to_json(atualizado), "convite": convite_resp})
            return

        mi = re.match(r"^/api/inscricoes/(INS-\d{4}-\d{4})$", path)
        if mi:
            self._modulo_descontinuado()
            return
        if False and mi:  # módulo de inscrição/triagem desativado (dados preservados no banco)
            # Ações do psicólogo técnico sobre uma inscrição. Cada ação é
            # explícita (analisar NÃO encaminha à triagem) e fica no histórico.
            sessao = self._exigir_papel({"tecnico"})
            if sessao is None:
                return
            ins_id = mi.group(1)
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            acao = str(body.get("acao", ""))
            try:
                ins = inscricoes_col.find_one({"_id": ins_id})
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/inscricoes (busca)")
                return
            if ins is None:
                self._send_error_json(404, "inscrição não encontrada")
                return
            status = ins.get("status")
            novo = {}
            filtro_status = [status]
            if acao == "analisar":
                if status != ST_INS_RECEBIDO:
                    self._send_error_json(409, "só uma inscrição com status 'Recebido' pode ser marcada como analisada")
                    return
                novo["status"] = ST_INS_ANALISADO
                evento = _evento_inscricao(sessao, "Marcada como analisada")
            elif acao == "encaminhar":
                if status not in (ST_INS_RECEBIDO, ST_INS_ANALISADO):
                    self._send_error_json(409, "esta inscrição já foi encaminhada ou concluída")
                    return
                novo["status"] = ST_INS_TRIAGEM
                evento = _evento_inscricao(sessao, "Encaminhada para triagem")
            elif acao == "agendar_triagem":
                if status != ST_INS_TRIAGEM:
                    self._send_error_json(409, "a triagem só pode ser agendada para inscrições 'Aguardando triagem'")
                    return
                data = str(body.get("data", "")).strip()
                hora = str(body.get("hora", "")).strip()
                local = str(body.get("local", "")).strip()
                if not _data_br_real(data):
                    self._send_error_json(400, "informe uma data de triagem válida no formato DD/MM/AAAA")
                    return
                if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", hora):
                    self._send_error_json(400, "informe o horário da triagem (HH:MM)")
                    return
                if not local:
                    self._send_error_json(400, "informe o local da triagem")
                    return
                triagem = dict(ins.get("triagem") or {})
                triagem["agendamento"] = {"data": data, "hora": hora, "local": local[:120]}
                novo["triagem"] = triagem
                evento = _evento_inscricao(sessao, "Triagem agendada", "%s às %s" % (data, hora))
            elif acao == "resultado":
                if status != ST_INS_TRIAGEM:
                    self._send_error_json(409, "o resultado só pode ser registrado para inscrições 'Aguardando triagem'")
                    return
                res = str(body.get("resultado", ""))
                if res not in ("aprovado", "nao_aprovado"):
                    self._send_error_json(400, "resultado inválido")
                    return
                triagem = dict(ins.get("triagem") or {})
                triagem["resultado"] = ST_INS_APROVADO if res == "aprovado" else ST_INS_NAO_APROVADO
                triagem["resultado_em"] = _agora_br()
                triagem["observacao"] = str(body.get("observacao", "")).strip()[:500]
                # Não aprovado: deixa preparado o acionamento da comunicação ao
                # candidato (o envio de e-mail depende do SMTP, ainda não configurado).
                triagem["comunicacao_pendente"] = res == "nao_aprovado"
                novo["triagem"] = triagem
                novo["status"] = triagem["resultado"]
                evento = _evento_inscricao(sessao, "Resultado da triagem: " + triagem["resultado"])
            else:
                self._send_error_json(400, "ação inválida")
                return
            try:
                r = inscricoes_col.update_one(
                    {"_id": ins_id, "status": {"$in": filtro_status}},
                    {"$set": novo, "$push": {"historico": evento}},
                )
                if r.matched_count == 0:
                    self._send_error_json(409, "esta inscrição foi alterada por outra pessoa; recarregue a lista")
                    return
                atualizada = inscricoes_col.find_one({"_id": ins_id})
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/inscricoes")
                return
            _registrar_auditoria(sessao, "inscrição: " + acao, detalhe=ins_id)
            self._send_json(inscricao_doc_to_json(atualizada))
            return

        m2 = re.match(r"^/api/solicitacoes/([0-9a-fA-F]{24})$", path)
        if m2:
            if self._exigir_papel(PAPEIS_SOLICITACOES_ESCRITA) is None:
                return
            try:
                obj_id = ObjectId(m2.group(1))
            except InvalidId:
                self._send_error_json(400, "id de solicitação inválido")
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return
            body = dict(body)
            body.pop("_id", None)
            if "status" in body and body["status"] not in STATUS_SOLICITACAO_VALIDOS:
                self._send_error_json(
                    400,
                    "status inválido: '%s' (valores aceitos: %s)" % (body["status"], ", ".join(sorted(STATUS_SOLICITACAO_VALIDOS))),
                )
                return
            try:
                antes = solicitacoes_col.find_one({"_id": obj_id})
                result = solicitacoes_col.replace_one({"_id": obj_id}, body)
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/solicitacoes/" + str(obj_id))
                return
            if result.matched_count == 0:
                self._send_error_json(404, "solicitação não encontrada: " + str(obj_id))
                return
            if antes and body.get("status") == "liberado" and antes.get("status") != "liberado":
                # O paciente é avisado só na primeira liberação, depois de gravada.
                try:
                    _avisar_paciente(_encontrar_caso_do_paciente(antes.get("paciente", "")), "prontuario_liberado",
                                     "protocolo " + str(antes.get("protocolo", "")), str(antes.get("protocolo", "")) or str(obj_id))
                except PyMongoError as exc:
                    print("[aviso ao paciente] caso não encontrado: %s" % exc, flush=True)
            body["_id"] = str(obj_id)
            self._send_json(body)
            return

        m3 = re.match(r"^/api/reagendamentos/([0-9a-fA-F]{24})$", path)
        if m3:
            sessao_rg = self._exigir_papel(PAPEIS_SOLICITACOES_ESCRITA)
            if sessao_rg is None:
                return
            try:
                obj_id = ObjectId(m3.group(1))
            except InvalidId:
                self._send_error_json(400, "id de reagendamento inválido")
                return
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return

            nova_data_val = str(body.get("nova_data", "")).strip()
            if not nova_data_val and not (body.get("data") and body.get("hora")):
                self._send_error_json(400, "o campo 'nova_data' é obrigatório para confirmar o reagendamento")
                return

            try:
                doc = reagendamentos_col.find_one({"_id": obj_id})
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/reagendamentos/" + str(obj_id) + " (busca)")
                return
            if not doc:
                self._send_error_json(404, "reagendamento não encontrado: " + str(obj_id))
                return
            ja_confirmado = doc.get("status") == "confirmado" and doc.get("nova_data") == nova_data_val

            # Se a tela mandou data e horário estruturados, a consulta REAL do caso é remarcada
            # junto (uma única operação): sem isso a agenda do estudante ficaria na data antiga.
            caso_rg = None
            agenda_alterada = False
            data_br, hora_br = _data_para_br(body.get("data")), _hora_para_br(body.get("hora"))
            if body.get("data") or body.get("hora"):
                if not data_br or not hora_br:
                    self._send_error_json(400, "data ou horário inválido"); return
                nova_data_val = "%s às %s" % (data_br, hora_br)
                with TRAVA_OPERACOES:
                    try:
                        caso_rg = _encontrar_caso_do_paciente(doc.get("paciente", ""), doc.get("caso_id") or None)
                        if not caso_rg:
                            self._send_error_json(404, "caso do paciente não encontrado"); return
                        ags = list(caso_rg.get("agendamentos") or [])
                        idx = body.get("indice")
                        idx = int(idx) if str(idx).isdigit() else _proxima_consulta_remarcavel(caso_rg)
                        if idx is None or idx >= len(ags):
                            self._send_error_json(409, "este paciente não tem consulta futura confirmada para reagendar — crie o agendamento no caso antes"); return
                        ag = dict(ags[idx])
                        if ag.get("status") != "Confirmada" or ag.get("comparecimento"):
                            self._send_error_json(409, "esta consulta não pode mais ser alterada"); return
                        if _parse_data_br(data_br) < _parse_data_br(_hoje_br()):
                            self._send_error_json(400, "não é possível reagendar para uma data que já passou"); return
                        if (data_br, hora_br) == (ag.get("data"), _norm_hora(ag.get("hora"))):
                            self._send_error_json(409, "informe uma data ou horário diferente do atual"); return
                        conflito = _conflito_agenda(data_br, hora_br, caso_rg["_id"], caso_rg.get("estudante"), ignorar=(caso_rg["_id"], idx))
                        if conflito:
                            self._send_error_json(409, conflito); return
                        ag.setdefault("reagendamentos", []).append({"de": "%s %s" % (ag.get("data"), ag.get("hora")), "quando": _agora_br(), "por": sessao_rg["nome"]})
                        ag["data"], ag["hora"] = data_br, hora_br
                        ags[idx] = ag
                        casos_col.update_one({"_id": caso_rg["_id"]}, {"$set": {"agendamentos": ags}})
                        agenda_alterada = True
                    except PyMongoError as exc:
                        self._erro_servidor(exc, "PUT /api/reagendamentos/" + str(obj_id) + " (agenda)")
                        return

            try:
                reagendamentos_col.update_one(
                    {"_id": obj_id},
                    {"$set": {"status": "confirmado", "nova_data": nova_data_val}},
                )
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/reagendamentos/" + str(obj_id))
                return

            # O e-mail só é disparado AQUI, depois que a nova data já está
            # salva no banco — assim, mesmo se o envio falhar (ou o SMTP não
            # estiver configurado), a confirmação em si não se perde.
            enviado = _enviar_confirmacao_reagendamento(doc.get("email", ""), doc.get("paciente", ""), nova_data_val)
            try:
                caso_rg = caso_rg or _encontrar_caso_do_paciente(doc.get("paciente", ""), doc.get("caso_id") or None)
                _avisar_paciente(caso_rg, "reagendamento_confirmado",
                                 "nova data: " + nova_data_val, "%s %s" % (obj_id, nova_data_val))
                # O estudante responsável e o supervisor do caso também precisam saber (sem nome do paciente).
                if caso_rg and not ja_confirmado:
                    _avisar_estudante(caso_rg, "reagendamento_confirmado", nova_data_val)
                    _avisar_supervisor_do_caso(caso_rg, "reagendamento_confirmado",
                                               "%s · %s" % (nova_data_val, caso_rg.get("estudante", "")))
            except PyMongoError as exc:
                print("[aviso ao paciente/estudante] caso não encontrado: %s" % exc, flush=True)

            doc["status"] = "confirmado"
            doc["nova_data"] = nova_data_val
            resposta = reagendamento_doc_to_json(doc)
            resposta["enviado_email"] = enviado
            resposta["agenda_alterada"] = agenda_alterada
            self._send_json(resposta)
            return

        self._send_error_json(404, "rota não encontrada: " + path)


def provisionar_admin_na_partida():
    """Cria a conta de Administração de TI quando o servidor liga, SEM rota pública: só acontece
    para quem controla as variáveis de ambiente do servidor (no Render).

        ADMIN_EMAIL              e-mail real da administradora (obrigatório para criar)
        ADMIN_NOME               nome completo (padrão: Milena Santana)
        ADMIN_REENVIAR_CONVITE=1 gera e envia um novo convite enquanto a conta ainda não foi ativada

    A conta nasce SEM senha; o link de ativação (uso único, 72 h) é enviado ao próprio e-mail e
    nunca é escrito no log. Idempotente: rodar de novo não duplica nada."""
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    if not email:
        return
    try:
        if not EMAIL_REGEX.match(email):
            print("[admin] ADMIN_EMAIL inválido — nada foi criado.")
            return
        existente = contas_col.find_one({"role": "admin_ti"})
        if existente:
            if existente["_id"] != email:
                print("[admin] já existe uma conta de administração com outro e-mail — nada foi alterado.")
                return
            if existente.get("status") == "convite_pendente" and os.environ.get("ADMIN_REENVIAR_CONVITE") == "1":
                token, convite = _novo_convite()
                contas_col.update_one({"_id": email}, {"$set": {"convite": convite}})
                _registrar_historico_admin({"email": "provisionamento", "nome": "Provisionamento"}, "Novo convite gerado para a conta de administração", email)
                enviado = _enviar_convite(email, existente.get("nome"), "admin_ti", token)
                print("[admin] novo convite gerado; e-mail %s." % ("ENVIADO" if enviado else "NÃO enviado (veja a configuração de e-mail)"))
            else:
                print("[admin] conta de administração já existe (situação: %s) — nada foi alterado." % existente.get("status"))
            return
        if email in CONTAS or contas_col.find_one({"_id": email}):
            print("[admin] este e-mail já é de outra conta — nada foi criado.")
            return
        nome = os.environ.get("ADMIN_NOME", "").strip() or "Milena Santana"
        token, convite = _novo_convite()
        contas_col.insert_one({
            "_id": email, "nome": nome, "role": "admin_ti", "funcao": FUNCAO_ADMIN, "instituicao": INSTITUICAO,
            "crp": "", "status": "convite_pendente", "salt": None, "senha_hash": None, "convite": convite,
            "criado_em": time.time(), "criado_em_br": _agora_br(), "criado_por": "provisionamento",
        })
        _registrar_historico_admin({"email": "provisionamento", "nome": "Provisionamento"}, "Conta de administração provisionada", email)
        enviado = _enviar_convite(email, nome, "admin_ti", token)
        if enviado:
            print("[admin] conta de administração criada; convite ENVIADO por e-mail.")
        else:
            print("[admin] conta de administração criada, mas o e-mail NÃO foi enviado (configure BREVO_API_KEY e EMAIL_FROM, "
                  "depois defina ADMIN_REENVIAR_CONVITE=1 e faça um novo deploy).")
    except Exception as exc:
        print("[admin] não foi possível provisionar a conta de administração: %s" % type(exc).__name__)


def main():
    provisionar_admin_na_partida()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("=" * 60)
    print(" Servidor do Prontuário Eletrônico rodando!")
    print(" Abra no navegador: http://localhost:%d" % PORT)
    print(" Banco de dados:    MongoDB (%s)" % DB_NAME)
    print(" Para parar: Ctrl+C")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")


if __name__ == "__main__":
    main()
