"""Direcionamento de notícias por rede social (Instagram, Facebook, X).

Públicos (pesquisa 2026 — Investopedia/Sprout Social/Onclusive):
- Instagram: público mais jovem (18-40), visual e emocional — desporto,
  cultura, estrelas, curiosidades com boa imagem e nostalgia.
- Facebook: o mais amplo e maduro (35-65+), discussão geral — política,
  sociedade, economia, marcos nacionais e regionais.
- X: menor mas instruído e viciado em atualidade — política, economia,
  ciência/tecnologia, mundial, marcos com debate.

Acontecimentos de nível 1-2 (Marco Histórico / Grande Relevância) são
transversais às três redes — não há limitação para o que mudou a História.
"""

NETWORKS = ("instagram", "facebook", "x")

NETWORK_LABELS_PT = {
    "instagram": "Instagram",
    "facebook": "Facebook",
    "x": "X",
}
NETWORK_LABELS_EN = {
    "instagram": "Instagram",
    "facebook": "Facebook",
    "x": "X",
}

NETWORK_DEFAULT_URLS = {
    "instagram": "https://www.instagram.com/noticiasdeontempt/",
    "facebook": "https://www.facebook.com/noticiasdeontempt",
    "x": "https://x.com/",
}

# Categorias (normalizadas sem acentos, maiúsculas) preferidas por rede.
NETWORK_CATEGORY_RULES = {
    "instagram": {"DESPORTO", "CULTURA", "ESTRELA", "CURIOSO", "ENTRETENIMENTO"},
    "facebook": {"POLITICA", "SOCIEDADE", "NACIONAL", "ECONOMIA", "LOCAL"},
    "x": {"POLITICA", "ECONOMIA", "CIENCIA", "MUNDIAL", "TECNOLOGIA"},
}

NETWORK_AUDIENCE_PT = {
    "instagram": "Público jovem e visual: desporto, cultura e histórias com nostalgia.",
    "facebook": "Público amplo e maduro: política, sociedade e economia para discussão.",
    "x": "Público instruído e atualizado: política, economia, ciência e mundial.",
}
NETWORK_AUDIENCE_EN = {
    "instagram": "Young visual audience: sports, culture and nostalgic stories.",
    "facebook": "Broad mature audience: politics, society and economy for discussion.",
    "x": "Informed real-time audience: politics, economy, science and world news.",
}


def fold_category(category):
    import unicodedata

    if not category:
        return ""
    return unicodedata.normalize("NFKD", str(category).upper()).encode("ASCII", "ignore").decode()


def networks_for_option(category, level):
    """Devolve a lista de redes sociais recomendadas para a categoria e nível."""
    folded = fold_category(category)
    if level in (1, 2):
        return list(NETWORKS)
    result = []
    for network, cats in NETWORK_CATEGORY_RULES.items():
        if folded in cats:
            result.append(network)
    return result or ["instagram"]


def normalize_networks(raw, category="", level=None):
    """Normaliza a lista de redes: converte strings, filtra inválidas, fallback."""
    if isinstance(raw, str):
        import json as _json
        try:
            raw = _json.loads(raw)
        except Exception:
            raw = [raw]
    if not isinstance(raw, list):
        raw = []
    valid = [n for n in raw if n in NETWORKS]
    if not valid and category:
        valid = networks_for_option(category, level)
    return valid or ["instagram"]


def networks_prompt_rules():
    categories = ", ".join(
        f"{network}: {', '.join(sorted(cats))}"
        for network, cats in NETWORK_CATEGORY_RULES.items()
    )
    return """NETWORK TARGETING (mandatory for every option):
- Add "networks": a JSON array choosing which of our social networks this story fits: "instagram", "facebook", "x".
- Audience profiles: {categories}.
- Choose based on where the TARGET audience engages best with this specific story. Most stories belong to ONE network; two networks only when the story genuinely fits both audiences.
- ALL THREE networks are allowed ONLY for historic landmark / major event stories (relevance level 1-2) that a very wide audience cares about.
- Never choose a network whose audience has no interest in the story."""


# ---------------------------------------------------------------------------
# CTAs canónicas por plataforma e idioma
# ---------------------------------------------------------------------------
_SOCIAL_CTA_MAP = {
    ("instagram", "pt"): "🔗 Lê a notícia completa no link da bio.",
    ("instagram", "en"): "🔗 Read the full story at the link in bio.",
    ("facebook", "pt"): "🔗 Lê a notícia completa no site no sobre do perfil.",
    ("facebook", "en"): "🔗 Read the full story on the website in the profile's About section.",
    ("x", "pt"): "🔗 Lê a notícia completa no link.",
    ("x", "en"): "🔗 Read the full story at the link.",
}


def social_link_cta(platform: str = "instagram", lang: str = "pt") -> str:
    """Devolve a CTA canónica para a plataforma e idioma indicados."""
    return _SOCIAL_CTA_MAP.get((platform.lower(), lang.lower()), "")


def replace_social_cta(caption: str, platform: str, lang: str) -> str:
    """Remove qualquer CTA existente do caption e adiciona a CTA canónica."""
    import re
    _strip = re.compile(r"🔗\s*(?:Lê|Le|Read|See|via)\s+[^\n]{0,140}", re.IGNORECASE)
    cleaned = _strip.sub("", caption or "").strip()
    cta = social_link_cta(platform=platform, lang=lang)
    return f"{cleaned}\n\n{cta}".strip() if cta else cleaned


# ---------------------------------------------------------------------------
# Tradução de categorias PT -> EN (uppercase para consistência)
# ---------------------------------------------------------------------------
_CATEGORY_EN_MAP = {
    "POLITICA": "POLITICS",
    "ECONOMIA": "ECONOMY",
    "SOCIEDADE": "SOCIETY",
    "DESPORTO": "SPORTS",
    "CULTURA": "CULTURE",
    "EDUCACAO": "EDUCATION",
    "SAUDE": "HEALTH",
    "CIENCIA": "SCIENCE",
    "TECNOLOGIA": "TECHNOLOGY",
    "MUNDO": "WORLD",
    "MUNDIAL": "WORLD",
    "NACIONAL": "NATIONAL",
    "LOCAL": "LOCAL",
    "INTERESSE PUBLICO": "PUBLIC INTEREST",
    "ENTRETENIMENTO": "ENTERTAINMENT",
    "ESTRELA": "CELEBRITIES",
    "CURIOSO": "CURIOSITIES",
    "AMBIENTE": "ENVIRONMENT",
    "JUSTICA": "JUSTICE",
    "CRIME": "CRIME",
    "INTERNACIONAL": "INTERNATIONAL",
    "HISTORIA": "HISTORY",
}


def translate_category_to_en(category: str) -> str:
    """Traduz uma categoria PT para EN (uppercase). Devolve a original se não encontrar."""
    if not category:
        return ""
    folded = fold_category(category)
    return _CATEGORY_EN_MAP.get(folded, category.upper())
