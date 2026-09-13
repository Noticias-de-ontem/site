"""Classificação de relevância histórica partilhada por pré-geração e site.

Cinco níveis determinados por PONTUAÇÃO ponderada (a IA propõe as notas; o
nível é sempre recalculado em código — a IA nunca decide o nível sozinha):

- 1 Marco Histórico — mudança estrutural e duradoura na História.
- 2 Grande Relevância — consequências nacionais/internacionais muito
  significativas sem ser necessariamente ponto de viragem.
- 3 Relevância Regional — impacto forte numa região/comunidade.
- 4 Interesse Público — grande atenção pública, impacto duradouro limitado.
- 5 Contexto Histórico — útil para compreender a época, sem importância própria.

Critérios e pesos (a relevância mediática nunca determina o nível):
impacto histórico 30% · dimensão do impacto 20% · consequências 15% ·
relevância posterior 15% · dimensão/duração 10% · relevância mediática 5% ·
singularidade 5%.
"""

WEIGHTS = {
    "impacto_historico": 0.30,
    "dimensao_impacto": 0.20,
    "consequencias": 0.15,
    "relevancia_posterior": 0.15,
    "dimensao_duracao": 0.10,
    "relevancia_mediatica": 0.05,
    "singularidade": 0.05,
}

SCORE_KEYS = list(WEIGHTS)

# Nível 1 exige notas altas nos critérios substantivos e uma justificação
# explícita sobre consequências posteriores.
LEVEL1_MIN_TOP_SCORES = 90
LEVEL1_JUSTIFICATION_KEYWORDS = (
    "consequ",
    "duradour",
    "mudou",
    "alterou",
    "levou",
    "estrutur",
    "influenc",
    "abriu",
    "origina",
    "iniciou",
    "marcou o início",
    "ponto de viragem",
    "ponto de virada",
)

# Limiar de downvote: o texto da justificação tem de ter substância mínima.
LEVEL1_MIN_JUSTIFICATION_CHARS = 60

LEVEL_NAMES_PT = {
    1: "Marco Histórico",
    2: "Grande Relevância",
    3: "Relevância Regional",
    4: "Interesse Público",
    5: "Contexto Histórico",
}

LEVEL_NAMES_EN = {
    1: "Historic Landmark",
    2: "Major Event",
    3: "Regional Relevance",
    4: "Public Interest",
    5: "Historical Context",
}

# Resumo curto para a tooltip do site (PT e EN americano natural).
LEVEL_TOOLTIPS_PT = {
    1: "Acontecimento que mudou o rumo da História, com consequências estruturais e duradouras.",
    2: "Grande impacto nacional ou internacional, sem ser necessariamente um ponto de viragem histórico.",
    3: "Importância especialmente forte para uma região, país ou comunidade.",
    4: "Grande atenção pública na época, com impacto histórico de longo prazo limitado.",
    5: "Não foi determinante por si, mas ajuda a compreender a época e outros acontecimentos.",
}

LEVEL_TOOLTIPS_EN = {
    1: "An event that changed the course of history, with lasting, structural consequences.",
    2: "Major national or international impact, though not necessarily a turning point.",
    3: "Especially significant for a specific region, country, or community.",
    4: "Drew major public attention at the time, with limited long-term historical impact.",
    5: "Not decisive on its own, but useful for understanding the era and later events.",
}

# Rótulos curtos para os templates de Instagram (maiúsculas, cabem no pill).
LEVEL_SHORT_PT = {
    1: "MARCO HISTÓRICO",
    2: "GRANDE RELEVÂNCIA",
    3: "RELEVÂNCIA REGIONAL",
    4: "INTERESSE PÚBLICO",
    5: "CONTEXTO HISTÓRICO",
}

LEVEL_SHORT_EN = {
    1: "HISTORIC LANDMARK",
    2: "MAJOR EVENT",
    3: "REGIONAL RELEVANCE",
    4: "PUBLIC INTEREST",
    5: "HISTORICAL CONTEXT",
}

# Cores base dos pills (usadas nos templates de imagem; o site usa classes CSS).
LEVEL_COLORS = {
    1: ((168, 32, 60), (255, 255, 255)),      # carmesim, texto branco
    2: ((214, 106, 21), (255, 255, 255)),     # laranja, texto branco
    3: ((196, 148, 12), (24, 24, 24)),        # âmbar, texto escuro
    4: ((17, 96, 155), (255, 255, 255)),      # azul, texto branco
    5: ((86, 98, 106), (255, 255, 255)),      # cinza-azulado, texto branco
}

