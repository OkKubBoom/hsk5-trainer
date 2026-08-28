"""เวอร์ชันที่กำลังให้บริการอยู่ — ตอบคำถาม "โค้ดที่แก้ขึ้นแล้วหรือยัง"

ก่อนมีไฟล์นี้ วิธีเดียวที่จะรู้คือเดาจากหน้าตาเว็บ ซึ่งพลาดได้ง่ายมาก
เพราะเบราว์เซอร์ค้าง cache ก็หน้าตาเหมือนเดิม build ยังไม่เสร็จก็เหมือนเดิม

อ่านค่าครั้งเดียวตอนโปรเซสเริ่ม ไม่ใช่ทุกครั้งที่มีคนเปิดหน้าเว็บ
เพราะค่าพวกนี้เปลี่ยนไม่ได้ระหว่างที่โปรเซสเดิมยังทำงานอยู่ —
คอนเทนเนอร์ใหม่ = โค้ดใหม่ = โปรเซสใหม่เสมอ

บนเซิร์ฟเวอร์ต้องพึ่งตัวแปรของแพลตฟอร์ม เพราะ .git/ อยู่ใน .dockerignore
(ตั้งใจ — โฟลเดอร์ .git ทำให้ image ใหญ่ขึ้นโดยไม่ได้ใช้)
บนเครื่องพัฒนาไม่มีตัวแปรพวกนั้น จึงถามจาก git ตรงๆ แทน
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone

# เลขเวอร์ชันที่คนอ่านรู้เรื่อง อยู่ในไฟล์ VERSION ที่รากโปรเจกต์
# แยกจากเลข commit เพราะคนละหน้าที่:
#   เวอร์ชัน  บอกว่า "รุ่นไหน มีอะไรใหม่"      → ผู้ใช้อ่าน ดูคู่กับ CHANGELOG.md
#   commit    บอกว่า "โค้ดบรรทัดไหนเป๊ะๆ"      → คนแก้บั๊กอ่าน
# กติกาการเพิ่มเลขเขียนไว้ใน CHANGELOG.md
DEFAULT_VERSION = "0.0.0"


def _release() -> str:
    try:
        text = (Path(settings.BASE_DIR) / "VERSION").read_text(encoding="utf-8").strip()
        return text or DEFAULT_VERSION
    except Exception:
        return DEFAULT_VERSION


def _from_platform() -> dict:
    """ค่าที่ Railway ใส่ให้อัตโนมัติตอน deploy — ไม่ต้องตั้งเอง"""
    sha = os.getenv("RAILWAY_GIT_COMMIT_SHA", "").strip()
    if not sha:
        return {}
    return {
        "sha": sha[:7],
        "sha_full": sha,
        "branch": os.getenv("RAILWAY_GIT_BRANCH", "").strip(),
        "message": os.getenv("RAILWAY_GIT_COMMIT_MESSAGE", "").strip().splitlines()[0][:120]
        if os.getenv("RAILWAY_GIT_COMMIT_MESSAGE") else "",
        "source": "server",
    }


def _from_git() -> dict:
    """เครื่องพัฒนา — ถาม git โดยตรง ล้มเหลวได้โดยไม่ทำให้เว็บพัง"""
    def run(*args) -> str:
        try:
            return subprocess.run(
                args, capture_output=True, text=True, timeout=2, check=True,
            ).stdout.strip()
        except Exception:
            return ""

    sha = run("git", "rev-parse", "HEAD")
    if not sha:
        return {}
    dirty = bool(run("git", "status", "--porcelain"))
    return {
        "sha": sha[:7] + ("+" if dirty else ""),
        "sha_full": sha,
        "branch": run("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "message": run("git", "log", "-1", "--pretty=%s")[:120],
        "source": "dev",
    }


def _resolve() -> dict:
    info = _from_platform() or _from_git() or {
        "sha": "unknown", "sha_full": "", "branch": "", "message": "", "source": "unknown",
    }
    info["release"] = _release()
    # เวลาที่โปรเซสนี้เริ่ม = เวลาที่โค้ดชุดนี้เริ่มให้บริการ
    info["started_at"] = timezone.now()
    return info


VERSION = _resolve()


def as_dict() -> dict:
    """รูปแบบสำหรับส่งออกเป็น JSON — ไม่มีอะไรเป็นความลับ"""
    started: datetime = VERSION["started_at"]
    uptime = timezone.now() - started
    return {
        "version": VERSION["release"],
        "commit": VERSION["sha"],
        "commit_full": VERSION["sha_full"],
        "branch": VERSION["branch"],
        "message": VERSION["message"],
        "source": VERSION["source"],
        "started_at": started.isoformat(),
        "uptime_seconds": int(uptime.total_seconds()),
        "uptime_human": _human(uptime.total_seconds()),
    }


def _human(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} วินาที"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} นาที"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ชั่วโมง {minutes % 60} นาที"
    return f"{hours // 24} วัน {hours % 24} ชั่วโมง"


def context(request) -> dict:
    """ใส่ให้ทุกเทมเพลตอัตโนมัติ ไม่ต้องส่งผ่านทุก view"""
    return {"app_version": VERSION}
