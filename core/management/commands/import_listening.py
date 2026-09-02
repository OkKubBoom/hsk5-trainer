"""เติมบทถอดเสียงให้ข้อสอบฟัง แล้วเปิดใช้งานข้อที่พร้อม

    python manage.py import_listening              # ดูอย่างเดียว
    python manage.py import_listening --apply      # เขียนจริง

**ปัญหาที่คำสั่งนี้แก้**
ข้อสอบฟัง 405 ข้อถูกนำเข้าไว้ตั้งแต่ต้นแต่เป็น draft ทั้งหมด เพราะไม่มีบทพูด
ผู้เรียนเห็นแค่ "(ฟังบทสนทนาแล้วเลือกคำตอบ)" กับตัวเลือกสี่ข้อ = เดาล้วน
คำสั่งนี้ดึงบทถอดเสียงจาก data/exam_corpus/ มาผูกเข้ากับข้อที่มีอยู่แล้ว

**ชุดที่ไม่มีบทถอดเสียงจะไม่ถูกแตะ** — ยังเป็น draft ต่อไป ซึ่งถูกแล้ว
ปล่อยให้ active โดยไม่มีเสียง = ผู้เรียนเจอข้อที่ตอบไม่ได้จริงแล้วถูกนับว่าผิด

**บนเซิร์ฟเวอร์ไม่มี data/exam_corpus/** — โฟลเดอร์นั้นอยู่ทั้งใน .gitignore และ
.dockerignore จึงไม่ติดไปกับ image คำสั่งนี้จึงอ่านจาก data/listening_fixture.json แทน
ซึ่งสร้างจากเครื่องพัฒนาด้วย `python manage.py export_listening` แล้ว commit ขึ้นไป
ถ้ามีทั้งสองแหล่ง จะใช้ของจริงจาก exam_corpus ก่อนเสมอ เพราะเป็นต้นทาง

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
FIXTURE = Path(settings.BASE_DIR) / "data" / "listening_fixture.json"


class Command(BaseCommand):
    help = "เติมบทถอดเสียงให้ข้อสอบฟัง และเปิดใช้ข้อที่พร้อมแล้ว"

    def add_arguments(self, parser_):
        parser_.add_argument("--apply", action="store_true", help="เขียนจริง (ค่าตั้งต้นคือดูอย่างเดียว)")
        parser_.add_argument("--papers", nargs="*", help="ระบุเฉพาะบางชุด เช่น H51001")

    @transaction.atomic
    def handle(self, *args, **opts):
        papers = self._read(opts.get("papers"))
        if papers is None:
            return

        filled = activated = missing_q = no_script = 0
        for paper, items in papers:
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

    # ── หาแหล่งบทถอดเสียง ────────────────────────────────

    def _read(self, wanted) -> list[tuple[str, list]] | None:
        """คืน [(ชื่อชุด, รายการข้อ)] จากแหล่งที่หาเจอ — None เมื่อไม่เจอเลย

        ลอง exam_corpus ก่อนเพราะเป็นต้นทางจริง ถ้าไม่มี (เช่นบนเซิร์ฟเวอร์)
        ค่อยใช้ไฟล์สรุปที่ export ไว้ ไม่สลับลำดับนี้ ไม่งั้นแก้ที่ต้นทางแล้วไม่มีผล
        """
        wanted = set(wanted or [])
        files = sorted(CORPUS.glob("H51*.json")) if CORPUS.is_dir() else []
        if files:
            out = []
            for path in files:
                if wanted and path.stem not in wanted:
                    continue
                raw = path.read_text(encoding="utf-8").replace("昀", "最")
                doc = json.loads(raw)
                out.append((doc["meta"]["paper"],
                            parser.parse((doc.get("listening") or {}).get("transcript") or "")))
            self.stdout.write(f"อ่านจาก {CORPUS.name}/ ({len(out)} ชุด)")
            return out

        if FIXTURE.exists():
            data = json.loads(FIXTURE.read_text(encoding="utf-8"))
            self.stdout.write(f"อ่านจาก {FIXTURE.name} (ไม่พบ exam_corpus บนเครื่องนี้)")
            out = []
            for paper, rows in data.items():
                if wanted and paper not in wanted:
                    continue
                out.append((paper, [parser.ListeningItem(**r) for r in rows]))
            return out

        self.stderr.write(
            "ไม่พบบทถอดเสียงเลย — ต้องมี data/exam_corpus/ (เครื่องพัฒนา) "
            "หรือ data/listening_fixture.json (เซิร์ฟเวอร์)\n"
            "สร้างไฟล์หลังด้วย: python manage.py export_listening"
        )
        return None

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
