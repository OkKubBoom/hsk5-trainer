"""นำเข้าข้อสอบจริงจาก data/exam_corpus/ เข้าตาราง Question

    python manage.py import_exams              # นำเข้าทุกชุด
    python manage.py import_exams --papers H51001 H51002

⚠️ ลิขสิทธิ์ — ทุกข้อที่นำเข้าจะถูกตั้ง source_type = official_past_paper
และ commercial_safe = False อัตโนมัติ (บังคับโดย Provenance.save)
ใช้ฝึกส่วนตัวได้ ห้ามหลุดเข้าเวอร์ชันขาย
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    GroupKind, ItemGroup, Question, QuestionOption, QuestionStatus,
    QuestionType, Section, SourceType,
)

CORPUS = Path(settings.BASE_DIR) / "data" / "exam_corpus"
LETTERS = ["A", "B", "C", "D"]


class Command(BaseCommand):
    help = "นำเข้าข้อสอบเก่าที่แยกโครงสร้างแล้วเข้าคลังคำถาม"

    def add_arguments(self, parser):
        parser.add_argument("--papers", nargs="*", help="ระบุเฉพาะบางชุด เช่น H51001")
        parser.add_argument("--reset", action="store_true", help="ลบข้อสอบเก่าที่เคยนำเข้าก่อน")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["reset"]:
            n, _ = Question.objects.filter(source_type=SourceType.OFFICIAL_PAST_PAPER).delete()
            self.stdout.write(f"ลบของเดิม {n} แถว")

        files = sorted(CORPUS.glob("H51*.json"))
        if opts["papers"]:
            wanted = set(opts["papers"])
            files = [f for f in files if f.stem in wanted]
        if not files:
            self.stderr.write("ไม่พบไฟล์ข้อสอบใน data/exam_corpus/")
            return

        totals = {"listening": 0, "reading": 0, "writing": 0, "skipped": 0}
        for path in files:
            # ฟอนต์ใน PDF บางชุดพิมพ์ 最 ออกมาเป็น 昀 — พบในหลายชุด ไม่ใช่แค่ H51332
            raw = path.read_text(encoding="utf-8").replace("昀", "最")
            doc = json.loads(raw)
            paper = doc["meta"]["paper"]
            key = {str(k): v for k, v in doc.get("answer_key", {}).items()}
            counts = self._import_paper(paper, doc, key)
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
            self.stdout.write(
                f"  {paper}: ฟัง {counts['listening']} · อ่าน {counts['reading']} · เขียน {counts['writing']}"
                + (f" · ข้าม {counts['skipped']}" if counts["skipped"] else "")
            )

        self.stdout.write(self.style.SUCCESS(
            f"นำเข้าแล้ว — ฟัง {totals['listening']} · อ่าน {totals['reading']} · เขียน {totals['writing']} "
            f"(รวม {sum(v for k, v in totals.items() if k != 'skipped')} ข้อ)"
        ))
        self.stdout.write(
            "ทุกข้อติดป้าย commercial_safe=False — ใช้ฝึกส่วนตัวเท่านั้น ห้ามเข้าเวอร์ชันขาย"
        )

    # ── ตัวช่วย ───────────────────────────────────────────

    def _group(self, paper, kind, section, text, index):
        if not text:
            return None
        group, _ = ItemGroup.objects.get_or_create(
            kind=kind, section=section, title=f"{paper} · {kind} #{index}",
            defaults={
                "passage_zh": text, "char_count": len(text),
                "source_type": SourceType.OFFICIAL_PAST_PAPER, "source_ref": paper,
            },
        )
        return group

    def _question(self, paper, number, *, qtype, section, prompt, answer,
                  options, group=None, instruction="", force_status=None):
        """สร้างหนึ่งข้อ — ข้อที่ไม่มีเฉลยจะถูกตั้งเป็น draft ไม่ใช่ active

        ข้อที่เฉลยหายจะไม่ถูกหยิบเข้าชุดฝึก เพราะระบบตรวจถูก/ผิดไม่ได้
        ปล่อยให้ active แล้วผู้เรียนจะถูกตัดสินว่าผิดทั้งที่ตอบถูก
        """
        has_answer = bool(answer)
        question, created = Question.objects.update_or_create(
            source_type=SourceType.OFFICIAL_PAST_PAPER,
            source_ref=f"{paper} ข้อ {number}",
            defaults={
                "qtype": qtype, "section": section,
                "status": force_status or (QuestionStatus.ACTIVE if has_answer else QuestionStatus.DRAFT),
                "prompt_zh": prompt, "prompt_th": instruction,
                "answer_text": (answer or "")[:400], "group": group,
                "commercial_safe": False,
            },
        )
        if options:
            question.options.all().delete()
            QuestionOption.objects.bulk_create([
                QuestionOption(
                    question=question, text=text[:400],
                    # เทียบข้อความเสมอ — เดิมใช้ len(answer)==1 เดาว่าเป็นตัวอักษร A-D
                    # แต่เฉลยของ 选词填空 หลายข้อเป็นอักษรจีนตัวเดียว (戴 逃 岸 摆 颗)
                    # ทำให้ไม่มีตัวเลือกไหนถูกทำเครื่องหมายว่าถูก แล้วผู้เรียนตอบถูกก็โดนนับว่าผิด
                    is_correct=(text == answer or letter == answer),
                    order=i,
                )
                for i, (letter, text) in enumerate(options.items())
            ])
        return created, has_answer

    def _import_paper(self, paper, doc, key):
        counts = {"listening": 0, "reading": 0, "writing": 0, "skipped": 0}

        # ── 听力 ──────────────────────────────────────────
        listening = doc.get("listening") or {}
        for part_name, part in (("part1", listening.get("part1")), ("part2", listening.get("part2"))):
            for item in part or []:
                num = str(item.get("number"))
                answer_letter = key.get(num, "")
                options = item.get("options") or {}
                text = next((options.get(answer_letter) for _ in [0] if answer_letter in options), "")
                _, ok = self._question(
                    paper, num, qtype=QuestionType.LISTENING_MC, section=Section.LISTENING,
                    prompt=item.get("question") or "(ฟังบทสนทนาแล้วเลือกคำตอบ)",
                    answer=text or answer_letter, options=options,
                    instruction="ฟังแล้วเลือกคำตอบที่ถูกต้อง",
                    # ยังไม่มีไฟล์เสียง — ปล่อยให้ active ไม่ได้ เพราะผู้เรียนจะเจอข้อที่
                    # ตอบไม่ได้จริง แล้วถูกนับว่าผิด เปิดใช้ตอนทำเสียงเสร็จในเฟส 3
                    force_status=QuestionStatus.DRAFT,
                )
                counts["listening"] += 1
                counts["skipped"] += (not ok)

        # ── 阅读 ──────────────────────────────────────────
        reading = doc.get("reading") or {}
        p1_passages = reading.get("part1_passages") or []
        p3_passages = reading.get("part3_passages") or []

        for item in reading.get("part1") or []:
            num = str(item.get("number"))
            options = item.get("options") or {}
            letter = key.get(num, "")
            ref = item.get("passage_ref")
            passage = item.get("passage") or (p1_passages[ref] if isinstance(ref, int) and ref < len(p1_passages) else "")
            group = self._group(paper, GroupKind.READING_CLOZE, Section.READING, passage, ref if isinstance(ref, int) else 0)
            _, ok = self._question(
                paper, num, qtype=QuestionType.SYNONYM_CLOZE, section=Section.READING,
                prompt=passage or "(เลือกคำเติมช่องว่าง)",
                answer=options.get(letter, letter), options=options, group=group,
                instruction="เลือกคำที่เหมาะกับช่องว่างที่สุด",
            )
            counts["reading"] += 1
            counts["skipped"] += (not ok)

        for item in reading.get("part2") or []:
            num = str(item.get("number"))
            options = item.get("options") or {}
            letter = key.get(num, "")
            _, ok = self._question(
                paper, num, qtype=QuestionType.READING_MC, section=Section.READING,
                prompt=item.get("passage") or item.get("question") or "(เลือกข้อที่ตรงกับเนื้อหา)",
                answer=options.get(letter, letter), options=options,
                instruction="เลือกข้อที่ตรงกับเนื้อหาที่อ่าน",
            )
            counts["reading"] += 1
            counts["skipped"] += (not ok)

        for item in reading.get("part3") or []:
            num = str(item.get("number"))
            options = item.get("options") or {}
            letter = key.get(num, "")
            ref = item.get("passage_ref")
            passage = p3_passages[ref] if isinstance(ref, int) and ref < len(p3_passages) else ""
            group = self._group(paper, GroupKind.READING_PASSAGE, Section.READING, passage, ref if isinstance(ref, int) else 0)
            _, ok = self._question(
                paper, num, qtype=QuestionType.READING_MC, section=Section.READING,
                prompt=item.get("question") or "(ตอบคำถามจากบทอ่าน)",
                answer=options.get(letter, letter), options=options, group=group,
                instruction="อ่านบทความแล้วเลือกคำตอบ",
            )
            counts["reading"] += 1
            counts["skipped"] += (not ok)

        # ── 书写 ──────────────────────────────────────────
        writing = doc.get("writing") or {}
        for item in writing.get("part1") or []:
            num = str(item.get("number"))
            words = item.get("words") or []
            answer = key.get(num, "")
            _, ok = self._question(
                paper, num, qtype=QuestionType.WORD_ORDER, section=Section.WRITING,
                prompt=" / ".join(words), answer=str(answer), options=None,
                instruction="เรียงคำให้เป็นประโยคที่ถูกต้อง",
            )
            counts["writing"] += 1
            counts["skipped"] += (not ok)

        for item in writing.get("part2") or []:
            num = str(item.get("number"))
            words = item.get("words") or []
            prompt = " / ".join(words) if words else "(เขียนเรียงความจากภาพ)"
            self._question(
                paper, num, qtype=QuestionType.WRITING_PROMPT, section=Section.WRITING,
                prompt=prompt, answer="", options=None,
                instruction="เขียนเรียงความราว 80 ตัวอักษร",
            )
            counts["writing"] += 1

        return counts
