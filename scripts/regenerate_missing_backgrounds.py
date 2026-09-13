"""Regenera a foto de fundo dos posts sem background, validada pela Gemini.

Para cada post indicado, pesquisa uma nova fotografia (mesma cascata do
projeto: Wikimedia -> Arquivo.pt -> Wikipedia -> Openverse), pede à Gemini a
análise de enquadramento e só aceita fotos sem texto dominante que funcionem
no banner largo e no cartão 4:5. Grava em images/backgrounds/<stem>-fundo.jpg
e atualiza local_background_path/background_source_url da option selecionada.

Uso: python regenerate_missing_backgrounds.py [post_id ...]
Sem argumentos processa todos os posts selecionados sem local_background_path.
"""

import json
import sys
import tempfile
from pathlib import Path

from post_templates import (
    TARGET_SIZE,
    _build_background_search_query,
    fetch_background_image,
)
from gemini_vision import GeminiUnavailableError, analyze_photo

ROOT = Path(__file__).resolve().parents[1]
PENDING_FILE = ROOT / "pending_posts.json"

# Consultas curtas de reserva: pesquisas de imagem funcionam melhor com
# 2-4 palavras temáticas do que com o título completo da notícia.
FALLBACK_QUERIES = {
    "pt_2026-07-01_2": [
        "Amália Rodrigues",
        "guitarra portuguesa fado",
        "Museu do Fado Lisboa",
        "Amália Rodrigues estátua Alfama",
    ],
    "pt_2026-07-02_2": ["PSP Polícia Segurança Pública", "polícia Portugal", "PSP"],
    "pt_2026-08-26_1": [
        "Provedoria de Justiça Lisboa",
        "Assembleia da República Lisboa",
        "João Cotrim Figueiredo",
        "manifestação Lisboa 2021",
    ],
    "pt_2026-08-28_2": [
        "Teatro Politeama Lisboa",
        "Coliseu dos Recreios Lisboa",
        "Teatro Eden Lisboa",
        "Rua Portas Santo Antão Lisboa",
        "Avenida da Liberdade Lisboa",
    ],
}

def evaluate(source_path, title="", theme=""):
    """Devolve (aceite, banner_ok, analise, motivo).

    Aceitação: foto ilustrável na CAPA 4:5 (o que os cartões mostram) e
    relevante para a notícia — o veredicto de banner só reforça
    banner_ok, usado pelo build para a prioridade no carrossel. Assim,
    notícias fora do destaque podem usar retratos verticais (ex.: Amália
    de corpo inteiro) que nunca dariam bom banner.
    """
    try:
        analysis = analyze_photo(source_path, news_title=f"{title} {theme}".strip())
    except GeminiUnavailableError:
        return True, False, None, "gemini indisponivel"
    if not analysis:
        return True, False, None, "sem analise"
    cover_ok = not analysis.get("embedded_text") and analysis.get("cover_suitable")
    if not cover_ok:
        return False, False, analysis, analysis.get("reason", "")
    if not analysis.get("relevant", True):
        return False, False, analysis, f"fora de tema: {analysis.get('subject', '')}"
    banner_ok = bool(analysis.get("banner_suitable"))
    return True, banner_ok, analysis, analysis.get("reason", "")


def main():
    wanted = set(sys.argv[1:])
    posts = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    changed = 0
    for post in posts:
        post_id = post.get("id", "")
        if wanted and post_id not in wanted:
            continue
        options = post.get("options") or []
        try:
            idx = int(post.get("selected_option", 0) or 0)
        except (TypeError, ValueError):
            idx = 0
        if not options or not (0 <= idx < len(options)):
            continue
        option = options[idx]
        if option.get("local_background_path"):
            continue
        title = option.get("title") or ""
        theme = option.get("image_theme") or option.get("theme_suggestion") or ""
        category = option.get("category") or ""
        year = str(option.get("year") or "")
        stem = Path(option.get("local_image_path", "")).stem or post_id.replace(":", "-")
        stem = f"{stem}-fundo.jpg"

        queries = []
        for candidate in (
            _build_background_search_query(title, f"{theme} {year}".strip(), category),
            _build_background_search_query(title, "", ""),
            " ".join(f"{title} {year}".split()),
            *FALLBACK_QUERIES.get(post_id, []),
        ):
            if candidate and candidate not in queries:
                queries.append(candidate)

        chosen = None
        for query in queries:
            print(f"\n== {post_id}: a pesquisar '{query}'", flush=True)
            try:
                image, source_url = fetch_background_image(query, "pt", target_size=TARGET_SIZE)
            except Exception as exc:
                print(f"   pesquisa falhou: {exc}", flush=True)
                continue
            if image is None:
                print("   sem resultados utilizáveis", flush=True)
                continue
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
                temp_path = handle.name
            image.convert("RGB").save(temp_path, quality=92)
            ok, banner_ok, analysis, motive = evaluate(temp_path, title, theme)
            if ok:
                chosen = (temp_path, source_url)
                if analysis is None:
                    print("   Gemini indisponível; aceite pelos filtros locais (não validada)", flush=True)
                else:
                    print(f"   aceite ({'banner+capa' if banner_ok else 'capa'}): {motive}", flush=True)
                break
            print(f"   rejeitada: {motive}", flush=True)

        if not chosen:
            print(f"!! {post_id}: nenhuma foto aceite; fica para revisão manual", flush=True)
            continue

        target = ROOT / "images" / "backgrounds" / stem
        target.parent.mkdir(parents=True, exist_ok=True)
        Path(chosen[0]).replace(target)
        option["local_background_path"] = str(target).replace("\\", "/")
        option["background_source_url"] = chosen[1] or ""
        changed += 1
        print(f"++ {post_id}: fundo novo guardado -> {target.name}", flush=True)

    if changed:
        PENDING_FILE.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nConcluído: {changed} post(s) atualizado(s).")


if __name__ == "__main__":
    main()
