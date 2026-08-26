# HSK5 Trainer — ใช้ได้ทั้ง Railway, Render, Fly.io และ VPS ธรรมดา
# ไม่ผูกกับแพลตฟอร์มไหน ย้ายที่ได้โดยไม่ต้องแก้อะไร
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# ติดตั้ง dependency ก่อนคัดลอกโค้ด — ชั้นนี้จะถูก cache ไว้ ทำให้ deploy ครั้งต่อไปเร็วขึ้นมาก
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# รวมไฟล์ static ตอน build ไม่ใช่ตอนรัน — ค่าพวกนี้เป็นค่าหลอกเฉพาะขั้นตอน build
RUN DJANGO_SECRET_KEY=build-only-not-used \
    DJANGO_DEBUG=0 \
    DJANGO_ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

EXPOSE 8000

# migrate ทุกครั้งที่ deploy แล้วค่อยเปิดเว็บ — ปลอดภัยเพราะ migration ของ Django รันซ้ำได้
CMD python manage.py migrate --noinput && \
    gunicorn config.wsgi:application \
      --bind 0.0.0.0:${PORT:-8000} \
      --workers 2 \
      --timeout 60 \
      --access-logfile - \
      --error-logfile -
