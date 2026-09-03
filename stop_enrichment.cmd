@echo off
setlocal
cd /d "%~dp0"

type nul > enrich_saved_posts.stop
echo Pedido de paragem criado. O script vai guardar e parar no proximo checkpoint.