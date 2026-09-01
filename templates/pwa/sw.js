{% load static %}/* Service worker — ทำให้ติดตั้งลงจอโฮมได้ และเปิดเร็วขึ้นบนเน็ตช้า
 *
 * **ตั้งใจไม่แคชหน้าเว็บ (HTML) เลย** แคชเฉพาะไฟล์ static
 * เพราะหน้าเว็บผูกกับบัญชีที่ล็อกอินอยู่ ถ้าแคชไว้แล้วมีคนอื่นมาใช้เครื่องเดียวกัน
 * (พี่น้องใช้เครื่องเดียวกันเป็นเรื่องปกติในบ้านเดียวกัน) จะเห็นหน้าของอีกคน
 * และโทเคน CSRF ที่แคชไว้จะหมดอายุ ทำให้ส่งฟอร์มไม่ผ่านโดยไม่มีใครรู้สาเหตุ
 *
 * ไฟล์นี้เสิร์ฟผ่าน Django ไม่ใช่ไฟล์ static เพราะ
 *   1. ต้องอยู่ที่ /sw.js ถึงจะคุมทั้งเว็บได้ ไฟล์ใน /static/ คุมได้แค่ /static/
 *   2. ตอน deploy ชื่อไฟล์ static ถูกเติมแฮช ต้องให้ Django เติมให้ผ่าน {% templatetag openblock %} static {% templatetag closeblock %}
 */
const VERSION = '{{ version }}';
const SHELL = 'shell-' + VERSION;

const ASSETS = [
  '{% static "css/app.css" %}',
  '{% static "js/alpine.min.js" %}',
  '{% static "js/alpine-collapse.min.js" %}',
  '{% static "js/htmx.min.js" %}',
  '{% static "js/listen.js" %}',
  '{% static "icons/icon-192.png" %}',
  '{% url "offline" %}',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  // ลบแคชของเวอร์ชันก่อน ไม่งั้นเครื่องผู้เรียนจะสะสมไฟล์เก่าไปเรื่อยๆ
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;                       // ฟอร์มต้องถึงเซิร์ฟเวอร์เสมอ
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;        // ฟอนต์จากภายนอก ปล่อยผ่าน

  // หน้าเว็บ: ต่อเน็ตเสมอ ถ้าเน็ตหลุดค่อยขึ้นหน้าบอกว่าออฟไลน์
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('{% url "offline" %}')));
    return;
  }

  // ไฟล์ static: เอาจากแคชก่อน ชื่อไฟล์มีแฮชอยู่แล้วจึงไม่มีปัญหาของเก่าค้าง
  if (url.pathname.startsWith('{% get_static_prefix %}')) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put(req, copy));
        }
        return res;
      }))
    );
  }
});
