import calendar
import argparse
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta

import requests

from archive_storage import load_posts_for_date
from historical_relevance import default_relevance, normalize_relevance, relevance_prompt_rules
from social_networks import networks_prompt_rules, normalize_networks
from imgbb_registry import register_imgbb_upload
from nvidia_client import DEFAULT_NVIDIA_MODEL, NvidiaKeyPool, load_nvidia_api_keys
from post_templates import create_image_with_text as render_post_image, is_volatile_image_url
from en_sync import (
    ensure_option_en_fields,
    format_platform_caption,
    is_valid_article_url,
    sync_approved_pt_to_en,
)
from publisher import clean_headline_text


PENDING_POSTS_FILE = "pending_posts.json"
REVIEW_HTML_FILES = {
    "pt": "review_pt.html",
    "en": "review_en.html",
}
PREGENERATION_STATE_FILE = "pregeneration_state.json"

import random

api_keys = load_nvidia_api_keys()
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", DEFAULT_NVIDIA_MODEL)
nvidia_pool = NvidiaKeyPool(api_keys)
if nvidia_pool.has_keys():
    nvidia_pool.current_index = random.randint(0, len(api_keys) - 1)

def get_current_key_info():
    return nvidia_pool.get_current_key_info()

def save_key_status_to_file():
    nvidia_pool.save_key_status_to_file()


save_key_status_to_file()

def rotate_nvidia_client():
    return nvidia_pool.rotate()

IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY")
PREGENERATOR_SOURCE_MODE = os.environ.get("PREGENERATOR_SOURCE_MODE", "arquivo-first")
MAX_NVIDIA_INPUT_ITEMS = int(os.environ.get("PREGENERATOR_NVIDIA_MAX_INPUT_ITEMS", "32"))
MAX_NVIDIA_CONTEXT_CHARS = int(os.environ.get("PREGENERATOR_NVIDIA_MAX_CONTEXT_CHARS", "320"))
NVIDIA_DISABLED = False
NVIDIA_ERROR_MARKERS = ("429", "503", "401", "403", "resource_exhausted", "unavailable", "quota exceeded", "rate limit", "invalid", "unauthorized", "forbidden")
CTA_PATTERNS = [
    r"\blink na bio\b",
    r"\bna bio\b",
    r"\bread more\b",
    r"\bsee more\b",
    r"\bsaiba mais\b",
    r"\bveja mais\b",
    r"\bacompanhe\b",
    r"\bstories\b",
    r"\bswipe\b",
    r"\barraste\b",
    r"\bclick\b",
    r"\btap\b",
    r"\blink in bio\b",
]
NVIDIA_HINT_KEYWORDS = [
    "meme",
    "viral",
    "celebrity",
    "celebridade",
    "cantor",
    "atriz",
    "actor",
    "futebol",
    "football",
    "sport",
    "desporto",
    "polit",
    "elei",
    "govern",
    "polici",
    "crime",
    "morte",
    "death",
    "war",
    "guerra",
    "attack",
    "ataque",
    "protest",
    "manifest",
    "ukraine",
    "ucrani",
    "russia",
    "israel",
    "palestin",
    "tesla",
    "spacex",
    "iphone",
    "apple",
    "google",
    "beyonc",
    "rihanna",
    "swift",
    "kardashian",
    "gaga",
    "ronaldo",
    "messi",
    "festival",
    "music",
    "cultura",
    "internet",
    "met gala",
    "saldos", "promocao", "promoção", "desconto", "descontos", "liquidacao",
    "liquidação", "loja", "lojas", "compras", "shopping", "mango", "zara",
    "primark", "outlet", "catalogo", "catálogo"
]
STRONG_TOPIC_KEYWORDS = [
    # Decisões institucionais, legislativas, judiciais e económicas estruturais (sem nomes próprios)
    "aprova", "aprovado", "aprovada", "veta", "veto", "chumba", "chumbado",
    "suspende", "suspensas", "trava", "proíbe", "proibe", "decreta", "promulga",
    "demite-se", "demissão", "demissao", "detido", "detenção", "detencao",
    "buscas", "corrupção", "corrupcao", "fraude", "investigação", "investigacao",
    "acusado", "condenado", "supremo", "tribunal constitucional", "parlamento",
    "assembleia da república", "assembleia da republica", "governo",
    "conselho de ministros", "comissão europeia", "comissao europeia",
    "conselho europeu", "banco central", "impostos", "iva", "irs", "taxa",
    "juros", "salário mínimo", "salario minimo", "habitação", "habitacao",
    "arrendamento", "alojamento local", "pensões", "pensoes", "reforma",
    "eutanásia", "eutanasia", "greve", "sns", "nacionalização", "nacionalizacao",
    "privatização", "privatizacao", "resgate", "falência", "falencia",
    # Geopolítica, diplomacia e segurança internacional
    "cessar-fogo", "cessar fogo", "tratado", "cimeira", "fronteira", "sanções",
    "sancoes", "bombardeamento", "mísseis", "misseis", "união europeia",
    "uniao europeia", "nato", "onu",
    # Decisões de emergência, saúde pública e funcionamento societário
    "estado de alerta", "estado de emergência", "estado de emergencia", "alerta", "emergência", "emergencia",
    "encerra", "encerramento", "fecha", "fecho", "confinamento", "quarentena", "escola", "escolas",
    "ensino", "aulas", "universidade", "universidades", "hospitais", "saúde pública", "saude publica",
    "pandemia", "prisão", "prisao",
    # Desporto (conquistas finais, mercado estrutural, decisões disciplinares/judiciais)
    "campeão", "campeao", "conquista", "troféu", "trofeu", "título", "titulo",
    "pré-acordo", "pre-acordo", "transferência", "transferencia", "recorde",
    # Fenómenos extremos e sociedade
    "sismo", "terramoto", "tsunami", "incêndio", "incendio", "cheias", "apagão",
]
ICONIC_MILESTONE_KEYWORDS = [
    # Marcos históricos ultra-conhecidos ("Piada / Vem atrasado")
    "25 de abril", "revolução dos cravos", "revolucao dos cravos", "salazar",
    "estado novo", "chernobil", "chernobyl", "fukushima", "madeleine mccann",
    "maddie", "praia da luz", "nossa senhora de fátima", "nossa senhora de fatima",
    "sismo de 1969", "terramoto de 1755", "fidel castro", "11 de setembro",
    "muro de berlim", "apollo 11", "homem na lua",
]
def extract_macro_topic(title, summary="", category=""):
    """
    Identifica macro-temas para controlo estrito de cadencia e saturacao:
    - covid: Covid-19, SARS-CoV-2, coronavirus, pandemia, confinamento, quarentena, etc.
    - sef: Servico de Estrangeiros e Fronteiras / SEF / lei da nacionalidade / fronteiras
    - bpp_rendeiro: Caso BPP / Joao Rendeiro
    - bes_salgado: Caso BES / Ricardo Salgado / Espirito Santo
    - eutanasia: Morte medicamente assistida / eutanasia
    - guerra_ucrania: Invasao russa / guerra na Ucrania
    - conflito_oriente: Israel, Gaza, Palestina
    - greve_educacao: Greves e protestos de professores, docentes, estudantes e fecho de escolas
    - orcamento_financas: Orcamento do Estado, beneficios fiscais, defice e divida
    - eleicoes: Eleicoes legislativas, presidenciais, autarquicas ou internacionais marcantes
    """
    text = f"{title} {summary}".lower()
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    if any(k in norm for k in ["covid", "anticovid", "coronavirus", "pandemia", "confinamento", "quarentena", "sars-cov"]):
        return "covid"
    if "estado de emergencia" in norm and any(k in norm for k in ["pandemia", "virus", "contagio", "restricoes", "mascaras", "sanitaria", "covid", "combate"]):
        return "covid"
    if any(k in norm for k in ["fecha escolas", "fecho de escolas", "suspende cantinas", "aulas presenciais"]) and any(k in norm for k in ["pandemia", "coronavirus", "covid", "confinamento", "novo coronavirus", "contagio", "2020", "2021"]):
        return "covid"
    if re.search(r"\bsef\b", norm) or ("fronteiras" in norm and ("estrangeiros" in norm or "aeroportos" in norm)) or "lei da nacionalidade" in norm:
        return "sef"
    if "rendeiro" in norm or "bpp" in norm:
        return "bpp_rendeiro"
    if "salgado" in norm or "espirito santo" in norm or re.search(r"\bbes\b", norm):
        return "bes_salgado"
    if "eutanasia" in norm or "medicamente assistida" in norm:
        return "eutanasia"
    if any(k in norm for k in ["ucrania", "zelensky", "zaporizhzhia", "invasao russa"]):
        return "guerra_ucrania"
    if any(k in norm for k in ["israel", "palestin", "gaza", "cisjordania", "netanyahu", "unrwa"]):
        return "conflito_oriente"
    if (
        any(k in norm for k in [
            "greve de professor", "greve dos professor", "greve nacional", "greve dos docentes",
            "docentes do ensino", "professores realizam greve", "professores mobilizam",
            "estudantes protestam", "fenprof", "fne", "fecho de escolas", "fecho de 311 escolas",
        ])
        and not any(k in norm for k in ["covid", "pandemia"])
    ):
        return "greve_educacao"
    if any(k in norm for k in ["orcamento do estado", "beneficios fiscais", "beneficio fiscal", "chumbo do orcamento", "chumbado na generalidade", "chumbado na assembleia", "divida publica", "defice"]):
        return "orcamento_financas"
    if any(k in norm for k in ["eleicoes legislativas", "eleicao presidencial", "eleicoes presidenciais", "eleicoes autarquicas", "eleito presidente", "primeiro presidente afro-americano"]):
        return "eleicoes"
    return None


WEAK_TOPIC_KEYWORDS = [
    "segundo a ap", "durante a reunião", "reunião pública", "executivo municipal",
    "relatório", "relatorio", "plano nacional", "secretário de estado",
    "secretario de estado", "comunicado", "conferência de imprensa",
    "conferencia de imprensa", "fonte oficial", "processo administrativo",
    # Ruído efémero, cultura de nicho, cinema/música/prémios e efemérides enciclopédicas
    "meme", "viral", "curioso", "insólito", "insolito", "bizarro",
    "velório", "velorio", "funeral", "tiktok", "perdem pontos", "perde pontos",
    "jornada da liga", "sondagem autárquica", "sondagem municipal", "concelhia",
    "concelhias", "meias criativas", "sem dentes",
    "festival", "concerto", "cinema", "filme", "série", "serie", "álbum", "album",
    "canção", "cancao", "banda sonora", "óscar", "oscar", "globo de ouro",
    "grammy", "guinness", "box office", "bilheteira", "teatro", "exposição",
    "exposicao", "museu", "sonda espacial", "telescópio", "telescopio", "asteroide",
    "fóssil", "fossil", "tratado de", "batalha de", "império romano", "cônsules",
    "dinastia", "hóquei no gelo", "hoquei no gelo", "torneio de poker",
    "saúde oral", "saude oral", "estátua", "estatua",
    "esqueleto", "esqueletos", "arqueologia", "arqueológico", "arqueologico", "fóssil", "fossil",
    "adega", "túmulo", "tumulo", "restos mortais", "turismo espacial", "telescópio webb", "sonda dawn",
    # Rotina administrativa, burocracia menor e notas processuais recorrentes
    "renova estado de emergencia", "renovacao do estado de emergencia",
    "tabela taxas", "taxas de entrega", "mefedrona", "adia extincao",
    "adia por seis meses", "evita encerramento do governo", "orcamento parcial",
    "orcamento provisorio", "revogacao de decretos", "edificios mais eficientes",
    "alimentacao saudavel nas escolas", "derrame de petroleo", "inspecao do sef",
]
NICHE_OR_PROMO_PATTERNS = [
    r"\bj[aá]\s+est[aá]\s+dispon[ií]vel\s+nos\s+locais\s+habituais\b",
    r"\bj[aá]\s+tem\s+o\s+seu\?",
    r"\bnas\s+bancas\b",
    r"\bedi[cç][aã]o\s+desta\s+semana\b",
    r"\bdebate\s+entre\b.{0,40}\bnas\s+legislativas\b",
    r"\bmomentos\s+antes\s+do\s+in[ií]cio\s+do\s+jogo\b",
    r"\bequipa\s+feminina\s+su[ií][cç]a\s+de\s+h[oó]quei\b",
    r"\bjo[aã]o\s+f[eé]lix\b.{0,50}\bbenfica\b",
    r"\bbenfica\b.{0,50}\bjo[aã]o\s+f[eé]lix\b",
    r"\bronaldo\b.{0,40}\bsexto\s+europeu\b",
    r"\brecompensa\s+por\s+captura\s+de\s+maduro\b",
    r"\boferecem\b.{0,30}\bcaptura\s+de\s+maduro\b",
    r"\brevista\s+de\s+imprensa\b",
    r"\bdestaques\s+d[eo]\s+p[u\u00fa]blico\b",
    r"^cr[i\u00ed]tica\s+a[os]?\b",
    r"\bapura[- ]se\b",
    r"\bapurado\s+para\b",
    r"\bmeias[- ]finais\b",
    r"\bquartos[- ]de[- ]final\b",
    r"\boitavos[- ]de[- ]final\b",
    r"\bduelo\s+televisivo\b",
    r"\b[uú]nico\s+candidato\s+[aà]\s+lideran[cç]a\b",
    r"\bdeixa\s+secretariado\b",
    r"\bpedem\s+para\s+sair\s+das\s+listas\b",
    r"\bglobo\s+de\s+ouro\b",
    r"\bhackers\s+brancos\b",
    r"\bataques\s+inform[aá]ticos\s+globais\b",
    r"\bmaduro\s+declara\s+apoio\b",
    r"\bbiden\b.{0,30}\bcorrida\s+[aà]s\s+presidenciais\b",
    r"\bdur[aã]o\s+barroso\b",
    r"\bschr[oö]der\b",
    r"\bcostas\s+simitis\b",
    r"\bcarla\s+alves\b",
    r"\bterceiro\s+lugar\b",
    r"\b3\.?[º°]\s+lugar\b",
    r"\bteve\s+g[eé]meos\b",
    r"\bconhecer\s+os\s+filhos\b",
    r"\bpode\s+crescer\s+para\b",
    r"\bfam[ií]lia\s+coxi\b",
    r"\bmuro\s+de\s+drones\b",
    r"\bconven[cç][aã]o\s+nacional\b",
    r"\bdisputa\s+lideran[cç]a\b",
    r"\bpede\s+clarifica[cç][oõ]es\b",
    r"\bquestiona\s+condi[cç][oõ]es\b",
    r"\badmite\s+rever\b",
    r"\bcenariza\b",
    r"\bexige\s+final\s+da\s+champions\b",
    r"\belogia\b.{0,30}\bseguro\s+de\s+vida\b",
    r"\bdesafia\b.{0,30}\bacordo\b",
    r"\bchega\s+a\s+washington\b",
]

WEAK_TOPIC_KEYWORDS.extend([
    "saldos", "promocao", "promoção", "desconto", "descontos", "liquidacao",
    "liquidação", "loja", "lojas", "compras", "shopping", "mango", "zara",
    "primark", "outlet", "catalogo", "catálogo",
])
COMMERCIAL_TOPIC_KEYWORDS = [
    "saldos", "promocao", "promoção", "desconto", "descontos", "liquidacao",
    "liquidação", "loja", "lojas", "compras", "shopping", "mango", "zara",
    "primark", "outlet", "catalogo", "catálogo",
]
LOW_VALUE_ANNIVERSARY_PATTERNS = [
    r"\bparab[eé]ns\b",
    r"\b(?:celebra|celebram|comemora|comemoram|assinala|assinalam)\b.{0,90}\b\d{1,3}\s+anos\b",
    r"\b\d{1,3}[.ºoª\s]*(?:anivers[aá]rio|anos de exist[eê]ncia)\b",
    r"\bfaz\s+\d{1,3}\s+anos\b",
]
SUBSTANTIVE_ANNIVERSARY_MARKERS = [
    "inaugura", "lança", "lanca", "estreia", "concerto", "exposição", "exposicao",
    "vence", "recorde", "descoberta", "eleição", "eleicao", "acordo", "lei", "reforma",
    "investigação", "investigacao", "campeonato", "festival", "filme", "álbum", "album",
]


def normalize_text(value, uppercase=False):
    if value is None:
        value = ""
    normalized = unicodedata.normalize("NFC", str(value)).strip()
    return normalized.upper() if uppercase else normalized


def compact_text(value, limit=MAX_NVIDIA_CONTEXT_CHARS):
    text = re.sub(r"\s+", " ", normalize_text(value)).strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "..."


def extract_item_headline(item):
    if not isinstance(item, dict):
        return ""
    direct = normalize_text(item.get("title", ""))
    if direct and not direct.endswith("..."):
        return clean_headline_text(re.sub(r"^\[\d{3,4}\]\s*", "", direct).strip())
    opts = item.get("options")
    if isinstance(opts, list) and opts and isinstance(opts[0], dict):
        opt_title = normalize_text(opts[0].get("title", ""))
        if opt_title and not opt_title.endswith("..."):
            return clean_headline_text(re.sub(r"^\[\d{3,4}\]\s*", "", opt_title).strip())
    return ""


def strip_publicity_text(value):
    text = re.sub(r"\s+", " ", normalize_text(value)).strip()
    if not text:
        return ""
    # Remove trailing hashtag blocks at the end, but keep inline #words as words so sentences don't lose their subject
    text = re.sub(r"(?:\s+#[\wÀ-ÿ]+)+\s*$", "", text)
    text = re.sub(r"#([\wÀ-ÿ]+)", r"\1", text)
    text = re.sub(r"@([\w.]+)", r"\1", text)
    # Remove leading flag emojis or decorative symbols
    text = re.sub(r"^[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\s]+", "", text)
    for pattern in CTA_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" -:;,.!")


def is_low_value_anniversary(item):
    text = normalize_text(
        f"{extract_item_headline(item)} "
        f"{item.get('enriched_context') or item.get('global_context') or item.get('caption') or item.get('raw_caption') or ''}"
    ).lower()
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in NICHE_OR_PROMO_PATTERNS):
        return True
    if not any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in LOW_VALUE_ANNIVERSARY_PATTERNS):
        return False
    return not any(marker in text for marker in SUBSTANTIVE_ANNIVERSARY_MARKERS)


def is_iconic_historical_milestone(item):
    text = normalize_text(build_editorial_context(item)).lower()
    return any(keyword in text for keyword in ICONIC_MILESTONE_KEYWORDS)


def score_nvidia_candidate(item):
    context_text = build_editorial_context(item)
    text = normalize_text(context_text).lower()
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    score = 0
    for keyword in STRONG_TOPIC_KEYWORDS:
        if keyword in text:
            score += 4
    for keyword in ICONIC_MILESTONE_KEYWORDS:
        if keyword in text:
            score += 4
    for keyword in WEAK_TOPIC_KEYWORDS:
        if keyword in text:
            score -= 6
    for keyword in COMMERCIAL_TOPIC_KEYWORDS:
        if keyword in text:
            score -= 10
    if is_low_value_anniversary(item):
        score -= 25
    if extract_item_headline(item):
        score += 3
    if re.search(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]+){1,3}\b", context_text):
        score += 2
    if any(p in text for p in ["/pais/", "/nacional/", "/sociedade/", "/politica/", "/economia/", "/educacao/", "portugal", "governo", "assembleia da república", "parlamento"]):
        score += 4
    if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:%|mil|milhoes|escolas|universidades|hospitais|produtos|euros)\b", folded):
        score += 5
    if any(p in folded for p in [
        "da posse", "secretarios de estado", "parada militar", "centenario do armisticio",
        "lanca desafio", "auditoria do tribunal", "atraso na entrega", "falta de auxiliares",
        "novas medidas anticovid", "novas restricoes contra a covid",
    ]):
        score -= 8
    try:
        year_int = int(str(item.get("date", ""))[:4] or 0)
    except ValueError:
        year_int = 0
    if 1996 <= year_int <= 2018:
        score += 4
    elif year_int >= 2025:
        score -= 5
    if any(p in text for p in ["venezuela", "maduro", "peru", "guatemala", "nicaragua"]):
        score -= 4
    if 80 <= len(text) <= 900:
        score += 2
    if len(text) > 1600:
        score -= 2
    return score


