import os
import sys
import time
import pickle
import base64
import subprocess
import instaloader

def export_session(cookie_dict, username, session_file="instaloader.session"):
    with open(session_file, "wb") as f:
        pickle.dump(cookie_dict, f)
    
    print(f"\n✅ Ficheiro de sessão guardado como '{session_file}'.")

    # Testar a sessão com o Instaloader
    try:
        L = instaloader.Instaloader()
        L.load_session_from_file(username, session_file)
        test_user = L.test_login()
        print(f"✅ Sessão verificada com sucesso! Conectado como: {test_user or username}")
    except Exception as e:
        print(f"⚠️ Nota ao verificar sessão no Instaloader: {e}")

    # Gerar Base64
    with open(session_file, "rb") as f:
        b64_str = base64.b64encode(f.read()).decode("utf-8")

    # Copiar para o clipboard no Windows se possível
    copied = False
    try:
        subprocess.run(["powershell", "-command", f"Set-Clipboard -Value '{b64_str}'"], check=True, capture_output=True)
        copied = True
    except Exception:
        pass

    print("\n" + "=" * 70)
    print("🔑 O TEU INSTA_SESSION_BASE64:")
    print("=" * 70)
    print(b64_str)
    print("=" * 70)

    if copied:
        print("\n📋 O código Base64 foi COPIADO AUTOMATICAMENTE para a tua área de transferência (Ctrl+V)!")
    else:
        print("\n📋 Copia o texto longo acima.")

    print("\nPassos seguintes no GitHub:")
    print("1. Vai ao teu repositório no GitHub -> Settings -> Secrets and variables -> Actions")
    print("2. Cria ou edita o Secret: INSTA_SESSION_BASE64")
    print("3. Cola o código Base64 lá dentro e guarda.")


def browser_login():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright não está instalado. Instala com: pip install playwright && playwright install chromium")
        return False

    print("\n🌐 A abrir o navegador para login visual no Instagram...")
    print("👉 Na janela que vai abrir, faz login normalmente na tua conta.")
    print("   (Se pedir código 2FA ou verificação 'Fui eu', confirma na janela do browser)\n")

    cookies_dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        
        try:
            page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
        except Exception as e:
            print(f"Erro ao carregar página: {e}")

        print("⏳ À espera que termines o login no navegador...")
        for _ in range(150):  # Espera até 5 minutos
            time.sleep(2)
            try:
                cookies = context.cookies("https://www.instagram.com")
                c_dict = {c["name"]: c["value"] for c in cookies}
                if "sessionid" in c_dict and "ds_user_id" in c_dict and "csrftoken" in c_dict:
                    cookies_dict = c_dict
                    break
            except Exception:
                pass

        browser.close()

    if not cookies_dict:
        print("❌ Não foi detetada uma sessão válida ou a janela foi fechada antes do login.")
        return False

    username = input("\nConfirma o teu username do Instagram (ex: noticiasdeontempt): ").strip()
    if not username:
        username = "noticiasdeontempt"

    export_session(cookies_dict, username)
    return True


def cli_login():
    username = input("Username do Instagram: ").strip()
    L = instaloader.Instaloader()
    try:
        L.interactive_login(username)
        session_file = "instaloader.session"
        L.save_session_to_file(session_file)
        with open(session_file, "rb") as f:
            cookie_dict = pickle.load(f)
        export_session(cookie_dict, username, session_file)
    except Exception as e:
        print(f"\n❌ Erro no login CLI: {e}")


def main():
    print("=" * 60)
    print("   GERADOR DE SESSÃO INSTAGRAM (BASE64)")
    print("=" * 60)
    print("1. Abrir Navegador (Recomendado - evita bloqueios/checkpoints)")
    print("2. Login tradicional no Terminal (CLI)")
    escolha = input("\nEscolhe a opção [1/2] (Enter para 1): ").strip()

    if escolha == "2":
        cli_login()
    else:
        success = browser_login()
        if not success:
            print("\nA tentar método alternativo...")
            cli_login()


if __name__ == "__main__":
    main()
