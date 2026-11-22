@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist data\logs mkdir data\logs
python pipeline\collect.py --morning >> data\logs\morning.log 2>&1
python pipeline\passages.py --finalize >> data\logs\morning.log 2>&1
python pipeline\export_villa.py >> data\logs\morning.log 2>&1
python pipeline\export_life.py >> data\logs\morning.log 2>&1
