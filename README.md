# Notícias de Ontem

**Português** | [English](README.en.md)

O **Notícias de Ontem** recupera notícias preservadas pelo [Arquivo.pt](https://arquivo.pt), organiza-as por data e volta a apresentá-las com contexto, fonte e ano original. O Arquivo.pt é a fonte principal do projeto; os sites atuais dos jornais não são usados para substituir páginas que não estejam preservadas.

O projeto tem duas frentes ligadas entre si:

- um site bilingue, em português e inglês, para explorar notícias por data e por tema;
- um fluxo editorial que prepara posts, permite revisão humana e publica os aprovados no Instagram.

O site pode continuar a funcionar em GitHub Pages como versão de segurança, mas a arquitetura principal passou a ser dinâmica: FastAPI serve o site e a API, PostgreSQL guarda o retrato público mais recente, Celery processa análises demoradas e uma fila Valkey/Redis coordena os trabalhos. Um índice OpenSearch opcional torna rápidas também as pesquisas inéditas.

## O que existe no site

- `/inicio/`: notícia principal, carrossel editorial e publicações recentes;
- `/calendário/`: notícias importantes do mesmo dia ao longo de vários anos;
- `/temas/`: evolução de uma pesquisa no índice do Arquivo.pt, com filtro por publicação e datas exatas;
- `/documentação/`: explicação simples do projeto e métricas atualizadas;
- `/noticia/?id=...`: página única de cada notícia, com contexto, imagem e ligação à fonte preservada.

As rotas sem acentos (`/calendario/` e `/documentacao/`) também existem para compatibilidade. O português é o idioma predefinido.

## Como os dados circulam

1. Os índices CDXJ públicos do Arquivo.pt são filtrados para os jornais e revistas acompanhados.
2. O pregenerator procura candidatos para cada data, compara anos, fontes e temas e prepara opções editoriais.
3. As opções ficam em `pending_posts.json`, onde podem ser aprovadas, ignoradas ou regeneradas.
4. O publisher publica apenas posts aprovados e regista o identificador e o endereço do Instagram.
5. `build_site.py` combina posts, métricas e imagens em `site/data/news.json`; as recomendações do calendário são pedidas à API dinâmica.
6. `Sync Dynamic Website` envia o retrato público para a API protegida e guarda-o em PostgreSQL.

Os workflows de publicação e pré-geração chamam esta sincronização diretamente depois de reconstruírem o site. Isto é necessário porque os commits automáticos usam `[skip ci]` e não lançariam um segundo workflow por `push`.
7. O frontend lê a versão dinâmica; se a API não estiver disponível, continua a conseguir abrir o retrato estático.

O uso de modelos de linguagem apoia a seleção, a síntese e a preparação editorial. A notícia, a data histórica e a ligação de origem continuam ancoradas no Arquivo.pt, e a publicação final passa por revisão humana.

Para publicar apenas a versão estática no Hugging Face, consulta [`HF_DEPLOYMENT.md`](HF_DEPLOYMENT.md). Essa opção usa um Static Space para o site e mantém os CDXJ pesados separadamente no Hugging Face.

## CDXJ

Os CDXJ são índices de metadados do Arquivo.pt. Contêm endereços, datas de captura, tipos de conteúdo e outros campos úteis para localizar páginas preservadas; não contêm o texto integral das notícias.

Como os CDXJ filtrados já se aproximam de 20 GB, a regra de operação gratuita é: **não guardar CDXJ, bases SQLite, dumps OpenSearch, ficheiros `.jsonl/.ndjson/.cdxj/.gz` pesados ou artefactos de reconstrução dentro do GitHub**. O repositório deve ficar só com código, site estático, estados pequenos e dados editoriais. O GitHub recomenda repositórios pequenos, idealmente abaixo de 1 GB e fortemente abaixo de 5 GB; 20 GB de índices tornariam clones, Actions e Pages lentos ou problemáticos.

### Plano gratuito para CDXJ perto de 20 GB

Para manter o projeto gratuito, exceto a compra do domínio final, usa esta separação:

- **GitHub Free**: código, workflows, `pending_posts.json`, `social_metrics.json`, páginas geradas e estados pequenos. Não é armazenamento de dados brutos.
- **GitHub Pages ou Cloudflare Pages Free**: frontend público estático/fallback. Cloudflare Pages é uma boa opção quando quiseres domínio final e CDN sem pagar alojamento; confirma sempre os limites atuais antes de migrar.
- **Disco local pessoal ou GitHub Actions cache temporária**: construção e atualização dos CDXJ filtrados. O índice de 20 GB deve viver fora do repositório e ser reconstruível a partir do Arquivo.pt.
- **Chunks comprimidos fora do Git**: se precisares de transportar o índice entre máquinas, divide por coleção ou ano (`arquivo_cdxj/YYYY/...`) e comprime (`.zst` ou `.gz`). Mantém um manifesto pequeno com nome, tamanho, hash e intervalo temporal.
- **R2/S3 só se couber no free tier**: Cloudflare R2 inclui apenas uma pequena franquia gratuita de armazenamento mensal; 20 GB persistentes podem ultrapassar essa franquia. Usa R2 apenas para snapshots parciais, estados, imagens e backups pequenos, ou aceita que acima do limite gratuito haverá custo.
- **Sem OpenSearch pago por defeito**: enquanto o objetivo for custo zero, a página de temas deve funcionar com TextSearch do Arquivo.pt, cache local e trabalhos por lotes. O índice OpenSearch integral fica opcional para uma fase com orçamento.
- **Base de dados gratuita/evitável**: para custo zero, o retrato público continua em JSON estático. PostgreSQL/Redis/Workers só entram se estiverem dentro de planos gratuitos e sem bloquear o fallback estático.

Fluxo recomendado quando os CDXJ estão grandes:

1. Reconstruir/atualizar CDXJ numa máquina local ou runner manual, nunca num commit.
2. Guardar apenas `arquivo_cdxj_state.json` e manifestos pequenos, sem os ficheiros pesados.
3. Gerar `site/data/news.json` e páginas estáticas a partir do estado local.
4. Publicar o site em GitHub Pages/Cloudflare Pages.
5. Usar o domínio comprado apenas como camada final (`SITE_PUBLIC_URL`), mantendo todo o resto em serviços gratuitos.


Para construir ou retomar o índice filtrado entre 1996 e 2026:

```cmd
recolher_cdxj_arquivo_pt.cmd 1996 2026
```

O progresso é guardado em `arquivo_cdxj_state.json`. Uma execução posterior:

- acrescenta coleções novas;
- volta a processar coleções que tenham mudado;
- mantém as coleções que continuam iguais;
- retoma uma coleção atualizada a partir do offset guardado quando o prefixo antigo ainda coincide;
- remove os registos antigos de uma coleção antes de uma reconstrução completa ou quando o prefixo mudou.

Cada coleção concluída guarda em `arquivo_cdxj_state.json` a posição em bytes e uma âncora do prefixo. A âncora é validada através de `Range` antes de uma atualização remota; isto evita assumir que a ordem dos CDXJ é temporal, algo que não é garantido. Os estados anteriores podem ser preenchidos explicitamente, incluindo as âncoras:

```cmd
python -u build_arquivo_cdxj_index.py --migrate-state-only
```

Se a âncora não puder ser validada, a coleção fica pendente para evitar iniciar silenciosamente uma leitura remota potencialmente insegura.

Se os CDXJ brutos já estiverem numa pasta local:

```cmd
recolher_cdxj_de_pasta_local.cmd C:\caminho\para\cdxj_brutos 1996 2026
```

Também é possível processar coleções concretas:

```cmd
python -u build_arquivo_cdxj_index.py --collections AWP30.cdxj AWP31.cdxj --start-year 1996 --end-year 2026
```

O modo `--all-remote` percorre todas as coleções remotas e pode demorar muitas horas ou dias. Deve ser usado para a construção inicial, não em todas as execuções normais.

Depois de terminar a primeira recolha completa, executa uma vez:

```cmd
reconstruir_cobertura_cdxj.cmd
```

Este comando calcula a primeira e a última captura de cada fonte e volta a gerar o site. A data máxima do gráfico passa a ser a última data realmente coberta pelos CDXJ; ao escolher um jornal, o limite muda para a última captura desse jornal.

## Preparar posts

Para preparar um intervalo em português, dando prioridade ao Arquivo.pt:

```cmd
python -u pregenerator.py --lang pt --start-date 2026-07-01 --end-date 2026-07-31 --source-mode arquivo-first
```

Modos disponíveis:

- `arquivo-first`: Arquivo.pt primeiro e arquivo local como apoio;
- `arquivo-only`: apenas informação recuperada através do Arquivo.pt;
- `local-first`: arquivo local primeiro;
- `local`: apenas dados locais.

O ficheiro `review_pt.html` permite rever as opções. Os estados usados em `pending_posts.json` são:

- `pending`: à espera de decisão;
- `approved`: autorizado para publicação;
- `published`: publicação concluída;
- `skip`: opção rejeitada.

## Pesquisa por temas

A página de temas compara até quatro pesquisas. Cada clique no `+` acrescenta uma análise e o botão desaparece quando são atingidas quatro; se uma for removida, volta a aparecer. Cada série tem fonte e cor próprias. Os números exatos sobre os pontos podem ser mostrados ou ocultados, e a legenda identifica tema, fonte, cor e total.

PNG, SVG e CSV incluem todas as séries. O SVG/PNG leva a legenda desenhada no próprio ficheiro; o CSV inclui análise, tema, fonte, cor, total, estado de verificação, datas, método e URL da consulta. Os cabeçalhos e textos exportados acompanham o idioma atual do site.

Sem índice rápido, a página consulta apenas a TextSearch API do Arquivo.pt. O nome de um jornal, como `www.publico.pt`, é enviado à API como filtro do índice preservado; o site atual desse jornal não é contactado.

O campo `estimated_nr_results` é usado apenas como pista interna para acelerar a procura da fronteira. O número apresentado no gráfico é verificado por paginação com `dedupValue=0`: a aplicação confirma a existência do último `offset` e a ausência do seguinte. Quando um intervalo ultrapassa a janela de resultados da API, é dividido em períodos menores e contado novamente. Um pedido que falhe fica assinalado como não verificado e nunca é convertido em zero.

Os valores representam registos arquivados que correspondem à pesquisa. A mesma página pode contar mais de uma vez se tiver sido preservada em momentos diferentes. O CSV exportado inclui datas, estado de verificação, método, URL da consulta e instante de recolha.

Para evitar milhares de pedidos ao Arquivo.pt, cada análise tem um limite de verificações e respeita o limite oficial de pedidos. Quando esse limite é atingido, os anos em falta ficam como não verificados e nunca são convertidos em zero.

O backend verifica primeiro se o índice OpenSearch está completo para o intervalo. Se estiver, uma agregação anual devolve todos os pontos da série numa só consulta. Se estiver incompleto ou indisponível, o trabalho passa para a fila e usa a API oficial. O índice rápido só é ativado depois de todos os ficheiros e páginas do intervalo terem sido indexados sem falhas.

## Site dinâmico e análise rápida

A infraestrutura preparada em `render.yaml` usa:

- Render Web Service para FastAPI e o frontend;
- Render Background Worker para Celery;
- um segundo worker persistente para atualizar CDXJ e OpenSearch;
- Render PostgreSQL para dados públicos e resultados em cache;
- Render Key Value para a fila;
- um serviço compatível com OpenSearch para o índice de texto;
- armazenamento de objetos S3/R2, recomendado para os CDXJ, cópias do índice e dados de reconstrução.

O OpenSearch não substitui o Arquivo.pt como fonte. Cada documento do índice corresponde a uma captura recuperada do Arquivo.pt e conserva URL, data, jornal e ligação preservada. Os CDXJ localizam as capturas; o texto é obtido das páginas preservadas.

O processo inicial do índice é pesado e não deve correr num GitHub Action normal. Pode demorar vários dias e exigir dezenas ou centenas de gigabytes, conforme o número e o tamanho das páginas. Depois desse primeiro carregamento, `build_topic_search_index.py` salta ficheiros inalterados e reprocessa apenas ficheiros novos ou modificados.

`backend/index_update_worker.py` automatiza o ciclo seguinte num disco persistente: recebe alterações do bucket, verifica coleções CDXJ novas ou modificadas no Arquivo.pt, atualiza o backup, sincroniza para PostgreSQL os anos e as fontes cobertos e executa o indexador.

O manual completo está em [`DYNAMIC_DEPLOYMENT.md`](DYNAMIC_DEPLOYMENT.md).

## Gerar e testar o site

```cmd
python -u build_site.py
python -m http.server 8765 --directory site
```

Depois abre [http://localhost:8765/inicio/](http://localhost:8765/inicio/).

Durante desenvolvimento, quando não queres reler vários gigabytes de CDXJ:

```powershell
$env:SITE_SKIP_CDXJ_REFRESH='1'
python -u build_site.py
```

Esta opção preserva a cache existente; os workflows normais continuam a detetar CDXJ novos ou alterados.

## Métricas

As métricas da documentação são reconstruídas em cada execução de `build_site.py`:

- notícias cobertas e intervalo temporal, a partir do estado dos CDXJ;
- fontes distintas, juntando jornais, revistas e perfis sem repetir a mesma marca;
- publicações acumuladas, conservadas em `social_metrics.json`;
- seguidores de todas as redes configuradas.

Na página pública, as métricas secundárias mostram apenas anos cobertos e fontes. Os três números principais reiniciam a animação sempre que o utilizador entra na documentação; em dispositivos com redução de movimento, a contagem é mais curta, mas continua visível.

Quando as credenciais Meta estão disponíveis, o build atualiza `followers_count`. Se a API falhar, conserva o último valor válido em vez de o substituir por zero.

## Workflows principais

- `Pregenerate PT Review Queue`: prepara a fila editorial regular;
- `Pregenerate PT Interval Review Queue`: prepara um intervalo manual e pode atualizar coleções CDXJ indicadas;
- `Daily Instagram Publisher`: publica posts aprovados e reconstrói o site;
- `Deploy Website`: gera e publica o site no GitHub Pages;
- `Sync Dynamic Website`: envia posts, métricas e cobertura para a API dinâmica;
- `Cleanup Used ImgBB Images`: remove imagens já utilizadas segundo o registo do projeto;
- `Weekly Data Extraction`: atualiza os arquivos locais complementares.

No workflow por intervalo, `update_cdxj` só executa a atualização quando também são indicadas coleções em `cdxj_collections` ou quando `cdxj_all_remote` é ativado deliberadamente.

## Configuração

Segredos e variáveis usados pelos fluxos, conforme a funcionalidade ativa:

- `NVIDIA_API_KEY` e `NVIDIA_MODEL`;
- `GEMINI_API_KEY`;
- `IMGBB_API_KEY`;
- `IG_ACCESS_TOKEN_PT` e `IG_USER_ID_PT`.
- `SITE_API_URL` e `SITE_SYNC_TOKEN` para sincronização dinâmica;
- `SITE_PUBLIC_URL` com o domínio público final, usado nos URLs canónicos, sitemap e dados estruturados;
- `DATABASE_URL` e `REDIS_URL`, fornecidos pelo Render;
- `OPENSEARCH_URL`, `OPENSEARCH_API_KEY` e `OPENSEARCH_INDEX` para a pesquisa rápida.

As chaves nunca devem ser guardadas no repositório. Em GitHub Actions, configura-as em **Settings > Secrets and variables > Actions**.

## Ficheiros importantes

- `build_arquivo_cdxj_index.py`: constrói o índice filtrado;
- `pregenerator.py`: seleciona candidatos e cria a fila de revisão;
- `publisher.py`: gera/publica posts aprovados;
- `build_site.py`: prepara dados, páginas e métricas do site;
- `site/sitemap.xml` e `site/robots.txt`: índice público e regras de rastreio, regenerados com o site;
- `backend/`: API, base de dados, fila e pesquisa rápida;
- `build_topic_search_index.py`: constrói/atualiza o índice integral OpenSearch;
- `sync_dynamic_site.py`: envia o retrato público para o backend;
- `sync_cdxj_storage.py`: sincroniza CDXJ e estados com S3 ou R2;
- `render.yaml`: infraestrutura dinâmica no Render;
- `pending_posts.json`: fila editorial;
- `social_metrics.json`: histórico de publicações e seguidores;
- `backend/calendar_service.py`: recomendações dinâmicas por dia e fonte e páginas permanentes das notícias indexadas;
- `SITE_AND_POSTS.md`: referência detalhada do site e dos fluxos;
- `PLANO_PREMIO_ARQUIVO_PT_2027.md`: plano de evolução da candidatura.

## Direitos e proveniência

O projeto aponta para páginas preservadas pelo Arquivo.pt e identifica as publicações de origem. Os conteúdos jornalísticos mantêm os direitos dos respetivos autores e meios de comunicação.

O código-fonte original deste projeto é disponibilizado sob a [Licença MIT](LICENSE). A licença não abrange notícias, fotografias, marcas ou outros conteúdos de terceiros, que permanecem sujeitos aos direitos dos respetivos titulares. As fontes Montserrat incluídas no repositório são distribuídas separadamente sob a [SIL Open Font License 1.1](images/montserrat/OFL.txt).
