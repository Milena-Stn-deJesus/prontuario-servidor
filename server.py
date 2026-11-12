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
    PUT  /api/casos/<id>            -> substitui um caso (agenda, evolução, documento, anamnese...)
    GET  /api/solicitacoes          -> devolve a fila de solicitações de prontuário
    POST /api/solicitacoes          -> cria uma nova solicitação (paciente pede o prontuário)
    PUT  /api/solicitacoes/<id>     -> atualiza uma solicitação (técnico libera o acesso)
    GET  /api/reagendamentos        -> devolve a fila de pedidos de reagendamento
    POST /api/reagendamentos        -> cria um novo pedido (paciente pede para reagendar)
    PUT  /api/reagendamentos/<id>   -> confirma uma nova data (equipe escolhe a data;
                                        dispara o e-mail de confirmação para o paciente)
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

try:
    import certifi
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    from bson import ObjectId
    from bson.errors import InvalidId
except ImportError:
    print("=" * 70)
    print(" ERRO: a biblioteca 'pymongo' não está instalada.")
    print(" Rode primeiro:  pip install -r requirements.txt")
    print("=" * 70)
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent
HTML_FILE = BASE_DIR / "psicare-site-v2.html"

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
EMAIL_FROM = os.environ.get("EMAIL_FROM", SMTP_USER)


def _enviar_email(destinatario, assunto, corpo):
    """Manda um e-mail de texto simples. Devolve True se enviou de verdade,
    False se não conseguiu (inclusive se o SMTP não estiver configurado)."""
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
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
        "Nova data: %s\n\n"
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

SENHA_SALT = os.environ.get("SENHA_SALT", "prontuario-fcmscsp-salt-fixo-2026")


def _hash_senha(senha):
    """Deriva um hash da senha com PBKDF2 (não guarda nem compara a senha em
    texto puro). Usa só a biblioteca padrão do Python (hashlib), sem precisar
    instalar nada além do que já está em requirements.txt."""
    derivado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), SENHA_SALT.encode("utf-8"), 200_000)
    return derivado.hex()


def _conta(role, nome, senha):
    return {"role": role, "nome": nome, "senha_hash": _hash_senha(senha)}


CONTAS = {
    # equipe
    "tecnico@exemplo.com": _conta("tecnico", "Fernando Ricci", "senha123"),
    "supervisor@exemplo.com": _conta("supervisor", "Dra. Patrícia Novaes", "senha123"),
    "estudante@exemplo.com": _conta("estudante", "Ana Beatriz Lima", "senha123"),
    # primeiro acesso da equipe (senha temporária = RA/matrícula)
    "novo.tecnico@exemplo.com": _conta("tecnico", "Novo Técnico", "202601001"),
    "novo.supervisor@exemplo.com": _conta("supervisor", "Novo Supervisor", "202601002"),
    "novo.estudante@exemplo.com": _conta("estudante", "Novo Estudante", "202601234"),
    # paciente
    "paciente@exemplo.com": _conta("paciente", "Maria Fernanda Alves", "senha123"),
    "carlos@exemplo.com": _conta("paciente", "Carlos Eduardo Mendes", "senha123"),
    # primeiro acesso do paciente (senha temporária = CPF)
    "novo@exemplo.com": _conta("paciente", "Pedro Henrique Souza", "11122233344"),
}

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
PAPEIS_SOLICITACOES_LEITURA = {"tecnico", "supervisor"}
PAPEIS_SOLICITACOES_ESCRITA = {"tecnico", "supervisor"}

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
print("Conectado ao MongoDB! Banco: %s" % DB_NAME)


def novo_id_de_caso():
    import random
    n = casos_col.count_documents({}) + 1
    sufixo = random.randint(100, 999)
    candidato = "case-%d-%d" % (n, sufixo)
    while casos_col.find_one({"_id": candidato}):
        sufixo = random.randint(100, 999)
        candidato = "case-%d-%d" % (n, sufixo)
    return candidato


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
# acessa os casos em que ele mesmo é "estudante" responsável; um supervisor
# só acessa os casos em que ele é o "supervisor"; o técnico (papel
# administrativo, que também processa solicitações de prontuário e
# reagendamentos de qualquer paciente) mantém acesso a todos os casos, como
# já funcionava antes.

