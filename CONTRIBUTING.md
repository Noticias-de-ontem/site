# Contribuir para o Notícias de Ontem

Obrigado pelo interesse em contribuir! Este projeto recupera notícias preservadas pelo [Arquivo.pt](https://arquivo.pt) e qualquer ajuda é bem-vinda — código, correções de texto, sugestões de fontes ou reportes de erros.

## Como contribuir

1. **Abre uma issue** antes de alterações grandes (nova funcionalidade, mudanças de estrutura), descrevendo o problema ou a ideia.
2. **Faz fork** do repositório e cria um ramo descritivo: `feat/Descricao`, `fix/Descricao` ou `docs/Descricao`.
3. **Mantém as alterações focadas** — um ramo, um objetivo.
4. **Testa localmente** antes de propôr:

   ```cmd
   python -m pytest tests/ -q
   python -u build_site.py
   python -m http.server 8765 --directory site
   ```

5. **Abre o pull request** para `main`, referenciando a issue (`Closes #123`) e descrevendo o que mudou e porquê.

## Regras do projeto

- **Segredos nunca no repositório**: chaves (NVIDIA, Gemini, ImgBB, Instagram, tokens) vão em `.env` local, `nvidia_api_key.local.txt` ou Secrets do GitHub.
- **Ficheiros pesados fora do Git**: índices CDXJ, bases de dados e imagens em massa ficam fora do repositório (ver README, secção CDXJ).
- **Proveniência sempre visível**: qualquer notícia mostrada tem de manter a ligação à página preservada no Arquivo.pt e o ano original.
- **Sem conteúdos de terceiros sem fonte**: fotografias e textos mantêm os direitos dos respetivos titulares; o projeto apenas liga e contextualiza.
- **Sem mortes/tragédias nos posts** (regra editorial atual do fluxo de Instagram).

## Estilo de código

- Python: segue o estilo existente (type hints onde já existirem, mensagens de log em português como o resto do projeto); sintaxe validada com `python -m compileall .` ou equivalente.
- JavaScript/CSS do site: vanilla, sem frameworks; manter o design system existente (Montserrat, ciano `#00c7d6`, cantos suaves).
- Comentários apenas onde a lógica não é óbvia, em português.

## Reportar erros

Usa as [issues](../../issues) com o template apropriado (erro do site, erro do pipeline, sugestão). Para falhas de segurança, lê [SECURITY.md](SECURITY.md) — não abras issue pública.
