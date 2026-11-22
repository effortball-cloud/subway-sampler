@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 평일 06:50마다 이 PC에서 지하철 아침 수집을 돌리도록 Windows 작업 스케줄러에 등록합니다.
echo 그 시간에 PC가 켜져 있어야 합니다(절전이면 수집 안 됨). GitHub 자동 수집을 켜면 이건 지우세요.
pause
schtasks /create /tn "subway-sampler-morning" /tr "\"%~dp0아침수집_자동.bat\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 06:50 /f
echo.
echo 지우려면: schtasks /delete /tn "subway-sampler-morning" /f
pause
