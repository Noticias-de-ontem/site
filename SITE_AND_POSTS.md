# Notícias de Ontem: site, posts e CDXJ

## Site

O frontend vive em `site/` e pode ser servido pelo backend dinâmico ou, como fallback, pelo GitHub Pages:

- `site/index.html`: estrutura das páginas.
- `site/styles.css`: estilo responsivo.
- `site/app.js`: idioma, rotas, carrossel, calendário e métricas.
- `site/data/news.json`: dados gerados automaticamente.
- `site/assets/`: ícone temporário e imagens copiadas dos posts.
- `backend/calendar_service.py`: consulta dinâmica das recomendações por dia e fonte no índice construído a partir do Arquivo.pt.
- `backend/`: API FastAPI, PostgreSQL, fila Celery e ligação ao índice de texto.

Para gerar os dados:

```bash
python -u build_site.py
```

Para testar localmente:

```bash
cd site
python -m http.server 8765
```

Depois abre `http://localhost:8765`.

As rotas públicas são geradas como pastas para funcionarem em GitHub Pages sem `.html` no fim:

```text
/inicio/
/calendário/
/temas/
/documentação/
/noticia/?id=noticia-...
```

Também existem aliases sem acentos (`/calendario/` e `/documentacao/`) para evitar problemas em browsers, partilhas ou ferramentas que normalizem URLs.

Os dias do calendário usam links únicos por query string para funcionar bem em GitHub Pages sem `.html`:

```text
/calendario/?data=2030-07-05
```

Ao abrir uma data, o site mostra no topo os posts desse dia no ano selecionado e no ano anterior. Por exemplo, `2030-07-05` procura posts de `2030-07-05` e `2029-07-05`, mesmo que o ano atual seja outro. Abaixo, completa a página com recomendações do Arquivo.pt para o mesmo mês/dia, até um total alvo de 25 notícias.

## Idiomas

O português é o idioma padrão. A interface tem versão em inglês e português. Os títulos das notícias preservam o título original recolhido/curado; se no futuro quiseres tradução automática dos títulos dinâmicos, é preciso ligar essa etapa ao mesmo modelo usado na curadoria ou rever manualmente os campos `title_en` e `summary_en`.

## Métricas da documentação

A página de documentação recebe as métricas através da API dinâmica ou, em fallback, de `site/data/news.json`. O `build_site.py` calcula automaticamente:

- registos jornalísticos cobertos, somando os candidatos filtrados registados em `arquivo_cdxj_state.json`;
- intervalo de anos coberto pelos índices processados;
- número de fontes distintas, juntando jornais, revistas e perfis e removendo marcas repetidas;
- posts marcados como `published`;
- seguidores somados em todas as redes declaradas em `social_metrics.json`.

As três métricas principais têm uma animação de contagem sempre que a documentação é aberta. Quando o utilizador prefere movimento reduzido, a contagem é mais curta. A faixa secundária mostra apenas anos cobertos e fontes; as datas vêm da cobertura CDXJ e mudam à medida que os índices são atualizados.

Estes valores não ficam fixos no HTML ou no JavaScript: são recalculados em cada execução de `build_site.py`. A contagem de publicações conserva os IDs já confirmados em `social_metrics.json`, pelo que continua a crescer mesmo que um post antigo deixe de estar na fila de revisão.

No workflow diário, o passo de construção usa as credenciais Meta já existentes para pedir `followers_count` ao Instagram Graph e conservar o último valor válido em `social_metrics.json`. Se a API estiver indisponível ou o build não tiver credenciais, o valor guardado não é substituído por zero. Para acrescentar outra rede social, adiciona uma entrada em `networks` com um campo numérico `followers`; o total do site soma todas as entradas.

## Páginas únicas de notícias

Posts e recomendações do calendário recebem um `page_id` derivado de uma assinatura SHA-256 da fonte. A mesma notícia preservada mantém o mesmo endereço e fontes diferentes não partilham acidentalmente a mesma página. Os cartões, o destaque principal e os resultados do calendário apontam primeiro para esta página interna.

A página mostra título, ano, descrição, imagem e ligação direta ao Arquivo.pt ou à publicação no Instagram. Quando uma recomendação CDXJ não tem imagem própria, é usada a miniatura oficial de página do Arquivo.pt, com o ícone do projeto como fallback.