def select_nvidia_candidates(news_items, max_total=MAX_NVIDIA_INPUT_ITEMS, max_per_year=3):
    """Seleciona candidatos priorizando notícias reais de jornais/media (1996-2025).

    Evita que os ~40 anos distintos da Wikipédia ocupem os slots todos e impeçam
    a seleção das melhores notícias de cada ano do Arquivo.pt/jornais/Instagram.
    """
    media_by_year = {}
    wiki_milestones = []
    for item in news_items:
        if is_low_value_anniversary(item):
            continue
        platform = normalize_text(item.get("source_platform", "")).lower()
        year = str(item.get("date", ""))[:4] or "0000"
        if platform == "wikipedia":
            if is_iconic_historical_milestone(item):
                wiki_milestones.append(item)
            continue
        media_by_year.setdefault(year, []).append(item)

    def selection_score(item):
        platform = normalize_text(item.get("source_platform", "")).lower()
        if platform in {"arquivo.pt", "web"}:
            priority = 2
        elif platform != "wikipedia":
            priority = 1
        else:
            priority = 0
        # Sem enviesamento por ano recente: prioridade igual entre 2000-2014 e 2015-2025 (1A)
        return (score_nvidia_candidate(item), priority)

    # Reserve at most 2 slots for iconic historical milestones ("Piada / Vem atrasado")
    wiki_milestones.sort(key=selection_score, reverse=True)
    reserved_wiki = wiki_milestones[:2]
    media_budget = max(max_total - len(reserved_wiki), 1)

    # Intercalar anos recentes (2015-2025) e anos do arquivo clássico (2000-2014) com igual prioridade
    recent_years = sorted([y for y in media_by_year.keys() if y >= "2015"], reverse=True)
    classic_years = sorted([y for y in media_by_year.keys() if y < "2015"], reverse=True)
    interleaved_years = []
    for idx in range(max(len(recent_years), len(classic_years))):
        if idx < len(recent_years):
            interleaved_years.append(recent_years[idx])
        if idx < len(classic_years):
            interleaved_years.append(classic_years[idx])

    selected = []
    # 1st pass: best news stories from each interleaved media year (allows 2 if 2nd also has high structural score)
    for year in interleaved_years:
        year_items = sorted(media_by_year[year], key=selection_score, reverse=True)
        if year_items:
            selected.append(year_items[0])
            if len(year_items) > 1 and selection_score(year_items[1])[0] >= 6 and len(selected) < media_budget:
                selected.append(year_items[1])
        if len(selected) >= media_budget:
            break

    # 2nd pass: fill remaining media slots with top-scoring 2nd/3rd stories balanced across all years
    if len(selected) < media_budget and max_per_year > 1:
        selected_ids = {id(item) for item in selected}
        remaining = []
        for year in interleaved_years:
            year_items = sorted(media_by_year[year], key=selection_score, reverse=True)
            remaining.extend(item for item in year_items[1:max_per_year] if id(item) not in selected_ids)
        remaining.sort(key=selection_score, reverse=True)
        selected.extend(remaining[: media_budget - len(selected)])

    selected.extend(reserved_wiki)
    return selected[:max_total]


def infer_category_from_text(text, lang):
    normalized = normalize_text(text).lower()
    category_rules = [
        ("EDUCAÇÃO" if lang == "pt" else "EDUCATION", ["professor", "professores", "docente", "docentes", "escola", "escolas", "universidade", "universidades", "aluno", "alunos", "estudante", "estudantes", "ensino", "fenprof", "fne", "propinas", "ministério da educação", "ministerio da educacao", "3º ciclo", "secundário", "secundario"]),
        ("ECONOMIA" if lang == "pt" else "ECONOMY", ["orçamento do estado", "orcamento do estado", "benefício fiscal", "beneficio fiscal", "benefícios fiscais", "beneficios fiscais", "imposto", "impostos", "iva", "irs", "irc", "pib", "inflação", "inflacao", "banco de portugal", "bce", "fmi", "troika", "défice", "defice", "dívida pública", "divida publica"]),
        ("SAÚDE" if lang == "pt" else "HEALTH", ["hospital", "hospitais", "médico", "medico", "médicos", "medicos", "médica", "medica", "enfermeiro", "enfermeiros", "sns", "serviço nacional de saúde", "vacinação", "vacinacao", "epidemia", "pandemia", "surto"]),
        ("JUSTIÇA" if lang == "pt" else "JUSTICE", ["tribunal", "juiz", "juízes", "juizes", "magistrado", "magistrados", "ministério público", "ministerio publico", "polícia judiciária", "policia judiciaria", "condenação", "condenacao", "julgamento", "acórdão", "acordao"]),
        ("DESPORTO" if lang == "pt" else "SPORTS", ["futebol", "football", "sport", "desporto", "ronaldo", "messi", "benfica", "sporting", "fc porto", "mourinho", "gyökeres", "campeonato", "taça", "liga"]),
        ("POLÍTICA" if lang == "pt" else "POLITICS", ["polit", "elei", "govern", "parliament", "presid", "prime minister", "assembleia da república", "são bento", "palácio de belém", "palacio de belem", "montenegro", "costa", "ventura", "chega", "ps ", "psd", "pcp", "cds", "bloco de esquerda", "sánchez", "trump", "lula"]),
        ("MUNDIAL" if lang == "pt" else "WORLD", ["war", "guerra", "ukraine", "ucrani", "russia", "israel", "palestin", "gaza", "nato", "onu", "estados unidos", "união europeia", "uniao europeia", "casa branca", "vaticano", "papa"]),
        ("TECNOLOGIA" if lang == "pt" else "TECHNOLOGY", ["tech", "tecnolog", "iphone", "apple", "google", "inteligência artificial", "cibersegurança", "smartphone"]),
        ("CULTURA" if lang == "pt" else "CULTURE", ["cultura", "book", "livr", "art", "museum", "teatro", "cinema", "literatura", "rádio", "radio", "música", "musica"]),
        ("SOCIEDADE" if lang == "pt" else "SOCIETY", ["habitação", "habitacao", "salário", "salario", "sismo", "terramoto", "incêndio", "eutanásia", "greve geral", "função pública", "transportes", "metro", "cp "]),
    ]
    for category, keywords in category_rules:
        if any(keyword in normalized for keyword in keywords):
            return category
    return "SOCIEDADE" if lang == "pt" else "NEWS"


_DANGLING_FALLBACK_WORDS = {
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "para", "até", "ate", "desde", "após", "apos", "com", "sem", "por",
    "pelo", "pela", "a", "o", "os", "as", "um", "uma", "e", "ou", "que",
    "como", "mais", "menos", "muito", "irão", "irá", "ira", "será", "sera",
    "foi", "estava", "está", "esta", "este", "esse", "essa", "quando", "onde",
}


def build_fallback_title(text, lang, item=None):
    headline = extract_item_headline(item) if item else ""
    if headline:
        headline = clean_headline_text(headline)
        if len(headline) > 78:
            words = headline.split()
            truncated = ""
            for w in words:
                if len(truncated) + len(w) + 1 <= 78:
                    truncated = f"{truncated} {w}".strip()
                else:
                    break
            headline = truncated or headline[:78]
        return clean_headline_text(headline)
    cleaned = strip_publicity_text(text)
    if not cleaned:
        return "Atualidade" if lang == "pt" else "News"
    # Prefer the first complete sentence if it is concise
    first_sentence = re.split(r"(?<=[.!?])\s+", cleaned)[0].strip()
    if 18 <= len(first_sentence) <= 78 and not first_sentence.endswith("..."):
        candidate = first_sentence.rstrip(".!? ")
    else:
        words = cleaned.split()
        candidate = " ".join(words[:11])
    # Trim trailing dangling prepositions/articles/conjunctions so it never looks cut mid-phrase
    cand_words = candidate.rstrip(" ,;:-").split()
    while len(cand_words) > 4 and cand_words[-1].lower().strip(",;:.!?'\"“”") in _DANGLING_FALLBACK_WORDS:
        cand_words.pop()
    result = " ".join(cand_words).rstrip(" ,;:-.")
    # Close or remove unmatched quotes
    if result.count('"') % 2 == 1:
        result = result.replace('"', "")
    return clean_headline_text(result)


def build_fallback_options(news_items, lang, limit=12):
    fallback_items = select_nvidia_candidates(news_items, max_total=limit)
    if not fallback_items:
        fallback_items = list(news_items[:limit])

    options = []
    for item in fallback_items:
        source_text = item.get("ai_summary") or item.get("global_context") or item.get("caption") or item.get("raw_caption") or ""
        cleaned_text = strip_publicity_text(source_text) or normalize_text(source_text)
        title = build_fallback_title(cleaned_text, lang, item=item)
        caption = compact_text(cleaned_text or title, limit=600)
        year_val = normalize_text(item.get("date", "")[:4])
        raw_url = normalize_text(item.get("source_url") or item.get("url") or "")
        options.append(
            {
                "article_url": resolve_verified_article_url(raw_url, year_val, title=title),
                "year": year_val,
                "category": infer_category_from_text(f"{title} {cleaned_text}", lang),
                "title": title,
                "highlight_text": "",
                "overlay_description": compact_text(cleaned_text or title, limit=110),
                "image_theme": title,
                "layout_preference": "template_1",
                "breaking_candidate": False,
                "caption": caption,
                "summary": compact_text(cleaned_text or title, limit=180),
            }
        )
    return options


def build_editorial_context(item):
    headline = extract_item_headline(item)
    ai_summary = normalize_text(item.get("ai_summary", ""))
    primary_context = compact_text(
        item.get("enriched_context")
        or item.get("global_context")
        or item.get("caption")
        or item.get("raw_caption")
        or "",
        limit=MAX_NVIDIA_CONTEXT_CHARS,
    )
    source_profile = normalize_text(item.get("source_profile", ""))
    content_mode = normalize_text(item.get("content_mode", ""))
    media_count = int(item.get("media_count") or 1)
    flags = [str(flag) for flag in item.get("content_flags", []) if str(flag)]

    parts = []
    if source_profile:
        parts.append(f"Source profile: {source_profile}")
    if content_mode:
        parts.append(f"Content mode: {content_mode}")
    if media_count > 1:
        parts.append(f"Media count: {media_count}")
    if flags:
        parts.append(f"Signals: {', '.join(flags)}")
    if headline:
        parts.append(f"Original Headline: {headline}")
    if ai_summary and ai_summary != primary_context:
        parts.append(f"Summary: {ai_summary}")
    if primary_context:
        parts.append(f"Context: {primary_context}")

    return "\n".join(parts).strip()


# Filtro opcional de fontes (definido por popular_site.py / ARQUIVO_SOURCE_DOMAINS).
SOURCE_DOMAIN_FILTER = set()


def _source_matches_filter(item):
    if not SOURCE_DOMAIN_FILTER:
        return True
    candidates = {
        normalize_text(item.get("source_profile", "")).lower(),
        normalize_text(item.get("domain", "")).lower(),
    }
    for handle in candidates:
        if not handle:
            continue
        if handle in SOURCE_DOMAIN_FILTER or handle.replace(".pt", "") in SOURCE_DOMAIN_FILTER:
            return True
        for allowed in SOURCE_DOMAIN_FILTER:
            if allowed in handle or handle in allowed:
                return True
    return False


def get_historical_news_for_date(date_obj, lang):
    posts = load_posts_for_date(lang, date_obj.month, date_obj.day)

    matching = []
    heavy_words = [
        "morre", "morto", "morte", "rapto", "raptado", "abuso", "abusa", "viola", 
        "violada", "violador", "assassina", "homicídio", "suicídio", 
        "pedofilia", "falece", "falecimento",
        "dies", "died", "death", "kidnap", "kidnapped", "abuse", "rape", "murder", 
        "murdered", "homicide", "suicide", "pedophilia", "fatal"
    ]
    for item in posts:
        if item.get("published", False):
            continue
        try:
            item_date = datetime.strptime(item["date"], "%Y-%m-%d %H:%M:%S")
            if item_date.day == date_obj.day and item_date.year < date_obj.year:
                caption_val = item.get("caption") or item.get("global_context") or item.get("title") or ""
                if isinstance(caption_val, list):
                    caption_val = " ".join([str(x) for x in caption_val])
                elif not isinstance(caption_val, str):
                    caption_val = str(caption_val)
                caption_lower = caption_val.lower()
                if any(w in caption_lower for w in heavy_words):
                    continue
                if is_low_value_anniversary(item):
                    continue
                if not _source_matches_filter(item):
                    continue
                matching.append(item)
        except ValueError:
            continue
    return matching


def load_json(filepath, default=None):
    if default is None:
        default = []
    if not os.path.exists(filepath):
        return default
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json(filepath, data):
    import time as _time
    tmp_path = f"{filepath}.tmp"
    payload = json.dumps(data, ensure_ascii=False, indent=4)
    for attempt in range(5):
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp_path, filepath)
            return
        except OSError:
            if attempt == 4:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(payload)
                return
            _time.sleep(0.4 * (attempt + 1))


def create_image_with_text(
    category_to_draw,
    title_to_draw,
    lang,
    template_path="template.jpg",
    overlay_path="overlay.png",
    output_path="output.jpg",
    description_to_draw="",
    highlight_text="",
    layout_name="auto",
    layout_preference="",
    breaking_candidate=False,
    background_query="",
    manual_background_url="",
    exclude_background_urls=None,
    return_details=False,
    year=None,
    relevance_level=None,
    background_image=None,
    **kwargs,
):
    return render_post_image(
        category_to_draw,
        title_to_draw,
        lang,
        template_path=template_path,
        overlay_path=overlay_path,
        output_path=output_path,
        description_to_draw=description_to_draw,
        highlight_text=highlight_text,
        layout_name=layout_name,
        layout_preference=layout_preference,
        breaking_candidate=breaking_candidate,
        background_query=background_query,
        manual_background_url=manual_background_url,
        exclude_background_urls=exclude_background_urls,
        return_details=return_details,
        year=year,
        relevance_level=relevance_level,
        background_image=background_image,
        **kwargs,
    )


def upload_to_imgbb(filepath, lang, metadata=None):
    if not IMGBB_API_KEY:
        return {}
    try:
        with open(filepath, "rb") as img_file:
            res = requests.post(
                "https://api.imgbb.com/1/upload",
                data={"key": IMGBB_API_KEY},
                files={"image": img_file},
                timeout=30,
            )
        data = res.json()
        if data.get("success"):
            upload_data = data.get("data", {})
            image_url = upload_data.get("url", "")
            delete_url = upload_data.get("delete_url", "")
            register_imgbb_upload(
                {
                    **(metadata or {}),
                    "image_url": image_url,
                    "delete_url": delete_url,
                    "kind": (metadata or {}).get("kind") or "review_preview",
                }
            )
            return {"url": image_url, "delete_url": delete_url}
        print(f"[{lang}] Upload IMGBB falhou: {data}")
        return {}
    except Exception as e:
        print(f"[{lang}] Excecao IMGBB: {e}")
        return {}


def safe_filename_part(value, fallback="preview"):
    text = normalize_text(value).lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:80] or fallback


def review_image_path(lang, date_str, option, index):
    year = safe_filename_part(option.get("year") or "preview")
    title = safe_filename_part(option.get("title") or option.get("image_theme") or "preview")
    directory = os.path.join("images", "review", lang)
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"{date_str}_{index + 1:02d}_{year}_{title}.jpg")


_WAYBACK_RESOLUTION_CACHE = {}


def generate_option_body_with_ai(option):
    """Gera o artigo detalhado (200-800 palavras) em PT e EN apenas para a opção selecionada do slot."""
    if not option or not option.get("title") or not nvidia_pool.has_keys():
        return ""
    existing_body = normalize_text(option.get("body", ""))
    if len(existing_body.split()) < 180:
        level = (option.get("relevance") or {}).get("level") or 4
        word_target = {1: "600-800", 2: "600-800", 3: "400-500", 4: "250-350", 5: "200-250"}.get(level, "250-350")
        consequences_rule = (
            ' O último parágrafo deve começar por "Consequências posteriores:" e descrever as consequências documentadas.'
            if level in (1, 2)
            else ""
        )
        prompt = f"""Escreve o artigo da página desta notícia histórica, em português de Portugal, tom jornalístico, factual.
Nível de relevância {level}: o corpo DEVE ter {word_target} palavras (mínimo absoluto 200).{consequences_rule}
Estrutura: contexto → desenvolvimento → relevância duradoura. Nunca inventes factos, citações ou números que não estejam abaixo.

Ano: {option.get("year")}
Categoria: {option.get("category")}
Título: {option.get("title")}
Resumo: {option.get("overlay_description") or option.get("summary")}
Legenda: {option.get("caption")}

Responde APENAS JSON válido: {{"body": "artigo completo"}}"""
        for attempt in range(2):
            try:
                response = nvidia_pool.chat_json(prompt, timeout=180)
                payload = json.loads(response or "{}")
                body_text = normalize_text(payload.get("body") or "")
                if len(body_text.split()) >= 160:
                    option["body"] = body_text
                    existing_body = body_text
                    break
            except Exception as exc:
                print(f"[pregen] geração de body falhou (tentativa {attempt + 1}): {exc}")
    ensure_option_en_fields(option, pool=nvidia_pool, need_caption_en=True)
    return existing_body


def enrich_options_with_ai(options, lang):
    """2.ª chamada leve: inglês americano (título + resumo + justificação) + relevância + redes."""
    if not options or not nvidia_pool.has_keys():
        return options
    compact = [
        {
            "idx": index,
            "year": option.get("year", ""),
            "category": option.get("category", ""),
            "title": option.get("title", ""),
            "overlay": (option.get("overlay_description") or "")[:200],
            "summary": (option.get("summary") or "")[:200],
        }
        for index, option in enumerate(options)
    ]
    prompt = f"""For each numbered news option below, respond with valid JSON only (no markdown):
{{
  "items": [
    {{
      "idx": 0,
      "title_en": "The headline in natural United States English (not a literal translation)",
      "summary_en": "The overlay/summary in natural United States English",
      "networks": ["instagram" ou "facebook" — ver regras],
      "relevance": {{
        "impacto_historico": 0-100,
        "dimensao_impacto": 0-100,
        "consequencias": 0-100,
        "relevancia_posterior": 0-100,
        "dimensao_duracao": 0-100,
        "relevancia_mediatica": 0-100,
        "singularidade": 0-100,
        "justification": "1-2 SHORT sentences in Portuguese (max 25 words)",
        "justification_en": "1-2 SHORT sentences in United States English (max 25 words)"
      }}
    }}
  ]
}}

Scoring rules: {relevance_prompt_rules()}

{networks_prompt_rules()}

Options:
{json.dumps(compact, ensure_ascii=False)}
"""
    try:
        response = nvidia_pool.chat_json(prompt, timeout=150)
        payload = json.loads(response or "{}")
        items = payload.get("items") if isinstance(payload, dict) else payload
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("idx"))
            except (TypeError, ValueError):
                continue
            if not (0 <= index < len(options)):
                continue
            option = options[index]
            if item.get("title_en"):
                option["title_en"] = normalize_text(item.get("title_en"))
            if item.get("summary_en"):
                option["summary_en"] = normalize_text(item.get("summary_en"))
            if item.get("body"):
                option["body"] = normalize_text(item.get("body"))
            if item.get("body_en"):
                option["body_en"] = normalize_text(item.get("body_en"))
            relevance = normalize_relevance(item.get("relevance"))
            if relevance:
                option["relevance"] = relevance
            option["networks"] = normalize_networks(
                item.get("networks"),
                option.get("category", ""),
                (option.get("relevance") or {}).get("level"),
            )
    except Exception as exc:
        print(f"[pregen] enriquecimento falhou (segue com backfill): {exc}")
    return options


def _fold_search_token(value):
    norm = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(ch for ch in norm if not unicodedata.combining(ch))


