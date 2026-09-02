"""ทำไฟล์บทถอดเสียงให้เซิร์ฟเวอร์ใช้ — รันบนเครื่องพัฒนาเท่านั้น

    python manage.py export_listening

**ทำไมต้องมีคำสั่งนี้**
`data/exam_corpus/` อยู่ทั้งใน .gitignore และ .dockerignore จึงไม่ติดไปกับ image
คำสั่ง import_listening บนเซิร์ฟเวอร์จึงหาบทถอดเสียงไม่เจอและไม่ทำอะไรเลย
คำสั่งนี้แปลงเฉพาะ *ผลการแยกบท* ออกมาเป็นไฟล์เดียวที่ commit ขึ้นไปได้

**สิ่งที่อยู่ในไฟล์** — บทพูดกับคำถามของข้อฟังเท่านั้น ไม่มีตัวเลือกและไม่มีเฉลย
แต่ยังเป็นข้อความจากข้อสอบจริง = ลิขสิทธิ์ ต้องถือเหมือน data/exam_fixture.json
คือใช้ฝึกส่วนตัวได้ ห้ามเข้าเวอร์ชันขาย (D6) และเป็นอีกเหตุผลที่ repo ควรเป็น private
"""
import json
from dataclasses import asdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core import listening as parser

CORPUS = Path(settings.BASE_DIR) / "data" / "exam_corpus"
OUT = Path(settings.BASE_DIR) / "data" / "listening_fixture.json"


class Command(BaseCommand):
    help = "แปลงบทถอดเสียงจาก data/exam_corpus/ เป็นไฟล์เดียวที่ deploy ไปด้วยได้"

    def handle(self, *args, **opts):
        if not CORPUS.is_dir():
            self.stderr.write(
                f"ไม่พบ {CORPUS} — คำสั่งนี้รันได้เฉพาะเครื่องที่มีข้อสอบต้นฉบับ"
            )
            return

        data, total = {}, 0
        for path in sorted(CORPUS.glob("H51*.json")):
            raw = path.read_text(encoding="utf-8").replace("昀", "最")
            doc = json.loads(raw)
            items = parser.parse((doc.get("listening") or {}).get("transcript") or "")
            if not items:
                self.stdout.write(f"  {path.stem}: ไม่มีบทถอดเสียง — ข้าม")
                continue
            data[doc["meta"]["paper"]] = [asdict(i) for i in items]
            total += len(items)
            self.stdout.write(f"  {path.stem}: {len(items)} ข้อ")

        OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        size = OUT.stat().st_size // 1024
        self.stdout.write(self.style.SUCCESS(
            f"เขียน {OUT.name} — {len(data)} ชุด · {total} ข้อ · {size} KB"
        ))
        self.stdout.write(
            "commit ไฟล์นี้แล้ว deploy จากนั้นบนเซิร์ฟเวอร์รัน:\n"
            "  python manage.py import_listening --apply"
        )