## Evolução de temas

A rota `/temas/` aceita até quatro análises, cada uma com tema, fonte e cor. O botão `+` acrescenta uma série de cada vez, desaparece ao chegar a quatro e reaparece quando uma série é removida. O utilizador pode mostrar ou ocultar os valores sobre os pontos.

Quando o índice integral está pronto, o backend usa OpenSearch para devolver todos os anos de uma série numa agregação. Até lá, consulta exclusivamente a API TextSearch oficial do Arquivo.pt através da fila. Os nomes de host (`www.publico.pt`, por exemplo) são filtros do índice preservado; os sites atuais dos jornais não são consultados.

No fallback TextSearch, o valor `estimated_nr_results` é usado apenas como pista interna. Cada contagem apresentada é confirmada por paginação com `dedupValue=0`, verificando a presença do último `offset` e a ausência do seguinte. Se a janela máxima da API for atingida, o intervalo é dividido automaticamente em períodos menores. Uma consulta que falhe é mostrada como não verificada e nunca como zero. Os resultados completos ficam em PostgreSQL por 30 dias; o modo estático mantém ainda a cache do browser durante 24 horas.

Os valores contam registos arquivados que correspondem à pesquisa. Uma página preservada em vários momentos pode, por isso, contar várias vezes. Esta definição aparece também nos ficheiros descarregados.

Cada análise na API tem um orçamento máximo e um limitador de ritmo. O índice rápido é derivado exclusivamente de capturas do Arquivo.pt e só é ativado quando o intervalo está completo. Os CDXJ localizam páginas e definem cobertura, mas o texto integral é recuperado das versões preservadas.

O gráfico assinala publicações Instagram existentes sobre o tema; cada ponto abre a página única da notícia. Para reutilização académica ou científica, a interface exporta:

- PNG em alta resolução, com título, intervalo, legenda e crédito;
- SVG vetorial, com legenda, cores e metadados das quatro séries;
- CSV com análise, tema, fonte, cor, total da série, opção de valores, datas, contagem verificada, estado, método, URL da consulta e instante de recolha.

Os textos e cabeçalhos de exportação acompanham português/inglês.

## Fonte Arquivo.pt

O site mostra uma marca de água com crédito ao Arquivo.pt. Sempre que o post tem URL arquivado, o botão "Abrir no Arquivo.pt" aponta para essa fonte.

## Índices CDXJ

A pasta `arquivo_cdxj/` é opcional. Quando contém índices locais, o pregenerator usa esses ficheiros antes de chamar o `textsearch` online do Arquivo.pt.

Com os CDXJ filtrados perto de 20 GB, trata `arquivo_cdxj/` como **dados locais descartáveis/reconstruíveis**, não como parte do projeto versionado. Para continuar sem custos fixos, exceto o domínio final:

- mantém `arquivo_cdxj/`, dumps de índice, bases de cache grandes e snapshots comprimidos fora do Git;
- versiona apenas código, configuração, estados pequenos, manifestos de cobertura e JSON público gerado;
- usa GitHub Pages ou Cloudflare Pages para alojar o site estático/fallback gratuitamente;
- usa o Arquivo.pt como fonte remota canónica e o CDXJ local apenas como aceleração;
- evita OpenSearch/servidores persistentes pagos enquanto o projeto estiver em modo gratuito;
- só usa R2/S3 gratuito para partes pequenas ou temporárias, porque 20 GB persistentes podem exceder a franquia gratuita disponível;
- se precisares de portabilidade, divide o índice por ano/coleção, comprime os blocos e guarda um manifesto pequeno com `path`, `bytes`, `sha256`, `collection`, `start_date` e `end_date`.

Modelo de operação gratuito recomendado:

1. Atualizar CDXJ numa máquina local com espaço suficiente.
2. Gerar/reconstruir cobertura e site.
3. Confirmar que nenhum ficheiro pesado entrou no Git.
4. Fazer commit apenas de código, `.md`, estados pequenos e `site/`.
5. Publicar em Pages e apontar o domínio comprado para esse alojamento gratuito.


Exemplos de nomes aceites:

