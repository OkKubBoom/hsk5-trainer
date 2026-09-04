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
    turns: [],
    audioUrl: '',
    el: null,                 // <audio> ของไฟล์ที่อัดไว้ ถ้ามี
    runId: 0,
    plays: 0,
    playing: false,
    loading: false,
    rate: 1,
    voiceName: localStorage.getItem('listenVoice') || '',
    supported: typeof window.speechSynthesis !== 'undefined',
    get usingFile() { return !!this.audioUrl; },
    get ready() { return this.usingFile || (this.supported && !!this.voice); },
    voice: null,
    voices: [],
    remoteVoice: false,
    error: '',
    revealed: false,

    init() {
      const saved = parseFloat(localStorage.getItem('listenRate'));
      if (saved >= 0.5 && saved <= 1.5) this.rate = saved;
      this.$watch('rate', (v) => {
        localStorage.setItem('listenRate', v);
        if (this.el) this.el.playbackRate = v;   // ไฟล์เสียงเปลี่ยนความเร็วได้ทันทีระหว่างเล่น
      });
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
      this.stop();
      speechSynthesis.speak(this.utter('你好，这是听力练习的声音。', 'n'));
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
        const body = await res.json();
        this.script = body.script || '';
        this.turns = body.turns || [];
        // 听写 มีไฟล์รายประโยคของตัวเอง เอนด์พอยต์ส่งมาให้แล้ว
        this.audioUrl = body.audio || '';
      } catch (e) {
        this.error = 'โหลดบทไม่สำเร็จ ลองกดใหม่อีกครั้ง';
      }
      this.loading = false;
      return !!this.script;
    },

    async play() {
      this.error = '';
      if (!(await this.load())) return;
      if (this.audioUrl) return this.playFile();
      if (!this.supported) return;

      speechSynthesis.cancel();
      this.plays += 1;
      if (this.turns.length) return this.speakTurns();

      const u = this.utter(this.script, 'n');
      u.onstart = () => { this.playing = true; };
      u.onend = () => { this.playing = false; };
      speechSynthesis.speak(u);
    },

    /* เล่นไฟล์ที่อัดไว้ล่วงหน้า
     *
     * เสียงในไฟล์ดีกว่าตัวอ่านของเบราว์เซอร์มาก และ *ทุกคนได้ยินเหมือนกัน*
     * ไม่ว่าจะเปิดจากเครื่องอะไร ซึ่งตัวอ่านของเบราว์เซอร์ทำไม่ได้เลย
     * จังหวะเว้นระหว่างคนพูดถูกอัดมาในไฟล์แล้ว
     *
     * ปรับความเร็วด้วย playbackRate ซึ่งเบราว์เซอร์สมัยใหม่รักษาระดับเสียงไว้ให้
     * ไม่กลายเป็นเสียงการ์ตูนเหมือนการเร่งเทป
     *
     * โหลดไฟล์ไม่ได้ (เน็ตหลุด / ยังไม่ได้สร้างไฟล์ข้อนั้น) ให้ถอยไปใช้ตัวอ่านของเบราว์เซอร์
     * ดีกว่าขึ้น error แล้วผู้เรียนทำข้อนั้นไม่ได้เลย
     */
    playFile() {
      if (!this.el) {
        this.el = new Audio(this.audioUrl);
        this.el.preload = 'auto';
        this.el.addEventListener('ended', () => { this.playing = false; });
        this.el.addEventListener('error', () => {
          this.audioUrl = '';
          this.el = null;
          this.playing = false;
          if (this.supported) this.play();     // ถอยไปใช้ตัวอ่านของเบราว์เซอร์
          else this.error = 'โหลดไฟล์เสียงไม่สำเร็จ';
        });
      }
      this.el.playbackRate = this.rate;
      this.el.currentTime = 0;
      this.plays += 1;
      this.playing = true;
      this.el.play().catch(() => { this.playing = false; });
    },

    /* สร้างคำสั่งอ่านหนึ่งช่วง — แยกเสียงผู้พูดด้วยระดับเสียง
     *
     * เครื่องส่วนใหญ่มีเสียงจีนที่ใช้ได้จริงตัวเดียว (บน Mac คือ Tingting)
     * จะสลับเป็นเสียงผู้ชายจริงๆ ไม่ได้ จึงลดระดับเสียงลงแทนเมื่อเป็นตาผู้ชายพูด
     * ไม่ได้ทำให้เหมือนผู้ชายจริง แต่ทำให้ *แยกออกว่าเปลี่ยนคนพูดแล้ว*
     * ซึ่งคือสิ่งที่คำถามอย่าง "ผู้ชายหมายความว่าอะไร" ต้องใช้
     *
     * คำถามท้ายข้อใช้ระดับเสียงปกติและช้าลงนิด เพราะเป็นเสียงผู้บรรยาย ไม่ใช่คู่สนทนา
     */
    utter(text, who) {
      const u = new SpeechSynthesisUtterance(text);
      if (this.voice) { u.voice = this.voice; u.lang = this.voice.lang; }
      else u.lang = 'zh-CN';
      u.rate = who === 'q' ? this.rate * 0.94 : this.rate;
      u.pitch = who === 'm' ? 0.72 : 1;
      u.onerror = (e) => {
        if (e.error === 'interrupted' || e.error === 'canceled') return;  // เรากดหยุดเอง
        this.playing = false;
        this.error = 'เล่นเสียงไม่สำเร็จ — ลองกดอีกครั้ง หรือเปิดเสียงเครื่องดู';
      };
      return u;
    },

    /* เล่นทีละช่วง พร้อมเว้นจังหวะ
     *
     * ข้อสอบจริงมีช่องว่างระหว่างคนพูด และเว้นนานกว่านั้นก่อนอ่านคำถาม
     * ถ้าอ่านรวดเดียวไม่หยุด ผู้เรียนจะไม่รู้ว่าคำถามเริ่มตรงไหน
     * แล้วพลาดทั้งข้อทั้งที่ฟังบทออกครบทุกคำ
     */
    speakTurns() {
      /* ใช้ *ตัวเลข* เป็นเครื่องหมายรอบ ไม่ใช่ object
         Alpine ห่อทุก object ที่เก็บใน x-data ด้วย Proxy การเทียบ !== กับตัวต้นฉบับ
         จึงเป็นจริงเสมอ แม้เป็นรอบเดียวกัน — เคยทำให้เสียงไม่เล่นเลยสักช่วง */
      const id = ++this.runId;
      this.playing = true;

      const step = (i) => {
        if (this.runId !== id) return;             // มีคนกดหยุดหรือกดเล่นใหม่
        if (i >= this.turns.length) { this.playing = false; return; }

        const turn = this.turns[i];
        const u = this.utter(turn.text, turn.who);
        u.onend = () => {
          if (this.runId !== id) return;
          const next = this.turns[i + 1];
          // เว้นนานกว่าก่อนคำถาม เพราะเป็นการเปลี่ยนบทบาท ไม่ใช่แค่เปลี่ยนคนพูด
          const gap = !next ? 0 : (next.who === 'q' ? 850 : 380);
          setTimeout(() => step(i + 1), gap);
        };
        speechSynthesis.speak(u);
      };
      step(0);
    },

    stop() {
      this.runId += 1;                 // ตัดคิวก่อน ไม่งั้น onend จะสั่งเล่นช่วงถัดไปต่อ
      if (this.el) { this.el.pause(); this.el.currentTime = 0; }
      if (this.supported) speechSynthesis.cancel();
      this.playing = false;
    },

    async reveal() {
      // ทางออกสุดท้ายเมื่อเครื่องไม่มีเสียงจีน — บอกตรงๆ ว่ากลายเป็นการอ่านแล้ว
      if (await this.load()) this.revealed = true;
    },
  };
};
