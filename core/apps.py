from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "HSK5 Trainer"

    def ready(self):
        # ต่อ signal ที่บันทึกวันเข้าระบบ — ต้อง import ตรงนี้เท่านั้น
        # ถ้า import ที่หัวไฟล์จะโหลดโมเดลก่อนที่ Django จะพร้อม
        from . import daily_session  # noqa: F401
