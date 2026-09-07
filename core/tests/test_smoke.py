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
        # หน้าที่เปิดได้โดยไม่ล็อกอิน — ทุกตัวมีเหตุผลเฉพาะ ห้ามเติมโดยไม่เขียนเหตุผล
        open_pages = {
            "login",
            "version",          # ใช้เช็คตอน deploy ว่าโค้ดขึ้นหรือยัง ต้องเปิดจากมือถือได้เร็ว
            "manifest",         # เบราว์เซอร์อ่านก่อนผู้ใช้ล็อกอิน ถ้าปิดจะติดตั้งลงจอโฮมไม่ได้
            "service_worker",   # ต้องโหลดได้ตั้งแต่ก่อนล็อกอิน ไม่งั้นไม่ทำงานเลย
            "offline",          # ถ้าปิด service worker จะแคชหน้า login ไว้แทน
                                # แล้วผู้เรียนที่เน็ตหลุดจะเห็นหน้าล็อกอินที่กดยังไงก็ไม่เข้า
        }
        for name, url in all_get_urls():
            if name in open_pages:
                continue
            with self.subTest(page=name):
                res = self.client.get(url)
                self.assertIn(res.status_code, (302, 403), f"{name} เปิดได้ทั้งที่ยังไม่ล็อกอิน")


class SmokeWithAwkwardDataTests(TestCase):
    """กวาดทุกหน้าอีกรอบ แต่คราวนี้ **มีข้อมูลที่ผิดรูปอยู่ในฐาน**

    SmokeTests ข้างบนกวาดบนฐานที่ว่างเปล่า จึงจับได้แค่บั๊กเรื่องเส้นทางกับค่า None
    ของโปรไฟล์ ไม่เคยจับบั๊กที่เกิดจาก *เนื้อข้อมูล* ได้เลย

    ที่รู้ว่าเป็นช่องโหว่จริงเพราะเคยหลุดมาแล้ว: /explanation/review/ เป็น 500
    ทั้งหน้าเมื่อมีโน้ตที่เจ้าของถูกลบ (author เป็น SET_NULL) เทสต์ชุดเดิมผ่านฉลุย
    เพราะฐานไม่มีโน้ตสักอัน กว่าจะเจอคือตอนเปิดหน้าดูด้วยตาเอง

    แถวที่สร้างที่นี่คือแถวที่ *เกิดขึ้นได้จริง* บนเซิร์ฟเวอร์ ไม่ใช่แถวที่แต่งให้พัง
    """

    @classmethod
    def setUpTestData(cls):
        from core.models import (
            Card, DrillSession, ExplanationNote, NoteStatus, NoteVerdict,
            Question, QuestionStatus, Section, WritingSubmission,
        )

        # คำศัพท์ที่ข้อมูลไม่ครบ — ของจริงมีแบบนี้อยู่ เพราะนำเข้ามาจากหลายแหล่ง
        VocabItem.objects.create(hanzi="字", pinyin="zì", meaning_th="ตัวอักษร", hsk_level=5)
        VocabItem.objects.create(hanzi="缺", pinyin="", meaning_th="", hsk_level=5)
        # ระดับ 6 มีในตัวเลือกของหน้าคลังคำศัพท์ แต่ในคลังจริงไม่มีคำสักคำ
        VocabItem.objects.create(hanzi="标", pinyin="biāo", meaning_th="ป้าย",
                                 hsk_level=6, tags=["needs_review", "review:warn"])

        profile, _ = create_learner(
            username="kid", password="passpass1", display_name="เด็ก",
            exam_date=timezone.localdate() + timedelta(days=60))
        cls.profile = profile

        # ผู้เรียนที่เลือกระดับที่ไม่มีการ์ดเหลือเลย — เลือกเองได้ตั้งแต่ 1.15.0
        profile.vocab_levels = [1]
        profile.save(update_fields=["vocab_levels"])

        # ชุดฝึกที่เปิดค้างไว้ไม่ได้ทำจนจบ — เกิดทุกครั้งที่ปิดแท็บกลางคัน
        DrillSession.objects.create(learner=profile, planned_size=10)

        boss = User.objects.create_user(username="boss", password="passpass1",
                                        role=Role.ADMIN, is_staff=True)
        cls.boss = boss

        question = Question.objects.create(
            qtype="reading_mc", section=Section.READING, status=QuestionStatus.ACTIVE,
            prompt_zh="…", answer_text="ถูก",
            explanation={
                "why_correct": "เพราะอย่างนี้",
                # คำสำคัญที่ไม่มีในคลังคำศัพท์ — เป็นที่มาของหน้า /vocab/beyond/
                "key_vocab": [{"hanzi": "旗鼓相当", "note": "สูสีกัน"}],
                "source": "ai_generated",
            },
        )
        # โน้ตที่เจ้าของถูกลบไปแล้ว — ทั้งที่รอตรวจและที่ตรวจไปแล้ว
        ExplanationNote.objects.create(question=question, author=None,
                                       verdict=NoteVerdict.WRONG, body="เฉลยผิด")
        ExplanationNote.objects.create(question=question, author=None,
                                       verdict=NoteVerdict.CONFIRMED, body="ถูกแล้ว",
                                       status=NoteStatus.ACCEPTED)

        # งานเขียนที่ส่งแล้วแต่ยังไม่มีผลตรวจกลับมา — สถานะปกติของคิว D11
        WritingSubmission.objects.create(learner=profile, text_zh="我们应该保护环境。",
                                         task_no=99, char_count=9)

    def _walk(self, username):
        self.client.login(username=username, password="passpass1")
        for name, url in all_get_urls():
            with self.subTest(page=name):
                res = self.client.get(url, follow=True)
                self.assertLess(res.status_code, 500,
                                f"{name} ({url}) → {res.status_code}")

    def test_ผู้เรียนเปิดได้ทุกหน้าแม้ฐานมีข้อมูลผิดรูป(self):
        self._walk("kid")

    def test_เจ้าของระบบเปิดได้ทุกหน้าแม้ฐานมีข้อมูลผิดรูป(self):
        self._walk("boss")
