"""เทสต์รายการคำศัพท์ให้ครูตรวจ

จุดที่ผิดแล้วเจ็บที่สุด: เรียงลำดับผิด
ถ้าดัน 很 是 不 ขึ้นมาก่อน ครูจะเสียเวลา 20 นาทีแรกกับคำที่ไม่มีทางแปลผิด
แล้วเลิก — และคำที่เสี่ยงจริงจะไม่มีใครดูเลย
"""
from django.test import TestCase
from django.urls import reverse

from core import vocab_review
from core.models import ExplanationNote, NoteVerdict, Role, User, VocabItem


def word(hanzi, **kw):
    base = {"pinyin": "x", "meaning_th": f"ความหมาย {hanzi}", "hsk_level": 5, "tags": []}
    base.update(kw)
    return VocabItem.objects.create(hanzi=hanzi, **base)


class QueueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # คำง่ายที่ออกทุกชุด — ห้ามขึ้นก่อน
        word("很", hsk_level=1, exam_papers_count=9, exam_as_answer=27,
             tags=["needs_review"])
        # คำเสี่ยงที่ด่านคุณภาพตีตก — ต้องขึ้นก่อน
        word("过敏", hsk_level=5, exam_papers_count=2, exam_as_answer=4,
             tags=["review:error", "needs_review"])
        word("方案", hsk_level=5, exam_papers_count=1, tags=["review:warn"])
        word("ยืนยันแล้ว", tags=["needs_review", "human_verified"])

    def test_คำเสี่ยงขึ้นก่อนคำที่ออกบ่อยแต่ไม่มีทางผิด(self):
        first = vocab_review.queue()[0]
        self.assertEqual(first.hanzi, "过敏")

    def test_คำที่ยืนยันแล้วต้องไม่กลับมาอยู่ในคิว(self):
        hanzi = [v.hanzi for v in vocab_review.queue()]
        self.assertNotIn("ยืนยันแล้ว", hanzi)

    def test_กรองตามกลุ่มได้(self):
        only = [v.hanzi for v in vocab_review.queue("error")]
        self.assertEqual(only, ["过敏"])

    def test_ป้าย_review_error_กับ_review_warn_ต้องไม่ชนกัน(self):
        """ทั้งสองขึ้นต้นด้วย review: — ถ้าค้นด้วย substring ธรรมดาจะปนกัน"""
        warn = [v.hanzi for v in vocab_review.queue("warn")]
        self.assertIn("方案", warn)
        self.assertNotIn("过敏", warn)

    def test_นับความคืบหน้าเป็นคำที่ยืนยันแล้ว(self):
        c = vocab_review.counts()
        self.assertEqual(c["verified"], 1)
        self.assertEqual(c["pending"], 3)

    def test_บอกได้ว่าคำนี้ถูกหยิบมาเพราะอะไร(self):
        v = VocabItem.objects.get(hanzi="过敏")
        self.assertIn("ด่านคุณภาพไม่ผ่าน", vocab_review.flags_of(v))


class PageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vocab = word("过敏", tags=["review:error", "needs_review"])
        cls.admin = User.objects.create_user(
            username="owner", password="passpass1", role=Role.ADMIN)
        cls.plain = User.objects.create_user(username="kid", password="passpass1")

    def test_คนทั่วไปเปิดไม่ได้(self):
        self.client.login(username="kid", password="passpass1")
        self.assertEqual(self.client.get(reverse("vocab_teacher")).status_code, 403)

    def test_ยืนยันแล้วป้ายรอตรวจถูกลบและติดป้ายว่าคนตรวจแล้ว(self):
        self.client.login(username="owner", password="passpass1")
        self.client.post(reverse("vocab_teacher"),
                         {"vocab_id": self.vocab.pk, "action": "ok"})

        self.vocab.refresh_from_db()
        self.assertIn("human_verified", self.vocab.tags)
        self.assertNotIn("review:error", self.vocab.tags)
        self.assertNotIn("needs_review", self.vocab.tags)

    def test_แก้คำแปลแล้วเขียนทับของ_ai_จริง(self):
        """ทำเครื่องหมายว่าผิดอย่างเดียวไม่พอ — คำแปลผิดยังถูกสอนต่อไป"""
        self.client.login(username="owner", password="passpass1")
        self.client.post(reverse("vocab_teacher"), {
            "vocab_id": self.vocab.pk, "action": "fix",
            "meaning_th": "แพ้ (อาการทางร่างกาย)", "source": "ครูหลิน",
        })

        self.vocab.refresh_from_db()
        self.assertEqual(self.vocab.meaning_th, "แพ้ (อาการทางร่างกาย)")
        self.assertIn("human_verified", self.vocab.tags)

    def test_เก็บร่องรอยว่าใครยืนยันและเมื่อไหร่(self):
        """อีกหกเดือนต้องตอบได้ว่าคำไหนครูดูจริง ไม่ใช่แค่มีป้ายติดอยู่"""
        self.client.login(username="owner", password="passpass1")
        self.client.post(reverse("vocab_teacher"), {
            "vocab_id": self.vocab.pk, "action": "fix",
            "meaning_th": "แพ้", "source": "ครูหลิน",
        })

        note = ExplanationNote.objects.get(vocab=self.vocab)
        self.assertEqual(note.verdict, NoteVerdict.CORRECTED)
        self.assertEqual(note.source, "ครูหลิน")

    def test_กดแก้แต่ไม่พิมพ์อะไรต้องไม่ล้างคำแปลเดิม(self):
        before = self.vocab.meaning_th
        self.client.login(username="owner", password="passpass1")
        self.client.post(reverse("vocab_teacher"),
                         {"vocab_id": self.vocab.pk, "action": "fix", "meaning_th": "  "})

        self.vocab.refresh_from_db()
        self.assertEqual(self.vocab.meaning_th, before)
        self.assertNotIn("human_verified", self.vocab.tags)


class ExamDateTests(TestCase):
    """แก้วันสอบจากหน้าจัดการผู้ใช้

    วันสอบผิดทำให้ตัวจัดตารางทบทวนคำนวณผิดทั้งระบบ — ช่วง freeze 14 วันสุดท้าย
    จะเริ่มผิดวัน และ SRS จะนัดทบทวนไกลเกินกว่าที่ควร
    """

    @classmethod
    def setUpTestData(cls):
        from datetime import date, timedelta

        from core.accounts import create_learner

        word("詞")
        cls.learner, _ = create_learner(
            username="kid2", password="passpass1",
            exam_date=date.today() + timedelta(days=200))
        cls.admin = User.objects.create_user(
            username="boss", password="passpass1", role=Role.ADMIN)

    def setUp(self):
        self.client.login(username="boss", password="passpass1")

    def test_ตั้งวันสอบหลักและรอบสำรองได้(self):
        self.client.post(reverse("user_admin"), {
            "form": "exam_date", "profile_id": self.learner.pk,
            "target": "2026-11-07", "backup": "2026-12-13",
        })
        self.learner.refresh_from_db()
        self.assertEqual(str(self.learner.target_exam_date), "2026-11-07")
        self.assertEqual(str(self.learner.backup_exam_date), "2026-12-13")

    def test_เว้นรอบสำรองว่างได้(self):
        self.client.post(reverse("user_admin"), {
            "form": "exam_date", "profile_id": self.learner.pk,
            "target": "2026-11-07", "backup": "",
        })
        self.learner.refresh_from_db()
        self.assertIsNone(self.learner.backup_exam_date)

    def test_วันที่ผิดรูปแบบต้องไม่เขียนทับของเดิม(self):
        before = self.learner.target_exam_date
        self.client.post(reverse("user_admin"), {
            "form": "exam_date", "profile_id": self.learner.pk, "target": "ไม่ใช่วันที่",
        })
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.target_exam_date, before)

    def test_คนทั่วไปแก้วันสอบของคนอื่นไม่ได้(self):
        before = self.learner.target_exam_date
        User.objects.create_user(username="other", password="passpass1")
        self.client.login(username="other", password="passpass1")
        self.client.post(reverse("user_admin"), {
            "form": "exam_date", "profile_id": self.learner.pk, "target": "2026-11-07",
        })
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.target_exam_date, before)