```text
arquivo_cdxj/20170705.cdxj
arquivo_cdxj/2017-07-05.cdxj
arquivo_cdxj/2017/20170705.cdxj
arquivo_cdxj/2017/2017-07-05.cdxj
arquivo_cdxj/2017/07-05.cdxj
arquivo_cdxj/2017/07/05.cdxj
arquivo_cdxj/07-05/2017.cdxj
arquivo_cdxj/2017.cdxj
```

Também são aceites `.gz`, `.jsonl` e `.ndjson`.

Se existir índice local para um ano/dia, o fluxo salta o `textsearch` desse ano e usa o índice para descobrir URLs candidatas. Se não existir índice, continua a usar o método antigo.

O worker usa estes índices para manter o OpenSearch atualizado. O calendário consulta a API por dia e fonte, por isso novas entradas ficam disponíveis depois da indexação incremental sem reconstruir um ficheiro estático de recomendações.

Para construir tudo a partir dos CDXJ remotos do Arquivo.pt:

```bash
recolher_cdxj_arquivo_pt.cmd 1996 2026
```

Este modo é muito pesado porque lê coleções CDXJ grandes diretamente do Arquivo.pt. O progresso fica em `arquivo_cdxj_state.json`, por isso podes parar e retomar.

Se já tiveres descarregado os CDXJ brutos para uma pasta local, usa este modo:

```bash
recolher_cdxj_de_pasta_local.cmd C:\caminho\para\cdxj_brutos 1996 2026
```

Para processar apenas algumas coleções remotas:

```bash
python -u build_arquivo_cdxj_index.py --collections EAWP5.cdxj FAWP60.cdxj --start-year 1996 --end-year 2026
```

O script guarda uma assinatura de cada fonte processada em `arquivo_cdxj_state.json`.
Quando um CDXJ local ou remoto muda, a coleção é reprocessada e as entradas antigas dessa mesma coleção são removidas antes de escrever as novas, evitando duplicados. Quando aparecem novos ficheiros CDXJ, eles são processados normalmente.

No workflow `Pregenerate PT Interval Review Queue`, a opção `update_cdxj` permite atualizar os índices antes de gerar os pending posts. Usa `cdxj_collections` para indicar coleções específicas, por exemplo:

```text
AWP30.cdxj AWP31.cdxj
```

`cdxj_all_remote` processa todas as coleções remotas do Arquivo.pt e deve ser usado raramente, porque pode demorar muitas horas e criar muitos dados.

Para atualizar o CDXJ filtrado no fim da recolha histórica local:

```bash
python run_historical_scrapers.py --start-year 1996 --end-year 2026 --lang pt --update-cdxj --cdxj-input-dir C:\caminho\para\cdxj_brutos
```

Se usares `--update-cdxj` sem `--cdxj-input-dir` nem `--cdxj-collections`, o script assume `--all-remote`.

## Posts

O ficheiro `pending_posts.json` é a fila central de revisão:

- `pending`: preparado, mas ainda não aprovado.
- `approved`: pode ser publicado pelo workflow.
- `published`: já foi publicado.
- `skip`: ignorado.

O site dá prioridade aos posts `published`. Se ainda não houver publicados, mostra a fila preparada para revisão para evitar uma página vazia.

## Instagram

O publisher passa a tentar guardar:

- `instagram_id`
- `instagram_url`
- `published_at`

Quando a API do Meta devolve o permalink, o site mostra o botão "Ver no Instagram" no post correspondente.

## Site dinâmico, GitHub Pages e Hugging Face

O backend dinâmico é a versão principal: FastAPI serve o frontend, PostgreSQL guarda o retrato público, Celery executa análises, Key Value mantém a fila e OpenSearch acelera o gráfico. `Sync Dynamic Website` envia alterações públicas para a API com um token.

Um segundo worker com disco persistente mantém os CDXJ fora do Git, sincroniza-os com armazenamento S3/R2 e atualiza o OpenSearch. Isto evita descarregar vários gigabytes em cada execução efémera do GitHub Actions.

O workflow `Deploy Website` continua a publicar `site/` no GitHub Pages como fallback. A configuração e os passos manuais estão em `DYNAMIC_DEPLOYMENT.md`.

Para a versão sem Render, o workflow `Deploy Website to Hugging Face` publica a mesma pasta `site/` num Hugging Face Static Space. Os passos e as limitações dessa versão estão em `HF_DEPLOYMENT.md`.
