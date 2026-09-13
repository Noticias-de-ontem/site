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
    "instagram": "https://www.instagram.com/",
    "facebook": "https://www.facebook.com/",
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

    text = str(category or "").upper().strip()
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def networks_for_option(category, level):
    """Redes adequadas por categoria e nível (regra local, sem IA)."""
    folded = fold_category(category)
    level = int(level) if level else 4
    if level in (1, 2):
        return list(NETWORKS)
    networks = [
        network
        for network in NETWORKS
        if folded in NETWORK_CATEGORY_RULES[network]
    ]
    return networks or ["instagram"]


def normalize_networks(raw, category="", level=None):
    """Normaliza a lista de redes devolvida pela IA com fallback por regra."""
    fallback = networks_for_option(category, level)
    if not isinstance(raw, (list, tuple)):
        return fallback
    cleaned = []
    for entry in raw:
        network = str(entry or "").strip().lower()
        if network in NETWORKS and network not in cleaned:
            cleaned.append(network)
    return cleaned or fallback


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
