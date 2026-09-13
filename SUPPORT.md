# Suporte

Precisas de ajuda com o **Notícias de Ontem**? Aqui ficam os caminhos:

## Dúvidas e problemas

1. **Consult primeiro a documentação**:
   - [README.md](README.md) — visão geral, fontes e scripts;
   - [SITE_AND_POSTS.md](SITE_AND_POSTS.md) — referência do site e dos posts;
   - página **Documentação** do próprio site (métricas, níveis de relevância, fontes).
2. **Procura em issues existentes** — [lista de issues](../../issues) — o problema pode já estar reportado.
3. **Abre uma issue nova** com o template adequado (*Bug report* ou *Feature request*) e o máximo de detalhe: o que fizeste, o que esperavas, o que aconteceu, e o ambiente (browser/sistema, ou comando executado).

## Problemas comuns

| Sintoma | Primeira coisa a verificar |
| --- | --- |
| Site local sem estilos/JS | Servir com `python -m http.server --directory site` e não abrir ficheiros diretos; hard-refresh |
| `build_site.py` lenta | `SITE_SKIP_CDXJ_REFRESH=1` durante desenvolvimento |
| Análises de fotos sem enquadramento Gemini | `GEMINI_API_KEY` definida? A cache `gemini_photo_cache.json` reduz chamadas; sem chave usa-se OpenCV |
| Geração NVIDIA falha (429/quota) | O pool roda modelos/chaves automaticamente; quota diária → esperar ou trocar de chave |
| Calendário sem notícias do dia | Gerar posts (`popular_site.py`) ou o índice de eventos (`--com-eventos`) |

## Segurança

Falhas de segurança não vão para issues públicas: lê [SECURITY.md](SECURITY.md).
