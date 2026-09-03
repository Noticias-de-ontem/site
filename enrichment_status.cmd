@echo off
setlocal
cd /d "%~dp0"

python enrichment_status.py %*
pause