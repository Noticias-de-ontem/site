@echo off
setlocal

set START_YEAR=1996
set END_YEAR=2026

if not "%~1"=="" set START_YEAR=%~1
if not "%~2"=="" set END_YEAR=%~2

echo A construir indice CDXJ filtrado do Arquivo.pt entre %START_YEAR% e %END_YEAR%.
echo Isto pode demorar muitas horas ou dias porque os CDXJ remotos sao muito grandes.
echo O progresso fica guardado em arquivo_cdxj_state.json.
echo.

python -u build_arquivo_cdxj_index.py --start-year %START_YEAR% --end-year %END_YEAR% --all-remote

echo.
if errorlevel 1 (
  echo ERRO: a construcao do indice CDXJ falhou. Ve as linhas acima antes de fechar esta janela.
  pause
  exit /b 1
)
echo Terminado. Verifica a pasta arquivo_cdxj.
pause
