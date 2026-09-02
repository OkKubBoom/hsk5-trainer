"""เทสต์พาร์ทฟัง

จุดที่ผิดแล้วเจ็บที่สุด: บทพูดหลุดขึ้นจอก่อนตอบ
ข้อฟังจะกลายเป็นข้ออ่านทันที ผู้เรียนได้คะแนนพาร์ทฟังสูงหลอก
แล้วเอาตัวเลขนั้นไปตัดสินใจว่าสมัครสอบรอบไหน
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import listen_explain, listening, reading
from core.accounts import create_learner
from core.models import (
    ItemGroup, Question, QuestionOption, QuestionStatus, QuestionType,
    Section, SourceType, VocabItem,
)

# ตัวอย่างที่ตัดมาจากรูปแบบจริง — ตัดบรรทัดกลางประโยคเหมือน PDF ต้นฉบับ
TRANSCRIPT = """H51001 卷听力材料
（音乐，30 秒，渐弱）
大家好！欢迎参加 HSK（五级）考试。
第一部分
第 1 到 20 题，请选出正确答案。现在开始第 1 题：
1．女：下雨了，出门时别忘了带伞。
男：放心吧，忘不了。
问：男的是什么意思？
2．男：我以为你早该到了，怎么现在才到？
女：别提了！本来我连飞机票都买好了，可是因为大雾，航班取消了，
我只好坐火车过来了。
问：女的为什么来晚了？
第二部分
第 21 到 45 题，请选出正确答案。现在开始第 21 题：
21．女：这儿的风景很漂亮，真后悔没带相机。
男：用手机拍啊，你的手机不是能照相吗？
问：女的后悔什么？
第 31 到 32 题是根据下面一段对话：
女：杨老师，我明天要去北京参加一个会议。
男：非常欢迎！我明天没有什么安排。
31．女的来北京做什么？
32．明天天气怎么样？
第 33 到 34 题是根据下面一段话：
大学毕业以后，李丽和好朋友陈慧一起找了一套房子，房费一人出一半
儿，既省钱又可以有个伴儿。
33．李丽现在和谁住在一起？
34．关于李丽，下列哪项正确？
听力考试现在结束。
"""


class ParseTests(TestCase):
    def setUp(self):
        self.items = {i.number: i for i in listening.parse(TRANSCRIPT)}

    def test_ได้ครบทุกข้อที่มีในบท(self):
        self.assertEqual(sorted(self.items), [1, 2, 21, 31, 32, 33, 34])

    def test_แยกคำถามออกจากบทได้(self):
        """ถ้าคำถามยังปนอยู่ในบท ตัวอ่านจะพูดคำว่า 问 ออกมาด้วย"""
        item = self.items[1]
        self.assertEqual(item.question_zh, "男的是什么意思？")
        self.assertNotIn("问", item.script)

    def test_ต่อบรรทัดที่_pdf_ตัดกลางประโยคกลับเข้าด้วยกัน(self):
        """ถ้าไม่ต่อ เสียงจะหยุดกลางประโยค ซึ่งฟังแล้วงงกว่าไม่มีเสียง"""
        self.assertIn("航班取消了，我只好坐火车过来了。", self.items[2].script)

    def test_ข้อที่ใช้บทเดียวกันได้บทเดียวกันแต่คนละคำถาม(self):
        a, b = self.items[31], self.items[32]
        self.assertEqual(a.script, b.script)
        self.assertEqual(a.passage_key, "31-32")
        self.assertNotEqual(a.question_zh, b.question_zh)

    def test_บทเล่าเรื่องถูกต่อเป็นก้อนเดียว(self):
        """บทยาวไม่มีชื่อผู้พูด ทุกบรรทัดคือประโยคเดียวกันที่ถูกตัด"""
        self.assertIn("房费一人出一半儿", self.items[33].script)

    def test_ไม่นับบรรทัดประกาศเป็นเนื้อหา(self):
        for item in self.items.values():
            self.assertNotIn("请选出正确答案", item.script)
            self.assertNotIn("欢迎参加", item.script)

    def test_ตัดชื่อผู้พูดออกก่อนอ่านออกเสียง(self):
        """ข้อสอบจริงใช้คนสองคนพูด ไม่ได้อ่านคำว่า 女 นำทุกประโยค"""
        speech = listening.speech_text(self.items[1])
        self.assertFalse(speech.startswith("女"))
        self.assertIn("下雨了", speech)
        self.assertTrue(speech.endswith("男的是什么意思？"))

    def test_ไม่ใส่จุดซ้ำหลังเครื่องหมายที่จบประโยคอยู่แล้ว(self):
        """"？。" ทำให้ตัวอ่านหยุดยาวผิดจังหวะ"""
        self.assertNotIn("？。", listening.speech_text(self.items[2]))

    def test_บทว่างต้องไม่ระเบิด(self):
        self.assertEqual(listening.parse(""), [])
        self.assertEqual(listening.parse("ไม่มีอะไรเลย"), [])


def make_listening_question(script="下雨了。男的是什么意思？", answer="他会带伞的"):
    group = ItemGroup.objects.create(
        kind="listening_dialog", section=Section.LISTENING,
        title="ทดสอบ", passage_zh=script,
        source_type=SourceType.OFFICIAL_PAST_PAPER,
    )
    q = Question.objects.create(
        qtype=QuestionType.LISTENING_MC, section=Section.LISTENING,
        status=QuestionStatus.ACTIVE, prompt_zh="男的是什么意思？",
        prompt_th="ฟังแล้วเลือกคำตอบที่ถูกต้อง",
        answer_text=answer, audio_script=script, group=group,
        source_type=SourceType.OFFICIAL_PAST_PAPER, source_ref="TEST ข้อ 1",
    )
    for i, text in enumerate([answer, "ผิด1", "ผิด2", "ผิด3"]):
        QuestionOption.objects.create(question=q, text=text, is_correct=(i == 0), order=i)
    return q


class TurnTests(TestCase):
    """แยกบทเป็นช่วงพูด — อ่านรวดเดียวด้วยเสียงเดียวฟังยากกว่าของจริง"""

    def setUp(self):
        self.items = {i.number: i for i in listening.parse(TRANSCRIPT)}

    def test_รู้ว่าใครพูดช่วงไหน(self):
        turns = listening.speech_turns(self.items[1])
        self.assertEqual([t["who"] for t in turns], ["f", "m", "q"])

    def test_ไม่มีชื่อผู้พูดปนอยู่ในข้อความที่จะอ่าน(self):
        """ปล่อยไว้ผู้เรียนจะได้ยินคำว่า "หนวี่" นำทุกประโยค ซึ่งไม่มีในห้องสอบ

        เช็คเฉพาะช่วงบทสนทนา — ตัวคำถามขึ้นต้นด้วย 男 ได้ตามปกติ
        เพราะ 男的 แปลว่า "ผู้ชายคนนั้น" เป็นเนื้อคำถาม ไม่ใช่ป้ายชื่อผู้พูด
        """
        for turn in listening.speech_turns(self.items[1]):
            if turn["who"] == "q":
                continue
            self.assertFalse(turn["text"].startswith(("女：", "男：", "女:", "男:")))

    def test_คำถามอยู่ช่วงสุดท้ายเสมอ(self):
        """เครื่องเล่นเว้นจังหวะยาวก่อนช่วง q — ถ้าลำดับเพี้ยนจะเว้นผิดที่"""
        for n in (1, 2, 21, 31):
            turns = listening.speech_turns(self.items[n])
            self.assertEqual(turns[-1]["who"], "q", f"ข้อ {n}")

    def test_บทเล่าเรื่องไม่มีผู้พูดใช้_n(self):
        turns = listening.speech_turns(self.items[33])
        self.assertEqual(turns[0]["who"], "n")

    def test_ต่อกลับเป็นบทเดิมได้ครบ(self):
        """ช่วงพูดกับบทเต็มต้องเป็นเนื้อเดียวกัน ไม่งั้นที่ได้ยินกับที่เห็นตอนเฉลยจะไม่ตรงกัน"""
        import re

        item = self.items[21]
        joined = "".join(t["text"] for t in listening.speech_turns(item))
        strip = lambda t: re.sub(r"[，。！？、]", "", t)
        self.assertEqual(strip(joined), strip(listening.speech_text(item)))


class DisplayTests(TestCase):
    def test_ห้ามแสดงบทพูดก่อนตอบ(self):
        """ข้อฟังมี group ที่เก็บบทไว้เหมือนข้ออ่าน — ถ้าไม่ดักไว้บทจะถูกพิมพ์ขึ้นจอ
        แล้วผู้เรียนอ่านเอาได้โดยไม่ต้องฟัง
        """
        q = make_listening_question()
        view = reading.build(q)

        self.assertTrue(view.is_listening)
        self.assertEqual(view.passage_html, "")
        self.assertNotIn("下雨了", view.passage_html)
        self.assertEqual(view.prompt, "男的是什么意思？")

    def test_บอกหมายเลขข้อให้เครื่องเล่นไปดึงบทเอง(self):
        q = make_listening_question()
        self.assertEqual(reading.build(q).question_id, q.pk)

    def test_บทไม่โผล่ในหน้าเว็บที่ส่งออกไป(self):
        """ด่านสุดท้าย — ต่อให้ view ถูก เทมเพลตก็ยังทำหลุดได้
        ถ้าบทอยู่ในหน้า ผู้เรียนกดดูซอร์สครั้งเดียวก็อ่านคำตอบได้
        """
        from django.template.loader import render_to_string

        q = make_listening_question(script="下雨了，出门时别忘了带伞。")
        html = render_to_string("core/partials/question_body.html", {"q": reading.build(q)})

        self.assertNotIn("下雨了", html)
        self.assertNotIn("别忘了带伞", html)
        self.assertIn(f"listenPlayer({q.pk})", html)   # เครื่องเล่นไปดึงเอาเอง


class ScriptEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        VocabItem.objects.create(hanzi="詞", pinyin="ci", meaning_th="ความหมาย", hsk_level=5)
        cls.learner, _ = create_learner(
            username="L", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60))
        cls.question = make_listening_question()

    def test_ต้องล็อกอินก่อนถึงจะขอบทได้(self):
        res = self.client.get(reverse("listen_script", args=[self.question.pk]))
        self.assertEqual(res.status_code, 302)

    def test_ล็อกอินแล้วได้บทกลับมา(self):
        self.client.login(username="L", password="passpass1")
        res = self.client.get(reverse("listen_script", args=[self.question.pk]))
        self.assertEqual(res.json()["script"], self.question.audio_script)

    def test_ข้อที่ไม่มีบทตอบ404_ไม่ใช่ส่งค่าว่างเงียบๆ(self):
        """ส่งค่าว่างเงียบๆ = ผู้เรียนกดฟังแล้วไม่มีอะไรเกิดขึ้นและไม่รู้ว่าทำไม"""
        q = Question.objects.create(
            qtype=QuestionType.READING_MC, section=Section.READING,
            status=QuestionStatus.ACTIVE, prompt_zh="อ่าน", answer_text="ก")
        self.client.login(username="L", password="passpass1")
        res = self.client.get(reverse("listen_script", args=[q.pk]))
        self.assertEqual(res.status_code, 404)


class ImportTests(TestCase):
    def test_ไม่เปิดใช้ข้อที่ไม่มีเฉลยแม้จะมีบทแล้ว(self):
        """มีเสียงแต่ไม่มีเฉลย = ตรวจถูกผิดไม่ได้ ปล่อยเข้าชุดฝึกไม่ได้"""
        from core.management.commands.import_listening import Command
        self.assertTrue(hasattr(Command, "handle"))

        q = Question.objects.create(
            qtype=QuestionType.LISTENING_MC, section=Section.LISTENING,
            status=QuestionStatus.DRAFT, prompt_zh="?", answer_text="",
            audio_script="มีบทแล้ว",
            source_type=SourceType.OFFICIAL_PAST_PAPER, source_ref="X ข้อ 1")
        self.assertEqual(q.status, QuestionStatus.DRAFT)


class ExplainTests(TestCase):
    """ชี้ประโยคที่มีคำตอบ — ชี้ผิดแย่กว่าไม่ชี้"""

    SCRIPT = "下雨了，出门时别忘了带伞。放心吧，忘不了。"

    def test_ชี้ประโยคเมื่อคำตอบอยู่ในบทตรงๆ(self):
        found = listen_explain.answer_sentence(self.SCRIPT, "他会带伞的")
        self.assertIsNotNone(found)
        self.assertIn("带伞", found["sentence"])
        self.assertEqual(found["index"], 0)

    def test_ไม่ชี้เมื่อคำตอบเป็นการตีความ(self):
        """คำตอบที่ต้องสรุปเอาเองไม่มีอยู่ในบท ชี้มั่วจะทำให้ผู้เรียนจำผิด"""
        self.assertIsNone(listen_explain.answer_sentence(self.SCRIPT, "他很生气"))

    def test_คำตอบว่างต้องไม่ระเบิด(self):
        self.assertIsNone(listen_explain.answer_sentence(self.SCRIPT, ""))
        self.assertIsNone(listen_explain.answer_sentence("", "อะไรก็ได้"))

    def test_ประโยคยาวไม่ชนะเพราะมีคำทั่วไปเยอะกว่า(self):
        """ถ้าไม่ตัดคำอย่าง 的 了 是 ออก ประโยคที่ยาวที่สุดจะถูกชี้เสมอ"""
        script = "我今天很累了。他会带伞的。"
        found = listen_explain.answer_sentence(script, "他会带伞的")
        self.assertEqual(found["index"], 1)

    def test_ตัดคำถามท้ายบทออกก่อนหาคำยาก(self):
        """คำในตัวคำถามอยู่บนจอให้อ่านอยู่แล้ว ไม่ใช่คำที่ต้องฟังให้ออก"""
        q = make_listening_question(script="他出差了。谁出差了？")
        q.prompt_zh = "谁出差了？"
        q.save()
        self.assertEqual(listen_explain.body_only(q), "他出差了。")

    def test_การ์ดเฉลยไฮไลต์ประโยคที่มีคำตอบ(self):
        from django.template.loader import render_to_string

        q = make_listening_question(script=self.SCRIPT, answer="他会带伞的")
        html = render_to_string("core/partials/listen_transcript.html",
                                {"question": q, "lx": listen_explain.explain(q)})
        self.assertIn("hitline", html)
        self.assertIn("ประโยคที่มีคำตอบอยู่", html)

    def test_การ์ดเฉลยบอกตรงๆ_เมื่อชี้ไม่ได้(self):
        """เงียบไปเฉยๆ ทำให้ผู้เรียนคิดว่าระบบพัง — ต้องบอกว่าข้อนี้ต้องสรุปเอง"""
        from django.template.loader import render_to_string

        q = make_listening_question(script=self.SCRIPT, answer="他很生气")
        html = render_to_string("core/partials/listen_transcript.html",
                                {"question": q, "lx": listen_explain.explain(q)})
        self.assertNotIn("hitline", html)
        self.assertIn("ต้องฟังแล้วสรุปเอง", html)


class FixtureFallbackTests(TestCase):
    """บนเซิร์ฟเวอร์ไม่มี data/exam_corpus/ (อยู่ใน .gitignore และ .dockerignore)
    ถ้าไม่มีทางสำรอง คำสั่งจะเงียบแล้วไม่ทำอะไร และไม่มีใครรู้ว่าทำไมข้อฟังไม่โผล่
    """

    def test_มีไฟล์สำรองอยู่ในรีโปจริง(self):
        import json
        from pathlib import Path

        from django.conf import settings

        path = Path(settings.BASE_DIR) / "data" / "listening_fixture.json"
        self.assertTrue(path.exists(), "ไม่มี listening_fixture.json — รัน export_listening")

        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(sum(len(v) for v in data.values()), 200)

    def test_ไฟล์สำรองแปลงกลับเป็นข้อได้ครบทุกช่อง(self):
        """ถ้าโครงของ ListeningItem เปลี่ยนแล้วไม่ได้ export ใหม่ จะพังตรงนี้"""
        import json
        from pathlib import Path

        from django.conf import settings

        data = json.loads(
            (Path(settings.BASE_DIR) / "data" / "listening_fixture.json")
            .read_text(encoding="utf-8"))
        rows = next(iter(data.values()))
        item = listening.ListeningItem(**rows[0])

        self.assertTrue(item.script)
        self.assertTrue(item.question_zh)
        self.assertTrue(listening.speech_text(item))
