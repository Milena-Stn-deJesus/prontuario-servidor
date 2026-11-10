# Prontuário Eletrônico — versão com MongoDB

Esta pasta contém a versão do protótipo que salva os dados no **MongoDB**
(um banco de dados de verdade, que pode ficar na nuvem) em vez de um arquivo
`.json` local. Com isso, técnico, supervisor, estudante e paciente — mesmo em
computadores e redes diferentes — podem enxergar os mesmos dados, desde que o
servidor esteja hospedado em algum lugar acessível por todos (veja a etapa de
hospedagem mais abaixo).

## O que tem aqui

```
prontuario-servidor/
├── server.py                 -> o servidor (lê/escreve no MongoDB)
├── seed_mongo.py              -> script para popular o banco com os 4 casos de demonstração
├── casos_seed.json            -> os dados originais desses 4 casos (usados pelo seed_mongo.py)
├── requirements.txt            -> lista de bibliotecas Python necessárias (só o pymongo)
├── psicare-site-v2.html       -> o site (a interface que você já conhece)
└── README.md                  -> este arquivo
```

## Etapa 1 — Criar o banco de dados gratuito no MongoDB Atlas

1. Acesse https://www.mongodb.com/cloud/atlas/register e crie uma conta gratuita.
2. Na criação do primeiro cluster, escolha o plano **M0 (Free)**.
3. Em **Database Access**, crie um usuário de banco de dados (um login e senha
   só para o servidor usar — pode ser diferente do seu login do Atlas).
4. Em **Network Access**, clique em "Add IP Address" e escolha **"Allow access
   from anywhere"** (0.0.0.0/0) — isso é necessário porque você (e depois o
   Render) vão acessar de endereços diferentes. Não é o ideal para um sistema
   real com pacientes de verdade, mas é apropriado para este protótipo.
5. Clique em **Connect** → **Drivers** → copie a "connection string". Vai ser
   algo parecido com:
   ```
   mongodb+srv://seu_usuario:sua_senha@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   Guarde esse texto — é a "chave" que o servidor usa para falar com o banco.
   **Nunca cole essa string dentro do código ou a compartilhe publicamente** —
   ela equivale a uma senha.

## Etapa 2 — Rodar localmente para testar

1. Instale a biblioteca necessária (só precisa fazer isso uma vez):
   ```
   pip install -r requirements.txt
   ```
2. Configure a connection string como variável de ambiente, no mesmo terminal
   onde você vai rodar o servidor:

   **Windows (PowerShell):**
   ```
   $env:MONGODB_URI = "sua-connection-string-aqui"
   python server.py
   ```

   **Windows (Prompt de Comando / cmd):**
   ```
   set MONGODB_URI=sua-connection-string-aqui
   python server.py
   ```

3. Na primeira vez, popule o banco com os 4 casos de demonstração (Maria,
   Carlos, Juliana, Pedro) — na mesma janela de terminal, com a variável já
   configurada:
   ```
   python seed_mongo.py
   ```
4. Agora rode o servidor:
   ```
   python server.py
   ```
5. Abra o navegador em `http://localhost:5000` e use o site normalmente.

Se aparecer um erro de conexão ao iniciar o servidor, confira: a connection
string foi colada certinha, o usuário/senha do banco estão corretos, e você
liberou o acesso "from anywhere" no Network Access do Atlas.

## Etapa 3 — Hospedar o servidor na internet (para acesso de qualquer lugar)

Isso é o que permite que um paciente acesse o site de casa, sem precisar
que o seu computador esteja ligado. Um serviço gratuito comum para isso é o
**Render** (render.com):

1. Crie uma conta gratuita em https://render.com.
2. O Render só hospeda a partir de um repositório do GitHub (não dá pra
   subir um .zip direto) — então, antes, suba os arquivos desta pasta
   para um repositório novo no seu GitHub.
3. No Render, clique em **New** → **Web Service**, conecte sua conta do
   GitHub e escolha esse repositório. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python server.py`
4. Em **Environment Variables**, adicione `MONGODB_URI` com o valor da sua
   connection string do Atlas (a mesma da Etapa 1) — é aqui, e não no código,
   que ela fica guardada com segurança.
5. Depois do deploy, o Render te dá uma URL pública (algo como
   `https://prontuario-milena.onrender.com`) — esse é o endereço que qualquer
   pessoa, em qualquer rede, pode acessar.

No plano gratuito do Render, o serviço "dorme" depois de um tempo sem uso, e
a primeira pessoa a acessar depois disso espera uns 30-50 segundos enquanto
ele "acorda" — normal para um protótipo, vale avisar quem for testar.

## Se aparecer uma faixa vermelha no topo da página

Significa que o navegador não conseguiu falar com o servidor — confira se o
`server.py` está rodando (ou se o serviço no Render está no ar) e se você
está acessando pelo endereço certo (não abrindo o `.html` direto).

## Resetar os dados de demonstração

Rode `python seed_mongo.py` novamente a qualquer momento — ele sempre
restaura os 4 casos originais (Maria, Carlos, Juliana, Pedro) ao conteúdo
inicial, sem apagar outros pacientes que você tenha cadastrado com outro id.
