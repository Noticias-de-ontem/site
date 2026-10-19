"""Vigia da geração: mantém a geração e o servidor vivos por N horas.

Corre popular_site.py (retomável) em ciclo contínuo; se o processo sair
(quota, rede, erro), reinicia ao fim de 60s. Reinicia também o servidor
local se a porta 8080 deixar de responder. Ao fim do prazo, termina.

Uso: python scripts/vigia_geracao.py [--horas 5]
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "vigia_geracao.log"
PORT = 8080


def log(message):
    line = f"[{datetime.now():%H:%M:%S}] {message}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def server_healthy():
    try:
        import requests

        response = requests.get(f"http://127.0.0.1:{PORT}/inicio/", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def ensure_server():
    if server_healthy():
        return
    log("servidor fora do ar; a reiniciar http.server")
    subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--directory", str(ROOT / "site")],
        cwd=str(ROOT),
    )
    time.sleep(3)
    log(f"servidor reiniciado: {'OK' if server_healthy() else 'AINDA FORA'}")


def progresso():
    try:
        posts = json.loads((ROOT / "pending_posts.json").read_text(encoding="utf-8"))
        dias = {}
        for post in posts:
            dias.setdefault(post.get("date"), []).append(post.get("slot"))
        completos = sum(1 for slots in dias.values() if 1 in slots and 2 in slots)
        return len(posts), completos
    except Exception:
        return "?", "?"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horas", type=float, default=48.0)
    args = parser.parse_args()

    deadline = time.time() + args.horas * 3600
    log(f"vigia iniciado por {args.horas} horas (até {datetime.fromtimestamp(deadline):%H:%M})")
    ensure_server()

    round_number = 0
    while time.time() < deadline:
        round_number += 1
        remaining_min = round((deadline - time.time()) / 60)
        posts, completos = progresso()
        log(f" ciclo {round_number}: a lançar geração (restam {remaining_min} min; posts {posts}, dias completos {completos})")
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", str(ROOT / "popular_site.py"),
                 "--tudo-ano", "--source-mode", "arquivo-first", "--limite", "0"],
                cwd=str(ROOT),
            )
            # Aguardar pelo fim do processo ou pelo prazo, o que chegar primeiro.
            while process.poll() is None and time.time() < deadline:
                time.sleep(30)
            if process.poll() is None:
                log(" prazo atingido com a geração a correr; a aguardar terminar o dia em curso")
                try:
                    process.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    process.kill()
                    log(" geração terminada à força (dia em curso era longo demais)")
            if time.time() >= deadline:
                break
            posts, completos = progresso()
            log(f" ciclo {round_number}: geração saiu (código {process.returncode}); posts {posts}, dias completos {completos}")
            try:
                subprocess.run([sys.executable, str(ROOT / "build_site.py")], cwd=str(ROOT), timeout=120)
                log(" site reconstruído com sucesso após ciclo de geração")
            except Exception as b_exc:
                log(f" aviso ao reconstruir site: {b_exc}")
            ensure_server()
            time.sleep(60)
        except Exception as exc:
            log(f" erro no ciclo {round_number}: {exc}")
            time.sleep(120)

    posts, completos = progresso()
    log(f"VIGIA TERMINADO. Estado final: {posts} posts, {completos}/365 dias completos.")
    print(f"VIGIA TERMINADO. Estado final: {posts} posts, {completos}/365 dias completos.")


if __name__ == "__main__":
    main()
