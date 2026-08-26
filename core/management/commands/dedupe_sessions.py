"""รวมเซสชันที่ซ้ำวันเดียวกันให้เหลือวันละชุด

    python manage.py dedupe_sessions --dry-run
    python manage.py dedupe_sessions

จำเป็นเพราะกฎ "หนึ่งวันหนึ่งชุด" เพิ่งถูกบังคับในโค้ด ข้อมูลที่สร้างก่อนหน้านั้น
อาจมีหลายชุดในวันเดียว ซึ่งทำให้ความแม่นและจำนวนวันที่ทำติดกันเพี้ยน

เก็บชุดที่ตอบไว้มากที่สุดของวันนั้น แล้วย้ายคำตอบจากชุดอื่นมารวม
ไม่ลบคำตอบทิ้ง เพราะเป็นหลักฐานว่าผู้เรียนทำอะไรไปจริง
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import DrillSession


class Command(BaseCommand):
    help = "รวมเซสชันซ้ำวันเดียวกันให้เหลือวันละชุด"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="ดูผลก่อน ไม่แก้จริง")

    @transaction.atomic
    def handle(self, *args, **opts):
        buckets = defaultdict(list)
        for s in DrillSession.objects.all().order_by("started_at"):
            buckets[(s.learner_id, s.started_at.date())].append(s)

        merged = removed = 0
        for (learner_id, day), sessions in sorted(buckets.items()):
            if len(sessions) < 2:
                continue
            keeper = max(sessions, key=lambda s: (s.answered, len(s.queue or []), s.pk))
            others = [s for s in sessions if s.pk != keeper.pk]
            moved = sum(s.answers.count() for s in others)
            self.stdout.write(
                f"  ผู้เรียน {learner_id} วันที่ {day}: {len(sessions)} ชุด → เก็บ #{keeper.pk} "
                f"(ตอบ {keeper.answered}) · ย้ายคำตอบมา {moved} ข้อ · ลบ {len(others)} ชุด"
            )
            if opts["dry_run"]:
                continue

            for other in others:
                other.answers.update(session=keeper)
                keeper.answered += other.answered
                keeper.correct += other.correct
                other.delete()
                removed += 1
            keeper.answered = keeper.answers.count()
            keeper.correct = keeper.answers.filter(is_correct=True).count()
            # คิวว่างแต่ยังไม่ปิด = ข้อมูลยุคก่อนมีคิวในฐานข้อมูล ถือว่าจบไปแล้ว
            if not keeper.queue and not keeper.finished_at:
                keeper.finished_at = keeper.updated_at
            keeper.save()
            merged += 1

        verb = "จะรวม" if opts["dry_run"] else "รวมแล้ว"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {merged} วัน · ลบเซสชันซ้ำ {removed} ชุด · "
            f"เหลือทั้งหมด {DrillSession.objects.count()} ชุด"
        ))
