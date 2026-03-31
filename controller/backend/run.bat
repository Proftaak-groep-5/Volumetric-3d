@echo off
echo Starting Multi-Camera 3D Recording Backend...
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Run the application
echo.
echo Starting FastAPI server on http://localhost:8000
echo.
python main.py

pause

