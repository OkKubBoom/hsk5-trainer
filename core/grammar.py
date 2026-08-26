"""จัดกลุ่มคำเชื่อมตามหน้าที่ในประโยค และคัดคำที่ควรรู้การจับคู่

⚠️ การจัดกลุ่มตามหน้าที่ในไฟล์นี้เป็นความรู้ทางภาษาที่เขียนไว้ตายตัว
ไม่ได้มาจากข้อมูลที่วัดได้เหมือนสถิติหน้าอื่น — ครูควรตรวจก่อนใช้สอน
ส่วนตัวอย่างประโยคและการจับคู่คำมาจากฐานข้อมูลที่ผ่าน pipeline ตรวจสอบแล้ว
"""
from __future__ import annotations

from .models import VocabItem

# กลุ่มตามหน้าที่ — เรียงตามความถี่ที่ข้อสอบใช้
CONNECTIVE_GROUPS = [
    {
        "key": "contrast",
        "name": "แสดงความขัดแย้ง",
        "hint": "ข้อสอบชอบสลับกลุ่มนี้กันเอง โดยเฉพาะ 尽管 (เรื่องจริง) กับ 即使 (เรื่องสมมติ)",
        "words": ["虽然", "尽管", "然而", "不过", "反而", "却", "但是", "可是", "而", "偏偏",
                  "即使", "哪怕", "无论", "不管", "而是", "相反"],
    },
    {
        "key": "cause",
        "name": "เหตุและผล",
        "hint": "เชื่อมเหตุกับผล — ดูว่าอันไหนวางหน้าเหตุ อันไหนวางหน้าผล",
        "words": ["因为", "所以", "因此", "于是", "从而", "因而", "由于", "既然", "以免",
                  "导致", "造成", "结果", "可见", "总之", "看来"],
    },
    {
        "key": "condition",
        "name": "เงื่อนไขและสมมติ",
        "hint": "ส่วนใหญ่มาเป็นคู่ ต้องจำทั้งคู่ ไม่ใช่จำตัวเดียว",
        "words": ["如果", "假如", "要是", "万一", "除非", "只要", "只有", "一旦", "凡是",
                  "否则", "不然", "要不", "无论", "不管", "既然"],
    },
    {
        "key": "addition",
        "name": "เสริมและลำดับความ",
        "hint": "ใช้ต่อความในเรียงความ — มีสามตัวนี้ในงานเขียนคะแนนขึ้นทันที",
        "words": ["而且", "并且", "以及", "此外", "另外", "甚至", "何况", "不仅", "不但",
                  "首先", "其次", "最后", "同时", "接着", "然后", "再说"],
    },
    {
        "key": "compare",
        "name": "เปรียบเทียบและเลือก",
        "hint": "กลุ่มนี้บังคับรูปประโยค ผิดโครงสร้างคือผิดทั้งข้อ",
        "words": ["与其", "不如", "宁可", "宁愿", "相比", "比如", "例如", "似的", "好像",
                  "仿佛", "不像", "至于", "对于", "关于"],
    },
    {
        "key": "degree",
        "name": "บอกระดับและขอบเขต",
        "hint": "คำกลุ่มนี้เป็นตัวลวงบ่อยในพาร์ทอ่าน เพราะความหมายใกล้กันมาก",
        "words": ["几乎", "简直", "毕竟", "究竟", "到底", "反正", "根本", "确实", "的确",
                  "尤其", "格外", "十分", "相当", "极其", "略微", "稍微", "一律", "总共"],
    },
]


def connective_groups(*, only_in_db: bool = True) -> list[dict]:
    """คืนกลุ่มคำเชื่อมพร้อมข้อมูลจากฐานข้อมูล — คำที่ไม่มีในคลังจะถูกตัดออก"""
    wanted = {w for g in CONNECTIVE_GROUPS for w in g["words"]}
    found = {
        v.hanzi: v
        for v in VocabItem.objects.filter(hanzi__in=wanted).exclude(meaning_th="")
    }

    groups = []
    for group in CONNECTIVE_GROUPS:
        items = [found[w] for w in group["words"] if w in found]
        if items or not only_in_db:
            items.sort(key=lambda v: (-(v.exam_papers_count or 0), v.hanzi))
            groups.append({**group, "items": items, "count": len(items)})
    return groups


def uncovered_connectives() -> list[str]:
    """คำที่ติดแท็กว่าเป็นคำเชื่อมแต่ยังไม่ถูกจัดเข้ากลุ่มไหน — ไว้เตือนให้จัดเพิ่ม"""
    grouped = {w for g in CONNECTIVE_GROUPS for w in g["words"]}
    return sorted(
        v.hanzi
        for v in VocabItem.objects.exclude(meaning_th="")
        if "conn" in (v.tags or []) and v.hanzi not in grouped
    )


def collocation_queryset(query: str = "", pos: str = "", min_level: int = 4):
    """คำที่มีข้อมูลการจับคู่ เรียงตามความสำคัญในข้อสอบ

    ตัดคำระดับ 1-3 ออกโดยค่าตั้งต้น — 是/在/有 พบครบ 9 ชุดจริง แต่ไม่มีใครต้อง
    ฝึกว่ามันจับคู่กับอะไร สิ่งที่ต้องฝึกคือกริยาระดับ 4-5 อย่าง 采取/达到/发挥
    """
    qs = (
        VocabItem.objects
        .filter(hsk_level__gte=min_level)
        .exclude(collocations=[])
        .exclude(meaning_th="")
    )
    if pos:
        qs = qs.filter(pos__icontains=pos)
    if query:
        from django.db.models import Q
        qs = qs.filter(
            Q(hanzi__icontains=query) | Q(pinyin__icontains=query) | Q(meaning_th__icontains=query)
        )
    return qs.order_by("-exam_papers_count", "-exam_occurrences", "hanzi")
