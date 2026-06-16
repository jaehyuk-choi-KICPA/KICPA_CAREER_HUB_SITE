@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [채용알림봇] 시작합니다. 이 창을 닫으면 봇이 멈춥니다.
python -m src.run --loop
pause
