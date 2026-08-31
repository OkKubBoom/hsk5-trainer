"""เทสต์การเตะออกตอนเที่ยงคืน และการบันทึกวันเข้าระบบ

จุดที่ผิดแล้วเจ็บ:
  - เตะออกผิดจังหวะ = ผู้เรียนโดนดีดกลางคันระหว่างทำข้อสอบ
  - วนกลับหน้าเดิม = เข้าระบบไม่ได้เลยทั้งวัน
  - ตอน deploy แล้วทุกคนโดนเตะพร้อมกันโดยไม่รู้สาเหตุ
"""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.accounts import create_learner
from core.daily_session import SESSION_DAY_KEY
from core.models import LoginDay, VocabItem


class LoginDayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="字", pinyin="zi", meaning_th="ตัวอักษร", hsk_level=5)
        create_learner(username="kid", password="passpass1",
                       exam_date=timezone.localdate() + timedelta(days=60))

    def test_เข้าระบบแล้วบันทึกวันไว้(self):
        self.client.post(reverse("login"), {"username": "kid", "password": "passpass1"})
        self.assertTrue(LoginDay.objects.filter(user__username="kid", date=timezone.localdate()).exists())

    def test_เข้าหลายครั้งในวันเดียวนับเป็นวันเดียว(self):
        """ไม่งั้นตัวเลข 'เข้าระบบกี่วัน' จะกลายเป็น 'เข้าระบบกี่ครั้ง' ซึ่งคนละเรื่อง"""
        for _ in range(3):
            self.client.post(reverse("login"), {"username": "kid", "password": "passpass1"})
            self.client.post(reverse("logout"))
        self.assertEqual(LoginDay.objects.filter(user__username="kid").count(), 1)

    def test_ประทับวันไว้ในเซสชันด้วย(self):
        self.client.post(reverse("login"), {"username": "kid", "password": "passpass1"})
        self.assertEqual(self.client.session[SESSION_DAY_KEY], timezone.localdate().isoformat())


class DailyLogoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="字", pinyin="zi", meaning_th="ตัวอักษร", hsk_level=5)
        create_learner(username="kid", password="passpass1",
                       exam_date=timezone.localdate() + timedelta(days=60))

    def login(self):
        self.client.post(reverse("login"), {"username": "kid", "password": "passpass1"})

    def set_session_day(self, value):
        session = self.client.session
        session[SESSION_DAY_KEY] = value
        session.save()

    def test_วันเดียวกันยังใช้งานได้ปกติ(self):
        self.login()
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_ข้ามวันแล้วโดนเตะออก(self):
        self.login()
        self.set_session_day((timezone.localdate() - timedelta(days=1)).isoformat())

        res = self.client.get("/")
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("login"), res["Location"])
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_เตะออกแล้วพากลับไปหน้าที่ตั้งใจเข้า(self):
        """ล็อกอินใหม่แล้วต้องไปต่อที่เดิม ไม่ใช่เด้งกลับหน้าแรกทุกครั้ง"""
        self.login()
        self.set_session_day((timezone.localdate() - timedelta(days=1)).isoformat())
        res = self.client.get(reverse("vocab_list"))
        self.assertIn("next=/vocab/", res["Location"])

    def test_หน้าล็อกอินต้องไม่วนกลับตัวเอง(self):
        self.login()
        self.set_session_day((timezone.localdate() - timedelta(days=1)).isoformat())
        self.assertEqual(self.client.get(reverse("login")).status_code, 302)  # ไปหน้าแรกเพราะยัง auth อยู่
        # เข้าอีกครั้งหลังถูกเตะ ต้องได้หน้าล็อกอินจริง ไม่ใช่ 302 ซ้ำๆ
        self.client.get("/")
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_หน้าเวอร์ชันเปิดได้เสมอ(self):
        """ใช้เช็ค deploy ต้องไม่ถูกบล็อกด้วยกฎเซสชัน"""
        self.login()
        self.set_session_day((timezone.localdate() - timedelta(days=1)).isoformat())
        self.assertEqual(self.client.get(reverse("version")).status_code, 200)

    def test_เซสชันเก่าที่ยังไม่มีวันประทับไม่โดนเตะ(self):
        """ตอน deploy ครั้งแรก ทุกคนมีเซสชันที่ยังไม่มีคีย์นี้
        ถ้าเตะทั้งหมดพร้อมกัน ผู้เรียนจะงงว่าเกิดอะไรขึ้น
        """
        self.login()
        session = self.client.session
        del session[SESSION_DAY_KEY]
        session.save()

        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.session[SESSION_DAY_KEY], timezone.localdate().isoformat())

    @override_settings(DAILY_LOGOUT=False)
    def test_ปิดสวิตช์แล้วไม่เตะ_แต่ยังบันทึกวันเข้าระบบ(self):
        """แยกสองเรื่องออกจากกัน — ถ้าการเตะออกสร้างความเสียดทานเกินไป
        ปิดได้โดยที่สถิติความสม่ำเสมอยังครบเหมือนเดิม
        """
        self.login()
        self.set_session_day((timezone.localdate() - timedelta(days=1)).isoformat())

        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertTrue(LoginDay.objects.filter(user__username="kid").exists())


