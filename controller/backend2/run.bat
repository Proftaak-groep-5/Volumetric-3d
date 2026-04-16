@echo off
echo Starting Multi-Camera 3D Recording Backend v2...
echo.

if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Starting FastAPI server on http://localhost:8000
echo.
python main.py

pause
