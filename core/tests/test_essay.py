"""เทสต์การตรวจเรียงความ 书写第二部分

จุดที่ผิดแล้วเจ็บที่สุด: ตัดสินระดับใจอ่อนเกินจริง ผู้เรียนเข้าใจว่าตัวเองพร้อมสอบ
ทั้งที่ยังไม่พร้อม — เกณฑ์ 高档 บังคับ 无错别字 พร้อมกับ 无语法错误
ผิดจุดเดียวตกลงมา 中档 ทันที
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import essay, essay_grader
from core.accounts import create_learner
from core.models import VocabItem, WritingFeedback, WritingSubmission


def observation(**kw):
    base = {
        "coherent_logical": True, "content_rich": True, "image_relevant": None,
        "issues": [], "suggestions_th": [], "strengths_th": [], "next_step_th": "",
    }
    base.update(kw)
    return base


def issue(kind="grammar_order", certainty="sure", wrong="很好的一个"):
    return {"span": wrong, "wrong": wrong, "right": "一个很好的",
            "why_th": "ภาษาจีนวางส่วนขยายไว้หน้าคำหลัก", "kind": kind, "certainty": certainty}


class CountingTests(TestCase):
    """ชั้นที่ 1 — Python นับ ห้ามให้โมเดลนับ"""

    def test_นับเฉพาะตัวอักษรจีน(self):
        self.assertEqual(essay.count_chars("今天我很高兴。"), 6)
        self.assertEqual(essay.count_chars("ไทย English 123"), 0)

    def test_หาคำที่ยังไม่ได้ใช้(self):
        text = "我今天很放松，收到一个礼物。"
        self.assertEqual(essay.missing_words(text, ["放松", "礼物", "表演"]), ["表演"])
        self.assertEqual(essay.missing_words(text, ["放松", "礼物"]), [])


class BandTests(TestCase):
    """ชั้นที่ 3 — Python ตัดสิน ห้ามถามโมเดลว่าให้กี่คะแนน"""

    def band(self, **kw):
        args = {"char_count": 96, "missing": [], "task_no": 99,
                "observation": observation()}
        args.update(kw)
        return essay.decide_band(**args)["band"]

    def test_ไม่ได้เขียนอะไรได้ศูนย์(self):
        self.assertEqual(self.band(char_count=0), "zero")

    def test_งานสมบูรณ์ได้ระดับสูง(self):
        self.assertEqual(self.band(), "high")

    def test_ผิดไวยากรณ์จุดเดียวก็ตกจากระดับสูง(self):
        """เกณฑ์ 高档 บังคับ 无语法错误 — ห้ามใจอ่อน"""
        self.assertEqual(self.band(observation=observation(issues=[issue()])), "mid")

    def test_สะกดผิดจุดเดียวก็ตกจากระดับสูง(self):
        self.assertEqual(
            self.band(observation=observation(issues=[issue(kind="typo_homophone")])), "mid")

    def test_ใช้คำไม่ครบตกลงระดับต้น(self):
        self.assertEqual(self.band(missing=["表演"]), "low")

    def test_เนื้อหาไม่ปะติดปะต่อตกลงระดับต้น(self):
        self.assertEqual(self.band(observation=observation(coherent_logical=False)), "low")

    def test_สะกดผิดมากตกลงระดับต้น(self):
        many = [issue(kind="typo_form", wrong=f"错{i}") for i in range(essay.MANY_TYPOS)]
        self.assertEqual(self.band(observation=observation(issues=many)), "low")

    def test_สั้นเกินไปไม่ได้ระดับสูงแม้ไม่มีข้อผิด(self):
        """篇幅不够 ระบุอยู่ในเกณฑ์ 中档 — ถ้าไม่ดักไว้ งาน 40 ตัวอักษรจะได้ระดับสูง"""
        self.assertEqual(self.band(char_count=40), "mid")

    def test_ข้อที่ไม่มั่นใจไม่ถูกนับในการตัดสิน(self):
        """โมเดลไม่แน่ใจ = ไม่ควรลดระดับผู้เรียน แต่ยังแสดงให้ดูได้"""
        self.assertEqual(
            self.band(observation=observation(issues=[issue(certainty="unsure")])), "high")

    def test_บอกเหตุผลเมื่อระดับถูกตัดสินด้วยเกณฑ์ที่ตีความเอง(self):
        """เกณฑ์ 较多错别字 ไม่ระบุตัวเลขในตัวบท ต้องบอกผู้เรียนว่าเป็นการตีความ"""
        many = [issue(kind="typo_form", wrong=f"错{i}") for i in range(essay.MANY_TYPOS)]
        result = essay.decide_band(char_count=96, missing=[], task_no=99,
                                   observation=observation(issues=many))
        self.assertIn("ตีความ", result["band_rule_note"])

    def test_ตัวเลขประมาณติดป้ายว่าเป็นของระบบเสมอ(self):
        result = essay.decide_band(char_count=96, missing=[], task_no=99,
                                   observation=observation())
        self.assertTrue(result["estimate_is_ai"])


class GraderTests(TestCase):
    """ชั้นที่ 2 — เรียก Claude"""

    def test_ไม่มีกุญแจต้องบอกตรงๆ_ไม่ใช่พัง(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            with self.assertRaises(essay_grader.GraderUnavailable) as cm:
                essay_grader.observe(text_zh="我很好", task_no=99, required_words=[],
                                     char_count=3, missing=[])
        self.assertIn("บันทึกไว้แล้ว", str(cm.exception))

    def test_ตัดข้อผิดที่โมเดลแต่งขึ้นเองทิ้ง(self):
        """ถ้าจุดที่บอกว่าผิดไม่มีอยู่ในงานเขียนจริง ผู้เรียนจะหาไม่เจอ
        และอาจแก้สิ่งที่ตัวเองไม่ได้เขียนผิด
        """
        text = "我今天很高兴。"
        cleaned = essay_grader._clean(
            observation(issues=[issue(wrong="我今天"), issue(wrong="ไม่มีในงานเขียน")]), text)
        self.assertEqual(len(cleaned["issues"]), 1)
        self.assertEqual(cleaned["dropped_issues"], 1)

    def test_บอกจำนวนตัวอักษรไปให้โมเดล_ไม่ให้นับเอง(self):
        prompt = essay_grader.build_prompt(
            text_zh="我很好", task_no=99, required_words=["放松"], char_count=3, missing=["放松"])
        self.assertIn("3 ตัวอักษรจีน", prompt)
        self.assertIn("ยังไม่ได้ใช้ 放松", prompt)


class FlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for i in range(10):
            VocabItem.objects.create(hanzi=f"詞{i}", pinyin=f"ci{i}",
                                     meaning_th=f"ความหมาย {i}", hsk_level=5)
        cls.learner, _ = create_learner(
            username="w", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60))

    def setUp(self):
        self.client.login(username="w", password="passpass1")

    def test_บันทึกงานเขียนก่อนเรียกตัวตรวจเสมอ(self):
        """ถ้าเรียกตัวตรวจก่อนแล้วพัง งานที่ผู้เรียนพิมพ์มาจะหายทั้งหมด"""
        self.client.get(reverse("essay_write"))
        res = self.client.post(reverse("essay_submit"), {"text_zh": "我今天很高兴。", "minutes": "5"})
        self.assertEqual(res.status_code, 302)

        sub = WritingSubmission.objects.get(learner=self.learner)
        self.assertEqual(sub.char_count, 6)
        self.assertFalse(hasattr(sub, "feedback"))

    def test_ยังไม่ยินยอมต้องส่งตรวจไม่ได้(self):
        """งานเขียนถูกส่งออกนอกระบบ ต้องกดยินยอมเองก่อน"""
        self.client.get(reverse("essay_write"))
        self.client.post(reverse("essay_submit"), {"text_zh": "我今天很高兴。"})
        sub = WritingSubmission.objects.get(learner=self.learner)

        with patch("core.essay_grader.observe") as mocked:
            self.client.post(reverse("essay_grade", args=[sub.pk]))
        mocked.assert_not_called()
        self.assertFalse(WritingFeedback.objects.exists())

    def test_ยินยอมแล้วตรวจได้และเก็บโทเคนที่ใช้จริง(self):
        self.client.post(reverse("essay_consent"), {"agree": "1"})
        self.client.get(reverse("essay_write"))
        # ต้องใส่คำที่โจทย์กำหนดให้ครบ ไม่งั้นถูกตัดสินเป็นระดับต้นตามเกณฑ์ 未全部使用
        words = "".join(self.client.session["essay_words"])
        self.client.post(reverse("essay_submit"),
                         {"text_zh": words + "我今天很高兴。" + "好" * 80})
        sub = WritingSubmission.objects.get(learner=self.learner)

        with patch("core.essay_grader.observe",
                   return_value=(observation(issues=[issue()]),
                                 {"input_tokens": 1900, "output_tokens": 3000})):
            self.client.post(reverse("essay_grade", args=[sub.pk]))

        fb = WritingFeedback.objects.get(submission=sub)
        self.assertEqual(fb.scores["band"], "mid")
        self.assertEqual(fb.input_tokens, 1900)
        self.assertEqual(fb.output_tokens, 3000)

    def test_ตัวตรวจล่มต้องไม่ทำให้หน้าพังและงานไม่หาย(self):
        self.client.post(reverse("essay_consent"), {"agree": "1"})
        self.client.get(reverse("essay_write"))
        self.client.post(reverse("essay_submit"), {"text_zh": "我今天很高兴。"})
        sub = WritingSubmission.objects.get(learner=self.learner)

        with patch("core.essay_grader.observe",
                   side_effect=essay_grader.GraderUnavailable("ตรวจไม่สำเร็จตอนนี้")):
            res = self.client.post(reverse("essay_grade", args=[sub.pk]), follow=True)

        self.assertEqual(res.status_code, 200)
        self.assertTrue(WritingSubmission.objects.filter(pk=sub.pk).exists())
        self.assertFalse(WritingFeedback.objects.exists())

    def test_แย้งผลตรวจได้และเก็บลงฐาน(self):
        from core.models import ExplanationNote

        self.client.get(reverse("essay_write"))
        self.client.post(reverse("essay_submit"), {"text_zh": "我今天很高兴。"})
        sub = WritingSubmission.objects.get(learner=self.learner)

        self.client.post(reverse("essay_dispute", args=[sub.pk]),
                         {"body": "ครูบอกว่าพูดแบบนี้ได้", "source": "ครูที่สอน"})
        note = ExplanationNote.objects.get()
        self.assertEqual(note.field_name, "essay_issue")
        self.assertIn("ครูบอกว่า", note.body)
