"""ใส่ข้อมูลตั้งต้น — รันซ้ำได้ ไม่สร้างซ้ำ

    python manage.py seed_hsk5
    python manage.py seed_hsk5 --learner nong --exam-date 2026-12-13

ชุดคำศัพท์ตั้งต้นคือคำที่ให้ผลตอบแทนสูงสุด ไม่ใช่คำที่มาก่อนตามตัวอักษร:
คำเชื่อมที่ใช้ในเรียงความ กริยานามธรรมความถี่สูง คำใกล้เคียงที่ข้อสอบชอบหลอก
และสำนวนสี่พยางค์ที่ยัดลงเรียงความได้ทุกหัวข้อ
"""
import json
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    Card, CardType, ExamSpec, GrammarPoint, LearnerProfile, Question,
    QuestionOption, QuestionStatus, QuestionType, Role, Section, SourceType,
    Standard, SynonymGroup, User, VocabItem, WritingTemplate,
)

DATA_DIR = Path(settings.BASE_DIR) / "data"


class Command(BaseCommand):
    help = "ใส่คำศัพท์ ไวยากรณ์ เทมเพลต และคำถามตั้งต้นสำหรับ HSK5"

    def add_arguments(self, parser):
        parser.add_argument("--learner", help="username ของผู้เรียนที่จะสร้างการ์ดให้")
        parser.add_argument("--exam-date", default=settings.TARGET_EXAM_DATE, help="วันสอบเป้าหมาย")

    @transaction.atomic
    def handle(self, *args, **opts):
        content = json.loads((DATA_DIR / "seed_content.json").read_text(encoding="utf-8"))

        self._exam_specs(content["exam_specs"])
        vocab_map = self._vocab()
        self._synonym_groups(content["synonym_groups"], vocab_map)
        self._grammar(content["grammar_points"])
        self._templates(content["writing_templates"])
        self._synonym_cloze(content["synonym_cloze"])
        self._word_order(content["word_order"])

        if opts.get("learner"):
            self._learner(opts["learner"], opts["exam_date"], vocab_map)

        self.stdout.write(self.style.SUCCESS("\nใส่ข้อมูลตั้งต้นเรียบร้อย"))
        self.stdout.write("ขั้นถัดไป: python manage.py createsuperuser แล้ว runserver → /admin/")

    # ── ส่วนย่อย ────────────────────────────────────────

    def _exam_specs(self, specs):
        for s in specs:
            ExamSpec.objects.update_or_create(
                standard=s["standard"], level=s["level"],
                defaults={k: v for k, v in s.items() if k not in ("standard", "level")},
            )
        self.stdout.write(f"  สเปกข้อสอบ           {len(specs)}")

    def _vocab(self):
        """seed_vocab.txt รูปแบบ:  汉字|pinyin|ความหมายไทย|ประโยคตัวอย่าง|แท็ก

        **เติมเฉพาะคำที่ยังไม่มี ห้ามเขียนทับของเดิม**

        ไฟล์นี้เป็นชุดตั้งต้นเขียนมือ 109 คำ ส่วน import_vocab นำเข้า 2,206 คำ
        พร้อมคำแปล ตัวอย่างจีน *และตัวอย่างไทยที่คู่กัน*

        เดิมคำสั่งนี้ update_or_create แล้วเขียนทับ example_zh โดยไม่แตะ example_th
        → ประโยคจีนกับคำแปลไทยเป็นคนละประโยคกัน 70 คำ
          (ผู้ใช้เจอเองที่ 与其 กับ 此外 — จีนพูดเรื่องหนึ่ง ไทยแปลอีกเรื่อง)
        และเขียนทับ tags ทั้งก้อนด้วย [tag] เดียว → ป้าย needs_review / human_verified
        ที่ครูตรวจไว้แล้วหายทั้งหมด 94 คำ ทุกครั้งที่รัน bootstrap ซ้ำ

        bootstrap รัน seed_hsk5 *หลัง* import_vocab เสมอ ความเสียหายจึงเกิดบน prod
        แต่ไม่เกิดบนเครื่องพัฒนาที่รัน import_vocab ทีหลัง — ซ่อนอยู่จนผู้ใช้เจอ
        """
        path = DATA_DIR / "seed_vocab.txt"
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        vocab_map, created, kept = {}, 0, 0
        for rank, line in enumerate(lines, start=1):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            hanzi, pinyin, meaning = parts[0], parts[1], parts[2]
            example = parts[3] if len(parts) > 3 else ""
            tag = parts[4] if len(parts) > 4 else "misc"

            existing = VocabItem.objects.filter(hanzi=hanzi, standard=Standard.V2).first()
            if existing:
                # ของที่มีอยู่แล้วสมบูรณ์กว่าเสมอ — แตะแค่ลำดับความสำคัญ
                if not existing.frequency_rank:
                    existing.frequency_rank = rank
                    existing.save(update_fields=["frequency_rank", "updated_at"])
                vocab_map[hanzi] = existing
                kept += 1
                continue

            vocab_map[hanzi] = VocabItem.objects.create(
                hanzi=hanzi, standard=Standard.V2,
                pinyin=pinyin, meaning_th=meaning, example_zh=example,
                tags=[tag], hsk_level=5, frequency_rank=rank,
                source_type=SourceType.HAND_WRITTEN, commercial_safe=True,
            )
            created += 1
        self.stdout.write(
            f"  คำศัพท์              {len(vocab_map)} (สร้างใหม่ {created} · มีอยู่แล้วไม่แตะ {kept})")
        return vocab_map

    def _synonym_groups(self, groups, vocab_map):
        for g in groups:
            obj, _ = SynonymGroup.objects.update_or_create(
                name=g["name"], defaults={"note_th": g["note_th"]},
            )
            items = [vocab_map[h] for h in g["items"] if h in vocab_map]
            if items:
                obj.items.set(items)
        self.stdout.write(f"  กลุ่มคำใกล้เคียง      {len(groups)}")

    def _grammar(self, points):
        for p in points:
            GrammarPoint.objects.update_or_create(
                title_zh=p["title_zh"],
                defaults={
                    "title_th": p["title_th"],
                    "explanation_th": p["explanation_th"],
                    "patterns": p.get("patterns", []),
                    "priority": p.get("priority", 50),
                    "section": Section.WRITING,
                    "source_type": SourceType.HAND_WRITTEN,
                },
            )
        self.stdout.write(f"  จุดไวยากรณ์          {len(points)}")

    def _templates(self, templates):
        for t in templates:
            WritingTemplate.objects.update_or_create(
                name=t["name"],
                defaults={
                    "body_zh": t["body_zh"],
                    "body_th": t["body_th"],
                    "approx_chars": t.get("approx_chars", 90),
                    "use_case": t.get("use_case", ""),
                    "source_type": SourceType.HAND_WRITTEN,
                },
            )
        self.stdout.write(f"  เทมเพลตเรียงความ     {len(templates)}")

    def _synonym_cloze(self, rows):
        made = 0
        for r in rows:
            q, created = Question.objects.update_or_create(
                prompt_zh=r["prompt"], qtype=QuestionType.SYNONYM_CLOZE,
                defaults={
                    "section": Section.READING,
                    "status": QuestionStatus.ACTIVE,
                    "prompt_th": "เลือกคำที่เหมาะกับบริบทที่สุด",
                    "answer_text": r["answer"],
                    "explanation_th": r["explanation"],
                    "difficulty": 3,
                    "target_seconds": 45,
                    "source_type": SourceType.HAND_WRITTEN,
                },
            )
            q.options.all().delete()
            for i, opt in enumerate(r["options"]):
                QuestionOption.objects.create(
                    question=q, text=opt, is_correct=(opt == r["answer"]), order=i,
                    distractor_type="" if opt == r["answer"] else "near_synonym",
                )
            made += 1
        self.stdout.write(f"  ข้อเลือกคำใกล้เคียง   {made}")

    def _word_order(self, rows):
        made = 0
        for r in rows:
            Question.objects.update_or_create(
                prompt_zh=" / ".join(r["parts"]), qtype=QuestionType.WORD_ORDER,
                defaults={
                    "section": Section.WRITING,
                    "status": QuestionStatus.ACTIVE,
                    "prompt_th": "เรียงคำต่อไปนี้เป็นประโยคที่ถูกต้อง",
                    "answer_text": r["answer"],
                    "explanation_th": r["rule"],
                    "difficulty": 3,
                    "target_seconds": 90,
                    "source_type": SourceType.HAND_WRITTEN,
                },
            )
            made += 1
        self.stdout.write(f"  ข้อเรียงประโยค        {made}")

    def _learner(self, username, exam_date, vocab_map):
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"role": Role.LEARNER, "display_name": username},
        )
        profile, _ = LearnerProfile.objects.get_or_create(
            user=user,
            defaults={
                "target_exam_date": date.fromisoformat(str(exam_date)),
                "target_level": 5,
            },
        )
        # การ์ดสองชนิดต่อคำ: อ่านได้ กับ ฟังออก — คนละทักษะ ต้องแยกฝึก
        made = 0
        for vocab in vocab_map.values():
            for ct in (CardType.RECOGNIZE, CardType.AUDIO):
                _, created = Card.objects.get_or_create(
                    learner=profile, vocab=vocab, card_type=ct,
                )
                made += int(created)
        self.stdout.write(
            f"  ผู้เรียน '{username}'  การ์ดใหม่ {made} ใบ (สอบ {profile.target_exam_date})"
        )
