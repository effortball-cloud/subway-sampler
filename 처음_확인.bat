@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo 실시간 지하철 키로 노선마다 1번씩 불러 봅니다(18회 안팎, 하루 1,000회 중).
python pipeline\collect.py --probe
python pipeline\collect.py --plan
pause
