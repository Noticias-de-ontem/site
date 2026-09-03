@echo off
title Lancador de Scraping em Separadores (Windows Terminal)
cd /d "%~dp0"

echo A abrir os 6 scripts de scraping em separadores do Windows Terminal...
echo Caminho atual: %CD%
echo.

wt -d "%CD%" cmd /k "historico_jan_fev.cmd" ; new-tab -d "%CD%" cmd /k "historico_mar_abr.cmd" ; new-tab -d "%CD%" cmd /k "historico_mai_jun.cmd" ; new-tab -d "%CD%" cmd /k "historico_jul_ago.cmd" ; new-tab -d "%CD%" cmd /k "historico_set_out.cmd" ; new-tab -d "%CD%" cmd /k "historico_nov_dez.cmd"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERRO] Nao foi possivel abrir o Windows Terminal wt.
    echo Certifique-se de que tem o Windows Terminal instalado.
    echo.
    pause
)