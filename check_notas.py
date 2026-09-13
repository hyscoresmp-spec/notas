"""
Avisador de Notas - TOTVS RM Portal Educacional
=================================================
Faz login no portal (via navegador real, usando Playwright),
intercepta a chamada de API que traz as notas, compara com a
última leitura salva e, se houver mudança, dispara avisos por
e-mail e/ou Discord.

Não deve ser necessário editar este arquivo. Ajustes de
comportamento vão em config.yaml. Credenciais e webhooks vão em
variáveis de ambiente / GitHub Secrets (veja README.md).
"""

import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

import requests
import yaml
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
STATE_PATH = BASE_DIR / "notas_state.json"


def carregar_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def carregar_estado_anterior():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def salvar_estado(notas):
    STATE_PATH.write_text(
        json.dumps(notas, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def pegar_credenciais():
    usuario = os.environ.get("PORTAL_USUARIO")
    senha = os.environ.get("PORTAL_SENHA")
    if not usuario or not senha:
        print(
            "ERRO: variáveis de ambiente PORTAL_USUARIO e PORTAL_SENHA "
            "não foram definidas. Configure os Secrets no GitHub "
            "(veja README.md)."
        )
        sys.exit(1)
    return usuario, senha


def logar_e_capturar_notas(config):
    usuario, senha = pegar_credenciais()
    sel = config["portal"]["selectors"]
    api_marker = config["portal"]["api_notas_endpoint"]

    notas_capturadas = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Escuta todas as respostas de rede; quando achar a chamada
        # de notas, guarda o JSON.
        def on_response(response):
            if api_marker in response.url and response.status == 200:
                try:
                    data = response.json()
                    notas_capturadas["payload"] = data
                except Exception:
                    pass

        page.on("response", on_response)

        print("Abrindo o portal...")
        page.goto(config["portal"]["url"], wait_until="domcontentloaded")

        # Tenta preencher o login. Se os campos não existirem
        # (ex: sessão já ativa / cache), apenas segue em frente.
        try:
            page.wait_for_selector(sel["username_input"], timeout=15000)
            page.fill(sel["username_input"], usuario)
            page.fill(sel["password_input"], senha)
            page.click(sel["submit_button"])
            print("Login enviado, aguardando carregar...")
            page.wait_for_timeout(config["portal"]["wait_after_login_ms"])
        except Exception as e:
            print(f"Aviso: não encontrei a tela de login ({e}). "
                  f"Seguindo (pode já estar logado ou os seletores "
                  f"em config.yaml precisam de ajuste).")
            # Salva evidências pra facilitar o diagnóstico: um print
            # da tela e o HTML da página no momento da falha.
            try:
                page.screenshot(path=str(BASE_DIR / "debug_login.png"), full_page=True)
                (BASE_DIR / "debug_login.html").write_text(page.content(), encoding="utf-8")
                print("Salvei debug_login.png e debug_login.html para diagnóstico.")
            except Exception as e2:
                print(f"Não consegui salvar os arquivos de debug: {e2}")

        # NÃO navegamos de novo aqui: como o portal é uma SPA (Angular)
        # que guarda a sessão em memória, um reload completo da página
        # jogaria de volta pra tela de login. Deixamos a própria SPA
        # reagir ao login e trocar de tela sozinha.
        page.wait_for_timeout(3000)

        # Espera ativa pela captura da API, até o timeout configurado
        timeout_ms = config["portal"]["wait_for_notas_ms"]
        esperado = 0
        intervalo = 500
        while "payload" not in notas_capturadas and esperado < timeout_ms:
            page.wait_for_timeout(intervalo)
            esperado += intervalo

        # Sempre salva um print + HTML do estado final da página.
        # Se a API de notas não foi capturada, isso ajuda a ver em
        # qual tela o script "travou" (ex: seleção de turma, menu
        # intermediário, etc.)
        try:
            page.screenshot(path=str(BASE_DIR / "debug_login.png"), full_page=True)
            (BASE_DIR / "debug_login.html").write_text(page.content(), encoding="utf-8")
        except Exception as e2:
            print(f"Não consegui salvar os arquivos de debug: {e2}")

        browser.close()

    if "payload" not in notas_capturadas:
        print(
            "ERRO: não consegui capturar a resposta da API de notas. "
            "Possíveis causas: login falhou (confira PORTAL_USUARIO/"
            "PORTAL_SENHA e os seletores em config.yaml), ou o portal "
            "mudou de endpoint. Veja debug_login.png / debug_login.html "
            "nos artefatos desta execução."
        )
        sys.exit(1)

    return notas_capturadas["payload"]


def extrair_notas_relevantes(payload):
    """
    Reduz o JSON bruto da API a um dicionário simples
    {chave_disciplina: {coluna: valor}} para facilitar comparação.
    """
    resultado = {}
    notas = payload.get("data", {}).get("Notas", [])
    for item in notas:
        chave = f"{item.get('CODTURMA')}|{item.get('CODDISC')}"
        colunas = {
            k: v
            for k, v in item.items()
            if k not in ("FILIAL", "CODTURMA", "CODDISC")
        }
        resultado[chave] = {
            "disciplina": item.get("DISCIPLINA"),
            "colunas": colunas,
        }
    return resultado


def formatar_boletim_completo(notas):
    """Monta um texto legível com todas as disciplinas e notas atuais."""
    linhas = []
    for dados in notas.values():
        disciplina = dados["disciplina"]
        colunas = dados["colunas"]
        linhas.append(f"\n{disciplina}")
        for coluna, valor in colunas.items():
            if valor not in (None, ""):
                linhas.append(f"   {coluna}: {valor}")
    return "\n".join(linhas) if linhas else "(nenhuma nota encontrada)"


def comparar_notas(antigo, novo):
    """Retorna lista de strings descrevendo o que mudou."""
    mudancas = []

    if antigo is None:
        return mudancas  # primeira execução, sem base de comparação

    for chave, dados_novos in novo.items():
        disciplina = dados_novos["disciplina"]
        colunas_novas = dados_novos["colunas"]
        colunas_antigas = antigo.get(chave, {}).get("colunas", {})

        for coluna, valor_novo in colunas_novas.items():
            valor_antigo = colunas_antigas.get(coluna)
            if valor_antigo != valor_novo and valor_novo is not None:
                mudancas.append(
                    f"{disciplina} — {coluna}: "
                    f"{valor_antigo if valor_antigo is not None else '(vazio)'} → {valor_novo}"
                )

    return mudancas


def enviar_email(config, mudancas, boletim_completo, primeira_execucao):
    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT")
    user = os.environ.get("SMTP_USER")
    senha = os.environ.get("SMTP_PASS")

    if not all([host, port, user, senha]):
        print("Aviso: variáveis SMTP_* não configuradas, pulando e-mail.")
        return

    destinatario = config["notifications"]["email"]["to"]

    if primeira_execucao:
        assunto = "📚 Boletim atual (primeira leitura)"
        corpo = (
            "Esta é a primeira leitura do sistema — ainda não havia "
            "nada salvo pra comparar. A partir de agora, qualquer "
            "mudança será avisada.\n"
            "\n=== Boletim atual ===" + boletim_completo
        )
    else:
        assunto = config["notifications"]["email"]["subject"]
        corpo = (
            "O que mudou:\n\n" + "\n".join(f"- {m}" for m in mudancas)
            + "\n\n=== Boletim completo atual ===" + boletim_completo
        )

    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = assunto
    msg["From"] = user
    msg["To"] = destinatario

    with smtplib.SMTP_SSL(host, int(port)) as server:
        server.login(user, senha)
        server.sendmail(user, [destinatario], msg.as_string())

    print("E-mail enviado.")


def enviar_discord(mudancas, boletim_completo, primeira_execucao):
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("Aviso: DISCORD_WEBHOOK_URL não configurado, pulando Discord.")
        return

    if primeira_execucao:
        texto = "**📚 Primeira leitura do boletim**\n```" + boletim_completo + "\n```"
    else:
        texto = (
            "**📚 Nova nota lançada!**\n"
            + "\n".join(f"• {m}" for m in mudancas)
            + "\n\n**Boletim completo:**\n```" + boletim_completo + "\n```"
        )
    # Discord limita mensagens a 2000 caracteres
    texto = texto[:1990]

    resp = requests.post(webhook_url, json={"content": texto}, timeout=15)
    resp.raise_for_status()
    print("Mensagem enviada ao Discord.")


def main():
    config = carregar_config()

    payload = logar_e_capturar_notas(config)
    notas_novas = extrair_notas_relevantes(payload)
    notas_antigas = carregar_estado_anterior()

    mudancas = comparar_notas(notas_antigas, notas_novas)
    boletim_completo = formatar_boletim_completo(notas_novas)

    primeira_execucao = notas_antigas is None
    deve_avisar = bool(mudancas) or (
        primeira_execucao and config.get("avisar_na_primeira_execucao")
    )

    if deve_avisar:
        if primeira_execucao:
            print("Primeira execução — enviando boletim completo.")
        else:
            print(f"{len(mudancas)} mudança(s) detectada(s):")
            for m in mudancas:
                print(" -", m)

        if config["notifications"]["email"]["enabled"]:
            enviar_email(config, mudancas, boletim_completo, primeira_execucao)
        if config["notifications"]["discord"]["enabled"]:
            enviar_discord(mudancas, boletim_completo, primeira_execucao)
    else:
        print("Nenhuma mudança relevante para avisar.")

    salvar_estado(notas_novas)


if __name__ == "__main__":
    main()