DEFAULT_LEVEL = 4


def _clamp_score(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score != score:  # NaN
        return None
    return max(0.0, min(100.0, score))


def weighted_score(scores):
    total = 0.0
    for key, weight in WEIGHTS.items():
        score = _clamp_score(scores.get(key))
        if score is None:
            continue
        total += score * weight
    return round(total, 1)


def level_from_score(weighted):
    if weighted >= 85:
        return 1
    if weighted >= 70:
        return 2
    if weighted >= 55:
        return 3
    if weighted >= 40:
        return 4
    return 5


def _justification_mentions_consequences(text):
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in LEVEL1_JUSTIFICATION_KEYWORDS)


def normalize_relevance(raw, lang="pt"):
    """Normaliza o bloco `relevance` da IA e devolve o dicionário final.

    O nível é derivado da pontuação ponderada; o proposto pela IA é ignorado.
    Nível 1 só se mantém com notas ≥90 nos quatro critérios substantivos e
    justificação explícita de consequências duradouras — caso contrário
    degrada para nível 2.
    """
    raw = raw if isinstance(raw, dict) else {}
    scores = {}
    for key in SCORE_KEYS:
        score = _clamp_score(raw.get(key))
        if score is None:
            score = _clamp_score((raw.get("scores") or {}).get(key))
        if score is None:
            return None
        scores[key] = score
    justification = str(raw.get("justification") or raw.get("justificacao") or "").strip()
    if not justification:
        return None

    weighted = weighted_score(scores)
    level = level_from_score(weighted)
    if level == 1:
        top_four_ok = all(
            (scores.get(key) or 0) >= LEVEL1_MIN_TOP_SCORES
            for key in ("impacto_historico", "dimensao_impacto", "consequencias", "relevancia_posterior")
        )
        justification_ok = (
            len(justification) >= LEVEL1_MIN_JUSTIFICATION_CHARS
            and _justification_mentions_consequences(justification)
        )
        if not (top_four_ok and justification_ok):
            level = 2
    return {
        "level": level,
        "scores": scores,
        "weighted_score": weighted,
        "justification": justification[:400],
        "lang": lang,
    }


def default_relevance():
    """Segurança para itens antigos sem pontuação: nível 4 sem scores."""
    return {
        "level": DEFAULT_LEVEL,
        "scores": {},
        "weighted_score": None,
        "justification": "",
        "lang": "",
    }


def level_name(level, lang="pt"):
    table = LEVEL_NAMES_EN if lang == "en" else LEVEL_NAMES_PT
    return table.get(int(level) if level else DEFAULT_LEVEL, "")


def level_tooltip(level, lang="pt"):
    table = LEVEL_TOOLTIPS_EN if lang == "en" else LEVEL_TOOLTIPS_PT
    return table.get(int(level) if level else DEFAULT_LEVEL, "")


def level_short(level, lang="pt"):
    table = LEVEL_SHORT_EN if lang == "en" else LEVEL_SHORT_PT
    return table.get(int(level) if level else DEFAULT_LEVEL, "")


def relevance_prompt_rules():
    """Bloco de regras para o prompt de geração (parte comum)."""
    weights_text = ", ".join(f"{key} {int(weight * 100)}%" for key, weight in WEIGHTS.items())
    return f"""RELEVANCE SCORING (mandatory for every option):
- Add a "relevance" object with a 0-100 integer score for EACH key: {weights_text}.
- Score objectively what the event itself caused. "relevancia_mediatica" (media attention back then) must NOT inflate the other scores: a story can be hugely popular for a week and historically minor, or barely covered yet hugely consequential.
- "justification": 1-2 SHORT sentences in PORTUGUESE (max 25 words total) explaining the scores. For events you score 85+ overall, the justification MUST explicitly describe the lasting consequences (what changed afterwards and why it still matters).
- Never invent facts to justify high scores; when unsure, score lower."""


def relevance_json_shape():
    return """          "relevance": {
            "impacto_historico": 0-100,
            "dimensao_impacto": 0-100,
            "consequencias": 0-100,
            "relevancia_posterior": 0-100,
            "dimensao_duracao": 0-100,
            "relevancia_mediatica": 0-100,
            "singularidade": 0-100,
            "justification": "1-2 frases em português"
          }"""
