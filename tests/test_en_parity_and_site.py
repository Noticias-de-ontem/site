import io
from unittest.mock import patch

from PIL import Image

import build_site
import publisher
from en_sync import (
    format_platform_caption,
    is_valid_article_url,
    strip_caption_metadata,
)
from scripts.collect_snapshots import is_valid_snapshot_bytes
from social_networks import replace_social_cta, social_link_cta, translate_category_to_en


def test_is_valid_article_url_filters_images_and_aggregators():
    assert is_valid_article_url(
        "https://arquivo.pt/wayback/20211027213859/https://esquerda.net/artigo/orcamento-do-estado-para-2022-chumbado-na-assembleia-da-republica/77576"
    )
    assert is_valid_article_url(
        "https://www.publico.pt/2015/11/03/sociedade/noticia/igreja-proibe-padres-com-tendencias-homossexuais-1713214"
    )

    # Rejeitar imagens, modificadores im_, Wikipedia/Wikimedia, agregadores e páginas de tag/pesquisa
    assert not is_valid_article_url(
        "https://arquivo.pt/wayback/20180126035715im_/https://static.noticiasaominuto.com/stockimages/1920/naom_59b138228d85c.jpg?151690096"
    )
    assert not is_valid_article_url(
        "https://commons.wikimedia.org/wiki/File:Praia-Supremo_Tribunal_de_Justi%C3%A7a.jpg"
    )
    assert not is_valid_article_url(
        "https://pt.wikipedia.org/wiki/Elei%C3%A7%C3%A3o_presidencial_nos_Estados_Unidos_em_2008"
    )
    assert not is_valid_article_url(
        "https://arquivo.pt/wayback/20160611062004/https://news.google.pt/news/story?ncl=abc"
    )
    assert not is_valid_article_url(
        "https://arquivo.pt/wayback/20230418155327/https://wsws.org/en/articles/2023/03/25/gycx-m25.html"
    )
    assert not is_valid_article_url(
        "https://arquivo.pt/wayback/20250101022144/https://radioatlantida.net/tag/bandeira-azul"
    )
    assert not is_valid_article_url(
        "https://arquivo.pt/wayback/20140925221612/https://dinis2.linguateca.pt/acesso/tokens/lemapos.chave.txt"
    )


def test_platform_specific_ctas_pt_and_en():
    assert social_link_cta("instagram", "pt") == "🔗 Lê a notícia completa no link da bio."
    assert social_link_cta("facebook", "pt") == "🔗 Lê a notícia completa no site no sobre do perfil."
    assert social_link_cta("instagram", "en") == "🔗 Read the full story at the link in bio."
    assert (
        social_link_cta("facebook", "en")
        == "🔗 Read the full story on the website in the profile's About section."
    )

    ig_pt = format_platform_caption("Texto narrativo de teste.", "2015", "EDUCAÇÃO", "instagram", "pt")
    fb_pt = format_platform_caption("Texto narrativo de teste.", "2015", "EDUCAÇÃO", "facebook", "pt")
    ig_en = format_platform_caption("English narrative text.", "2015", "EDUCAÇÃO", "instagram", "en")
    fb_en = format_platform_caption("English narrative text.", "2015", "EDUCAÇÃO", "facebook", "en")

    assert "🔗 Lê a notícia completa no link da bio." in ig_pt
    assert "🔗 Lê a notícia completa no site no sobre do perfil." in fb_pt
    assert "🔗 Read the full story at the link in bio." in ig_en
    assert "🔗 Read the full story on the website in the profile's About section." in fb_en
    assert "#Education" in ig_en

    # Conversão limpa de CTA antigo em tempo de publicação
    legacy_en = (
        "Teachers staged a strike in 2022.\n\n"
        "This post is intended solely to recall past events in history, never representing current events. This story is from 2022.\n\n"
        "🔗 Read the full story via the link in our bio/about section.\n\n#YesterdaysNews"
    )
    converted_fb = replace_social_cta(legacy_en, platform="facebook", lang="en")
    assert "🔗 Read the full story on the website in the profile's About section." in converted_fb
    assert "bio/about section" not in converted_fb
    assert strip_caption_metadata(converted_fb) == "Teachers staged a strike in 2022."


def test_category_translation_coverage():
    assert translate_category_to_en("EDUCAÇÃO") == "EDUCATION"
    assert translate_category_to_en("HISTÓRIA") == "HISTORY"
    assert translate_category_to_en("POLÍTICA") == "POLITICS"
    assert translate_category_to_en("SAÚDE") == "HEALTH"


