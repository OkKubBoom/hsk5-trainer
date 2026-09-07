"""เติมคำอธิบายเฉลยจาก data/explanations_extra.json

    python manage.py import_explanations            # ดูเฉยๆ ไม่แก้
    python manage.py import_explanations --apply    # เขียนจริง

**ทำไมต้องมีไฟล์นี้แยกจาก exam_fixture.json**
ชุดคำอธิบาย 492 ข้อแรกฝังอยู่ใน `data/exam_fixture.json` ซึ่ง `bootstrap` โหลด
"ครั้งเดียวตอนฐานยังว่าง" การแก้ไฟล์นั้นจึงไม่มีผลกับเซิร์ฟเวอร์ที่มีข้อมูลแล้ว
คำอธิบายที่เติมทีหลังจึงต้องมาทางคำสั่งนี้ วิธีเดียวกับ `fix_vocab_examples`

**อ้างอิงด้วย source_ref ไม่ใช่ pk**
เลข id ของเครื่องพัฒนากับเซิร์ฟเวอร์ไม่รับประกันว่าตรงกัน ถ้าอ้างด้วย pk
แล้วเลขเหลื่อม คำอธิบายจะไปติดผิดข้อ ซึ่งแย่กว่าไม่มีคำอธิบายเลย

**ไม่เขียนทับของเดิม** เว้นแต่สั่ง --force — ครูอาจแก้คำอธิบายไว้แล้ว
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import Question

SOURCE = "data/explanations_extra.json"


class Command(BaseCommand):
    help = "เติมคำอธิบายเฉลยที่เพิ่มทีหลัง (ข้อที่ตกสำรวจตอนสร้างชุดแรก)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="เขียนจริง")
        parser.add_argument("--force", action="store_true",
                            help="เขียนทับข้อที่มีคำอธิบายอยู่แล้ว (ระวัง: ทับของที่ครูแก้ไว้)")

    def handle(self, *args, **opts):
        path = Path(settings.BASE_DIR) / SOURCE
        if not path.exists():
            self.stdout.write(self.style.ERROR(f"ไม่พบไฟล์ {SOURCE}"))
            return

        items = json.loads(path.read_text(encoding="utf-8")).get("items") or []
        written = skipped = missing = ambiguous = 0

        for item in items:
            match = item.get("match") or {}
            explanation = item.get("explanation") or {}
            if not match or not explanation:
                continue

            found = list(Question.objects.filter(**match)[:2])
            label = " · ".join(f"{k}={v}" for k, v in match.items())

            if not found:
                self.stdout.write(self.style.WARNING(f"  ไม่เจอข้อที่ตรงกับ {label}"))
                missing += 1
                continue
            if len(found) > 1:
                # ตรงหลายข้อแปลว่าเงื่อนไขกว้างไป ใส่ผิดข้อดีกว่าไม่ใส่ก็ไม่จริง
                self.stdout.write(self.style.WARNING(f"  ตรงมากกว่าหนึ่งข้อ ข้าม: {label}"))
                ambiguous += 1
                continue

            question = found[0]
            if question.explanation and not opts["force"]:
                self.stdout.write(f"  มีคำอธิบายอยู่แล้ว ข้าม: {label}")
                skipped += 1
                continue

            if opts["apply"]:
                question.explanation = explanation
                question.save(update_fields=["explanation", "updated_at"])
            written += 1
            self.stdout.write(self.style.SUCCESS(
                f"  {'เขียน' if opts['apply'] else 'จะเขียน'}: {label} → {question.pk}"))

        self.stdout.write(
            f"\nเขียน {written} · มีอยู่แล้ว {skipped} · ไม่เจอ {missing} · กำกวม {ambiguous}")
        if written and not opts["apply"]:
            self.stdout.write("เติม --apply เพื่อเขียนจริง")
