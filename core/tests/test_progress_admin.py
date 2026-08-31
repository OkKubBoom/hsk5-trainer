"""เทสต์หน้าความคืบหน้ากลุ่มและสิทธิ์ของ admin

สองเรื่องที่ผิดแล้วอันตราย: การนับวันติดกันผิด (ผู้เรียนเสียกำลังใจโดยไม่มีเหตุ)
และผู้เรียนธรรมดาเข้าหน้าเพิ่มผู้ใช้ได้
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core import progress
from core.accounts import create_learner
from core.models import (
    DrillSession, LearnerProfile, MockExam, ReviewSession, Role, User, VocabItem,
)


class StreakTests(TestCase):
    def test_streak_counts_consecutive_days(self):
        today = timezone.localdate()
        dates = {today, today - timedelta(days=1), today - timedelta(days=2)}
        self.assertEqual(progress.streak(dates, today), 3)

    def test_gap_breaks_the_streak(self):
        today = timezone.localdate()
        dates = {today, today - timedelta(days=2), today - timedelta(days=3)}
        self.assertEqual(progress.streak(dates, today), 1)

    def test_not_done_today_but_done_yesterday_keeps_streak(self):
        """ยังไม่ทำวันนี้ไม่ควรทำให้สถิติที่สะสมมาหายทันที — วันยังไม่จบ"""
        today = timezone.localdate()
        dates = {today - timedelta(days=1), today - timedelta(days=2)}
        self.assertEqual(progress.streak(dates, today), 2)

    def test_missed_two_days_resets(self):
        today = timezone.localdate()
        dates = {today - timedelta(days=2), today - timedelta(days=3)}
        self.assertEqual(progress.streak(dates, today), 0)

    def test_no_history_is_zero(self):
        self.assertEqual(progress.streak(set()), 0)


class GroupProgressTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for i in range(3):
            VocabItem.objects.create(hanzi=f"字{i}", pinyin=f"zi{i}",
                                     meaning_th=f"ความหมาย{i}", hsk_level=5)
        cls.a, _ = create_learner(username="aaa", password="passpass1",
                                  display_name="เอ", exam_date=timezone.localdate() + timedelta(days=60))
        cls.b, _ = create_learner(username="bbb", password="passpass1",
                                  display_name="บี", exam_date=timezone.localdate() + timedelta(days=90))

    def test_shows_every_learner(self):
        rows = progress.group_progress()
        self.assertEqual({r["name"] for r in rows}, {"เอ", "บี"})

    def test_learner_who_has_not_practiced_is_listed_first(self):
        DrillSession.objects.create(learner=self.a, finished_at=timezone.now())
        rows = progress.group_progress()
        self.assertEqual(rows[0]["name"], "บี", "คนที่ยังไม่ทำต้องขึ้นก่อน")
        self.assertTrue(rows[-1]["done_today"])

    def test_does_not_expose_other_peoples_accuracy(self):
        """ความแม่นเทียบกันไม่ได้ จึงต้องไม่หลุดออกมาในหน้ารวม"""
        DrillSession.objects.create(learner=self.a, answered=10, correct=9,
                                    finished_at=timezone.now())
        row = next(r for r in progress.group_progress() if r["name"] == "เอ")
        self.assertNotIn("accuracy", row)
        self.assertNotIn("correct", row)


class UserAdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("boss", password="passpass1", role=Role.ADMIN)
        learner = User.objects.create_user("kid", password="passpass1", role=Role.LEARNER)
        LearnerProfile.objects.create(user=learner,
                                      target_exam_date=timezone.localdate() + timedelta(days=30))

    def test_learner_cannot_open_user_admin(self):
        self.client.login(username="kid", password="passpass1")
        self.assertEqual(self.client.get("/users/").status_code, 403)

    def test_admin_can_open_user_admin(self):
        self.client.login(username="boss", password="passpass1")
        self.assertEqual(self.client.get("/users/").status_code, 200)

    def test_learner_cannot_create_user_by_posting(self):
        """กันการยิง POST ตรงโดยไม่ผ่านหน้าเว็บ"""
        self.client.login(username="kid", password="passpass1")
        before = User.objects.count()
        self.client.post("/users/", {"username": "sneaky", "password": "passpass1",
                                     "exam_date": "2026-12-13"})
        self.assertEqual(User.objects.count(), before)

    def test_duplicate_username_is_rejected(self):
        self.client.login(username="boss", password="passpass1")
        before = User.objects.count()
        response = self.client.post("/users/", {"username": "kid", "password": "passpass1",
                                                "exam_date": "2026-12-13"})
        self.assertEqual(User.objects.count(), before)
        self.assertContains(response, "มีชื่อผู้ใช้")

    def test_everyone_can_see_group_progress(self):
        self.client.login(username="kid", password="passpass1")
        self.assertEqual(self.client.get("/progress/").status_code, 200)


class ActivityTests(TestCase):
    """หน้ากลุ่มต้องบอกว่าแต่ละคน *ทำอะไร* ไม่ใช่แค่ทำ/ไม่ทำ

    วันที่ทวนคำศัพท์อย่างเดียวกับวันที่ไม่ได้แตะระบบเลย ไม่เหมือนกัน
    แต่ปฏิทินเดิมแสดงเป็นสีเทาเหมือนกันทั้งคู่
    """

    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="字", pinyin="zi", meaning_th="ตัวอักษร", hsk_level=5)
        cls.learner, _ = create_learner(
            username="act", password="passpass1", display_name="แอค",
            exam_date=timezone.localdate() + timedelta(days=60),
        )

    def at(self, model, days_ago, **kw):
        obj = model.objects.create(learner=self.learner, **kw)
        when = timezone.now() - timedelta(days=days_ago)
        model.objects.filter(pk=obj.pk).update(started_at=when)
        return obj

    def row(self):
        return next(r for r in progress.group_progress() if r["learner"] == self.learner)

    def test_วันที่ทำชุดหลักกับวันที่ทำอย่างอื่นแยกระดับกัน(self):
        self.at(DrillSession, 1, planned_size=40, answered=40, finished_at=timezone.now())
        self.at(ReviewSession, 2, queue=[], answered=20, correct=15)

        cal = {c["date"]: c["level"] for c in self.row()["calendar"]}
        today = timezone.localdate()
        self.assertEqual(cal[today - timedelta(days=1)], "full")
        self.assertEqual(cal[today - timedelta(days=2)], "some")
        self.assertEqual(cal[today - timedelta(days=3)], "none")

    def test_ทุกช่องมีวันที่ในข้อความเสมอ(self):
        """ข้อร้องเรียนเดิม: ชี้แล้วไม่ขึ้นวันที่เลย"""
        for cell in self.row()["calendar"]:
            self.assertRegex(cell["label"], r"^\d+/\d+ · ")

    def test_ข้อความบอกด้วยว่าทำอะไรไป(self):
        self.at(DrillSession, 1, planned_size=40, answered=40, finished_at=timezone.now())
        cal = {c["date"]: c["label"] for c in self.row()["calendar"]}
        label = cal[timezone.localdate() - timedelta(days=1)]
        self.assertIn("ชุดฝึกวันนี้", label)
        self.assertIn("40 ข้อ", label)

    def test_วันที่ไม่ได้ทำบอกตรงๆ(self):
        cal = {c["date"]: c["label"] for c in self.row()["calendar"]}
        self.assertIn("ไม่ได้ทำอะไร", cal[timezone.localdate() - timedelta(days=5)])

    def test_สรุปว่าใช้ส่วนไหนของระบบไปแล้วบ้าง(self):
        self.at(DrillSession, 1, planned_size=40, answered=40, finished_at=timezone.now())
        self.at(ReviewSession, 1, queue=[], answered=20, correct=15)
        self.at(ReviewSession, 3, queue=[], answered=10, correct=8)

        acts = {a["key"]: a for a in self.row()["activities"]}
        self.assertEqual(acts["drill"]["count"], 1)
        self.assertEqual(acts["review"]["count"], 2)
        self.assertEqual(acts["review"]["answered"], 30)
        self.assertEqual(acts["mock"]["count"], 0)

    def test_ทวนคำศัพท์อย่างเดียวไม่นับเป็น_streak(self):
        """streak คือคำสัญญาว่าทำชุดหลักทุกวัน — เปิดทวน 2 นาทีต้องไม่รักษาไว้ได้"""
        self.at(ReviewSession, 0, queue=[], answered=20, correct=15)
        self.at(ReviewSession, 1, queue=[], answered=20, correct=15)
        self.assertEqual(self.row()["streak"], 0)


class ExamCountdownTests(TestCase):
    """แถบนับถอยหลังต้องอยู่ทุกหน้า และต้องไม่พังกับบัญชีที่ไม่มีวันสอบ"""

    def test_แสดงทั้งรอบหลักและรอบสำรอง(self):
        learner, _ = create_learner(
            username="cd", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=68),
        )
        learner.backup_exam_date = timezone.localdate() + timedelta(days=104)
        learner.save()
        self.client.login(username="cd", password="passpass1")

        res = self.client.get("/")
        rounds = res.context["exam_rounds"]
        self.assertEqual([r["days"] for r in rounds], [68, 104])
        self.assertContains(res, "รอบแรก")
        self.assertContains(res, "รอบสำรอง")

    def test_ไม่มีรอบสำรองก็แสดงรอบเดียว(self):
        create_learner(username="cd2", password="passpass1",
                       exam_date=timezone.localdate() + timedelta(days=30))
        self.client.login(username="cd2", password="passpass1")
        self.assertEqual(len(self.client.get("/").context["exam_rounds"]), 1)

    def test_บัญชีผู้ดูแลที่ไม่มีโปรไฟล์ผู้เรียนไม่พัง(self):
        """เคยเจอมาแล้วว่าบัญชี admin ไม่มี LearnerProfile"""
        User.objects.create_user(username="boss", password="passpass1", role=Role.ADMIN)
        self.client.login(username="boss", password="passpass1")
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["exam_rounds"], [])
