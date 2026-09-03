@echo off
setlocal
cd /d "%~dp0"

if exist enrich_saved_posts.stop del /f enrich_saved_posts.stop

if "%NVIDIA_API_KEY%"=="" if not exist nvidia_api_key.local.txt (
  echo ERRO: NVIDIA_API_KEY nao esta definida.
  echo.
  echo Define primeiro:
  echo   set NVIDIA_API_KEY=A_TUA_CHAVE
  echo.
  echo Ou coloca a chave no ficheiro:
  echo   nvidia_api_key.local.txt
  exit /b 1
)

python enrich_ai_parallel.py --lang pt %*
pause