# ============================================================
#  AutoXabar / VIPADSUZ  —  ishlab chiqarish uchun konteyner
#
#  Yig'ish:   docker build -t autoxabar .
#  Yurgizish: docker run -p 5000:5000 --env-file .env -v ax-data:/data autoxabar
#  Yoki:      docker compose up -d
# ============================================================
FROM python:3.12-slim

# tzdata — loglardagi vaqt Toshkent bo'yicha ko'rinishi uchun.
# (Ilova mantiqi core/db.py dagi qat'iy UTC+5 ga tayanadi, lekin
#  log yozuvlari tizim vaqtini ishlatadi.)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Tashkent

# Root huquqisiz ishlaydi
RUN useradd --create-home --uid 10001 app

WORKDIR /app

# Kutubxonalar alohida qatlamda: kod o'zgarganda qayta o'rnatilmaydi
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .

# Doimiy ma'lumotlar konteyner ichida emas, volume'da turishi kerak:
#   /data                 — SQLite bazasi va Telegram sessiyalari
#   /app/static/uploads   — foydalanuvchi yuklagan rasmlar
# UPLOAD_DIR config.py da qat'iy belgilangan, shuning uchun yo'l aynan shunday.
ENV DATA_DIR=/data \
    SESSION_DIR=/data/sessions \
    HOST=0.0.0.0 \
    PORT=5000

RUN mkdir -p /data/sessions /app/static/uploads \
 && chown -R app:app /data /app/static/uploads

USER app

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD python -c "import os,sys,urllib.request; \
url='http://127.0.0.1:'+os.environ.get('PORT','5000')+'/'; \
sys.exit(0 if urllib.request.urlopen(url, timeout=4).status == 200 else 1)"

# DIQQAT: --workers 1 — fon vazifalari (yuborish sikli, obuna muddatini
# tekshirish) bir nechta jarayonda takrorlanmasligi uchun MAJBURIY.
# Parallellik --threads orqali beriladi. Konteynerni ham ko'paytirmang.
CMD ["sh", "-c", "exec gunicorn --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:${PORT:-5000} app:app"]
