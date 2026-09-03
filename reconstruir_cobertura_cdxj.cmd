@echo off
setlocal
cd /d "%~dp0"

echo A reconstruir as datas de cobertura por fonte a partir dos CDXJ filtrados.
echo Executa este comando apenas depois de terminar recolher_cdxj_arquivo_pt.cmd.
echo.
python -u build_arquivo_cdxj_index.py --rebuild-coverage
if errorlevel 1 (
  echo.
  echo A reconstrucao terminou com erro.
  pause
  exit /b 1
)

echo.
echo Cobertura concluida. A gerar novamente os dados do site...
python -u build_site.py
if errorlevel 1 (
  echo.
  echo A cobertura foi guardada, mas a geracao do site terminou com erro.
  pause
  exit /b 1
)

echo.
echo Concluido. As datas maxima e minima do grafico foram atualizadas.
pause
