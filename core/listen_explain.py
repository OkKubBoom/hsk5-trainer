"""ชี้ว่าคำตอบของข้อฟังอยู่ตรงไหนในบท

**ทำไมไม่ให้ AI เขียนคำอธิบายข้อฟัง 225 ข้อ**
ข้อฟังผิดเพราะ "ฟังไม่ทัน" เกือบทั้งหมด ไม่ใช่เพราะไม่เข้าใจเหตุผล
สิ่งที่ช่วยได้จริงคือชี้ให้เห็นว่า *ประโยคไหน* ที่พลาดไป ซึ่งหาได้จากข้อมูลที่มีอยู่แล้ว
ไม่ต้องแต่งขึ้นมา — และของที่ไม่ได้แต่งขึ้นก็ไม่ต้องให้ใครมาตรวจว่าจริงไหม

**วิธีหา** เทียบตัวอักษรที่ซ้ำกันระหว่างคำตอบที่ถูกกับแต่ละประโยคในบท
ประโยคที่ซ้ำมากที่สุดคือประโยคที่มีคำตอบ ถ้าซ้ำน้อยเกินเกณฑ์จะไม่ชี้เลย
ชี้ผิดแย่กว่าไม่ชี้ เพราะผู้เรียนจะจำประโยคที่ไม่เกี่ยวไปใช้
"""
from __future__ import annotations

import re
from functools import lru_cache

from .models import VocabItem

SENTENCE_SPLIT = re.compile(r"(?<=[。！？])")
HAN = re.compile(r"[一-鿿]")

# ตัวอักษรที่พบในเกือบทุกประโยค นับแล้วไม่ได้บอกอะไร
# ถ้าไม่ตัดออก ประโยคยาวจะชนะเสมอเพราะมี 的 เยอะกว่า
COMMON = set("的了是在有和就不人我你他她们这那个也都很会到说要么吗呢啊")

# ต่ำกว่านี้ถือว่าเดา — ยอมไม่ชี้ดีกว่าชี้ผิด
MIN_SCORE = 0.34


def sentences(script: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(script or "") if s.strip()]


def _signal(text: str) -> set[str]:
    return {c for c in HAN.findall(text or "") if c not in COMMON}


def answer_sentence(script: str, answer: str) -> dict | None:
    """ประโยคในบทที่มีคำตอบอยู่ — คืน None เมื่อไม่มั่นใจพอ"""
    target = _signal(answer)
    if not target:
        return None

    best = None
    for i, sentence in enumerate(sentences(script)):
        chars = _signal(sentence)
        if not chars:
            continue
        # วัดจากฝั่งคำตอบ — ถามว่า "คำในคำตอบไปโผล่ในประโยคนี้กี่ตัว"
        # ไม่ใช่ฝั่งประโยค ไม่งั้นประโยคสั้นจะได้เปรียบโดยไม่มีเหตุผล
        score = len(target & chars) / len(target)
        if best is None or score > best["score"]:
            best = {"index": i, "sentence": sentence, "score": round(score, 2)}

    if not best or best["score"] < MIN_SCORE:
        return None
    return best


@lru_cache(maxsize=1)
def _vocab_index() -> dict[str, dict]:
    """คำศัพท์ในคลังที่ยาว 2 ตัวอักษรขึ้นไป ใช้สแกนหาในบท

    คำตัวเดียวถูกตัดออกเพราะไปโผล่ในเกือบทุกบทและไม่ได้ช่วยอะไร
    แคชไว้ตลอดอายุโปรเซส — คลังคำศัพท์แทบไม่เปลี่ยนระหว่างที่เซิร์ฟเวอร์ทำงาน
    """
    rows = (
        VocabItem.objects.filter(hsk_level__gte=4)
        .exclude(hanzi="").values("hanzi", "pinyin", "pinyin_sandhi", "meaning_th", "hsk_level")
    )
    return {r["hanzi"]: r for r in rows if len(r["hanzi"]) >= 2}


def hard_words(script: str, limit: int = 8) -> list[dict]:
    """คำ HSK4 ขึ้นไปที่โผล่ในบท — คือคำที่น่าจะเป็นตัวที่ฟังไม่ออก

    เรียงตามระดับจากยากไปง่าย เพราะถ้าแสดงได้แค่ไม่กี่คำ ควรเป็นคำที่ยากที่สุด
    """
    index = _vocab_index()
    found = {w: row for w, row in index.items() if w in (script or "")}
    ordered = sorted(found.values(), key=lambda r: (-r["hsk_level"], r["hanzi"]))
    return ordered[:limit]


def body_only(question) -> str:
    """บทพูดโดยไม่รวมคำถามที่อ่านต่อท้าย

    คำถามถูกต่อท้ายบทตอนสร้างเสียง (ดู listening.speech_text)
    ถ้าไม่ตัดออก คำอย่าง 对话 发生 ที่มาจากตัวคำถามจะถูกนับเป็น "คำยากในบท"
    ทั้งที่ผู้เรียนอ่านคำถามอยู่บนจอแล้ว ไม่ได้ต้องฟังคำพวกนั้น
    """
    script = question.audio_script or ""
    tail = (question.prompt_zh or "").strip()
    if tail and script.endswith(tail):
        script = script[: -len(tail)]
    return script.strip()


def explain(question) -> dict:
    """ข้อมูลประกอบการเฉลยข้อฟัง — ไม่มีอะไรที่ถูกแต่งขึ้น"""
    script = body_only(question)
    correct = question.options.filter(is_correct=True).first()
    answer = (correct.text if correct else question.answer_text) or ""
    return {
        "answer_sentence": answer_sentence(script, answer),
        "hard_words": hard_words(script),
        "sentences": sentences(script),
        "script": script,
    }
