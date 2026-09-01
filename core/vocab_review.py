"""รายการคำศัพท์ที่ต้องให้ครูตรวจ — เรียงตามผลกระทบจริง ไม่ใช่ตามลำดับตัวอักษร

**ปัญหาที่ต้องแก้**
คำที่ด่านคุณภาพติดธงมี 879 คำ ถ้ายื่นให้ครูทั้งก้อน ครูจะไม่เริ่มเลย
เพราะไม่มีใครนั่งตรวจ 879 คำรวดเดียว และถ้าตรวจไปได้ 50 คำแล้วหยุด
50 คำนั้นควรเป็นคำที่ผู้เรียนจะเจอจริงในข้อสอบ ไม่ใช่คำแรกๆ ตามพจนานุกรม

**ลำดับความสำคัญ** — เรียงตาม "โอกาสที่จะผิด × ราคาของการผิด" ไม่ใช่ตามความถี่ล้วน
  1. กลุ่มที่ด่านคุณภาพตีตกก่อน แล้วค่อยกลุ่มที่แค่น่าสงสัย
  2. ระดับ HSK สูงก่อน — 很 是 不 ออกในข้อสอบทุกชุดก็จริง แต่คำแปลของมัน
     ไม่มีทางผิด การให้ครูไล่ดูคำพวกนี้คือการเผาเวลาครูทิ้ง
     คำที่เสี่ยงคือคำนามธรรมระดับ 5-6 ที่มีหลายความหมาย
  3. เคยเป็น *เฉลย* ในข้อสอบจริง — แปลผิดตรงนี้คือตอบผิดตรงๆ
  4. โผล่ในข้อสอบจริงกี่ชุด และมีกี่คนกำลังท่องคำนี้อยู่ตอนนี้

**ทำไมไม่ให้ AI ตรวจคำแปลที่ AI แปลเอง**
วนอยู่ในวงจรเดิม ถ้าโมเดลแปลผิดเพราะเข้าใจคำนั้นผิด มันก็จะยืนยันคำแปลผิดเดิม
คำที่ต้องมีคนตรวจ ต้องเป็นคนตรวจจริงๆ
"""
from __future__ import annotations

from django.db.models import Case, Count, IntegerField, Q, Value, When

from .models import Card, VocabItem

# ป้ายที่แปลว่า "ยังไม่มีใครยืนยัน" — ดูรายละเอียดที่ flag_vocab_quality.py
FLAGS = ["review:error", "review:warn", "needs_review", "disputed"]

BUCKETS = [
    {"key": "error", "label": "ด่านคุณภาพไม่ผ่าน", "tag": "review:error",
     "why": "ตรวจอัตโนมัติแล้วพบว่าน่าจะผิดจริง — กลุ่มนี้ควรตรวจก่อน"},
    {"key": "disputed", "label": "มีคนกดว่าแปลผิด", "tag": "disputed",
     "why": "ผู้เรียนหรือครูกดแย้งไว้แล้ว"},
    {"key": "warn", "label": "น่าสงสัย", "tag": "review:warn",
     "why": "ตรวจอัตโนมัติแล้วไม่มั่นใจ เช่น คำแปลสั้นผิดปกติหรือมีหลายความหมาย"},
    {"key": "review", "label": "ยังไม่มีใครตรวจ", "tag": "needs_review",
     "why": "คำแปลมาจาก AI และยังไม่มีคนยืนยัน"},
]


def _tagged(tag: str):
    """หาคำที่ติดป้ายนี้ — ใช้ icontains เพราะ SQLite ค้นใน JSONField ตรงๆ ไม่ได้

    ป้ายทุกตัวในระบบไม่มีตัวไหนเป็นส่วนหนึ่งของอีกตัว จึงไม่ชนกัน
    ยกเว้น review:error กับ review:warn ที่ขึ้นต้นเหมือนกัน — จึงต้องใส่ให้ครบคำ
    """
    return Q(tags__icontains=f'"{tag}"')


def counts() -> dict:
    """จำนวนคำในแต่ละกลุ่ม และที่ตรวจไปแล้ว"""
    total = VocabItem.objects.count()
    verified = VocabItem.objects.filter(_tagged("human_verified")).count()
    pending = VocabItem.objects.filter(
        _tagged("review:error") | _tagged("review:warn")
        | _tagged("needs_review") | _tagged("disputed")
    ).exclude(_tagged("human_verified")).count()
    return {
        "total": total,
        "verified": verified,
        "pending": pending,
        "percent": round(verified / total * 100) if total else 0,
    }


def queue(bucket: str = "", *, limit: int = 60):
    """คำที่รอตรวจ เรียงตามผลกระทบ

    จำกัดจำนวนต่อหน้าโดยตั้งใจ — รายการที่ยาวไม่มีที่สิ้นสุดทำให้คนเลิกก่อนเริ่ม
    ตรวจหมดชุดนี้แล้วค่อยโหลดชุดถัดไป จะได้เห็นว่าจบเป็นรอบๆ
    """
    picked = next((b for b in BUCKETS if b["key"] == bucket), None)
    if picked:
        rows = VocabItem.objects.filter(_tagged(picked["tag"]))
    else:
        rows = VocabItem.objects.filter(
            _tagged("review:error") | _tagged("review:warn")
            | _tagged("needs_review") | _tagged("disputed")
        )

    # คำที่ผู้เรียนกำลังท่องอยู่ตอนนี้ = แปลผิดแล้วเขากำลังจำผิดอยู่จริงๆ
    return (
        rows.exclude(_tagged("human_verified"))
        .annotate(
            in_cards=Count("cards", distinct=True),
            severity=Case(
                When(_tagged("review:error"), then=Value(3)),
                When(_tagged("disputed"), then=Value(2)),
                When(_tagged("review:warn"), then=Value(1)),
                default=Value(0), output_field=IntegerField(),
            ),
        )
        .order_by("-severity", "-hsk_level", "-exam_as_answer",
                  "-exam_papers_count", "-in_cards", "frequency_rank", "hanzi")[:limit]
    )


def flags_of(vocab) -> list[str]:
    """ป้ายที่ทำให้คำนี้เข้าคิว — บอกครูว่าทำไมคำนี้ถูกหยิบมา"""
    tags = set(vocab.tags or [])
    return [b["label"] for b in BUCKETS if b["tag"] in tags]


def learners_studying(vocab) -> int:
    """มีกี่คนที่กำลังท่องคำนี้อยู่ — ใช้บอกความเร่งด่วน"""
    return Card.objects.filter(vocab=vocab).values("learner").distinct().count()
