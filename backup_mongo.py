# -*- coding: utf-8 -*-
"""
Faz um backup de segurança dos dados do MongoDB Atlas (coleções "casos" e
"solicitacoes") para arquivos JSON locais, com data e hora no nome do
arquivo. Não apaga nem altera nada no banco — só LÊ e salva uma cópia.

Por que isso existe: antes de qualquer auditoria de segurança ou mudança
grande no servidor, é importante ter uma cópia dos dados de agora, pra caso
algo dê errado e seja preciso restaurar.

Como rodar (com a MONGODB_URI já configurada no terminal, do mesmo jeito
que pro server.py):
    python backup_mongo.py

Isso cria uma pasta "backups/" (se ainda não existir) com dois arquivos,
por exemplo:
    backups/casos_2026-11-10_21-40-00.json
    backups/solicitacoes_2026-11-10_21-40-00.json

Para restaurar um backup manualmente, é só abrir o arquivo JSON e, se
necessário, usar o MongoDB Atlas (Browse Collections) para recriar os
documentos — ou pedir ajuda para escrever um script de restauração a
partir de um desses arquivos.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import certifi
    from pymongo import MongoClient
except ImportError:
    print("ERRO: rode 'pip install -r requirements.txt' antes de usar este script.")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent
BACKUP_DIR = BASE_DIR / "backups"

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME = os.environ.get("MONGODB_DB_NAME", "prontuario")

if not MONGODB_URI:
    print("ERRO: configure a variável de ambiente MONGODB_URI antes de rodar este script")
    print("(as instruções estão no topo do arquivo server.py).")
    sys.exit(1)

client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000, tlsCAFile=certifi.where())
client.admin.command("ping")
db = client[DB_NAME]

BACKUP_DIR.mkdir(exist_ok=True)
stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def dump_collection(name, id_field="_id"):
    docs = list(db[name].find({}))
    for d in docs:
        d[id_field] = str(d[id_field])
    out_path = BACKUP_DIR / f"{name}_{stamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)
    print(f"OK: {len(docs)} documento(s) de '{name}' salvos em {out_path}")


dump_collection("casos")
dump_collection("solicitacoes")

print("\nBackup concluído. Guarde a pasta 'backups/' em um lugar seguro")
print("(ela não precisa ir para o GitHub nem para o Render).")
