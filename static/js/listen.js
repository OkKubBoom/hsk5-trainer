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
    voiceName: localStorage.getItem('listenVoice') || '',
    supported: typeof window.speechSynthesis !== 'undefined',
    voice: null,
    voices: [],
    remoteVoice: false,
    error: '',
    revealed: false,

    init() {
      const saved = parseFloat(localStorage.getItem('listenRate'));
      if (saved >= 0.5 && saved <= 1.5) this.rate = saved;
      this.$watch('rate', (v) => localStorage.setItem('listenRate', v));
      // จำเสียงที่เลือกไว้ — คนละเครื่องมีเสียงคนละชุด จึงเก็บเป็นชื่อ ไม่ใช่ลำดับ
      this.$watch('voiceName', (v) => { localStorage.setItem('listenVoice', v); this.pickVoice(); });
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
      this.voices = zh.slice().sort((a, b) => this.rank(a) - this.rank(b));

      // ผู้เรียนเลือกเองแล้วให้ใช้ของที่เลือก ไม่ใช่ของที่ระบบคิดว่าดีที่สุด
      this.voice = this.voices.find((v) => v.name === this.voiceName) || this.voices[0] || null;
      this.remoteVoice = !!(this.voice && this.voice.localService === false);
      if (!this.voice && all.length) {
        this.error = 'เครื่องนี้ไม่มีเสียงภาษาจีนติดตั้งอยู่';
      }
    },

    /* เรียงเสียงจากฟังรู้เรื่องที่สุดไปน้อยที่สุด
     *
     * ตัวเลือกแรกสำคัญมาก เพราะคนส่วนใหญ่ไม่กดเปลี่ยน — เดิมโค้ดหยิบตัวแรกที่เจอ
     * ซึ่งบน macOS คือ Eddy/Flo/Grandma ที่เป็น "เสียงเล่น" ของ Apple
     * ออกแบบมาให้ตลก ไม่ได้ออกแบบมาให้ฟังชัด ผู้เรียนจึงฟังไม่รู้เรื่องตั้งแต่ข้อแรก
     *
     * เกณฑ์: อยู่ในเครื่อง > จีนแผ่นดินใหญ่ > ไม่ใช่เสียงเล่น > เป็นเสียงมาตรฐานที่รู้จัก
     */
    rank(v) {
      const name = (v.name || '').toLowerCase();
      const NOVELTY = ['eddy', 'flo', 'grandma', 'grandpa', 'reed', 'rocko',
                       'sandy', 'shelley', 'superstar', 'bubbles', 'jester'];
      const KNOWN_GOOD = ['ting-ting', 'tingting', '婷婷', 'li-mu', 'lilian', 'yu-shu',
                          'meijia', 'huihui', 'yaoyao', 'kangkang', 'xiaoxiao', 'yunxi',
                          '普通话', 'mandarin'];
      let score = 0;
      if (v.localService === false) score += 8;                       // ต้องต่อเน็ต + ข้อความออกนอกเครื่อง
      if (!/zh[-_](cn|hans)/i.test(v.lang)) score += 4;               // ไต้หวัน/กวางตุ้ง ออกเสียงคนละแบบ
      if (NOVELTY.some((n) => name.includes(n))) score += 2;          // เสียงเล่นของ Apple
      if (!KNOWN_GOOD.some((n) => name.includes(n))) score += 1;      // ไม่ใช่เสียงมาตรฐานที่รู้จัก
      return score;
    },

    /* ประโยคตัวอย่างสำหรับลองเสียง — ตั้งใจใช้ประโยคของเราเอง ไม่ใช่บทจากข้อสอบ
     * เพราะปุ่มนี้กดตอนไหนก็ได้ รวมถึงตอนยังไม่ได้เริ่มทำข้อ */
    preview() {
      if (!this.supported || !this.voice) return;
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance('你好，这是听力练习的声音。');
      u.voice = this.voice;
      u.lang = this.voice.lang;
      u.rate = this.rate;
      speechSynthesis.speak(u);
    },

    async load() {
      if (this.script) return true;
      this.loading = true;
      // 听写 ขอทีละประโยค ส่วนข้อฟังปกติขอทั้งบท
      const url = opts.sentence == null
        ? `/listen/${questionId}/script/`
        : `/listen/${questionId}/script/?s=${opts.sentence}`;
      try {
        const res = await fetch(url, { headers: { 'X-Requested-With': 'fetch' } });
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
