"""คำที่อยู่ *นอก* คลังคำศัพท์ — สำนวนและคำระดับ HSK6 ขึ้นไปที่โผล่ในข้อสอบจริง

ทำไมต้องมีไฟล์นี้
-----------------
คลังคำศัพท์มีแค่ HSK1-5 (2,206 คำ) แต่บทอ่าน/บทฟังของข้อสอบจริงมีคำเกินระดับ
ปนอยู่เสมอ — นั่นคือส่วนหนึ่งของความยากที่ข้อสอบตั้งใจให้เดาจากบริบท

คำแปลของคำพวกนี้ **มีอยู่ในระบบแล้ว** ในช่อง key_vocab ของคำอธิบายเฉลย
แต่เห็นได้เฉพาะ *หลัง* ตอบข้อนั้นแล้วเท่านั้น การค้นหาที่หน้าคลังคำศัพท์
มองไม่เห็นเลย ผู้เรียนที่เจอคำแปลกระหว่างอ่านจึงต้องออกไปเปิดแอปอื่นถาม
(เจอจริง: น้องออกไปถาม AI ตัวอื่นเรื่อง 旗鼓相当 ทั้งที่ระบบมีคำแปลอยู่แล้ว
ที่คำอธิบายข้อ 75 ของ H51327)

โมดูลนี้จึงรวบคำเหล่านั้นให้ค้นหาได้ที่เดียว

⚠️ ลิขสิทธิ์ (D6) — คำและคำอธิบายมาจากข้อสอบเก่า `commercial_safe=False`
ใช้ส่วนตัวได้ ห้ามติดไปกับเวอร์ชันที่จะขาย
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from .models import Question, VocabItem


@lru_cache(maxsize=1)
def _pinyin_file() -> dict:
    """พินอินที่เตรียมไว้ล่วงหน้าสำหรับคำนอกคลัง — ไฟล์เดียวกับที่ reading.py ใช้"""
    try:
        path = Path(settings.BASE_DIR) / "data" / "key_vocab_pinyin.json"
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def rows(query: str = "") -> list[dict]:
    """คำนอกคลังทั้งหมด เรียงตามจำนวนชุดข้อสอบที่พบ

    อ่านสดทุกครั้ง ไม่ cache — สแกนแค่ ~4 ms และคำอธิบายถูกแก้ได้จาก
    หน้าตรวจคำอธิบาย ถ้า cache ไว้ครูจะแก้แล้วไม่เห็นผล ซึ่งงงกว่าที่ประหยัดได้
    """
    seen: dict[str, dict] = {}
    for explanation, source_ref in (
        Question.objects
        .exclude(explanation={}).exclude(explanation=None)
        .values_list("explanation", "source_ref")
    ):
        for item in (explanation or {}).get("key_vocab") or []:
            hanzi = (item.get("hanzi") or "").strip()
            note = (item.get("note") or "").strip()
            if not hanzi or not note:
                continue
            row = seen.setdefault(hanzi, {"hanzi": hanzi, "notes": [], "papers": set()})
            if note not in row["notes"]:
                row["notes"].append(note)
            paper = (source_ref or "").split(" ")[0]
            if paper:
                row["papers"].add(paper)

    # คำที่อยู่ในคลังอยู่แล้วตัดออก — หน้าคลังคำศัพท์แสดงให้อยู่แล้ว จะซ้ำกันเปล่าๆ
    in_library = set(
        VocabItem.objects.filter(hanzi__in=list(seen)).values_list("hanzi", flat=True)
    )
    pinyin_of = _pinyin_file()

    out = []
    for hanzi, row in seen.items():
        if hanzi in in_library:
            continue
        out.append({
            "hanzi": hanzi,
            "pinyin": pinyin_of.get(hanzi, ""),
            "meaning_th": _merge_notes(row["notes"]),
            "papers": sorted(row["papers"]),
        })

    out.sort(key=lambda r: (-len(r["papers"]), r["hanzi"]))
    return search(out, query) if query else out


def search(items: list[dict], query: str) -> list[dict]:
    """กรองรายการที่ได้จาก rows() — แยกออกมาเพื่อไม่ต้องสแกนฐานซ้ำ
    เวลาต้องใช้ทั้งจำนวนรวมและผลค้นหาในหน้าเดียวกัน"""
    q = query.strip().lower()
    if not q:
        return items
    return [r for r in items
            if q in r["hanzi"].lower()
            or q in r["pinyin"].lower()
            or q in r["meaning_th"].lower()]


def _merge_notes(notes: list[str]) -> str:
    """รวมคำอธิบายของคำเดียวกันจากหลายข้อให้เหลืออันที่ให้ข้อมูลมากที่สุด

    คำเดียวกันมักถูกอธิบายซ้ำเกือบเหมือนเดิม ("อย่างหลัง (คู่กับ 前者)" กับ
    "อย่างหลัง (คู่กับ 前者 อย่างแรก)") ต่อกันตรงๆ แล้วอ่านไม่รู้เรื่อง
    จึงตัดอันที่เป็นส่วนย่อยของอีกอันทิ้ง แล้วเอามาแค่ 2 สำนวนที่ต่างกันจริง
    """
    kept: list[str] = []
    seen: list[str] = []
    for note in sorted(notes, key=len, reverse=True):
        flat = _flatten(note)
        if not any(flat in bigger for bigger in seen):
            kept.append(note)
            seen.append(flat)
    return " · ".join(kept[:2])


def _flatten(text: str) -> str:
    """ตัดช่องว่างและเครื่องหมายออกก่อนเทียบ

    "(ราคา/ระดับน้ำ) สูงขึ้น" กับ "(ราคา ระดับน้ำ) สูงขึ้น" คือคำอธิบายเดียวกัน
    ต่างแค่เครื่องหมาย เทียบดิบๆ จะไม่รู้ว่าซ้ำ แล้วโชว์ทั้งคู่
    """
    return re.sub(r"[\s/·,.()\-—]+", "", text)
