"""Newsletter semanal do Notícias de Ontem via Brevo.

Três modos:
  --mapear   : interpreta (NVIDIA) a mensagem livre de temas de cada
               subscritor novo, grava as categorias no contacto e agrupa
               perfis idênticos em listas Brevo (segmentos) — o envio é
               1 campanha por PERFIL, não por pessoa.
  --enviar   : constrói 1 email minimalista por perfil único com as
               notícias publicadas da semana nas categorias do perfil
               (rank por relevância) e envia 1 campanha Brevo para a
               lista desse perfil. --seco grava HTMLs sem enviar.
  --seco     : atalho para --enviar --seco.

Configuração (.env):
  BREVO_API_KEY           — chave v3 (Settings → API keys)
  BREVO_LISTA_BASE_ID     — id da lista "Subscritores" (números)
  NEWSLETTER_REMETENTE_EMAIL / NEWSLETTER_REMETENTE_NOME
  NEWSLETTER_URL_SITE     — base pública do site (links "Ler no site")

Sem BREVO_API_KEY tudo corre em modo local (útil para testes de template).
"""

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import json as _json
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

BREVO_API = "https://api.brevo.com/v3"
ATTR_MENSAGEM = "NOTICIAS_MENSAGEM"
ATTR_CATEGORIAS = "NOTICIAS_CATEGORIAS"
PERFIL_LISTA_PREFIXO = "perfil-"
MAX_NOTICIAS_POR_EMAIL = 6
DIAS_JANELA = 7


# ---------------------------------------------------------------- utilitários

def _fold(text):
    normalized = unicodedata.normalize("NFKD", str(text or "").upper())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _headers():
    key = os.environ.get("BREVO_API_KEY", "").strip()
    if not key:
        return None
    return {"api-key": key, "Content-Type": "application/json", "Accept": "application/json"}


def _brevo_get(path, params=None):
    headers = _headers()
    if not headers:
        return None
    response = requests.get(f"{BREVO_API}{path}", headers=headers, params=params or {}, timeout=60)
    response.raise_for_status()
    return response.json()


def _brevo_post(path, payload):
    headers = _headers()
    if not headers:
        return None
    response = requests.post(f"{BREVO_API}{path}", headers=headers, json=payload, timeout=120)
    if response.status_code >= 400:
        print(f"[brevo] {path} → {response.status_code}: {response.text[:200]}")
        response.raise_for_status()
    return response.json()


def categorias_do_site():
    """Categorias existentes no site (para a IA escolher de dentro delas)."""
    data = _json.loads((ROOT / "site" / "data" / "news.json").read_text(encoding="utf-8")) if (ROOT / "site" / "data" / "news.json").exists() else {}
    categorias = set()
    for item in data.get("all", []):
        category = str(item.get("category") or "").strip()
        if category:
            categorias.add(category)
    return sorted(categorias)


# ---------------------------------------------------------------- mapear (IA)

def mapear_subscritores(dry_run=False):
    """Mensagem livre → categorias (IA) + agrupamento em listas de perfil."""
    from nvidia_client import NvidiaKeyPool, load_nvidia_api_keys

    pool = NvidiaKeyPool(load_nvidia_api_keys())
    headers = _headers()
    if not headers:
        print("BREVO_API_KEY ausente: nada a fazer no modo mapear.")
        return

    base_list = os.environ.get("BREVO_LISTA_BASE_ID", "").strip()
    contacts = []
    offset = 0
    while True:
        page = _brevo_get("/contacts", params={"limit": 100, "offset": offset})
        if not page:
            break
        batch = page.get("contacts", [])
        contacts.extend(batch)
        if len(batch) < 100 or offset > 1000:
            break
        offset += 100

    pendentes = [
        contact for contact in contacts
        if str(contact.get("attributes", {}).get(ATTR_MENSAGEM) or "").strip()
        and not str(contact.get("attributes", {}).get(ATTR_CATEGORIAS) or "").strip()
    ]
    print(f"Contactos com mensagem sem mapear: {len(pendentes)}")
    if not pendentes:
        return

    categorias_site = categorias_do_site()
    if dry_run:
        for contact in pendentes:
            print(f"  [seco] {contact.get('email')}: {contact['attributes'][ATTR_MENSAGEM][:80]}")
        return

    for contact in pendentes:
        email = contact.get("email", "")
        mensagem = str(contact["attributes"].get(ATTR_MENSAGEM) or "").strip()
        categorias = interpretar_mensagem(pool, mensagem, categorias_site)
        if not categorias:
            print(f"[mapear] {email}: IA sem categorias; fica para a próxima")
            continue
        try:
            _brevo_post(f"/contacts/{email}", {"attributes": {ATTR_CATEGORIAS: ", ".join(categorias)}})
            print(f"[mapear] {email}: {', '.join(categorias)}")
        except Exception as exc:
            print(f"[mapear] {email}: erro a gravar ({exc})")


