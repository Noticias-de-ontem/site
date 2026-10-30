#!/usr/bin/env python3
"""Espelha as imagens dos posts APROVADOS no proprio site.

Porque existe: o publicador, na hora de publicar, sacava a imagem aprovada
do ImgBB (i.ibb.co) e o runner do GitHub esgotava o timeout — duas noites
seguidas (29 e 30 out 2026) o slot da noite perdeu-se por isso, apesar do
retry de 30 s x 3. A partir daqui a imagem aprovada vive no site
(https://www.noticiasdeontem.pt/images/approved/<post-id>.<ext>) e o
`image_url` do post passa a apontar para la. O publicador nunca mais depende
de um servidor externo na hora de publicar.

Quando corre: workflow `mirror_approved_images.yml` — a cada push que toque
em `pending_posts.json` (ou seja, logo a seguir a uma aprovacao), de 6 em 6
horas como rede de seguranca, ou manualmente. So mexe em posts com
`status == "approved"` e com `image_url` externo (http/https); posts
pendentes, rejeitados ou ja publicados nao sao tocados, e um `image_url` que
ja aponte para o site e deixado como esta.

Isto NAO faz a noticia aparecer no site antes de ser publicada: o
`build_site.py` so inclui no site os posts com `status == "published"`
(o filtro esta em `build_payload()`); um post aprovado continua de fora do
`news.json`, do carrossel, das rotas e do sitemap. O ficheiro da imagem
passa a existir no site, mas nada aponta para ele ate a publicacao.

Falhas: se o download de uma imagem falhar apos as tentativas, o `image_url`
fica como estava (o publicador mantem o comportamento antigo para esse post)
e o erro fica no log; a proxima corrida volta a tentar. O script sai sempre
com 0 quando correu ate ao fim, para uma imagem instavel nao falhar a run.
"""

import json
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PENDING_POSTS = os.path.join(ROOT, "pending_posts.json")
MIRROR_DIR = os.path.join(ROOT, "site", "images", "approved")
SITE_ORIGIN = "https://www.noticiasdeontem.pt"

TIMEOUT = 60
RETRIES = 3
RETRY_WAIT = 10

# O Wikimedia Commons (upload.wikimedia.org) recusa pedidos sem User-Agent
# descritivo (403); o ImgBB tambem agradece um UA real. Sem isto, as imagens
# da Wikimedia falham sempre.
HEADERS = {
    "User-Agent": "Noticias-de-Ontem/1.0 (espelho de imagens aprovadas; https://www.noticiasdeontem.pt)"
}

# magic bytes -> extensao
MAGIC = [
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
]


def sniff_extension(data, content_type=""):
    for magic, ext in MAGIC:
        if data.startswith(magic):
            return ext
    if data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if "png" in content_type:
        return "png"
    if "webp" in content_type:
        return "webp"
    if "gif" in content_type:
        return "gif"
    return "jpg"


def download_image(url):
    """Saca a imagem com retry (mesma politica do publisher). Devolve bytes ou None."""
    last_exc = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
            if resp.status_code == 200 and resp.content:
                ctype = resp.headers.get("content-type", "")
                if "image" not in ctype and not any(
                    resp.content.startswith(m) for m, _ in MAGIC
                ) and resp.content[0:4] != b"RIFF":
                    print(f"  ERRO: {url} devolveu content-type inesperado: {ctype}")
                    return None
                return resp.content
            print(f"  tentativa {attempt}/{RETRIES}: HTTP {resp.status_code} em {url}")
        except Exception as exc:  # noqa: BLE001 - registar e voltar a tentar
            last_exc = exc
            print(f"  tentativa {attempt}/{RETRIES}: excecao em {url}: {exc}")
        if attempt < RETRIES:
            time.sleep(RETRY_WAIT)
    if last_exc is not None:
        print(f"  ERRO final: {url}: {last_exc}")
    return None


def main():
    with open(PENDING_POSTS, "r", encoding="utf-8") as f:
        raw = f.read()
    posts = json.loads(raw)

    mirrored = 0
    already = 0
    skipped = 0
    failed = 0
    new_raw = raw

    for entry in posts:
        if entry.get("status") != "approved":
            continue
        post_id = entry.get("id") or ""
        options = entry.get("options") or []
        sel = entry.get("selected_option", 0)
        if not options or sel >= len(options):
            print(f"{post_id}: sem opcao selecionada valida, a saltar")
            skipped += 1
            continue
        option = options[sel]
        image_url = (option.get("image_url") or "").strip()
        if not image_url:
            print(f"{post_id}: sem image_url, a saltar (nada para espelhar)")
            skipped += 1
            continue
        if image_url.startswith(SITE_ORIGIN + "/"):
            already += 1
            continue
        if not image_url.lower().startswith(("http://", "https://")):
            print(f"{post_id}: image_url nao e URL externo ({image_url}), a saltar")
            skipped += 1
            continue
        print(f"{post_id}: a espelhar {image_url[:100]}")
        data = download_image(image_url)
        if data is None:
            print(f"{post_id}: FALHOU o download, image_url fica como estava")
            failed += 1
            continue
        ext = sniff_extension(data)
        filename = f"{post_id}.{ext}"
        mirror_url = f"{SITE_ORIGIN}/images/approved/{filename}"
        if new_raw.count(image_url) != 1:
            print(
                f"{post_id}: URL aparece {new_raw.count(image_url)} vezes em "
                "pending_posts.json, a saltar por seguranca"
            )
            failed += 1
            continue
        os.makedirs(MIRROR_DIR, exist_ok=True)
        with open(os.path.join(MIRROR_DIR, filename), "wb") as f:
            f.write(data)
        new_raw = new_raw.replace(image_url, mirror_url)
        print(f"{post_id}: espelhado ({len(data)} bytes) -> {mirror_url}")
        mirrored += 1

    if mirrored:
        with open(PENDING_POSTS, "w", encoding="utf-8") as f:
            f.write(new_raw)
    print(
        f"Resumo: {mirrored} espelhadas, {already} ja estavam no site, "
        f"{skipped} sem imagem para espelhar, {failed} falhadas"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
