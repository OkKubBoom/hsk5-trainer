"""ซ่อมคำศัพท์ที่ประโยคจีนกับคำแปลไทยไม่ตรงกัน

    python manage.py fix_vocab_examples            # ดูอย่างเดียว
    python manage.py fix_vocab_examples --apply    # ซ่อมจริง

**ความเสียหายเกิดจากอะไร**
seed_hsk5 เดิมเขียนทับ example_zh ด้วยประโยคจากไฟล์ตั้งต้น แต่ไม่แตะ example_th
พอ bootstrap รัน seed_hsk5 หลัง import_vocab ประโยคจีนจึงเป็นของไฟล์ตั้งต้น
ส่วนคำแปลไทยยังเป็นของประโยคเดิม → คนละเรื่องกันคนละประโยค
(ผู้ใช้เจอเองที่ 与其 กับ 此外 — จีนบอกอย่าง ไทยแปลอีกอย่าง)

seed_hsk5 แก้แล้วไม่ให้เขียนทับอีก แต่ฐานที่พังไปแล้วต้องซ่อมด้วยคำสั่งนี้

**ซ่อมยังไง** เอาคู่ประโยคจีน-ไทยที่ถูกต้องจาก data/vocab/hsk5_merged.json กลับมา
ถ้าไฟล์นั้นไม่มีตัวอย่างของคำนั้น จะ *ลบคำแปลไทยที่ไม่ตรงทิ้ง* แทนการปล่อยไว้ —
ไม่มีคำแปลดีกว่ามีคำแปลผิด เพราะผู้เรียนจะจำประโยคผิดไปใช้
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import VocabItem

SEED = Path(settings.BASE_DIR) / "data" / "seed_vocab.txt"
MERGED = Path(settings.BASE_DIR) / "data" / "vocab" / "hsk5_merged.json"


class Command(BaseCommand):
    help = "ซ่อมคำที่ประโยคตัวอย่างจีนกับคำแปลไทยไม่ตรงกัน"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="ซ่อมจริง")

    def handle(self, *args, **opts):
        seed_examples = {}
        if SEED.exists():
            for line in SEED.read_text(encoding="utf-8").splitlines():
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 4 and parts[3]:
                    seed_examples[parts[0]] = parts[3]

        good = {}
        if MERGED.exists():
            doc = json.loads(MERGED.read_text(encoding="utf-8"))
            # คีย์คือ "words" เหมือนที่ import_vocab ใช้ ไม่ใช่ list ตรงๆ
            rows = doc if isinstance(doc, list) else doc.get("words", [])
            for r in rows:
                if r.get("hanzi") and r.get("example_zh") and r.get("example_th"):
                    good[r["hanzi"]] = (r["example_zh"], r["example_th"])

        restored = cleared = 0
        for hanzi, seeded in seed_examples.items():
            v = VocabItem.objects.filter(hanzi=hanzi).first()
            # พังคือ: ประโยคจีนเป็นของไฟล์ตั้งต้น แต่ยังมีคำแปลไทยของประโยคอื่นค้างอยู่
            if not v or not v.example_th or v.example_zh != seeded:
                continue

            if hanzi in good:
                v.example_zh, v.example_th = good[hanzi]
                restored += 1
                action = "คืนคู่ที่ถูกต้อง"
            else:
                # ไม่มีคำแปลที่คู่กัน — ทิ้งคำแปลที่ไม่ตรง เก็บประโยคจีนไว้
                v.example_th = ""
                cleared += 1
                action = "ลบคำแปลที่ไม่ตรงทิ้ง"

            self.stdout.write(f"  {hanzi:<6} {action}")
            if opts["apply"]:
                v.save(update_fields=["example_zh", "example_th", "updated_at"])

        head = "ซ่อมแล้ว" if opts["apply"] else "ดูอย่างเดียว (ยังไม่เขียน) —"
        self.stdout.write(self.style.SUCCESS(
            f"{head} คืนคู่ที่ถูกต้อง {restored} คำ · ลบคำแปลที่ไม่ตรง {cleared} คำ"))
        if not opts["apply"]:
            self.stdout.write("เติม --apply เพื่อซ่อมจริง")
