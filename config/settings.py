"""Django settings — HSK5 Trainer

dev  : SQLite, DEBUG=1
prod : Postgres ผ่าน DATABASE_URL, DEBUG=0
"""
from pathlib import Path
import os
import sys

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


TESTING = "test" in sys.argv


def env_bool(key, default=False):
    return os.getenv(key, str(int(default))).strip().lower() in ("1", "true", "yes", "on")


# ค่าตั้งต้นต้องปลอดภัยเสมอ — ถ้าลืมตั้ง DJANGO_DEBUG บนเซิร์ฟเวอร์
# หรือพิมพ์ชื่อตัวแปรผิด ระบบต้องเลือกทางที่ปลอดภัยไว้ก่อน ไม่ใช่เปิดโหมดดีบัก
# เพราะหน้า error ของโหมดดีบักพ่นค่า env ทั้งหมดรวมถึงรหัสผ่านฐานข้อมูล
DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or TESTING:
        SECRET_KEY = "dev-only-key-never-used-in-production"
    else:
        raise ImproperlyConfigured(
            "ต้องตั้ง DJANGO_SECRET_KEY บนเซิร์ฟเวอร์ — "
            "สร้างด้วย python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # ต้องอยู่หลัง auth (ต้องรู้ว่าใครล็อกอิน) และหลัง messages (ต้องฝากข้อความบอกเหตุผล)
    "core.daily_session.DailyLogoutMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.version.context",
                "core.context.exam_countdown",
                "core.context.pending_work",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_db_url = os.getenv("DATABASE_URL", "").strip()
if _db_url:
    DATABASES = {"default": dj_database_url.parse(_db_url, conn_max_age=600)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "core.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "th"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Bangkok")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
# ตอนรันเทสต์ยังไม่ได้ collectstatic — ถ้าใช้ manifest storage เทสต์ที่ render
# เทมเพลตจะพังด้วย "Missing staticfiles manifest entry" ซึ่งไม่เกี่ยวกับสิ่งที่กำลังทดสอบ

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if TESTING
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"

# ── ค่าเฉพาะของโดเมนนี้ ──────────────────────────────────
# วันสอบเป้าหมาย ใช้โดยตัวจัดตารางทบทวน (ไม่มีประโยชน์ที่จะนัดทบทวนหลังวันสอบ)
TARGET_EXAM_DATE = os.getenv("TARGET_EXAM_DATE", "2026-12-13")

# Daily Drill Engine
DRILL_DEFAULT_SIZE = 40
DRILL_MIX = {"due": 0.50, "wrong": 0.30, "new": 0.20}
# เตะออกจากระบบเมื่อข้ามวัน เพื่อให้เห็นว่าผู้เรียนเข้ามาใหม่ทุกวันจริงไหม
# ปิดได้ด้วย DJANGO_DAILY_LOGOUT=0 — การบันทึกวันเข้าระบบยังทำงานอยู่ไม่ว่าจะเปิดหรือปิด
DAILY_LOGOUT = env_bool("DJANGO_DAILY_LOGOUT", True)

# เพดานข้อสอบจริงต่อชุดฝึกหนึ่งวัน — ที่เหลือเป็นคำศัพท์ทั้งหมด
#
# ชุดฝึกรายวันมีหน้าที่ *สร้างฐานคำศัพท์* ซึ่งเป็นคอขวดจริงของ HSK5
# ข้อสอบจริงยาวและกินเวลาต่อข้อมากกว่าการ์ดคำศัพท์หลายเท่า
# ถ้าปล่อยให้เข้ามาเยอะ ชุด 40 ข้อจะกลายเป็นการอ่านบทความ 40 นาที
# โดยได้คำศัพท์ใหม่แค่หยิบมือ
#
# การฝึกทำข้อสอบเต็มรูปแบบมีที่ทางของมันแล้วที่โหมดจำลองสอบ (สัปดาห์ละครั้ง)
DRILL_MAX_QUESTIONS = 10

# ของค้างเกินจำนวนนี้ → หยุดคำใหม่วันนั้นอัตโนมัติ
SRS_BACKLOG_CEILING = 130
# จำนวนวันก่อนสอบที่หยุดเรียนคำใหม่ทั้งหมด
SRS_FREEZE_DAYS = 14

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