def interpretar_mensagem(pool, mensagem, categorias_site):
    """IA: mensagem livre → lista de categorias do site (fallback por termos)."""
    if not pool.has_keys():
        return fallback_por_termos(mensagem, categorias_site)
    prompt = f"""Uma pessoa subscreveu a newsletter do site português "Notícias de Ontem"
(notícias históricas preservadas pelo Arquivo.pt, apresentadas como se fossem de hoje).

A pessoa escreveu esta mensagem a descrever o que lhe interessa:
"{mensagem.strip()}"

Escolhe, de entre as categorias disponíveis do site, as 1 a 4 que melhor correspondem
ao interesse da pessoa. Usa EXATAMENTE estas categorias (nomes com acentos como indicado):
{', '.join(categorias_site)}

Responde APENAS com JSON válido:
{{"categorias": ["...", "..."], "termos": ["palavra-chave adicional", "..."]}}

Se a mensagem for ambígua, escolhe as mais prováveis (máximo 4). Não inventes categorias."""
    try:
        response = pool.chat_json(prompt, timeout=120)
        payload = _json.loads(response or "{}")
        escolhas = [str(c).strip().upper() for c in payload.get("categorias", [])]
        validas = [c for c in categorias_site if _fold(c) in {_fold(x) for x in escolhas}]
        if validas:
            return validas
    except Exception as exc:
        print(f"[mapear] IA falhou ({exc}); fallback por termos")
    return fallback_por_termos(mensagem, categorias_site)


def fallback_por_termos(mensagem, categorias_site):
    """Sem IA: casa termos da mensagem com nomes de categorias."""
    termos = _fold(mensagem).split()
    matched = []
    for category in categorias_site:
        folded = _fold(category)
        for word in folded.replace("Ç", "C").split("-"):
            if len(word) >= 4 and word in termos:
                matched.append(category)
                break
    return matched


# ------------------------------------------------- segmentação por perfil

def perfil_hash(categorias):
    normalized = "|".join(sorted(_fold(c) for c in categorias))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]


def segmentar_perfis(contacts):
    """Agrupa contactos por perfil de categorias idêntico → {hash: [emails]}."""
    perfis = {}
    for contact in contacts:
        raw = str(contact.get("attributes", {}).get(ATTR_CATEGORIAS) or "").strip()
        if not raw:
            continue
        categorias = [c.strip() for c in raw.split(",") if c.strip()]
        if not categorias:
            continue
        perfis.setdefault(perfil_hash(categorias), {
            "categorias": categorias,
            "emails": [contact.get("email")],
        })["emails"].append(contact.get("email"))
    return perfis


def sincronizar_listas_de_perfil(perfis, dry_run=False):
    """Cria uma lista Brevo por perfil único e coloca os contactos lá."""
    headers = _headers()
    if not headers:
        print("BREVO_API_KEY ausente: segmentação saltada.")
        return perfis
    if dry_run:
        for perfil_id, perfil in perfis.items():
            print(f"  [seco] {PERFIL_LISTA_PREFIXO}{perfil_id}: {len(perfil['emails'])} contacto(s) — {', '.join(perfil['categorias'])}")
        return perfis
    existing = _brevo_get("/contacts/lists", params={"limit": 100}) or {}
    lists = {lst.get("name"): lst.get("id") for lst in existing.get("lists", [])}
    base_list = os.environ.get("BREVO_LISTA_BASE_ID", "").strip()
    for perfil_id, perfil in perfis.items():
        name = f"{PERFIL_LISTA_PREFIXO}{perfil_id}"
        list_id = lists.get(name)
        if not list_id:
            created = _brevo_post("/contacts/lists", {"name": name, "folderId": int(base_list) if base_list.isdigit() else 1})
            list_id = created.get("id")
            print(f"[segmentar] lista criada: {name} (id {list_id})")
        perfil["list_id"] = list_id
    return perfis


