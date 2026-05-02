// api/translate.js — Vercel serverless function
// Reads OPENROUTER_API_KEY and OPENROUTER_MODEL_ID from Vercel env vars

const LANG_CONFIG = {
  vi:      { name: 'Vietnamese',           script: 'latin-diacritics', tonal: true },
  zh:      { name: 'Chinese Mandarin',     script: 'cjk',             tonal: true,  romanLabel: 'pinyin' },
  ja:      { name: 'Japanese',             script: 'cjk',             tonal: false, romanLabel: 'romaji' },
  th:      { name: 'Thai',                 script: 'thai',            tonal: true,  romanLabel: 'romanization' },
  tl:      { name: 'Filipino',             script: 'latin',           tonal: false },
  ru:      { name: 'Russian',              script: 'cyrillic',        tonal: false, romanLabel: 'transliteration' },
  uk:      { name: 'Ukrainian',            script: 'cyrillic',        tonal: false, romanLabel: 'transliteration' },
  it:      { name: 'Italian',              script: 'latin',           tonal: false },
  de:      { name: 'German',               script: 'latin',           tonal: false },
  fr:      { name: 'French',               script: 'latin',           tonal: false },
  'pt-br': { name: 'Brazilian Portuguese', script: 'latin',           tonal: false }
};

function buildForwardPrompt(lang) {
  const cfg = LANG_CONFIG[lang];
  if (!cfg) return null;
  const langName = cfg.name;

  let formatSpec;
  if (cfg.script === 'cjk') {
    formatSpec = `{"t":"${langName} text"${cfg.romanLabel ? `,"p":"${cfg.romanLabel}"` : ''},"s":[{"t":"syllable","m":"SIMPLE English mnemonic","h":"like [English word]"}]}`;
  } else if (cfg.script === 'cyrillic') {
    formatSpec = `{"t":"${langName} text in Cyrillic"${cfg.romanLabel ? `,"p":"${cfg.romanLabel}"` : ''},"s":[{"t":"syllable in original script","m":"SIMPLE English mnemonic","h":"like [English word]"}]}`;
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
}

function buildReversePrompt(lang) {
  const cfg = LANG_CONFIG[lang];
  if (!cfg) return null;
  const langName = cfg.name;

  const mnemonicMap = {
    zh: 'Chinese characters that approximate the English sounds (like 三克油 for "thank you")',
    ja: 'katakana that approximate the English sounds (like サンキュー for "thank you")',
    th: 'Thai script approximations of the English sounds',
    ru: 'Russian Cyrillic approximations of the English sounds (like сенк ю for "thank you")',
    uk: 'Ukrainian Cyrillic approximations of the English sounds'
  };
  const mnemonicDesc = mnemonicMap[lang] || `${langName} phonetic approximations of the English sounds`;

  const exampleMap = {
    zh: 'Example: "thank you" → word:"Thank you", m:"三克油", h:"sān kè yóu"',
    ja: 'Example: "thank you" → word:"Thank you", m:"サンキュー", h:"san kyuu"',
    vi: 'Example: "thank you" → word:"Thank you", m:"then-kiu", h:"đen-kiu"'
  };
  const formatExample = exampleMap[lang] || `Use ${langName} sounds/words that a native speaker would naturally reach for.`;

  const hintDesc = cfg.romanLabel || 'pronunciation note';

  return `A ${langName} speaker wants to say something in English. Translate their input to English, then provide ${mnemonicDesc} so they know how to PRONOUNCE the English words.

IMPORTANT: The user is a native ${langName} speaker. Write ALL hint text ("h" field) in ${langName}, NOT in English. The hints should be ${langName} explanations that help them pronounce the English words.

Return ONLY valid JSON (no markdown fences).
Format: {"e":"English translation","s":[{"word":"English word","m":"${langName} mnemonic","h":"${langName} hint explaining pronunciation"}]}
${formatExample}
Keep it natural — use ${langName} sounds/words that a native speaker would actually recognize and use. All explanatory text must be in ${langName}.`;
}

export default async function handler(req, res) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });

  const apiKey = process.env.OPENROUTER_API_KEY;
  const modelId = process.env.OPENROUTER_MODEL_ID;

  if (!apiKey || !modelId) {
    return res.status(500).json({ error: 'Server missing OPENROUTER_API_KEY or OPENROUTER_MODEL_ID env vars' });
  }

  const { phrase, lang, direction } = req.body;
  if (!phrase || !lang) {
    return res.status(400).json({ error: 'Missing phrase or lang in request body' });
  }

  if (!LANG_CONFIG[lang]) {
    return res.status(400).json({ error: `Unsupported language: ${lang}` });
  }

  const isReverse = direction === 'reverse';
  const systemPrompt = isReverse ? buildReversePrompt(lang) : buildForwardPrompt(lang);
  const userPrompt = isReverse ? phrase : `Translate: "${phrase}"`;

  try {
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
          content: userPrompt
        }],
        temperature: 0.2,
        max_tokens: 600
      })
    });

    if (!resp.ok) {
      const errText = await resp.text();
      return res.status(resp.status).json({ error: `OpenRouter error: ${resp.status}`, details: errText });
    }

    const data = await resp.json();
    const content = data.choices[0].message.content;
    const jsonMatch = content.match(/\{[\s\S]*\}/);

    if (!jsonMatch) {
      return res.status(500).json({ error: 'Could not parse AI response' });
    }

    return res.status(200).json(JSON.parse(jsonMatch[0]));
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
