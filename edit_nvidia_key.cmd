@echo off
setlocal
cd /d "%~dp0"

if not exist nvidia_api_key.local.txt type nul > nvidia_api_key.local.txt
notepad nvidia_api_key.local.txt