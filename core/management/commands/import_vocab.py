"""นำเข้าคำศัพท์จาก data/vocab/hsk5_merged.json เข้าตาราง VocabItem

    python manage.py import_vocab                 # นำเข้าเฉพาะคำที่ไม่ติดธง
    python manage.py import_vocab --include-flagged   # นำเข้าทั้งหมด (คำที่ติดธงจะถูกทำเครื่องหมายไว้)

คำที่ยังไม่ผ่านการตรวจของครูจะได้แท็ก "needs_review" เพื่อให้ UI เตือนได้
และไม่ถูกเลือกเป็นคำใหม่ก่อนคำที่ตรวจแล้ว

ธงมีสองแหล่งที่ต้องอ่านทั้งคู่:
  hsk5_merged.json → needs_human_review  ธงที่ผู้สร้างข้อมูลตั้งเอง (149 คำ)
  needs_review.json → severity           ธงจากด่านตรวจอัตโนมัติ (error 100 · warn 934)

เดิมอ่านแค่แหล่งแรก คำระดับ error 62 คำและ warn 817 คำจึงหลุดเข้าระบบ
โดยไม่มีป้ายอะไรเลย และผู้เรียนไม่มีทางรู้ว่าคำไหนน่าสงสัย
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import SourceType, Standard, VocabItem

DATA = Path(settings.BASE_DIR) / "data" / "vocab" / "hsk5_merged.json"
REVIEW = Path(settings.BASE_DIR) / "data" / "vocab" / "needs_review.json"

# ป้ายบอกระดับความน่าสงสัยจากด่านตรวจอัตโนมัติ — ติดไว้ให้ UI เตือน ไม่ได้กันคำออก
SEVERITY_TAG = {"error": "review:error", "warn": "review:warn", "self_flagged": "review:self"}


class Command(BaseCommand):
    help = "นำเข้าคำศัพท์ HSK1-5 จากไฟล์ที่ผ่าน pipeline ตรวจสอบแล้ว"

    def add_arguments(self, parser):
        parser.add_argument("--include-flagged", action="store_true",
                            help="นำเข้าคำที่ยังต้องให้ครูตรวจด้วย (ติดแท็ก needs_review)")
        parser.add_argument("--limit", type=int, help="นำเข้าจำกัดจำนวน (ใช้ตอนทดสอบ)")


    def _severity_map(self) -> dict:
        """อ่านธงจากด่านตรวจอัตโนมัติ — คำเดียวอาจมีหลายธง เก็บระดับที่รุนแรงสุด"""
        if not REVIEW.exists():
            return {}
        doc = json.loads(REVIEW.read_text(encoding="utf-8"))
        rows = doc["words"] if isinstance(doc, dict) and "words" in doc else doc
        order = ["self_flagged", "warn", "error"]
        worst: dict[str, str] = {}
        for r in rows:
            hanzi, sev = r.get("hanzi"), r.get("severity")
            if not hanzi or sev not in SEVERITY_TAG:
                continue
            if hanzi not in worst or order.index(sev) > order.index(worst[hanzi]):
                worst[hanzi] = sev
        return worst

    @transaction.atomic
    def handle(self, *args, **opts):
        if not DATA.exists():
            self.stderr.write(f"ไม่พบไฟล์ {DATA}")
            return

        words = json.loads(DATA.read_text(encoding="utf-8"))["words"]
        if opts.get("limit"):
            words = words[: opts["limit"]]

        severity_of = self._severity_map()

        created = updated = skipped = flagged = 0
        for w in words:
            hanzi = w.get("hanzi", "")
            severity = severity_of.get(hanzi)
            needs_review = bool(w.get("needs_human_review"))

            # ธงจากด่านอัตโนมัติ *ไม่* กันคำออก แค่ติดป้ายไว้
            #
            # ดูตัวอย่างจริงแล้ว severity=error หมายถึง "ด่านตรวจไม่ผ่าน"
            # ไม่ได้แปลว่าคำแปลผิดแน่นอน เช่น 称赞 ติดธงเพราะประโยคตัวอย่างซ้ำกับคำอื่น
            # ซึ่งไม่กระทบความถูกต้องของคำแปลเลย
            #
            # ถ้ากันทั้งหมดออก คลังจะเหลือ 1,313 จาก 2,206 คำ (หายไป 40%)
            # ซึ่งตัดคำที่ส่วนใหญ่ถูกต้องทิ้งไปด้วย — เสียมากกว่าได้
            # ป้ายเตือน + ปุ่มแย้ง เป็นกลไกที่ระบบใช้กับคำอธิบาย AI อยู่แล้ว
            if needs_review and not opts["include_flagged"]:
                skipped += 1
                continue

            tags = list(w.get("tags") or [])
            if (needs_review or severity) and "needs_review" not in tags:
                tags.append("needs_review")
            if severity and SEVERITY_TAG[severity] not in tags:
                tags.append(SEVERITY_TAG[severity])
                flagged += 1

            ev = w.get("exam_evidence") or {}
            defaults = {
                "pinyin": w.get("pinyin", ""),
                "meaning_th": w.get("meaning_th", ""),
                "meaning_en": w.get("meaning_en", "")[:255],
                "pos": ",".join(w.get("pos") or [])[:24],
                "hsk_level": w.get("hsk_level", 5),
                # จัดลำดับด้วยหลักฐานจากข้อสอบจริงก่อน แล้วค่อยความถี่ในคลังข้อความ
                "frequency_rank": w.get("priority") or w.get("frequency_rank_corpus"),
                "tags": tags,
                "collocations": w.get("collocations") or [],
                "confusable_with": w.get("confusable_with") or [],
                "example_zh": (w.get("example_zh") or "")[:255],
                "example_th": (w.get("example_th") or "")[:255],
                "standard": Standard.V2,
                "source_type": SourceType.PUBLIC_DOMAIN,
                "source_ref": f"HSK Official 2012 · พบในข้อสอบ {ev.get('papers_count', 0)} ชุด",
                "exam_papers_count": ev.get("papers_count", 0),
                "exam_occurrences": ev.get("occurrences", 0),
                "exam_as_answer": ev.get("as_answer_key", 0),
                "exam_as_distractor": ev.get("as_distractor", 0),
                "exam_evidence": {
                    "papers": ev.get("papers", []),
                    "sections": ev.get("sections", {}),
                    "likelihood": ev.get("likelihood", ""),
                    "reason": ev.get("reason", ""),
                },
                "commercial_safe": bool(w.get("commercial_safe", True)),
            }
            obj, was_created = VocabItem.objects.update_or_create(
                hanzi=w["hanzi"], standard=Standard.V2, defaults=defaults,
            )
            created += was_created
            updated += (not was_created)

        self.stdout.write(self.style.SUCCESS(
            f"นำเข้าแล้ว — เพิ่มใหม่ {created} · อัปเดต {updated} · "
            f"ข้ามคำที่ต้องให้ครูตรวจ {skipped} · ติดแท็กรอตรวจ {flagged}"
        ))
        self.stdout.write(f"รวมในฐานข้อมูลตอนนี้ {VocabItem.objects.count()} คำ")
