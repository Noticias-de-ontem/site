"""Descarrega as logos das fontes para site/assets/logos/ (uma vez)."""

import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "assets" / "logos"

# handle/domínio -> domínio para favicon
SOURCES = {
    "arquivo.pt": "arquivo.pt",
    "record.pt": "record.pt",
    "ojogo.pt": "ojogo.pt",
    "abola.pt": "abola.pt",
    "caras.pt": "caras.pt",
    "flash.pt": "flash.pt",
    "tv7dias.pt": "tv7dias.pt",
    "holofote.pt": "holofote.pt",
    "selfie.iol.pt": "selfie.iol.pt",
    "lux.iol.pt": "lux.iol.pt",
    "timeout.pt": "timeout.pt",
    "blitz.pt": "blitz.pt",
    "mag.sapo.pt": "mag.sapo.pt",
    "exameinformatica.pt": "exameinformatica.pt",
    "activa.pt": "activa.pt",
    "maxima.pt": "maxima.pt",
    "sapo24": "24sapo.com",
    "publico.pt": "publico.pt",
    "sicnoticias.pt": "sicnoticias.pt",
    "cnnportugal.pt": "cnnportugal.iol.pt",
    "rtp.pt": "rtp.pt",
    "cmjornal.pt": "cmjornal.pt",
    "observador.pt": "observador.pt",
    "dn.pt": "dn.pt",
    "jn.pt": "jn.pt",
    "expresso.pt": "expresso.pt",
    "sabado.pt": "sabado.pt",
    "visao.pt": "visao.pt",
    "noticiasaominuto.com": "noticiasaominuto.com",
    "renascenca": "renascenca.pt",
    "4gnewspt": "4gnews.pt",
    "nit.pt": "nit.pt",
    "wikipedia": "wikipedia.org",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}


def fetch_google_favicon(domain):
    url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
    response = requests.get(url, headers=HEADERS, timeout=25)
    if response.status_code == 200 and response.content[:4] != b"<htm":
        return response.content
    return b""


def fetch_touch_icon(domain):
    for path in ("apple-touch-icon.png", "apple-touch-icon-precomposed.png"):
        try:
            response = requests.get(f"https://{domain}/{path}", headers=HEADERS, timeout=20)
            if response.status_code == 200 and response.headers.get("content-type", "").startswith("image"):
                return response.content
        except requests.RequestException:
            continue
    return b""


IG_PROFILES = ["epahsaiu", "hojenomundomilitar", "revista_nit", "revistaoriana"]


def fetch_ig_profile_pics():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "x-ig-app-id": "936619743392459",
    }
    for handle in IG_PROFILES:
        target = OUT / f"ig-{handle}.jpg"
        if target.exists() and target.stat().st_size > 800:
            continue
        try:
            r = requests.get(
                f"https://www.instagram.com/api/v1/users/web_profile_info/?username={handle}",
                headers=headers,
                timeout=20,
            )
            if r.status_code == 200:
                url = r.json().get("data", {}).get("user", {}).get("profile_pic_url_hd") or r.json().get("data", {}).get("user", {}).get("profile_pic_url")
                if url:
                    pic = requests.get(url, timeout=20)
                    if pic.status_code == 200:
                        target.write_bytes(pic.content)
                        print("IG pic ok:", handle)
                        continue
        except requests.RequestException as exc:
            print("IG pic falhou:", handle, str(exc)[:60])
        print("IG pic sem foto:", handle)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fetch_ig_profile_pics()
    report = {}
    for name, domain in SOURCES.items():
        target = OUT / f"{name}.png"
        if target.exists() and target.stat().st_size > 800:
            report[name] = "já existia"
            continue
        content = b""
        try:
            content = fetch_touch_icon(domain) or fetch_google_favicon(domain)
        except requests.RequestException as exc:
            report[name] = f"erro: {exc}"
        if content:
            target.write_bytes(content)
            report[name] = f"ok ({len(content) // 1024} KB)"
        else:
            report[name] = "SEM LOGO"
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
