@echo off
cd /d "%~dp0"
title Noticias de Ontem - Jul-Dez (NVIDIA)

if "%NVIDIA_API_KEY%"=="" if not exist nvidia_api_key.local.txt (
  echo ERRO: NVIDIA_API_KEY nao esta definida e nvidia_api_key.local.txt nao existe.
  echo.
  echo Corre edit_nvidia_key.cmd ou cria nvidia_api_key.local.txt com a chave da NVIDIA.
  pause
  exit /b 1
)

:loop
echo.
echo ========================================================
echo   Processamento Paralelo - Julho a Dezembro (NVIDIA)
echo ========================================================
echo.
python run_historical_scrapers.py --lang pt --start-year 1990 --end-year 2026 --limit 0 --months 7,8,9,10,11,12 --use-nvidia --nvidia-model meta/llama-3.1-8b-instruct

set EXIT_CODE=%ERRORLEVEL%
if %EXIT_CODE% equ 2 (
  echo.
  echo [NVIDIA] Limite diario de quota atingido.
  echo A aguardar 24 horas antes de retomar...
  timeout /t 86400 /nobreak
  goto loop
) else if %EXIT_CODE% equ 0 (
  echo.
  echo [SUCESSO] Processamento de Julho a Dezembro concluido!
  echo Este separador ira terminar.
  pause
  exit /b 0
) else (
  echo.
  echo [ERRO] O script terminou com erro ou foi interrompido com codigo %EXIT_CODE%.
  echo A tentar retomar em 30 segundos...
  timeout /t 30 /nobreak
  goto loop
)