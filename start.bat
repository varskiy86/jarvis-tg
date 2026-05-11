@echo off
echo [J.A.R.V.I.S. Initialization]
echo.

if not exist .env (
    echo ERROR: .env file not found!
    echo Please copy .env.example to .env and fill in your tokens.
    echo.
    pause
    exit /b 1
)

echo Loading dependencies...
pip install -q -r requirements.txt

if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo Starting J.A.R.V.I.S. bot...
echo.
python main.py

pause
