"""เติมรูปพินอินที่ออกเสียงจริง (tone sandhi ของ 一 กับ 不)

    python manage.py fix_pinyin_sandhi           # ดูก่อน ไม่เขียนอะไร
    python manage.py fix_pinyin_sandhi --apply   # เขียนจริง

**ไม่มีการคำนวณเกิดขึ้นในไฟล์นี้เลย** ตารางข้างล่างคัดมาจากลิสต์คำศัพท์ทางการ
HSK 2012 (glxxyz/hskhsk.com ซึ่งเป็นแหล่งที่ data/vocab/hsk5_merged.json อ้างไว้เอง)
วางเป็นค่าคงที่เพื่อให้เห็นใน diff ตอนรีวิวโค้ด และเพื่อไม่ต้องต่อเน็ตตอนรัน

ทำไมไม่ให้เครื่องคำนวณเอง — วัดแล้วสองรอบได้ผลตรงกัน:
    pypinyin เปิด sandhi   เปลี่ยน 26 คำ · ทำของถูกให้ผิด 21 คำ (81%)
    lookup จากลิสต์ทางการ   เปลี่ยน 13 คำ · ทำของถูกให้ผิด 0 คำ
ตัวอย่างความพัง: pypinyin เปลี่ยน 大使馆 เป็น dàshíguǎn ซึ่งชนกับเสียงของ 时/实/食
เป็นความผิดคลาสเดียวกับกรณี 事物/食物 ที่ QUALITY_REPORT §4 เคยจับได้ว่า
"เป็นจุดตัดสินในพาร์ทฟัง"

**ห้ามแตะคอลัมน์ pinyin เดิมในทุกกรณี** — เขียนลง pinyin_sandhi เท่านั้น
เพราะผู้เรียนจะเจอรูปพจนานุกรมในหนังสือและ Pleco ตลอด ต้องเห็นทั้งสองรูปคู่กัน

กฎที่ *ไม่* แตะ:
  三声 sandhi (处理 老板 展览 …)  ธรรมเนียมทุกแหล่งตรงกันว่าไม่เขียน และขึ้นกับ
                                 โครงสร้างวลี ไม่ใช่ขึ้นกับคำ จึงเก็บลงคอลัมน์ของคำไม่ได้
  เสียงเบา 轻声                    เป็นคนละเรื่องกับ sandhi ต้องตรวจแยก
"""
from django.core.management.base import BaseCommand

from core.models import VocabItem

# 汉字: (พินอินเดิมที่คาดว่าอยู่ในฐาน, รูปที่ออกเสียงจริง, กฎ)
# ถ้าค่าในฐานไม่ตรงคอลัมน์แรก แปลว่ามีคนแก้ไปแล้ว → ข้าม ไม่เขียนทับ
SANDHI = {
    "一下":    ("yīxià",       "yíxià",       "一 + เสียง 4"),
    "一切":    ("yīqiè",       "yíqiè",       "一 + เสียง 4"),
    "一样":    ("yīyàng",      "yíyàng",      "一 + เสียง 4"),
    "一共":    ("yīgòng",      "yígòng",      "一 + เสียง 4"),
    "一再":    ("yīzài",       "yízài",       "一 + เสียง 4"),
    "一律":    ("yīlǜ",        "yílǜ",        "一 + เสียง 4"),
    "一辈子":  ("yībèizi",     "yíbèizi",     "一 + เสียง 4"),
    "一边":    ("yībiān",      "yìbiān",      "一 + เสียง 1"),
    "一举两得": ("yī jǔ liǎng dé", "yìjǔliǎngdé", "一 + เสียง 3"),
    "不但":    ("bùdàn",       "búdàn",       "不 + เสียง 4"),
    "不过":    ("bùguò",       "búguò",       "不 + เสียง 4"),
    "不断":    ("bùduàn",      "búduàn",      "不 + เสียง 4"),
    "不耐烦":  ("bùnàifán",    "búnàifán",    "不 + เสียง 4"),
}


class Command(BaseCommand):
    help = "เติมรูปพินอินที่ออกเสียงจริงจากลิสต์ทางการ HSK 2012 (13 คำ)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="เขียนจริง (ค่าตั้งต้นคือดูอย่างเดียว)")

    def handle(self, *args, **opts):
        found = {v.hanzi: v for v in VocabItem.objects.filter(hanzi__in=SANDHI)}

        write, skip, missing, already = [], [], [], []
        for hanzi, (expect_old, sandhi, rule) in SANDHI.items():
            vocab = found.get(hanzi)
            if not vocab:
                missing.append(hanzi)
                continue
            if vocab.pinyin_sandhi == sandhi:
                already.append(hanzi)
                continue
            if vocab.pinyin.strip() != expect_old:
                skip.append((hanzi, vocab.pinyin, expect_old))
                continue
            write.append((vocab, sandhi, rule))

        self.stdout.write(f"{'คำ':<10}{'ในฐาน (รูปพจนานุกรม)':<24}{'รูปที่ออกเสียงจริง':<20}กฎ")
        self.stdout.write("─" * 74)
        for vocab, sandhi, rule in write:
            self.stdout.write(f"{vocab.hanzi:<10}{vocab.pinyin:<24}{sandhi:<20}{rule}")

        if skip:
            self.stdout.write(self.style.WARNING("\nข้าม — ค่าในฐานไม่ตรงกับที่คาด (มีคนแก้ไปแล้ว):"))
            for hanzi, actual, expect in skip:
                self.stdout.write(f"  {hanzi}  ในฐาน '{actual}'  คาดว่า '{expect}'")
        if missing:
            self.stdout.write(self.style.WARNING(f"\nไม่มีในคลัง: {' '.join(missing)}"))
        if already:
            self.stdout.write(f"\nมีค่าอยู่แล้ว {len(already)} คำ: {' '.join(already)}")

        if not write:
            self.stdout.write(self.style.SUCCESS("\nไม่มีอะไรต้องเขียน"))
            return

        if not opts["apply"]:
            self.stdout.write(self.style.WARNING(
                f"\n[ดูอย่างเดียว] จะเขียน {len(write)} คำ — เติม --apply เพื่อเขียนจริง"
                "\nคอลัมน์ pinyin เดิมไม่ถูกแตะในทุกกรณี"
            ))
            return

        for vocab, sandhi, _rule in write:
            vocab.pinyin_sandhi = sandhi
            vocab.pinyin_sandhi_source = "official_list"
        VocabItem.objects.bulk_update(
            [v for v, _, _ in write], ["pinyin_sandhi", "pinyin_sandhi_source"])
        self.stdout.write(self.style.SUCCESS(
            f"\nเขียนแล้ว {len(write)} คำ — คอลัมน์ pinyin เดิมไม่ถูกแตะ"
        ))
