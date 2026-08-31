"""ติดป้ายคำที่ด่านตรวจคุณภาพตั้งธงไว้ ให้ผู้เรียนเห็นก่อนเชื่อ

    python manage.py flag_vocab_quality --dry-run
    python manage.py flag_vocab_quality

ที่มา: import_vocab กรองด้วย needs_human_review อย่างเดียว ซึ่งครอบเฉพาะธง
self_flagged (149 คำ) ส่วนธงจากการตรวจอัตโนมัติใน data/vocab/needs_review.json
ไม่เคยถูกอ่านเลย ทำให้คำระดับ error 62 คำ และ warn 817 คำ อยู่ในระบบและกำลังสอนอยู่

**ทำไมติดป้ายแทนที่จะลบ**
ดูตัวอย่างจริงแล้ว severity=error หมายถึง "ด่านตรวจอัตโนมัติไม่ผ่าน"
ไม่ได้แปลว่าคำแปลผิดแน่นอน — เช่น 称赞 ติดธงเพราะประโยคตัวอย่างซ้ำกับคำอื่น
ซึ่งไม่กระทบความถูกต้องของคำแปลเลย

การลบ 879 คำ (37% ของคลัง) ออกกลางคอร์สจะทำลายคิวทบทวนที่สะสมมา
และตัดคำที่ส่วนใหญ่ถูกต้องออกไปด้วย — เสียมากกว่าได้

ป้ายนี้ทำงานเหมือนป้าย ✱✱✱ ของคำอธิบาย AI: บอกผู้เรียนว่าอย่าเพิ่งเชื่อสนิท
และเปิดทางให้กดแย้งได้ ซึ่งเป็นกลไกที่ระบบมีอยู่แล้ว
"""
import json
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import VocabItem

SEVERITY_TAG = {
    "error": "review:error",
    "warn": "review:warn",
    "self_flagged": "review:self",
}


class Command(BaseCommand):
    help = "ติดป้ายคำที่ด่านตรวจคุณภาพตั้งธงไว้ เพื่อให้ผู้เรียนเห็นก่อนเชื่อ"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        path = Path(settings.BASE_DIR) / "data" / "vocab" / "needs_review.json"
        if not path.exists():
            self.stderr.write(f"ไม่พบไฟล์ {path}")
            return

        doc = json.loads(path.read_text(encoding="utf-8"))
        rows = doc["words"] if isinstance(doc, dict) and "words" in doc else doc

        # คำเดียวอาจมีหลายธง — เก็บระดับที่รุนแรงที่สุดไว้
        worst: dict[str, str] = {}
        order = ["self_flagged", "warn", "error"]
        for r in rows:
            hanzi, sev = r.get("hanzi"), r.get("severity")
            if not hanzi or sev not in SEVERITY_TAG:
                continue
            if hanzi not in worst or order.index(sev) > order.index(worst[hanzi]):
                worst[hanzi] = sev

        found = {v.hanzi: v for v in VocabItem.objects.filter(hanzi__in=worst)}
        counts, changed = Counter(), []

        for hanzi, sev in worst.items():
            vocab = found.get(hanzi)
            if not vocab:
                continue  # ถูกกันไว้ตอน import แล้ว ไม่ต้องทำอะไร
            tag = SEVERITY_TAG[sev]
            tags = list(vocab.tags or [])
            if tag in tags:
                continue
            tags = [t for t in tags if not t.startswith("review:")] + [tag]
            if "needs_review" not in tags:
                tags.append("needs_review")
            vocab.tags = tags
            changed.append(vocab)
            counts[sev] += 1

        for sev in order[::-1]:
            if counts[sev]:
                self.stdout.write(f"  {SEVERITY_TAG[sev]:<14} {counts[sev]:>5} คำ")

        if not changed:
            self.stdout.write(self.style.SUCCESS("ทุกคำที่ตั้งธงไว้ติดป้ายครบแล้ว"))
            return

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING(
                f"\n[ดูอย่างเดียว] จะติดป้าย {len(changed)} คำ"
            ))
            return

        VocabItem.objects.bulk_update(changed, ["tags"], batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"\nติดป้ายแล้ว {len(changed)} คำ — ผู้เรียนจะเห็นคำเตือนและกดแย้งได้"
        ))
