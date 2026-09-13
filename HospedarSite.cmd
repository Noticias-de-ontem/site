@echo off
cd /d "%~dp0"
title Noticias de Ontem - Servidor Local (http://127.0.0.1:8080)
echo A servir o site em http://127.0.0.1:8080
echo Fecha esta janela para parar o servidor.
echo.
start "" "http://127.0.0.1:8080/inicio/"
python -m http.server 8080 --directory site
