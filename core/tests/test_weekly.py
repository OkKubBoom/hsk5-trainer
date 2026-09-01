"""เทสต์สรุปรายสัปดาห์

จุดที่ผิดแล้วเจ็บที่สุด: ตัวเลขที่อ่านผิดความหมาย
"ตอบ 2 ข้อ · แม่น 0%" ทั้งที่ตอบถูกทั้งสองข้อ ทำให้เจ้าของระบบเข้าใจผิด
แล้วไปคุยกับน้องด้วยข้อมูลที่ผิด ซึ่งแย่กว่าไม่มีหน้านี้เลย
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import weekly
from core.accounts import create_learner
from core.models import (
    ErrorCode, ErrorLog, ListeningAttempt, Question, QuestionStatus, QuestionType,
    Role, Section, User, VocabItem, WordOrderAttempt,
)


class SummaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="詞", pinyin="ci", meaning_th="ความหมาย", hsk_level=5)
        cls.learner, _ = create_learner(
            username="w", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60))
        cls.question = Question.objects.create(
            qtype=QuestionType.LISTENING_MC, section=Section.LISTENING,
            status=QuestionStatus.ACTIVE, prompt_zh="?", answer_text="ก",
            audio_script="บท")

    def test_ยังไม่ได้ทำอะไรต้องไม่ระเบิดและไม่แต่งตัวเลข(self):
        s = weekly.summary(self.learner)
        self.assertEqual(s["counts"]["days"], 0)
        self.assertIsNone(s["counts"]["accuracy"])
        self.assertIn("ยังไม่ได้แตะระบบ", s["advice"][0])

    def test_ความแม่นนับรวมทุกอย่างที่นับเป็นข้อที่ตอบ(self):
        """ถ้านับคนละฐาน จะขึ้นว่า 'ตอบ 2 ข้อ · แม่น 0%' ทั้งที่ถูกทั้งสองข้อ"""
        for correct in (True, True):
            ListeningAttempt.objects.create(
                learner=self.learner, question=self.question, is_correct=correct, plays=1)

        s = weekly.summary(self.learner)
        self.assertEqual(s["counts"]["answered"], 2)
        self.assertEqual(s["counts"]["accuracy"], 100)

    def test_นับวันที่ทำจากทุกชนิดกิจกรรม(self):
        """วันที่ฝึกฟังอย่างเดียวก็คือวันที่ได้ทำ ไม่ใช่วันที่หายไป"""
        ListeningAttempt.objects.create(
            learner=self.learner, question=self.question, is_correct=True)
        WordOrderAttempt.objects.create(
            learner=self.learner, question=self.question, is_correct=True)
        self.assertEqual(weekly.summary(self.learner)["counts"]["days"], 1)

    def test_แยกสาเหตุที่ผิดตาม_d8(self):
        ErrorLog.record(self.learner, ErrorCode.SOUND, label="x",
                        section=Section.LISTENING, question=self.question)
        s = weekly.summary(self.learner)
        self.assertEqual(s["causes"][0]["code"], ErrorCode.SOUND)
        self.assertEqual(s["causes"][0]["percent"], 100)

    def test_ข้อเสนอต้องอ้างสาเหตุที่พบจริง(self):
        """คำแนะนำที่ไม่มีตัวเลขรองรับเอาไปตัดสินใจอะไรไม่ได้"""
        ListeningAttempt.objects.create(
            learner=self.learner, question=self.question, is_correct=False)
        ErrorLog.record(self.learner, ErrorCode.SOUND, label="x",
                        section=Section.LISTENING, question=self.question)
        advice = " ".join(weekly.summary(self.learner)["advice"])
        self.assertIn("ฝึกฟัง", advice)

    def test_เทียบกับสัปดาห์ก่อนหน้าไม่ใช่แสดงตัวเลขเดี่ยว(self):
        old = timezone.now() - timedelta(days=9)
        a = ListeningAttempt.objects.create(
            learner=self.learner, question=self.question, is_correct=True)
        ListeningAttempt.objects.filter(pk=a.pk).update(created_at=old)

        s = weekly.summary(self.learner)
        self.assertEqual(s["prev"]["answered"], 1)
        self.assertEqual(s["compare"]["answered"]["direction"], "down")


class PageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="詞", pinyin="ci", meaning_th="ความหมาย", hsk_level=5)
        cls.learner, _ = create_learner(
            username="a", password="passpass1", display_name="เอ",
            exam_date=timezone.localdate() + timedelta(days=60))
        cls.other, _ = create_learner(
            username="b", password="passpass1", display_name="บี",
            exam_date=timezone.localdate() + timedelta(days=60))
        cls.admin = User.objects.create_user(
            username="owner", password="passpass1", role=Role.ADMIN)

    def test_ผู้เรียนเห็นของตัวเองและเลือกคนอื่นไม่ได้(self):
        """ตั้งใจไม่ให้เทียบกันเอง — เหตุผลอยู่ในหัวไฟล์ core/progress.py"""
        self.client.login(username="a", password="passpass1")
        res = self.client.get(reverse("weekly"), {"learner": self.other.pk})
        self.assertEqual(res.context["s"]["learner"], self.learner)
        self.assertEqual(res.context["pickable"], [])

    def test_เจ้าของระบบเลือกดูของแต่ละคนได้(self):
        self.client.login(username="owner", password="passpass1")
        res = self.client.get(reverse("weekly"), {"learner": self.other.pk})
        self.assertEqual(res.context["s"]["learner"], self.other)
        self.assertEqual(len(res.context["pickable"]), 2)

    def test_เจ้าของระบบที่ไม่มีโปรไฟล์เปิดหน้าได้ไม่พัง(self):
        """บัญชีผู้ดูแลไม่มี LearnerProfile — เคยทำทุกหน้าพัง 500 มาแล้ว"""
        self.client.login(username="owner", password="passpass1")
        res = self.client.get(reverse("weekly"))
        self.assertEqual(res.status_code, 200)

    def test_ความแม่นที่ยังไม่มีข้อมูลขึ้นขีดไม่ใช่ศูนย์(self):
        self.client.login(username="a", password="passpass1")
        res = self.client.get(reverse("weekly"))
        acc = next(c for c in res.context["cards"] if c["label"] == "ความแม่น")
        self.assertEqual(acc["now"], "—")
