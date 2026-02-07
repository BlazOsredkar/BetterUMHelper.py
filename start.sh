#!/bin/sh

echo "========================================"
echo "  UMHelper - Zagon"
echo "========================================"

# Ustvari simbolicno povezavo do baze, da oba procesa uporabljata isto
if [ -n "$DATABASE_PATH" ]; then
    # Ce baza se ne obstaja, jo ustvari
    touch "$DATABASE_PATH"
    # Simbolicna povezava v /app, da koda deluje brez sprememb
    ln -sf "$DATABASE_PATH" /app/studij.db
    echo "[OK] Baza podatkov: $DATABASE_PATH"
fi

echo "[..] Zaganjam Admin Panel (Streamlit) na portu 8501..."
streamlit run admin_panel.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false &
STREAMLIT_PID=$!

echo "[..] Zaganjam Discord Bot..."
while true; do
    python main.py
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[!!] Discord Bot se je normalno ustavil."
        break
    fi
    echo "[!!] Discord Bot padel (koda: $EXIT_CODE). Ponoven zagon cez 10s..."
    sleep 10
done &
BOT_PID=$!

echo "[OK] Oba procesa tečeta (Streamlit PID=$STREAMLIT_PID, Bot PID=$BOT_PID)"

# Cakaj na oba procesa - ce eden pade, ustavi drugega
while kill -0 $STREAMLIT_PID 2>/dev/null && kill -0 $BOT_PID 2>/dev/null; do
    sleep 5
done

echo "[!!] Eden izmed procesov se je ustavil. Koncujem..."
kill $STREAMLIT_PID 2>/dev/null || true
kill $BOT_PID 2>/dev/null || true
exit 1
