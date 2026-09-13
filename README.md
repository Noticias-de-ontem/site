# Notícias de Ontem

**Português** | [English](README.en.md)

O **Notícias de Ontem** recupera notícias preservadas pelo [Arquivo.pt](https://arquivo.pt), organiza-as por data e volta a apresentá-las com contexto, fonte e ano original — como uma edição de jornal sobre o passado, publicada hoje. Candidato ao [Prémio Arquivo.pt 2027](https://sobre.arquivo.pt/pt/premio-arquivo-pt/).

O projeto tem duas frentes ligadas entre si:

- um site bilingue (PT/EN) para explorar notícias por data e por tema, com páginas individuais em URL limpo estilo jornal;
- um fluxo editorial que prepara posts de Instagram, classifica a relevância histórica e publica após revisão humana.

A arquitetura é estática por omissão (GitHub Pages) e pode passar a dinâmica (FastAPI + PostgreSQL + Celery + OpenSearch) quando há infraestrutura disponível.

## O que existe no site

- **Início** — notícia principal (carrossel de altura fixa), destaques por nível de relevância (Marcos Históricos, Grande Relevância, Mais notícias) e últimas publicações;
- **Calendário** — duas vistas (**Notícias de Ontem**: notícias importantes do mesmo dia em todos os anos; **Dia exato**: só aquela data precisa) em dois formatos (**Mês** ou **Semana**, de domingo a sábado), com filtro por jornal e até 6 publicações do projeto no topo de cada período;
- **Temas** — evolução de uma pesquisa no índice do Arquivo.pt, com gráfico progressivo, filtro por jornal e exportação PNG/SVG/CSV;
- **Documentação** — como funciona, métricas, [níveis de relevância histórica](#relevância-histórica) explicados e grelha de fontes com logos;
- **Notícia individual** — URL limpo estilo jornal (`/noticia/AAAA/MM/DD/slug-id/`), badge de relevância com pontuação completa, página original preservada (snapshot), módulo "No mesmo dia" e navegação anterior/seguinte.

O português é o idioma predefinido; a versão inglesa usa inglês americano natural (não tradução literal).

## Relevância histórica

Cada notícia recebe um **badge** de relevância com ícone + nome, calculado por pontuação ponderada — a IA propõe as notas, o sistema calcula o nível:

| Nível | Nome | O que significa |
| --- | --- | --- |
| 1 | Marco Histórico | Mudança estrutural e duradoura na História (exige ≥90 nos critérios substantivos + justificação de consequências) |
| 2 | Grande Relevância | Consequências nacionais/internacionais muito significativas |
| 3 | Relevância Regional | Impacto forte numa região ou comunidade |
| 4 | Interesse Público | Grande atenção pública, impacto duradouro limitado |
| 5 | Contexto Histórico | Útil para compreender a época |

Critérios: impacto histórico 30% · dimensão do impacto 20% · consequências 15% · relevância posterior 15% · dimensão/duração 10% · **relevância mediática 5% (nunca determina o nível)** · singularidade 5%. Os destaques (notícia principal e carrossel) saem apenas dos níveis 1-2. Explicação completa na página de Documentação.

## Fontes

Jornais, revistas e origens acompanhados pelo projeto:

[![Arquivo.pt](site/assets/logos/arquivo.pt.png)](https://arquivo.pt/)
[![Público](site/assets/logos/publico.pt.png)](https://www.publico.pt/)
[![SIC Notícias](site/assets/logos/sicnoticias.pt.png)](https://sicnoticias.pt/)
[![CNN Portugal](site/assets/logos/cnnportugal.pt.png)](https://cnnportugal.iol.pt/)
[![RTP](site/assets/logos/rtp.pt.png)](https://www.rtp.pt/noticias)
[![Correio da Manhã](site/assets/logos/cmjornal.pt.png)](https://www.cmjornal.pt/)
[![Observador](site/assets/logos/observador.pt.png)](https://observador.pt/)
[![Diário de Notícias](site/assets/logos/dn.pt.png)](https://www.dn.pt/)
[![Jornal de Notícias](site/assets/logos/jn.pt.png)](https://www.jn.pt/)
[![Expresso](site/assets/logos/expresso.pt.png)](https://expresso.pt/)
[![Sábado](site/assets/logos/sabado.pt.png)](https://www.sabado.pt/)
[![Visão](site/assets/logos/visao.pt.png)](https://visao.sapo.pt/)
[![Notícias ao Minuto](site/assets/logos/noticiasaominuto.com.png)](https://www.noticiasaominuto.com/)
[![Renascença](site/assets/logos/renascenca.png)](https://www.tsfdifusao.pt/)
[![4gnews](site/assets/logos/4gnewspt.png)](https://4gnews.pt/)
[![NiT](site/assets/logos/nit.pt.png)](https://nit.pt/)
[![Wikipédia](site/assets/logos/wikipedia.png)](https://pt.wikipedia.org/)

As mesmas fontes aparecem com logos na página de Documentação do site. Conteúdos de perfis da internet (ex.: Epa hSaiu, Hoje no Mundo Militar) são identificados com o chip "Perfil da internet", distinto do chip "Jornal".

## Como os dados circulam

1. Os índices CDXJ públicos do Arquivo.pt são filtrados para os jornais e revistas acompanhados (`recolher_cdxj_*.cmd`);
2. O `pregenerator` procura candidatos para cada data (blocos locais `pt/MM-DD.json` e/ou Arquivo.pt), pede à IA (NVIDIA) 10 opções com categorias, títulos PT/EN, descrição e **pontuação de relevância**;
3. **Grounding obrigatório**: cada opção tem de ficar ancorada a uma captura wayback real (CDX/textsearch do Arquivo.pt); opções desancoradas — como o antigo falso "Ronaldo lidera a I Liga" — são descartadas;
4. As opções ficam em `pending_posts.json` para revisão (images/`review`, `review_pt.html`) e podem ser aprovadas, ignoradas ou regeneradas;
5. O `publisher` publica apenas posts aprovados no Instagram e regista o permalink;
6. `build_site.py` combina posts, métricas, imagens e o índice de eventos em `site/data/news.json`, gera páginas (incluindo snapshots via `collect_snapshots.py`) e analisa cada foto com a Gemini (ponto focal, caras, texto incorporado, adequação a banner/capa);
7. O carrossel tem **tempo de permanência** (`carrossel_estado.json`): cada notícia fica ~8 dias e é depois substituída por outra — sem ser apagada do site.

## Relevância do índice CDXJ

Os CDXJ são índices de metadados do Arquivo.pt (endereços, datas de captura, tipos de conteúdo); não contêm o texto integral. Como os CDXJ filtrados se aproximam de 20 GB, **nunca os guardar no GitHub**: o repositório fica com código, site estático, estados pequenos e dados editoriais.

- Espelho completo dos CDXJ no Hugging Face: dataset `MaNmAxImO/arquivo-pt-cdxj` (autenticar com `HF_TOKEN` no `.env`);
- Recolha a partir do Arquivo.pt: `recolher_cdxj_arquivo_pt.cmd 1996 2026` (retomável, guardando offset/âncora em `arquivo_cdxj_state.json`);
- CDXJ brutos já descarregados: `recolher_cdxj_de_pasta_local.cmd <pasta> 1996 2026`;
- Após a primeira recolha: `reconstruir_cobertura_cdxj.cmd` (datas de cobertura por fonte + rebuild do site);
- Coleções concretas: `python -u build_arquivo_cdxj_index.py --collections AWP30.cdxj --start-year 1996 --end-year 2026`;
- Sincronização com S3/R2 (usado pelo worker do backend): `sync_cdxj_storage.py`.

## Popular o site (geração local)

Tudo passa pelo CLI retomável `popular_site.py` (usa `.env`; 2-3 chamadas NVIDIA por dia gerado):

```cmd
:: gerar ~50 dias (1-2 posts/dia) espalhados pelo ano, usando os blocos locais pt/*.json
python popular_site.py --tudo-ano --source-mode local --limite 50

:: intervalo concreto, com prioridade ao Arquivo.pt
python popular_site.py --start 2026-03-01 --end 2026-03-31 --source-mode arquivo-first

:: só um jornal
python popular_site.py --jornal publico.pt --start 2026-05-01 --end 2026-05-31

:: índice de eventos por dia (Wikipedia "on this day" pontuado por IA) — dá
:: conteúdo ao calendário para os 365 dias; retomável e em cache
python popular_site.py --com-eventos

:: completar posts antigos (relevância, EN, wayback)
python popular_site.py --backfill-relevance
```

Modos de fonte: `local` (blocos `pt/*.json` recolhidos), `local-first`, `arquivo-first`, `arquivo-only`.

## Preparar posts e revisão

Alternativa direta ao `popular_site`:

```cmd
python -u pregenerator.py --lang pt --start-date 2026-07-01 --end-date 2026-07-31 --source-mode arquivo-first
```

A análise de fotos de fundo pode ser regenerada individualmente (`python regenerate_missing_backgrounds.py <post_id> ...`), sempre validada pela Gemini. Estados em `pending_posts.json`: `pending`, `approved`, `published`, `skip`.

## Pesquisa por temas

A página de temas compara até quatro pesquisas, com filtro por fonte e cores próprias. Os valores são verificados por paginação (`dedupValue=0`) com limites de pedidos ao Arquivo.pt; falhas ficam como não verificadas, nunca como zero. Com backend + OpenSearch completos, uma agregação anual substitui a paginação.

## Site dinâmico e análise rápida

`render.yaml` prepara: FastAPI + frontend (Web Service), Celery (worker), atualização de CDXJ/OpenSearch (segundo worker persistente), PostgreSQL, fila Valkey/Redis e OpenSearch opcional. O índice inicial é pesado (dias) e não deve correr em Actions. Manual completo: [`DYNAMIC_DEPLOYMENT.md`](DYNAMIC_DEPLOYMENT.md). Versão estática no Hugging Face: [`HF_DEPLOYMENT.md`](HF_DEPLOYMENT.md).

## Gerar e testar o site

```cmd
python -u build_site.py
python -m http.server 8765 --directory site
```

Abrir [http://localhost:8765/inicio/](http://localhost:8765/inicio/). Em desenvolvimento, para não reler os CDXJ:

```powershell
$env:SITE_SKIP_CDXJ_REFRESH='1'; python -u build_site.py
```

## Métricas

Reconstruídas em cada `build_site.py`: notícias cobertas e intervalo temporal (estado dos CDXJ), fontes distintas, publicações acumuladas (`social_metrics.json`) e seguidores das redes configuradas. Quando as credenciais Meta falham, conserva o último valor válido em vez de zerar.

## Workflows principais

- `Pregenerate PT Review Queue` / `Pregenerate PT Interval Review Queue` — fila editorial;
- `Daily Instagram Publisher` — publica aprovados e reconstrói o site;
- `Deploy Website` — gera e publica no GitHub Pages;
- `Sync Dynamic Website` — envia o retrato público para a API;
- `Cleanup Used ImgBB Images` — limpeza de imagens usadas;
- `Weekly Data Extraction` — atualiza os arquivos locais complementares.

## Configuração

- `NVIDIA_API_KEY`, `NVIDIA_MODEL` — análise e preparação editorial;
- `GEMINI_API_KEY` — análise de fotos (ponto focal, caras, texto, adequação; com cache em `gemini_photo_cache.json` e fallback OpenCV sem chave);
- `IMGBB_API_KEY` — alojamento de imagens de revisão;
- `IG_ACCESS_TOKEN_PT`, `IG_USER_ID_PT` — publicação no Instagram;
- `SITE_API_URL`, `SITE_SYNC_TOKEN` — sincronização dinâmica;
- `SITE_PUBLIC_URL` — domínio público final (canonical/sitemap/dados estruturados);
- `DATABASE_URL`, `REDIS_URL`, `OPENSEARCH_URL`, `OPENSEARCH_API_KEY`, `OPENSEARCH_INDEX` — infraestrutura dinâmica.

Chaves nunca no repositório: em GitHub Actions, usar **Settings > Secrets and variables > Actions**; localmente, ficheiro `.env` (não commitado) ou `nvidia_api_key.local.txt`.

## Comandos .cmd úteis

- `recolher_cdxj_arquivo_pt.cmd [inicio] [fim]` — construir/retomar o índice CDXJ a partir do Arquivo.pt;
- `recolher_cdxj_de_pasta_local.cmd <pasta> [inicio] [fim]` — indexar CDXJ brutos já descarregados;
- `reconstruir_cobertura_cdxj.cmd` — recalcular cobertura por fonte e regenerar o site;
- `iniciar_historico_nvidia.cmd` — recolha contínua dos perfis de Instagram com NVIDIA em 6 separadores (mensais em `historico_*_nvidia.cmd`; versão leve em `iniciar_historico_nvidia_leve.cmd`).

## Ficheiros importantes

- `build_arquivo_cdxj_index.py` — constrói o índice filtrado;
- `pregenerator.py` — candidatos, IA, grounding e fila de revisão;
- `historical_relevance.py` — critérios, pesos e níveis de relevância;
- `gemini_vision.py` — análise visual de fotos (enquadramento/adequação);
- `popular_site.py` — CLI de população (notícias, eventos, backfill);
- `collect_snapshots.py` — descarrega snapshots do Arquivo.pt para as notícias;
- `fetch_logos.py` — descarrega as logos das fontes;
- `publisher.py` — geração/publicação dos posts aprovados;
- `build_site.py` — site, dados, URLs limpos, carrossel de permanência, páginas e métricas;
- `carrossel_estado.json` — estado do carrossel (permanência/rotação);
- `data/eventos_por_dia.json` — índice de eventos por dia para o calendário;
- `pending_posts.json` / `social_metrics.json` / `imgbb_uploads.json` — fila editorial, histórico de publicações e registo de imagens;
- `backend/` — API, base de dados, fila e pesquisa rápida;
- `SITE_AND_POSTS.md` — referência detalhada do site e dos fluxos.

## Direitos e proveniência

O projeto aponta para páginas preservadas pelo Arquivo.pt e identifica as publicações de origem. Os conteúdos jornalísticos mantêm os direitos dos respetivos autores e meios de comunicação. O código-fonte original é disponibilizado sob a [Licença MIT](LICENSE); as fontes Montserrat incluídas seguem a [SIL Open Font License 1.1](images/montserrat/OFL.txt).
