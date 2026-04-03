@echo off
echo ================================================
echo   TMRP - Starting all services
echo ================================================
echo.

if not exist ".env" (
    echo [ERROR] .env file not found.
    echo         Copy .env.example to .env and edit the settings.
    pause
    exit /b 1
)

if not exist "data\tutoring.accdb" (
    echo [INFO] Database not found. Initializing...
    python -m app.database --init
    if errorlevel 1 (
        echo [ERROR] Database initialization failed.
        pause
        exit /b 1
    )
)

echo [1/3] Starting Huey worker...
start "huey-worker" cmd /k "python -m app.worker"

echo [2/3] Starting FastAPI server...
start "fastapi-server" cmd /k "uvicorn app.main:app --reload --port 8000"

timeout /t 3 /nobreak >nul

echo [3/3] Starting Vue dev server...
start /D "%~dp0..\tutor-platform-web" "vue-dev-server" cmd /k "npm run dev"

echo.
echo ================================================
echo   All services started
echo.
echo   API Server : http://localhost:8000
echo   Swagger UI : http://localhost:8000/docs
echo   Frontend   : http://localhost:5273
echo ================================================
pause
