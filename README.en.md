# Notícias de Ontem

[Português](README.md) | **English**

**Notícias de Ontem** retrieves news preserved by [Arquivo.pt](https://arquivo.pt), organizes it by date, and presents it again with context, source, and original year. Arquivo.pt is the project's main source; current newspaper websites are not used to replace pages that have not been preserved.

The project has two interconnected components:

- a bilingual website, in Portuguese and English, for exploring news by date and topic;
- an editorial workflow that prepares posts, enables human review, and publishes approved posts on Instagram.

The website can continue to run on GitHub Pages as a fallback version, but the main architecture is now dynamic: FastAPI serves the website and API, PostgreSQL stores the latest public snapshot, Celery processes time-consuming analyses, and a Valkey/Redis queue coordinates the jobs. An optional OpenSearch index also makes new searches fast.

## What is available on the website

- `/inicio/`: lead story, editorial carousel, and recent posts;
- `/calendário/`: important news from the same day across several years;
- `/temas/`: evolution of a search in the Arquivo.pt index, with filters by publication and exact dates;
- `/documentação/`: a simple explanation of the project and updated metrics;
- `/noticia/?id=...`: a dedicated page for each news story, with context, image, and a link to the preserved source.

The unaccented routes (`/calendario/` and `/documentacao/`) are also available for compatibility. Portuguese is the default language.

## How the data flows

1. Arquivo.pt's public CDXJ indexes are filtered for the newspapers and magazines being tracked.
2. The pregenerator searches for candidates for each date, compares years, sources, and topics, and prepares editorial options.
3. The options are stored in `pending_posts.json`, where they can be approved, skipped, or regenerated.
4. The publisher publishes only approved posts and records the Instagram identifier and address.
5. `build_site.py` combines posts, metrics, and images in `site/data/news.json`; calendar recommendations are requested from the dynamic API.
6. `Sync Dynamic Website` sends the public snapshot to the protected API and stores it in PostgreSQL.

The publishing and pregeneration workflows call this synchronization directly after rebuilding the website. This is necessary because automated commits use `[skip ci]` and would not trigger a second workflow on `push`.
7. The frontend reads the dynamic version; if the API is unavailable, it can still open the static snapshot.

Language models support selection, summarization, and editorial preparation. The news story, historical date, and source link remain anchored in Arquivo.pt, and the final post undergoes human review.

For a Hugging Face-only public website, see [`HF_DEPLOYMENT.md`](HF_DEPLOYMENT.md). This option uses a Static Space for the site and keeps the large CDXJ files separately on Hugging Face.

## CDXJ

CDXJ files are Arquivo.pt metadata indexes. They contain addresses, capture dates, content types, and other fields useful for locating preserved pages; they do not contain the full text of the news stories.

Because the filtered CDXJ files are already approaching 20 GB, the rule for operating at no cost is: **do not store CDXJ files, SQLite databases, OpenSearch dumps, large `.jsonl/.ndjson/.cdxj/.gz` files, or reconstruction artifacts on GitHub**. The repository should contain only code, the static website, small state files, and editorial data. GitHub recommends keeping repositories small, ideally below 1 GB and well below 5 GB; 20 GB of indexes would make clones, Actions, and Pages slow or problematic.

### Free plan for CDXJ data approaching 20 GB

To keep the project free, apart from purchasing the final domain, use this separation:

- **GitHub Free**: code, workflows, `pending_posts.json`, `social_metrics.json`, generated pages, and small state files. It is not storage for raw data.
- **GitHub Pages or Cloudflare Pages Free**: public static/fallback frontend. Cloudflare Pages is a good option when you want the final domain and a CDN without paying for hosting; always confirm the current limits before migrating.
- **Personal local disk or temporary GitHub Actions cache**: building and updating the filtered CDXJ files. The 20 GB index should live outside the repository and be reproducible from Arquivo.pt.
- **Compressed chunks outside Git**: if you need to move the index between machines, split it by collection or year (`arquivo_cdxj/YYYY/...`) and compress it (`.zst` or `.gz`). Keep a small manifest with the name, size, hash, and date range.
- **R2/S3 only if it fits within the free tier**: Cloudflare R2 includes only a small monthly free storage allowance; 20 GB of persistent data may exceed that allowance. Use R2 only for partial snapshots, state files, images, and small backups, or accept that exceeding the free limit will incur a cost.
- **No paid OpenSearch by default**: while the goal is zero cost, the topics page should work with Arquivo.pt TextSearch, a local cache, and batch jobs. The full OpenSearch index remains optional for a phase with a budget.
- **Free/avoidable database**: for zero cost, the public snapshot remains in static JSON. PostgreSQL/Redis/Workers are introduced only if they fit within free plans and do not block the static fallback.

Recommended workflow when the CDXJ data is large:

1. Rebuild/update CDXJ data on a local machine or manual runner, never in a commit.
2. Store only `arquivo_cdxj_state.json` and small manifests, without the large files.
3. Generate `site/data/news.json` and static pages from the local state.
4. Publish the website on GitHub Pages/Cloudflare Pages.
5. Use the purchased domain only as the final layer (`SITE_PUBLIC_URL`), keeping everything else on free services.


To build or resume the filtered index between 1996 and 2026:

```cmd
recolher_cdxj_arquivo_pt.cmd 1996 2026
```

Progress is stored in `arquivo_cdxj_state.json`. A subsequent run:

- adds new collections;
- reprocesses collections that have changed;
- keeps collections that remain unchanged;
- resumes an updated collection from the saved offset when the old prefix still matches;
- removes old records from a collection before a full rebuild or when the prefix has changed.

For each completed collection, `arquivo_cdxj_state.json` stores the byte position and a prefix anchor. The anchor is validated through `Range` before a remote update; this avoids assuming that CDXJ ordering is chronological, which is not guaranteed. Previous state files can be populated explicitly, including the anchors:

```cmd
python -u build_arquivo_cdxj_index.py --migrate-state-only
```

If the anchor cannot be validated, the collection remains pending to avoid silently starting a potentially unsafe remote read.

If the raw CDXJ files are already in a local folder:

```cmd
recolher_cdxj_de_pasta_local.cmd C:\caminho\para\cdxj_brutos 1996 2026
```

Specific collections can also be processed:

```cmd
python -u build_arquivo_cdxj_index.py --collections AWP30.cdxj AWP31.cdxj --start-year 1996 --end-year 2026
```

The `--all-remote` mode goes through all remote collections and can take many hours or days. It should be used for the initial build, not for every normal run.

After completing the first full data collection, run this once:

```cmd
reconstruir_cobertura_cdxj.cmd
```

This command calculates the first and last capture for each source and regenerates the website. The chart's maximum date becomes the last date actually covered by the CDXJ data; when a newspaper is selected, the limit changes to that newspaper's last capture.

## Preparing posts

To prepare a date range in Portuguese, prioritizing Arquivo.pt:

```cmd
python -u pregenerator.py --lang pt --start-date 2026-07-01 --end-date 2026-07-31 --source-mode arquivo-first
```

Available modes:

- `arquivo-first`: Arquivo.pt first, with the local archive as support;
- `arquivo-only`: only information retrieved through Arquivo.pt;
- `local-first`: local archive first;
- `local`: local data only.

The `review_pt.html` file is used to review the options. The states used in `pending_posts.json` are:

- `pending`: awaiting a decision;
- `approved`: authorized for publication;
- `published`: publication completed;
- `skip`: option rejected.

## Topic search

The topics page compares up to four searches. Each click on `+` adds an analysis, and the button disappears when the limit of four is reached; if one is removed, it reappears. Each series has its own source and color. Exact numbers above the points can be shown or hidden, and the legend identifies the topic, source, color, and total.

PNG, SVG, and CSV include all series. The SVG/PNG includes the legend drawn into the file itself; the CSV includes the analysis, topic, source, color, total, verification status, dates, method, and query URL. Exported headings and text follow the website's current language.

Without a fast index, the page queries only the Arquivo.pt TextSearch API. A newspaper name, such as `www.publico.pt`, is sent to the API as a filter for the preserved index; that newspaper's current website is not contacted.

The `estimated_nr_results` field is used only as an internal hint to speed up the boundary search. The number shown in the chart is verified through pagination with `dedupValue=0`: the application confirms that the last `offset` exists and the next one does not. When a range exceeds the API's result window, it is divided into smaller periods and counted again. A failed request is marked as unverified and is never converted to zero.

The values represent archived records that match the search. The same page may be counted more than once if it was preserved at different times. The exported CSV includes dates, verification status, method, query URL, and retrieval timestamp.

To avoid thousands of requests to Arquivo.pt, each analysis has a verification limit and respects the official request limit. When that limit is reached, missing years remain unverified and are never converted to zero.

The backend first checks whether the OpenSearch index is complete for the range. If it is, an annual aggregation returns all points in the series in a single query. If it is incomplete or unavailable, the job moves to the queue and uses the official API. The fast index is enabled only after all files and pages in the range have been indexed without errors.

## Dynamic website and fast analysis

The infrastructure prepared in `render.yaml` uses:

- Render Web Service for FastAPI and the frontend;
- Render Background Worker for Celery;
- a second persistent worker to update CDXJ data and OpenSearch;
- Render PostgreSQL for public data and cached results;
- Render Key Value for the queue;
- an OpenSearch-compatible service for the text index;
- S3/R2 object storage, recommended for CDXJ data, index copies, and reconstruction data.

OpenSearch does not replace Arquivo.pt as the source. Each document in the index corresponds to a capture retrieved from Arquivo.pt and retains its URL, date, newspaper, and preserved link. The CDXJ files locate the captures; the text is obtained from the preserved pages.

The initial indexing process is resource-intensive and should not run in a normal GitHub Action. It can take several days and require tens or hundreds of gigabytes, depending on the number and size of the pages. After this initial load, `build_topic_search_index.py` skips unchanged files and reprocesses only new or modified files.

`backend/index_update_worker.py` automates the following cycle on a persistent disk: it receives changes from the bucket, checks for new or modified CDXJ collections on Arquivo.pt, updates the backup, synchronizes the covered years and sources to PostgreSQL, and runs the indexer.

The complete guide is available in [`DYNAMIC_DEPLOYMENT.md`](DYNAMIC_DEPLOYMENT.md).

## Generating and testing the website

```cmd
python -u build_site.py
python -m http.server 8765 --directory site
```

Then open [http://localhost:8765/inicio/](http://localhost:8765/inicio/).

During development, when you do not want to reread several gigabytes of CDXJ data:

```powershell
$env:SITE_SKIP_CDXJ_REFRESH='1'
python -u build_site.py
```

This option preserves the existing cache; normal workflows continue to detect new or modified CDXJ files.

## Metrics

The documentation metrics are rebuilt each time `build_site.py` runs:

- news coverage and date range, based on the CDXJ state;
- distinct sources, combining newspapers, magazines, and profiles without counting the same brand more than once;
- cumulative posts, retained in `social_metrics.json`;
- followers across all configured networks.

On the public page, the secondary metrics show only years covered and sources. The three main numbers restart their animation whenever the user enters the documentation page; on devices with reduced motion, the count is shorter but remains visible.

When Meta credentials are available, the build updates `followers_count`. If the API fails, it retains the last valid value instead of replacing it with zero.

## Main workflows

- `Pregenerate PT Review Queue`: prepares the regular editorial queue;
- `Pregenerate PT Interval Review Queue`: prepares a manual date range and can update specified CDXJ collections;
- `Daily Instagram Publisher`: publishes approved posts and rebuilds the website;
- `Deploy Website`: generates and publishes the website on GitHub Pages;
- `Sync Dynamic Website`: sends posts, metrics, and coverage to the dynamic API;
- `Cleanup Used ImgBB Images`: removes images already used according to the project's records;
- `Weekly Data Extraction`: updates the supplementary local archives.

In the date-range workflow, `update_cdxj` runs the update only when collections are also specified in `cdxj_collections` or when `cdxj_all_remote` is deliberately enabled.

## Configuration

Secrets and variables used by the workflows, depending on the enabled functionality:

- `NVIDIA_API_KEY` and `NVIDIA_MODEL`;
- `GEMINI_API_KEY`;
- `IMGBB_API_KEY`;
- `IG_ACCESS_TOKEN_PT` and `IG_USER_ID_PT`.
- `SITE_API_URL` and `SITE_SYNC_TOKEN` for dynamic synchronization;
- `SITE_PUBLIC_URL` with the final public domain, used in canonical URLs, the sitemap, and structured data;
- `DATABASE_URL` and `REDIS_URL`, provided by Render;
- `OPENSEARCH_URL`, `OPENSEARCH_API_KEY`, and `OPENSEARCH_INDEX` for fast search.

Keys must never be stored in the repository. In GitHub Actions, configure them under **Settings > Secrets and variables > Actions**.

## Important files

- `build_arquivo_cdxj_index.py`: builds the filtered index;
- `pregenerator.py`: selects candidates and creates the review queue;
- `publisher.py`: generates/publishes approved posts;
- `build_site.py`: prepares the website's data, pages, and metrics;
- `site/sitemap.xml` and `site/robots.txt`: public index and crawling rules, regenerated with the website;
- `backend/`: API, database, queue, and fast search;
- `build_topic_search_index.py`: builds/updates the full OpenSearch index;
- `sync_dynamic_site.py`: sends the public snapshot to the backend;
- `sync_cdxj_storage.py`: synchronizes CDXJ data and state files with S3 or R2;
- `render.yaml`: dynamic infrastructure on Render;
- `pending_posts.json`: editorial queue;
- `social_metrics.json`: history of posts and followers;
- `backend/calendar_service.py`: dynamic recommendations by day and source, and permanent pages for indexed news stories;
- `SITE_AND_POSTS.md`: detailed reference for the website and workflows;
- `PLANO_PREMIO_ARQUIVO_PT_2027.md`: development plan for the submission.

## Rights and provenance

The project links to pages preserved by Arquivo.pt and identifies the original publications. Journalistic content remains the property of its respective authors and media organizations.

This project's original source code is made available under the [MIT License](LICENSE). The license does not cover news stories, photographs, trademarks, or other third-party content, which remain subject to the rights of their respective owners. The Montserrat fonts included in the repository are distributed separately under the [SIL Open Font License 1.1](images/montserrat/OFL.txt).
