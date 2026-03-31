@echo off
echo Starting Multi-Camera 3D Recording Frontend...
echo.

REM Check if node_modules exists
if not exist "node_modules\" (
    echo Installing dependencies...
    call npm install
)

REM Start the development server
echo.
echo Starting React development server on http://localhost:3000
echo.
call npm start

pause

