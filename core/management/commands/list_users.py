"""ดูว่ามีบัญชีอะไรอยู่ในระบบบ้าง — ใช้ตอนเข้าระบบไม่ได้แล้วไม่แน่ใจว่าพิมพ์ชื่อถูกไหม

    python manage.py list_users

แสดงเฉพาะ *ชื่อ* ที่มีอยู่จริงและสถานะบัญชี ไม่แสดงรหัสผ่าน
เพราะ Django เก็บรหัสผ่านเป็นค่าที่ถอดกลับไม่ได้ (hash) — ไม่มีใครอ่านของเดิมได้
ถ้าลืมรหัส ต้องตั้งใหม่ ไม่ใช่ไปเปิดดู
"""
from django.core.management.base import BaseCommand

from core.models import LearnerProfile, User


class Command(BaseCommand):
    help = "แสดงรายชื่อบัญชีทั้งหมด พร้อมสถานะและวิธีตั้งรหัสใหม่"

    def handle(self, *args, **opts):
        users = User.objects.order_by("username")
        if not users:
            self.stdout.write(self.style.WARNING("ยังไม่มีบัญชีในระบบเลย"))
            return

        learner_usernames = set(
            LearnerProfile.objects.values_list("user__username", flat=True)
        )

        self.stdout.write(f"{'ชื่อผู้ใช้':<20} {'สถานะ':<10} {'สิทธิ์':<12} เข้าระบบล่าสุด")
        self.stdout.write("─" * 68)
        for u in users:
            role = "ผู้ดูแลสูงสุด" if u.is_superuser else (u.role or "-")
            if u.username in learner_usernames:
                role = f"{role} · ผู้เรียน"
            active = "ใช้งานได้" if u.is_active else "ถูกปิด"
            last = u.last_login.strftime("%d/%m/%Y %H:%M") if u.last_login else "ยังไม่เคยเข้า"
            line = f"{u.username:<20} {active:<10} {role:<12} {last}"
            self.stdout.write(line if u.is_active else self.style.WARNING(line))

        self.stdout.write(
            "\nชื่อผู้ใช้ต้องพิมพ์ให้ตรงตัวพิมพ์เล็กใหญ่ — Bam กับ bam ถือว่าคนละบัญชี"
            "\n\nลืมรหัสผ่าน ตั้งใหม่ได้ด้วย:"
            "\n  python manage.py make_learner <ชื่อผู้ใช้> --name <ชื่อจริง> "
            "--exam-date YYYY-MM-DD --password '<รหัสใหม่>'   # ผู้เรียน"
            "\n  python manage.py changepassword <ชื่อผู้ใช้>"
            "                                     # บัญชีผู้ดูแล"
        )
