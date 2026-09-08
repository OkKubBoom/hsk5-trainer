"""ข้อฟังในชุดฝึกรายวันต้องมีเครื่องเล่นเสียง

ผู้ใช้รายงาน (5 ก.ย.): ชุดฝึกรายวันเอาข้อฟังมาใส่ แต่ไม่มีปุ่มเล่นเสียงเลย
เห็นแค่คำถามเป็นตัวอักษรจีน — ตอบไม่ได้ และกลายเป็นข้ออ่านที่วัดคนละทักษะ

สาเหตุ: DrillQuestion ไม่มีช่อง audio_script จึงไม่ได้รับค่าจาก reading.build()
เทมเพลตเช็ก q.is_listening ซึ่งบน DrillQuestion เป็น undefined = เท็จเสมอ
หน้าฝึกฟัง (listen_practice) ใช้ ReadingView ตรงๆ จึงไม่พังตาม เลยไม่มีใครเห็น
"""
from django.test import TestCase

from core import drill, listen_explain
from core.models import (
    Question, QuestionOption, QuestionStatus, Section, SourceType,
)

SCRIPT = "女：你昨天怎么没来上课？\n男：我发烧了，在家休息。\n问：男的昨天为什么没来上课？"


def _listening_question(**kw):
    q = Question.objects.create(
        qtype="listening_mc", section=Section.LISTENING, status=QuestionStatus.ACTIVE,
        prompt_zh="男的昨天为什么没来上课？", answer_text="生病了",
        source_ref="H51001 ข้อ 1", source_type=SourceType.OFFICIAL_PAST_PAPER,
        audio_script=kw.pop("audio_script", SCRIPT), **kw,
    )
    for i, (text, ok) in enumerate([("生病了", True), ("起晚了", False),
                                    ("有事儿", False), ("忘了", False)]):
        QuestionOption.objects.create(question=q, text=text, is_correct=ok, order=i)
    return q


class DrillListeningTests(TestCase):
    def test_listening_question_carries_its_script(self):
        q = _listening_question()
        dq = drill.build_question({"kind": "question", "id": q.pk, "source": "due"}, 1, 40)
        self.assertTrue(dq.is_listening)
        self.assertEqual(dq.audio_script, SCRIPT)

    def test_reading_question_is_not_marked_as_listening(self):
        q = Question.objects.create(
            qtype="reading_mc", section=Section.READING, status=QuestionStatus.ACTIVE,
            prompt_zh="根据上文，可以知道：", answer_text="ถูก",
        )
        for i, (text, ok) in enumerate([("ถูก", True), ("ผิด", False)]):
            QuestionOption.objects.create(question=q, text=text, is_correct=ok, order=i)
        dq = drill.build_question({"kind": "question", "id": q.pk, "source": "due"}, 1, 40)
        self.assertFalse(dq.is_listening)

    def test_the_page_actually_renders_a_player(self):
        from django.template.loader import render_to_string
        q = _listening_question()
        dq = drill.build_question({"kind": "question", "id": q.pk, "source": "due"}, 1, 40)
        html = render_to_string("core/partials/question_body.html", {"q": dq})
        self.assertIn("listenPlayer", html)
        self.assertIn(f"listenPlayer({q.pk})", html)


class TranscriptFallbackTests(TestCase):
    """กล่อง 'บทที่ได้ยิน' ห้ามพูดสิ่งที่ไม่จริงเมื่อเราไม่มีข้อมูล

    เดิมถ้า lx ว่าง เทมเพลตตกไปเข้าข้อความ "ข้อนี้คำตอบไม่ได้ถูกพูดออกมาตรงๆ"
    ซึ่งเป็นการบอกผู้เรียนว่าข้อนี้ยากเป็นพิเศษ ทั้งที่ความจริงคือระบบไม่มีบท
    """

    def setUp(self):
        from django.template.loader import render_to_string
        self.render = render_to_string
        self.q = _listening_question()

    def test_shows_the_transcript_when_there_is_one(self):
        lx = listen_explain.explain(self.q)
        html = self.render("core/partials/listen_transcript.html",
                           {"question": self.q, "lx": lx})
        self.assertIn("我发烧了", html)

    def test_says_it_has_no_transcript_instead_of_blaming_the_question(self):
        html = self.render("core/partials/listen_transcript.html",
                           {"question": self.q, "lx": None})
        self.assertIn("ยังไม่มีบทถอดเสียง", html)
        self.assertNotIn("ไม่ได้ถูกพูดออกมาตรงๆ", html)
