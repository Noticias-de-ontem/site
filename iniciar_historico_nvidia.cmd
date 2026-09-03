@echo off
title Lancador de Scraping NVIDIA em Separadores (Windows Terminal)
cd /d "%~dp0"

if "%NVIDIA_API_KEY%"=="" if not exist nvidia_api_key.local.txt (
  echo ERRO: NVIDIA_API_KEY nao esta definida e nvidia_api_key.local.txt nao existe.
  echo.
  echo Corre edit_nvidia_key.cmd ou cria nvidia_api_key.local.txt com a chave da NVIDIA.
  pause
  exit /b 1
)

echo A abrir os 6 scripts de scraping NVIDIA em separadores do Windows Terminal...
echo.

wt -d "%CD%" cmd /k "historico_jan_fev_nvidia.cmd" ; new-tab -d "%CD%" cmd /k "historico_mar_abr_nvidia.cmd" ; new-tab -d "%CD%" cmd /k "historico_mai_jun_nvidia.cmd" ; new-tab -d "%CD%" cmd /k "historico_jul_ago_nvidia.cmd" ; new-tab -d "%CD%" cmd /k "historico_set_out_nvidia.cmd" ; new-tab -d "%CD%" cmd /k "historico_nov_dez_nvidia.cmd"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [AVISO] Nao foi possivel abrir o Windows Terminal wt.
    echo A abrir em 6 janelas CMD independentes em alternativa...
    echo.
    start "Jan-Fev NVIDIA" cmd /k "historico_jan_fev_nvidia.cmd"
    start "Mar-Abr NVIDIA" cmd /k "historico_mar_abr_nvidia.cmd"
    start "Mai-Jun NVIDIA" cmd /k "historico_mai_jun_nvidia.cmd"
    start "Jul-Ago NVIDIA" cmd /k "historico_jul_ago_nvidia.cmd"
    start "Set-Out NVIDIA" cmd /k "historico_set_out_nvidia.cmd"
    start "Nov-Dez NVIDIA" cmd /k "historico_nov_dez_nvidia.cmd"
)