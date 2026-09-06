"""Runner local: carrega o .env e gera um intervalo de posts (fase de testes)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, val = line.split("=", 1)
    key = key.strip()
    val = val.strip().strip("'\"")
    if key not in os.environ and val and not val.startswith("utilizador"):
        os.environ[key] = val

sys.argv = [
    "pregenerator.py",
    "--lang", "pt",
    "--start-date", sys.argv[1] if len(sys.argv) > 1 else "2026-08-25",
    "--end-date", sys.argv[2] if len(sys.argv) > 2 else "2026-09-01",
    "--source-mode", "arquivo-first",
]

# Run de testes: menos termos e anos com índice pesquisável (2022+ ainda
# devolve zero resultados na TextSearch do Arquivo.pt).
os.environ.setdefault(
    "ARQUIVO_SEARCH_TERMS",
    "Portugal,politica,economia,futebol,desporto,mundo,cultura",
)
os.environ.setdefault("ARQUIVO_SEARCH_YEAR_START", "2016")
os.environ.setdefault("ARQUIVO_SEARCH_YEAR_END", "2022")
# Pool mais pequeno na filtragem por IA: evita timeouts com 300 cabeçalhos.
os.environ.setdefault("ARQUIVO_AI_MAX_CANDIDATES", "150")

os.chdir(ROOT)
exec(compile((ROOT / "pregenerator.py").read_text(encoding="utf-8"), "pregenerator.py", "exec"))
