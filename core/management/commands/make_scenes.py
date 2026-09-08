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
SKIN = "#F2D9C2"
HAIR = "#3A322E"
# เสื้อคนละสีเพื่อให้แยกออกว่าเป็นคนละคน — ผู้เรียนต้องเล่าได้ว่า "ผู้ชายคนนั้น"
# กับ "ผู้หญิงคนนี้" ทำอะไรต่างกัน ถ้าทุกคนหน้าตาเหมือนกันหมดก็เล่าแยกไม่ได้
SHIRTS = ["#2E6F8E", "#C25E4A", "#5B8C5A", "#8A6BA8", "#C99A2E"]

# คนสูงราว 120px บนผืน 320px — สัดส่วนเดียวกับภาพในข้อสอบจริง
# เคยวาดเล็กกว่านี้แล้วคนกลายเป็นจุดเล็กๆ มุมภาพ มองไม่ออกว่าทำอะไรอยู่
UNIT = 2.3


def face(cx, cy, r, *, mood="neutral", look=1, color=INK):
    """หน้า — ตา 2 จุด กับปากที่เปลี่ยนตามอารมณ์

    **เดิมจงใจไม่วาดหน้า** ด้วยเหตุผลว่าผู้เรียนจะได้ไม่เสียเวลาบรรยายสีหน้า
    แต่ผู้ใช้เปิดมาแล้วถามว่า "ภาพไรนิ" — คือมองไม่ออกด้วยซ้ำว่าเป็นคน
    และเหตุผลเดิมกลับด้าน: ข้อ 看图写作 ให้คะแนน 内容与图片相关 การเล่าว่า
    ในภาพใครรู้สึกยังไงคือเนื้อหาที่ได้คะแนน ไม่ใช่ส่วนเกิน
    """
    eye = r * 0.17
    ex = r * 0.34
    ey = cy - r * 0.12
    mouth = {
        "happy":   f"M{cx-r*0.34},{cy+r*0.28} Q{cx},{cy+r*0.62} {cx+r*0.34},{cy+r*0.28}",
        "sad":     f"M{cx-r*0.30},{cy+r*0.50} Q{cx},{cy+r*0.18} {cx+r*0.30},{cy+r*0.50}",
        "tired":   f"M{cx-r*0.28},{cy+r*0.42} L{cx+r*0.28},{cy+r*0.42}",
        "neutral": f"M{cx-r*0.26},{cy+r*0.40} L{cx+r*0.26},{cy+r*0.40}",
    }[mood]
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{SKIN}" stroke="{color}" '
        f'stroke-width="{r*0.16:.2f}"/>'
        # ผมเป็นฝาครอบครึ่งบน ทำให้หัวอ่านออกว่าเป็นหัวคนแม้ภาพย่อเล็ก
        f'<path d="M{cx-r},{cy-r*0.18} A{r},{r} 0 0 1 {cx+r},{cy-r*0.18} '
        f'Q{cx},{cy-r*0.55} {cx-r},{cy-r*0.18} Z" fill="{HAIR}"/>'
        f'<circle cx="{cx-ex*look if look>0 else cx-ex}" cy="{ey}" r="{eye}" fill="{INK}"/>'
        f'<circle cx="{cx+ex}" cy="{ey}" r="{eye}" fill="{INK}"/>'
        f'<path d="{mouth}" fill="none" stroke="{INK}" stroke-width="{r*0.13:.2f}" '
        f'stroke-linecap="round"/>'
    )


