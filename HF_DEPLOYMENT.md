# Publicação no Hugging Face

O site pode funcionar sem Render, PostgreSQL, Redis, OpenSearch ou disco
persistente usando dois repositórios no Hugging Face:

- um **Static Space público**, que serve a pasta `site/`;
- um **Dataset ou Storage Bucket privado**, que guarda os CDXJ pesados como
  cópia de construção/restauro.

O Static Space não executa Python nem descarrega os CDXJ. A página pública usa
o `site/data/news.json` e os assets já gerados.

## Criar o Space

No Hugging Face, cria um Space com:

- visibilidade **Public**;
- SDK **Static**;
- nome, por exemplo `noticias-de-ontem`.

O ficheiro `site/README.md` já contém a configuração `sdk: static` e
`app_file: index.html` necessária ao Space.

## Publicação automática

Cria um token Hugging Face com permissão de escrita no Space e adiciona estes
GitHub Actions secrets no repositório:

```text
HF_TOKEN=token de escrita do Hugging Face
HF_SPACE_ID=utilizador/noticias-de-ontem
HF_SITE_PUBLIC_URL=https://utilizador-noticias-de-ontem.hf.space  # opcional
```

O workflow `.github/workflows/huggingface_space.yml` irá:

1. gerar o site com `SITE_STATIC_ONLY=1`;
2. publicar apenas `site/` no Space;
3. remover ficheiros antigos do Space que já não existam localmente.

Também é possível publicar manualmente:

```powershell
python -m pip install -U huggingface_hub
hf auth login
$env:HF_SPACE_ID = "utilizador/noticias-de-ontem"
$env:HF_SITE_PUBLIC_URL = "https://utilizador-noticias-de-ontem.hf.space"
$env:SITE_STATIC_ONLY = "1"
python -u build_site.py
python -u deploy_hf_space.py
```

## O que fica disponível

- página inicial, navegação PT/EN, assets e páginas de notícias geradas;
- calendário com os posts que já estão no retrato estático;
- pesquisa de temas através da TextSearch API pública do Arquivo.pt;
- sitemap, robots.txt e metadados SEO;
- publicação pública sem Render.

## O que não fica disponível sem backend

- recomendações novas do calendário calculadas a partir de todos os CDXJ;
- páginas de capturas que não tenham sido incluídas no `news.json`;
- OpenSearch e o modo rápido de pesquisa;
- jobs Celery, fila Redis/Valkey, PostgreSQL e endpoints FastAPI;
- atualização automática de notícias, Instagram ou CDXJ pelo próprio Space.

Essas tarefas continuam a ser executadas localmente ou por GitHub Actions. O
Hugging Face Static Space apenas publica o resultado. A pesquisa direta do
Arquivo.pt depende da disponibilidade, CORS e limites da API pública.

## CDXJ

Os CDXJ podem permanecer no Dataset/Storage Bucket privado já criado. Não os
copies para o Space público: não são necessários para servir a página e
revelariam um volume pesado ao visitante. O site só precisa dos ficheiros já
gerados dentro de `site/`.

Depois de confirmares que o Space está a servir corretamente, podes desativar
o deploy do GitHub Pages e os serviços Render. Mantém o `DYNAMIC_DEPLOYMENT.md`
como documentação histórica do backend que deixou de ser usado nesta versão.
