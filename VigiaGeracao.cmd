@echo off
cd /d "%~dp0"
title Noticias de Ontem - Vigia da Geracao (5h)
if "%NVIDIA_API_KEY%"=="" if not exist nvidia_api_key.local.txt (
  echo ERRO: Cria nvidia_api_key.local.txt com a chave NVIDIA.
  pause
  exit /b 1
)
echo Vigia da geracao: mantem a geracao e o servidor vivos por 5 horas.
echo Fecha esta janela para parar tudo.
echo.
python -u scripts/vigia_geracao.py --horas 5
echo.
echo Vigia terminado.
pause
