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

# curl ใช้ดึงไฟล์เสียงข้อฟังตอน build (ดูด้านล่าง) — image ฐานไม่มีมาให้
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# ── ไฟล์เสียงข้อฟัง ─────────────────────────────────────────────
#
# **ตอนนี้ไฟล์เสียงอยู่ใน git** จึงติดมากับ COPY ข้างบนแล้ว ไม่ต้องดึงอะไร
#
# เคยย้ายออกไปไว้ใน GitHub Release เพื่อไม่ให้ประวัติ git บวม
# แต่ย้ายออกก่อนที่จะตั้งที่เก็บใหม่เสร็จ → prod ไม่มีไฟล์เสียงเลยหนึ่งรอบ deploy
# ผู้เรียนได้ยินตัวอ่านของเบราว์เซอร์แทน ซึ่งแย่กว่าเดิม จึงเอากลับเข้า git ก่อน
#
# กลไกข้างล่างยังอยู่ เผื่อวันที่ย้ายออกจริง (เช่นตอนเพิ่มเสียงข้อสอบจริง ~350 MB
# ซึ่งใส่ใน git ไม่ไหวแน่นอน) — ไม่ตั้ง LISTENING_AUDIO_URL ก็ไม่ทำอะไร
# ถ้าตั้ง ไฟล์จาก Release จะเขียนทับของที่มากับ git
#
# **ดาวน์โหลดไม่สำเร็จต้องไม่ทำให้ build พัง** — ถ้าไม่มีไฟล์เสียง
# ระบบถอยไปใช้ตัวอ่านของเบราว์เซอร์เองอยู่แล้ว (static/js/listen.js)
# ยอมให้เสียงแย่ลงชั่วคราว ดีกว่าเว็บล่มทั้งเว็บเพราะโหลดไฟล์เสียงไม่ได้
ARG LISTENING_AUDIO_URL=""
RUN if [ -n "$LISTENING_AUDIO_URL" ]; then       echo "กำลังดึงไฟล์เสียงข้อฟัง…" &&       (curl -fsSL --retry 3 --max-time 300 "$LISTENING_AUDIO_URL" | tar xz -C static/         && echo "ได้ไฟล์เสียง $(ls static/listening/*.m4a 2>/dev/null | wc -l) ไฟล์"         || echo "⚠️ ดึงไฟล์เสียงไม่สำเร็จ — ระบบจะใช้ตัวอ่านของเบราว์เซอร์แทน") ;     else       echo "ไม่ได้ตั้ง LISTENING_AUDIO_URL — ระบบจะใช้ตัวอ่านของเบราว์เซอร์" ;     fi

# รวมไฟล์ static ตอน build ไม่ใช่ตอนรัน — ค่าพวกนี้เป็นค่าหลอกเฉพาะขั้นตอน build
RUN DJANGO_SECRET_KEY=build-only-not-used \
    DJANGO_DEBUG=0 \
    DJANGO_ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

EXPOSE 8000

# migrate ทุกครั้งที่ deploy แล้วค่อยเปิดเว็บ — ปลอดภัยเพราะ migration ของ Django รันซ้ำได้
# timeout 180 เพราะการตรวจเรียงความเรียก API ภายนอกซึ่งใช้เวลา 40-90 วินาที
# ถ้าเกิน gunicorn จะฆ่า worker ทิ้ง ผู้เรียนเห็น 502 และคำขอหายเฉยๆ
#
# gthread + threads 4 เพราะ workers 2 ตัวจะถูกบล็อกทั้งคู่ระหว่างรอ API
# ถ้าน้องสองคนกดตรวจพร้อมกัน เว็บจะค้างทั้งเว็บสำหรับทุกคน
CMD python manage.py migrate --noinput && \
    gunicorn config.wsgi:application \
      --bind 0.0.0.0:${PORT:-8000} \
      --workers 2 \
      --worker-class gthread \
      --threads 4 \
      --timeout 180 \
      --access-logfile - \
      --error-logfile -