def test_build_site_merges_pt_and_en_without_duplicate_cards(monkeypatch):
    fake_posts = [
        {
            "id": "pt_2026-11-02_1",
            "date": "2026-11-02",
            "slot": 1,
            "lang": "pt",
            "status": "published",
            "selected_option": 0,
            "instagram_url": "https://www.instagram.com/p/PT123/",
            "facebook_url": "https://www.facebook.com/1030669413467151_111",
            "options": [
                {
                    "year": "2022",
                    "category": "EDUCAÇÃO",
                    "title": "Professores realizam greve nacional contra o Orçamento do Estado",
                    "title_en": "Teachers Stage a National Strike Over the State Budget",
                    "overlay_description": "Escolas fechadas e forte adesão à greve nacional.",
                    "summary": "Escolas fechadas e forte adesão à greve nacional.",
                    "summary_en": "Schools closed as teachers mounted a national strike.",
                    "body": "Parágrafo um em português.\n\nParágrafo dois em português.",
                    "body_en": "Paragraph one in English.\n\nParagraph two in English.",
                    "article_url": "https://arquivo.pt/wayback/20221102192712/https://impala.pt/noticias/atualidade/professores-hoje-em-greve-contra-oe2023",
                    "relevance": {
                        "level": 3,
                        "justification": "Impacto nacional no setor educativo.",
                        "justification_en": "National impact across the education sector.",
                    },
                }
            ],
        },
        {
            "id": "en_2026-11-02_1",
            "date": "2026-11-02",
            "slot": 1,
            "lang": "en",
            "status": "published",
            "selected_option": 0,
            "instagram_url": "https://www.instagram.com/p/EN456/",
            "facebook_url": "https://www.facebook.com/1318455601360516_222",
            "options": [
                {
                    "year": "2022",
                    "category": "EDUCATION",
                    "title": "Teachers Stage a National Strike Over the State Budget",
                    "summary": "Schools closed as teachers mounted a national strike.",
                }
            ],
        },
    ]

    def fake_load_json(path, default):
        if path == build_site.PENDING_POSTS_FILE:
            return fake_posts
        return default

    monkeypatch.setattr(build_site, "load_json", fake_load_json)
    monkeypatch.setattr(
        build_site,
        "build_project_metrics",
        lambda items: {
            "published_posts": len(items),
            "coverage_start_year": 1918,
            "coverage_end_year": 2025,
            "news_source_domains": [],
        },
    )
    monkeypatch.setattr(build_site, "filtered_cdxj_latest_date", lambda d: d)
    monkeypatch.setattr(
        build_site,
        "build_calendar_payload",
        lambda items: {"post_dates": [], "post_years": [], "recommendations_by_day": {}},
    )
    monkeypatch.setattr(build_site, "select_carousel_with_tenure", lambda items: items[:1])

    payload = build_site.build_payload()
    assert payload["metrics"]["published_posts"] == 1
    assert len(payload["all"]) == 1
    item = payload["all"][0]
    assert item["id"] == "pt_2026-11-02_1"
    assert item["title_en"] == "Teachers Stage a National Strike Over the State Budget"
    assert item["summary_en"] == "Schools closed as teachers mounted a national strike."
    assert "Paragraph two in English." in item["body_en"]
    assert item["relevance_justification_en"] == "National impact across the education sector."
    assert item["instagram_url"] == "https://www.instagram.com/p/PT123/"
    assert item["instagram_url_en"] == "https://www.instagram.com/p/EN456/"
    assert item["facebook_url_en"] == "https://www.facebook.com/1318455601360516_222"


def test_snapshot_validation_rejects_covers_stock_and_429():
    def make_jpeg(size, color):
        buf = io.BytesIO()
        img = Image.new("RGB", size, color=color)
        # Adicionar variação para ultrapassar 2 KB
        for x in range(0, size[0], 7):
            for y in range(0, min(size[1], 300), 7):
                img.putpixel((x, y), ((color[0] + x) % 256, color[1], color[2]))
        img.save(buf, format="JPEG", quality=92)
        return buf.getvalue()

    # Capa 1080x1350 rejeitada
    assert not is_valid_snapshot_bytes(make_jpeg((1080, 1350), (30, 40, 50)))
    # Miniatura demasiado pequena rejeitada
    assert not is_valid_snapshot_bytes(make_jpeg((400, 300), (120, 90, 70)))
    # Erro 429 roxo 1000x1000 rejeitado
    assert not is_valid_snapshot_bytes(make_jpeg((1000, 1000), (92, 62, 235)))
    # Screenshots genuínas (1000px e 1280px de largura) aceites
    assert is_valid_snapshot_bytes(make_jpeg((1000, 2200), (248, 248, 248)))
    assert is_valid_snapshot_bytes(make_jpeg((1280, 2400), (248, 248, 248)))


def test_facebook_story_en_skips_cleanly_without_en_credentials():
    with patch.dict("os.environ", {"FB_PAGE_ID_EN": "", "FB_PAGE_ACCESS_TOKEN_EN": ""}, clear=False):
        result = publisher.publish_facebook_story("https://example.com/test.jpg", lang="en")
    assert result == "skipped_no_credentials"


