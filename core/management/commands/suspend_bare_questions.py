"""พักข้อที่ไม่มีคำอธิบายเฉลยเลย

    python manage.py suspend_bare_questions --dry-run
    python manage.py suspend_bare_questions

ตอบผิดแล้วเงียบ แย่กว่าไม่เจอข้อนั้นเลย — ผู้เรียนรู้แค่ว่าผิด
แต่ไม่รู้ว่าผิดเพราะอะไร ซึ่งขัดกับ D8 ที่เป็นเหตุผลหลักของระบบนี้

ใช้ status=suspended ตาม CLAUDE.md ข้อ 11 ไม่ใช่ลบทิ้ง
เพราะข้อยังใช้ได้ทันทีที่มีคำอธิบาย — แค่ยังไม่พร้อมให้ผู้เรียนเจอ
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from core.models import Question, QuestionStatus

# ข้อฟังกับข้อเขียนยังไม่มีหน้าจอรองรับอยู่แล้ว ไม่ต้องแตะ
SKIP_TYPES = ["listening_mc", "writing_prompt"]


class Command(BaseCommand):
    help = "พักข้อที่ไม่มีคำอธิบายเฉลย เพื่อไม่ให้ผู้เรียนเจอข้อที่ผิดแล้วเงียบ"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="ดูก่อนว่าจะพักข้อไหน")
        parser.add_argument("--unsuspend", action="store_true",
                            help="ปลดพักข้อที่มีคำอธิบายแล้ว (ใช้หลังเติมคำอธิบายเข้าไป)")

    def handle(self, *args, **opts):
        if opts["unsuspend"]:
            return self._unsuspend(opts["dry_run"])

        bare = (
            Question.objects
            .filter(status=QuestionStatus.ACTIVE, explanation={}, explanation_th="")
            .exclude(qtype__in=SKIP_TYPES)
        )
        total = bare.count()
        if not total:
            self.stdout.write(self.style.SUCCESS("ทุกข้อที่ใช้งานอยู่มีคำอธิบายครบแล้ว"))
            return

        for q in bare:
            self.stdout.write(f"  #{q.pk:<5} {q.qtype:<15} {(q.source_ref or q.prompt_zh[:40])}")

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING(f"\n[ดูอย่างเดียว] จะพัก {total} ข้อ"))
            return

        bare.update(status=QuestionStatus.SUSPENDED)
        self.stdout.write(self.style.SUCCESS(
            f"\nพักแล้ว {total} ข้อ — ผู้เรียนจะไม่เจอข้อที่ตอบผิดแล้วไม่มีคำอธิบายอีก"
        ))

    def _unsuspend(self, dry_run: bool):
        fixed = (
            Question.objects
            .filter(status=QuestionStatus.SUSPENDED)
            .exclude(Q(explanation={}) & Q(explanation_th=""))
        )
        total = fixed.count()
        if not total:
            self.stdout.write("ไม่มีข้อที่พักไว้แล้วมีคำอธิบายเพิ่มเข้ามา")
            return
        if dry_run:
            self.stdout.write(self.style.WARNING(f"[ดูอย่างเดียว] จะปลดพัก {total} ข้อ"))
            return
        fixed.update(status=QuestionStatus.ACTIVE)
        self.stdout.write(self.style.SUCCESS(f"ปลดพักแล้ว {total} ข้อ"))
