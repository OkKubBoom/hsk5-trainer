"""เติมบทถอดเสียงให้ข้อสอบฟัง แล้วเปิดใช้งานข้อที่พร้อม

    python manage.py import_listening              # ดูอย่างเดียว
    python manage.py import_listening --apply      # เขียนจริง

**ปัญหาที่คำสั่งนี้แก้**
ข้อสอบฟัง 405 ข้อถูกนำเข้าไว้ตั้งแต่ต้นแต่เป็น draft ทั้งหมด เพราะไม่มีบทพูด
ผู้เรียนเห็นแค่ "(ฟังบทสนทนาแล้วเลือกคำตอบ)" กับตัวเลือกสี่ข้อ = เดาล้วน
คำสั่งนี้ดึงบทถอดเสียงจาก data/exam_corpus/ มาผูกเข้ากับข้อที่มีอยู่แล้ว

**ชุดที่ไม่มีบทถอดเสียงจะไม่ถูกแตะ** — ยังเป็น draft ต่อไป ซึ่งถูกแล้ว
ปล่อยให้ active โดยไม่มีเสียง = ผู้เรียนเจอข้อที่ตอบไม่ได้จริงแล้วถูกนับว่าผิด

⚠️ ลิขสิทธิ์ — บททั้งหมดมาจากข้อสอบจริง commercial_safe = False (D6)
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from core import listening as parser
from core.models import (
    GroupKind, ItemGroup, Question, QuestionStatus, Section, SourceType,
)

CORPUS = Path(settings.BASE_DIR) / "data" / "exam_corpus"


class Command(BaseCommand):
    help = "เติมบทถอดเสียงให้ข้อสอบฟัง และเปิดใช้ข้อที่พร้อมแล้ว"

    def add_arguments(self, parser_):
        parser_.add_argument("--apply", action="store_true", help="เขียนจริง (ค่าตั้งต้นคือดูอย่างเดียว)")
        parser_.add_argument("--papers", nargs="*", help="ระบุเฉพาะบางชุด เช่น H51001")

    @transaction.atomic
    def handle(self, *args, **opts):
        files = sorted(CORPUS.glob("H51*.json"))
        if opts["papers"]:
            wanted = set(opts["papers"])
            files = [f for f in files if f.stem in wanted]
        if not files:
            self.stderr.write("ไม่พบไฟล์ข้อสอบใน data/exam_corpus/")
            return

        filled = activated = missing_q = no_script = 0
        for path in files:
            raw = path.read_text(encoding="utf-8").replace("昀", "最")
            doc = json.loads(raw)
            paper = doc["meta"]["paper"]
            items = parser.parse((doc.get("listening") or {}).get("transcript") or "")
            if not items:
                no_script += 1
                self.stdout.write(f"  {paper}: ไม่มีบทถอดเสียง — ข้ามไป ข้อยังเป็น draft")
                continue

            groups: dict[str, ItemGroup] = {}
            hit = act = 0
            for item in items:
                question = Question.objects.filter(
                    source_type=SourceType.OFFICIAL_PAST_PAPER,
                    source_ref=f"{paper} ข้อ {item.number}",
                    section=Section.LISTENING,
                ).first()
                if not question:
                    missing_q += 1
                    continue

                speech = parser.speech_text(item)
                # เฉลยหายก็ยังเปิดใช้ไม่ได้ แม้จะมีเสียงแล้ว — ตรวจถูกผิดไม่ได้
                can_open = bool(question.answer_text) and bool(speech)

                if opts["apply"]:
                    group = self._group(groups, paper, item)
                    question.audio_script = speech
                    question.group = group
                    # โจทย์จริงคือคำถามที่อ่านท้ายบท ไม่ใช่ข้อความ placeholder
                    if item.question_zh:
                        question.prompt_zh = item.question_zh
                    question.prompt_th = "ฟังแล้วเลือกคำตอบที่ถูกต้อง"
                    if can_open and question.status == QuestionStatus.DRAFT:
                        question.status = QuestionStatus.ACTIVE
                        act += 1
                    question.save(update_fields=[
                        "audio_script", "group", "prompt_zh", "prompt_th", "status", "updated_at",
                    ])
                elif can_open and question.status == QuestionStatus.DRAFT:
                    act += 1
                hit += 1

            filled += hit
            activated += act
            self.stdout.write(f"  {paper}: เติมบท {hit} ข้อ · เปิดใช้ {act} ข้อ")

        head = "เขียนแล้ว" if opts["apply"] else "ดูอย่างเดียว (ยังไม่เขียน) —"
        self.stdout.write(self.style.SUCCESS(
            f"{head} เติมบท {filled} ข้อ · เปิดใช้ {activated} ข้อ"
        ))
        if no_script:
            self.stdout.write(
                f"อีก {no_script} ชุดไม่มีบทถอดเสียงในไฟล์ ข้อของชุดนั้นยังเป็น draft "
                "— ถูกแล้ว ปล่อยให้ active โดยไม่มีเสียงคือให้ผู้เรียนเดา"
            )
        if missing_q:
            self.stdout.write(f"⚠️ มีบท {missing_q} ข้อที่หาคำถามคู่กันไม่เจอ — รัน import_exams ก่อน")
        if not opts["apply"]:
            self.stdout.write("เติม --apply เพื่อเขียนจริง")

    def _group(self, cache, paper, item):
        """ชุดเนื้อหาที่เก็บบทไว้ให้ดูตอนเฉลย

        ข้อ 31-45 ใช้บทเดียวกันหลายข้อ จึงใช้กลุ่มเดียวกัน
        ข้อ 1-30 บทสั้นและไม่ซ้ำ จึงเป็นกลุ่มละข้อ
        """
        key = item.passage_key or f"q{item.number}"
        if key in cache:
            return cache[key]
        kind = GroupKind.LISTENING_PASSAGE if item.passage_key else GroupKind.LISTENING_DIALOG
        group, _ = ItemGroup.objects.get_or_create(
            kind=kind, section=Section.LISTENING, title=f"{paper} · ฟัง {key}",
            defaults={
                "passage_zh": item.script, "char_count": len(item.script),
                "source_type": SourceType.OFFICIAL_PAST_PAPER, "source_ref": paper,
            },
        )
        if group.passage_zh != item.script:
            group.passage_zh = item.script
            group.char_count = len(item.script)
            group.save(update_fields=["passage_zh", "char_count", "updated_at"])
        cache[key] = group
        return group
