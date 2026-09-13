@echo off
cd /d "%~dp0"
title Noticias de Ontem - Gerador de Noticias
if "%NVIDIA_API_KEY%"=="" if not exist nvidia_api_key.local.txt (
  echo ERRO: Cria nvidia_api_key.local.txt com a chave NVIDIA ou define NVIDIA_API_KEY.
  pause
  exit /b 1
)
echo A gerar noticias (arquivo-first, retomavel).
echo Fecha esta janela para interromper — volta a correr para retomar.
echo.
python -u popular_site.py --tudo-ano --source-mode arquivo-first --limite 50
echo.
echo Geracao concluida ou interrompida. Corre de novo para retomar.
pause
