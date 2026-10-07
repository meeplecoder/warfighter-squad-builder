/* =====================================================================
   i18n — UI strings + enum labels. Loaded before api.js / app.js.
   Dictionaries: /static/i18n/<lang>.json (flat keys; en.json is the source of truth).
   See spec/07_i18n.md.
   ===================================================================== */
const I18N = {
  SUPPORTED: ['en', 'es'],
  NAMES: { en: 'English', es: 'Español' },
  lang: 'en',
  dict: {},
  en: {},
};

async function _i18nLoad(lang) {
  const res = await fetch(`/static/i18n/${lang}.json`, { cache: 'no-cache' });
  if (!res.ok) throw new Error('i18n ' + lang);
  return res.json();
}

function i18nNormalize(lang) {
  const code = (lang || '').toLowerCase().split(/[-_]/)[0];
  return I18N.SUPPORTED.includes(code) ? code : null;
}

// Preferred language: ?lang= in URL → profile → localStorage → browser → en
function i18nPreferred(user) {
  let stored = null;
  try { stored = localStorage.getItem('lang'); } catch (_) {}
  const fromUrl = new URLSearchParams(location.search).get('lang');
  return i18nNormalize(fromUrl) || i18nNormalize(user?.language) || i18nNormalize(stored)
    || i18nNormalize(navigator.language) || 'en';
}

async function i18nSetLang(lang) {
  lang = i18nNormalize(lang) || 'en';
  if (!Object.keys(I18N.en).length) {
    try { I18N.en = await _i18nLoad('en'); } catch (_) { I18N.en = {}; }
  }
  if (lang === 'en') {
    I18N.dict = I18N.en;
  } else {
    try { I18N.dict = await _i18nLoad(lang); } catch (_) { I18N.dict = {}; lang = 'en'; }
  }
  I18N.lang = lang;
  try { localStorage.setItem('lang', lang); } catch (_) {}
  document.documentElement.lang = lang;
  i18nApplyStatic();
}

function _interp(str, params) {
  if (!params) return str;
  return str.replace(/\{(\w+)\}/g, (m, k) => (params[k] != null ? params[k] : m));
}

// t('cards.showing', {from, to, total}) — missing key → English → key itself
function t(key, params) {
  const str = I18N.dict[key] ?? I18N.en[key] ?? key;
  return _interp(str, params);
}

// Plural: tn('squads.count', n) looks up key_one / key_other (Intl plural rules); {n} available
function tn(key, n, params) {
  const cat = new Intl.PluralRules(I18N.lang).select(n);
  const k = (I18N.dict[`${key}_${cat}`] ?? I18N.en[`${key}_${cat}`]) != null ? `${key}_${cat}` : `${key}_other`;
  return t(k, { n, ...params });
}

// Enum value → label: tv('card_type', 'Weapon'). Unknown values are shown as-is.
function tv(ns, value) {
  if (value == null || value === '') return value ?? '';
  const k = `enum.${ns}.${value}`;
  return I18N.dict[k] ?? I18N.en[k] ?? value;
}

// Static markup: <el data-i18n="key"> sets textContent; data-i18n-title sets title
function i18nApplyStatic(root = document) {
  root.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });
  document.title = t('app.title');
}

function fmtNumber(n) {
  return n == null ? '' : new Intl.NumberFormat(I18N.lang).format(n);
}
