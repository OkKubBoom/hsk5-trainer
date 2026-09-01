"""สร้างภาพโจทย์สำหรับเรียงความข้อ 100 (看图写作)

    python manage.py make_scenes

**ทำไมวาดเอง ไม่ใช้ภาพจากที่อื่น**
  ภาพจากข้อสอบจริง  ติดลิขสิทธิ์ ห้ามเข้าเวอร์ชันขาย (D6)
  ภาพจากเว็บภายนอก   ต้องต่อเน็ตตอนแสดง และสัญญาอนุญาตเปลี่ยนได้ทีหลัง
  ภาพที่ AI สร้าง     ตรวจสอบที่มาไม่ได้ และสร้างซ้ำให้เหมือนเดิมไม่ได้
วาดเองด้วย SVG จบทุกปัญหา: เป็นของเรา 100% ไฟล์เล็ก คมทุกความละเอียด
ไม่ต้องต่อเน็ต และแก้ทีหลังได้ด้วยการแก้โค้ดบรรทัดเดียว

**ภาพต้องอ่านออกโดยไม่ต้องมีคำอธิบาย**
ใช้ท่าทางกับของประกอบฉากบอกเรื่อง ไม่ใส่ตัวอักษรลงในภาพเด็ดขาด —
ใส่ตัวจีนลงไปคือให้คำศัพท์ฟรี ใส่ตัวไทยคือบอกคำตอบ ทั้งสองอย่างทำลายโจทย์

**คำบรรยายฉาก** เก็บไว้ใน data/essay_scenes.json ใช้ตอนส่งให้ตรวจเท่านั้น
เพราะผลตรวจส่งผ่านข้อความ ผู้ตรวจไม่เห็นภาพ ถ้าไม่บอกว่าภาพเป็นอะไร
จะตัดสินไม่ได้ว่าผู้เรียนเขียนตรงภาพหรือเปล่า (เกณฑ์ 内容与图片相关)
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

W, H = 480, 320
INK = "#2F3A38"
SOFT = "#9DB0AB"
ACCENT = "#1E6B5D"
WARM = "#D69E2E"
SKY = "#EAF1EF"

# คนสูงราว 120px บนผืน 320px — สัดส่วนเดียวกับภาพในข้อสอบจริง
# เคยวาดเล็กกว่านี้แล้วคนกลายเป็นจุดเล็กๆ มุมภาพ มองไม่ออกว่าทำอะไรอยู่
UNIT = 2.3


def person(x, y, s=1.0, *, arms="down", color=INK, head=True):
    """คนหนึ่งคน — เส้นล้วน ไม่มีหน้าตา

    ไม่ใส่หน้าตาโดยตั้งใจ ผู้เรียนจะได้ไม่เสียเวลาบรรยายสีหน้า
    ซึ่งไม่ใช่สิ่งที่ข้อสอบวัด และเป็นจุดที่คนไทยชอบเขียนเกินความจำเป็น
    """
    s = s * UNIT
    a = {
        "down":  f"M{x-11*s},{y-14*s} L{x},{y-24*s} L{x+11*s},{y-14*s}",
        "up":    f"M{x-12*s},{y-40*s} L{x},{y-26*s} L{x+12*s},{y-40*s}",
        "front": f"M{x-15*s},{y-22*s} L{x},{y-26*s} L{x+15*s},{y-22*s}",
        "one":   f"M{x-11*s},{y-14*s} L{x},{y-24*s} L{x+13*s},{y-34*s}",
        "walk":  f"M{x-12*s},{y-16*s} L{x},{y-24*s} L{x+12*s},{y-30*s}",
    }[arms]
    legs = (f"M{x-10*s},{y} L{x},{y-12*s} L{x+10*s},{y}" if arms != "walk"
            else f"M{x-13*s},{y} L{x},{y-12*s} L{x+11*s},{y-3*s}")
    out = []
    if head:
        out.append(f'<circle cx="{x}" cy="{y-46*s}" r="{7.5*s}" fill="none" '
                   f'stroke="{color}" stroke-width="{2.4*s}"/>')
    out.append(
        f'<path d="M{x},{y-38*s} L{x},{y-12*s} {legs} {a}" fill="none" '
        f'stroke="{color}" stroke-width="{2.4*s}" stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
    )
    return "".join(out)


def sitting(x, y, s=1.0, color=INK, face=1):
    """คนนั่ง — ขาพับเป็นมุมฉาก ต่างจากคนยืนชัดเจนแม้ภาพเล็ก

    face=1 หันขวา · face=-1 หันซ้าย ใช้ตอนวาดคนนั่งหันหน้าเข้าหากันคนละฝั่งโต๊ะ
    """
    s = s * UNIT
    d = face
    return (
        f'<circle cx="{x}" cy="{y-44*s}" r="{7.5*s}" fill="none" stroke="{color}" '
        f'stroke-width="{2.4*s}"/>'
        f'<path d="M{x},{y-36*s} L{x},{y-15*s} L{x+16*s*d},{y-15*s} L{x+16*s*d},{y} '
        f'M{x},{y-30*s} L{x+15*s*d},{y-21*s}" fill="none" stroke="{color}" '
        f'stroke-width="{2.4*s}" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def box(x, y, w, h, color=SOFT, fill="none", r=3):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" '
            f'stroke="{color}" stroke-width="2.6"/>')


def table(x, y, w=110):
    return (f'<path d="M{x},{y} L{x+w},{y} M{x+10},{y} L{x+10},{y+46} '
            f'M{x+w-10},{y} L{x+w-10},{y+46}" fill="none" stroke="{INK}" '
            f'stroke-width="3" stroke-linecap="round"/>')


def tree(x, y, s=1.0):
    return (f'<path d="M{x},{y} L{x},{y-40*s}" stroke="{INK}" stroke-width="{4*s}" '
            f'stroke-linecap="round"/>'
            f'<circle cx="{x}" cy="{y-66*s}" r="{30*s}" fill="{SKY}" stroke="{ACCENT}" '
            f'stroke-width="2.8"/>')


def ground(y=286):
    return f'<path d="M20,{y} L{W-20},{y}" stroke="{SOFT}" stroke-width="2.6" stroke-linecap="round"/>'


SCENES = [
    {
        "id": "library",
        "title_th": "อ่านหนังสือในห้องสมุด",
        "describe_th": "ผู้หญิงคนหนึ่งนั่งอ่านหนังสือที่โต๊ะในห้องสมุด มีชั้นหนังสือสูงอยู่ด้านหลัง "
                       "และมีหนังสือวางซ้อนอยู่บนโต๊ะอีกหลายเล่ม",
        "body": (
            box(320, 46, 132, 200) +
            "".join(f'<path d="M324,{y} L448,{y}" stroke="{SOFT}" stroke-width="2.4"/>'
                    for y in (96, 146, 196)) +
            "".join(box(330 + i * 28, 56, 20, 36, WARM) for i in range(4)) +
            table(60, 216, 210) +
            sitting(110, 216) +
            box(196, 196, 56, 18, INK) + box(200, 178, 46, 16, SOFT) +
            ground(286)
        ),
    },
    {
        "id": "family_meal",
        "title_th": "ครอบครัวกินข้าวด้วยกัน",
        "describe_th": "คนสามคนนั่งล้อมโต๊ะกินข้าวเย็นด้วยกัน บนโต๊ะมีจานอาหารหลายจาน "
                       "ทุกคนดูมีความสุข",
        "body": (
            table(120, 214, 250) +
            "".join(f'<ellipse cx="{cx}" cy="208" rx="22" ry="8" fill="none" '
                    f'stroke="{WARM}" stroke-width="2.6"/>' for cx in (185, 245, 305)) +
            sitting(80, 214, 0.95) +
            sitting(410, 214, 0.95, face=-1) +
            person(245, 168, 0.62, arms="front") +
            ground(286)
        ),
    },
    {
        "id": "bus_rain",
        "title_th": "รอรถเมล์ตอนฝนตก",
        "describe_th": "ผู้ชายคนหนึ่งยืนรอรถเมล์อยู่ที่ป้าย กางร่มเพราะฝนกำลังตก "
                       "มีรถเมล์กำลังวิ่งเข้ามาจากทางขวา",
        "body": (
            "".join(f'<path d="M{x},{22 + (x % 26)} L{x-7},{54 + (x % 26)}" stroke="{ACCENT}" '
                    f'stroke-width="2.2" stroke-linecap="round" opacity=".65"/>'
                    for x in range(40, 460, 30)) +
            f'<path d="M56,116 A62,62 0 0 1 180,116 Z" fill="{SKY}" stroke="{ACCENT}" stroke-width="3"/>'
            f'<path d="M118,116 L118,196" stroke="{INK}" stroke-width="2.6" stroke-linecap="round"/>' +
            person(118, 286, 0.86, arms="up") +
            box(288, 158, 164, 96, INK, fill=SKY) +
            box(302, 174, 46, 34, SOFT) + box(358, 174, 46, 34, SOFT) +
            f'<circle cx="322" cy="258" r="14" fill="none" stroke="{INK}" stroke-width="3"/>'
            f'<circle cx="420" cy="258" r="14" fill="none" stroke="{INK}" stroke-width="3"/>' +
            ground(286)
        ),
    },
    {
        "id": "park_run",
        "title_th": "วิ่งออกกำลังกายในสวน",
        "describe_th": "ผู้ชายคนหนึ่งกำลังวิ่งออกกำลังกายในสวนสาธารณะตอนเช้า "
                       "มีต้นไม้และม้านั่งอยู่ข้างทาง มีคนแก่นั่งพักอยู่บนม้านั่ง",
        "body": (
            tree(58, 286, 1.0) + tree(438, 286, 0.8) +
            f'<circle cx="392" cy="62" r="24" fill="none" stroke="{WARM}" stroke-width="3"/>' +
            f'<path d="M136,244 L246,244 M148,244 L148,278 M234,244 L234,278" fill="none" '
            f'stroke="{SOFT}" stroke-width="3" stroke-linecap="round"/>' +
            sitting(168, 244, 0.72, color=SOFT) +
            person(320, 286, 0.9, arms="walk") +
            ground(286)
        ),
    },
    {
        "id": "interview",
        "title_th": "สัมภาษณ์งาน",
        "describe_th": "ผู้หญิงคนหนึ่งกำลังถูกสัมภาษณ์งาน นั่งอยู่ฝั่งตรงข้ามโต๊ะกับผู้สัมภาษณ์ "
                       "ที่ถือเอกสารอยู่ในมือ บนโต๊ะมีแฟ้มเอกสาร",
        "body": (
            box(300, 40, 130, 86, SOFT, fill=SKY) +
            table(126, 216, 230) +
            box(206, 192, 70, 22, WARM) +
            sitting(86, 216, 0.95) +
            sitting(400, 216, 0.95, color=ACCENT, face=-1) +
            ground(286)
        ),
    },
    {
        "id": "supermarket",
        "title_th": "ซื้อของในซูเปอร์มาร์เก็ต",
        "describe_th": "ผู้หญิงคนหนึ่งกำลังเข็นรถเข็นเลือกซื้อของในซูเปอร์มาร์เก็ต "
                       "มีชั้นวางสินค้าเต็มไปด้วยของอยู่ด้านหลัง",
        "body": (
            box(268, 40, 186, 210) +
            "".join(f'<path d="M272,{y} L450,{y}" stroke="{SOFT}" stroke-width="2.4"/>'
                    for y in (98, 156, 214)) +
            "".join(box(278 + i * 32, 52, 22, 40, WARM) for i in range(5)) +
            "".join(box(278 + i * 32, 110, 22, 40, ACCENT) for i in range(5)) +
            "".join(box(278 + i * 32, 168, 22, 40, SOFT) for i in range(5)) +
            person(86, 286, 0.86, arms="front") +
            f'<path d="M126,222 L206,222 L194,268 L138,268 Z" fill="none" stroke="{INK}" stroke-width="3"/>'
            f'<circle cx="146" cy="280" r="10" fill="none" stroke="{INK}" stroke-width="2.6"/>'
            f'<circle cx="186" cy="280" r="10" fill="none" stroke="{INK}" stroke-width="2.6"/>' +
            ground(292)
        ),
    },
    {
        "id": "late_work",
        "title_th": "ทำงานดึกหน้าคอมพิวเตอร์",
        "describe_th": "ผู้ชายคนหนึ่งนั่งทำงานหน้าคอมพิวเตอร์จนดึก มีนาฬิกาบนผนังชี้เวลาดึกมาก "
                       "บนโต๊ะมีแก้วกาแฟและกองเอกสาร เขาดูเหนื่อย",
        "body": (
            f'<circle cx="392" cy="66" r="34" fill="none" stroke="{SOFT}" stroke-width="3"/>'
            f'<path d="M392,66 L392,42 M392,66 L408,76" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>'
            f'<path d="M74,52 A22,22 0 1 0 96,88 A26,26 0 0 1 74,52 Z" fill="{SKY}" stroke="{SOFT}" stroke-width="2.4"/>' +
            table(120, 218, 240) +
            box(224, 152, 84, 62, INK, fill=SKY) +
            f'<path d="M214,214 L318,214" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>' +
            box(150, 188, 28, 26, WARM) +
            box(330, 196, 34, 18, SOFT) +
            sitting(150, 218, 0.95) +
            ground(286)
        ),
    },
    {
        "id": "photo_trip",
        "title_th": "เที่ยวกับเพื่อนแล้วถ่ายรูป",
        "describe_th": "เพื่อนสองคนไปเที่ยวภูเขาด้วยกัน คนหนึ่งกำลังยกกล้องถ่ายรูปวิว "
                       "อีกคนยืนโบกมือ อากาศดี มีภูเขาอยู่ด้านหลัง",
        "body": (
            f'<path d="M20,254 L120,110 L216,254 Z" fill="{SKY}" stroke="{ACCENT}" stroke-width="3" stroke-linejoin="round"/>'
            f'<path d="M164,254 L262,132 L358,254 Z" fill="none" stroke="{SOFT}" stroke-width="3" stroke-linejoin="round"/>'
            f'<circle cx="412" cy="62" r="24" fill="none" stroke="{WARM}" stroke-width="3"/>' +
            person(140, 286, 0.86, arms="up") +
            person(300, 286, 0.86, arms="front") +
            box(280, 226, 40, 26, INK) +
            f'<circle cx="300" cy="239" r="7" fill="none" stroke="{INK}" stroke-width="2.4"/>' +
            ground(286)
        ),
    },
    {
        "id": "clinic",
        "title_th": "ไปหาหมอที่โรงพยาบาล",
        "describe_th": "หมอกำลังตรวจคนไข้ที่นั่งอยู่บนเตียง หมอสวมเสื้อกาวน์และถือหูฟัง "
                       "ในห้องตรวจของโรงพยาบาล",
        "body": (
            box(236, 200, 214, 62, SOFT, fill=SKY) +
            f'<path d="M252,262 L252,286 M434,262 L434,286" stroke="{SOFT}" stroke-width="3" stroke-linecap="round"/>' +
            sitting(300, 200, 0.9, face=-1) +
            person(110, 286, 0.86, arms="one", color=ACCENT) +
            f'<path d="M110,212 q-20,22 0,32 q20,-10 0,-32" fill="none" stroke="{ACCENT}" stroke-width="2.4"/>' +
            f'<path d="M40,58 L88,58 M64,34 L64,82" stroke="{WARM}" stroke-width="5" stroke-linecap="round"/>' +
            ground(286)
        ),
    },
    {
        "id": "moving_house",
        "title_th": "ย้ายบ้าน ขนของ",
        "describe_th": "คนสองคนกำลังช่วยกันขนกล่องย้ายบ้าน คนหนึ่งยกกล่องอยู่ "
                       "อีกคนวางกล่องซ้อนกันไว้หน้าบ้าน มีรถบรรทุกจอดอยู่",
        "body": (
            f'<path d="M18,150 L92,88 L166,150 Z" fill="none" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
            + box(34, 150, 116, 136, INK) + box(74, 208, 36, 78, SOFT) +
            box(180, 218, 56, 56, WARM) + box(180, 160, 56, 56, WARM) +
            person(280, 286, 0.8, arms="front") +
            box(258, 216, 50, 40, INK) +
            box(342, 176, 118, 74, SOFT, fill=SKY) +
            f'<circle cx="368" cy="258" r="13" fill="none" stroke="{INK}" stroke-width="2.8"/>'
            f'<circle cx="436" cy="258" r="13" fill="none" stroke="{INK}" stroke-width="2.8"/>' +
            ground(286)
        ),
    },
]


class Command(BaseCommand):
    help = "สร้างภาพโจทย์ SVG สำหรับ 书写第二部分 ข้อ 100"

    def handle(self, *args, **opts):
        out = Path(settings.BASE_DIR) / "static" / "scenes"
        out.mkdir(parents=True, exist_ok=True)

        index = []
        for scene in SCENES:
            svg = (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
                f'width="{W}" height="{H}" role="img" aria-label="{scene["title_th"]}">'
                f'<rect width="{W}" height="{H}" rx="12" fill="#FFFFFF"/>'
                f'{scene["body"]}</svg>'
            )
            (out / f'{scene["id"]}.svg').write_text(svg, encoding="utf-8")
            index.append({
                "id": scene["id"],
                "title_th": scene["title_th"],
                "describe_th": scene["describe_th"],
                "file": f'scenes/{scene["id"]}.svg',
            })
            self.stdout.write(f'  {scene["id"]}.svg — {scene["title_th"]}')

        data = Path(settings.BASE_DIR) / "data" / "essay_scenes.json"
        data.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"เขียนภาพ {len(index)} ฉาก และคำบรรยายที่ {data.name}"
        ))
        self.stdout.write(
            "คำบรรยายฉากใช้ตอนส่งให้ตรวจเท่านั้น ห้ามแสดงให้ผู้เรียนเห็นก่อนเขียน"
        )
