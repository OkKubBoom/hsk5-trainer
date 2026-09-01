"""สร้างไอคอนของแอปสำหรับ PWA

    python manage.py make_icons

**ทำไมต้องเขียนเอง**
เครื่องนี้ไม่มี Pillow และไม่มี ImageMagick และการเพิ่ม dependency แค่เพื่อสร้าง
ไฟล์สามไฟล์ที่สร้างครั้งเดียวจบ ไม่คุ้มกับการที่ทุกคนต้องติดตั้งเพิ่มตอน deploy
โค้ดนี้เขียน PNG ตรงๆ ด้วย zlib กับ struct ซึ่งอยู่ใน Python มาตรฐานอยู่แล้ว

**รูปที่วาด** คือเครื่องหมายเดียวกับที่อยู่มุมซ้ายบนของเว็บ (templates/base.html)
เส้นนอน เส้นตั้ง และเส้นโค้งสองเส้น บนพื้นสีเขียวของระบบ
ถ้าเปลี่ยนโลโก้บนเว็บ ต้องมาแก้ที่นี่ด้วย ไม่งั้นไอคอนบนจอโฮมจะไม่ตรงกับเว็บ
"""
import struct
import zlib
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

BRAND = (30, 107, 93)        # --accent ของระบบ
INK = (255, 255, 255)
SIZES = [(192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")]

# เส้นของเครื่องหมาย ในระบบพิกัด 24×24 เดียวกับ SVG ในเว็บ
LINES = [((4, 5), (20, 5)), ((12, 5), (12, 19))]
CURVES = [
    ((7, 10), (8.6, 13.2), (10.1, 15.4), (12, 17)),
    ((17, 10), (15.4, 13.2), (13.9, 15.4), (12, 17)),
]


def _bezier(p0, p1, p2, p3, steps=140):
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        yield (u**3 * p0[0] + 3 * u*u*t * p1[0] + 3 * u*t*t * p2[0] + t**3 * p3[0],
               u**3 * p0[1] + 3 * u*u*t * p1[1] + 3 * u*t*t * p2[1] + t**3 * p3[1])


def _points(scale, steps=400):
    for (a, b) in LINES:
        for i in range(steps + 1):
            t = i / steps
            yield ((a[0] + (b[0] - a[0]) * t) * scale, (a[1] + (b[1] - a[1]) * t) * scale)
    for c in CURVES:
        for p in _bezier(*c):
            yield (p[0] * scale, p[1] * scale)


def _disc(radius):
    r2 = radius * radius
    return [(dx, dy) for dy in range(-radius, radius + 1)
            for dx in range(-radius, radius + 1) if dx * dx + dy * dy <= r2]


def _png(size: int, rounded: bool) -> bytes:
    scale = size / 24
    stroke = max(2, round(size * 0.075))
    disc = _disc(stroke // 2)

    # ── พื้นหลัง ──
    px = bytearray(BRAND * (size * size))
    alpha = bytearray([255]) * (size * size)

    if rounded:
        # มุมโค้งสำหรับไอคอน iOS ที่ระบบไม่ตัดให้เอง
        r = int(size * 0.22)
        for y in range(size):
            for x in range(size):
                cx = r - x if x < r else (x - (size - 1 - r) if x > size - 1 - r else 0)
                cy = r - y if y < r else (y - (size - 1 - r) if y > size - 1 - r else 0)
                if cx and cy and cx * cx + cy * cy > r * r:
                    alpha[y * size + x] = 0

    # ── เส้น ──
    ink = bytearray(size * size)
    for fx, fy in _points(scale):
        bx, by = int(fx), int(fy)
        for dx, dy in disc:
            x, y = bx + dx, by + dy
            if 0 <= x < size and 0 <= y < size:
                ink[y * size + x] = 255

    # ลบขอบหยักด้วยการเฉลี่ยเพื่อนบ้าน — ถูกกว่าการ supersample ทั้งภาพมาก
    smooth = bytearray(ink)
    for y in range(1, size - 1):
        row = y * size
        for x in range(1, size - 1):
            i = row + x
            if ink[i] != ink[i - 1] or ink[i] != ink[i + 1] \
                    or ink[i] != ink[i - size] or ink[i] != ink[i + size]:
                total = (ink[i - 1] + ink[i + 1] + ink[i - size] + ink[i + size]
                         + ink[i] + ink[i - size - 1] + ink[i - size + 1]
                         + ink[i + size - 1] + ink[i + size + 1])
                smooth[i] = total // 9

    for i, cover in enumerate(smooth):
        if cover:
            j = i * 3
            for k in range(3):
                px[j + k] = (px[j + k] * (255 - cover) + INK[k] * cover) // 255

    # ── ประกอบเป็นไฟล์ PNG ──
    raw = bytearray()
    for y in range(size):
        raw.append(0)                       # filter type 0
        for x in range(size):
            i = y * size + x
            raw += px[i * 3:i * 3 + 3]
            raw.append(alpha[i])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


class Command(BaseCommand):
    help = "สร้างไอคอน PWA จากเครื่องหมายของระบบ"

    def handle(self, *args, **opts):
        out = Path(settings.BASE_DIR) / "static" / "icons"
        out.mkdir(parents=True, exist_ok=True)
        for size, name in SIZES:
            # ไอคอน iOS ต้องมีมุมโค้งมาในไฟล์เอง ส่วนของ Android ระบบตัดให้
            data = _png(size, rounded=name.startswith("apple"))
            (out / name).write_bytes(data)
            self.stdout.write(f"  {name} — {size}×{size} · {len(data) // 1024} KB")
        self.stdout.write(self.style.SUCCESS(f"เขียนไอคอน {len(SIZES)} ไฟล์ที่ {out}"))
