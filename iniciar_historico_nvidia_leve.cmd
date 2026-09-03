@echo off
title Lancador de Scraping NVIDIA Leve (2 Processos)
cd /d "%~dp0"

if "%NVIDIA_API_KEY%"=="" if not exist nvidia_api_key.local.txt (
  echo ERRO: NVIDIA_API_KEY nao esta definida e nvidia_api_key.local.txt nao existe.
  echo.
  echo Corre edit_nvidia_key.cmd ou cria nvidia_api_key.local.txt com a chave da NVIDIA.
  pause
  exit /b 1
)

echo A abrir os 2 scripts de scraping NVIDIA (Semestre 1 e 2)...
echo.

wt -d "%CD%" cmd /k "historico_sem1_nvidia.cmd" ; new-tab -d "%CD%" cmd /k "historico_sem2_nvidia.cmd"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [AVISO] Nao foi possivel abrir o Windows Terminal wt.
    echo A abrir em 2 janelas CMD independentes em alternativa...
    echo.
    start "Jan-Jun NVIDIA (Semestre 1)" cmd /k "historico_sem1_nvidia.cmd"
    start "Jul-Dez NVIDIA (Semestre 2)" cmd /k "historico_sem2_nvidia.cmd"
)