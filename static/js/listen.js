/* เครื่องเล่นเสียงข้อฟัง — ใช้ตัวอ่านออกเสียงของเบราว์เซอร์ ไม่มีไฟล์เสียง
 *
 * ทำไมไม่ทำไฟล์เสียง:
 *   บทพูดมาจากข้อสอบลิขสิทธิ์ จึงขึ้น repo สาธารณะไม่ได้ (D6)
 *   ระบบรันบน Railway ซึ่งดิสก์หายทุกครั้งที่ deploy ไฟล์จะไม่รอด
 *   TTS ฝั่งเซิร์ฟเวอร์ที่เสียงดีต้องใช้บริการนอกที่คิดเงินและต้องมีกุญแจ ซึ่งขัด D11
 *   ตัวอ่านของเบราว์เซอร์ฟรี ไม่ต้องมีกุญแจ ไม่เก็บไฟล์ และมีอยู่แล้วบนมือถือทุกเครื่อง
 *
 * ข้อจำกัดที่ต้องบอกผู้เรียนตรงๆ: เสียงไม่ใช่เสียงเดียวกับในห้องสอบ
 * ใช้ฝึกจับใจความและฝึกความเร็วได้ แต่ไม่ใช่การซ้อมเสียงจริง
 */
window.listenPlayer = function (questionId, opts) {
  opts = opts || {};
  return {
    script: '',
    plays: 0,
    playing: false,
    loading: false,
    rate: 1,
    supported: typeof window.speechSynthesis !== 'undefined',
    voice: null,
    error: '',
    revealed: false,

    init() {
      const saved = parseFloat(localStorage.getItem('listenRate'));
      if (saved >= 0.5 && saved <= 1.5) this.rate = saved;
      this.$watch('rate', (v) => localStorage.setItem('listenRate', v));
      if (this.supported) this.pickVoice();
      // รายชื่อเสียงบางเบราว์เซอร์มาทีหลัง ต้องรอสัญญาณ ไม่ใช่เช็คครั้งเดียวแล้วยอมแพ้
      if (this.supported && speechSynthesis.onvoiceschanged !== undefined) {
        speechSynthesis.onvoiceschanged = () => this.pickVoice();
      }
      // ออกจากหน้าไปแล้วเสียงต้องหยุด ไม่ใช่พูดต่อทับข้อถัดไป
      document.addEventListener('htmx:beforeSwap', () => this.stop());
      window.addEventListener('beforeunload', () => this.stop());
    },

    pickVoice() {
      const all = speechSynthesis.getVoices() || [];
      const zh = all.filter((v) => (v.lang || '').toLowerCase().startsWith('zh'));
      // จีนกลางแผ่นดินใหญ่ก่อนเสมอ — เสียงไต้หวัน/กวางตุ้งออกเสียงต่างจากที่ใช้สอบ
      this.voice =
        zh.find((v) => /zh[-_]cn/i.test(v.lang)) ||
        zh.find((v) => /zh[-_]hans/i.test(v.lang)) ||
        zh[0] || null;
      if (!this.voice && all.length) {
        this.error = 'เครื่องนี้ไม่มีเสียงภาษาจีนติดตั้งอยู่';
      }
    },

    async load() {
      if (this.script) return true;
      this.loading = true;
      try {
        const res = await fetch(`/listen/${questionId}/script/`, {
          headers: { 'X-Requested-With': 'fetch' },
        });
        if (!res.ok) throw new Error(res.status);
        this.script = (await res.json()).script || '';
      } catch (e) {
        this.error = 'โหลดบทไม่สำเร็จ ลองกดใหม่อีกครั้ง';
      }
      this.loading = false;
      return !!this.script;
    },

    async play() {
      if (!this.supported) return;
      this.error = '';
      if (!(await this.load())) return;

      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(this.script);
      u.lang = (this.voice && this.voice.lang) || 'zh-CN';
      if (this.voice) u.voice = this.voice;
      u.rate = this.rate;
      u.onstart = () => { this.playing = true; };
      u.onend = () => { this.playing = false; };
      u.onerror = () => {
        this.playing = false;
        this.error = 'เล่นเสียงไม่สำเร็จ — ลองกดอีกครั้ง หรือเปิดเสียงเครื่องดู';
      };
      this.plays += 1;
      speechSynthesis.speak(u);
    },

    stop() {
      if (this.supported) speechSynthesis.cancel();
      this.playing = false;
    },

    async reveal() {
      // ทางออกสุดท้ายเมื่อเครื่องไม่มีเสียงจีน — บอกตรงๆ ว่ากลายเป็นการอ่านแล้ว
      if (await this.load()) this.revealed = true;
    },
  };
};
