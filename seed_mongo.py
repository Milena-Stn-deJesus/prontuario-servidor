# -*- coding: utf-8 -*-
"""
Popula o MongoDB com os 4 casos de demonstração (Maria, Carlos, Juliana, Pedro)
que o site já usava antes. Rode este script UMA VEZ, depois de configurar a
variável de ambiente MONGODB_URI (veja as instruções no topo do server.py),
e antes de usar o site pela primeira vez com o banco novo.

Como rodar:
    (com a MONGODB_URI já configurada no terminal, do mesmo jeito que pro server.py)
    python seed_mongo.py

Rodar este script mais de uma vez não duplica os dados: ele sempre SUBSTITUI
os casos de demonstração (case-1 a case-4) pelo conteúdo original do arquivo
casos_seed.json, sem mexer em nenhum paciente novo que você já tenha cadastrado
com outro id.
"""

import json
import os
import sys
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError:
    print("ERRO: rode 'pip install -r requirements.txt' antes de usar este script.")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent
SEED_FILE = BASE_DIR / "casos_seed.json"

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME = os.environ.get("MONGODB_DB_NAME", "prontuario")

if not MONGODB_URI:
    print("ERRO: configure a variável de ambiente MONGODB_URI antes de rodar este script")
    print("(as instruções estão no topo do arquivo server.py).")
    sys.exit(1)

if not SEED_FILE.exists():
    print("ERRO: não encontrei o arquivo casos_seed.json nesta pasta.")
    sys.exit(1)

with open(SEED_FILE, "r", encoding="utf-8") as f:
    seed = json.load(f)

client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000)
client.admin.command("ping")
db = client[DB_NAME]
casos_col = db["casos"]

for case_id, caso in seed.items():
    doc = dict(caso)
    doc["_id"] = case_id
    casos_col.replace_one({"_id": case_id}, doc, upsert=True)
    print("OK:", case_id, "-", caso.get("paciente"))

print("\nPronto! %d casos de demonstração estão no banco '%s'." % (len(seed), DB_NAME))
print("Os dados antigos do arquivo data/casos.json NÃO são mais usados a partir de agora.")
