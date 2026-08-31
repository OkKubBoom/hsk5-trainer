"""เทสต์การติดป้ายสาเหตุการตอบผิด — D8 ใน CLAUDE.md

D8 บอกว่านี่คือเหตุผลเดียวที่ระบบนี้ควรมีอยู่ แต่ก่อนหน้านี้ป้ายถูกฮาร์ดโค้ดไว้
ข้อคำศัพท์ได้ VOCAB เสมอ ข้ออื่นได้ MEANING เสมอ รหัสที่เหลือไม่เคยถูกใช้เลย
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import diagnose
from core import drill as drill_engine
from core.accounts import create_learner
from core.models import (
    Card, ErrorCode, ErrorLog, Question, QuestionOption, QuestionStatus,
    Section, SourceType, VocabItem,
)


def make_question(qtype="reading_mc", section=Section.READING, **kw):
    q = Question.objects.create(
        qtype=qtype, section=section, status=QuestionStatus.ACTIVE,
        prompt_zh="โจทย์", answer_text="ถูก", source_type=SourceType.HAND_WRITTEN, **kw,
    )
    QuestionOption.objects.create(question=q, text="ถูก", is_correct=True, order=0)
    QuestionOption.objects.create(question=q, text="ผิด", is_correct=False, order=1)
    return q


class CodePickerTests(TestCase):
    def test_ข้อเรียงคำได้รหัสโครงสร้างไม่ใช่ความหมาย(self):
        """ผู้เรียนที่รู้ศัพท์ครบแต่เรียงผิด ต้องไปทบทวนไวยากรณ์ ไม่ใช่ท่องคำเพิ่ม"""
        q = make_question("word_order", Section.WRITING)
        self.assertEqual(diagnose.code_for(question=q), ErrorCode.STRUCTURE)

    def test_ชนิดโจทย์มาก่อนเวลา(self):
        """ข้อเรียงคำที่ตอบช้าก็ยังเป็นปัญหาลำดับคำ ไม่ใช่ปัญหาความเร็ว"""
        q = make_question("word_order", Section.WRITING)
        self.assertEqual(
            diagnose.code_for(question=q, elapsed_ms=99_000), ErrorCode.STRUCTURE)

    def test_ตอบช้าได้รหัสไม่ทันเวลา(self):
        q = make_question()
        self.assertEqual(
            diagnose.code_for(question=q, elapsed_ms=diagnose.SLOW_MS + 1),
            ErrorCode.TOO_SLOW,
        )

    def test_ข้อฟังได้รหัสเสียง(self):
        q = make_question("listening_mc", Section.LISTENING)
        self.assertEqual(diagnose.code_for(question=q), ErrorCode.SOUND)

    def test_ข้อเติมคำใกล้เคียงนับเป็นปัญหาคำศัพท์(self):
        """阅读第一部分 วัดการแยกคำใกล้เคียงโดยตรง"""
        q = make_question("synonym_cloze")
        self.assertEqual(diagnose.code_for(question=q), ErrorCode.VOCAB)


class DrillIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="字", pinyin="zi", meaning_th="ตัวอักษร", hsk_level=5)
        cls.learner, _ = create_learner(
            username="kid", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60),
        )

    def run_question(self, question, given, elapsed_ms=0):
        session, _ = drill_engine.start_or_resume(self.learner)
        entry = {"kind": "question", "id": question.pk, "source": "due"}
        return drill_engine.submit(
            session, entry, given=given, correct_answer="ถูก", elapsed_ms=elapsed_ms)

    def test_ตอบผิดช้าได้รหัสไม่ทันเวลาไม่ใช่ความหมาย(self):
        """รหัสนี้ไม่เคยถูกเขียนลงฐานเลยก่อนหน้านี้"""
        q = make_question()
        self.run_question(q, "ผิด", elapsed_ms=40_000)
        self.assertEqual(
            ErrorLog.objects.get(learner=self.learner, question=q).code,
            ErrorCode.TOO_SLOW,
        )

    def test_ตอบถูกแล้วบันทึกข้อผิดของข้อสอบต้องถูกปิด(self):
        """เดิมปิดเฉพาะข้อคำศัพท์ ข้อสอบจึงค้างในคิว 30% ตลอดกาล"""
        q = make_question()
        self.run_question(q, "ผิด")
        self.assertTrue(ErrorLog.objects.filter(
            learner=self.learner, question=q, resolved_at__isnull=True).exists())

        self.run_question(q, "ถูก")
        self.assertFalse(ErrorLog.objects.filter(
            learner=self.learner, question=q, resolved_at__isnull=True).exists())

    def test_ตอบถูกแล้วบันทึกข้อผิดของคำศัพท์ยังถูกปิดเหมือนเดิม(self):
        card = Card.objects.filter(learner=self.learner).first()
        session, _ = drill_engine.start_or_resume(self.learner)
        entry = {"kind": "vocab", "id": card.pk, "source": "due"}

        drill_engine.submit(session, entry, given="มั่ว", correct_answer=card.vocab.meaning_th)
        self.assertTrue(ErrorLog.objects.filter(
            learner=self.learner, vocab=card.vocab, resolved_at__isnull=True).exists())

        drill_engine.submit(session, entry, given=card.vocab.meaning_th,
                            correct_answer=card.vocab.meaning_th)
        self.assertFalse(ErrorLog.objects.filter(
            learner=self.learner, vocab=card.vocab, resolved_at__isnull=True).exists())


class SelfReportTests(TestCase):
    """ผู้เรียนกดบอกสาเหตุเอง — เชื่อถือได้กว่าที่ระบบเดา"""

    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="字", pinyin="zi", meaning_th="ตัวอักษร", hsk_level=5)
        cls.learner, _ = create_learner(
            username="kid", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60),
        )

    def setUp(self):
        self.client.login(username="kid", password="passpass1")
        self.log = ErrorLog.record(
            self.learner, ErrorCode.MEANING, "字", section=Section.VOCAB)

    def test_กดแล้วทับค่าที่ระบบเดาไว้(self):
        res = self.client.post(
            reverse("error_reason", args=[self.log.pk]), {"code": ErrorCode.TOO_SLOW})
        self.assertEqual(res.status_code, 200)
        self.log.refresh_from_db()
        self.assertEqual(self.log.code, ErrorCode.TOO_SLOW)

    def test_รหัสที่ไม่รู้จักไม่เปลี่ยนอะไร(self):
        self.client.post(reverse("error_reason", args=[self.log.pk]), {"code": "ไม่มีจริง"})
        self.log.refresh_from_db()
        self.assertEqual(self.log.code, ErrorCode.MEANING)

    def test_แก้บันทึกของคนอื่นไม่ได้(self):
        other, _ = create_learner(
            username="other", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60))
        theirs = ErrorLog.record(other, ErrorCode.MEANING, "字", section=Section.VOCAB)

        res = self.client.post(
            reverse("error_reason", args=[theirs.pk]), {"code": ErrorCode.TOO_SLOW})
        self.assertEqual(res.status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.code, ErrorCode.MEANING)
