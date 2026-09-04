"""เทสต์ 听写

จุดที่ผิดแล้วเจ็บที่สุด: ติดป้าย "เสียงพ้อง" ให้ตัวที่เสียงไม่เหมือนกัน
ผู้เรียนจะเข้าใจว่าตัวเองฟังออกแล้ว ทั้งที่จริงฟังไม่ออก แล้วไปแก้ผิดจุด
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import dictation
from core.accounts import create_learner
from core.models import (
    DictationAttempt, Question, QuestionStatus, QuestionType, Section, VocabItem,
)


class CompareTests(TestCase):
    def test_พิมพ์ถูกทุกตัวได้เต็ม(self):
        r = dictation.compare("我今天很高兴", "我今天很高兴")
        self.assertEqual(r["accuracy"], 100)
        self.assertTrue(r["perfect"])

    def test_ไม่นับเครื่องหมายวรรคตอน(self):
        """คนที่ฟังออกครบแต่ไม่ใส่จุลภาค ไม่ควรถูกหักคะแนน —
        เครื่องหมายวรรคตอนไม่ได้อยู่ในเสียงที่ได้ยิน
        """
        r = dictation.compare("你好，是在这儿吗？", "你好是在这儿吗")
        self.assertTrue(r["perfect"])

    def test_พิมพ์ตกหนึ่งตัวไม่ทำให้ที่เหลือผิดหมด(self):
        """เทียบตำแหน่งตรงๆ จะพังทันทีที่ตกไปหนึ่งตัว — ตัวหลังเลื่อนหมด"""
        r = dictation.compare("我今天很高兴", "我天很高兴")
        self.assertEqual(r["wrong"], 1)
        self.assertEqual([o["type"] for o in r["ops"] if o["type"] != "ok"], ["missing"])

    def test_พิมพ์เกินมานับเป็นเกิน_ไม่ใช่ผิด(self):
        r = dictation.compare("我很好", "我很很好")
        self.assertIn("extra", [o["type"] for o in r["ops"]])


class HomophoneTests(TestCase):
    """ป้ายเสียงพ้องติดได้ต่อเมื่อพิสูจน์ได้จากคลังคำศัพท์ของเราเอง"""

    @classmethod
    def setUpTestData(cls):
        for hanzi, pinyin in [("在", "zài"), ("再", "zài"), ("兴", "xìng"), ("心", "xīn")]:
            VocabItem.objects.create(hanzi=hanzi, pinyin=pinyin,
                                     meaning_th=f"ความหมาย {hanzi}", hsk_level=5)
        dictation._char_pinyin.cache_clear()

    @classmethod
    def tearDownClass(cls):
        dictation._char_pinyin.cache_clear()
        super().tearDownClass()

    def test_ติดป้ายเสียงพ้องเมื่อพินอินตรงกัน(self):
        r = dictation.compare("我在家", "我再家")
        self.assertEqual([o["type"] for o in r["ops"] if o["type"] != "ok"], ["homophone"])
        self.assertEqual(len(r["homophones"]), 1)

    def test_ไม่ติดป้ายเสียงพ้องเมื่อเสียงไม่เหมือน(self):
        """兴 xìng กับ 心 xīn เสียงต่างกัน ติดป้ายเสียงพ้องคือสอนผิด"""
        r = dictation.compare("很高兴", "很高心")
        self.assertEqual([o["type"] for o in r["ops"] if o["type"] != "ok"], ["wrong"])

    def test_ไม่รู้พินอินต้องไม่เดาว่าเป็นเสียงพ้อง(self):
        """ไม่มีข้อมูลไม่ใช่หลักฐาน — ตกไปเป็น 'ตัวผิด' ซึ่งพูดน้อยกว่าแต่ไม่ผิด"""
        r = dictation.compare("我喜欢", "我喜歡")
        self.assertNotIn("homophone", [o["type"] for o in r["ops"]])


class PickTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.question = Question.objects.create(
            qtype=QuestionType.LISTENING_MC, section=Section.LISTENING,
            status=QuestionStatus.ACTIVE, prompt_zh="男的是什么意思？",
            answer_text="ก",
            audio_script="下雨了，出门时别忘了带伞。好。男的是什么意思？")

    def test_เลือกเฉพาะประโยคที่ยาวพอดี(self):
        """สั้นเกินไปฝึกอะไรไม่ได้ ยาวเกินไปจำไม่ไหวใน 1-2 รอบ"""
        found = dictation.sentences_of(self.question)
        self.assertEqual(len(found), 1)
        self.assertIn("别忘了带伞", found[0])

    def test_ไม่เอาคำถามท้ายบทมาให้พิมพ์(self):
        """คำถามอยู่บนจอให้อ่านอยู่แล้ว ไม่ใช่สิ่งที่ต้องฟังให้ออก"""
        for s in dictation.sentences_of(self.question):
            self.assertNotIn("男的是什么意思", s)

    def test_เลี่ยงประโยคที่เคยฝึกแล้ว(self):
        first = dictation.pick(seed=1)
        again = dictation.pick(exclude=[first["key"]], seed=1)
        # มีประโยคเดียวในคลัง จึงวนกลับมาได้ — ขอแค่ต้องไม่ระเบิดและต้องคืนของ
        self.assertIsNotNone(again)

    def test_คลังว่างต้องคืน_none_ไม่ใช่ระเบิด(self):
        Question.objects.all().delete()
        self.assertIsNone(dictation.pick())


class FlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="詞", pinyin="ci", meaning_th="ความหมาย", hsk_level=5)
        cls.learner, _ = create_learner(
            username="d", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60))
        cls.question = Question.objects.create(
            qtype=QuestionType.LISTENING_MC, section=Section.LISTENING,
            status=QuestionStatus.ACTIVE, prompt_zh="?", answer_text="ก",
            audio_script="下雨了，出门时别忘了带伞。")

    def setUp(self):
        self.client.login(username="d", password="passpass1")

    def test_บันทึกผลพร้อมจำนวนครั้งที่ฟัง(self):
        self.client.post(reverse("dictation"), {
            "question_id": self.question.pk, "key": f"{self.question.pk}:0",
            "expected": "下雨了，出门时别忘了带伞。",
            "typed": "下雨了出门时别忘了带伞", "plays": "3", "rate": "0.85",
        })
        attempt = DictationAttempt.objects.get()
        self.assertEqual(attempt.accuracy_pct, 100)
        self.assertEqual(attempt.replay_count, 3)
        self.assertEqual(attempt.playback_rate, 0.85)

    def test_ไม่ได้พิมพ์อะไรต้องไม่พังและได้ศูนย์(self):
        res = self.client.post(reverse("dictation"), {
            "question_id": self.question.pk, "key": f"{self.question.pk}:0",
            "expected": "下雨了", "typed": "", "plays": "1",
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(DictationAttempt.objects.get().accuracy_pct, 0)

    def test_ขอบทเป็นรายประโยคได้(self):
        url = reverse("listen_script", args=[self.question.pk])
        res = self.client.get(url, {"s": "0"})
        self.assertEqual(res.json()["script"], "下雨了，出门时别忘了带伞。")

    def test_ขอประโยคที่ไม่มีต้องตอบ404(self):
        res = self.client.get(reverse("listen_script", args=[self.question.pk]), {"s": "99"})
        self.assertEqual(res.status_code, 404)


class SentenceAudioTests(TestCase):
    """听写 ต้องใช้ไฟล์เสียงเหมือนหน้าอื่น

    ถ้ายังใช้ตัวอ่านของเบราว์เซอร์ เสียงจะต่างกันไปตามเครื่องของแต่ละคน —
    Android ได้เสียงของ Google · Windows ได้ของ Microsoft · บางเครื่องไม่มีเสียงจีนเลย
    ผู้เรียนสองคนฝึกประโยคเดียวกันแล้วได้ยินคนละอย่าง เทียบผลกันไม่ได้
    """

    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="詞", pinyin="ci", meaning_th="ความหมาย", hsk_level=5)
        from datetime import timedelta

        from django.utils import timezone
        create_learner(username="sa", password="passpass1",
                       exam_date=timezone.localdate() + timedelta(days=60))
        cls.q = Question.objects.create(
            qtype=QuestionType.LISTENING_MC, section=Section.LISTENING,
            status=QuestionStatus.ACTIVE, prompt_zh="男的是什么意思？",
            answer_text="ก", source_ref="H51001 ข้อ 1",
            audio_script="下雨了，出门时别忘了带伞。放心吧，忘不了。男的是什么意思？",
            audio_turns=[{"who": "f", "text": "下雨了，出门时别忘了带伞。"},
                         {"who": "m", "text": "放心吧，忘不了。"},
                         {"who": "q", "text": "男的是什么意思？"}])

    def test_รู้ว่าประโยคไหนใครพูด(self):
        """อัดด้วยเสียงผิดคน ผู้เรียนจะจำเสียงคำผิดไปเลย"""
        rows = dictation.sentence_rows(self.q)
        self.assertEqual([r["who"] for r in rows], ["f"])   # ของ m สั้นเกินเกณฑ์
        self.assertIn("带伞", rows[0]["text"])

    def test_ไม่เอาคำถามมาให้พิมพ์(self):
        for r in dictation.sentence_rows(self.q):
            self.assertNotIn("男的是什么意思", r["text"])

    def test_ชื่อไฟล์รายประโยคแยกจากไฟล์ทั้งข้อ(self):
        from core import listening

        self.assertEqual(listening.sentence_slug("H51001 ข้อ 1", 0), "H51001-1-s0")
        self.assertNotEqual(listening.audio_url("H51001 ข้อ 1"),
                            listening.audio_url("H51001 ข้อ 1", sentence=0))

    def test_เอนด์พอยต์ส่งไฟล์รายประโยคมาให้(self):
        self.client.login(username="sa", password="passpass1")
        body = self.client.get(reverse("listen_script", args=[self.q.pk]), {"s": "0"}).json()
        self.assertIn("audio", body)
        self.assertIn("H51001-1-s0", body["audio"])

    def test_ข้อเก่าที่ไม่มี_audio_turns_ยังใช้ได้(self):
        """ต้องถอยไปตัดจากบทรวมเหมือนเดิม ไม่ใช่ทำให้ข้อนั้นหายไปจากคลัง"""
        old = Question.objects.create(
            qtype=QuestionType.LISTENING_MC, section=Section.LISTENING,
            status=QuestionStatus.ACTIVE, prompt_zh="?", answer_text="ก",
            audio_script="下雨了，出门时别忘了带伞。", audio_turns=[])
        rows = dictation.sentence_rows(old)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["who"], "n")