def test_resolve_verified_article_url_protects_future_news(monkeypatch):
    import pregenerator

    monkeypatch.setattr(pregenerator, "resolve_wayback_capture", lambda url, yr, title="": "")
    monkeypatch.setattr(pregenerator, "resolve_wayback_by_title", lambda title, yr: "")

    # Eventos pré-1996 nunca devem guardar links anacrónicos ou da Wikipédia
    assert (
        pregenerator.resolve_verified_article_url(
            "https://pt.wikipedia.org/wiki/Terramoto_de_1755",
            "1755",
            title="Terramoto de Lisboa",
        )
        == ""
    )

    # Imagens ou modificadores im_ nunca passam como article_url
    assert (
        pregenerator.resolve_verified_article_url(
            "https://arquivo.pt/wayback/20101105120000im_/https://publico.pt/foto.jpg",
            "2010",
            title="Notícia de teste",
        )
        == ""
    )

    # Captura wayback válida do próprio ano (±1) é aceite diretamente e normalizada
    valid_wb = pregenerator.resolve_verified_article_url(
        "https://arquivo.pt/noFrame/replay/20141105101500/https://www.publico.pt/2014/11/05/economia/noticia/teste-1675",
        "2014",
        title="Notícia de teste",
    )
    assert valid_wb == "https://arquivo.pt/wayback/20141105101500/https://www.publico.pt/2014/11/05/economia/noticia/teste-1675"

    # URL ao vivo antigo (<2023) sem captura wayback NÃO fica guardado como link quebrado
    assert (
        pregenerator.resolve_verified_article_url(
            "https://www.dn.pt/2003/11/05/noticia-antiga-sem-arquivo.html",
            "2003",
            title="Notícia antiga",
        )
        == ""
    )


def test_editorial_taste_ranking_prefers_concrete_archival_impact_and_avoids_covid_fatigue():
    from datetime import date
    import pregenerator

    history = [
        {
            "date": date(2026, 11, 1),
            "slot": 2,
            "year": "2020",
            "category": "POLÍTICA",
            "topic": "covid",
            "tokens": {"presidente", "estado", "emergencia"},
            "title": "Presidente envia decreto do estado de emergência ao Parlamento",
        }
    ]
    candidates = [
        {
            "year": "2025",
            "category": "POLÍTICA",
            "editorial_tier": "high",
            "title": "Governo lança desafio às autarquias em cerimónia oficial",
            "summary": "Declaração durante tomada de posse dos secretários de Estado.",
            "article_url": "https://www.rtp.pt/noticias/politica/desafio_n1",
            "relevance": {"level": 5, "weighted_score": 31.0},
        },
        {
            "year": "2020",
            "category": "SAÚDE",
            "editorial_tier": "high",
            "title": "Novas medidas anticovid entram em vigor em Portugal",
            "summary": "Restrições de circulação alargadas durante a pandemia.",
            "article_url": "https://arquivo.pt/wayback/20201105120000/https://www.rtp.pt/noticias/pais/covid_n2",
            "relevance": {"level": 3, "weighted_score": 62.0},
        },
        {
            "year": "2012",
            "category": "ECONOMIA",
            "editorial_tier": "high",
            "title": "Parlamento aprova corte de 500 milhões de euros nas empresas públicas",
            "summary": "Votação do Orçamento do Estado impõe redução salarial e fusão de serviços.",
            "article_url": "https://arquivo.pt/wayback/20121105150000/https://www.publico.pt/2012/11/05/economia/noticia/corte-1570",
            "relevance": {"level": 2, "weighted_score": 74.0},
        },
        {
            "year": "2006",
            "category": "EDUCAÇÃO",
            "editorial_tier": "high",
            "title": "Governo encerra 180 escolas do primeiro ciclo com menos de dez alunos",
            "summary": "Reorganização da rede escolar transfere milhares de crianças para centros escolares.",
            "article_url": "https://arquivo.pt/wayback/20061105110000/https://www.jn.pt/nacional/escolas-5512",
            "relevance": {"level": 3, "weighted_score": 64.0},
        },
    ]

    chosen_map = pregenerator.select_diverse_slot_options(
        candidates,
        date(2026, 11, 5),
        history,
        [1, 2],
    )
    assert chosen_map[1][0]["year"] == "2012"
    assert chosen_map[2][0]["year"] == "2006"


def test_calendar_service_blocks_image_urls_and_avoids_duplicate_detail_screenshot():
    from backend.calendar_service import item_from_source

    bad_img = item_from_source(
        {
            "capture_id": "1",
            "captured_at": "2010-11-05T12:00:00Z",
            "domain": "publico.pt",
            "title": "Fotografia isolada",
            "original_url": "https://static.publico.pt/imagens/capa.jpg",
            "arquivo_url": "https://arquivo.pt/wayback/20101105120000im_/https://static.publico.pt/imagens/capa.jpg",
        }
    )
    assert bad_img["source_url"] == ""
    assert bad_img["snapshot_url"] == ""
    assert bad_img["detail_image"] == ""

    good_news = item_from_source(
        {
            "capture_id": "2",
            "captured_at": "2010-11-05T12:00:00Z",
            "domain": "publico.pt",
            "title": "Parlamento debate orçamento",
            "original_url": "https://www.publico.pt/2010/11/05/politica/noticia/orcamento-1464",
            "arquivo_url": "https://arquivo.pt/wayback/20101105120000/https://www.publico.pt/2010/11/05/politica/noticia/orcamento-1464",
        }
    )
    assert good_news["source_url"].startswith("https://arquivo.pt/wayback/20101105")
    assert good_news["detail_image"] == ""
    assert "noFrame%2Freplay" in good_news["snapshot_url"]
