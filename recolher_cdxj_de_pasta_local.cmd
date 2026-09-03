@echo off
setlocal

if "%~1"=="" (
  echo Uso:
  echo   recolher_cdxj_de_pasta_local.cmd C:\caminho\para\cdxj_brutos 1996 2026
  exit /b 1
)

set INPUT_DIR=%~1
set START_YEAR=1996
set END_YEAR=2026

if not "%~2"=="" set START_YEAR=%~2
if not "%~3"=="" set END_YEAR=%~3

echo A processar CDXJ brutos locais em:
echo %INPUT_DIR%
echo Anos: %START_YEAR%-%END_YEAR%
echo.

python -u build_arquivo_cdxj_index.py --input-dir "%INPUT_DIR%" --start-year %START_YEAR% --end-year %END_YEAR%

echo.
if errorlevel 1 (
  echo ERRO: a construcao do indice CDXJ falhou. Ve as linhas acima antes de fechar esta janela.
  pause
  exit /b 1
)
echo Terminado. Verifica a pasta arquivo_cdxj.
pause
