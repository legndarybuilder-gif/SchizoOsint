@echo off
echo Checking Python...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed!
    pause
    exit
)

echo Installing dependencies...
pip install -r requirements.txt

echo Starting app...
python main.py

pause
