"""เทสต์ทางที่ให้คนแย้งคำอธิบายของ AI

นี่คือกติกาข้อ D8 ของโปรเจกต์ — ห้ามเชื่อเฉลยที่ AI สร้างโดยไม่มีทางให้ผู้ใช้กดว่าผิด
ถ้าทางนี้พังเงียบๆ ระบบจะกลายเป็นแหล่งข้อมูลผิดที่ไม่มีใครแก้ได้
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import (
    ExplanationNote, LearnerProfile, NoteStatus, NoteVerdict, Question,
    QuestionStatus, Role, Section, SourceType, User,
)


class ExplanationNoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.learner_user = User.objects.create_user("kid", password="passpass1", role=Role.LEARNER)
        LearnerProfile.objects.create(user=cls.learner_user,
                                      target_exam_date=timezone.localdate() + timedelta(days=60))
        cls.admin = User.objects.create_user("boss", password="passpass1", role=Role.ADMIN)
        cls.q = Question.objects.create(
            qtype="word_order", section=Section.WRITING, status=QuestionStatus.ACTIVE,
            prompt_zh="他 / 去 / 偶尔", answer_text="他偶尔去。",
            source_type=SourceType.HAND_WRITTEN,
            explanation={"why_correct": "คำอธิบายของ AI", "source": "ai_generated"},
        )

    def _login_learner(self):
        self.client.login(username="kid", password="passpass1")

    def test_learner_can_report_wrong_explanation(self):
        self._login_learner()
        response = self.client.post(f"/explanation/{self.q.pk}/note/", {"verdict": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExplanationNote.objects.count(), 1)

    def test_reporting_marks_explanation_disputed(self):
        """คนอื่นที่เจอข้อนี้ต้องเห็นว่ามีคนแย้งไว้แล้ว"""
        self._login_learner()
        self.client.post(f"/explanation/{self.q.pk}/note/", {"verdict": "wrong"})
        self.q.refresh_from_db()
        self.assertTrue(self.q.explanation.get("disputed"))

    def test_body_upgrades_verdict_to_corrected(self):
        """ส่งคำอธิบายที่ถูกมาด้วย = ไม่ใช่แค่แจ้งว่าผิด"""
        self._login_learner()
        self.client.post(f"/explanation/{self.q.pk}/note/",
                         {"verdict": "wrong", "body": "ที่ถูกคือแบบนี้", "source": "ครูที่สอน"})
        note = ExplanationNote.objects.get()
        self.assertEqual(note.verdict, NoteVerdict.CORRECTED)
        self.assertEqual(note.source, "ครูที่สอน")

    def test_confirming_does_not_mark_disputed(self):
        self._login_learner()
        self.client.post(f"/explanation/{self.q.pk}/note/", {"verdict": "confirmed"})
        self.q.refresh_from_db()
        self.assertFalse(self.q.explanation.get("disputed"))

    def test_anonymous_cannot_post_note(self):
        response = self.client.post(f"/explanation/{self.q.pk}/note/", {"verdict": "wrong"})
        self.assertEqual(ExplanationNote.objects.count(), 0)
        self.assertIn(response.status_code, (302, 403))

    def test_learner_cannot_open_review_page(self):
        self._login_learner()
        self.assertEqual(self.client.get("/explanation/review/").status_code, 403)

    def test_admin_accepts_note_and_marks_verified(self):
        self._login_learner()
        self.client.post(f"/explanation/{self.q.pk}/note/",
                         {"verdict": "wrong", "body": "คำอธิบายที่ถูกจากครู"})
        note = ExplanationNote.objects.get()

        self.client.login(username="boss", password="passpass1")
        self.client.post("/explanation/review/", {"note_id": note.pk, "action": "accept"})

        note.refresh_from_db()
        self.q.refresh_from_db()
        self.assertEqual(note.status, NoteStatus.ACCEPTED)
        self.assertTrue(self.q.explanation.get("human_verified"))
        self.assertFalse(self.q.explanation.get("disputed"), "รับแล้วต้องเลิกขึ้นป้ายว่าถูกแย้ง")

    def test_rejected_note_leaves_explanation_disputed(self):
        self._login_learner()
        self.client.post(f"/explanation/{self.q.pk}/note/", {"verdict": "wrong"})
        note = ExplanationNote.objects.get()

        self.client.login(username="boss", password="passpass1")
        self.client.post("/explanation/review/", {"note_id": note.pk, "action": "reject"})

        note.refresh_from_db()
        self.q.refresh_from_db()
        self.assertEqual(note.status, NoteStatus.REJECTED)
        self.assertTrue(self.q.explanation.get("disputed"))

    def test_note_without_body_cannot_be_accepted(self):
        """ไม่มีเนื้อหาก็เอามาแทนของ AI ไม่ได้ — กันการรับของว่าง"""
        self._login_learner()
        self.client.post(f"/explanation/{self.q.pk}/note/", {"verdict": "wrong"})
        note = ExplanationNote.objects.get()

        self.client.login(username="boss", password="passpass1")
        self.client.post("/explanation/review/", {"note_id": note.pk, "action": "accept"})

        note.refresh_from_db()
        self.assertNotEqual(note.status, NoteStatus.ACCEPTED)
