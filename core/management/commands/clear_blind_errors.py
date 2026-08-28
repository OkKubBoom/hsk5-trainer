"""ล้างบันทึกข้อผิดที่เกิดจากข้อที่ *ตอบไม่ได้* ไม่ใช่ข้อที่ผู้เรียนทำไม่ได้

    python manage.py clear_blind_errors --dry-run    # ดูก่อนว่าจะลบอะไร
    python manage.py clear_blind_errors              # ลบจริง

ที่มา: หน้าชุดฝึกรายวันเคยไม่แสดงบทอ่านเลย ผู้เรียนจึงเจอคำถามอย่าง
"根据上文…" โดยไม่มีบทความให้อ่าน ตอบได้อย่างเดียวคือเดา

เดาผิดถูกบันทึกเป็น "ตอบผิด" แล้วชุดฝึกวันถัดไปเอากลับมาถามซ้ำผ่านโควตา 30%
= ระบบตามตื้อคำที่ผู้เรียนไม่ได้ผิดจริง และไปกินที่ของคำที่ผิดจริง

ลบเฉพาะบันทึกที่ผูกกับคำถามที่มีบทอ่านอยู่ในกลุ่ม (ชนิดที่จอเคยไม่แสดง)
บันทึกจากข้อคำศัพท์และข้อสั้นไม่ถูกแตะ เพราะข้อพวกนั้นแสดงครบมาตลอด
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from core.models import ErrorLog


class Command(BaseCommand):
    help = "ล้างบันทึกข้อผิดที่เกิดตอนหน้าจอยังไม่แสดงบทอ่าน"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="แสดงว่าจะลบอะไรบ้าง แต่ยังไม่ลบจริง")
        parser.add_argument("--learner", default=None,
                            help="จำกัดเฉพาะ username เดียว (ไม่ใส่ = ทุกคน)")

    def handle(self, *args, **opts):
        # ข้อที่จอเคยไม่แสดงบทอ่าน = ข้อที่บทอ่านอยู่ใน ItemGroup
        blind = ErrorLog.objects.filter(
            question__isnull=False,
            question__group__isnull=False,
        ).exclude(question__group__passage_zh="")

        if opts["learner"]:
            blind = blind.filter(learner__user__username=opts["learner"])

        total = blind.count()
        if not total:
            self.stdout.write(self.style.SUCCESS("ไม่มีบันทึกที่ต้องล้าง"))
            return

        by_learner = {}
        for e in blind.select_related("learner__user", "question"):
            by_learner.setdefault(e.learner.user.username, []).append(e)

        for username, rows in sorted(by_learner.items()):
            self.stdout.write(f"\n{username} — {len(rows)} รายการ")
            for e in rows[:8]:
                self.stdout.write(f"   {e.label[:50]:<52} ผิดไป {e.miss_count} ครั้ง")
            if len(rows) > 8:
                self.stdout.write(f"   … และอีก {len(rows) - 8} รายการ")

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING(
                f"\n[ดูอย่างเดียว] จะลบ {total} รายการ — รันซ้ำโดยไม่ใส่ --dry-run เพื่อลบจริง"
            ))
            return

        blind.delete()
        self.stdout.write(self.style.SUCCESS(
            f"\nล้างแล้ว {total} รายการ — คิวคำที่เคยผิดกลับมาสะท้อนความจริง"
        ))
