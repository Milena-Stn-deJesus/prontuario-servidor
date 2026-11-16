# -*- coding: utf-8 -*-
"""
Provisionamento da conta de Administração de TI (perfil "admin_ti").

QUANDO USAR: uma única vez, para criar a primeira conta de administração
(Milena Santana). Não existe cadastro público de administrador: esta é a única
forma de criar essa conta, e ela só funciona para quem tem a MONGODB_URI do
banco (ou seja, quem já controla o servidor).

COMO RODAR (no seu computador, com Python e as dependências do projeto):

    1. Abra um terminal na pasta do projeto.
    2. Defina a connection string do MongoDB Atlas (a mesma MONGODB_URI do Render):
         Linux/Mac:   export MONGODB_URI="mongodb+srv://..."
         Windows:     set MONGODB_URI=mongodb+srv://...
    3. (Opcional) defina o endereço do site, para o link sair certo:
         export SITE_URL="https://prontuario-servidor.onrender.com"
    4. Rode:
         python3 provisionar_admin.py
       O programa pergunta o seu e-mail real. Você também pode passá-lo pela
       variável ADMIN_EMAIL, mas ele NUNCA é gravado no código.

O QUE ACONTECE:
    - Cria a conta com status "convite pendente" e SEM senha (nenhuma senha é
      escrita no código nem aparece em lugar algum).
    - Mostra, uma única vez, na tela do seu terminal, um link de ativação de
      uso único (válido por 72 horas). Ele não é salvo em arquivo nem em log do
      servidor. Abra o link no navegador, crie a sua senha (mínimo de 10
      caracteres, com maiúscula, número e caractere especial) e depois entre
      normalmente pela tela de login da equipe.
    - Rodar de novo NÃO cria conta duplicada: se a conta já existe, o programa
      só avisa. Se o link expirou antes de você ativar, rode com --novo-convite.

NÃO execute este programa em um ambiente que grave a saída do terminal (CI,
logs de deploy), porque o link de ativação aparece nela.
"""
import os
import sys
import time

NOME_PADRAO = "Milena Santana"


def main():
    novo_convite = "--novo-convite" in sys.argv[1:]
    if not os.environ.get("MONGODB_URI"):
        print("Defina a variável MONGODB_URI antes de rodar (veja as instruções no topo deste arquivo).")
        return 1

    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    if not email:
        email = input("E-mail real da conta de Administração de TI: ").strip().lower()
        confirmacao = input("Digite o e-mail novamente para confirmar: ").strip().lower()
        if email != confirmacao:
            print("Os e-mails não conferem. Nada foi criado.")
            return 1

    nome = os.environ.get("ADMIN_NOME", "").strip()
    if not nome:
        nome = input("Nome completo (Enter para usar \"%s\"): " % NOME_PADRAO).strip() or NOME_PADRAO
    if len(nome) < 3 or len(nome) > 120:
        print("Nome inválido. Nada foi criado.")
        return 1

    import server  # reutiliza o banco, o hash de senha e as regras do servidor (não inicia o servidor)

    if not server.EMAIL_REGEX.match(email):
        print("E-mail inválido. Nada foi criado.")
        return 1

    existente = server.contas_col.find_one({"role": "admin_ti"})
    if existente:
        if existente["_id"] != email:
            print("Já existe uma conta de Administração de TI com outro e-mail. Este procedimento cria apenas a primeira conta; nada foi alterado.")
            return 1
        if existente.get("status") == "convite_pendente" and novo_convite:
            token, convite = server._novo_convite()
            server.contas_col.update_one({"_id": email}, {"$set": {"convite": convite}})
            server._registrar_historico_admin({"email": "provisionamento", "nome": "Provisionamento"}, "Novo convite gerado para a conta de administração", email)
            _mostrar_link(server, token)
            return 0
        print("A conta de Administração de TI já existe (situação: %s). Nada foi alterado." % existente.get("status"))
        if existente.get("status") == "convite_pendente":
            print("Se o link de ativação expirou ou foi perdido, rode: python3 provisionar_admin.py --novo-convite")
        return 0

    if email in server.CONTAS or server.contas_col.find_one({"_id": email}):
        print("Este e-mail já está em uso por outra conta. Nada foi criado.")
        return 1

    token, convite = server._novo_convite()
    server.contas_col.insert_one({
        "_id": email,
        "nome": nome,
        "role": "admin_ti",
        "funcao": server.FUNCAO_ADMIN,
        "instituicao": server.INSTITUICAO,
        "crp": "",
        "status": "convite_pendente",
        "salt": None,
        "senha_hash": None,
        "convite": convite,
        "criado_em": time.time(),
        "criado_em_br": server._agora_br(),
        "criado_por": "provisionamento",
    })
    server._registrar_historico_admin({"email": "provisionamento", "nome": "Provisionamento"}, "Conta de administração provisionada", email)
    print("Conta de Administração de TI criada (sem senha, aguardando ativação).")
    _mostrar_link(server, token)
    return 0


def _mostrar_link(server, token):
    print()
    print("Link de ativação (uso único, válido por %d horas). Ele aparece só agora:" % (server.CONVITE_VALIDADE_SEGUNDOS // 3600))
    print()
    print("    " + server._link_convite(token))
    print()
    print("Abra-o no navegador, crie a sua senha e depois entre pela tela de login da equipe.")


if __name__ == "__main__":
    sys.exit(main())