# ---------------------------------------------------------------- envio

def data_json():
    path = ROOT / "site" / "data" / "news.json"
    if not path.exists():
        return {}
    return _json.loads(path.read_text(encoding="utf-8"))


def noticias_da_semana():
    data = data_json()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DIAS_JANELA)).date()
    recentes = []
    for item in data.get("all", []):
        if not item.get("instagram_url") and not (item.get("network_posts") or {}):
            continue
        try:
            published = datetime.fromisoformat(str(item.get("date"))[:10]).date()
        except ValueError:
            continue
        if published >= cutoff:
            recentes.append(item)
    recentes.sort(key=lambda item: (
        item.get("relevance_level") or 5,
        str(item.get("date") or ""),
    ))
    return recentes


def selecionar_para_perfil(recentes, categorias, termos):
    wanted = {_fold(c) for c in categorias}
    termos_low = [t.lower() for t in termos or []]
    matched = []
    for item in recentes:
        category_folded = _fold(item.get("category") or "")
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if category_folded in wanted or any(term in text for term in termos_low):
            matched.append(item)
    return matched[:MAX_NOTICIAS_POR_EMAIL]


def email_html(perfil_categorias, items):
    sender_name = os.environ.get("NEWSLETTER_REMETENTE_NOME", "Notícias de Ontem")
    site_url = (os.environ.get("NEWSLETTER_URL_SITE") or "https://noticias-de-ontem.github.io/site/").rstrip("/")
    rows = []
    for item in items:
        year = str(item.get("original_year") or "")
        title = str(item.get("title") or "")
        summary = str(item.get("summary") or "")
        category = str(item.get("category") or "")
        url = str(item.get("url_path") or "")
        link = f"{site_url}/{url.lstrip('/')}" if url else site_url
        rows.append(f"""
        <tr>
          <td style="padding:0 0 22px 0;">
            <div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#0d9ba8;margin:0 0 6px;">{category} · {year}</div>
            <h3 style="margin:0 0 6px;font-size:18px;line-height:1.35;"><a href="{link}" style="color:#15181d;text-decoration:none;">{title}</a></h3>
            <p style="margin:0;font-size:14px;line-height:1.6;color:#5a6a71;">{summary}</p>
          </td>
        </tr>""")
    reconfigure_url = f"{site_url}/newsletter/?reconfigurar=1"
    return f"""<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f8f9;font-family:Montserrat,'Segoe UI',Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f8f9;padding:24px 0;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">
        <tr><td style="background:#15181d;padding:22px 28px;">
          <span style="font-size:19px;font-weight:800;color:#ffffff;">Notícias <span style="color:#00c7d6;">de Ontem</span></span>
          <div style="font-size:11px;color:#9fb0b8;margin-top:4px;">A tua seleção semanal — o mesmo dia, outros anos</div>
        </td></tr>
        <tr><td style="padding:28px 28px 8px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#0d9ba8;margin-bottom:14px;">{' · '.join(perfil_categorias)}</div>
        </td></tr>
        {''.join(rows) or '<tr><td style="padding:0 28px 20px;font-size:14px;color:#5a6a71;">Sem notícias novas esta semana nos teus temas.</td></tr>'}
        <tr><td style="padding:6px 28px 26px;">
          <a href="{reconfigure_url}" style="display:inline-block;padding:11px 20px;border:1.5px solid #00c7d6;border-radius:999px;color:#0d9ba8;font-size:13px;font-weight:700;text-decoration:none;">Não foi o que pedi — reconfigurar temas</a>
        </td></tr>
        <tr><td style="background:#f5f8f9;padding:16px 28px;border-top:1px solid #dbe4e7;">
          <div style="font-size:11px;color:#9fb0b8;line-height:1.6;">
            Dados recolhidos e contextualizados a partir do <a href="https://arquivo.pt/" style="color:#0d9ba8;">Arquivo.pt</a>.<br>
            Recebes este email porque subscreveste os temas: {', '.join(perfil_categorias)}.
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def enviar_semanal(dry_run=False):
    headers = _headers()
    contacts = []
    if headers:
        offset = 0
        while True:
            page = _brevo_get("/contacts", params={"limit": 100, "offset": offset})
            if not page:
                break
            batch = page.get("contacts", [])
            contacts.extend(batch)
            if len(batch) < 100 or offset > 1000:
                break
            offset += 100
    else:
        # Modo local: subscritor de demonstração para ver o template.
        contacts = [{"email": "exemplo@local", "attributes": {ATTR_CATEGORIAS: "CULTURA, DESPORTO"}}]

    perfis = segmentar_perfis(contacts)
    if not perfis:
        print("Sem subscritores com categorias mapeadas.")
        return
    if not dry_run:
        perfis = sincronizar_listas_de_perfil(perfis, dry_run=False)

    recentes = noticias_da_semana()
    print(f"Notícias publicadas nos últimos {DIAS_JANELA} dias: {len(recentes)}")
    if not recentes:
        # Fase de testes: sem publicações na janela, usa as notícias do site
        # mais relevantes para o template não sair vazio. Com publicações
        # regulares, este fallback deixa de disparar.
        fallback_items = [i for i in (data_json() or {}).get("all", [])]
        fallback_items.sort(key=lambda item: (item.get("relevance_level") or 5, str(item.get("date") or "")))
        recentes = fallback_items
        if recentes:
            print("Janela vazia: a usar as notícias mais relevantes do site (fase de testes).")

    out_dir = ROOT / "newsletter_previews"
    out_dir.mkdir(exist_ok=True)
    sender_email = os.environ.get("NEWSLETTER_REMETENTE_EMAIL", "").strip()
    sender_name = os.environ.get("NEWSLETTER_REMETENTE_NOME", "Notícias de Ontem")

    for perfil_id, perfil in perfis.items():
        items = selecionar_para_perfil(recentes, perfil["categorias"], [])
        html = email_html(perfil["categorias"], items)
        preview = out_dir / f"{PERFIL_LISTA_PREFIXO}{perfil_id}.html"
        preview.write_text(html, encoding="utf-8")
        total_people = len(perfil["emails"])
        if dry_run or not headers:
            print(f"[seco] {PERFIL_LISTA_PREFIXO}{perfil_id}: {len(items)} notícias para {total_people} pessoa(s) → {preview.name}")
            continue
        if not items:
            print(f"[enviar] {perfil_id}: sem notícias novas; saltado")
            continue
        if not sender_email:
            print("[enviar] NEWSLETTER_REMETENTE_EMAIL ausente; campanhas não criadas")
            return
        subject = f"Notícias de Ontem — {' · '.join(perfil['categorias'][:3])}"
        campaign = _brevo_post("/emailCampaigns", {
            "name": f"semanal-{perfil_id}-{datetime.now(timezone.utc):%Y-%m-%d}",
            "subject": subject,
            "sender": {"name": sender_name, "email": sender_email},
            "type": "classic",
            "htmlContent": html,
            "recipients": {"lists": [perfil["list_id"]]} if perfil.get("list_id") else {"excludedListIds": []},
        })
        print(f"[enviar] campanha criada para {PERFIL_LISTA_PREFIXO}{perfil_id} ({total_people} pessoa(s)): {campaign.get('id', 'id?')}")


def main():
    parser = argparse.ArgumentParser(description="Newsletter semanal do Notícias de Ontem.")
    parser.add_argument("--mapear", action="store_true", help="Interpreta mensagens de temas (IA) e segmenta perfis")
    parser.add_argument("--enviar", action="store_true", help="Constrói e envia os emails semanais por perfil")
    parser.add_argument("--seco", action="store_true", help="Pré-visualização: grava HTMLs, não envia nem altera contactos")
    args = parser.parse_args()

    if args.seco:
        enviar_semanal(dry_run=True)
        return
    if args.mapear:
        mapear_subscritores()
    if args.enviar:
        enviar_semanal()
    if not (args.mapear or args.enviar or args.seco):
        parser.print_help()


if __name__ == "__main__":
    main()
