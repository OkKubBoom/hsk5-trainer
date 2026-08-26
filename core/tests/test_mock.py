"""เทสต์ข้อสอบจำลอง — จุดที่ผิดแล้วคะแนนโกหกตัวเอง

สองเรื่องสำคัญ: ชุดต้องเปลี่ยนทุกครั้ง (ไม่งั้นคะแนนขึ้นเพราะจำได้ ไม่ใช่เก่งขึ้น)
และหมดเวลาต้องส่งอัตโนมัติ (ไม่งั้นค้างไว้แล้วมาทำต่อวันหลังได้)
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core import mock
from core.accounts import create_learner
from core.models import (
    ItemGroup, MockExam, Question, QuestionOption, QuestionStatus,
    Section, SourceType, VocabItem,
)


def make_question(i, qtype, group=None):
    q = Question.objects.create(
        qtype=qtype, section=Section.READING, status=QuestionStatus.ACTIVE,
        prompt_zh=f"โจทย์ {i}", answer_text="ถูก", group=group,
        source_type=SourceType.HAND_WRITTEN,
    )
    QuestionOption.objects.create(question=q, text="ถูก", is_correct=True, order=0)
    for j in range(3):
        QuestionOption.objects.create(question=q, text=f"ผิด{i}-{j}", is_correct=False, order=j + 1)
    return q


class MockExamTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="字", pinyin="zi", meaning_th="ตัวอักษร", hsk_level=5)
        group = ItemGroup.objects.create(kind="reading_passage", section=Section.READING,
                                         passage_zh="บทอ่าน", source_type=SourceType.HAND_WRITTEN)
        for i in range(40):
            make_question(i, "synonym_cloze")
        for i in range(40):
            make_question(100 + i, "reading_mc")
        for i in range(60):
            make_question(200 + i, "reading_mc", group=group)
        cls.learner, _ = create_learner(username="kid", password="passpass1",
                                        exam_date=timezone.localdate() + timedelta(days=60))

    def test_set_follows_real_exam_blueprint(self):
        exam = mock.start(self.learner)
        self.assertEqual(exam.question_count, 45)
        kinds = {}
        for q in Question.objects.filter(pk__in=exam.queue):
            key = q.qtype if q.qtype != "reading_mc" else ("part3" if q.group_id else "part2")
            kinds[key] = kinds.get(key, 0) + 1
        self.assertEqual(kinds, {"synonym_cloze": 15, "part2": 10, "part3": 20})

    def test_second_exam_avoids_previous_questions(self):
        first = mock.start(self.learner)
        mock.grade(first)
        second = mock.start(self.learner)
        overlap = set(first.queue) & set(second.queue)
        self.assertEqual(overlap, set(), "ชุดที่สองต้องไม่ซ้ำกับชุดแรก ไม่งั้นคะแนนขึ้นเพราะจำได้")

    def test_starting_twice_resumes_instead_of_creating(self):
        first = mock.start(self.learner)
        again = mock.start(self.learner)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(MockExam.objects.filter(learner=self.learner).count(), 1)

    def test_answers_are_saved_for_resume(self):
        exam = mock.start(self.learner)
        mock.save_answer(exam, exam.queue[0], "ถูก")
        reloaded = MockExam.objects.get(pk=exam.pk)
        self.assertEqual(reloaded.answers[str(exam.queue[0])], "ถูก")

    def test_flag_toggles(self):
        exam = mock.start(self.learner)
        qid = exam.queue[0]
        self.assertTrue(mock.toggle_flag(exam, qid))
        self.assertFalse(mock.toggle_flag(exam, qid))
        self.assertEqual(exam.flagged, [])

    def test_grading_counts_only_exact_matches(self):
        exam = mock.start(self.learner)
        for qid in exam.queue[:10]:
            mock.save_answer(exam, qid, "ถูก")
        for qid in exam.queue[10:15]:
            mock.save_answer(exam, qid, "ผิดแน่ๆ")
        mock.grade(exam)
        self.assertEqual(exam.correct_count, 10)
        self.assertEqual(exam.reading, round(10 / 45 * 100))

    def test_unanswered_counts_as_wrong(self):
        exam = mock.start(self.learner)
        mock.save_answer(exam, exam.queue[0], "ถูก")
        mock.grade(exam)
        self.assertEqual(exam.correct_count, 1)

    def test_expired_exam_is_detected(self):
        exam = mock.start(self.learner)
        MockExam.objects.filter(pk=exam.pk).update(
            started_at=timezone.now() - timedelta(minutes=mock.READING_MINUTES + 1))
        exam.refresh_from_db()
        self.assertTrue(exam.is_expired)
        self.assertEqual(exam.seconds_left, 0)

    def test_stats_track_attempt_count_and_trend(self):
        first = mock.start(self.learner)
        for qid in first.queue[:20]:
            mock.save_answer(first, qid, "ถูก")
        mock.grade(first)

        second = mock.start(self.learner)
        for qid in second.queue[:30]:
            mock.save_answer(second, qid, "ถูก")
        mock.grade(second)

        stats = mock.stats(self.learner)
        self.assertEqual(stats["times"], 2)
        self.assertEqual(stats["best"], round(30 / 45 * 100))
        self.assertGreater(stats["trend"], 0, "ทำได้ดีขึ้นต้องเห็นเป็นบวก")

    def test_wrong_answers_go_to_error_log(self):
        from core.models import ErrorLog
        exam = mock.start(self.learner)
        mock.save_answer(exam, exam.queue[0], "ผิดแน่ๆ")
        mock.grade(exam)
        self.assertTrue(ErrorLog.objects.filter(learner=self.learner).exists(),
                        "ข้อที่ผิดต้องไหลเข้าชุดฝึกวันถัดไป")