def person(x, y, s=1.0, *, arms="down", color=INK, head=True,
           mood="neutral", shirt=0, look=1):
    """คนหนึ่งคนยืน — มีหน้า มีเสื้อ มีขา

    เดิมเป็นเส้นล้วนไม่มีหน้าตาและไม่มีลำตัว ผู้ใช้เปิดดูแล้วบอกว่าดูไม่ออกว่าภาพอะไร
    ตอนนี้ใส่ลำตัวเป็นเสื้อทึบ + หน้า เพื่อให้ "เห็นแวบเดียวรู้ว่าใครทำอะไร"
    ซึ่งเป็นเงื่อนไขเดียวที่ทำให้ข้อ 看图写作 ใช้งานได้จริง

    x,y = จุดที่เท้าเหยียบพื้น (เหมือนเดิม ฉากเดิมจึงไม่ต้องแก้)
    """
    u = s * UNIT
    c = SHIRTS[shirt % len(SHIRTS)]
    hip, shoulder, neck = y - 22 * u, y - 42 * u, y - 45 * u
    hx = 9.5 * u                     # ครึ่งความกว้างไหล่
    arm = {
        "down":  f"M{x-hx},{shoulder+2*u} L{x-hx-5*u},{hip+2*u} "
                 f"M{x+hx},{shoulder+2*u} L{x+hx+5*u},{hip+2*u}",
        "up":    f"M{x-hx},{shoulder+2*u} L{x-hx-7*u},{shoulder-14*u} "
                 f"M{x+hx},{shoulder+2*u} L{x+hx+7*u},{shoulder-14*u}",
        "front": f"M{x-hx},{shoulder+3*u} L{x-hx-11*u},{shoulder+7*u} "
                 f"M{x+hx},{shoulder+3*u} L{x+hx+11*u},{shoulder+7*u}",
        "one":   f"M{x-hx},{shoulder+2*u} L{x-hx-5*u},{hip+2*u} "
                 f"M{x+hx},{shoulder+2*u} L{x+hx+9*u},{shoulder-11*u}",
        "walk":  f"M{x-hx},{shoulder+2*u} L{x-hx-7*u},{hip} "
                 f"M{x+hx},{shoulder+2*u} L{x+hx+7*u},{shoulder+9*u}",
    }[arms]
    legs = (f"M{x-4.5*u},{hip} L{x-6*u},{y} M{x+4.5*u},{hip} L{x+6*u},{y}"
            if arms != "walk"
            else f"M{x-4.5*u},{hip} L{x-11*u},{y} M{x+4.5*u},{hip} L{x+8*u},{y-2*u}")
    out = []
    # ลำตัวเป็นรูปเสื้อ กว้างที่ไหล่ สอบเข้าที่เอว
    out.append(
        f'<path d="M{x-hx},{shoulder} Q{x},{shoulder-3*u} {x+hx},{shoulder} '
        f'L{x+hx-1.5*u},{hip} L{x-hx+1.5*u},{hip} Z" fill="{c}" stroke="{color}" '
        f'stroke-width="{1.8*u:.2f}" stroke-linejoin="round"/>'
    )
    out.append(f'<path d="{legs}" fill="none" stroke="{color}" '
               f'stroke-width="{2.6*u:.2f}" stroke-linecap="round"/>')
    out.append(f'<path d="{arm}" fill="none" stroke="{color}" '
               f'stroke-width="{2.4*u:.2f}" stroke-linecap="round"/>')
    if head:
        out.append(f'<path d="M{x},{neck} L{x},{shoulder}" stroke="{color}" '
                   f'stroke-width="{2*u:.2f}"/>')
        out.append(face(x, y - 53 * u, 8 * u, mood=mood, look=look, color=color))
    return "".join(out)


def chair(x, y, s=1.0, face_dir=1, color=INK):
    """เก้าอี้ — ถ้าไม่วาด คนนั่งจะลอยอยู่กลางอากาศ ซึ่งอ่านไม่ออกว่านั่งอยู่"""
    u = s * UNIT
    d = face_dir
    seat = y - 30 * u
    back = x - 11 * u * d
    return (f'<path d="M{x-12*u*d},{seat} L{x+13*u*d},{seat} '
            f'M{back},{seat} L{back},{seat-24*u} '
            f'M{x-9*u*d},{seat} L{x-9*u*d},{y} M{x+11*u*d},{seat} L{x+11*u*d},{y}" '
            f'fill="none" stroke="{color}" stroke-width="{2.4*u:.2f}" '
            f'stroke-linecap="round"/>')


