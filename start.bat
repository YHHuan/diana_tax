@echo off
REM Windows 一鍵啟動 — 雙擊執行

cd /d "%~dp0"

if not exist ".venv" (
    echo 第一次啟動，建立虛擬環境...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo.
echo 啟動 Diana Tax...
echo 瀏覽器應該會自動打開 http://localhost:8501
echo.
streamlit run ui/app.py
pause
