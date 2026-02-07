FROM python:3.11-slim

# Nastavi delovni direktorij
WORKDIR /app

# Namesti curl za healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Kopiraj requirements in namesti odvisnosti
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiraj kodo
COPY . .

# Nastavi izvrsljive pravice na start.sh
RUN chmod +x /app/start.sh

# Ustvari direktorij za bazo podatkov (za persistent volume)
RUN mkdir -p /data

# Izpostavi port za Streamlit admin panel
EXPOSE 8501

# Nastavi spremenljivke okolja
ENV DATABASE_PATH=/data/studij.db
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_PORT=8501

# Zdravstveni pregled za admin panel
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Zaženi oba servisa
ENTRYPOINT ["/bin/sh", "/app/start.sh"]
