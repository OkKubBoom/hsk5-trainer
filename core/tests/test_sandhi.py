"""เทสต์การเติมรูปพินอินที่ออกเสียงจริง

งานนี้อันตรายกว่าที่เห็น เพราะการ "แก้พินอินให้ถูก" ด้วยเครื่องมืออัตโนมัติ
ทำของที่ถูกอยู่แล้วให้ผิดได้ 81% (วัดแล้ว: pypinyin เปิด sandhi เปลี่ยน 26 คำ
ผิด 21 คำ) เทสต์ชุดนี้ล็อกไว้ว่าเราแตะเฉพาะ 13 คำที่มีคำตอบจากลิสต์ทางการ
และไม่แตะกลุ่มที่เป็นกับดัก
"""
from django.core.management import call_command
from django.test import TestCase

from core.management.commands.fix_pinyin_sandhi import SANDHI
from core.models import VocabItem

# กลุ่มที่ห้ามแตะ พร้อมเหตุผล
UNTOUCHED = {
    # 三声 sandhi — บังคับตอนออกเสียง แต่ธรรมเนียมทุกแหล่งไม่เขียน
    "处理": "chǔlǐ", "老板": "lǎobǎn", "展览": "zhǎnlǎn",
    "保险": "bǎoxiǎn", "管理": "guǎnlǐ",
    # 一 ท้ายคำ / เลขลำดับ — ไม่เข้ากฎ
    "万一": "wànyī", "唯一": "wéiyī", "第一": "dìyī", "统一": "tǒngyī",
    # 不 หน้าเสียง 1/2/3 — ไม่เปลี่ยน
    "不管": "bùguǎn", "不如": "bùrú", "不仅": "bùjǐn",
    # กับดัก: ตัวอักษรมีเสียง yi/bu แต่ไม่ใช่ 一/不
    "医生": "yīshēng", "医院": "yīyuàn", "依然": "yīrán", "步骤": "bùzhòu",
    # มี sandhi อยู่ในคอลัมน์เดิมแล้ว ห้ามแก้ซ้ำ
    "一旦": "yídàn",
}


class SandhiCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for hanzi, (old, _new, _rule) in SANDHI.items():
            VocabItem.objects.create(hanzi=hanzi, pinyin=old,
                                     meaning_th=f"ความหมาย {hanzi}", hsk_level=5)
        for hanzi, pinyin in UNTOUCHED.items():
            VocabItem.objects.create(hanzi=hanzi, pinyin=pinyin,
                                     meaning_th=f"ความหมาย {hanzi}", hsk_level=5)

    def test_ดูอย่างเดียวต้องไม่เขียนอะไร(self):
        """ค่าตั้งต้นต้องปลอดภัย ต้องพิมพ์ --apply ถึงจะเขียน"""
        call_command("fix_pinyin_sandhi")
        self.assertFalse(VocabItem.objects.exclude(pinyin_sandhi="").exists())

    def test_เขียนครบ13คำตามลิสต์ทางการ(self):
        call_command("fix_pinyin_sandhi", apply=True)
        for hanzi, (_old, expected, _rule) in SANDHI.items():
            with self.subTest(word=hanzi):
                v = VocabItem.objects.get(hanzi=hanzi)
                self.assertEqual(v.pinyin_sandhi, expected)
                self.assertEqual(v.pinyin_sandhi_source, "official_list")

    def test_ห้ามแตะคอลัมน์พินอินเดิม(self):
        """ผู้เรียนต้องยังเห็นรูปพจนานุกรมที่ตรงกับหนังสือและ Pleco"""
        call_command("fix_pinyin_sandhi", apply=True)
        for hanzi, (old, _new, _rule) in SANDHI.items():
            with self.subTest(word=hanzi):
                self.assertEqual(VocabItem.objects.get(hanzi=hanzi).pinyin, old)

    def test_กลุ่มที่ห้ามแตะต้องไม่ถูกแตะเลย(self):
        """กับดักหลัก — 医生 依然 步骤 มีเสียง yi/bu แต่ไม่ใช่อักษร 一/不
        และ 处理 老板 เป็น 三声 sandhi ซึ่งธรรมเนียมไม่เขียน
        """
        call_command("fix_pinyin_sandhi", apply=True)
        for hanzi, pinyin in UNTOUCHED.items():
            with self.subTest(word=hanzi):
                v = VocabItem.objects.get(hanzi=hanzi)
                self.assertEqual(v.pinyin, pinyin)
                self.assertEqual(v.pinyin_sandhi, "")

    def test_รันซ้ำได้ผลเท่าเดิม(self):
        call_command("fix_pinyin_sandhi", apply=True)
        first = dict(VocabItem.objects.values_list("hanzi", "pinyin_sandhi"))
        call_command("fix_pinyin_sandhi", apply=True)
        self.assertEqual(dict(VocabItem.objects.values_list("hanzi", "pinyin_sandhi")), first)

    def test_ค่าในฐานไม่ตรงที่คาดต้องข้าม_ไม่เขียนทับ(self):
        """ถ้าครูแก้พินอินไปแล้ว ห้ามเขียนทับงานของคน"""
        v = VocabItem.objects.get(hanzi="一样")
        v.pinyin = "ครูแก้ไว้แล้ว"
        v.save()

        call_command("fix_pinyin_sandhi", apply=True)
        v.refresh_from_db()
        self.assertEqual(v.pinyin, "ครูแก้ไว้แล้ว")
        self.assertEqual(v.pinyin_sandhi, "")

    def test_ไม่มีคำไหนมาจาก_ai(self):
        """ป้ายที่มาต้องตรงความจริง — ข้อมูลนี้มาจากลิสต์ทางการ ไม่ใช่ AI
        ถ้าติดป้าย ✱✱✱ ให้ของที่มาจากแหล่งทางการ ป้ายจะเฟ้อ
        แล้ววันที่ผลตรวจเรียงความติดป้ายเดียวกัน ผู้เรียนจะเลิกสนใจ
        """
        call_command("fix_pinyin_sandhi", apply=True)
        sources = set(VocabItem.objects.exclude(pinyin_sandhi="")
                      .values_list("pinyin_sandhi_source", flat=True))
        self.assertEqual(sources, {"official_list"})
