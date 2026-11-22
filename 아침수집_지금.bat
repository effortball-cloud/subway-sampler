@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo 평일 아침 지하철 수집(06:58~09:02, 4분 간격). 창을 닫으면 멈춥니다.
python pipeline\collect.py --morning %*
python pipeline\passages.py --finalize
python pipeline\export_villa.py
python pipeline\export_life.py
pause
