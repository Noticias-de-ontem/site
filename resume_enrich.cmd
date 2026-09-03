@echo off
setlocal
cd /d "%~dp0"

if "%NVIDIA_API_KEY%"=="" if not exist nvidia_api_key.local.txt (
  echo ERRO: NVIDIA_API_KEY nao esta definida.
  echo.
  echo No CMD, define primeiro:
  echo set NVIDIA_API_KEY=A_TUA_CHAVE
  echo.
  echo Ou coloca a chave no ficheiro local:
  echo nvidia_api_key.local.txt
  exit /b 1
)

if exist enrich_saved_posts.stop del /f enrich_saved_posts.stop

python enrich_saved_posts.py --lang pt %*
pause