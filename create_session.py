import instaloader
import os

def create_session():
    print("--- GERADOR DE SESSÃO DO INSTALOADER ---")
    print("Este script vai iniciar sessão na tua conta e guardar os cookies de acesso.")
    print("Assim, o GitHub Actions poderá usar a tua conta sem disparar alertas de segurança (Checkpoints).")

    username = input("Username do Instagram: ")

    L = instaloader.Instaloader()

    try:

        L.interactive_login(username)


        session_file = "instaloader.session"
        L.save_session_to_file(session_file)

        print(f"\n✅ SUCESSO! A sessão foi guardada no ficheiro '{session_file}'.")
        print("\nPara usar no GitHub Actions:")
        print("1. Abre o terminal nesta pasta e corre o seguinte comando para converter o ficheiro para texto (Base64):")
        print("   Windows (PowerShell): [convert]::ToBase64String([IO.File]::ReadAllBytes('instaloader.session'))")
        print("   Mac: base64 -i instaloader.session | tr -d '\\n'")
        print("   Linux: base64 -w 0 instaloader.session")
        print("2. Copia todo o texto gerado.")
        print("3. No GitHub, vai a Settings -> Secrets and variables -> Actions.")
        print("4. Cria um novo Secret com o nome INSTA_SESSION_BASE64 e cola o texto lá dentro.")

    except instaloader.exceptions.TwoFactorAuthRequiredException:
        print("\n⚠️ A tua conta tem Autenticação de 2 Fatores ativa.")
        print("O instaloader deverá ter-te pedido o código acima. Se falhou, tenta correr este script novamente.")
    except Exception as e:
        print(f"\n❌ Erro ao criar a sessão: {e}")

if __name__ == "__main__":
    create_session()
