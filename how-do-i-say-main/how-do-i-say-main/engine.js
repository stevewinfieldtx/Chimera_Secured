// engine.js — Core pronunciation engine for HowDoISay
var Engine = {

  // ── Language Configuration ─────────────────────────────────────
  // Central config for all supported languages

  LANGS: {
    vi:    { name: 'Vietnamese',          flag: '🇻🇳', tonal: true,  hasRomanization: false, dictVar: 'DICT_VI',    script: 'latin-diacritics',
             nativeUI: { say: 'Nói:', typed: 'Gõ tiếng Việt...', loading: 'Đang dịch bằng AI...', toEn: 'Tiếng Việt → Tiếng Anh', poweredBy: 'Hỗ trợ bởi AI', phrasesLoaded: 'câu đã tải offline' } },
    zh:    { name: 'Chinese Mandarin',    flag: '🇨🇳', tonal: true,  hasRomanization: true,  dictVar: 'DICT_ZH',    script: 'cjk',  romanLabel: 'pinyin',
             nativeUI: { say: '说：', typed: '输入中文...', loading: 'AI翻译中...', toEn: '中文 → 英文', poweredBy: 'AI 驱动', phrasesLoaded: '个短语已离线加载' } },
    ja:    { name: 'Japanese',            flag: '🇯🇵', tonal: false, hasRomanization: true,  dictVar: 'DICT_JA',    script: 'cjk',  romanLabel: 'romaji',
             nativeUI: { say: '言う：', typed: '日本語を入力...', loading: 'AI翻訳中...', toEn: '日本語 → 英語', poweredBy: 'AI搭載', phrasesLoaded: 'フレーズをオフラインで読み込み済み' } },
    th:    { name: 'Thai',                flag: '🇹🇭', tonal: true,  hasRomanization: true,  dictVar: 'DICT_TH',    script: 'thai', romanLabel: 'romanization',
             nativeUI: { say: 'พูด:', typed: 'พิมพ์ภาษาไทย...', loading: 'กำลังแปลด้วย AI...', toEn: 'ไทย → อังกฤษ', poweredBy: 'ขับเคลื่อนด้วย AI', phrasesLoaded: 'วลีที่โหลดออฟไลน์' } },
    tl:    { name: 'Filipino',            flag: '🇵🇭', tonal: false, hasRomanization: false, dictVar: 'DICT_TL',    script: 'latin',
             nativeUI: { say: 'Sabihin:', typed: 'Mag-type ng Filipino...', loading: 'Nagta-translate gamit ang AI...', toEn: 'Filipino → English', poweredBy: 'Pinapagana ng AI', phrasesLoaded: 'mga parirala na naka-load offline' } },
    ru:    { name: 'Russian',             flag: '🇷🇺', tonal: false, hasRomanization: true,  dictVar: 'DICT_RU',    script: 'cyrillic', romanLabel: 'transliteration',
             nativeUI: { say: 'Скажите:', typed: 'Введите по-русски...', loading: 'AI переводит...', toEn: 'Русский → Английский', poweredBy: 'На базе AI', phrasesLoaded: 'фраз загружено офлайн' } },
    uk:    { name: 'Ukrainian',           flag: '🇺🇦', tonal: false, hasRomanization: true,  dictVar: 'DICT_UK',    script: 'cyrillic', romanLabel: 'transliteration',
             nativeUI: { say: 'Скажіть:', typed: 'Введіть українською...', loading: 'AI перекладає...', toEn: 'Українська → Англійська', poweredBy: 'На базі AI', phrasesLoaded: 'фраз завантажено офлайн' } },
    it:    { name: 'Italian',             flag: '🇮🇹', tonal: false, hasRomanization: false, dictVar: 'DICT_IT',    script: 'latin',
             nativeUI: { say: 'Dì:', typed: 'Scrivi in italiano...', loading: 'Traduzione AI in corso...', toEn: 'Italiano → Inglese', poweredBy: 'Con AI', phrasesLoaded: 'frasi caricate offline' } },
    de:    { name: 'German',              flag: '🇩🇪', tonal: false, hasRomanization: false, dictVar: 'DICT_DE',    script: 'latin',
             nativeUI: { say: 'Sag:', typed: 'Auf Deutsch tippen...', loading: 'KI übersetzt...', toEn: 'Deutsch → Englisch', poweredBy: 'KI-gestützt', phrasesLoaded: 'Sätze offline geladen' } },
    fr:    { name: 'French',              flag: '🇫🇷', tonal: false, hasRomanization: false, dictVar: 'DICT_FR',    script: 'latin',
             nativeUI: { say: 'Dites :', typed: 'Tapez en français...', loading: 'Traduction IA en cours...', toEn: 'Français → Anglais', poweredBy: 'Propulsé par IA', phrasesLoaded: 'phrases chargées hors ligne' } },
    'pt-br': { name: 'Brazilian Portuguese', flag: '🇧🇷', tonal: false, hasRomanization: false, dictVar: 'DICT_PTBR', script: 'latin',
             nativeUI: { say: 'Diga:', typed: 'Digite em português...', loading: 'Traduzindo com IA...', toEn: 'Português → Inglês', poweredBy: 'Com IA', phrasesLoaded: 'frases carregadas offline' } }
  },

  langName(lang) {
    return (this.LANGS[lang] || {}).name || lang;
  },

  langFlag(lang) {
    return (this.LANGS[lang] || {}).flag || '';
  },

  // ── Tone / Stress Detection ────────────────────────────────────

  detectTone(text, lang) {
    if (lang === 'vi') return this.detectViTone(text);
    if (lang === 'zh') return this.detectZhTone(text);
    if (lang === 'th') return this.detectThTone(text);
    // Non-tonal languages: use stress markers if present in entry, else neutral
    return 'neutral';
  },

  detectViTone(text) {
    for (const ch of text) {
      if (/[ạặậẹịọộụựỵ]/.test(ch)) return 'heavy';
      if (/[ãẵẫẽĩõỗũữỹ]/.test(ch)) return 'broken';
      if (/[ảẳẩẻỉỏổủửỷ]/.test(ch)) return 'dipping';
      if (/[áắấéíóốúứý]/.test(ch)) return 'rising';
      if (/[àằầèìòồùừỳ]/.test(ch)) return 'falling';
    }
    return 'flat';
  },

  detectZhTone(text) {
    for (const ch of text) {
      if (/[āēīōūǖ]/.test(ch)) return 'flat';
      if (/[áéíóúǘ]/.test(ch)) return 'rising';
      if (/[ǎěǐǒǔǚ]/.test(ch)) return 'dipping';
      if (/[àèìòùǜ]/.test(ch)) return 'falling';
    }
    return 'neutral';
  },

  detectThTone(text) {
    // Thai tone marks: mai ek (่) = low, mai tho (้) = falling, mai tri (๊) = high, mai chattawa (๋) = rising
    for (const ch of text) {
      if (ch === '่') return 'low';      // mai ek
      if (ch === '้') return 'falling';   // mai tho
      if (ch === '๊') return 'high';      // mai tri
      if (ch === '๋') return 'rising';    // mai chattawa
    }
    return 'mid';
  },

  // ── Tone Metadata ───────────────────────────────────────────

  toneColor(tone) {
    return {
      flat:'#16a34a', rising:'#2563eb', falling:'#dc2626',
      dipping:'#ea580c', heavy:'#7f1d1d', broken:'#7c3aed', neutral:'#6b7280',
      low:'#7c3aed', mid:'#16a34a', high:'#dc2626'
    }[tone] || '#333';
  },

  toneLabel(tone) {
    return {
      flat:'→ Flat', rising:'↗ Rising', falling:'↘ Falling',
      dipping:'↘↗ Dip-rise', heavy:'↓ Heavy drop', broken:'↗↘↗ Broken rise', neutral:'— Neutral',
      low:'↘ Low', mid:'→ Mid', high:'↗ High'
    }[tone] || tone;
  },

  toneEmoji(tone) {
    return {
      flat:'➡️', rising:'⬆️', falling:'⬇️',
      dipping:'↩️', heavy:'⏬', broken:'🔀', neutral:'⚪',
      low:'⬇️', mid:'➡️', high:'⬆️'
    }[tone] || '';
  },

  // ── Staircase Curve ─────────────────────────────────────────
  // Returns array of Y-offsets (px). 0 = highest pitch.

  getToneCurve(len, tone) {
    if (len < 1) return [];
    const n = len;
    const step = 4; // px per step
    const curves = {
      flat:    () => Array(n).fill(0),
      rising:  () => Array.from({length:n}, (_,i) => (n-1-i) * step),
      falling: () => Array.from({length:n}, (_,i) => i * step),
      dipping: () => {
        const mid = Math.floor(n/2);
        return Array.from({length:n}, (_,i) => {
          if (i <= mid) return i * step;
          return (n-1-i) * step;
        });
      },
      heavy:   () => Array.from({length:n}, (_,i) => i * step),
      broken:  () => {
        const t = Math.floor(n/3) || 1;
        return Array.from({length:n}, (_,i) => {
          if (i < t) return (t-i) * step;
          if (i < t*2) return (i-t) * step;
          return (n-1-i) * step;
        });
      },
      neutral: () => Array(n).fill(0),
      low:     () => Array.from({length:n}, (_,i) => i * (step * 0.5)),
      mid:     () => Array(n).fill(0),
      high:    () => Array.from({length:n}, (_,i) => (n-1-i) * (step * 0.5))
    };
    return (curves[tone] || curves.neutral)();
  },

  // ── Rendering ───────────────────────────────────────────────

  renderSyllableHTML(syl, tone, lang) {
    const cfg = this.LANGS[lang] || {};
    const word = syl.m;
    const color = cfg.tonal ? this.toneColor(tone) : 'var(--pri)';

    if (cfg.tonal) {
      // Tonal languages: show staircase visualization
      const curve = this.getToneCurve(word.length, tone);
      const label = this.toneLabel(tone);
      let letters = '';
      for (let i = 0; i < word.length; i++) {
        const ch = word[i] === ' ' ? '&nbsp;' : word[i];
        letters += `<span class="stair-ch" style="transform:translateY(${curve[i]}px)">${ch}</span>`;
      }
      return `
        <div class="syl-block">
          <div class="staircase" style="color:${color}">${letters}</div>
          <div class="syl-hint">${syl.h}</div>
          <div class="syl-tone" style="color:${color}">${label}</div>
          <div class="syl-target">${syl.t}</div>
        </div>`;
    } else {
      // Non-tonal: simpler block, no staircase curves
      return `
        <div class="syl-block">
          <div class="staircase" style="color:${color}">${word.split('').map(ch => ch === ' ' ? '&nbsp;' : `<span class="stair-ch">${ch}</span>`).join('')}</div>
          <div class="syl-hint">${syl.h}</div>
          <div class="syl-target">${syl.t}</div>
        </div>`;
    }
  },

  renderResult(entry, lang) {
    const cfg = this.LANGS[lang] || {};

    // Quick mnemonic line (top)
    const quick = entry.s.map(s => s.m).join(' · ');
    let html = `<div class="res-quick">Say: <strong>${quick}</strong></div>`;

    // Target text + romanization (if applicable)
    if (entry.t) {
      html += `<div class="res-target">${entry.t}</div>`;
      if (entry.p && cfg.hasRomanization) {
        html += `<div class="res-pinyin">${entry.p}</div>`;
      }
    }

    // Syllable blocks
    html += `<div class="staircase-row">`;
    for (const syl of entry.s) {
      const tone = this.detectTone(syl.t, lang);
      html += this.renderSyllableHTML(syl, tone, lang);
    }
    html += `</div>`;

    return html;
  },

  // ── Dictionary Lookup ───────────────────────────────────────

  _dict(lang) {
    const cfg = this.LANGS[lang];
    if (!cfg) return {};
    return window[cfg.dictVar] || {};
  },

  lookup(phrase, lang) {
    const dict = this._dict(lang);
    const key = phrase.toLowerCase().trim().replace(/[?.!,'"]/g, '');
    if (dict[key]) return dict[key];

    // Try with/without "please", "the", "a"
    const stripped = key.replace(/\b(please|the|a|an)\b/g, '').replace(/\s+/g, ' ').trim();
    if (dict[stripped]) return dict[stripped];

    return null;
  },

  fuzzyMatch(phrase, lang) {
    const dict = this._dict(lang);
    const key = phrase.toLowerCase().trim();
    const keys = Object.keys(dict);
    let best = null, bestScore = 0;

    const inputWords = key.split(/\s+/);

    for (const k of keys) {
      // Substring containment
      if (k.includes(key) || key.includes(k)) {
        const score = Math.min(k.length, key.length) / Math.max(k.length, key.length);
        if (score > bestScore) { bestScore = score; best = {key:k, entry:dict[k]}; }
      }
      // Word overlap
      const entryWords = k.split(/\s+/);
      const common = inputWords.filter(w => entryWords.includes(w)).length;
      if (common > 0) {
        const score = common / Math.max(inputWords.length, entryWords.length);
        if (score > bestScore) { bestScore = score; best = {key:k, entry:dict[k]}; }
      }
    }

    return bestScore > 0.3 ? best : null;
  },

  // Get all keys for suggestion filtering
  allKeys(lang) { return Object.keys(this._dict(lang)); },

  // ── API Prompt Builders ────────────────────────────────────────

  _buildForwardPrompt(lang) {
    const cfg = this.LANGS[lang];
    const langName = cfg.name;

    // Build the format spec based on language features
    let formatSpec;
    if (cfg.script === 'cjk') {
      formatSpec = `{"t":"${langName} text"${cfg.hasRomanization ? `,"p":"${cfg.romanLabel}"` : ''},"s":[{"t":"syllable","m":"SIMPLE English mnemonic","h":"like [English word]"}]}`;
    } else if (cfg.script === 'cyrillic') {
      formatSpec = `{"t":"${langName} text in Cyrillic"${cfg.hasRomanization ? `,"p":"${cfg.romanLabel}"` : ''},"s":[{"t":"syllable in original script","m":"SIMPLE English mnemonic","h":"like [English word]"}]}`;
    } else if (cfg.script === 'thai') {
      formatSpec = `{"t":"Thai script","p":"romanization","s":[{"t":"Thai syllable","m":"SIMPLE English mnemonic","h":"like [English word]"}]}`;
    } else if (cfg.script === 'latin-diacritics') {
      formatSpec = `{"t":"${langName} text with diacritics","s":[{"t":"syllable with diacritics/accents","m":"SIMPLE English mnemonic","h":"like [English word]"}]}`;
    } else {
      formatSpec = `{"t":"${langName} text","s":[{"t":"word/syllable","m":"SIMPLE English mnemonic","h":"like [English word]"}]}`;
    }

    return `You translate English to ${langName} and provide dead-simple pronunciation help using English words or syllables — NOT IPA. Return ONLY valid JSON (no markdown fences).
Format: ${formatSpec}
Rules for mnemonics:
- Use REAL English words or obvious parts of words — the reader must already know how to say it
- Pattern A (best): m is a real word — "Knee", "How", "Boo", "Joe", "Kong"
- Pattern B: a known word with modification — "'fun' without the N", "'shed' without the D"
- Pattern C: two known things — "'gee' then 'N'", "'she' + 'way'"
- NEVER use made-up syllables like "Bahn", "Hwey", "Tahng"
- One entry per syllable or natural word-chunk.`;
  },

  _buildReversePrompt(lang) {
    const cfg = this.LANGS[lang];
    const langName = cfg.name;

    let mnemonicDesc;
    if (lang === 'zh') {
      mnemonicDesc = 'Chinese characters that approximate the English sounds (like 三克油 for "thank you")';
    } else if (lang === 'ja') {
      mnemonicDesc = 'katakana that approximate the English sounds (like サンキュー for "thank you")';
    } else if (lang === 'th') {
      mnemonicDesc = 'Thai script approximations of the English sounds';
    } else if (lang === 'ru') {
      mnemonicDesc = 'Russian Cyrillic approximations of the English sounds (like сенк ю for "thank you")';
    } else if (lang === 'uk') {
      mnemonicDesc = 'Ukrainian Cyrillic approximations of the English sounds';
    } else {
      mnemonicDesc = `${langName} phonetic approximations of the English sounds`;
    }

    let formatExample;
    if (lang === 'zh') {
      formatExample = 'Example: "thank you" → word:"Thank you", m:"三克油", h:"sān kè yóu"';
    } else if (lang === 'ja') {
      formatExample = 'Example: "thank you" → word:"Thank you", m:"サンキュー", h:"san kyuu"';
    } else if (lang === 'vi') {
      formatExample = 'Example: "thank you" → word:"Thank you", m:"then-kiu", h:"đen-kiu"';
    } else {
      formatExample = `Use ${langName} sounds/words that a native speaker would naturally reach for.`;
    }

    const hintDesc = cfg.hasRomanization ? cfg.romanLabel : 'pronunciation note';

    const nui = cfg.nativeUI || {};
    const nativeSay = nui.say || 'Say:';

    return `A ${langName} speaker wants to say something in English. Translate their input to English, then provide ${mnemonicDesc} so they know how to PRONOUNCE the English words.

IMPORTANT: The user is a native ${langName} speaker. Write ALL hint text ("h" field) in ${langName}, NOT in English. The hints should be ${langName} explanations that help them pronounce the English words.

Return ONLY valid JSON (no markdown fences).
Format: {"e":"English translation","s":[{"word":"English word","m":"${langName} mnemonic","h":"${langName} hint explaining pronunciation"}]}
${formatExample}
Keep it natural — use ${langName} sounds/words that a native speaker would actually recognize and use. All explanatory text must be in ${langName}.`;
  },

  // ── OpenRouter API Fallback ─────────────────────────────────

  async apiTranslate(phrase, lang, apiKey, modelId) {
    // 1. Try server-side proxy
    try {
      const proxyResp = await fetch('/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phrase, lang })
      });
      if (proxyResp.ok) {
        return await proxyResp.json();
      }
    } catch (e) {}

    // 2. Fall back to direct OpenRouter call
    if (!apiKey || !modelId) {
      throw new Error('No API available. Add an OpenRouter key in Settings or deploy to Vercel with env vars.');
    }

    const systemPrompt = this._buildForwardPrompt(lang);

    const resp = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://howdoisay.app'
      },
      body: JSON.stringify({
        model: modelId,
        messages: [{
          role: 'system',
          content: systemPrompt
        }, {
          role: 'user',
          content: `Translate: "${phrase}"`
        }],
        temperature: 0.2,
        max_tokens: 600
      })
    });

    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    const data = await resp.json();
    const content = data.choices[0].message.content;
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error('Could not parse API response');
    return JSON.parse(jsonMatch[0]);
  },

  // ── Reverse Translation (Target → English) ──────────────────

  async apiReverseTranslate(phrase, lang, apiKey, modelId) {
    // 1. Try server-side proxy first
    try {
      const proxyResp = await fetch('/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phrase, lang, direction: 'reverse' })
      });
      if (proxyResp.ok) return await proxyResp.json();
    } catch (e) {}

    // 2. Fall back to direct call
    if (!apiKey || !modelId) {
      throw new Error('No API available. Deploy to Vercel with env vars or add a key in Settings.');
    }

    const systemPrompt = this._buildReversePrompt(lang);

    const resp = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://howdoisay.app'
      },
      body: JSON.stringify({
        model: modelId,
        messages: [{
          role: 'system',
          content: systemPrompt
        }, {
          role: 'user',
          content: phrase
        }],
        temperature: 0.2,
        max_tokens: 600
      })
    });

    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    const data = await resp.json();
    const content = data.choices[0].message.content;
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error('Could not parse API response');
    return JSON.parse(jsonMatch[0]);
  },

  // ── Render Reverse Result ──────────────────────────────────

  renderReverseResult(entry, lang) {
    const nui = (this.LANGS[lang] && this.LANGS[lang].nativeUI) || {};
    const sayLabel = nui.say || 'Say:';
    let html = `<div class="rev-label">${sayLabel}</div>`;
    html += `<div class="rev-english">${entry.e}</div>`;
    html += `<div class="rev-row">`;
    for (const s of entry.s) {
      html += `<div class="rev-block">`;
      html += `<div class="rev-word">${s.word}</div>`;
      html += `<div class="rev-mnemonic">${s.m}</div>`;
      html += `<div class="rev-hint">${s.h}</div>`;
      html += `</div>`;
    }
    html += `</div>`;
    return html;
  },

  // ── Reverse-mode sample chips per language ─────────────────

  reverseSamples: {
    vi: ['xin chào','cảm ơn','bao nhiêu','bia','nước','phở','tạm biệt','giúp tôi'],
    zh: ['你好','谢谢','多少钱','啤酒','水','再见','救命','厕所在哪'],
    ja: ['こんにちは','ありがとう','いくら','ビール','水','さようなら','助けて','トイレはどこ'],
    th: ['สวัสดี','ขอบคุณ','ราคาเท่าไหร่','เบียร์','น้ำ','ลาก่อน','ช่วยด้วย','ห้องน้ำอยู่ที่ไหน'],
    tl: ['kumusta','salamat','magkano','beer','tubig','paalam','tulong','saan ang banyo'],
    ru: ['привет','спасибо','сколько','пиво','вода','до свидания','помогите','где туалет'],
    uk: ['привіт','дякую','скільки','пиво','вода','до побачення','допоможіть','де туалет'],
    it: ['ciao','grazie','quanto costa','birra','acqua','arrivederci','aiuto','dove il bagno'],
    de: ['hallo','danke','wie viel','Bier','Wasser','auf Wiedersehen','Hilfe','wo ist die Toilette'],
    fr: ['bonjour','merci','combien','bière','eau','au revoir','aidez-moi','où sont les toilettes'],
    'pt-br': ['olá','obrigado','quanto custa','cerveja','água','tchau','socorro','onde é o banheiro']
  },

  // ── Main Entry Point ────────────────────────────────────────

  async process(phrase, lang, apiKey, modelId) {
    if (!phrase.trim()) return null;

    // 1. Exact lookup
    const exact = this.lookup(phrase, lang);
    if (exact) return { entry: exact, source: 'local' };

    // 2. Fuzzy match
    const fuzzy = this.fuzzyMatch(phrase, lang);
    if (fuzzy) return { entry: fuzzy.entry, source: 'local', matchedKey: fuzzy.key };

    // 3. API fallback
    if (apiKey && modelId) {
      const entry = await this.apiTranslate(phrase, lang, apiKey, modelId);
      return { entry, source: 'api' };
    }

    return null;
  }
};
