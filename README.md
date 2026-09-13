# Avisador de Notas — Portal Educacional TOTVS RM

Sistema que verifica periodicamente o portal de notas e te avisa por
**e-mail** e/ou **Discord** quando alguma nota mudar. Roda sozinho no
GitHub Actions (de graça), sem precisar deixar celular ou PC ligado.

---

## 1. Criar o repositório no GitHub

1. Crie uma conta em https://github.com (se ainda não tiver)
2. Clique em **New repository**
3. Marque como **Private** (importante — evita expor a estrutura do
   projeto publicamente, embora nenhuma senha fique no código)
4. Suba todos os arquivos deste zip para o repositório (pode arrastar
   os arquivos na interface web do GitHub, em "Add file" → "Upload files")

---

## 2. Configurar os Secrets (senhas e webhooks)

No repositório: **Settings → Secrets and variables → Actions → New
repository secret**. Crie um secret para cada item abaixo:

| Nome do Secret | O que colocar |
|---|---|
| `PORTAL_USUARIO` | Seu usuário/login do portal |
| `PORTAL_SENHA` | Sua senha do portal |
| `DISCORD_WEBHOOK_URL` | URL do webhook do Discord (veja passo 2.1) |
| `SMTP_HOST` | Servidor de e-mail (veja passo 2.2) |
| `SMTP_PORT` | Porta do servidor (geralmente `465`) |
| `SMTP_USER` | Seu e-mail completo |
| `SMTP_PASS` | Senha de app do seu e-mail (veja passo 2.2) |

### 2.1 Criar o webhook do Discord
1. No servidor do Discord, vá em **Configurações do canal → Integrações → Webhooks**
2. Clique em **Novo Webhook**, dê um nome (ex: "Avisador de Notas")
3. Clique em **Copiar URL do Webhook**
4. Cole esse valor no Secret `DISCORD_WEBHOOK_URL`

### 2.2 Configurar o e-mail (exemplo com Gmail)
Gmail não permite usar a senha normal para isso — você precisa de uma
**senha de app**:
1. Ative a verificação em duas etapas na sua conta Google (obrigatório)
2. Acesse https://myaccount.google.com/apppasswords
3. Crie uma senha de app (nome sugerido: "avisador-notas")
4. Use os valores:
   - `SMTP_HOST` = `smtp.gmail.com`
   - `SMTP_PORT` = `465`
   - `SMTP_USER` = seu e-mail do Gmail
   - `SMTP_PASS` = a senha de app gerada (16 caracteres, sem espaços)

Se usar outro provedor (Outlook, Yahoo etc), procure o "host SMTP" e
"senha de app" desse provedor especificamente.

---

## 3. Editar o config.yaml

Abra `config.yaml` e ajuste:
- `notifications.email.to` → seu e-mail de destino
- `notifications.email.enabled` / `notifications.discord.enabled` →
  `true` ou `false` pra ligar/desligar cada canal
- Deixe o resto como está por enquanto

---

## 4. Conferir os seletores de login (passo mais importante)

O script precisa saber o "nome" dos campos de usuário/senha na tela de
login. Já deixei os mais comuns em `config.yaml`, mas **pode ser que
precisem de ajuste** para o seu portal específico. Para conferir:

1. Abra o portal em uma aba anônima (sem estar logado)
2. Aperte `F12` → clique no ícone de "inspecionar elemento" (setinha)
3. Clique em cima do campo de **usuário** da tela de login
4. No painel que abre, vai aparecer algo como `<input id="txtUsuario" ...>`
   — anote esse `id`
5. Repita para o campo de **senha** e para o **botão de entrar**
6. Se os valores forem diferentes dos que já estão no `config.yaml`,
   edite a seção `portal.selectors` com os valores corretos, no formato:
   ```yaml
   username_input: "#id_que_voce_achou"
   password_input: "#id_que_voce_achou"
   submit_button: "#id_que_voce_achou"
   ```

---

## 5. Testar

1. No repositório, vá na aba **Actions**
2. Clique no workflow **"Verificar novas notas"**
3. Clique em **Run workflow** (canto direito) → **Run workflow**
4. Espere terminar e clique na execução pra ver os logs — se dizer
   "Nenhuma mudança relevante para avisar", funcionou (primeira
   execução nunca avisa, só salva o estado inicial)
5. Se der erro, o log vai indicar o motivo (login incorreto, seletor
   errado, etc.) — a seção de Solução de Problemas abaixo ajuda

---

## 6. Ajustar a frequência

Abra `.github/workflows/check-notas.yml` e edite a linha `cron`.
O horário do GitHub Actions é sempre em **UTC** (Brasil = UTC−3, sem
horário de verão atualmente). Exemplos:

```yaml
cron: "*/30 * * * *"     # a cada 30 minutos, o dia todo
cron: "0 * * * *"        # uma vez por hora
cron: "0 9-23/2 * * *"   # a cada 2h, das 6h às 20h no horário do Brasil
```

⚠️ Evite deixar menos que 15-20 min de intervalo — o GitHub Actions
pode atrasar ou pular execuções muito frequentes em contas gratuitas.

---

## Solução de problemas

**"não encontrei a tela de login"** — o `wait_for_selector` não achou
os campos. Refaça o passo 4 (seletores).

**"não consegui capturar a resposta da API"** — login pode ter
falhado silenciosamente (senha errada?) ou o portal mudou de endpoint.
Confira `PORTAL_USUARIO`/`PORTAL_SENHA`.

**E-mail não chega** — confira se ativou a senha de app corretamente
(passo 2.2), e olhe a caixa de spam.

**Discord não recebe nada** — confira se a URL do webhook foi colada
inteira no Secret.

---

## Arquivos do projeto

```
aviso-notas/
├── check_notas.py              # script principal
├── config.yaml                 # configurações (tempo, e-mail, etc)
├── notas_state.json            # última leitura das notas (gerado automaticamente)
├── requirements.txt            # dependências Python
├── README.md                   # este guia
└── .github/workflows/
    └── check-notas.yml         # agendamento (GitHub Actions)
```
