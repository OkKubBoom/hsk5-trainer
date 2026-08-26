"""เทสต์กฎ 'หนึ่งวันหนึ่งชุด' และการทำต่อจากที่ค้าง

กฎนี้ผิดแล้วเงียบ — ถ้าสร้างชุดที่สองได้ ความแม่นจะถูกเฉลี่ยข้ามชุด
จำนวนวันที่ทำติดกันนับผิด และการ์ดถูกทบทวนถี่เกินจริงโดยไม่มีอะไรเตือน
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core import drill
from core.models import (
    Card, CardType, DrillSession, LearnerProfile, Role, User, VocabItem,
)


class DrillFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for i in range(60):
            VocabItem.objects.create(
                hanzi=f"字{i}", pinyin=f"zi{i}", meaning_th=f"ความหมาย{i}",
                hsk_level=5, frequency_rank=i,
            )
        user = User.objects.create_user("nong", password="x", role=Role.LEARNER)
        cls.learner = LearnerProfile.objects.create(
            user=user, target_exam_date=timezone.localdate() + timedelta(days=90),
        )
        for v in VocabItem.objects.all():
            Card.objects.create(learner=cls.learner, vocab=v, card_type=CardType.RECOGNIZE)

    def test_second_start_returns_same_session(self):
        first, created_1 = drill.start_or_resume(self.learner)
        second, created_2 = drill.start_or_resume(self.learner)
        self.assertTrue(created_1)
        self.assertFalse(created_2, "วันเดียวกันต้องไม่สร้างชุดใหม่")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(DrillSession.objects.filter(learner=self.learner).count(), 1)

    def test_finished_session_is_not_restarted(self):
        session, _ = drill.start_or_resume(self.learner)
        drill.finish(session)
        again, created = drill.start_or_resume(self.learner)
        self.assertFalse(created)
        self.assertEqual(again.pk, session.pk)
        self.assertTrue(again.is_finished)

    def test_position_survives_without_browser_session(self):
        """ปิดเบราว์เซอร์แล้วกลับมา ต้องได้ข้อเดิม ไม่ใช่เริ่มใหม่"""
        session, _ = drill.start_or_resume(self.learner)
        first_entry = drill.current_entry(session)
        drill.advance(session)

        reloaded = drill.today_session(self.learner)
        self.assertEqual(reloaded.position, 1)
        self.assertNotEqual(drill.current_entry(reloaded), first_entry)

    def test_queue_is_stored_and_stable(self):
        session, _ = drill.start_or_resume(self.learner)
        self.assertTrue(session.queue, "คิวต้องถูกเก็บลงฐานข้อมูล")
        snapshot = list(session.queue)
        again, _ = drill.start_or_resume(self.learner)
        self.assertEqual(again.queue, snapshot, "เรียกซ้ำต้องไม่สลับคิว")

    def test_advance_never_passes_end_of_queue(self):
        session, _ = drill.start_or_resume(self.learner)
        for _ in range(len(session.queue) + 5):
            drill.advance(session)
        self.assertEqual(session.position, len(session.queue))
        self.assertIsNone(drill.current_entry(session))

    def test_new_day_gets_a_new_session(self):
        session, _ = drill.start_or_resume(self.learner)
        DrillSession.objects.filter(pk=session.pk).update(
            started_at=timezone.now() - timedelta(days=1)
        )
        fresh, created = drill.start_or_resume(self.learner)
        self.assertTrue(created, "วันใหม่ต้องได้ชุดใหม่")
        self.assertNotEqual(fresh.pk, session.pk)

    def test_answer_updates_counters_and_position(self):
        session, _ = drill.start_or_resume(self.learner)
        entry = drill.current_entry(session)
        question = drill.build_question(entry, 1, len(session.queue))
        drill.submit(session, entry, given=question.answer,
                     correct_answer=question.answer, elapsed_ms=1500)
        drill.advance(session)
        session.refresh_from_db()
        self.assertEqual(session.answered, 1)
        self.assertEqual(session.correct, 1)
        self.assertEqual(session.position, 1)