def _title_keywords(title):
    stopwords = {
        "para", "como", "mais", "pela", "pelo", "sobre", "entre", "apos",
        "contra", "durante", "antes", "depois", "onde", "quando", "este",
        "esta", "isso", "novo", "nova", "novos", "novas", "dois", "tres",
        "hoje", "ontem", "ainda", "vira", "torna", "portugal", "governo",
        "nacional", "estado", "primeira", "primeiro", "mundial",
        "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    }
    words = []
    for raw in re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", str(title or "")):
        folded = _fold_search_token(raw)
        if folded not in stopwords and not folded.isdigit() and folded not in words:
            words.append(folded)
    return words


def _candidate_matches_title(archive_link, item_title, keywords):
    if not keywords:
        return True
    haystack = _fold_search_token(f"{item_title or ''} {archive_link or ''}")
    hits = sum(1 for kw in keywords if kw in haystack)
    required = 1 if len(keywords) <= 2 else 2
    return hits >= required


def resolve_wayback_capture(url, year, title=""):
    """Resolve a captura wayback mais próxima do artigo original.

    Consulta o serviço CDX do Arquivo.pt para o URL exato, preferindo capturas
    do próprio ano (aceita o ano seguinte se não houver). Devolve o URL
    `arquivo.pt/wayback/<timestamp>/<url>` ou "" quando não existe captura —
    sem captura não há snapshot nem ligação verificável.
    """
    url = normalize_text(url)
    if not url or not url.startswith(("http://", "https://")):
        return ""
    if "/noFrame/replay/" in url:
        url = url.replace("/noFrame/replay/", "/wayback/")
    if not is_valid_article_url(url):
        return ""
    url_lower = url.lower()
    if "/wayback/" in url_lower:
        return url
    cache_key = f"{url}|{year}"
    if cache_key in _WAYBACK_RESOLUTION_CACHE:
        return _WAYBACK_RESOLUTION_CACHE[cache_key]
    result = ""
    try:
        year_int = int(str(year)[:4] or 0)
    except ValueError:
        year_int = 0
    if year_int and year_int >= 1996:
        try:
            response = requests.get(
                "https://arquivo.pt/wayback/cdx",
                params={
                    "url": url,
                    "output": "json",
                    "from": str(year_int),
                    "to": str(year_int + 1),
                    "limit": "60",
                },
                timeout=4,
            )
        except requests.RequestException:
            response = None
        rows = []
        if response is not None and response.status_code == 200:
            # O CDX responde em JSONL (um objeto JSON por linha) ou num único
            # array — aceitar os dois formatos.
            text = response.text or ""
            try:
                parsed = json.loads(text)
                rows = parsed if isinstance(parsed, list) else []
            except ValueError:
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(item, dict):
                        rows.append(item)
        normalized_rows = []
        for row in rows:
            if isinstance(row, dict):
                normalized_rows.append([row.get("timestamp"), row.get("status"), row.get("mime"), row.get("original")])
            elif isinstance(row, list):
                normalized_rows.append(row)
        rows = normalized_rows
        best_ts, best_rank = "", None
        for row in rows or []:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            timestamp, status = str(row[0]), str(row[1])
            mime = str(row[2] or "").lower() if len(row) > 2 else ""
            if mime and any(mime.startswith(bad) for bad in ("image/", "video/", "audio/", "application/pdf", "application/json", "text/plain", "text/css")):
                continue
            try:
                capture_year = int(timestamp[:4])
            except ValueError:
                continue
            # Capturas 2xx preferidas; 3xx servem de fallback (o replay segue
            # o redirecionamento para a página final preservada).
            if status.startswith("2"):
                status_rank = 0
            elif status.startswith("3"):
                status_rank = 1
            else:
                continue
            is_html = mime.startswith("text/html")
            rank = (status_rank, 0 if is_html else 1, abs(capture_year - year_int))
            if best_rank is None or rank < best_rank:
                best_ts, best_rank = timestamp, rank
        if best_ts:
            candidate = f"https://arquivo.pt/wayback/{best_ts}/{url}"
            if is_valid_article_url(candidate):
                result = candidate
    if not result and year_int and year_int >= 1996:
        # Fallback Memento timemap: mais tolerante com variações do URL.
        try:
            timemap = requests.get(
                f"https://arquivo.pt/wayback/timemap/link/{url}",
                timeout=4,
            )
            for line in (timemap.text or "").splitlines():
                line = line.strip()
                m_link = re.search(r"<(https?://arquivo\.pt/wayback/(\d{8,14})/[^>]+)>", line)
                if not m_link:
                    continue
                candidate, timestamp = m_link.group(1), m_link.group(2)
                if abs(int(timestamp[:4]) - year_int) <= 1 and is_valid_article_url(candidate):
                    result = candidate
                    break
        except requests.RequestException:
            pass
    if not result and year_int >= 1996:
        # O URL exato pode nunca ter sido arquivado (ex.: sitemaps modernos
        # com datas antigas): procurar a captura pelo título no mesmo domínio.
        title_query = normalize_text(title)
        keywords = _title_keywords(title_query)
        domain_match = re.search(r"https?://([^/]+)/", url)
        domain = domain_match.group(1) if domain_match else ""
        if title_query and year_int:
            try:
                search_params = {
                    "q": title_query,
                    "maxItems": "8",
                    "from": f"{year_int}0101",
                    "to": f"{year_int + 1}1231",
                }
                if domain:
                    search_params["siteSearch"] = domain
                search = requests.get("https://arquivo.pt/textsearch", params=search_params, timeout=4)
                items = (search.json() or {}).get("response_items", []) if search.status_code == 200 else []
                for item in items:
                    archive_link = normalize_text(item.get("linkToArchive")).replace("/noFrame/replay/", "/wayback/")
                    if "/wayback/" in archive_link and is_valid_article_url(archive_link):
                        if _candidate_matches_title(archive_link, item.get("title"), keywords):
                            result = archive_link
                            break
            except (requests.RequestException, ValueError):
                pass
    if not result and year_int >= 2023 and is_valid_article_url(url):
        result = url
    _WAYBACK_RESOLUTION_CACHE[cache_key] = result
    return result


def resolve_wayback_by_title(title, year):
    """Procura a captura wayback de uma notícia apenas pelo título e ano.

    Usada no backfill de posts antigos que não têm URL de origem guardada.
    """
    title_query = normalize_text(title)
    try:
        year_int = int(str(year)[:4] or 0)
    except ValueError:
        year_int = 0
    # Eventos anteriores a 1996 não têm cobertura contemporânea na web do Arquivo.pt
    if not title_query or year_int < 1996:
        return ""
    keywords = _title_keywords(title_query)
    if not keywords:
        return ""
    short_query = " ".join(keywords[:5])
    compact_query = " ".join(keywords[:3]) if len(keywords) >= 3 else ""
    queries = [title_query]
    if short_query and short_query != title_query.lower():
        queries.append(short_query)
    if compact_query and compact_query not in queries:
        queries.append(compact_query)

    for q in queries:
        try:
            search = requests.get(
                "https://arquivo.pt/textsearch",
                params={
                    "q": q,
                    "maxItems": "12",
                    "from": f"{year_int}0101",
                    "to": f"{year_int + 1}1231",
                    "type": "html",
                },
                timeout=12,
            )
            payload = search.json() if search.status_code == 200 else {}
            items = payload.get("response_items") or payload.get("responseItems") or []
            for item in items:
                archive_link = normalize_text(item.get("linkToArchive"))
                if "/noFrame/replay/" in archive_link:
                    archive_link = archive_link.replace("/noFrame/replay/", "/wayback/")
                if "/wayback/" not in archive_link or not is_valid_article_url(archive_link):
                    continue
                capture_year = re.search(r"/wayback/(\d{4})", archive_link)
                if not capture_year or abs(int(capture_year.group(1)) - year_int) > 1:
                    continue
                if _candidate_matches_title(archive_link, item.get("title"), keywords):
                    return archive_link
        except (requests.RequestException, ValueError):
            pass
    return ""


def resolve_verified_article_url(candidate_url, year, title=""):
    """Garante que qualquer article_url guardado num post futuro é uma notícia válida e arquivada.

    - Rejeita URLs inválidos (Wikipédia, Instagram/Facebook, imagens .jpg/.png/im_, tags, pesquisas).
    - Para eventos anteriores a 1996, devolve "" (sem cobertura web contemporânea no Arquivo.pt).
    - Se já for um URL /wayback/ válido do mesmo ano (±1), mantém-no diretamente.
    - Caso contrário, resolve captura wayback pelo URL original e faz fallback para pesquisa por título.
    - Só aceita URL ao vivo não arquivado quando o ano é >= 2023.
    """
    raw = normalize_text(candidate_url)
    if "/noFrame/replay/" in raw:
        raw = raw.replace("/noFrame/replay/", "/wayback/")
    try:
        year_int = int(str(year)[:4] or 0)
    except ValueError:
        year_int = 0
    if year_int < 1996:
        return ""

    if raw and is_valid_article_url(raw):
        if "/wayback/" in raw.lower():
            m_yr = re.search(r"/wayback/(\d{4})", raw)
            if not m_yr or abs(int(m_yr.group(1)) - year_int) <= 1:
                return raw
            raw = ""
        else:
            resolved = resolve_wayback_capture(raw, year_int, title=title)
            if resolved and is_valid_article_url(resolved):
                return resolved

    if title:
        by_title = resolve_wayback_by_title(title, year_int)
        if by_title and is_valid_article_url(by_title):
            return by_title

    if raw and year_int >= 2023 and is_valid_article_url(raw) and "/wayback/" not in raw.lower():
        return raw
    return ""


CONDITIONAL_POOL_FILE = "conditional_posts_pool.json"


def save_new_conditional_options(cond_options, lang):
    if not cond_options:
        return
    pool = load_json(CONDITIONAL_POOL_FILE, [])
    existing_keys = {
        (normalize_text(item.get("year", "")), normalize_text(item.get("title", "")).lower())
        for item in pool
        if isinstance(item, dict)
    }
    added = 0
    for opt in cond_options:
        key = (normalize_text(opt.get("year", "")), normalize_text(opt.get("title", "")).lower())
        if not key[1] or key in existing_keys:
            continue
        trig = normalize_text(opt.get("conditional_trigger", ""))
        verified_url = resolve_verified_article_url(
            opt.get("article_url", ""),
            opt.get("year", ""),
            title=opt.get("title", ""),
        )
        opt_copy = dict(opt)
        opt_copy["article_url"] = verified_url
        pool.append(
            {
                "id": f"cond_auto_{opt.get('year', '0000')}_{len(pool) + 1}",
                "original_post_id": "",
                "original_date": "",
                "lang": lang,
                "trigger": trig,
                "trigger_description": f"Evento condicional ({trig})",
                "curadoria_note": "auto_detected_by_ai",
                "year": opt.get("year", ""),
                "category": opt.get("category", ""),
                "title": opt.get("title", ""),
                "overlay_description": opt.get("overlay_description", ""),
                "caption": opt.get("caption", ""),
                "summary": opt.get("summary", ""),
                "article_url": verified_url,
                "image_url": opt.get("image_url", ""),
                "local_image_path": opt.get("local_image_path", ""),
                "option": opt_copy,
            }
        )
        existing_keys.add(key)
        added += 1
    if added:
        save_json(CONDITIONAL_POOL_FILE, pool)
        print(f"[{lang}][Bolsa Condicional] +{added} notícia(s) condicional(is) guardada(s) em {CONDITIONAL_POOL_FILE}.")


def rank_all_stories_for_day(news_items, lang, feedback_note=""):
    global NVIDIA_DISABLED

    if NVIDIA_DISABLED or not nvidia_pool.has_keys() or not news_items:
        return build_fallback_options(news_items, lang)

    filtered_items = select_nvidia_candidates(news_items, max_total=MAX_NVIDIA_INPUT_ITEMS, max_per_year=3)

    payload_items = [
        {
            "idx": i,
            "year": item.get("date", "")[:4],
            "context": build_editorial_context(item),
        }
        for i, item in enumerate(filtered_items)
    ]

    normalized_feedback = normalize_text(feedback_note)

    prompt = f"""
    You are the chief editorial director for an archival news publication.
    I will provide you with historical news records from previous years that took place on this exact calendar day and month.

    Language required for the output: {lang.upper()}

    OBJECTIVE EDITORIAL STANDARDS (ZERO EXAMPLES — APPLY ABSTRACT CRITERIA STRICTLY):

    1. TEMPORAL COHERENCE AND PLAUSIBILITY:
       - The post must read like factual breaking news happening today when the archival year is shown only in small print.
       - NEVER include any year, month, or day in 	itle, overlay_description, caption, or summary. Stories must be written completely timelessly for delayed/historical publication (e.g. write 'Orçamento do Estado chumbado na Assembleia da República', NEVER 'Orçamento do Estado para 2022 chumbado').
       - NEVER use absolute or sensationalist historical claims like 'inédito', 'primeira vez na história', or 'acontecimento sem precedentes desde...'.
       - For lang='pt', STRICTLY REJECT domestic news of remote third countries (e.g. municipal/local health decrees in Liberia, smog in Beijing, provincial decrees in Latin America/Asia/Africa) whenever Portuguese or European stories exist. Prioritize Portugal, Portuguese institutions, society, and European events.
       - IMAGE THEME GUIDELINE: When the news concerns Portuguese institutional acts, government, or state organs (e.g. Presidente da República, Governo, Parlamento, São Bento, Belém), the image_theme query MUST explicitly specify Portuguese context (e.g. 'Palácio de Belém Lisboa', 'Assembleia da República Lisboa', 'Governo de Portugal São Bento'), NEVER generic words like 'posse governamental cerimonia' that could return images of Donald Trump or foreign leaders.
       - INSTITUTIONAL ROLE PRINCIPLE:
         * If a news item concerns an official institutional act (such as an executive decision, legislative vote, governmental measure, or judicial ruling) carried out by an officeholder who no longer holds that position today, the `title`, `overlay_description`, and `caption` must refer to the institutional office (e.g. "Governo", "Presidente da República", "Tribunal", "Parlamento") rather than attributing the action to the former officeholder by their personal name.
         * If a news item is a personal opinion, diplomatic tour, speech, warning, challenge, or political declaration by someone who is retired, out of active leadership, playing for a different club, or detained/incapacitated today, STRICTLY REJECT IT.
         * For sports transfers or club memberships: reject placing an athlete at a club they no longer represent today, unless it concerns a lasting regulatory rule or market transaction.

    2. FACTUAL ACTIONS vs. DECLARATIVE / EPHEMERAL NOISE:
       - Select only events where a concrete action, official decision, structural development, or historic turning point actually occurred.
       - STRICTLY REJECT:
         * Declarative noise: verbal opinions, praise, accusations, criticisms, warnings, challenges, or hypothetical speculations between public figures;
         * Internal party disputes, organic leadership races, party conventions, candidate list controversies, or polling projections;
         * Private life, family matters, relationships, or personal milestones of public figures;
         * Routine service statistics, periodic percentage variations, or administrative reports lacking a definitive decision;
         * Intermediate phases in tournaments (qualifications, quarter-finals, semi-finals, third-place matches) — only final tournament championship victories are eligible;
         * Cultural/cinema/music awards, festivals, concerts, commercial promotions, and tragic deaths/funerals.;
         * Routine administrative/procedural items: periodic decree renewals (e.g. routine 15-day renewals of states of emergency), procedural deadline extensions (e.g. postponing agency extinctions by six months), minor platform/delivery fee caps, technical drug schedule updates, foreign government budget shutdown avoidance votes, routine EU directives (building energy efficiency, fruit/milk distribution in schools), administrative revocation of obsolete laws, or remote minor local environmental incidents.

    3. TWO-TIER RELEVANCE HIERARCHY (`editorial_tier`):
       - Classify every option in `"editorial_tier"` as either `"high"` or `"lower_relevance"`:
         * `"high"` (TOP PRIORITY): Events of broad collective scale that affect the daily life, rights, health, public services, institutional functioning, or free movement of the general population or nation (such as official emergency or alert declarations, broad suspensions or closures of public facilities/schools/universities/services, major judicial sentences of national significance, landmark international agreements or geopolitical shifts, final championship titles, or universally known historical turning points).
           - GEOGRAPHICAL & SOCIETAL PROXIMITY: Prioritize national and European-scale events directly touching the population, public institutions, and collective life over remote domestic/internal decisions of distant foreign countries.
           - QUOTIDIAN DISRUPTION AS PEAK PRIORITY: Official measures that disrupt, shut down, or suspend normal societal functioning (educational system, transportation, health, public circulation) must ALWAYS be ranked at the very top of "high".
         * `"lower_relevance"` (FALLBACK ONLY / STRICTLY SECONDARY): Factual events of narrower, local, incremental, or sectoral scope (routine administrative orders, incremental scientific studies, instrument calibrations, archaeological curiosities, ancient fossils/bones, isolated domestic match results without a trophy).
           - Under no circumstances choose a "lower_relevance" curiosity (archaeological finds, space telemetry, routine meetings) if there are valid "high" collective events available in the raw data.
       - Always rank `"high"` tier options ahead of `"lower_relevance"` options. `"lower_relevance"` options must only be selected if the raw data lacks sufficient valid `"high"` tier options.

    4. CONDITIONAL POOL (`conditional_trigger`):
       - If a major event is tied to an event that only recurs on specific political or athletic calendar dates (such as presidential inaugurations, national election cycles, or cup finals), mark `"conditional_trigger"` accordingly. Otherwise, set `"conditional_trigger"` to `""`.

    5. FORMATTING & DIVERSITY:
       - Valid Portuguese categories: EDUCAÇÃO, ECONOMIA, POLÍTICA, SAÚDE, JUSTIÇA, SOCIEDADE, CULTURA, DESPORTO, CIÊNCIA, TECNOLOGIA, MUNDIAL.
       - STRICT CATEGORIZATION: News about schools, teachers, professors, universities, or exams MUST be categorized as 'EDUCAÇÃO' (NEVER generic 'SOCIEDADE'). News about the State Budget, taxes, public debt, or fiscal benefits MUST be categorized as 'ECONOMIA' (NEVER generic 'POLÍTICA' or 'SOCIEDADE'). News about hospitals, doctors, or epidemics MUST be 'SAÚDE'. News about courts or judicial sentences MUST be 'JUSTIÇA'.
       - NEVER include any year, month, or day in `title` or `overlay_description`.
       - `title` must be a complete, self-contained journalistic headline (max 70 chars).
       - Maximize chronological diversity across 1996-2025: at most 2 options from the same year, and ensure representation across different eras.
       - Ground every option strictly in one of the provided RAW DATA items (matching its exact `year`). Never invent facts.

    6. THEMATIC CADENCE & SATURATION LIMITS:
       - Strictly avoid topic saturation: At least 3 days of interval between news of the same macro-theme (e.g. Covid-19/pandemia, repeated judicial cases, recurring disputes).
       - Maximum 8 stories on the same macro-theme within any 30-day window. Even during high-intensity years (like 2020-2021 with the pandemic), do not oversaturate the publication with repetitive pandemic news; diversify into other historical milestones of the era.
       - Prevent Redundant Near-Duplicates: Never select near-duplicate measures, procedural delays, or identical headlines in consecutive or adjacent days.
       - INTRA-DAY THEMATIC DIVERSITY: Do not select multiple headlines about the same entity, sector, or category on the same day. Slot 1 and Slot 2 must be thematic contrasts (e.g. if one is education/strikes, the other must be an international milestone, culture, or economy).
       - INTER-DAY DIVERSITY: Avoid selecting the same macro-topic or sector across consecutive days (e.g. do not schedule strikes or elections two days in a row).
       - HISTORICAL WEIGHT OF WORLD EVENTS: Any world event ('MUNDIAL') must be a landmark historical turning point that impacted world history (e.g. Barack Obama elected first African-American president, fall of the Berlin Wall) rather than foreign local news.

    Format:
    {{
      "options": [
        {{
          "year": "YYYY",
          "category": "ONE WORD CATEGORY IN PORTUGUESE",
          "editorial_tier": "high or lower_relevance",
          "title": "Complete journalistic headline (max 70 chars, no year/date, institutional role if ex-officeholder)",
          "highlight_text": "Empty string or 1-3 words from title",
          "overlay_description": "Timeless 1-sentence context for image overlay (no dates/years/hashtags)",
          "image_theme": "2 to 5 word visual search query",
          "layout_preference": "template_1, template_2, or template_3",
          "breaking_candidate": false,
          "conditional_trigger": "Empty string '' or specific trigger",
          "caption": "Concise paragraph for social post (no hashtags)",
          "summary": "1-sentence editorial rationale"
        }}
      ]
    }}

    Editorial review feedback from the human reviewer:
    {normalized_feedback or "No extra feedback provided."}

    RAW DATA:
    {json.dumps(payload_items, ensure_ascii=False)}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        if not nvidia_pool.has_keys():
            break
        try:
            response_text = nvidia_pool.chat_json(prompt, model=NVIDIA_MODEL, timeout=240)
            save_key_status_to_file()
            payload = json.loads(response_text or "{}")
            if isinstance(payload, dict):
                options = payload.get("options", [])
            else:
                options = payload if isinstance(payload, list) else []
            if isinstance(options, list):
                candidates_by_year = {}
                for item in filtered_items:
                    candidates_by_year.setdefault(str(item.get("date", ""))[:4], []).append(item)

                def _option_tokens(text):
                    return set(re.findall(r"[a-záâãéêíóôõúç]{4,}", normalize_text(text).lower()))

                grounded_options = []
                for option in options:
                    if not isinstance(option, dict):
                        continue
                    option["year"] = normalize_text(option.get("year", ""))
                    option["category"] = normalize_text(option.get("category", ""), uppercase=True)
                    option["title"] = normalize_text(option.get("title", ""))
                    option["title_en"] = normalize_text(option.get("title_en", ""))
                    option["highlight_text"] = normalize_text(option.get("highlight_text", ""))
                    option["overlay_description"] = normalize_text(option.get("overlay_description", ""))
                    option["image_theme"] = normalize_text(option.get("image_theme", ""))
                    option["caption"] = normalize_text(option.get("caption", ""))
                    option["summary"] = normalize_text(option.get("summary", ""))
                    option["summary_en"] = normalize_text(option.get("summary_en", ""))
                    option["body_en"] = normalize_text(option.get("body_en", ""))
                    relevance = normalize_relevance(option.get("relevance"))
                    option["relevance"] = relevance or default_relevance(lang)
                    if not option["title"] or not option["year"]:
                        continue
                    # Ligar a opção à notícia candidata correspondente (ano +
                    # palavras partilhadas) e resolver a captura wayback —
                    # opções desancoradas (ex.: alucinações da IA) são
                    # descartadas: sem artigo real não há snapshot nem fonte.
                    option["article_url"] = ""
                    pool = candidates_by_year.get(option["year"][:4], [])
                    opt_tokens = _option_tokens(f"{option.get('title', '')} {option.get('summary', '')}")
                    best, best_score = None, 0
                    for candidate in pool:
                        score = len(opt_tokens & _option_tokens(build_editorial_context(candidate)))
                        if score > best_score:
                            best, best_score = candidate, score
                    if best and best_score >= 2:
                        # Entre candidatos do MESMO evento (score empatado),
                        # preferir a fonte com mais conteúdo e sem paywall.
                        FREE_SOURCES = {"publico.pt", "rtp.pt", "sicnoticias.pt", "dn.pt", "jn.pt", "observador.pt", "noticiasaominuto.com"}
                        PAYWALLED = {"expresso.pt", "sabado.pt", "visao.pt", "activa.pt", "maxima.pt", "exameinformatica.pt"}
                        best_domain = normalize_text(best.get("domain") or "")
                        if best_domain in PAYWALLED:
                            for candidate in pool:
                                if candidate is best:
                                    continue
                                c_score = len(opt_tokens & _option_tokens(build_editorial_context(candidate)))
                                c_domain = normalize_text(candidate.get("domain") or "")
                                if c_score >= best_score and c_domain in FREE_SOURCES:
                                    best = candidate
                                    best_domain = c_domain
                                    break
                        best_opts = best.get("options") if isinstance(best.get("options"), list) else []
                        opt0_url = best_opts[0].get("article_url") or best_opts[0].get("url") if best_opts and isinstance(best_opts[0], dict) else ""
                        candidate_url = normalize_text(best.get("source_url") or opt0_url or best.get("url") or "")
                        # Âncora a um candidato REAL (impede alucinações) e garante que
                        # todas as opções ficam apenas com um URL de notícia válido e arquivado.
                        option["article_url"] = resolve_verified_article_url(
                            candidate_url,
                            option.get("year", ""),
                            title=option.get("title", ""),
                        )
                        # Proveniência do candidato (chip Jornal/Perfil/Wikipédia).
                        option["source_platform"] = normalize_text(best.get("source_platform"))
                        option["source_profile"] = normalize_text(best.get("source_profile"))
                        grounded_options.append(option)
                    else:
                        print(f"[pregen] opção desancorada descartada: {option['title'][:60]} ({option['year']})")
                options = enrich_options_with_ai(grounded_options, lang) if grounded_options else []
                if options:
                    regular_options = []
                    cond_options = []
                    for opt in options:
                        trig = normalize_text(opt.get("conditional_trigger", "")).lower()
                        if trig and trig not in {"none", "null", "false"}:
                            opt["conditional_trigger"] = trig
                            cond_options.append(opt)
                        else:
                            opt["conditional_trigger"] = ""
                            regular_options.append(opt)
                    if cond_options:
                        save_new_conditional_options(cond_options, lang)
                    if regular_options:
                        regular_options.sort(
                            key=lambda o: 0 if str(o.get("editorial_tier", "high")).lower() == "high" else 1
                        )
                    if len(regular_options) >= 2:
                        options = regular_options
            return options if isinstance(options, list) and options else []
        except Exception as e:
            err_msg = str(e).lower()
            is_quota = "429" in err_msg or "exhausted" in err_msg or "limit" in err_msg or "quota" in err_msg
            if is_quota:
                if ("day" in err_msg or "daily" in err_msg) and "minute" not in err_msg:
                    print(f"\n[NVIDIA] {get_current_key_info()} atingiu limite de API na pre-geracao. A rodar...")
                    nvidia_pool.mark_current_exhausted()
                if rotate_nvidia_client():
                    continue
            print(f"[NVIDIA] Erro na pre-geracao (tentativa {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(2)
            else:
                print(f"[{lang}] Falha na pre-geracao apos {max_retries} tentativas: {e}")
                return build_fallback_options(news_items, lang)
    return build_fallback_options(news_items, lang)


def generate_external_day_suggestions(date_obj, lang, existing_options=None):
    global NVIDIA_DISABLED

    if NVIDIA_DISABLED or not nvidia_pool.has_keys():
        return []

    existing_options = existing_options or []
    existing_titles = [
        normalize_text(option.get("title", ""))
        for option in existing_options
        if isinstance(option, dict) and normalize_text(option.get("title", ""))
    ]
    audience_guidance = (
        "Focus primarily on events or cultural moments from Portugal, Portuguese public life, Portuguese media, Portuguese sport, "
        "or stories with especially strong resonance for a Portuguese audience."
        if lang == "pt"
        else "Focus primarily on world events, globally recognisable stories, internet culture, celebrity moments, major sport, "
        "and internationally relevant events rather than country-specific niche items."
    )
    output_language = "Portuguese" if lang == "pt" else "English"

    prompt = f"""
    You are helping a delayed-news editor find 3 extra historical post ideas for a specific calendar day.

    Calendar day:
    - day: {date_obj.day}
    - month: {date_obj.month}

    Language for the output: {output_language}

    CRITICAL RULES:
    1. STRICT CALENDAR DATE MATCHING:
       - You MUST only suggest events that actually happened on this exact day: {date_obj.day} of {date_obj.strftime('%B')}.
       - Do NOT suggest events from other dates. For example, if today is in July, do NOT suggest the Carnation Revolution (which happened on April 25th), do NOT suggest Christmas, and do NOT suggest any other off-season events.
    2. CATEGORY AND CONTENT LANGUAGE (STRICTLY PORTUGUESE):
       - Since the language is {lang.upper()}, ALL fields ("title", "summary", "category") MUST be written 100% in European Portuguese!
       - NEVER use English titles or phrasing (e.g. write 'Estreia de Morte e Vida de Fernando Pessoa', NEVER 'Premiere of...').
       - Use categories like: POLÍTICA, DESPORTO, CULTURA, SOCIEDADE, CIÊNCIA, NACIONAL, MUNDIAL, ESTRELA, CURIOSO. Never use English words.
    3. NO DEATHS:
       - Do NOT suggest any events about deaths, passings, murders, violence, or violent tragedies.
    4. HISTORICAL ACCURACY (PORTUGAL):
       - The dictatorship in Portugal (Estado Novo) lasted from 1933 until the Carnation Revolution on April 25, 1974. Never refer to 1960 or any other year as the end of the dictatorship.
    5. ENDURING EDITORIAL VALUE:
       - Prefer events that remain meaningful without relying on an anniversary number, institutional greeting, or ceremonial publicity.
       - Anniversary coverage is only suitable when it contains a substantive event or lasting cultural, social, scientific, sporting, or political consequence.

    Audience guidance:
    {audience_guidance}

    Existing archive-backed titles already available in the local database:
    {json.dumps(existing_titles, ensure_ascii=False)}

    Task:
    1. Suggest exactly 3 historical events, moments, or culturally important stories tied exactly to this calendar day and month.
    2. These suggestions should be independent from the local archive and can come from your own general knowledge base.
    3. Prefer high-confidence, recognisable events rather than obscure ones.
    4. Try not to duplicate the existing archive-backed titles above.
    5. Mix seriousness and virality well when possible.

    Return strict JSON as an object with a "suggestions" array containing exactly 3 objects:
    {{
      "suggestions": [
        {{
          "year": "YYYY",
          "category": "SHORT CATEGORY IN PORTUGUESE (e.g., CULTURA, DESPORTO)",
          "title": "Short headline idea",
          "summary": "1 sentence on why this matters or could work well as a post"
        }}
      ]
    }}
    """

    max_retries = 3
    for attempt in range(max_retries):
        if not nvidia_pool.has_keys():
            break
        try:
            response_text = nvidia_pool.chat_json(prompt, model=NVIDIA_MODEL)
            save_key_status_to_file()
            payload = json.loads(response_text or "{}")
            if isinstance(payload, dict):
                payload = payload.get("suggestions", [])
            elif not isinstance(payload, list):
                payload = []
            if not isinstance(payload, list):
                return []

            suggestions = []
            for item in payload[:3]:
                if not isinstance(item, dict):
                    continue
                suggestions.append(
                    {
                        "year": normalize_text(item.get("year", "")),
                        "category": normalize_text(item.get("category", ""), uppercase=True),
                        "title": normalize_text(item.get("title", "")),
                        "summary": normalize_text(item.get("summary", "")),
                    }
                )
            return suggestions
        except Exception as exc:
            err_msg = str(exc).lower()
            is_quota = "429" in err_msg or "exhausted" in err_msg or "limit" in err_msg or "quota" in err_msg
            if is_quota:
                if ("day" in err_msg or "daily" in err_msg) and "minute" not in err_msg:
                    print(f"\n[NVIDIA] {get_current_key_info()} atingiu limite de API nas sugestoes. A rodar...")
                    nvidia_pool.mark_current_exhausted()
                if rotate_nvidia_client():
                    continue
            print(f"[NVIDIA] Erro nas sugestoes (tentativa {attempt + 1}/{max_retries}): {exc}")
            if attempt < max_retries - 1:
                import time
                time.sleep(2)
            else:
                if any(marker in str(exc).lower() for marker in NVIDIA_ERROR_MARKERS):
                    NVIDIA_DISABLED = True
                    print(f"[{lang}] NVIDIA indisponivel nas sugestoes externas: {exc}")
                return []
    return []


def month_key(date_obj):
    return date_obj.strftime("%Y-%m")


def parse_month_key(value):
    return datetime.strptime(f"{value}-01", "%Y-%m-%d").date()


def add_one_month(date_obj):
    year = date_obj.year + (1 if date_obj.month == 12 else 0)
    month = 1 if date_obj.month == 12 else date_obj.month + 1
    return datetime(year, month, 1).date()


def end_of_month(date_obj):
    return datetime(date_obj.year, date_obj.month, calendar.monthrange(date_obj.year, date_obj.month)[1]).date()


def sort_pending_posts(posts):
    posts.sort(key=lambda item: (item.get("date", ""), 0 if item.get("lang") == "pt" else 1, int(item.get("slot", 1))))


def normalize_pending_post(post):
    post["layout_override"] = str(post.get("layout_override", "")).strip().lower().replace("-", "_")
    post["theme_suggestion"] = normalize_text(post.get("theme_suggestion", ""))
    review_action = str(post.get("review_action", "")).strip().lower()
    post["review_action"] = review_action if review_action in {"regenerate", "refresh_image"} else ""
    post["review_note"] = normalize_text(post.get("review_note", ""))
    post["manual_background_url"] = normalize_text(post.get("manual_background_url", ""))
    post["status"] = str(post.get("status", "pending")).strip().lower() or "pending"
    post["generated_month"] = str(post.get("generated_month") or str(post.get("date", ""))[:7]).strip()
    post["selected_option"] = int(post.get("selected_option", 0) or 0)
    external_suggestions = []
    for suggestion in post.get("external_suggestions", []) or []:
        if not isinstance(suggestion, dict):
            continue
        external_suggestions.append(
            {
                "year": normalize_text(suggestion.get("year", "")),
                "category": normalize_text(suggestion.get("category", ""), uppercase=True),
                "title": normalize_text(suggestion.get("title", "")),
                "summary": normalize_text(suggestion.get("summary", "")),
            }
        )
    post["external_suggestions"] = external_suggestions
    options = []
    for option in post.get("options", []) or []:
        if not isinstance(option, dict):
            continue
        normalized_option = dict(option)
        normalized_option["year"] = normalize_text(normalized_option.get("year", ""))
        normalized_option["category"] = normalize_text(normalized_option.get("category", ""), uppercase=True)
        normalized_option["title"] = normalize_text(normalized_option.get("title", ""))
        normalized_option["title_en"] = normalize_text(normalized_option.get("title_en", ""))
        normalized_option["highlight_text"] = normalize_text(normalized_option.get("highlight_text", ""))
        normalized_option["overlay_description"] = normalize_text(normalized_option.get("overlay_description", ""))
        normalized_option["image_theme"] = normalize_text(normalized_option.get("image_theme", ""))
        normalized_option["caption"] = normalize_text(normalized_option.get("caption", ""))
        normalized_option["summary"] = normalize_text(normalized_option.get("summary", ""))
        normalized_option["summary_en"] = normalize_text(normalized_option.get("summary_en", ""))
        normalized_option["body"] = normalize_text(normalized_option.get("body", ""))
        normalized_option["body_en"] = normalize_text(normalized_option.get("body_en", ""))
        normalized_option["networks"] = normalize_networks(
            normalized_option.get("networks"),
            normalized_option.get("category", ""),
            (normalized_option.get("relevance") or {}).get("level"),
        )
        normalized_option["layout_preference"] = str(normalized_option.get("layout_preference", "template_1")).strip().lower().replace("-", "_")
        normalized_option["breaking_candidate"] = bool(normalized_option.get("breaking_candidate", False))
        normalized_option["background_source_url"] = normalize_text(normalized_option.get("background_source_url", ""))
        normalized_option["local_image_path"] = normalize_text(normalized_option.get("local_image_path", ""))
        normalized_option["image_delete_url"] = normalize_text(normalized_option.get("image_delete_url", ""))
        relevance = normalize_relevance(normalized_option.get("relevance"))
        normalized_option["relevance"] = relevance or default_relevance(post.get("lang", "pt"))
        normalized_option["article_url"] = normalize_text(normalized_option.get("article_url", ""))
        options.append(normalized_option)
    post["options"] = options
    if post["selected_option"] >= len(options):
        post["selected_option"] = 0
    return post


def load_pregeneration_state():
    return load_json(PREGENERATION_STATE_FILE, {})


def save_pregeneration_state(state):
    save_json(PREGENERATION_STATE_FILE, state)


def latest_month_in_pending(pending_posts, lang_filter=""):
    latest = None
    for post in pending_posts:
        if lang_filter and post.get("lang") != lang_filter:
            continue
        try:
            post_date = datetime.strptime(post["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        candidate = post_date.replace(day=1)
        if latest is None or candidate > latest:
            latest = candidate
    return latest


def determine_next_target_month(pending_posts, state, lang_filter=""):
    state_for_lang = state.get(lang_filter, {}) if lang_filter else state
    last_generated_month = normalize_text(state_for_lang.get("last_generated_month", ""))
    base_month = None

    if last_generated_month:
        try:
            base_month = parse_month_key(last_generated_month)
        except ValueError:
            base_month = None

    if base_month is None:
        base_month = latest_month_in_pending(pending_posts, lang_filter=lang_filter)

    if base_month is None:
        base_month = datetime.now().date().replace(day=1)

    return add_one_month(base_month)


def determine_focus_month(pending_posts, fallback_month=""):
    regenerate_posts = [post for post in pending_posts if post.get("review_action") == "regenerate"]
    if regenerate_posts:
        return sorted({post.get("date", "")[:7] for post in regenerate_posts if post.get("date")})[0]

    pending_posts_open = [
        post for post in pending_posts
        if post.get("status", "pending") not in {"approved", "published", "skip"}
    ]
    if pending_posts_open:
        return sorted({post.get("date", "")[:7] for post in pending_posts_open if post.get("date")})[0]

    return fallback_month


def match_option_to_article(option, articles):
    if not articles:
        return None
    opt_year = option.get("year", "")
    opt_title = (option.get("title") or "").lower()
    
    same_year_articles = [art for art in articles if str(art.get("date", ""))[:4] == opt_year]
    if not same_year_articles:
        return None
        
    if len(same_year_articles) == 1:
        return same_year_articles[0]
        
    best_match = same_year_articles[0]
    max_matches = -1
    for art in same_year_articles:
        art_title = (art.get("title") or "").lower()
        art_context = (art.get("global_context") or "").lower()
        words = [w for w in opt_title.split() if len(w) > 3]
        matches = sum(1 for w in words if w in art_title or w in art_context)
        if matches > max_matches:
            max_matches = matches
            best_match = art
            
    return best_match


def format_standard_caption(caption, year, category, platform="instagram", lang="pt"):
    return format_platform_caption(caption, year, category, platform=platform, lang=lang)


def append_review_hashtags(caption, lang, year="", category="", platform="instagram"):
    return format_standard_caption(caption, year, category, platform=platform, lang=lang)


def prepare_options_for_review(
    options_list,
    lang,
    date_str,
    manual_background_url="",
    force_new_background=False,
    matching_news=None,
    selected_option_index=0,
    render_all=False,
):
    prepared_options = []
    try:
        selected_option_index = int(selected_option_index or 0)
    except Exception:
        selected_option_index = 0

    for option_index, opt in enumerate(options_list):
        option = dict(opt)
        option["title"] = clean_headline_text(option.get("title", ""))
        should_render_image = render_all or option_index == selected_option_index
        matched_background_url = ""
        matched_article_url = ""
        if matching_news:
            matched = match_option_to_article(option, matching_news)
            if matched:
                matched_article_url = normalize_text(matched.get("source_url") or matched.get("url") or "")
                if should_render_image:
                    candidate_background_url = normalize_text(matched.get("image_url", ""))
                    if candidate_background_url and not is_volatile_image_url(candidate_background_url):
                        matched_background_url = candidate_background_url
                    elif candidate_background_url:
                        print(f"[{lang}] Imagem do artigo ignorada: URL temporario do Instagram/Facebook CDN.")

        option["article_url"] = resolve_verified_article_url(
            option.get("article_url", "") or matched_article_url,
            option.get("year", ""),
            title=option.get("title", ""),
        )

        if should_render_image:
            generate_option_body_with_ai(option)
            stable_img_path = review_image_path(lang, date_str, option, option_index)
            current_background_source = normalize_text(option.get("background_source_url", ""))
            effective_manual_background_url = manual_background_url or ("" if force_new_background else matched_background_url)
            render_details = create_image_with_text(
                option.get("category"),
                option.get("title"),
                lang,
                output_path=stable_img_path,
                description_to_draw=option.get("overlay_description", ""),
                highlight_text=option.get("highlight_text", ""),
                layout_preference=option.get("layout_preference", "template_1"),
                breaking_candidate=bool(option.get("breaking_candidate", False)),
                background_query=option.get("image_theme", "") or option.get("title", ""),
                manual_background_url=effective_manual_background_url,
                exclude_background_urls=[current_background_source] if force_new_background and current_background_source and not manual_background_url else [],
                return_details=True,
                year=option.get("year"),
                relevance_level=(option.get("relevance") or {}).get("level"),
            )
            imgbb_upload = upload_to_imgbb(
                stable_img_path,
                lang,
                metadata={
                    "kind": "review_preview",
                    "lang": lang,
                    "date": date_str,
                    "option_index": option_index,
                    "title": option.get("title", ""),
                    "year": option.get("year", ""),
                },
            )
            imgbb_url = imgbb_upload.get("url", "")
            local_review_url = stable_img_path.replace(os.sep, "/")
            option["image_url"] = imgbb_url or local_review_url
            option["image_delete_url"] = imgbb_upload.get("delete_url", "")
            option["local_image_path"] = local_review_url
            background_src = ""
            background_local = ""
            if isinstance(render_details, dict):
                background_src = render_details.get("background_source_url", "")
                background_local = render_details.get("background_local_path", "")
            option["background_source_url"] = normalize_text(background_src)
            option["local_background_path"] = normalize_text(background_local)
        else:
            option["image_url"] = normalize_text(option.get("image_url", ""))
            option["image_delete_url"] = normalize_text(option.get("image_delete_url", ""))
            option["local_image_path"] = normalize_text(option.get("local_image_path", ""))
            option["background_source_url"] = normalize_text(option.get("background_source_url", ""))
            option["local_background_path"] = normalize_text(option.get("local_background_path", ""))

        option["image_theme"] = normalize_text(option.get("image_theme", ""))
        option["layout_preference"] = str(option.get("layout_preference", "template_1")).strip().lower().replace("-", "_")
        option["breaking_candidate"] = bool(option.get("breaking_candidate", False))
        year = option.get("year", "")
        cat = option.get("category", "")
        option["caption_instagram"] = format_standard_caption(option.get("caption", ""), year, cat, platform="instagram", lang=lang)
        option["caption_facebook"] = format_standard_caption(option.get("caption", ""), year, cat, platform="facebook", lang=lang)
        option["caption"] = option["caption_instagram"]
        prepared_options.append(option)
    return prepared_options


def clone_options(options_list):
    return json.loads(json.dumps(options_list, ensure_ascii=False))


def refresh_marked_post_images(pending_posts):
    targets = [post for post in pending_posts if post.get("review_action") == "refresh_image"]
    if not targets:
        return False, False, ""

    changed = False
    focus_month = determine_focus_month(targets, fallback_month="")

    for post in targets:
        lang = post.get("lang", "pt")
        date_str = post.get("date", "")
        manual_background_url = post.get("manual_background_url", "")

        if not post.get("options"):
            continue

        print(f"[{lang}] A atualizar apenas a imagem de fundo em {post.get('id', '')}.")
        prepared_options = prepare_options_for_review(
            post.get("options", []),
            lang,
            date_str,
            manual_background_url=manual_background_url,
            force_new_background=not bool(manual_background_url),
            selected_option_index=post.get("selected_option", 0),
        )
        post["options"] = clone_options(prepared_options)
        if post["selected_option"] >= len(post["options"]):
            post["selected_option"] = 0
        post["status"] = "pending"
        post["review_action"] = ""
        post["last_image_refresh_at"] = datetime.now().isoformat()
        changed = True

    return True, changed, focus_month


def tag_source_origin(items, origin):
    tagged = []
    for item in items or []:
        clone = dict(item)
        clone["source_origin"] = clone.get("source_origin") or origin
        tagged.append(clone)
    return tagged


def get_news_with_arquivo_first(date_obj, lang):
    """Regra 1B: Usa a pasta D:\arquivo_cdxj como fonte principal e recorre a pt/*.json apenas como fallback."""
    local_news = get_historical_news_for_date(date_obj, lang)
    arquivo_news = []
    try:
        from publisher import arquivo_cdxj_paths_for_day, get_today_news_from_arquivo
        has_cdxj = any(arquivo_cdxj_paths_for_day(y, date_obj.month, date_obj.day) for y in range(1996, 2026))
        if has_cdxj:
            print(f"[{lang}][Arquivo.pt/CDXJ] A ler notícias do dia a partir dos ficheiros CDXJ locais...")
            arquivo_news = get_today_news_from_arquivo(lang, date_obj.month, date_obj.day, max_items=24)
            if arquivo_news:
                print(f"[{lang}][Arquivo.pt/CDXJ] Obtidos {len(arquivo_news)} artigos a partir do índice CDXJ.")
        else:
            print(f"[{lang}][Arquivo.pt/CDXJ] Sem ficheiros CDXJ para {date_obj.month:02d}-{date_obj.day:02d}. A usar pt/*.json ({len(local_news)} notícias)...")
    except Exception as e:
        print(f"[{lang}][Arquivo.pt/CDXJ] Aviso ({e}). A usar pt/*.json como fallback...")

    local_news = get_historical_news_for_date(date_obj, lang)
    if len(arquivo_news) >= 8:
        # Mantém apenas marcos históricos icónicos ("Piada / Vem atrasado") do arquivo local e usa D:rquivo_cdxj como fonte principal
        iconic_local = [item for item in local_news if is_iconic_historical_milestone(item)]
        return tag_source_origin(arquivo_news, "arquivo.pt") + tag_source_origin(iconic_local, "local_fallback")
    if arquivo_news:
        return tag_source_origin(arquivo_news, "arquivo.pt") + tag_source_origin(local_news, "local_fallback")
    return tag_source_origin(local_news, "local_fallback")


def normalize_source_mode(value):
    mode = normalize_text(value or PREGENERATOR_SOURCE_MODE).lower().replace("_", "-")
    aliases = {
        "arquivo": "arquivo-first",
        "arquivo-only": "arquivo-only",
        "full": "arquivo-first",
        "fast": "local",
        "local-only": "local",
        "localfirst": "local-first",
        "arquivofirst": "arquivo-first",
    }
    return aliases.get(mode, mode if mode in {"local", "local-first", "arquivo-first", "arquivo-only"} else "arquivo-first")


def get_news_for_generation(date_obj, lang, source_mode=""):
    mode = normalize_source_mode(source_mode)

    if mode in {"local", "local-first"}:
        local_news = get_historical_news_for_date(date_obj, lang)
        if local_news:
            print(f"[{lang}][Local] Obtidas {len(local_news)} noticias locais.")
            return tag_source_origin(local_news, "local")
        if mode == "local":
            print(f"[{lang}][Local] Sem noticias locais para este dia.")
            return []
        print(f"[{lang}][Local] Sem noticias locais. A tentar Arquivo.pt...")

    if mode == "arquivo-only":
        try:
            from publisher import get_today_news_from_arquivo
            print(f"[{lang}][Arquivo.pt] A procurar noticias do dia no Arquivo.pt...")
            return tag_source_origin(get_today_news_from_arquivo(lang, date_obj.month, date_obj.day), "arquivo.pt")
        except Exception as exc:
            print(f"[{lang}][Arquivo.pt] Erro ao aceder ao Arquivo.pt ({exc}).")
            return []

    return get_news_with_arquivo_first(date_obj, lang)


def regenerate_marked_posts(pending_posts):
    targets = [post for post in pending_posts if post.get("review_action") == "regenerate"]
    if not targets:
        return False, False, ""

    target_groups = {}
    for post in targets:
        key = (post.get("lang", "pt"), post.get("date", ""))
        target_groups.setdefault(key, []).append(post)

    print(f"A regenerar {len(targets)} post(s) marcados para refresh seletivo...")
    changed = False

    for (lang, date_str), grouped_targets in target_groups.items():
        try:
            post_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            print(f"[{lang}] Data invalida em {date_str}.")
            continue

        matching_news = get_news_for_generation(post_date, lang)
        if not matching_news:
            print(f"[{lang}] Sem noticias historicas para regenerar {date_str}.")
            continue

        siblings = [
            post for post in pending_posts
            if post.get("lang", "pt") == lang and post.get("date", "") == date_str
        ]
        approved_siblings = [
            s for s in siblings
            if s.get("status") == "approved" and s.get("review_action") != "regenerate"
        ]
        avoid_notes = []
        for app_sib in approved_siblings:
            app_opts = app_sib.get("options") or []
            app_sel = int(app_sib.get("selected_option", 0) or 0)
            if app_sel < len(app_opts):
                app_opt = app_opts[app_sel]
                avoid_notes.append(f"DO NOT duplicate this already-approved story on this day: {app_opt.get('title')} ({app_opt.get('year')})")

        feedback_note = "\n".join(
            note for note in ([post.get("review_note", "") for post in grouped_targets] + avoid_notes) if note
        )
        manual_background_url = next(
            (normalize_text(post.get("manual_background_url", "")) for post in grouped_targets if normalize_text(post.get("manual_background_url", ""))),
            "",
        )

        print(f"[{lang}] A regenerar {date_str} com {len(matching_news)} noticias.")
        options_list = rank_all_stories_for_day(
            matching_news,
            lang,
            feedback_note=feedback_note,
        )
        if not options_list:
            print(f"[{lang}] Falha da IA em {date_str}.")
            continue

        external_suggestions = generate_external_day_suggestions(post_date, lang, options_list)
        slot1_base_options = options_list[:5]
        slot2_base_options = options_list[5:10] if len(options_list) > 5 else options_list

        for sibling in siblings:
            if sibling.get("status") == "approved" and sibling.get("review_action") != "regenerate":
                continue
            slot = int(sibling.get("slot", 1))
            base_options = slot1_base_options if slot == 1 else slot2_base_options
            default_selected = 1 if slot == 2 and len(base_options) > 1 else 0
            current_selected = int(sibling.get("selected_option", default_selected) or default_selected)
            current_selected = current_selected if current_selected < len(base_options) else default_selected
            sibling_options = prepare_options_for_review(
                base_options,
                lang,
                date_str,
                manual_background_url=manual_background_url,
                matching_news=matching_news,
                selected_option_index=current_selected,
            )
            sibling["options"] = clone_options(sibling_options)
            sibling["external_suggestions"] = clone_options(external_suggestions)
            sibling["selected_option"] = current_selected
            sibling["status"] = "pending"
            sibling["review_action"] = ""
            sibling["last_regenerated_at"] = datetime.now().isoformat()
            sibling["regeneration_count"] = int(sibling.get("regeneration_count", 0) or 0) + 1
        changed = True

    return True, changed, determine_focus_month(targets, fallback_month="")


def generate_review_html(pending_posts, focus_month="", lang_filter="pt"):
    embedded_posts = json.dumps(pending_posts, ensure_ascii=False).replace("</", "<\\/")
    conditional_pool_data = json.dumps(load_json(CONDITIONAL_POOL_FILE, []), ensure_ascii=False).replace("</", "<\\/")
    month_options = json.dumps(
        sorted({post.get("date", "")[:7] for post in pending_posts if post.get("date") and post.get("lang") == lang_filter})
    )
    initial_focus_month = focus_month or determine_focus_month([post for post in pending_posts if post.get("lang") == lang_filter])
    review_output_path = REVIEW_HTML_FILES[lang_filter]
    html = f"""<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Notícias de Ontem · Painel Editorial ({lang_filter.upper()})</title>
    <style>
        :root {{
            color-scheme: dark;
            --bg: #0b1017;
            --bg-elev: #111823;
            --panel: #151e2b;
            --panel-soft: #1c2838;
            --panel-hover: #223044;
            --text: #f1f5f9;
            --muted: #94a3b8;
            --accent: #22c8d2;
            --accent-strong: #14b8a6;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --info: #38bdf8;
            --border: rgba(148, 163, 184, 0.16);
            --border-strong: rgba(148, 163, 184, 0.28);
            --shadow: 0 18px 40px rgba(2, 6, 23, 0.42);
            --radius-lg: 18px;
            --radius-md: 12px;
            --radius-sm: 8px;
        }}
        * {{ box-sizing: border-box; }}
        html {{
            container-type: scroll-state;
            scroll-behavior: smooth;
        }}
        :target {{
            scroll-margin-top: 5.5rem;
        }}
        body {{
            margin: 0;
            font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
            font-size: 1rem;
            line-height: 1.5;
            background: radial-gradient(circle at 15% 0%, rgba(34, 200, 210, 0.08), transparent 38%), var(--bg);
            color: var(--text);
        }}
        .visually-hidden {{
            position: absolute;
            clip-path: inset(50%);
            overflow: hidden;
            width: 1px;
            height: 1px;
            margin: -1px;
            padding: 0;
            border: 0;
            white-space: nowrap;
        }}
        :focus-visible {{
            outline: 3px solid var(--accent);
            outline-offset: 2px;
        }}

        /* Compact single-row sticky bar (<12% viewport) with scroll-down auto-hide */
        .top-bar {{
            position: sticky;
            top: 0;
            z-index: 30;
            background: rgba(11, 16, 23, 0.92);
            backdrop-filter: blur(14px);
            border-block-end: 1px solid var(--border);
            transition: transform 0.22s ease;
        }}
        @container scroll-state((scrolled: bottom) and (scrollable: top)) {{
            .top-bar {{
                transform: translateY(-100%);
            }}
        }}
        .top-bar:focus-within {{
            transform: none;
        }}
        .top-bar.is-hidden:not(:focus-within) {{
            transform: translateY(-100%);
        }}
        .top-bar-inner {{
            max-width: 1400px;
            margin-inline: auto;
            padding: 0.65rem 1.25rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.85rem;
            flex-wrap: wrap;
        }}
        .brand-cluster {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        .brand-mark {{
            width: 2.1rem;
            height: 2.1rem;
            border-radius: 10px;
            background: linear-gradient(135deg, var(--accent), #0ea5e9);
            color: #041016;
            font-weight: 900;
            font-size: 0.85rem;
            display: grid;
            place-items: center;
            letter-spacing: -0.03em;
        }}
        .brand-title {{
            margin: 0;
            font-size: 1.02rem;
            font-weight: 800;
            letter-spacing: -0.01em;
        }}
        .brand-sub {{
            font-size: 0.75rem;
            color: var(--muted);
            display: block;
        }}
        .summary-pills {{
            display: flex;
            align-items: center;
            gap: 0.45rem;
            flex-wrap: wrap;
        }}
        .stat-chip {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.3rem 0.65rem;
            border-radius: 999px;
            background: var(--panel-soft);
            border: 1px solid var(--border);
            font-size: 0.78rem;
            color: var(--muted);
            font-weight: 600;
        }}
        .stat-chip b {{
            color: var(--text);
            font-size: 0.85rem;
        }}
        .stat-chip.accent b {{ color: var(--accent); }}
        .stat-chip.success b {{ color: var(--success); }}
        .stat-chip.warn b {{ color: var(--warning); }}

        .top-actions {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
        }}
        .dirty-indicator {{
            font-size: 0.78rem;
            font-weight: 700;
            color: var(--warning);
            padding: 0.25rem 0.6rem;
            border-radius: 999px;
            background: rgba(245, 158, 11, 0.14);
            border: 1px solid rgba(245, 158, 11, 0.35);
        }}
        .dirty-indicator[hidden] {{ display: none; }}

        button, .btn-link {{
            appearance: none;
            border: 1px solid transparent;
            border-radius: var(--radius-sm);
            padding: 0.55rem 0.9rem;
            min-height: 44px;
            font: inherit;
            font-size: 0.86rem;
            font-weight: 700;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.4rem;
            text-decoration: none;
            transition: background 0.15s ease, border-color 0.15s ease, transform 0.1s ease;
        }}
        button.primary {{
            background: var(--accent);
            color: #041318;
        }}
        button.primary:hover {{ background: #36d6df; }}
        button.secondary, .btn-link {{
            background: var(--panel-soft);
            color: var(--text);
            border-color: var(--border-strong);
        }}
        button.secondary:hover, .btn-link:hover {{
            background: var(--panel-hover);
        }}
        button.approve-btn.is-active {{
            background: rgba(34, 197, 94, 0.2);
            color: #86efac;
            border-color: rgba(34, 197, 94, 0.55);
        }}
        button.pending-btn.is-active {{
            background: rgba(34, 200, 210, 0.18);
            color: var(--accent);
            border-color: rgba(34, 200, 210, 0.5);
        }}
        button.skip-btn.is-active {{
            background: rgba(239, 68, 68, 0.18);
            color: #fca5a5;
            border-color: rgba(239, 68, 68, 0.48);
        }}

        .page {{
            max-width: 1400px;
            margin-inline: auto;
            padding: 1.25rem;
        }}

        /* Filter & Day-Jump Control Panel */
        .control-strip {{
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 1rem 1.15rem;
            margin-block-end: 1.25rem;
            box-shadow: var(--shadow);
        }}
        .filter-row {{
            display: grid;
            grid-template-columns: auto minmax(160px, 200px) minmax(220px, 1fr) auto;
            gap: 0.85rem;
            align-items: end;
        }}
        .view-tabs {{
            display: inline-flex;
            background: var(--bg-elev);
            padding: 0.22rem;
            border-radius: 10px;
            border: 1px solid var(--border);
            gap: 0.2rem;
        }}
        .view-tab {{
            min-height: 42px;
            padding: 0.4rem 0.8rem;
            border-radius: 8px;
            background: transparent;
            color: var(--muted);
            font-size: 0.83rem;
            border: 0;
        }}
        .view-tab[aria-pressed="true"] {{
            background: var(--panel-soft);
            color: var(--text);
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
        }}
        .form-field {{
            display: flex;
            flex-direction: column;
            gap: 0.32rem;
        }}
        .form-field label {{
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: var(--muted);
        }}
        select, input[type="text"], input[type="url"], input[type="search"], textarea {{
            width: 100%;
            font-size: 1rem;
            line-height: 1.4;
            padding: 0.62rem 0.8rem;
            min-height: 48px;
            background: var(--bg-elev);
            color: var(--text);
            border: 1px solid var(--border-strong);
            border-radius: 10px;
            font-family: inherit;
        }}
        textarea {{
            min-height: 92px;
            resize: vertical;
        }}
        input[type="radio"], input[type="checkbox"] {{
            accent-color: var(--accent);
            width: 1.15rem;
            height: 1.15rem;
            cursor: pointer;
        }}
        @media (pointer: coarse) {{
            select, input[type="text"], input[type="url"], input[type="search"], button {{
                min-height: 52px;
            }}
        }}

        .day-jump-bar {{
            display: flex;
            align-items: center;
            gap: 0.45rem;
            overflow-x: auto;
            padding-block-start: 0.85rem;
            margin-block-start: 0.85rem;
            border-block-start: 1px solid var(--border);
            scrollbar-width: thin;
        }}
        .day-jump-bar:empty {{ display: none; }}
        .day-chip {{
            flex: 0 0 auto;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            background: var(--bg-elev);
            border: 1px solid var(--border);
            color: var(--text);
            text-decoration: none;
            font-size: 0.8rem;
            font-weight: 600;
            min-height: 36px;
        }}
        .day-chip:hover {{ border-color: var(--accent); }}
        .day-chip.is-complete {{
            border-color: rgba(34, 197, 94, 0.45);
            background: rgba(34, 197, 94, 0.1);
            color: #bbf7d0;
        }}

        .secondary-drawers {{
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
            margin-block-start: 0.75rem;
        }}
        details.disclosure {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 0.65rem 0.9rem;
            width: 100%;
        }}
        details.disclosure > summary {{
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 700;
            color: var(--accent);
            user-select: none;
            padding-block: 0.15rem;
        }}
        details.disclosure[open] > summary {{
            margin-block-end: 0.75rem;
            padding-block-end: 0.55rem;
            border-block-end: 1px solid var(--border);
        }}

        /* Post Cards */
        .post-card {{
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            margin-block-end: 1.5rem;
            overflow: hidden;
            box-shadow: var(--shadow);
        }}
        /* Deferred rendering strictly for off-screen cards below the initial fold */
        .post-card-deferred {{
            content-visibility: auto;
            contain-intrinsic-size: auto none auto 720px;
        }}
        .post-card.status-approved {{ border-color: rgba(34, 197, 94, 0.45); }}
        .post-card.needs-refresh {{ border-color: rgba(245, 158, 11, 0.6); }}

        .post-header {{
            padding: 0.9rem 1.25rem;
            background: rgba(15, 23, 36, 0.85);
            border-block-end: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
        }}
        .post-slot-meta {{
            display: flex;
            align-items: center;
            gap: 0.65rem;
            flex-wrap: wrap;
        }}
        .slot-date-badge {{
            font-size: 0.95rem;
            font-weight: 800;
            color: var(--text);
        }}
        .slot-num-badge {{
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding: 0.24rem 0.58rem;
            border-radius: 6px;
            background: var(--panel-soft);
            color: var(--muted);
        }}
        .status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            padding: 0.28rem 0.68rem;
            border-radius: 999px;
        }}
        .status-badge.pending {{ background: rgba(56, 189, 248, 0.14); color: var(--info); }}
        .status-badge.approved {{ background: rgba(34, 197, 94, 0.16); color: #86efac; }}
        .status-badge.published {{ background: rgba(168, 85, 247, 0.18); color: #d8b4fe; }}
        .status-badge.skip {{ background: rgba(239, 68, 68, 0.16); color: #fca5a5; }}
        .status-badge.refresh {{ background: rgba(245, 158, 11, 0.18); color: #fcd34d; }}

        .quick-status-group {{
            display: flex;
            align-items: center;
            gap: 0.45rem;
            flex-wrap: wrap;
        }}
        .quick-status-group button {{
            min-height: 40px;
            padding: 0.4rem 0.75rem;
            font-size: 0.81rem;
        }}

        .post-body {{
            display: grid;
            grid-template-columns: 360px minmax(0, 1fr);
            gap: 1.5rem;
            padding: 1.25rem;
            align-items: start;
        }}
        .media-column {{
            position: sticky;
            top: 4.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }}
        .image-wrap {{
            background: #070b10;
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid var(--border-strong);
            aspect-ratio: 4 / 5;
            display: grid;
            place-items: center;
            position: relative;
        }}
        .image-wrap img {{
            display: block;
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .source-verify-card {{
            background: var(--bg-elev);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 0.75rem 0.85rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            font-size: 0.82rem;
        }}
        .source-status-line {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
            font-weight: 700;
        }}
        .source-ok {{ color: #86efac; }}
        .source-warn {{ color: #fcd34d; }}
        .source-links {{
            display: flex;
            gap: 0.45rem;
            flex-wrap: wrap;
        }}
        .source-links a {{
            font-size: 0.78rem;
            padding: 0.35rem 0.65rem;
            min-height: 36px;
        }}

        /* Right Column Content */
        .editorial-column {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
            min-width: 0;
        }}
        .meta-row {{
            display: flex;
            gap: 0.45rem;
            flex-wrap: wrap;
            align-items: center;
        }}
        .pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.26rem 0.65rem;
            border-radius: 999px;
            background: rgba(34, 200, 210, 0.13);
            color: var(--accent);
            font-size: 0.76rem;
            font-weight: 700;
        }}
        .pill.rel-1, .pill.rel-2 {{ background: rgba(245, 158, 11, 0.18); color: #fcd34d; }}
        .pill.rel-3 {{ background: rgba(56, 189, 248, 0.16); color: #7dd3fc; }}
        .pill.rel-4, .pill.rel-5 {{ background: rgba(148, 163, 184, 0.16); color: #cbd5e1; }}
        .pill.warning {{ background: rgba(245, 158, 11, 0.2); color: #fcd34d; }}

        .headline {{
            font-size: clamp(1.35rem, 2.1vw, 1.85rem);
            line-height: 1.15;
            font-weight: 800;
            margin: 0;
            letter-spacing: -0.02em;
        }}
        .overlay-lead {{
            margin: 0.35rem 0 0;
            color: #cbd5e1;
            font-size: 0.95rem;
        }}
        .en-preview-box {{
            background: rgba(56, 189, 248, 0.06);
            border: 1px solid rgba(56, 189, 248, 0.2);
            border-radius: var(--radius-md);
            padding: 0.65rem 0.85rem;
            font-size: 0.85rem;
        }}
        .en-preview-box strong {{
            color: #bae6fd;
            display: block;
            margin-block-end: 0.15rem;
        }}
        .en-preview-box span {{ color: var(--muted); }}

        .caption-box {{
            background: var(--bg-elev);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 0.8rem 0.95rem;
        }}
        .caption-tabs {{
            display: flex;
            gap: 0.4rem;
            margin-block-end: 0.55rem;
        }}
        .caption-tab {{
            min-height: 32px;
            padding: 0.2rem 0.65rem;
            font-size: 0.76rem;
            border-radius: 999px;
            background: var(--panel-soft);
            color: var(--muted);
        }}
        .caption-tab.is-active {{
            background: rgba(34, 200, 210, 0.18);
            color: var(--accent);
            border-color: rgba(34, 200, 210, 0.45);
        }}
        .caption-text {{
            white-space: pre-wrap;
            font-size: 0.88rem;
            color: #dbe6f0;
            line-height: 1.55;
            max-height: 180px;
            overflow-y: auto;
        }}

        /* Visible Radio Option Cards (1-5 options) */
        .options-fieldset {{
            border: 0;
            padding: 0;
            margin: 0;
        }}
        .options-legend {{
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--muted);
            margin-block-end: 0.55rem;
        }}
        .options-list {{
            display: grid;
            gap: 0.55rem;
        }}
        .option-item {{
            display: grid;
            grid-template-columns: auto minmax(0, 1fr) auto;
            gap: 0.8rem;
            align-items: start;
            padding: 0.75rem 0.9rem;
            border-radius: var(--radius-md);
            background: var(--bg-elev);
            border: 1px solid var(--border);
            cursor: pointer;
            transition: border-color 0.15s ease, background 0.15s ease;
        }}
        .option-item:hover {{
            border-color: var(--border-strong);
            background: rgba(30, 41, 59, 0.65);
        }}
        .option-item.is-selected {{
            border-color: var(--accent);
            background: rgba(34, 200, 210, 0.08);
        }}
        .option-item input[type="radio"] {{
            margin-block-start: 0.2rem;
        }}
        .option-copy {{
            min-width: 0;
            font-size: 0.84rem;
            color: var(--muted);
        }}
        .option-head-line {{
            display: flex;
            align-items: center;
            gap: 0.45rem;
            flex-wrap: wrap;
            margin-block-end: 0.2rem;
        }}
        .option-year {{
            font-weight: 800;
            color: var(--accent);
            font-size: 0.82rem;
        }}
        .option-title {{
            display: block;
            color: var(--text);
            font-weight: 700;
            font-size: 0.93rem;
            margin-block-end: 0.2rem;
        }}
        .option-thumb {{
            width: 56px;
            height: 70px;
            border-radius: 8px;
            overflow: hidden;
            background: #090d13;
            border: 1px solid var(--border);
            flex-shrink: 0;
        }}
        .option-thumb img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }}

        .controls-grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.85rem;
        }}
        .controls-stack {{
            display: grid;
            gap: 0.85rem;
            margin-block-start: 0.85rem;
        }}
        .empty {{
            color: var(--muted);
            text-align: center;
            padding: 2rem 1rem;
            background: var(--panel);
            border-radius: var(--radius-lg);
            border: 1px dashed var(--border-strong);
        }}

        .toast {{
            position: fixed;
            inset-block-end: 1.25rem;
            inset-inline-end: 1.25rem;
            z-index: 60;
            background: #0f172a;
            color: var(--text);
            border: 1px solid var(--accent);
            border-radius: 12px;
            padding: 0.7rem 1rem;
            font-size: 0.86rem;
            font-weight: 700;
            box-shadow: var(--shadow);
            opacity: 0;
            transform: translateY(8px);
            pointer-events: none;
            transition: opacity 0.18s ease, transform 0.18s ease;
        }}
        .toast.is-visible {{
            opacity: 1;
            transform: translateY(0);
        }}

        @media (max-width: 1024px) {{
            .filter-row {{
                grid-template-columns: 1fr 1fr;
            }}
            .post-body {{
                grid-template-columns: 1fr;
            }}
            .media-column {{
                position: static;
                max-width: 420px;
            }}
        }}
        @media (max-width: 640px) {{
            .filter-row, .controls-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <header class="top-bar" id="top-bar">
        <div class="top-bar-inner">
            <div class="brand-cluster">
                <div class="brand-mark" aria-hidden="true">NO</div>
                <div>
                    <h1 class="brand-title">Painel de Aprovação · {lang_filter.upper()}</h1>
                    <span class="brand-sub">Curadoria PT + espelho automático EN (Site, IG &amp; FB/Buffer)</span>
                </div>
            </div>
            <div class="summary-pills" id="summary"></div>
            <div class="top-actions">
                <span class="dirty-indicator" id="dirty-badge" hidden>● Alterações por guardar</span>
                <button type="button" class="primary" id="btn-save-direct">💾 Guardar no pending_posts.json</button>
                <button type="button" class="secondary" id="btn-approve-visible">✓ Aprovar visíveis</button>
                <button type="button" class="secondary" id="btn-download-json">⬇ JSON</button>
            </div>
        </div>
    </header>

    <main class="page" id="app-main">
        <section class="control-strip" aria-label="Filtros e navegação">
            <div class="filter-row">
                <div class="form-field">
                    <label id="view-mode-label">Vista</label>
                    <div class="view-tabs" role="group" aria-labelledby="view-mode-label">
                        <button type="button" class="view-tab" data-view-mode="open" aria-pressed="true">Por aprovar</button>
                        <button type="button" class="view-tab" data-view-mode="approved" aria-pressed="false">Aprovados</button>
                        <button type="button" class="view-tab" data-view-mode="all" aria-pressed="false">Todos</button>
                    </div>
                </div>
                <div class="form-field">
                    <label for="month-filter">Mês</label>
                    <select id="month-filter" name="month_filter"></select>
                </div>
                <div class="form-field">
                    <label for="search-filter">Pesquisar notícia, ano, categoria ou nota</label>
                    <input type="search" id="search-filter" name="search_filter" placeholder="Ex.: 2008, educação, orçamento, Arquivo.pt..." autocorrect="off" autocapitalize="off" spellcheck="false" enterkeyhint="search">
                </div>
                <div class="form-field">
                    <label for="btn-copy-json">Área de transferência</label>
                    <button type="button" class="secondary" id="btn-copy-json">📋 Copiar JSON</button>
                </div>
            </div>

            <nav class="day-jump-bar" id="day-jump-bar" aria-label="Saltar para dia"></nav>

            <div class="secondary-drawers">
                <details class="disclosure">
                    <summary>Bolsa de Eventos Condicionais (Clássicos / Taça / Campeonato / Eleições)</summary>
                    <div id="conditional-pool-panel" style="display:grid; gap:0.55rem;"></div>
                </details>
                <details class="disclosure">
                    <summary>Como funciona o fluxo de aprovação &amp; sincronização EN</summary>
                    <p style="margin:0; color:var(--muted); font-size:0.86rem;">
                        1. Escolhe a opção pretendida em cada slot (as opções estão ordenadas por relevância histórica, impacto concreto em Portugal, distância temporal e verificação no Arquivo.pt).<br>
                        2. Clica em <strong>✓ Aprovar</strong> no topo do cartão (ou pede <strong>↻ Nova imagem</strong> / <strong>✦ Regenerar IA</strong>) e depois em <strong>💾 Guardar no pending_posts.json</strong>.<br>
                        3. Todos os slots aprovados em PT geram automaticamente a versão inglesa espelhada (capa EN + título/resumo/artigo EN + CTAs específicas para Instagram e Facebook/Buffer).
                    </p>
                </details>
            </div>
        </section>

        <div id="posts-root"></div>

        <details class="disclosure" style="margin-block-top:1.5rem;">
            <summary>Inspecionar JSON bruto atualizado (pending_posts.json)</summary>
            <div class="form-field">
                <label for="json-preview">Conteúdo completo do ficheiro</label>
                <textarea id="json-preview" readonly style="min-height:220px; font-family:Consolas, monospace; font-size:0.82rem;"></textarea>
            </div>
        </details>
    </main>

    <div class="toast" id="toast" role="status" aria-live="polite"></div>

    <script>
        const posts = {embedded_posts};
        const conditionalPool = {conditional_pool_data};
        const monthOptions = {month_options};
        const initialFocusMonth = {json.dumps(initial_focus_month)};
        const fixedLang = {json.dumps(lang_filter)};
        const templateOptions = [
            ["", "Automático (IA + legibilidade)"],
            ["template_1", "Template 1 · Editorial Clássico"],
            ["template_2", "Template 2 · Destaque Topo"],
            ["template_3", "Template 3 · Caixa Moderna"],
            ["template_4", "Template 4 · Minimalista"],
            ["breaking", "Template Especial · Última Hora"],
        ];
        const reviewActionOptions = [
            ["", "Manter como está"],
            ["refresh_image", "↻ Pedir nova imagem de fundo"],
            ["regenerate", "✦ Regenerar opções com IA (NVIDIA)"],
        ];
        const relevanceLabels = {{
            1: "Nível 1 · Marco Histórico",
            2: "Nível 2 · Grande Relevância",
            3: "Nível 3 · Relevância Nacional",
            4: "Nível 4 · Interesse Público",
            5: "Nível 5 · Memória do Dia",
        }};
        const uiState = {{
            viewMode: "open",
            monthFilter: initialFocusMonth || "",
            search: "",
            captionPlatformByPost: {{}},
            dirty: false,
            fileHandle: null,
        }};

        function escapeHtml(value) {{
            return String(value ?? "")
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#39;");
        }}

        let toastTimer = null;
        function showToast(message) {{
            const el = document.getElementById("toast");
            if (!el) return;
            el.textContent = message;
            el.classList.add("is-visible");
            clearTimeout(toastTimer);
            toastTimer = setTimeout(() => el.classList.remove("is-visible"), 2600);
        }}

        function markDirty(isDirty = true) {{
            uiState.dirty = isDirty;
            const badge = document.getElementById("dirty-badge");
            if (badge) badge.hidden = !isDirty;
        }}

        function selectedOption(post) {{
            const options = Array.isArray(post.options) ? post.options : [];
            return options[post.selected_option] || options[0] || null;
        }}

        function monthKey(post) {{
            return String(post.date || "").slice(0, 7);
        }}

        function isOpenPost(post) {{
            const status = post.status || "pending";
            return ["regenerate", "refresh_image"].includes(post.review_action || "") || !["approved", "published", "skip"].includes(status);
        }}

        function matchesFilters(post, option) {{
            if ((post.lang || "") !== fixedLang) return false;
            const status = post.status || "pending";
            if (uiState.viewMode === "open" && !isOpenPost(post)) return false;
            if (uiState.viewMode === "approved" && status !== "approved") return false;
            if (uiState.monthFilter && monthKey(post) !== uiState.monthFilter) return false;
            if (!uiState.search) return true;
            const haystack = [
                post.date,
                post.id,
                post.theme_suggestion,
                post.manual_background_url,
                post.review_note,
                option?.title,
                option?.title_en,
                option?.caption,
                option?.summary,
                option?.category,
                option?.year,
                option?.image_theme,
                option?.article_url,
                ...(Array.isArray(post.options) ? post.options.flatMap(o => [o?.title, o?.title_en, o?.year, o?.category]) : []),
                ...(Array.isArray(post.external_suggestions) ? post.external_suggestions.flatMap(item => [item?.title, item?.summary, item?.category, item?.year]) : []),
            ].join(" ").toLowerCase();
            return haystack.includes(uiState.search.toLowerCase());
        }}

        function formatPtDateShort(dateStr) {{
            const parts = String(dateStr || "").split("-");
            if (parts.length !== 3) return dateStr;
            const months = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
            const m = parseInt(parts[1], 10);
            return `${{parts[2]}} ${{months[m - 1] || parts[1]}}`;
        }}

        function resolvePreviewSrc(opt) {{
            if (!opt) return "";
            const localPath = String(opt.local_image_path || "").replace(/\\\\/g, "/");
            if (window.location.protocol === "file:" && localPath) {{
                return localPath;
            }}
            return opt.image_url || localPath || "";
        }}

        function updateSummaryAndDays() {{
            const counts = {{ total: 0, open: 0, approved: 0, published: 0, refresh: 0 }};
            const byDate = new Map();
            posts.forEach(post => {{
                if ((post.lang || "") !== fixedLang) return;
                counts.total += 1;
                const st = post.status || "pending";
                if (isOpenPost(post)) counts.open += 1;
                if (st === "approved") counts.approved += 1;
                if (st === "published") counts.published += 1;
                if (["regenerate", "refresh_image"].includes(post.review_action || "")) counts.refresh += 1;

                if (!uiState.monthFilter || monthKey(post) === uiState.monthFilter) {{
                    const d = post.date || "";
                    if (d) {{
                        const rec = byDate.get(d) || {{ total: 0, done: 0, visible: false }};
                        rec.total += 1;
                        if (["approved", "published", "skip"].includes(st) && !["regenerate", "refresh_image"].includes(post.review_action || "")) {{
                            rec.done += 1;
                        }}
                        if (matchesFilters(post, selectedOption(post))) {{
                            rec.visible = true;
                        }}
                        byDate.set(d, rec);
                    }}
                }}
            }});

            document.getElementById("summary").innerHTML = `
                <span class="stat-chip accent">Por aprovar <b>${{counts.open}}</b></span>
                <span class="stat-chip success">Aprovados <b>${{counts.approved}}</b></span>
                <span class="stat-chip">Publicados <b>${{counts.published}}</b></span>
                ${{counts.refresh ? `<span class="stat-chip warn">Para refresh <b>${{counts.refresh}}</b></span>` : ""}}
            `;

            const dayBar = document.getElementById("day-jump-bar");
            const visibleDates = Array.from(byDate.entries()).filter(([, info]) => info.visible);
            dayBar.innerHTML = visibleDates.map(([dateStr, info]) => {{
                const complete = info.done >= info.total && info.total > 0;
                const icon = complete ? "✓" : `${{info.done}}/${{info.total}}`;
                return `<a class="day-chip ${{complete ? "is-complete" : ""}}" href="#day-${{escapeHtml(dateStr)}}">${{escapeHtml(formatPtDateShort(dateStr))}} · ${{icon}}</a>`;
            }}).join("");

            document.querySelectorAll(".view-tab[data-view-mode]").forEach(btn => {{
                btn.setAttribute("aria-pressed", btn.dataset.viewMode === uiState.viewMode ? "true" : "false");
            }});
        }}

        function refreshJsonPreview() {{
            const preview = document.getElementById("json-preview");
            if (preview) preview.value = JSON.stringify(posts, null, 2);
        }}

        function fillMonthFilter() {{
            const select = document.getElementById("month-filter");
            if (!select) return;
            select.innerHTML = [`<option value="">Todos os meses</option>`]
                .concat(monthOptions.map(month => {{
                    const selected = uiState.monthFilter === month ? "selected" : "";
                    return `<option value="${{escapeHtml(month)}}" ${{selected}}>${{escapeHtml(month)}}</option>`;
                }}))
                .join("");
        }}

        function statusLabelAndClass(post) {{
            const action = post.review_action || "";
            if (action === "regenerate") return ["✦ Regenerar IA", "refresh"];
            if (action === "refresh_image") return ["↻ Nova imagem", "refresh"];
            const st = post.status || "pending";
            if (st === "approved") return ["✓ Aprovado", "approved"];
            if (st === "published") return ["🚀 Publicado", "published"];
            if (st === "skip") return ["⏭ Ignorado", "skip"];
            return ["⏳ Por aprovar", "pending"];
        }}

        function render() {{
            updateSummaryAndDays();
            fillMonthFilter();
            const root = document.getElementById("posts-root");
            const seenDayAnchors = new Set();
            let visibleIndex = 0;

            const visibleCards = posts.map((post, postIndex) => {{
                const option = selectedOption(post);
                if (!matchesFilters(post, option)) return "";

                const isDeferred = visibleIndex >= 2;
                visibleIndex += 1;

                const dateStr = post.date || "";
                let dayAnchorAttr = "";
                if (dateStr && !seenDayAnchors.has(dateStr)) {{
                    seenDayAnchors.add(dateStr);
                    dayAnchorAttr = `id="day-${{escapeHtml(dateStr)}}"`;
                }}

                const [badgeText, badgeClass] = statusLabelAndClass(post);
                const statusVal = post.status || "pending";
                const cardClasses = [
                    "post-card",
                    isDeferred ? "post-card-deferred" : "",
                    statusVal === "approved" ? "status-approved" : "",
                    ["regenerate", "refresh_image"].includes(post.review_action || "") ? "needs-refresh" : "",
                ].filter(Boolean).join(" ");

                const previewSrc = resolvePreviewSrc(option);
                const imageMarkup = previewSrc
                    ? `<div class="image-wrap"><img src="${{escapeHtml(previewSrc)}}" alt="Pré-visualização ${{escapeHtml(option?.title || "")}}" width="1080" height="1350" loading="${{isDeferred ? "lazy" : "eager"}}"></div>`
                    : `<div class="image-wrap"><div style="padding:1.5rem; text-align:center; color:var(--muted); font-size:0.88rem;">Sem imagem renderizada para esta opção.<br><strong style="color:var(--warning);">Guarda com "↻ Pedir nova imagem" e corre o pregenerator.</strong></div></div>`;

                const articleUrl = String(option?.article_url || "");
                const hasWayback = articleUrl.toLowerCase().includes("arquivo.pt/wayback/");
                const bgSourceUrl = String(option?.background_source_url || "");
                const sourceVerifyMarkup = `
                    <div class="source-verify-card">
                        <div class="source-status-line">
                            <span class="${{hasWayback ? "source-ok" : "source-warn"}}">
                                ${{hasWayback ? "✓ Notícia preservada no Arquivo.pt" : (articleUrl ? "ℹ Fonte web direta (sem captura wayback)" : "⚠ Efeméride histórica sem link web")}}
                            </span>
                            <span>${{escapeHtml(option?.year || "")}}</span>
                        </div>
                        <div class="source-links">
                            ${{articleUrl ? `<a class="btn-link" href="${{escapeHtml(articleUrl)}}" target="_blank" rel="noreferrer">🔗 Ver notícia original ↗</a>` : ""}}
                            ${{bgSourceUrl && bgSourceUrl.startsWith("http") ? `<a class="btn-link" href="${{escapeHtml(bgSourceUrl)}}" target="_blank" rel="noreferrer">🖼️ Fonte da foto ↗</a>` : ""}}
                            ${{previewSrc ? `<a class="btn-link" href="${{escapeHtml(previewSrc)}}" target="_blank" rel="noreferrer">🔍 Abrir capa 4:5 ↗</a>` : ""}}
                        </div>
                    </div>
                `;

                const relLevel = Number(option?.relevance?.level || 4);
                const relScore = option?.relevance?.weighted_score != null ? Number(option.relevance.weighted_score).toFixed(1) : "";
                const relText = `${{relevanceLabels[relLevel] || `Nível ${{relLevel}}`}}${{relScore ? ` (${{relScore}})` : ""}}`;
                const nets = Array.isArray(option?.networks) && option.networks.length ? option.networks.join(" + ").toUpperCase() : "INSTAGRAM + FACEBOOK";

                const pills = [
                    option?.year ? `<span class="pill">📅 ${{escapeHtml(option.year)}}</span>` : "",
                    option?.category ? `<span class="pill">${{escapeHtml(option.category)}}</span>` : "",
                    `<span class="pill rel-${{relLevel}}">★ ${{escapeHtml(relText)}}</span>`,
                    `<span class="pill">📣 ${{escapeHtml(nets)}}</span>`,
                    option?.layout_preference ? `<span class="pill">Layout: ${{escapeHtml(option.layout_preference)}}</span>` : "",
                    (post.review_action === "regenerate") ? `<span class="pill warning">✦ A regenerar no próximo run</span>` : "",
                    (post.review_action === "refresh_image") ? `<span class="pill warning">↻ A gerar nova imagem no próximo run</span>` : "",
                ].filter(Boolean).join("");

                const activeCapTab = uiState.captionPlatformByPost[postIndex] || "ig";
                const igCap = option?.caption_instagram || option?.caption || "";
                const fbCap = option?.caption_facebook || option?.caption || "";
                const shownCaption = activeCapTab === "fb" ? fbCap : igCap;

                const optionsMarkup = (post.options || []).map((opt, optionIndex) => {{
                    const isSel = optionIndex === Number(post.selected_option || 0);
                    const optThumbSrc = resolvePreviewSrc(opt);
                    const optLevel = Number(opt?.relevance?.level || 4);
                    const optScore = opt?.relevance?.weighted_score != null ? Number(opt.relevance.weighted_score).toFixed(0) : "";
                    const optWayback = String(opt?.article_url || "").toLowerCase().includes("arquivo.pt/wayback/");
                    const radioId = `opt-${{postIndex}}-${{optionIndex}}`;
                    return `
                        <label class="option-item ${{isSel ? "is-selected" : ""}}" for="${{radioId}}">
                            <input type="radio" id="${{radioId}}" name="selected-option-${{postIndex}}" value="${{optionIndex}}" ${{isSel ? "checked" : ""}} data-action="select-option" data-post-index="${{postIndex}}">
                            <div class="option-copy">
                                <div class="option-head-line">
                                    <span class="option-year">Opção ${{optionIndex + 1}} · ${{escapeHtml(opt.year || "")}}</span>
                                    ${{opt.category ? `<span class="pill" style="padding:0.12rem 0.5rem; font-size:0.7rem;">${{escapeHtml(opt.category)}}</span>` : ""}}
                                    <span class="pill rel-${{optLevel}}" style="padding:0.12rem 0.5rem; font-size:0.7rem;">L${{optLevel}}${{optScore ? ` · ${{optScore}}` : ""}}</span>
                                    ${{optWayback ? `<span style="color:#86efac; font-size:0.74rem; font-weight:700;">Arquivo.pt ✓</span>` : ""}}
                                </div>
                                <span class="option-title">${{escapeHtml(opt.title || "")}}</span>
                                <div>${{escapeHtml(opt.summary || opt.overlay_description || "")}}</div>
                            </div>
                            ${{optThumbSrc ? `<div class="option-thumb"><img src="${{escapeHtml(optThumbSrc)}}" alt="" width="56" height="70" loading="lazy"></div>` : `<div></div>`}}
                        </label>
                    `;
                }}).join("") || `<div class="empty">Sem opções disponíveis neste slot.</div>`;

                const layoutMarkup = templateOptions.map(([value, label]) => {{
                    const selected = (post.layout_override || "") === value ? "selected" : "";
                    return `<option value="${{escapeHtml(value)}}" ${{selected}}>${{escapeHtml(label)}}</option>`;
                }}).join("");

                const reviewActionMarkup = reviewActionOptions.map(([value, label]) => {{
                    const selected = (post.review_action || "") === value ? "selected" : "";
                    return `<option value="${{escapeHtml(value)}}" ${{selected}}>${{escapeHtml(label)}}</option>`;
                }}).join("");

                const hasCustomOverrides = Boolean(post.theme_suggestion || post.manual_background_url || post.review_note || post.layout_override || post.review_action);

                const externalSuggestionsMarkup = (post.external_suggestions || []).map((suggestion, suggestionIndex) => `
                    <div class="option-item" style="grid-template-columns: minmax(0, 1fr) auto; cursor:default;">
                        <div class="option-copy">
                            <div class="option-head-line">
                                <span class="option-year">${{escapeHtml(suggestion.year || "")}}</span>
                                ${{suggestion.category ? `<span class="pill" style="padding:0.12rem 0.5rem; font-size:0.7rem;">${{escapeHtml(suggestion.category)}}</span>` : ""}}
                            </div>
                            <span class="option-title">${{escapeHtml(suggestion.title || "")}}</span>
                            <div>${{escapeHtml(suggestion.summary || "")}}</div>
                        </div>
                        <button type="button" class="secondary" style="min-height:38px; font-size:0.78rem;" data-action="use-external" data-post-index="${{postIndex}}" data-sug-index="${{suggestionIndex}}">Usar sugestão</button>
                    </div>
                `).join("") || `<div style="color:var(--muted); font-size:0.84rem;">Sem sugestões externas guardadas para este dia.</div>`;

                return `
                    <article class="${{cardClasses}}" ${{dayAnchorAttr}}>
                        <div class="post-header">
                            <div class="post-slot-meta">
                                <span class="slot-date-badge">${{escapeHtml(dateStr)}}</span>
                                <span class="slot-num-badge">Slot ${{escapeHtml(post.slot || 1)}}/2 · ${{escapeHtml(post.id || "")}}</span>
                                <span class="status-badge ${{badgeClass}}">${{badgeText}}</span>
                            </div>
                            <div class="quick-status-group" role="group" aria-label="Decisão editorial rápida">
                                <button type="button" class="secondary approve-btn ${{statusVal === "approved" && !post.review_action ? "is-active" : ""}}" data-action="quick-status" data-post-index="${{postIndex}}" data-status="approved">✓ Aprovar</button>
                                <button type="button" class="secondary pending-btn ${{statusVal === "pending" && !post.review_action ? "is-active" : ""}}" data-action="quick-status" data-post-index="${{postIndex}}" data-status="pending">⏳ Pendente</button>
                                <button type="button" class="secondary" data-action="quick-refresh" data-post-index="${{postIndex}}" data-refresh="refresh_image">↻ Nova imagem</button>
                                <button type="button" class="secondary" data-action="quick-refresh" data-post-index="${{postIndex}}" data-refresh="regenerate">✦ Regenerar IA</button>
                                <button type="button" class="secondary skip-btn ${{statusVal === "skip" ? "is-active" : ""}}" data-action="quick-status" data-post-index="${{postIndex}}" data-status="skip">⏭ Saltar</button>
                            </div>
                        </div>

                        <div class="post-body">
                            <div class="media-column">
                                ${{imageMarkup}}
                                ${{sourceVerifyMarkup}}
                            </div>

                            <div class="editorial-column">
                                ${{option ? `
                                    <div class="meta-row">${{pills}}</div>
                                    <div>
                                        <h2 class="headline">${{escapeHtml(option.title || "")}}</h2>
                                        ${{option.overlay_description ? `<p class="overlay-lead">${{escapeHtml(option.overlay_description)}}</p>` : ""}}
                                    </div>
                                    <div class="en-preview-box">
                                        <strong>🇬🇧 EN · ${{escapeHtml(option.title_en || "(tradução EN gerada automaticamente ao aprovar)")}}</strong>
                                        <span>${{escapeHtml(option.summary_en || "")}}</span>
                                    </div>
                                    <div class="caption-box">
                                        <div class="caption-tabs" role="tablist" aria-label="Plataforma da legenda">
                                            <button type="button" class="caption-tab ${{activeCapTab === "ig" ? "is-active" : ""}}" data-action="switch-caption-tab" data-post-index="${{postIndex}}" data-tab="ig">Instagram (bio)</button>
                                            <button type="button" class="caption-tab ${{activeCapTab === "fb" ? "is-active" : ""}}" data-action="switch-caption-tab" data-post-index="${{postIndex}}" data-tab="fb">Facebook · Buffer (sobre)</button>
                                        </div>
                                        <div class="caption-text">${{escapeHtml(shownCaption)}}</div>
                                    </div>
                                ` : `<div class="empty">Sem opção selecionada.</div>`}}

                                <form class="slot-controls" data-slot-form="${{postIndex}}">
                                    <fieldset class="options-fieldset">
                                        <legend class="options-legend">Escolher notícia para este slot (${{(post.options || []).length}} opções)</legend>
                                        <div class="options-list">
                                            ${{optionsMarkup}}
                                        </div>
                                    </fieldset>

                                    <details class="disclosure" style="margin-block-start:0.85rem;" ${{hasCustomOverrides ? "open" : ""}}>
                                        <summary>Personalizar template, imagem de fundo ou nota de regeneração IA</summary>
                                        <div class="controls-grid">
                                            <div class="form-field">
                                                <label for="layout-${{postIndex}}">Template visual da capa</label>
                                                <select id="layout-${{postIndex}}" name="layout_override" data-field="layout_override" data-post-index="${{postIndex}}">${{layoutMarkup}}</select>
                                            </div>
                                            <div class="form-field">
                                                <label for="action-${{postIndex}}">Ação para o próximo pregenerator</label>
                                                <select id="action-${{postIndex}}" name="review_action" data-field="review_action" data-post-index="${{postIndex}}">${{reviewActionMarkup}}</select>
                                            </div>
                                        </div>
                                        <div class="controls-stack">
                                            <div class="form-field">
                                                <label for="theme-${{postIndex}}">Sugestão manual de tema visual (pesquisa de fotografia)</label>
                                                <input type="text" id="theme-${{postIndex}}" name="theme_suggestion" value="${{escapeHtml(post.theme_suggestion || "")}}" placeholder="Ex.: Assembleia da República Lisboa, sala de aula anos 2000..." data-field="theme_suggestion" data-post-index="${{postIndex}}">
                                            </div>
                                            <div class="form-field">
                                                <label for="bgurl-${{postIndex}}">Link direto para imagem de fundo (opcional)</label>
                                                <input type="url" id="bgurl-${{postIndex}}" name="manual_background_url" value="${{escapeHtml(post.manual_background_url || "")}}" placeholder="https://..." autocorrect="off" autocapitalize="off" spellcheck="false" data-field="manual_background_url" data-post-index="${{postIndex}}">
                                            </div>
                                            <div class="form-field">
                                                <label for="note-${{postIndex}}">Nota editorial para regeneração seletiva</label>
                                                <textarea id="note-${{postIndex}}" name="review_note" placeholder="Ex.: procurar uma notícia portuguesa de economia/sociedade entre 2000 e 2015, evitar Covid..." data-field="review_note" data-post-index="${{postIndex}}">${{escapeHtml(post.review_note || "")}}</textarea>
                                            </div>
                                        </div>
                                    </details>

                                    ${{option ? `
                                    <details class="disclosure" style="margin-block-start:0.65rem;">
                                        <summary>Editar rapidamente texto PT / EN ou link da opção selecionada</summary>
                                        <div class="controls-stack" style="margin-block-start:0;">
                                            <div class="controls-grid">
                                                <div class="form-field">
                                                    <label for="opt-title-${{postIndex}}">Título PT (nota: alterar título pede nova capa se quiseres atualizar a imagem)</label>
                                                    <input type="text" id="opt-title-${{postIndex}}" value="${{escapeHtml(option.title || "")}}" data-opt-field="title" data-post-index="${{postIndex}}">
                                                </div>
                                                <div class="form-field">
                                                    <label for="opt-title-en-${{postIndex}}">Título EN (US English)</label>
                                                    <input type="text" id="opt-title-en-${{postIndex}}" value="${{escapeHtml(option.title_en || "")}}" data-opt-field="title_en" data-post-index="${{postIndex}}">
                                                </div>
                                            </div>
                                            <div class="form-field">
                                                <label for="opt-url-${{postIndex}}">URL da fonte preservada (Arquivo.pt)</label>
                                                <input type="url" id="opt-url-${{postIndex}}" value="${{escapeHtml(option.article_url || "")}}" autocorrect="off" autocapitalize="off" spellcheck="false" data-opt-field="article_url" data-post-index="${{postIndex}}">
                                            </div>
                                        </div>
                                    </details>
                                    ` : ""}}

                                    <details class="disclosure" style="margin-block-start:0.65rem;">
                                        <summary>Sugestões externas de efemérides para este dia (${{(post.external_suggestions || []).length}})</summary>
                                        <div class="options-list">
                                            ${{externalSuggestionsMarkup}}
                                        </div>
                                    </details>
                                </form>
                            </div>
                        </div>
                    </article>
                `;
            }}).filter(Boolean);

            root.innerHTML = visibleCards.length
                ? visibleCards.join("")
                : `<div class="empty">Nenhum post corresponde aos filtros selecionados. Experimenta mudar a vista para <strong>Aprovados</strong> ou <strong>Todos</strong>.</div>`;
            refreshJsonPreview();
        }}

        function downloadJson() {{
            const blob = new Blob([JSON.stringify(posts, null, 2)], {{ type: "application/json" }});
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = "pending_posts.json";
            link.click();
            URL.revokeObjectURL(url);
            markDirty(false);
            showToast("pending_posts.json transferido.");
        }}

        async function saveDirect() {{
            const content = JSON.stringify(posts, null, 2);
            if (window.showSaveFilePicker) {{
                try {{
                    if (!uiState.fileHandle) {{
                        uiState.fileHandle = await window.showSaveFilePicker({{
                            suggestedName: "pending_posts.json",
                            types: [{{ description: "JSON", accept: {{ "application/json": [".json"] }} }}],
                        }});
                    }}
                    const writable = await uiState.fileHandle.createWritable();
                    await writable.write(content);
                    await writable.close();
                    markDirty(false);
                    showToast("✓ Guardado diretamente em pending_posts.json!");
                    return;
                }} catch (error) {{
                    if (error && error.name === "AbortError") return;
                    uiState.fileHandle = null;
                    console.warn(error);
                }}
            }}
            downloadJson();
        }}

        async function copyJson() {{
            const content = JSON.stringify(posts, null, 2);
            try {{
                await navigator.clipboard.writeText(content);
                showToast("📋 JSON copiado para a área de transferência.");
            }} catch (error) {{
                console.warn(error);
                showToast("Não foi possível copiar automaticamente.");
            }}
        }}

        function approveAllVisible() {{
            let count = 0;
            posts.forEach(post => {{
                const opt = selectedOption(post);
                if (!matchesFilters(post, opt)) return;
                if ((post.status || "pending") === "pending" && !post.review_action) {{
                    post.status = "approved";
                    count += 1;
                }}
            }});
            if (!count) {{
                showToast("Não há slots pendentes visíveis para aprovar.");
                return;
            }}
            markDirty(true);
            render();
            showToast(`✓ ${{count}} slot(s) marcados como aprovados. Clica em Guardar!`);
        }}

        function renderConditionalPool() {{
            const container = document.getElementById("conditional-pool-panel");
            if (!container) return;
            if (!Array.isArray(conditionalPool) || !conditionalPool.length) {{
                container.innerHTML = "<div style='color:var(--muted); font-size:0.85rem;'>Sem posts na bolsa condicional.</div>";
                return;
            }}
            container.innerHTML = conditionalPool.map((item, idx) => `
                <div style="display:flex; justify-content:space-between; align-items:center; gap:0.75rem; flex-wrap:wrap; padding:0.65rem 0.85rem; background:var(--bg-elev); border:1px solid var(--border); border-radius:10px;">
                    <div>
                        <span class="pill" style="margin-inline-end:0.45rem;">${{escapeHtml(item.trigger || "condicional")}}</span>
                        <strong>(${{escapeHtml(item.year)}}) ${{escapeHtml(item.title)}}</strong>
                        <div style="color:var(--muted); font-size:0.78rem; margin-block-start:0.15rem;">${{escapeHtml(item.trigger_description || "")}}</div>
                    </div>
                    <div style="display:flex; gap:0.5rem; align-items:center;">
                        <label class="visually-hidden" for="cond-date-${{idx}}">Data alvo (YYYY-MM-DD)</label>
                        <input type="text" id="cond-date-${{idx}}" placeholder="YYYY-MM-DD" style="width:140px; min-height:40px; padding:0.4rem 0.6rem; font-size:0.85rem;" autocorrect="off" autocapitalize="off" spellcheck="false" value="${{escapeHtml(item.original_date || "")}}">
                        <button type="button" class="secondary" style="min-height:40px; padding:0.4rem 0.75rem; font-size:0.8rem;" data-action="inject-conditional" data-cond-index="${{idx}}">Ativar nesta data</button>
                    </div>
                </div>
            `).join("");
        }}

        function injectConditionalPost(condIdx) {{
            const item = conditionalPool[condIdx];
            if (!item || !item.option) return;
            const dateInput = document.getElementById(`cond-date-${{condIdx}}`);
            const targetDate = (dateInput?.value || "").trim();
            if (!targetDate) {{
                showToast("Indica a data (YYYY-MM-DD) para ativar este post condicional.");
                dateInput?.focus();
                return;
            }}
            const targetPost = posts.find(p => p.lang === fixedLang && p.date === targetDate && p.status !== "approved")
                || posts.find(p => p.lang === fixedLang && p.date === targetDate);
            if (!targetPost) {{
                showToast(`Sem slot encontrado para ${{targetDate}} no ficheiro atual.`);
                return;
            }}
            targetPost.options.unshift(JSON.parse(JSON.stringify(item.option)));
            targetPost.selected_option = 0;
            targetPost.status = "approved";
            targetPost.review_action = "";
            targetPost.editorial_mode = "conditional_activated";
            uiState.viewMode = "all";
            markDirty(true);
            render();
            showToast(`✓ Post condicional ativado em ${{targetDate}} (${{targetPost.id}})!`);
        }}

        // Event listeners & delegation (no inline onclick handlers)
        document.getElementById("btn-save-direct")?.addEventListener("click", saveDirect);
        document.getElementById("btn-download-json")?.addEventListener("click", downloadJson);
        document.getElementById("btn-copy-json")?.addEventListener("click", copyJson);
        document.getElementById("btn-approve-visible")?.addEventListener("click", approveAllVisible);

        document.getElementById("month-filter")?.addEventListener("change", (e) => {{
            uiState.monthFilter = e.target.value;
            render();
        }});
        document.getElementById("search-filter")?.addEventListener("input", (e) => {{
            uiState.search = e.target.value;
            render();
        }});

        document.addEventListener("submit", (e) => {{
            if (e.target.matches("[data-slot-form]")) e.preventDefault();
        }});

        document.addEventListener("click", (e) => {{
            const viewBtn = e.target.closest("[data-view-mode]");
            if (viewBtn) {{
                uiState.viewMode = viewBtn.dataset.viewMode;
                render();
                return;
            }}
            const actionEl = e.target.closest("[data-action]");
            if (!actionEl) return;
            const action = actionEl.dataset.action;
            const postIndex = Number(actionEl.dataset.postIndex);

            if (action === "quick-status" && !Number.isNaN(postIndex)) {{
                posts[postIndex].status = actionEl.dataset.status;
                if (actionEl.dataset.status === "approved") {{
                    posts[postIndex].review_action = "";
                }}
                markDirty(true);
                render();
                showToast(`Slot ${{posts[postIndex].id}} marcado como ${{actionEl.dataset.status}}.`);
            }} else if (action === "quick-refresh" && !Number.isNaN(postIndex)) {{
                const nextAction = actionEl.dataset.refresh;
                posts[postIndex].review_action = posts[postIndex].review_action === nextAction ? "" : nextAction;
                if (posts[postIndex].review_action) {{
                    posts[postIndex].status = "pending";
                }}
                markDirty(true);
                render();
            }} else if (action === "switch-caption-tab" && !Number.isNaN(postIndex)) {{
                uiState.captionPlatformByPost[postIndex] = actionEl.dataset.tab;
                render();
            }} else if (action === "use-external" && !Number.isNaN(postIndex)) {{
                const sugIdx = Number(actionEl.dataset.sugIndex);
                const post = posts[postIndex];
                const sug = (post.external_suggestions || [])[sugIdx];
                if (!sug) return;
                post.review_note = `Gera opções baseadas no evento de ${{sug.year}}: ${{sug.title}} (${{sug.summary}})`;
                post.review_action = "regenerate";
                post.theme_suggestion = sug.title;
                post.status = "pending";
                markDirty(true);
                render();
                showToast("Sugestão aplicada — corre o pregenerator após guardar.");
            }} else if (action === "inject-conditional") {{
                injectConditionalPost(Number(actionEl.dataset.condIndex));
            }}
        }});

        document.addEventListener("change", (e) => {{
            const target = e.target;
            if (target.dataset.action === "select-option") {{
                const postIndex = Number(target.dataset.postIndex);
                const post = posts[postIndex];
                const previous = Number(post.selected_option || 0);
                const next = Number(target.value);
                post.selected_option = next;
                const selected = Array.isArray(post.options) ? post.options[next] : null;
                const hasPreview = Boolean(selected && (selected.image_url || selected.local_image_path));
                if (next !== previous && !hasPreview) {{
                    post.review_action = "refresh_image";
                    post.status = "pending";
                    showToast("Opção sem capa renderizada — marcada para pedir nova imagem.");
                }}
                markDirty(true);
                render();
                return;
            }}
            if (target.dataset.field === "layout_override" || target.dataset.field === "review_action") {{
                const postIndex = Number(target.dataset.postIndex);
                posts[postIndex][target.dataset.field] = target.value;
                if (target.dataset.field === "review_action" && target.value) {{
                    posts[postIndex].status = "pending";
                }}
                markDirty(true);
                render();
            }}
        }});

        document.addEventListener("input", (e) => {{
            const target = e.target;
            const postIndex = Number(target.dataset.postIndex);
            if (Number.isNaN(postIndex) || !posts[postIndex]) return;
            if (target.dataset.field && ["theme_suggestion", "manual_background_url", "review_note"].includes(target.dataset.field)) {{
                posts[postIndex][target.dataset.field] = target.value;
                markDirty(true);
                refreshJsonPreview();
            }} else if (target.dataset.optField) {{
                const opt = selectedOption(posts[postIndex]);
                if (opt) {{
                    opt[target.dataset.optField] = target.value;
                    markDirty(true);
                    refreshJsonPreview();
                }}
            }}
        }});

        // Scroll-state fallback for browsers without CSS scroll-state queries
        if (typeof CSS !== "undefined" && !CSS.supports("container-type", "scroll-state")) {{
            const bar = document.getElementById("top-bar");
            let lastY = window.scrollY;
            window.addEventListener("scroll", () => {{
                const maxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
                const y = Math.max(0, Math.min(window.scrollY, maxScroll));
                if (y === lastY) return;
                bar?.classList.toggle("is-hidden", y > lastY && y > (bar.offsetHeight || 64));
                lastY = y;
            }}, {{ passive: true }});
        }}

        renderConditionalPool();
        render();
    </script>
</body>
</html>
"""
    with open(review_output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated {review_output_path}")


def generate_review_files(pending_posts, focus_months=None, langs=None):
    focus_months = focus_months or {}
    langs = langs or ["pt"]
    for lang in langs:
        generate_review_html(
            pending_posts,
            focus_month=focus_months.get(lang, ""),
            lang_filter=lang,
        )


def parse_cli_date(value, field_name):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} tem de estar no formato YYYY-MM-DD.") from exc


def _story_tokens(text):
    norm = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()
    return set(re.findall(r"[a-z0-9]{4,}", norm))


def build_selected_history(pending_posts, lang="pt"):
    """Reconstrói o histórico acumulado de seleções PT para controlo de cadência, frescura e gosto editorial."""
    history = []
    for p in pending_posts:
        if p.get("lang", "pt") != lang or p.get("status") == "skip":
            continue
        opts = p.get("options") or []
        sel = int(p.get("selected_option", 0) or 0)
        if 0 <= sel < len(opts):
            c_opt = opts[sel]
            try:
                p_date = datetime.strptime(p.get("date", ""), "%Y-%m-%d").date()
            except Exception:
                continue
            p_topic = extract_macro_topic(c_opt.get("title", ""), c_opt.get("summary", ""), c_opt.get("category", ""))
            p_toks = _story_tokens(c_opt.get("title", ""))
            history.append({
                "date": p_date,
                "slot": int(p.get("slot", 1) or 1),
                "year": str(c_opt.get("year", ""))[:4],
                "category": normalize_text(c_opt.get("category", ""), uppercase=True),
                "topic": p_topic,
                "tokens": p_toks,
                "title": c_opt.get("title", ""),
            })
    return history


def select_diverse_slot_options(options_list, current_date, all_selected_history, slots_to_create):
    """Seleciona e ordena as melhores opções para Slot 1 e Slot 2 alinhadas com o gosto editorial:
    - Prioriza impacto público concreto em Portugal (números, decisões, votos, serviços públicos, greves nacionais)
      e marcos mundiais verdadeiramente icónicos (níveis 1–2).
    - Privilegia a janela histórica clássica do Arquivo.pt (1996–2018) face a notícias demasiado recentes (2025).
    - Penaliza ruído cerimonial/retórico (tomadas de posse, paradas, desafios verbais, auditorias menores, casos hiper-locais)
      e evita fadiga pandémica (intervalo mínimo de 7 dias para Covid-19).
    - Valoriza opções com captura verificada no Arquivo.pt (/wayback/) e diversidade de categorias/décadas entre dias consecutivos.
    """
    day_selected_topics = set()
    day_selected_tokens = []
    day_selected_years = set()
    day_selected_decades = set()
    day_selected_categories = set()

    yesterday_categories = {
        item.get("category")
        for item in all_selected_history
        if item.get("category") and abs((current_date - item["date"]).days) == 1
    }
    recent_years_2d = {
        item.get("year")
        for item in all_selected_history
        if item.get("year") and 0 < abs((current_date - item["date"]).days) <= 2
    }

    def _evaluate_candidate(cand):
        c_title = cand.get("title", "")
        c_summary = cand.get("summary", "")
        c_cat = normalize_text(cand.get("category", ""), uppercase=True)
        c_year = str(cand.get("year", ""))[:4]
        try:
            year_int = int(c_year or 0)
        except ValueError:
            year_int = 0
        c_decade = (year_int // 10) * 10 if year_int >= 1900 else 0
        c_tier = str(cand.get("editorial_tier", "high")).lower()
        c_toks = _story_tokens(c_title)
        c_topic = extract_macro_topic(c_title, c_summary, c_cat)

        c_norm = unicodedata.normalize("NFKD", f"{c_title} {c_summary}".lower()).encode("ascii", "ignore").decode("ascii")
        if any(bad in c_norm for bad in [
            "renova estado de emergencia", "renovacao do estado de emergencia",
            "novas medidas anticovid", "novas restricoes contra a covid",
            "tabela taxas", "taxas de entrega", "mefedrona", "adia extincao",
            "adia por seis meses", "evita encerramento do governo", "orcamento parcial",
            "orcamento provisorio", "revogacao de decretos", "edificios mais eficientes",
            "alimentacao saudavel nas escolas", "derrame de petroleo", "inspecao do sef",
            "falta de auxiliares na escola",
        ]):
            return -100, "minor_routine"

        # No próprio dia:
        if c_topic and c_topic in day_selected_topics:
            return -50, f"topic '{c_topic}' used today"
        for prev_toks in day_selected_tokens:
            if len(c_toks & prev_toks) >= 2:
                return -50, "headline overlaps with other slot today"

        # Histórico recente (cadência e saturação):
        if c_topic:
            min_gap_days = 7 if c_topic == "covid" else 3
            for item in all_selected_history:
                if item.get("topic") == c_topic:
                    diff = abs((current_date - item["date"]).days)
                    if diff <= min_gap_days:
                        return -40, f"topic '{c_topic}' interval <= {min_gap_days}"
            max_30d = 4 if c_topic == "covid" else 8
            count_30 = sum(
                1 for item in all_selected_history
                if item.get("topic") == c_topic and abs((current_date - item["date"]).days) <= 30
            )
            if count_30 >= max_30d:
                return -40, f"topic '{c_topic}' 30d cap reached"

        for item in all_selected_history:
            if abs((current_date - item["date"]).days) <= 15:
                ov = len(c_toks & item.get("tokens", set()))
                if ov >= 3 or (c_year == item.get("year") and ov >= 2):
                    return -40, f"overlap with {item['date']}"

        score = 100
        if c_tier == "high":
            score += 45

        # Relevância histórica calculada (L1–L5 + weighted_score)
        rel = cand.get("relevance") if isinstance(cand.get("relevance"), dict) else {}
        rel_level = int(rel.get("level") or 4)
        rel_weighted = float(rel.get("weighted_score") or 45.0)
        score += int(round((rel_weighted - 40.0) * 0.55))
        score += {1: 26, 2: 16, 3: 8, 4: 0, 5: -6}.get(rel_level, 0)

        # Curva de memória histórica ("Notícias de Ontem"): privilegiar arquivo clássico 1996–2018
        if 1996 <= year_int <= 2016:
            score += 28
        elif 2017 <= year_int <= 2021:
            score += 14
        elif 0 < year_int < 1996 and rel_level <= 3:
            score += 16
        elif year_int == 2024:
            score -= 12
        elif year_int >= 2025:
            score -= 35

        # Impacto concreto, números tangíveis e decisões estruturais
        if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:%|mil|milhoes|escolas|universidades|hospitais|produtos|euros|dias|anos)\b", c_norm):
            score += 18
        if any(act in c_norm for act in [
            "chumbado", "aprova", "isenta", "proibe", "extincao", "fecho de",
            "corte de", "greve nacional", "obras urgentes", "entra em vigor",
            "eleito", "primeira emissao", "nacionaliza", "resgate",
        ]):
            score += 12

        # Âncora real verificada no Arquivo.pt (garante fonte preservada e elegibilidade de snapshot)
        if "/wayback/" in str(cand.get("article_url") or "").lower():
            score += 18

        # Equilíbrio Portugal vs. Mundial: internacional só quando é marco global de topo (L1–L2)
        if c_cat == "MUNDIAL":
            if rel_level <= 2:
                score += 18
            elif rel_level >= 4:
                score -= 40

        # Penalização de protocolo cerimonial, soundbites políticos e auditorias menores
        if any(cer in c_norm for cer in [
            "parada militar", "centenario", "da posse", "secretarios de estado",
            "lanca desafio", "auditoria do tribunal", "atraso na entrega",
            "entrega proposta de orcamento", "diz que pais", "afirma que duvidas",
        ]):
            score -= 45

        # Diversidade intra-dia e entre dias consecutivos
        if c_year in day_selected_years:
            score -= 35
        elif c_year in recent_years_2d:
            score -= 16
        if c_decade and c_decade in day_selected_decades:
            score -= 14
        if c_cat and c_cat in day_selected_categories:
            score -= 65
        elif c_cat and c_cat in yesterday_categories:
            score -= 24

        return score, "ok"

    deduped_candidates = []
    seen_cand_titles = set()
    for cand in options_list:
        ct = cand.get("title", "")
        if ct and ct not in seen_cand_titles:
            seen_cand_titles.add(ct)
            deduped_candidates.append(cand)

    slot_options_map = {}
    for slot in slots_to_create:
        if not deduped_candidates:
            break
        scored_candidates = []
        for cand in deduped_candidates:
            s, r = _evaluate_candidate(cand)
            scored_candidates.append((s, cand, r))
        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        chosen_primary = (
            scored_candidates[0][1]
            if scored_candidates and scored_candidates[0][0] > 0
            else deduped_candidates[0]
        )
        if chosen_primary:
            cp_top = extract_macro_topic(
                chosen_primary.get("title", ""),
                chosen_primary.get("summary", ""),
                chosen_primary.get("category", ""),
            )
            cp_toks = _story_tokens(chosen_primary.get("title", ""))
            cp_yr = str(chosen_primary.get("year", ""))[:4]
            cp_cat = normalize_text(chosen_primary.get("category", ""), uppercase=True)
            try:
                cp_dec = (int(cp_yr or 0) // 10) * 10
            except ValueError:
                cp_dec = 0
            if cp_top:
                day_selected_topics.add(cp_top)
            if cp_cat:
                day_selected_categories.add(cp_cat)
            day_selected_tokens.append(cp_toks)
            day_selected_years.add(cp_yr)
            if cp_dec >= 1900:
                day_selected_decades.add(cp_dec)
            all_selected_history.append({
                "date": current_date,
                "slot": slot,
                "year": cp_yr,
                "category": cp_cat,
                "topic": cp_top,
                "tokens": cp_toks,
                "title": chosen_primary.get("title", ""),
            })
            remaining_sorted = [c for _, c, _ in scored_candidates if c is not chosen_primary]
            slot_options_map[slot] = [chosen_primary] + remaining_sorted[:8]
            deduped_candidates = [c for c in deduped_candidates if c is not chosen_primary]

    return slot_options_map


def sync_remote_huggingface_cdxj(start_date, end_date):
    """Garante que os ficheiros CDXJ remotos do dataset Hugging Face
    (MaNmAxImO/arquivo-pt-cdxj) estão disponíveis localmente na pasta arquivo_cdxj/.
    """
    hf_dataset = os.environ.get("HF_DATASET_ID", "MaNmAxImO/arquivo-pt-cdxj")
    hf_token = os.environ.get("HF_TOKEN")
    if not hf_dataset:
        return
    try:
        import concurrent.futures
        from huggingface_hub import HfApi, hf_hub_download

        api = HfApi(token=hf_token)
        repo_files = api.list_repo_files(repo_id=hf_dataset, repo_type="dataset")
        cur = start_date
        needed_suffixes = set()
        while cur <= end_date:
            needed_suffixes.add(f"{cur.month:02d}-{cur.day:02d}.cdxj")
            cur += timedelta(days=1)

        target_files = [f for f in repo_files if any(f.endswith(s) for s in needed_suffixes)]
        missing = []
        for f in target_files:
            local_path = os.path.join("arquivo_cdxj", f.replace("/", os.sep))
            if not os.path.exists(local_path) or os.path.getsize(local_path) < 100:
                missing.append(f)

        if missing:
            print(f"[Hugging Face] A sincronizar {len(missing)} ficheiros CDXJ remotos de {hf_dataset}...")

            def _dl(filename):
                try:
                    return hf_hub_download(
                        repo_id=hf_dataset,
                        repo_type="dataset",
                        filename=filename,
                        token=hf_token,
                        local_dir="arquivo_cdxj",
                    )
                except Exception:
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(_dl, missing))
            print(f"[Hugging Face] {len(missing)} ficheiros sincronizados com sucesso.")
        else:
            print(
                f"[Hugging Face] Ficheiros CDXJ remotos para {start_date} a {end_date} já presentes localmente ({len(target_files)} ficheiros)."
            )
    except Exception as exc:
        print(f"[Hugging Face] Aviso ao sincronizar CDXJ ({exc}).")


def generate_pending_posts_for_interval(pending_posts, lang, start_date, end_date, source_mode="", save_progress=False):
    os.makedirs("temp_pregen", exist_ok=True)
    sync_remote_huggingface_cdxj(start_date, end_date)
    existing_ids = {post["id"]: post for post in pending_posts if post.get("id")}
    new_entries_added = False
    current_date = start_date
    focus_month = month_key(start_date)

    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        print(f"\n--- Dia: {date_str} [{lang}] ---")
        day_entries_added = False

        slot1_exists = f"{lang}_{date_str}_{1}" in existing_ids
        slot2_exists = f"{lang}_{date_str}_{2}" in existing_ids
        if slot1_exists and slot2_exists:
            print(f"[{lang}] Ambos os slots ja existem. A saltar.")
            current_date += timedelta(days=1)
            continue

        matching_news = get_news_for_generation(current_date, lang, source_mode=source_mode)
        if not matching_news:
            print(f"[{lang}] Sem noticias historicas para este dia.")
            current_date += timedelta(days=1)
            continue

        print(f"[{lang}] A enviar {len(matching_news)} noticias para a IA...")
        options_list = rank_all_stories_for_day(matching_news, lang)
        if not options_list:
            print(f"[{lang}] Falha na IA.")
            current_date += timedelta(days=1)
            continue

        external_suggestions = generate_external_day_suggestions(current_date, lang, options_list)
        all_selected_history = build_selected_history(pending_posts, lang=lang)

        slots_to_create = []
        if not slot1_exists:
            slots_to_create.append(1)
        if not slot2_exists and len(options_list) >= 2:
            slots_to_create.append(2)

        slot_options_map = select_diverse_slot_options(
            options_list,
            current_date,
            all_selected_history,
            slots_to_create,
        )

        for slot in slots_to_create:
            post_id = f"{lang}_{date_str}_{slot}"
            if post_id in existing_ids:
                continue
            base_options = slot_options_map.get(slot, [])
            if not base_options:
                continue
            selected_option = 0
            slot_options = prepare_options_for_review(
                base_options,
                lang,
                date_str,
                matching_news=matching_news,
                selected_option_index=selected_option,
            )
            new_post = normalize_pending_post(
                {
                    "id": post_id,
                    "date": date_str,
                    "slot": slot,
                    "lang": lang,
                    "selected_option": selected_option if selected_option < len(slot_options) else 0,
                    "layout_override": "",
                    "theme_suggestion": "",
                    "manual_background_url": "",
                    "review_action": "",
                    "review_note": "",
                    "status": "pending",
                    "generated_month": month_key(current_date),
                    "external_suggestions": clone_options(external_suggestions),
                    "options": clone_options(slot_options),
                }
            )
            pending_posts.append(new_post)
            existing_ids[post_id] = new_post
            new_entries_added = True
            day_entries_added = True
            print(f"[{lang}] Slot {slot}: Criado ({len(slot_options)} opcoes).")

        if save_progress and day_entries_added:
            sort_pending_posts(pending_posts)
            save_json(PENDING_POSTS_FILE, pending_posts)
            print(f"[{lang}] Progresso guardado ate {date_str}.")

        current_date += timedelta(days=1)

    sort_pending_posts(pending_posts)
    return new_entries_added, focus_month


def main():
    parser = argparse.ArgumentParser(description="Gera e revê filas mensais de posts históricos.")
    parser.add_argument("--lang", choices=["pt"], help="Processa apenas um idioma e gera o respetivo review.")
    parser.add_argument("--start-date", help="Data inicial do intervalo manual (YYYY-MM-DD). Ativa o modo por intervalo para um unico idioma.")
    parser.add_argument("--end-date", help="Data final do intervalo manual (YYYY-MM-DD). Se omitida, usa a data inicial.")
    parser.add_argument(
        "--source-mode",
        choices=["local", "local-first", "arquivo-first", "arquivo-only"],
        default=PREGENERATOR_SOURCE_MODE,
        help="Fonte de noticias historicas: arquivo-first usa Arquivo.pt como principal; arquivo-only nao usa fallback local.",
    )
    args = parser.parse_args()

    interval_mode = bool(args.start_date or args.end_date)
    start_date = None
    end_date = None

    if interval_mode:
        if not args.lang:
            parser.error("O modo por intervalo requer --lang pt|en.")
        if not args.start_date:
            parser.error("O modo por intervalo requer --start-date.")
        try:
            start_date = parse_cli_date(args.start_date, "--start-date")
            end_date = parse_cli_date(args.end_date, "--end-date") if args.end_date else start_date
        except ValueError as exc:
            parser.error(str(exc))
        if start_date and end_date:
            if end_date < start_date:
                parser.error("--end-date tem de ser igual ou posterior a --start-date.")

    langs_to_process = [args.lang] if args.lang else ["pt"]

    print("=== STARTING PREGENERATOR ===")
    pending_posts = [normalize_pending_post(post) for post in load_json(PENDING_POSTS_FILE, [])]

    if interval_mode:
        print("=== STARTING PREGENERATOR INTERVAL MODE ===")
        interval_lang = args.lang
        new_entries_added, interval_focus_month = generate_pending_posts_for_interval(
            pending_posts,
            interval_lang,
            start_date,
            end_date,
            source_mode=args.source_mode,
            save_progress=True,
        )

        if new_entries_added:
            save_json(PENDING_POSTS_FILE, pending_posts)
            print("\npending_posts.json atualizado.")

        generate_review_files(
            pending_posts,
            focus_months={interval_lang: interval_focus_month},
            langs=[interval_lang],
        )
        return

    had_refresh_targets, refresh_changed, refresh_focus_month = refresh_marked_post_images(
        [post for post in pending_posts if post.get("lang") in langs_to_process]
    )

    if had_refresh_targets:
        if refresh_changed:
            sort_pending_posts(pending_posts)
            save_json(PENDING_POSTS_FILE, pending_posts)
            print("\npending_posts.json atualizado apos refresh de imagem.")
        generate_review_files(
            pending_posts,
            focus_months={args.lang: refresh_focus_month} if args.lang else {post_lang: refresh_focus_month for post_lang in langs_to_process},
            langs=langs_to_process,
        )
        return

    had_regeneration_targets, regeneration_changed, regeneration_focus_month = regenerate_marked_posts(
        [post for post in pending_posts if post.get("lang") in langs_to_process]
    )

    if had_regeneration_targets:
        if regeneration_changed:
            sort_pending_posts(pending_posts)
            save_json(PENDING_POSTS_FILE, pending_posts)
            print("\npending_posts.json atualizado apos regeneracao seletiva.")
        generate_review_files(
            pending_posts,
            focus_months={args.lang: regeneration_focus_month} if args.lang else {post_lang: regeneration_focus_month for post_lang in langs_to_process},
            langs=langs_to_process,
        )
        return

    state = load_pregeneration_state()
    if not isinstance(state, dict):
        state = {}
    os.makedirs("temp_pregen", exist_ok=True)
    existing_ids = {post["id"]: post for post in pending_posts if post.get("id")}
    new_entries_added = False
    focus_months = {}
    new_entries_by_lang = {lang: False for lang in langs_to_process}

    for lang in langs_to_process:
        target_month_start = determine_next_target_month(pending_posts, state, lang_filter=lang)
        start_date = target_month_start
        end_date = end_of_month(target_month_start)
        target_month_label = month_key(target_month_start)
        focus_months[lang] = target_month_label
        print(f"Gerando apenas o proximo mes [{lang}]: {target_month_label} ({start_date} a {end_date})")

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            print(f"\n--- Dia: {date_str} [{lang}] ---")

            slot1_exists = f"{lang}_{date_str}_{1}" in existing_ids
            slot2_exists = f"{lang}_{date_str}_{2}" in existing_ids
            if slot1_exists and slot2_exists:
                print(f"[{lang}] Ambos os slots ja existem. A saltar.")
                current_date += timedelta(days=1)
                continue

            matching_news = get_news_for_generation(current_date, lang, source_mode=args.source_mode)
            if not matching_news:
                print(f"[{lang}] Sem noticias historicas para este dia.")
                current_date += timedelta(days=1)
                continue

            print(f"[{lang}] A enviar {len(matching_news)} noticias para a IA...")
            options_list = rank_all_stories_for_day(matching_news, lang)
            if not options_list:
                print(f"[{lang}] Falha na IA.")
                current_date += timedelta(days=1)
                continue

            external_suggestions = generate_external_day_suggestions(current_date, lang, options_list)
            all_selected_history = build_selected_history(pending_posts, lang=lang)
            slots_to_create = []
            if not slot1_exists:
                slots_to_create.append(1)
            if not slot2_exists and len(options_list) >= 2:
                slots_to_create.append(2)
            slot_options_map = select_diverse_slot_options(
                options_list,
                current_date,
                all_selected_history,
                slots_to_create,
            )

            for slot in slots_to_create:
                post_id = f"{lang}_{date_str}_{slot}"
                if post_id in existing_ids:
                    continue
                selected_option = 0
                base_options = slot_options_map.get(slot, [])
                if not base_options:
                    continue
                slot_options = prepare_options_for_review(
                    base_options,
                    lang,
                    date_str,
                    matching_news=matching_news,
                    selected_option_index=selected_option,
                )
                new_post = normalize_pending_post(
                    {
                        "id": post_id,
                        "date": date_str,
                        "slot": slot,
                        "lang": lang,
                        "selected_option": selected_option if selected_option < len(slot_options) else 0,
                        "layout_override": "",
                        "theme_suggestion": "",
                        "manual_background_url": "",
                        "review_action": "",
                        "review_note": "",
                        "status": "pending",
                        "generated_month": target_month_label,
                        "external_suggestions": clone_options(external_suggestions),
                        "options": clone_options(slot_options),
                    }
                )
                pending_posts.append(new_post)
                existing_ids[post_id] = new_post
                new_entries_added = True
                new_entries_by_lang[lang] = True
                print(f"[{lang}] Slot {slot}: Criado ({len(slot_options)} opcoes).")

            current_date += timedelta(days=1)

    en_synced = sync_approved_pt_to_en(pending_posts, pool=nvidia_pool)
    sort_pending_posts(pending_posts)
    if new_entries_added or en_synced:
        save_json(PENDING_POSTS_FILE, pending_posts)
        print("\npending_posts.json atualizado.")

    for lang in langs_to_process:
        state.setdefault(lang, {})
        if new_entries_by_lang.get(lang):
            state[lang]["last_generated_month"] = focus_months.get(lang, state[lang].get("last_generated_month", ""))
        state[lang]["updated_at"] = datetime.now().isoformat()
        state[lang]["new_entries_added"] = new_entries_added
    save_pregeneration_state(state)
    generate_review_files(pending_posts, focus_months=focus_months, langs=langs_to_process)


if __name__ == "__main__":
    main()
