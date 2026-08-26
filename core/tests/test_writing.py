"""เทสต์การตรวจข้อเรียงคำ — จุดที่ผิดแล้วผู้เรียนเสียกำลังใจโดยไม่มีเหตุ

ถ้าตรวจเข้มเกินไป (เช่นบังคับต้องมีจุดท้ายประโยค) ผู้เรียนที่เรียงถูก
จะถูกนับว่าผิด ซึ่งแย่กว่าปล่อยผ่านเพราะทำลายความเชื่อใจในระบบ
"""
from django.test import TestCase

from core import writing
from core.models import Question, QuestionStatus, Section, SourceType


class WordOrderCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.q = Question.objects.create(
            qtype="word_order", section=Section.WRITING, status=QuestionStatus.ACTIVE,
            prompt_zh="认真 / 我们 / 这个问题 / 对待 / 必须",
            answer_text="我们必须认真对待这个问题。",
            source_type=SourceType.HAND_WRITTEN,
        )
        cls.multi = Question.objects.create(
            qtype="word_order", section=Section.WRITING, status=QuestionStatus.ACTIVE,
            prompt_zh="他 / 去 / 偶尔 / 健身房",
            answer_text="他偶尔去健身房。/ 偶尔他去健身房。",
            source_type=SourceType.HAND_WRITTEN,
        )

    def test_exact_answer_is_correct(self):
        self.assertTrue(writing.check(self.q, self.q.answer_text)["is_correct"])

    def test_missing_final_period_still_correct(self):
        self.assertTrue(writing.check(self.q, "我们必须认真对待这个问题")["is_correct"])

    def test_extra_spaces_still_correct(self):
        self.assertTrue(writing.check(self.q, " 我们 必须 认真 对待 这个问题 ")["is_correct"])

    def test_wrong_order_is_wrong(self):
        self.assertFalse(writing.check(self.q, "这个问题我们对待必须认真")["is_correct"])

    def test_all_accepted_orders_pass(self):
        for answer in writing.accepted_answers(self.multi):
            self.assertTrue(writing.check(self.multi, answer)["is_correct"], answer)

    def test_other_answers_are_shown_after_checking(self):
        result = writing.check(self.multi, "他偶尔去健身房。")
        self.assertEqual(len(result["other_answers"]), 1)

    def test_words_are_split_from_prompt(self):
        self.assertEqual(writing.words_of(self.q),
                         ["认真", "我们", "这个问题", "对待", "必须"])

    def test_empty_answer_is_wrong_not_crash(self):
        self.assertFalse(writing.check(self.q, "")["is_correct"])

    def test_pick_avoids_recently_seen(self):
        picked = writing.pick_question(exclude_ids=[self.q.pk])
        self.assertEqual(picked.pk, self.multi.pk)

    def test_pick_recycles_when_all_seen(self):
        """ทำครบทุกข้อแล้วต้องวนใหม่ ไม่ใช่คืน None แล้วหน้าว่าง"""
        picked = writing.pick_question(exclude_ids=[self.q.pk, self.multi.pk])
        self.assertIsNotNone(picked)