class LoginDaysOnGroupPageTests(TestCase):
    """หน้ากลุ่มต้องบอกได้ว่าใครเข้าระบบกี่วันใน 30 วัน"""

    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="字", pinyin="zi", meaning_th="ตัวอักษร", hsk_level=5)
        cls.learner, _ = create_learner(
            username="kid", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60),
        )

    def test_นับวันเข้าระบบใน30วัน(self):
        from core import progress

        today = timezone.localdate()
        for back in (0, 1, 3, 40):  # 40 วันก่อน อยู่นอกหน้าต่าง ต้องไม่ถูกนับ
            LoginDay.objects.create(user=self.learner.user, date=today - timedelta(days=back))

        row = next(r for r in progress.group_progress() if r["learner"] == self.learner)
        self.assertEqual(row["login_days"], 3)
        self.assertTrue(row["logged_in_today"])

    def test_วันที่เข้าระบบแต่ไม่ได้ทำอะไรมีระดับของตัวเอง(self):
        """ต่างจากวันที่หายไปเลย — เป็นสัญญาณคนละแบบ"""
        from core import progress

        yesterday = timezone.localdate() - timedelta(days=1)
        LoginDay.objects.create(user=self.learner.user, date=yesterday)

        row = next(r for r in progress.group_progress() if r["learner"] == self.learner)
        cal = {c["date"]: c for c in row["calendar"]}
        self.assertEqual(cal[yesterday]["level"], "seen")
        self.assertIn("เข้าระบบแต่ไม่ได้ทำอะไร", cal[yesterday]["label"])


class SettingsSafetyTests(TestCase):
    """ค่าตั้งต้นต้องปลอดภัย — พิมพ์ชื่อ env ผิดครั้งเดียวต้องไม่เปิดโหมดดีบัก"""

    def test_debug_ตั้งต้นเป็นปิด(self):
        """หน้า error ของโหมดดีบักพ่นค่า env ทั้งหมดรวมถึงรหัสผ่านฐานข้อมูล"""
        import os
        from config import settings as conf

        self.assertFalse(conf.env_bool("DJANGO_A_NAME_THAT_DOES_NOT_EXIST"))
        self.assertNotIn("DJANGO_A_NAME_THAT_DOES_NOT_EXIST", os.environ)

    def test_ค่าสำรองของ_secret_key_ไม่อยู่ในโค้ดสำหรับ_production(self):
        """คีย์สำรองเดิมอยู่ใน repo สาธารณะ ใครก็ปลอม session cookie ได้"""
        from pathlib import Path

        from django.conf import settings as dj

        source = (Path(dj.BASE_DIR) / "config" / "settings.py").read_text(encoding="utf-8")
        self.assertIn("ImproperlyConfigured", source)
        self.assertNotIn("dev-insecure-key-change-me", source)
