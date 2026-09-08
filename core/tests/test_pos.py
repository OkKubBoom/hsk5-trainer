"""ชนิดของคำ — ผู้ใช้ขอมาเอง ("อยากให้เพิ่มชนิดของคำศัพท์ … เป็นตัวย่อหลังคำก็ได้")

สำคัญกว่าที่คิด: ภาษาจีนไม่ผันรูปตามชนิดคำ 影响 เป็นได้ทั้งกริยาและนาม
โดยหน้าตาไม่เปลี่ยนเลย และข้อเรียงคำตัดสินถูกผิดที่ชนิดคำล้วนๆ
"""
from django.template import Context, Template
from django.test import TestCase

from core import pos
from core.models import VocabItem


def _v(**kw):
    return VocabItem.objects.create(
        hanzi=kw.pop("hanzi", "影响"), pinyin="yǐngxiǎng",
        meaning_th="ส่งผล", hsk_level=5, **kw)


class PosTests(TestCase):
    def test_a_word_can_have_more_than_one_type(self):
        # บอกว่า 影响 เป็นกริยาอย่างเดียวคือข้อมูลผิด ผู้เรียนจะเรียงประโยคผิดตาม
        v = _v(tags=["n", "v", "abstract"])
        self.assertEqual(pos.short(v), "ก. · น.")

    def test_order_is_fixed_not_whatever_the_tags_happen_to_be(self):
        a = _v(hanzi="甲", tags=["n", "v"])
        b = _v(hanzi="乙", tags=["v", "n"])
        self.assertEqual(pos.short(a), pos.short(b))

    def test_non_type_tags_are_ignored(self):
        v = _v(tags=["adj", "needs_review", "review:warn", "essay_useful"])
        self.assertEqual(pos.short(v), "คุณ.")

    def test_no_type_tag_gives_an_empty_string(self):
        self.assertEqual(pos.short(_v(tags=["abstract"])), "")
        self.assertEqual(pos.short(_v(hanzi="丙", tags=[])), "")

    def test_spelling_variants_from_different_imports_are_merged(self):
        self.assertEqual(pos.short(_v(tags=["verb"])), pos.short(_v(hanzi="丁", tags=["v"])))

    def test_a_connector_is_not_listed_twice(self):
        # conn เป็นหมวดของหน้าคำเชื่อม ไม่ใช่ชนิดคำคนละตัวกับ conj
        v = _v(hanzi="虽然", tags=["conj", "conn"])
        self.assertEqual(pos.short(v), "สัน.")

    def test_a_connector_without_conj_still_shows(self):
        self.assertEqual(pos.short(_v(hanzi="另外", tags=["conn"])), "เชื่อม")

    def test_works_on_a_plain_dict_from_values(self):
        # listen_explain ส่ง dict จาก .values() ไม่ใช่ VocabItem
        self.assertEqual(pos.short({"tags": ["v"]}), "ก.")
        self.assertEqual(pos.short({}), "")

    def test_full_names_are_available_for_the_tooltip(self):
        v = _v(tags=["v"])
        self.assertIn("คำกริยา", pos.title(v))

    def test_every_abbreviation_is_unique(self):
        shorts = [s for _, (s, _) in pos.POS]
        self.assertEqual(len(shorts), len(set(shorts)), "ตัวย่อซ้ำกัน อ่านแล้วแยกไม่ออก")


class PosTemplateTests(TestCase):
    def test_filters_render(self):
        v = _v(tags=["n", "v"])
        out = Template("{% load hsk %}{{ v|pos_short }}|{{ v|pos_title }}").render(
            Context({"v": v}))
        short, title = out.split("|")
        self.assertEqual(short, "ก. · น.")
        self.assertIn("动词", title)

    def test_filters_are_safe_on_a_word_with_no_tags(self):
        out = Template("{% load hsk %}[{{ v|pos_short }}]").render(
            Context({"v": _v(hanzi="戊", tags=[])}))
        self.assertEqual(out, "[]")


class PosCoverageTests(TestCase):
    """เช็คของจริงในฐาน ไม่ใช่แค่ของที่แต่งขึ้นในเทสต์"""

    def test_most_of_the_library_has_a_type(self):
        from django.conf import settings  # noqa: F401
        total = VocabItem.objects.count()
        if total < 100:
            self.skipTest("ฐานทดสอบว่าง — เช็คนี้มีความหมายเฉพาะกับฐานจริง")
        known = sum(1 for v in VocabItem.objects.all() if pos.of(v))
        self.assertGreater(known / total, 0.8)
