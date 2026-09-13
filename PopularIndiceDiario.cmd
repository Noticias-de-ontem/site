@echo off
cd /d "%~dp0"
title Noticias de Ontem - Indice Diario de Relevancia
if "%NVIDIA_API_KEY%"=="" if not exist nvidia_api_key.local.txt (
  echo ERRO: Cria nvidia_api_key.local.txt com a chave NVIDIA.
  pause
  exit /b 1
)
echo A construir o indice diario de relevancia (1996-hoje, retomavel).
echo Fecha esta janela para interromper — volta a correr para retomar.
echo.
python -u scripts/popular_indice_diario.py
echo.
echo Indice concluido ou interrompido. Corre de novo para retomar.
pause
