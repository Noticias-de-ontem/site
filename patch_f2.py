"""Patch F2: URLs por categoria, dedupe, botão fonte original."""
from pathlib import Path
import ast

p = Path("build_site.py")
text = p.read_text(encoding="utf-8")

# 1. news_url_path: /{categoria}/{6 palavras}/ com colisão por +palavras
old = '''    page_id = clean_text(item.get("page_id")) or news_page_id(item)
    digest8 = page_id.replace("noticia-", "")[:8]
    date_match = re.match(r"^(\\d{4})-(\\d{2})-(\\d{2})", clean_text(item.get("date")))
    year, month, day = date_match.groups() if date_match else ("0000", "00", "00")
    title_slug = re.sub(r"[^a-z0-9-]+", "-", _fold_to_ascii(item.get("title") or "")).strip("-")
    title_slug = re.sub(r"-{2,}", "-", title_slug)[:90].strip("-") or "noticia"
    return f"noticia/{year}/{month}/{day}/{title_slug}-{digest8}"'''
new = '''    category_slug = re.sub(
        r"[^a-z0-9-]+", "-",
        _fold_to_ascii(item.get("category") or "atualidade"),
    ).strip("-").lower() or "atualidade"
    title_slug = re.sub(r"[^a-z0-9-]+", "-", _fold_to_ascii(item.get("title") or "")).strip("-")
    title_slug = re.sub(r"-{2,}", "-", title_slug).strip("-") or "noticia"
    words = title_slug.split("-")
    base = "-".join(words[:6])
    path = f"noticia/{category_slug}/{base}"
    if taken_paths is not None:
        candidate = path
        word_count = min(6, len(words))
        while candidate in taken_paths and word_count < len(words):
            word_count += 1
            candidate = f"noticia/{category_slug}/{'-'.join(words[:word_count])}"
        if candidate in taken_paths:
            candidate = f"{path}-{page_id[:8]}"
        taken_paths.add(candidate)
        return candidate
    return path'''
assert old in text, "news_url_path body missing"
text = text.replace(old, new, 1)

# 2. assinatura com taken_paths
old2 = "def news_url_path(item):"
new2 = "def news_url_path(item, taken_paths=None):"
assert old2 in text
text = text.replace(old2, new2, 1)

# 3. taken_paths preenchido no loop de escrita
old3 = '''    alias_shell = build_story_shell(source_html, "../../")
    for item in payload.get("all", []):'''
new3 = '''    alias_shell = build_story_shell(source_html, "../../")
    taken_urls = set()
    for item in payload.get("all", []):
        if clean_text(item.get("url_path")):
            taken_urls.add(clean_text(item.get("url_path")))'''
assert old3 in text, "taken_urls anchor missing"
text = text.replace(old3, new3, 1)

# 4. dedupe por título: mantém o com âncora wayback
old4 = '''    items = []
    for post in pending_posts if isinstance(pending_posts, list) else []:
        item = post_to_site_item(post, registry_by_post_id)
        if item:
            items.append(item)
'''
new4 = '''    items = []
    seen_titles_build = {}
    for post in pending_posts if isinstance(pending_posts, list) else []:
        item = post_to_site_item(post, registry_by_post_id)
        if not item:
            continue
        title_key = re.sub(r"[^a-z0-9]", "", _fold_to_ascii(item.get("title") or "").lower())[:80]
        if title_key and title_key in seen_titles_build:
            existing = seen_titles_build[title_key]
            item_anchored = "/wayback/" in str(item.get("source_url") or "")
            existing_anchored = "/wayback/" in str(existing.get("source_url") or "")
            if item_anchored and not existing_anchored:
                items[items.index(existing)] = item
                seen_titles_build[title_key] = item
            continue
        if title_key:
            seen_titles_build[title_key] = item
        items.append(item)
'''
assert old4 in text, "items loop anchor missing"
text = text.replace(old4, new4, 1)

# 5. latest exclui carrossel
old5 = '"latest": published[:12] if published else public_items[:12],'
new5 = '"latest": [item for item in (published[:12] if published else public_items[:12]) if item not in carousel_items],'
assert old5 in text, "latest anchor missing"
text = text.replace(old5, new5, 1)

# 6. botão fonte original vs arquivo.pt
old6 = "newsOpenArquivo"
# esta mudança é no app.js, não aqui

# 7. sitemap: URLs por data de publicação para o ano correto
# (o sitemap global mantém-se, mas agora usa os urls_path corretos)
p.write_text(text, encoding="utf-8")
ast.parse(text)
print("F2 build_site OK")

# 7b. app.js: botão "Abrir na fonte original" quando não é arquivo.pt
p2 = Path("site/app.js")
text2 = p2.read_text(encoding="utf-8")
old7 = 'escapeHtml(t("newsOpenArquivo"))}'
new7 = 'escapeHtml((item.source_url || "").includes("arquivo.pt") ? t("newsOpenArquivo") : (state.lang === "pt" ? "Abrir na fonte original" : "Open original source"))}'
# não vou substituir globalmente porque o texto aparece em vários contextos
# vou apenas no renderNewsDetail (primeira ocorrência no bloco de ações)
count = text2.count(old7)
if count > 0:
    # substitui apenas no bloco news-article-actions (primeira ocorrência do botão secundário)
    idx = text2.find('item.source_url ? `<a class="button secondary" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("newsOpenArquivo"))}</a>`')
    if idx > 0:
        text2 = text2[:idx] + 'item.source_url ? `<a class="button secondary" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml((item.source_url || "").includes("arquivo.pt") ? t("newsOpenArquivo") : (state.lang === "pt" ? "Abrir na fonte original" : "Open original source"))}</a>`' + text2[idx + len('item.source_url ? `<a class="button secondary" href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(t("newsOpenArquivo"))}</a>`'):]
        print("botão fonte original OK")
p2.write_text(text2, encoding="utf-8")
print("F2 completo")
