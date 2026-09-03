@echo off
setlocal
cd /d "%~dp0"

if "%NVIDIA_API_KEY%"=="" if not exist nvidia_api_key.local.txt (
  echo ERRO: NVIDIA_API_KEY nao esta definida e nvidia_api_key.local.txt nao existe.
  echo.
  echo Corre edit_nvidia_key.cmd ou cria nvidia_api_key.local.txt com a chave da NVIDIA.
  exit /b 1
)

if "%~1"=="" (
  echo Modo normal: a reanalisar todas as candidatas PT e EN com NVIDIA.
  echo.
  python reanalyze_basic_news.py --lang both
  echo.
  echo Para filtrar, usa por exemplo:
  echo   reanalisar_sem_ia_nvidia.cmd --lang pt --limit 50
  echo   reanalisar_sem_ia_nvidia.cmd --lang en --limit 50
  echo   reanalisar_sem_ia_nvidia.cmd --lang both --months 1,2 --limit 100
  echo   reanalisar_sem_ia_nvidia.cmd --lang pt --months 1,2 --limit 100
  echo   reanalisar_sem_ia_nvidia.cmd --lang pt --dry-run --limit 50
  pause
  exit /b %ERRORLEVEL%
)

python reanalyze_basic_news.py %*
pause