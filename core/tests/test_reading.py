"""เทสต์การแสดงบทอ่าน — บั๊กที่ผู้เรียนเจอเองก่อนที่เราจะรู้

น้องเจอคำถาม "根据上文…" (ตามบทความข้างต้น) โดยไม่มีบทความให้อ่าน
สาเหตุคือเทมเพลตชุดฝึกรายวันไม่เคยแสดง group.passage_zh เลย
ทั้งที่หน้าข้อสอบจำลองแสดงถูกต้อง — เขียนไว้ที่เดียวแล้วลืมอีกที่

เทสต์ชุดนี้ล็อกไว้ว่าทุกหน้าที่ถามข้ออ่านต้องแสดงบทอ่านด้วยเสมอ
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import drill as drill_engine
from core import reading
from core.accounts import create_learner
from core.models import (
    Card, ItemGroup, Question, QuestionOption, QuestionStatus,
    Section, SourceType, VocabItem,
)

PASSAGE = "在沙滩排球场上，球场两边各有两名  46  着太阳眼镜、晒得一身古铜色  47  的运动员在网前争夺。"
LONG_PASSAGE = "一位著名的作家在外旅游，来到一座城市，决定去参观这个城市最大的书店。书店的老板想做点让这位作家高兴的事情。"


def add_options(q, correct="ถูก"):
    QuestionOption.objects.create(question=q, text=correct, is_correct=True, order=0)
    for i in range(3):
        QuestionOption.objects.create(question=q, text=f"ผิด{i}", is_correct=False, order=i + 1)
    return q


class ClozeTests(TestCase):
    """阅读第一部分 — บทอ่านหนึ่งบทมีหลายช่อง ถามทีละช่อง"""

    @classmethod
    def setUpTestData(cls):
        cls.group = ItemGroup.objects.create(
            kind="reading_cloze", section=Section.READING,
            passage_zh=PASSAGE, source_type=SourceType.OFFICIAL_PAST_PAPER,
        )
        cls.q46, cls.q47 = [
            add_options(Question.objects.create(
                qtype="synonym_cloze", section=Section.READING, status=QuestionStatus.ACTIVE,
                prompt_zh=PASSAGE, answer_text="ถูก", group=cls.group,
                source_ref=f"H51001 ข้อ {n}", source_type=SourceType.OFFICIAL_PAST_PAPER,
            )) for n in (46, 47)
        ]

    def test_รู้ว่ากำลังตอบช่องไหน(self):
        """น้องถามว่า 'มี 4 ช่อง ตอบยังไง' — เลขช่องเคยซ่อนอยู่ใน source_ref เท่านั้น"""
        self.assertEqual(reading.blank_number(self.q46), 46)
        self.assertEqual(reading.group_blanks(self.q46), [46, 47])

    def test_ช่องที่กำลังตอบเด่นและช่องอื่นจาง(self):
        view = reading.build(self.q46)
        self.assertIn('class="blank now">', view.passage_html)
        self.assertIn('class="blank other">', view.passage_html)
        self.assertIn("ช่อง 46", view.instruction)
        self.assertEqual(view.total_blanks, 2)

    def test_ไม่แสดงบทอ่านซ้ำสองรอบ(self):
        """ข้อชนิดนี้เก็บบทอ่านไว้ทั้งใน group และ prompt_zh — แสดงทั้งคู่คืออ่านสองรอบ"""
        view = reading.build(self.q46)
        self.assertTrue(view.has_passage)
        self.assertFalse(view.has_prompt)

    def test_บทอ่านถูก_escape_ก่อนใส่แท็ก(self):
        self.group.passage_zh = "<script>alert(1)</script> ช่อง  46  ต่อ"
        self.group.save()
        html = reading.build(self.q46).passage_html
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


class PassageTests(TestCase):
    """阅读第三部分 — บทอ่านยาว มีหลายคำถาม"""

    @classmethod
    def setUpTestData(cls):
        cls.group = ItemGroup.objects.create(
            kind="reading_passage", section=Section.READING,
            passage_zh=LONG_PASSAGE, source_type=SourceType.OFFICIAL_PAST_PAPER,
        )
        cls.q = add_options(Question.objects.create(
            qtype="reading_mc", section=Section.READING, status=QuestionStatus.ACTIVE,
            prompt_zh="根据上文，可以知道：", answer_text="ถูก", group=cls.group,
            source_type=SourceType.OFFICIAL_PAST_PAPER,
        ))

    def test_แสดงทั้งบทอ่านและคำถาม(self):
        view = reading.build(self.q)
        self.assertIn("一位著名的作家", view.passage_html)
        self.assertEqual(view.prompt, "根据上文，可以知道：")

    def test_ข้อที่ไม่มีคำถามแยกต้องบอกให้รู้(self):
        """阅读第二部分 — prompt_zh คือบทอ่าน ไม่มีคำถาม น้องเลยหาคำถามที่ไม่มีอยู่"""
        solo = add_options(Question.objects.create(
            qtype="reading_mc", section=Section.READING, status=QuestionStatus.ACTIVE,
            prompt_zh=LONG_PASSAGE, prompt_th="เลือกข้อที่ตรงกับเนื้อหาที่อ่าน",
            answer_text="ถูก", source_type=SourceType.OFFICIAL_PAST_PAPER,
        ))
        view = reading.build(solo)
        self.assertTrue(view.has_passage)
        self.assertFalse(view.has_prompt)
        self.assertIn("เลือกข้อที่ตรงกับเนื้อหา", view.instruction)


class DrillShowsPassageTests(TestCase):
    """บั๊กหลัก — ชุดฝึกรายวันต้องแสดงบทอ่าน ไม่ใช่แสดงแต่หน้าจำลองสอบ"""

    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="字", pinyin="zi", meaning_th="ตัวอักษร", hsk_level=5)
        cls.learner, _ = create_learner(
            username="kid", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60),
        )
        group = ItemGroup.objects.create(
            kind="reading_passage", section=Section.READING,
            passage_zh=LONG_PASSAGE, source_type=SourceType.OFFICIAL_PAST_PAPER,
        )
        cls.q = add_options(Question.objects.create(
            qtype="reading_mc", section=Section.READING, status=QuestionStatus.ACTIVE,
            prompt_zh="根据上文，可以知道：", answer_text="ถูก", group=group,
            source_type=SourceType.OFFICIAL_PAST_PAPER,
        ))

    def test_ข้อที่ไม่มีคำถามแยกต้องบอกไปถึงหน้าจอด้วย(self):
        """DrillQuestion เป็นคนละชนิดกับ ReadingView — ต้องส่งค่านี้ต่อ ไม่งั้นป้ายหาย"""
        solo = add_options(Question.objects.create(
            qtype="reading_mc", section=Section.READING, status=QuestionStatus.ACTIVE,
            prompt_zh=LONG_PASSAGE, prompt_th="เลือกข้อที่ตรงกับเนื้อหาที่อ่าน",
            answer_text="ถูก", source_type=SourceType.OFFICIAL_PAST_PAPER,
        ))
        dq = drill_engine.build_question(
            {"kind": "question", "id": solo.pk, "source": "due"}, 1, 1)
        self.assertTrue(dq.answers_whole_passage)

    def test_build_question_ส่งบทอ่านไปให้หน้าเว็บด้วย(self):
        entry = {"kind": "question", "id": self.q.pk, "source": "due"}
        dq = drill_engine.build_question(entry, 1, 1)
        self.assertIn("一位著名的作家", dq.passage_html)
        self.assertEqual(dq.prompt, "根据上文，可以知道：")

    def test_หน้าชุดฝึกแสดงบทอ่านจริงบนหน้าจอ(self):
        """เทสต์ผ่าน view จริง เพราะบั๊กเดิมอยู่ในเทมเพลต ไม่ได้อยู่ในตรรกะ"""
        self.client.login(username="kid", password="passpass1")
        session, _ = drill_engine.start_or_resume(self.learner)
        session.queue = [{"kind": "question", "id": self.q.pk, "source": "due"}]
        session.position = 0
        session.save()

        res = self.client.get(reverse("drill_run"))
        self.assertContains(res, "一位著名的作家")
        self.assertContains(res, "根据上文")
