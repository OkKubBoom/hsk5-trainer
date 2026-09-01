"""เทสต์การวัดผลพาร์ทฟัง

จุดที่ผิดแล้วเจ็บที่สุด: แปลงชุด 5 ข้อเป็นคะแนนเต็ม 100
ตอบถูก 4 จาก 5 จะขึ้นว่า 80 คะแนน ซึ่งผู้เรียนจะเอาไปเชื่อว่าพร้อมสอบ
ทั้งที่เป็นความบังเอิญของชุดเล็ก — หนึ่งข้อคิดเป็น 20% ของผล
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import listen_mock
from core.accounts import create_learner
from core.models import (
    ErrorCode, ErrorLog, ListeningAttempt, MockExam, Question, QuestionOption,
    QuestionStatus, QuestionType, Section, VocabItem,
)


def make_questions(n: int):
    made = []
    for i in range(n):
        q = Question.objects.create(
            qtype=QuestionType.LISTENING_MC, section=Section.LISTENING,
            status=QuestionStatus.ACTIVE, prompt_zh=f"คำถาม {i}",
            answer_text=f"ถูก{i}", audio_script=f"บทที่ {i}。คำถาม {i}",
            source_ref=f"T ข้อ {i}")
        for j, text in enumerate([f"ถูก{i}", f"ผิดก{i}", f"ผิดข{i}", f"ผิดค{i}"]):
            QuestionOption.objects.create(question=q, text=text, is_correct=(j == 0), order=j)
        made.append(q)
    return made


class StartTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="詞", pinyin="ci", meaning_th="ความหมาย", hsk_level=5)
        cls.learner, _ = create_learner(
            username="m", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60))
        cls.questions = make_questions(12)

    def test_เวลาคิดจากอัตราเดียวกับข้อสอบจริง(self):
        """45 ข้อ 30 นาที = 40 วินาทีต่อข้อ ชุดสั้นต้องใช้อัตราเดียวกัน
        ไม่งั้นชุดสั้นจะง่ายกว่าจริงและตัวเลขที่ได้จะสูงหลอก
        """
        exam = listen_mock.start(self.learner, 5)
        self.assertEqual(exam.time_limit_minutes, 3)

    def test_คลังไม่พอต้องคืน_none_ไม่ใช่สร้างชุดสั้นกว่าที่ขอ(self):
        """ชุดที่สั้นกว่าที่บอกไว้ทำให้ตัวเลขเทียบกันไม่ได้ระหว่างครั้ง"""
        self.assertIsNone(listen_mock.start(self.learner, 45))

    def test_มีชุดค้างอยู่ต้องทำต่อ_ไม่สร้างใหม่(self):
        first = listen_mock.start(self.learner, 5)
        self.assertEqual(listen_mock.start(self.learner, 10).pk, first.pk)

    def test_เลี่ยงข้อที่เพิ่งเจอ(self):
        """เจอชุดเดิมซ้ำแล้วคะแนนสูงขึ้นเพราะจำได้ ไม่ใช่เพราะเก่งขึ้น"""
        first = listen_mock.start(self.learner, 5)
        listen_mock.submit(first)
        second = listen_mock.start(self.learner, 5)
        self.assertFalse(set(first.queue) & set(second.queue))


class FlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="詞", pinyin="ci", meaning_th="ความหมาย", hsk_level=5)
        cls.learner, _ = create_learner(
            username="n", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60))
        make_questions(6)

    def setUp(self):
        self.client.login(username="n", password="passpass1")

    def start(self, count=5):
        self.client.post(reverse("listen_test_start"), {"count": count})
        return MockExam.objects.get(learner=self.learner, section=Section.LISTENING)

    def answer_all(self, exam, correct=True):
        for qid in exam.queue:
            q = Question.objects.get(pk=qid)
            opt = q.options.filter(is_correct=correct).first()
            self.client.post(reverse("listen_test_answer", args=[exam.pk]),
                             {"question_id": qid, "given": opt.text})

    def test_ตอบครบแล้วปิดชุดและคิดคะแนนให้เอง(self):
        exam = self.start()
        self.answer_all(exam)
        exam.refresh_from_db()

        self.assertIsNotNone(exam.finished_at)
        self.assertEqual(exam.correct_count, 5)
        self.assertEqual(exam.listening, 100)

    def test_ตอบแล้วย้อนกลับไปแก้ไม่ได้(self):
        """เหมือนห้องสอบจริง — ถ้าแก้ได้ ตัวเลขจะไม่ใช่ความสามารถจริง"""
        exam = self.start()
        first_id = exam.queue[0]
        wrong = Question.objects.get(pk=first_id).options.filter(is_correct=False).first()
        right = Question.objects.get(pk=first_id).options.filter(is_correct=True).first()

        self.client.post(reverse("listen_test_answer", args=[exam.pk]),
                         {"question_id": first_id, "given": wrong.text})
        self.client.post(reverse("listen_test_answer", args=[exam.pk]),
                         {"question_id": first_id, "given": right.text})

        exam.refresh_from_db()
        self.assertEqual(exam.answers[str(first_id)], wrong.text)

    def test_บันทึกลงประวัติฝึกฟังด้วย_plays_เท่ากับหนึ่ง(self):
        """ชุดนี้ฟังได้ครั้งเดียวจริง ตัวเลข 'ถูกตั้งแต่ฟังรอบเดียว' จึงรวมผลนี้ได้"""
        exam = self.start()
        self.answer_all(exam)

        rows = ListeningAttempt.objects.filter(learner=self.learner)
        self.assertEqual(rows.count(), 5)
        self.assertTrue(all(r.plays == 1 for r in rows))

    def test_ไม่ได้ตอบไม่ถูกนับว่าฟังไม่ออก(self):
        """หมดเวลาแล้วยังไม่ได้ตอบ ไม่ใช่ 'ตอบผิด' — ติดป้าย SOUND ให้จะสอนผิด"""
        exam = self.start()
        listen_mock.submit(exam, auto=True)
        self.assertFalse(ErrorLog.objects.filter(code=ErrorCode.SOUND).exists())

    def test_ตอบผิดติดป้ายสาเหตุ_sound(self):
        exam = self.start()
        self.answer_all(exam, correct=False)
        self.assertEqual(ErrorLog.objects.filter(code=ErrorCode.SOUND).count(), 5)

    def test_หมดเวลาแล้วเปิดหน้าทำต่อไม่ได้(self):
        exam = self.start()
        MockExam.objects.filter(pk=exam.pk).update(
            started_at=timezone.now() - timedelta(minutes=99))

        res = self.client.get(reverse("listen_test_run", args=[exam.pk]), follow=True)
        exam.refresh_from_db()
        self.assertIsNotNone(exam.finished_at)
        self.assertTrue(exam.auto_submitted)
        self.assertEqual(res.status_code, 200)

    def test_ชุดสั้นไม่ถูกแปลงเป็นคะแนนเต็มร้อยบนหน้าจอ(self):
        exam = self.start()
        self.answer_all(exam)
        res = self.client.get(reverse("listen_test_result", args=[exam.pk]))

        self.assertFalse(res.context["is_measure"])
        self.assertContains(res, "เป็นการซ้อม ไม่ใช่การวัด")

    def test_ชุดสั้นไม่ถูกนับในประวัติคะแนน(self):
        """ถ้าเอาชุด 5 ข้อมาปนในแนวโน้ม เส้นจะเด้งจนอ่านไม่ได้"""
        exam = self.start()
        self.answer_all(exam)
        self.assertEqual(listen_mock.history(self.learner)["full_times"], 0)
        self.assertIsNone(listen_mock.history(self.learner)["latest"])

    def test_ดูผลของคนอื่นไม่ได้(self):
        exam = self.start()
        other, _ = create_learner(
            username="z", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60))
        self.client.login(username="z", password="passpass1")
        res = self.client.get(reverse("listen_test_result", args=[exam.pk]))
        self.assertEqual(res.status_code, 404)
