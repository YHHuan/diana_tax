#!/usr/bin/env bash
# Mac / Linux 一鍵啟動
# 使用：chmod +x start.command && ./start.command (or 雙擊)

set -e
cd "$(dirname "$0")"

# 檢查 venv
if [ ! -d ".venv" ]; then
    echo "🔧 第一次啟動，建立虛擬環境..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo "🚀 啟動 Diana Tax..."
echo "瀏覽器應該會自動打開 http://localhost:8501"
streamlit run ui/app.py
