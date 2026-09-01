"""เทสต์การติดตั้งลงจอโฮม (PWA)

ผู้เรียนใช้ระบบบนมือถือเป็นหลัก (D5) การเปิดผ่านเบราว์เซอร์ทุกครั้ง
ทำให้ต้องพิมพ์ URL หรือหาบุ๊กมาร์ก ซึ่งเป็นแรงเสียดทานที่พอจะทำให้ข้ามวันได้
"""
import json

from django.test import TestCase
from django.urls import reverse


class ManifestTests(TestCase):
    def test_เปิดได้โดยไม่ต้องล็อกอิน(self):
        """เบราว์เซอร์อ่าน manifest ก่อนผู้ใช้ล็อกอิน ถ้าบังคับล็อกอินจะติดตั้งไม่ได้"""
        res = self.client.get(reverse("manifest"))
        self.assertEqual(res.status_code, 200)

    def test_เป็น_json_ที่อ่านได้จริง(self):
        data = json.loads(self.client.get(reverse("manifest")).content)
        self.assertEqual(data["scope"], "/")
        self.assertEqual(data["display"], "standalone")

    def test_มีไอคอนครบขนาดที่เบราว์เซอร์ต้องการ(self):
        """ขาด 192 หรือ 512 แล้วปุ่มติดตั้งจะไม่ขึ้นเลย"""
        data = json.loads(self.client.get(reverse("manifest")).content)
        sizes = {i["sizes"] for i in data["icons"]}
        self.assertIn("192x192", sizes)
        self.assertIn("512x512", sizes)
        self.assertIn("maskable", {i["purpose"] for i in data["icons"]})

    def test_พาธไอคอนมาจากระบบ_static_ไม่ใช่เขียนตายตัว(self):
        """ตอน deploy ชื่อไฟล์ถูกเติมแฮช ถ้าเขียนตายตัวไอคอนจะหายทุกครั้งที่ deploy"""
        data = json.loads(self.client.get(reverse("manifest")).content)
        for icon in data["icons"]:
            self.assertTrue(icon["src"].startswith("/static/"), icon["src"])


class ServiceWorkerTests(TestCase):
    def test_เสิร์ฟจากรากเว็บไม่ใช่ใน_static(self):
        """ขอบเขตของ service worker คือโฟลเดอร์ที่มันถูกเสิร์ฟออกมา"""
        self.assertEqual(reverse("service_worker"), "/sw.js")

    def test_ส่งด้วยชนิดไฟล์ที่เบราว์เซอร์ยอมรับ(self):
        res = self.client.get(reverse("service_worker"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("javascript", res["Content-Type"])

    def test_ไม่แคชหน้าเว็บ(self):
        """หน้าเว็บผูกกับบัญชีที่ล็อกอินอยู่ — แคชไว้แล้วคนอื่นในบ้านจะเห็นหน้าของอีกคน
        และโทเคน CSRF ที่ค้างจะทำให้ส่งฟอร์มไม่ผ่านโดยไม่มีใครรู้สาเหตุ
        """
        body = self.client.get(reverse("service_worker")).content.decode()
        self.assertIn("req.mode === 'navigate'", body)
        self.assertIn("fetch(req).catch", body)   # ต่อเน็ตก่อนเสมอ

    def test_ข้ามคำขอที่ไม่ใช่_get(self):
        """ถ้าดักฟอร์มไว้ คำตอบของผู้เรียนอาจไม่ถึงเซิร์ฟเวอร์"""
        body = self.client.get(reverse("service_worker")).content.decode()
        self.assertIn("req.method !== 'GET'", body)

    def test_เปลี่ยนเวอร์ชันแล้วแคชเก่าถูกลบ(self):
        body = self.client.get(reverse("service_worker")).content.decode()
        self.assertIn("caches.delete", body)


class OfflinePageTests(TestCase):
    def test_เปิดได้โดยไม่ต้องล็อกอิน(self):
        """ถ้าบังคับล็อกอิน service worker จะแคชหน้า login ไว้แทน
        แล้วผู้เรียนที่เน็ตหลุดจะเห็นหน้าล็อกอินที่กดยังไงก็ไม่เข้า
        """
        res = self.client.get(reverse("offline"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "ไม่มีอินเทอร์เน็ต")


class IconFileTests(TestCase):
    def test_ไฟล์ไอคอนมีอยู่จริงและเป็น_png(self):
        """manifest ชี้ไปที่ไฟล์ที่ไม่มีอยู่ = ปุ่มติดตั้งไม่ขึ้น และไม่มี error บอก"""
        from pathlib import Path

        from django.conf import settings

        for name in ("icon-192.png", "icon-512.png", "apple-touch-icon.png"):
            path = Path(settings.BASE_DIR) / "static" / "icons" / name
            with self.subTest(icon=name):
                self.assertTrue(path.exists(), f"ไม่มีไฟล์ {name} — รัน make_icons")
                self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
