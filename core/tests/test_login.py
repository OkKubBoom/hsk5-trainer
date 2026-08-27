"""เทสต์หน้าเข้าสู่ระบบ — จุดที่ผู้ใช้ติดแล้วเข้าระบบไม่ได้เลย

น้องแจ้งว่า "กด logout แล้ว login ไม่ได้" ซึ่งตรวจแล้วไม่ใช่ปัญหาของ session
แต่หน้าจอเดิมขึ้นข้อความเดียวกันหมดทุกกรณี ทำให้ไล่หาสาเหตุผิดทาง
เทสต์ชุดนี้ล็อกไว้ว่าแต่ละกรณีต้องบอกคนละเรื่อง
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.accounts import create_learner


class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_learner(
            username="mint", password="passpass1", display_name="มิ้นท์",
            exam_date=timezone.localdate() + timedelta(days=60),
        )

    def post(self, username, password):
        return self.client.post(reverse("login"), {"username": username, "password": password})

    def test_ออกจากระบบแล้วเข้าใหม่ได้(self):
        """ข้อร้องเรียนหลัก — ยืนยันว่าวงจรนี้ไม่พัง"""
        self.assertRedirects(self.post("mint", "passpass1"), "/")
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
        self.assertRedirects(self.post("mint", "passpass1"), "/")

    def test_รหัสผิดบอกว่าไม่ถูกต้องไม่ใช่บอกว่าลืมกรอก(self):
        res = self.post("mint", "รหัสมั่ว")
        self.assertContains(res, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
        self.assertNotContains(res, "ยังไม่ได้กรอก")

    def test_ลืมกรอกรหัสบอกว่าลืมกรอกไม่ใช่บอกว่ารหัสผิด(self):
        res = self.post("mint", "")
        self.assertContains(res, "ยังไม่ได้กรอกรหัสผ่าน")
        self.assertNotContains(res, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

    def test_ไม่กรอกอะไรเลยบอกทั้งสองช่อง(self):
        self.assertContains(self.post("", ""), "ยังไม่ได้กรอกทั้งชื่อผู้ใช้และรหัสผ่าน")

    def test_ชื่อผู้ใช้แยกตัวพิมพ์เล็กใหญ่(self):
        """สาเหตุที่พบบ่อยและมองไม่ออก — ต้องเข้าไม่ได้จริง หน้าจอจึงเตือนเรื่องนี้ไว้"""
        self.assertContains(self.post("Mint", "passpass1"), "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
        self.assertRedirects(self.post("mint", "passpass1"), "/")

    def test_มีปุ่มดูรหัสผ่าน(self):
        res = self.client.get(reverse("login"))
        self.assertContains(res, "pweye")
        self.assertContains(res, "แสดงรหัสผ่าน")