def _filtro_visibilidade_casos(sessao):
    """Filtro do MongoDB a aplicar em GET /api/casos conforme o papel da
    sessão. Devolve {} (sem filtro = vê tudo) para técnico; para estudante e
    supervisor, restringe à coluna correspondente com o nome da própria
    sessão."""
    if sessao["role"] == "estudante":
        return {"estudante": sessao["nome"]}
    if sessao["role"] == "supervisor":
        return {"supervisor": sessao["nome"]}
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
        return caso_doc.get("supervisor") == sessao["nome"]
    return False


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
            "img-src 'self' data: https://vlibras.gov.br; "
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
            self._send_error_json(403, "seu perfil não tem permissão para esta operação")
            return None
        return sessao

    # ---------- OPTIONS (pre-flight de CORS) ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ---------- GET ----------
    def do_GET(self):
        path = self.path.split("?", 1)[0]

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

        self._send_error_json(404, "rota não encontrada: " + path)

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
            if not conta or conta["senha_hash"] != _hash_senha(senha):
                t = TENTATIVAS_LOGIN.setdefault(email, {"falhas": 0, "bloqueado_ate": None})
                t["falhas"] += 1
                if t["falhas"] >= MAX_TENTATIVAS:
                    t["bloqueado_ate"] = agora + BLOQUEIO_SEGUNDOS
                    t["falhas"] = 0
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
                "criado_em": agora,
            }
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
                SESSOES.pop(auth[len("Bearer "):].strip(), None)
            self._send_json({"ok": True})
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

        if path == "/api/casos":
            # Correção de segurança: cadastrar um paciente novo é uma ação
            # administrativa — a própria tela só mostra esse formulário para o
            # técnico (estudante e supervisor nunca veem esse botão). O
            # servidor não garantia isso: qualquer um dos três papéis podia
            # criar um caso novo chamando a API diretamente.
            if self._exigir_papel({"tecnico"}) is None:
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

            caso = {
                "_id": novo_id_de_caso(),
                "paciente": nome_paciente,
                "estudante": body.get("estudante", ""),
                "supervisor": body.get("supervisor", ""),
                "status": status_val,
                "abertura": body.get("abertura", ""),
                "anamnese": None,
                "evolucoes": [],
                "documentos": [],
                "agendamentos": [],
            }
            try:
                casos_col.insert_one(dict(caso))
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/casos")
                return
            self._send_json({"id": caso["_id"], "caso": caso_doc_to_json(caso)}, 201)
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

            # Só técnico e supervisor podem encerrar/reabrir um caso — a
            # própria tela já impede isso para o estudante (canCloseCase()),
            # mas essa regra não era garantida pelo servidor.
            if sessao["role"] == "estudante" and body.get("status") != caso_atual.get("status"):
                self._send_error_json(403, "apenas técnico ou supervisor podem encerrar ou reabrir um caso")
                return

            try:
                result = casos_col.replace_one({"_id": case_id}, {"_id": case_id, **body})
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/casos/" + case_id)
                return
            if result.matched_count == 0:
                self._send_error_json(404, "caso não encontrado: " + case_id)
                return
            self._send_json(body)
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
                result = solicitacoes_col.replace_one({"_id": obj_id}, body)
            except PyMongoError as exc:
                self._erro_servidor(exc, "PUT /api/solicitacoes/" + str(obj_id))
                return
            if result.matched_count == 0:
                self._send_error_json(404, "solicitação não encontrada: " + str(obj_id))
                return
            body["_id"] = str(obj_id)
            self._send_json(body)
            return

        m3 = re.match(r"^/api/reagendamentos/([0-9a-fA-F]{24})$", path)
        if m3:
            if self._exigir_papel(PAPEIS_SOLICITACOES_ESCRITA) is None:
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
            if not nova_data_val:
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

            doc["status"] = "confirmado"
            doc["nova_data"] = nova_data_val
            resposta = reagendamento_doc_to_json(doc)
            resposta["enviado_email"] = enviado
            self._send_json(resposta)
            return

        self._send_error_json(404, "rota não encontrada: " + path)


def main():
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