def sitting(x, y, s=1.0, color=INK, face_dir=1, *, mood="neutral", shirt=1,
            seat_h=30, **kw):
    """คนนั่ง — x,y คือจุดที่ **เท้าเหยียบพื้น** เหมือน person()

    เดิม y คือระดับสะโพก ฉากจึงส่งค่าความสูงโต๊ะเข้ามา ทำให้คนลอยเหนือเส้นพื้น
    สมัยที่เป็นเส้นบางๆ ยังพอมองข้ามได้ พอใส่ลำตัวทึบแล้วเห็นชัดว่าลอย
    ให้ทุกฟังก์ชันใช้ "เท้าอยู่ตรงไหน" เป็นหลักเดียวกัน จะได้วางบนพื้นเดียวกันได้

    face_dir=1 หันขวา · -1 หันซ้าย (รับ face= ของเดิมไว้ด้วย)
    """
    if "face" in kw:
        face_dir = kw.pop("face")
    u = s * UNIT
    d = face_dir
    c = SHIRTS[shirt % len(SHIRTS)]
    seat = y - seat_h * u
    shoulder = seat - 20 * u
    hx = 9 * u
    return (
        f'<path d="M{x-hx},{shoulder} Q{x},{shoulder-3*u} {x+hx},{shoulder} '
        f'L{x+hx-1.5*u},{seat} L{x-hx+1.5*u},{seat} Z" fill="{c}" stroke="{color}" '
        f'stroke-width="{1.8*u:.2f}" stroke-linejoin="round"/>'
        # ต้นขาไปข้างหน้า แล้วหน้าแข้งลงถึงพื้น
        f'<path d="M{x},{seat} L{x+13*u*d},{seat} L{x+13*u*d},{y}" fill="none" '
        f'stroke="{color}" stroke-width="{2.6*u:.2f}" stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
        # แขนยื่นไปข้างหน้า วางบนโต๊ะ
        f'<path d="M{x+hx*d*0.3},{shoulder+3*u} L{x+14*u*d},{seat-4*u}" fill="none" '
        f'stroke="{color}" stroke-width="{2.4*u:.2f}" stroke-linecap="round"/>'
        f'<path d="M{x},{shoulder-3*u} L{x},{shoulder}" stroke="{color}" '
        f'stroke-width="{2*u:.2f}"/>'
        + face(x, shoulder - 11 * u, 8 * u, mood=mood, look=d, color=color)
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
            table(60, 218, 210) +
            chair(112, 286, 1.0, -1, SOFT) +
            sitting(112, 286, 1.0, mood="happy", shirt=2, face_dir=1) +
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
            table(120, 216, 250) +
            "".join(f'<ellipse cx="{cx}" cy="208" rx="22" ry="8" fill="none" '
                    f'stroke="{WARM}" stroke-width="2.6"/>' for cx in (185, 245, 305)) +
            chair(84, 286, 0.95, 1, SOFT) + chair(404, 286, 0.95, -1, SOFT) +
            sitting(84, 286, 0.95, mood="happy", shirt=0) +
            sitting(404, 286, 0.95, mood="happy", shirt=1, face_dir=-1) +
            person(244, 216, 0.5, arms="front", mood="happy", shirt=3) +
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
            # ก้านร่มต้องจบที่มือที่ยกขึ้น ไม่ใช่ลอยอยู่เหนือหัว — ผู้ใช้ต้องดูออกว่า "ถือร่ม"
            f'<path d="M88,120 A60,60 0 0 1 208,120 Z" fill="{SKY}" stroke="{ACCENT}" stroke-width="3"/>'
            f'<path d="M148,120 L148,252" stroke="{INK}" stroke-width="2.8" stroke-linecap="round"/>' +
            person(112, 286, 0.86, arms="one", mood="neutral", shirt=0) +
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
            chair(168, 286, 0.72, 1, SOFT) +
            sitting(168, 286, 0.72, mood="happy", shirt=4) +
            person(320, 286, 0.9, arms="walk", mood="happy", shirt=2) +
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
            table(126, 218, 230) +
            box(206, 192, 70, 22, WARM) +
            chair(90, 286, 0.95, 1, SOFT) + chair(396, 286, 0.95, -1, SOFT) +
            sitting(90, 286, 0.95, mood="tired", shirt=0) +
            sitting(396, 286, 0.95, mood="neutral", shirt=2, face_dir=-1) +
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
            person(86, 292, 0.86, arms="front", mood="happy", shirt=3) +
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
            table(120, 220, 240) +
            box(224, 152, 84, 62, INK, fill=SKY) +
            f'<path d="M214,214 L318,214" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>' +
            box(150, 188, 28, 26, WARM) +
            box(330, 196, 34, 18, SOFT) +
            chair(154, 286, 0.95, 1, SOFT) +
            sitting(154, 286, 0.95, mood="tired", shirt=0) +
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
            person(140, 286, 0.86, arms="up", mood="happy", shirt=1) +
            person(300, 286, 0.86, arms="front", mood="happy", shirt=2) +
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
            chair(304, 286, 0.9, -1, SOFT) +
            sitting(304, 286, 0.9, mood="neutral", shirt=2, face_dir=-1) +
            person(110, 286, 0.86, arms="one", mood="sad", shirt=1) +
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
            person(280, 286, 0.8, arms="front", mood="tired", shirt=0) +
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
