# Notícias de Ontem

[Português](README.md) | **English**

**Notícias de Ontem** ("Yesterday's News") brings back stories preserved by [Arquivo.pt](https://arquivo.pt), organizes them by date, and republishes them with context and the original year, linking to the capture preserved on Arquivo.pt — like a newspaper edition about the past, published today. A candidate for the [Arquivo.pt Award 2027](https://sobre.arquivo.pt/en/arquivo-pt-award/).

The project has two connected parts:

- a bilingual website (PT/EN) to explore news by date and topic, with individual story pages on newspaper-style clean URLs;
- an editorial pipeline that prepares Instagram and Facebook posts, scores their historical relevance, and publishes them after human review.

The architecture is static by default (GitHub Pages) and can switch to dynamic (FastAPI + PostgreSQL + Celery + OpenSearch) when infrastructure is available.

## What is on the website

- **Home** — lead story (fixed-height carousel), highlights by relevance level (Historic Landmarks, Major Events, More stories), and the latest posts;
- **Calendar** — two views (**On this day**: important stories from the same date across the years; **Exact date**: only that precise day) in two layouts (**Month** or **Week**, Sunday through Saturday), with a newspaper filter and up to 6 project posts pinned to the top of each period;
- **Topics** — a phrase's evolution across the Arquivo.pt index, with a progressive chart, per-source filter, and PNG/SVG/CSV export;
- **Documentation** — how the project works, live metrics, the method, and an explainer on the [historical relevance levels](#historical-relevance);
- **Newsletter** — subscribe by writing your topics freely; a weekly send interpreted by the AI;
- **Individual story** — newspaper-style clean URL (`/noticia/YYYY/MM/DD/slug-id/`), relevance badge with the full score breakdown, the preserved original page (snapshot), an "On the same day" module, and previous/next navigation.

Portuguese is the default language; the English version uses natural American English (never a literal translation).

## Historical relevance

Every story gets a relevance badge (icon + name) backed by a weighted score — the AI proposes the ratings, the system computes the level:

| Level | Name | Meaning |
| --- | --- | --- |
| 1 | Historic Landmark | Lasting structural change in history (requires ≥90 on the substantive criteria + explicit account of later consequences) |
| 2 | Major Event | Very significant national or international consequences |
| 3 | Regional Relevance | Strong impact on a region or community |
| 4 | Public Interest | Major public attention, limited long-term impact |
| 5 | Historical Context | Useful to understand the era, not decisive on its own |

Criteria: historical impact 30% · scope of impact 20% · consequences 15% · influence on later events 15% · scale and duration 10% · **media attention 5% (never decides the level)** · uniqueness 5%. Site highlights (lead story and carousel) are drawn only from levels 1-2. The full explainer lives on the Documentation page.

## Sources

The origins the project follows (newspapers, magazines, and internet profiles) are recorded in `pending_posts.json`, the repository's editorial file, and are not shown on the website: the Documentation page and the footer have no sources grid, and individual story pages show no source chip. The verifiable source shown to the reader for each story is its capture preserved on Arquivo.pt.

## How the data flows

1. Public Arquivo.pt CDXJ indexes are filtered down to the newspapers and magazines the project follows (`recolher_cdxj_*.cmd`);
2. The `pregenerator` finds candidates for each date (local `pt/MM-DD.json` blocks and/or Arquivo.pt) and asks the AI (NVIDIA) for 10 options with categories, PT/EN titles, overlay copy, and a **relevance score**;
3. **Mandatory grounding**: every option must anchor to a real wayback capture (Arquivo.pt CDX/textsearch); unanchored options — like the old fake "Ronaldo lidera a I Liga" story — are dropped;
4. Options land in `pending_posts.json` for human review (`review_pt.html`, images under `images/review`), where they can be approved, skipped, or regenerated;
5. The `publisher` publishes approved posts to Instagram and Facebook (feed + stories) and records the permalinks;
6. `build_site.py` combines posts, metrics, images, and the events index into `site/data/news.json`, generates pages (including snapshots via `collect_snapshots.py`), and analyzes every photo with Gemini (focus point, faces, embedded text, banner/cover suitability); route pages are generated from the master shell `site/index.html`, each already with its own view active, so the home page does not flash on refresh of another page;
7. The carousel has a **tenure system** (`carrossel_estado.json`): each story stays in for ~8 days and is then replaced by another one — without being removed from the site.

## The CDXJ index

CDXJ files are Arquivo.pt metadata indexes (URLs, capture dates, content types); they do not contain full article text. Because the filtered CDXJ set approaches 20 GB, **never store it in GitHub**: the repository keeps code, the static site, small state files, and editorial data.

- Full CDXJ mirror on the Hugging Face: dataset `MaNmAxImO/arquivo-pt-cdxj` (authenticate with `HF_TOKEN` in `.env`);
- Collect from Arquivo.pt: `recolher_cdxj_arquivo_pt.cmd 1996 2026` (resumable; offset/anchor stored in `arquivo_cdxj_state.json`);
- Raw CDXJ already downloaded: `recolher_cdxj_de_pasta_local.cmd <folder> 1996 2026`;
- After the first full run: `reconstruir_cobertura_cdxj.cmd` (per-source coverage dates + site rebuild);
- Specific collections: `python -u build_arquivo_cdxj_index.py --collections AWP30.cdxj --start-year 1996 --end-year 2026`;
- S3/R2 sync (used by the backend worker): `sync_cdxj_storage.py`.

## Populating the site (local generation)

Everything runs through the resumable CLI `popular_site.py` (reads `.env`; 2-3 NVIDIA calls per generated day):

```cmd
:: generate ~50 days (1-2 posts/day) spread across the year, from local blocks
python popular_site.py --tudo-ano --source-mode local --limite 50

:: a specific date range, prioritizing Arquivo.pt
python popular_site.py --start 2026-03-01 --end 2026-03-31 --source-mode arquivo-first

:: a single newspaper
python popular_site.py --jornal publico.pt --start 2026-05-01 --end 2026-05-31

:: per-day events index (Wikipedia "on this day" scored by the AI) — gives the
:: calendar content for all 365 days; resumable and cached
python popular_site.py --com-eventos

:: complete older posts (relevance scores, EN fields, wayback links)
python popular_site.py --backfill-relevance
```

Source modes: `local` (collected `pt/*.json` blocks), `local-first`, `arquivo-first`, `arquivo-only`.

## Preparing posts and review

Direct alternative to `popular_site`:

```cmd
python -u pregenerator.py --lang pt --start-date 2026-07-01 --end-date 2026-07-31 --source-mode arquivo-first
```

Background photo analysis can be regenerated per post (`python scripts/regenerate_missing_backgrounds.py <post_id> ...`), always validated by Gemini. States in `pending_posts.json`: `pending`, `approved`, `published`, `skip`.

## Topic search

The topics page compares up to four queries, each with its own source and color. Values are verified by pagination (`dedupValue=0`) under Arquivo.pt rate limits; failures stay marked as unverified, never zeroed. With a backend and a complete OpenSearch index, a yearly aggregation replaces pagination.

## Dynamic website and fast analysis

`render.yaml` provisions: FastAPI + frontend (Web Service), Celery (worker), CDXJ/OpenSearch updates (a second persistent worker), PostgreSQL, a Valkey/Redis queue, and optional OpenSearch. The initial indexing is heavy (days) and must not run in normal Actions. Full manual: [`DYNAMIC_DEPLOYMENT.md`](docs/DYNAMIC_DEPLOYMENT.md).

## Generating and testing the website

```cmd
python -u build_site.py
python -m http.server 8765 --directory site
```

Open [http://localhost:8765/inicio/](http://localhost:8765/inicio/). During development, to skip re-reading gigabytes of CDXJ:

```powershell
$env:SITE_SKIP_CDXJ_REFRESH='1'; python -u build_site.py
```

## Metrics

Rebuilt on every `build_site.py` run: stories covered and time range (from CDXJ state), distinct sources, cumulative posts (`social_metrics.json`), and followers for the configured social networks. If the Meta API fails, the last valid value is kept rather than zeroed.

## Main workflows

- `Pregenerate PT Review Queue` / `Pregenerate PT Interval Review Queue` — editorial queue;
- `Daily Instagram Publisher` — publishes approved posts to Instagram and Facebook and rebuilds the site (triggered by cron-job.org, not by GitHub's schedule);
- `Deploy Website` — builds and publishes to GitHub Pages;
- `Sync Dynamic Website` — sends the public snapshot to the API;
- `Cleanup Used ImgBB Images`;
- `Weekly Data Extraction` — refreshes the complementary local archives.

## Configuration

- `NVIDIA_API_KEY`, `NVIDIA_MODEL` — editorial analysis and preparation;
- `GEMINI_API_KEY` — photo analysis (framing, faces, embedded text, suitability; cached in `gemini_photo_cache.json`, OpenCV fallback without a key);
- `IMGBB_API_KEY` — review image hosting;
- `IG_ACCESS_TOKEN_PT`, `IG_USER_ID_PT` — Instagram publishing;
- `SITE_API_URL`, `SITE_SYNC_TOKEN` — dynamic sync;
- `SITE_PUBLIC_URL` — final public domain (canonical/sitemap/structured data);
- `DATABASE_URL`, `REDIS_URL`, `OPENSEARCH_URL`, `OPENSEARCH_API_KEY`, `OPENSEARCH_INDEX` — dynamic infrastructure.

Keys never go into the repository: in GitHub Actions use **Settings > Secrets and variables > Actions**; locally use a `.env` file (not committed) or `nvidia_api_key.local.txt`.

## Useful .cmd commands

- `recolher_cdxj_arquivo_pt.cmd [start] [end]` — build/resume the CDXJ index from Arquivo.pt;
- `recolher_cdxj_de_pasta_local.cmd <folder> [start] [end]` — index raw CDXJ files already downloaded;
- `reconstruir_cobertura_cdxj.cmd` — recompute per-source coverage and rebuild the site;
- `iniciar_historico_nvidia.cmd` — continuous NVIDIA collection of Instagram profiles in 6 tabs (monthly scripts in `historico_*_nvidia.cmd`; light variant in `iniciar_historico_nvidia_leve.cmd`).

## Important files

- `build_arquivo_cdxj_index.py` — builds the filtered index;
- `pregenerator.py` — candidates, AI, grounding, and review queue;
- `historical_relevance.py` — relevance criteria, weights, and levels;
- `gemini_vision.py` — visual photo analysis (framing/suitability);
- `popular_site.py` — population CLI (stories, events, backfill);
- `scripts/collect_snapshots.py` — downloads Arquivo.pt snapshots for stories;
- `scripts/fetch_logos.py` — downloads source logos;
- `publisher.py` — generates/publishes approved posts;
- `build_site.py` — site, data, clean URLs, carousel tenure, pages, and metrics;
- `carrossel_estado.json` — carousel state (tenure/rotation);
- `data/eventos_por_dia.json` — per-day events index for the calendar;
- `pending_posts.json` / `social_metrics.json` / `imgbb_uploads.json` — editorial queue, publication history, and image registry;
- `backend/` — API, database, queue, and fast search;
- `docs/SITE_AND_POSTS.md` — detailed reference for the site and pipelines.

## Weekly newsletter

Subscribers pick their topics by **writing a free-form message** on the `/newsletter/` page. The AI maps that message to the site's categories and **groups subscribers with identical profiles** — one campaign per unique profile, not per person.

- **Email**: minimalist, using the site's colors; each story carries its category, original year, summary and a "Read on the site" link; plus a **"Not what I asked for — reconfigure topics"** button that reopens the topic message; unsubscribe is handled by Brevo.
- **External service**: [Brevo](https://www.brevo.com/) (free tier 300 emails/day). To activate:
  1. Create the Brevo account, a list named `Subscritores`, and copy its **id**;
  2. Create the **v3 API key** (Settings → SMTP & API);
  3. Set `BREVO_API_KEY` and `BREVO_LISTA_BASE_ID` in your local `.env` and in **GitHub Secrets**; add `NEWSLETTER_REMETENTE_EMAIL` (a verified sender email);
  4. (Static site) create a **hosted subscription form** in Brevo and put its URL in `NEWSLETTER_FORM_URL` — that's where the form goes when no dynamic backend is present.
- **Sending**: the `Weekly Newsletter` workflow runs Sundays 19:00 Lisbon time; it interprets new messages (AI), segments profiles, builds and sends the campaigns. `workflow_dispatch` with "seco" records previews without sending.
- **Local testing**: `python scripts/newsletter.py --seco` writes the HTMLs to `newsletter_previews/`.

## Rights and provenance

The project points to pages preserved by Arquivo.pt and identifies the originating publications. Journalistic content keeps the rights of its authors and media outlets. The original source code is available under the [MIT License](LICENSE); the included Montserrat fonts follow the [SIL Open Font License 1.1](images/montserrat/OFL.txt).
