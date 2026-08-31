"""กวาดทุกหน้าในระบบ ดูว่ามีหน้าไหนพัง

เขียนขึ้นเพราะเจ้าของระบบ (บัญชีผู้ดูแลที่ไม่มีโปรไฟล์ผู้เรียน) กดเข้าหน้าต่างๆ
แล้วเจอ 500 ทุกหน้ายกเว้นหน้าแรก — 23 view เรียก _learner() แล้วใช้ต่อทันที
โดยไม่เช็คว่าได้ None กลับมาไหม

เทสต์แบบนี้จับบั๊กประเภท "ลืมเช็คค่าว่าง" ได้ทั้งหมดในครั้งเดียว
และจะจับหน้าใหม่ที่เพิ่มเข้ามาทีหลังด้วยโดยอัตโนมัติ

เกณฑ์คือ "ห้าม 5xx" ไม่ใช่ "ต้อง 200" เพราะ 403 (ไม่มีสิทธิ์)
กับ 405 (เปิดด้วย GET ไม่ได้) เป็นพฤติกรรมที่ถูกต้องของบางหน้า
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import get_resolver, reverse
from django.utils import timezone

from core.accounts import create_learner
from core.models import Role, User, VocabItem

# หน้าที่ต้องส่งพารามิเตอร์ — ทดสอบแยกในไฟล์ของฟีเจอร์นั้น
SKIP = {"logout", "admin"}


def all_get_urls() -> list[tuple[str, str]]:
    """ทุก URL ที่เปิดด้วย GET ได้โดยไม่ต้องมี id"""
    out = []
    for name, patterns in get_resolver().reverse_dict.items():
        if not isinstance(name, str) or name in SKIP:
            continue
        try:
            out.append((name, reverse(name)))
        except Exception:
            continue  # ต้องมีพารามิเตอร์ ข้ามไป
    return sorted(set(out))


class SmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="字", pinyin="zi", meaning_th="ตัวอักษร", hsk_level=5)
        create_learner(username="kid", password="passpass1", display_name="เด็ก",
                       exam_date=timezone.localdate() + timedelta(days=60))
        User.objects.create_user(username="boss", password="passpass1",
                                 role=Role.ADMIN, is_staff=True)

    def test_ผู้เรียนเปิดได้ทุกหน้าโดยไม่พัง(self):
        self.client.login(username="kid", password="passpass1")
        for name, url in all_get_urls():
            with self.subTest(page=name):
                res = self.client.get(url, follow=True)
                self.assertLess(res.status_code, 500, f"{name} ({url}) → {res.status_code}")

    def test_ผู้ดูแลที่ไม่มีโปรไฟล์ผู้เรียนก็ต้องไม่พัง(self):
        """เดิมพัง 500 ทุกหน้ายกเว้นหน้าแรก — ซึ่งเป็นบัญชีที่เจ้าของระบบใช้ตรวจงาน"""
        self.client.login(username="boss", password="passpass1")
        for name, url in all_get_urls():
            with self.subTest(page=name):
                res = self.client.get(url, follow=True)
                self.assertLess(res.status_code, 500, f"{name} ({url}) → {res.status_code}")

    def test_คนที่ยังไม่ล็อกอินถูกพาไปหน้าล็อกอิน_ไม่ใช่เห็นข้อมูล(self):
        open_pages = {"login", "version"}
        for name, url in all_get_urls():
            if name in open_pages:
                continue
            with self.subTest(page=name):
                res = self.client.get(url)
                self.assertIn(res.status_code, (302, 403), f"{name} เปิดได้ทั้งที่ยังไม่ล็อกอิน")
