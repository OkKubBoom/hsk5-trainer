"""นำเข้ากลุ่มคำใกล้เคียงที่ดึงจากตัวเลือกจริงของ 阅读第一部分

    python manage.py import_synonyms

กลุ่มพวกนี้มีค่ากว่ากลุ่มที่ AI จับคู่เอง เพราะผู้ออกข้อสอบเป็นคนยืนยันเองว่า
สี่คำนี้สับสนกันได้ — และ 15 ข้อจาก 45 ของพาร์ทอ่านคือข้อสอบแบบนี้ล้วน
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import SynonymGroup, VocabItem

# บนเซิร์ฟเวอร์ไม่มี data/exam_corpus/ (อยู่ใน .gitignore) จึงเก็บสำเนาไว้ใน data/ ด้วย
# ค้นจากที่แรกที่เจอ — เครื่องพัฒนาใช้ต้นฉบับ เซิร์ฟเวอร์ใช้สำเนา
CANDIDATES = [
    Path(settings.BASE_DIR) / "data" / "exam_corpus" / "synonym_sets.json",
    Path(settings.BASE_DIR) / "data" / "synonym_sets.json",
]


def _source() -> Path | None:
    return next((p for p in CANDIDATES if p.exists()), None)


class Command(BaseCommand):
    help = "นำเข้ากลุ่มคำใกล้เคียงจากข้อสอบจริง"

    @transaction.atomic
    def handle(self, *args, **opts):
        path = _source()
        if path is None:
            self.stderr.write("ไม่พบไฟล์ synonym_sets.json ทั้งใน data/ และ data/exam_corpus/")
            return

        doc = json.loads(path.read_text(encoding="utf-8"))
        created = updated = 0
        for g in doc.get("merged_groups", []):
            words = g.get("words") or []
            items = list(VocabItem.objects.filter(hanzi__in=words))
            if len(items) < 2:
                continue  # กลุ่มที่จับคู่กับคลังคำศัพท์ไม่ได้ ข้ามไป ไม่สร้างกลุ่มเปล่า

            answers = [s.get("answer_word") for s in g.get("sources") or [] if s.get("answer_word")]
            seen_in = ", ".join(f"{s['paper']} ข้อ {s['number']}" for s in (g.get("sources") or [])[:4])
            name = " / ".join(words)
            note = (
                f"กลุ่มนี้มาจากตัวเลือกจริงในข้อสอบ ({seen_in}) — "
                f"ผู้ออกข้อสอบยืนยันเองว่าสับสนกันได้\n"
                + (f"คำที่เคยเป็นเฉลย: {', '.join(dict.fromkeys(answers))}" if answers else "")
            )
            obj, was_created = SynonymGroup.objects.update_or_create(
                name=name[:120], defaults={"note_th": note},
            )
            obj.items.set(items)
            created += was_created
            updated += (not was_created)

        self.stdout.write(self.style.SUCCESS(
            f"นำเข้ากลุ่มคำใกล้เคียง — ใหม่ {created} · อัปเดต {updated} "
            f"(รวมในระบบ {SynonymGroup.objects.count()} กลุ่ม)"
        ))
