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

import json
import os
import re
import sys
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


class Handler(BaseHTTPRequestHandler):
    server_version = "ProntuarioServerMongo/1.0"

    # ---------- utilidades de resposta ----------
    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status, mensagem):
        self._send_json({"erro": mensagem}, status)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

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
            try:
                casos = {doc["_id"]: caso_doc_to_json(doc) for doc in casos_col.find({})}
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/casos")
                return
            self._send_json(casos)
            return

        if path == "/api/solicitacoes":
            try:
                fila = [solicitacao_doc_to_json(doc) for doc in solicitacoes_col.find({}).sort("_id", 1)]
            except PyMongoError as exc:
                self._erro_servidor(exc, "GET /api/solicitacoes")
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
        self.end_headers()
        self.wfile.write(content)

    # ---------- POST ----------
    def do_POST(self):
        path = self.path.split("?", 1)[0]

        if path == "/api/casos":
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
            try:
                body = self._read_json_body()
            except Exception:
                self._send_error_json(400, "corpo da requisição não é um JSON válido")
                return

            doc = dict(body)
            doc.pop("_id", None)

            paciente_val = str(doc.get("paciente", "")).strip()
            protocolo_val = str(doc.get("protocolo", "")).strip()
            if not paciente_val or not protocolo_val:
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
            doc["paciente"] = paciente_val
            doc["protocolo"] = protocolo_val

            try:
                result = solicitacoes_col.insert_one(doc)
            except PyMongoError as exc:
                self._erro_servidor(exc, "POST /api/solicitacoes")
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
            case_id = unquote(m.group(1))
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
