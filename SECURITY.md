# Política de Segurança

## Versões suportadas

O projeto é servido a partir de `main` (GitHub Pages e, na arquitetura dinâmica, o deploy do Render). Reporta sempre contra a versão mais recente de `main`.

| Versão | Suportada |
| --- | --- |
| `main` | ✅ |
| outras ramificações/tags | ❌ |

## Como reportar uma vulnerabilidade

**Não abras issue pública para falhas de segurança.**

1. Usa o relatório privado de segurança do GitHub: **Security → Report a vulnerability** (Private Vulnerability Reporting) neste repositório; ou
2. Se não estiver disponível, contacta os mantenedores através do perfil da organização [Noticias-de-ontem](https://github.com/Noticias-de-ontem).

Inclui: descrição, passos para reproduzir, impacto avaliado e, se possível, sugestão de correção. Responderemos normalmente em até 7 dias e manteremos a comunicação até à correção.

## Âmbito e notas do projeto

- **Chaves de API** (NVIDIA, Gemini, ImgBB, Instagram, tokens de sincronização) são o ativo mais sensível: nunca devem aparecer no repositório, em issues, PRs ou logs colados. Se uma chave for exposta, revoga-a imediatamente no respetivo fornecedor.
- **`.env` e `nvidia_api_key.local.txt`** nunca devem ser commitados (já constam do `.gitignore`; confirma antes de fazer push).
- O site é estático por omissão: a superfície pública reduz-se a HTML/JS gerado e `data/news.json`. O backend dinâmico (FastAPI/PostgreSQL/Celery/OpenSearch) tem autenticação por token nas rotas de sincronização e rate limiting nos endpoints públicos.
- Conteúdos de terceiros: o projeto liga a páginas preservadas pelo Arquivo.pt e não rehospeda artigos; fotografias usadas seguem a pesquisa de imagens do projeto com filtro de proveniência.

## Boas práticas para contribuidores

- Corre novas dependências com mínimo privilégio e versões fixadas (`requirements.txt`);
- Não introduzas `eval`/`exec` sobre input externo; valida parâmetros de API contra listas conhecidas (o backend valida `source` contra `topic_search.sources`);
- Limites de pedidos (`backend/rate_limit.py`) não devem ser desativados.
