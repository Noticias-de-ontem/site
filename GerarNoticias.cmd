@echo off
chcp 65001 >nul 2>&1
title Noticias de Ontem - Gerador
echo.
echo  ============================================
echo   NOTICIAS DE ONTEM - Gerador de Conteudo
echo  ============================================
echo.
echo  [1] Iniciar/Retomar Vigia de Geracao (5h)
echo  [2] Gerar Noticias do Ano Completo
echo  [3] Reconstruir Site
echo  [4] Iniciar Servidor Local
echo  [0] Sair
echo.
set /p opcao="  Escolha uma opcao: "
if "%opcao%"=="1" (
    echo.
    echo  A iniciar vigia de geracao...
    python scripts/vigia_geracao.py --horas 5
) else if "%opcao%"=="2" (
    echo.
    echo  A gerar noticias do ano completo...
    python popular_site.py --tudo-ano --source-mode arquivo-first
) else if "%opcao%"=="3" (
    echo.
    echo  A reconstruir o site...
    python build_site.py
) else if "%opcao%"=="4" (
    echo.
    echo  A iniciar servidor local...
    if exist HospedarSite.cmd (
        call HospedarSite.cmd
    ) else (
        python -m http.server 8000 --directory site
    )
) else if "%opcao%"=="0" (
    exit /b
) else (
    echo  Opcao invalida.
)
pause
