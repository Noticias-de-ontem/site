@echo off
setlocal
cd /d "%~dp0"

if "%NVIDIA_API_KEY%"=="" if not exist nvidia_api_key.local.txt (
  echo ERRO: NVIDIA_API_KEY nao esta definida e nvidia_api_key.local.txt nao existe.
  echo.
  echo Corre edit_nvidia_key.cmd ou cria nvidia_api_key.local.txt com a chave da NVIDIA.
  exit /b 1
)

python reanalyze_basic_news.py --lang pt %*
pause