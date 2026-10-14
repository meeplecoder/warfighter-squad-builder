/* =====================================================================
   Warfighter Squad Builder — SPA (vanilla JS, hash router)
   ===================================================================== */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let currentUser = null;

const builderState = {
  squadId: null,       // null = new squad
  parentSquadId: null, // set when copying another squad ("based on")
  parentName: '',
  name: '',
  missionCard: null,
  objectiveCards: [],
  situationCard: null,
  nation: '',
  notes: '',
  soldiers: [],        // [{card, gear:[{card,quantity}], defaultGear:[{card,quantity}]}]
  pickerMode: null,    // 'mission'|'objective'|'situation'|'soldier'|'gear'
  pickerTarget: null,  // soldier index (for gear mode)
  pickerGearCat: null, // 'Weapon'|'Equipment'|'Skill'|'Service Record'|null=all
  pickerSort: 'module',
  pickerOrder: 'asc',
  pickerPage: 1,
  pickerModule: '',
  pickerQ: '',
};

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------
const routes = {};

function register(name, fn) { routes[name] = fn; }

function route() {
  const hash = location.hash.slice(1) || '/cards';
  const parts = hash.split('/').filter(Boolean);
  const key = parts[0] || 'cards';
  const rest = parts.slice(1);
  // Campaign editor (new or edit) lights up the nested campaign "Builder" link
  updateActiveNav(key === 'campaigns' && (rest[0] === 'new' || rest[1] === 'edit') ? 'campaigns/new' : key);
  // Tab title: section by default; detail / editor views refine it with setPageTitle
  const section = { cards: 'nav.cards', squads: 'nav.squads', builder: 'nav.builder', generator: 'nav.generator', campaigns: 'nav.campaigns',
                    expansions: 'nav.expansions', profile: 'nav.profile', translations: 'nav.translations' }[key];
  setPageTitle(section ? t(section) : null);
  const handler = routes[key] || routes['404'];
  if (handler) handler(...rest);
}

// Browser tab title: "<parts> · <app>"
function setPageTitle(...parts) {
  document.title = [...parts.filter(Boolean), t('app.title')].join(' · ');
}

function navigate(path) {
  location.hash = '#/' + path;
}

window.addEventListener('hashchange', route);
window.addEventListener('load', boot);

function updateActiveNav(key) {
  document.querySelectorAll('#sidebar .nav-link').forEach(a => {
    a.classList.toggle('active', a.dataset.route === key);
  });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function boot() {
  try {
    const data = await API.get('/auth/me');
    currentUser = data.user;
  } catch (e) {
    currentUser = null;
  }
  await i18nSetLang(i18nPreferred(currentUser));
  // Pre-load nations so builder nation select is available on first visit
  try { const r = await API.get('/nations'); allNations = r.nations || []; } catch (_) {}
  renderHeader();
  updateProfileLink();
  route();
}

function renderHeader() {
  const nav = document.getElementById('header-auth');
  const langSelect = `
    <select id="lang-select" class="lang-select" title="${esc(t('header.language'))}">
      ${I18N.SUPPORTED.map(l => `<option value="${l}" ${l === I18N.lang ? 'selected' : ''}>${esc(I18N.NAMES[l])}</option>`).join('')}
    </select>`;
  if (currentUser) {
    nav.innerHTML = `
      ${langSelect}
      <div class="user-menu-wrap">
        <button type="button" class="user-btn" id="user-menu-btn" aria-haspopup="menu" aria-expanded="false"
                aria-controls="user-menu" title="${esc(t('user.menu'))}">
          <span class="username">${esc(currentUser.username)}</span>
          <span class="user-avatar" aria-hidden="true">${icon('user')}</span>
        </button>
        <div class="user-menu" id="user-menu" role="menu" hidden>
          <a role="menuitem" href="#/expansions">${icon('layers')}<span>${esc(t('nav.expansions'))}</span></a>
          <a role="menuitem" href="#/profile">${icon('user')}<span>${esc(t('nav.profile'))}</span></a>
          <hr>
          <button type="button" role="menuitem" id="logout-btn">${icon('logout')}<span>${esc(t('header.logout'))}</span></button>
        </div>
      </div>`;
    wireUserMenu(nav);
  } else {
    nav.innerHTML = `
      ${langSelect}
      <a href="#/login" class="btn btn-sm btn-ghost">${esc(t('header.login'))}</a>
      <a href="#/register" class="btn btn-sm btn-primary">${esc(t('header.register'))}</a>`;
  }
  nav.querySelector('#lang-select').addEventListener('change', e => changeLanguage(e.target.value));
}

// Header user menu: opens from the icon next to the name; closes on outside click, Esc, selection and navigation
function wireUserMenu(root) {
  const btn = root.querySelector('#user-menu-btn'), menu = root.querySelector('#user-menu');
  const items = () => [...menu.querySelectorAll('[role=menuitem]')];
  const setOpen = open => {
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) items()[0]?.focus();
  };
  btn.addEventListener('click', e => { e.stopPropagation(); setOpen(menu.hidden); });
  menu.addEventListener('click', e => { if (e.target.closest('[role=menuitem]')) setOpen(false); });
  menu.addEventListener('keydown', e => {
    const list = items(), i = list.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); list[(i + 1) % list.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); list[(i - 1 + list.length) % list.length].focus(); }
    else if (e.key === 'Escape') { setOpen(false); btn.focus(); }
    else if (e.key === 'Tab') setOpen(false);
  });
  root.querySelector('#logout-btn').addEventListener('click', doLogout);
  if (!wireUserMenu.global) {                 // page-level listeners are added once, whatever the header re-renders
    wireUserMenu.global = true;
    const close = () => {
      const m = document.getElementById('user-menu'), b = document.getElementById('user-menu-btn');
      if (m && !m.hidden) { m.hidden = true; b?.setAttribute('aria-expanded', 'false'); }
    };
    document.addEventListener('click', e => { const m = document.getElementById('user-menu'); if (m && !m.contains(e.target)) close(); });
    window.addEventListener('hashchange', close);
  }
}

function updateProfileLink() {
  const link = document.getElementById('nav-expansions');           // My Expansions needs a login
  if (link) link.style.display = currentUser ? '' : 'none';
  const trLink = document.getElementById('nav-translations');
  if (trLink) trLink.style.display = currentUser?.is_admin ? '' : 'none';
  const cbLink = document.getElementById('nav-campaign-builder');   // campaign editor needs a login
  if (cbLink) cbLink.style.display = currentUser ? '' : 'none';
  const genLink = document.getElementById('nav-generator');          // generator needs a login
  if (genLink) genLink.style.display = currentUser ? '' : 'none';
}

// Switch UI + card language, persist it, and re-render the current view in place
async function changeLanguage(lang) {
  await i18nSetLang(lang);
  if (currentUser) {
    try { await API.put('/profile/', { language: I18N.lang }); currentUser.language = I18N.lang; } catch (_) {}
  }
  renderHeader();
  const key = (location.hash.slice(1) || '/cards').split('/').filter(Boolean)[0];
  if (key === 'builder') {
    await refreshBuilderCards();
    renderBuilder();
  } else {
    route();
  }
}

// After login: adopt the profile language if the user has one
async function applyUserLanguage() {
  const lang = i18nNormalize(currentUser?.language);
  if (lang && lang !== I18N.lang) await i18nSetLang(lang);
}

async function doLogout() {
  await API.post('/auth/logout');
  currentUser = null;
  renderHeader();
  updateProfileLink();
  navigate('cards');
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function setMain(html) {
  document.getElementById('app-main').innerHTML = html;
}

function showSpinner() {
  setMain('<div class="spinner-wrap"><div class="spinner"></div></div>');
}

function showError(msg) {
  setMain(`<div class="alert alert-error">${esc(msg)}</div>`);
}

function alertHtml(msg, type = 'error') {
  return `<div class="alert alert-${type}">${esc(msg)}</div>`;
}

// ---- Action icons + buttons (squad/campaign detail and builders) ---------
// 24px line icons, stroke = currentColor, sized by .icon
const ICON_PATHS = {
  back:     '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',
  prev:     '<path d="m15 18-6-6 6-6"/>',
  next:     '<path d="m9 18 6-6-6-6"/>',
  up:       '<path d="m18 15-6-6-6 6"/>',
  down:     '<path d="m6 9 6 6 6-6"/>',
  edit:     '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  trash:    '<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="m19 6-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  copy:     '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  upload:   '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
  save:     '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/>',
  publish:  '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  validate: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>',
  close:    '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  heart:    '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',
  plus:     '<path d="M12 5v14"/><path d="M5 12h14"/>',
  user:     '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>',
  layers:   '<path d="m12 3 9 5-9 5-9-5Z"/><path d="m3 13 9 5 9-5"/><path d="m3 17.500 9 5 9-5"/>',
  logout:   '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
};
function icon(name) {
  return `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name]}</svg>`;
}

// Icon + label button. variant: ghost | primary | danger (outlined red). href → <a>; disabled href → inert <span>.
// The label hides on narrow screens (secondary buttons only), the title keeps it discoverable.
function actionBtn({ icon: ic, label, variant = 'ghost', id, href, title, attrs = '', cls: extra = '', iconOnly = false, disabled = false }) {
  const cls = `btn btn-${variant === 'danger' ? 'danger-ghost' : variant}${iconOnly ? ' btn-square' : ''}${extra ? ' ' + extra : ''}`;
  const inner = `${ic ? icon(ic) : ''}${iconOnly ? '' : `<span class="btn-label">${esc(label)}</span>`}`;
  const common = `class="${cls}" ${id ? `id="${id}"` : ''} title="${esc(title || label)}" aria-label="${esc(label)}" ${attrs}`;
  if (href != null) return disabled ? `<span ${common} aria-disabled="true">${inner}</span>` : `<a href="${href}" ${common}>${inner}</a>`;
  return `<button type="button" ${common} ${disabled ? 'disabled' : ''}>${inner}</button>`;
}

// Page action bar shared by the four views:
//   start: navigation (back / cancel, pager) · end: secondary actions | destructive · primary (rightmost)
function pageToolbar(start, secondary = [], main = []) {
  const sec = secondary.filter(Boolean).join(''), mn = main.filter(Boolean).join('');
  return `
    <div class="page-toolbar">
      <div class="tb-start">${start}</div>
      <div class="tb-end">${sec}${sec && mn ? '<span class="tb-sep" aria-hidden="true"></span>' : ''}${mn}</div>
    </div>`;
}

function chipForCategory(cat) {
  const map = {
    Soldier: 'chip-soldier', Weapon: 'chip-weapon', Equipment: 'chip-equipment',
    Skill: 'chip-skill', Mission: 'chip-mission', Objective: 'chip-mission',
  };
  return `<span class="chip ${map[cat] || ''}">${esc(tv('card_type', cat))}</span>`;
}

// card_types where card_subtype is a real type label (not a theater name)
const SUBTYPE_CATS = new Set(['Soldier','Weapon','Skill','Equipment','Objective','Mission']);

function chipForSubtype(subtype, category) {
  if (category && !SUBTYPE_CATS.has(category)) return '';
  if (subtype === 'Player') return `<span class="chip chip-ps" title="${esc(tv('card_subtype', 'Player'))}">${esc(t('chip.ps'))}</span>`;
  if (subtype === 'NPS') return `<span class="chip chip-nps" title="${esc(tv('card_subtype', 'NPS'))}">${esc(t('chip.nps'))}</span>`;
  return subtype ? `<span class="chip">${esc(tv('card_subtype', subtype))}</span>` : '';
}

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return iso.slice(0, 10);
  return d.toLocaleDateString(I18N.lang, { year: 'numeric', month: 'short', day: 'numeric' });
}

// Canonical (English) card name — use for logic/comparisons, never display
function cardKey(card) {
  return (card.name_en || card.name || '').toLowerCase();
}

// Owner-only marker for cards whose translation is missing / unreviewed
function trMarker(card) {
  const st = card?.translation_status;
  if (!st || st === 'reviewed') return '';
  return `<span class="tr-marker tr-${st}" title="${esc(t('tr.marker.' + st))}">⚑</span>`;
}

// ---------------------------------------------------------------------------
// Card mentions: [[W-001]] / [[Card name]] in notes and comments (backend: app/mentions.py)
// ---------------------------------------------------------------------------
function renderMentions(text, mentions = {}) {
  if (!text) return '';
  return String(text).split(/(\[\[[^\[\]\n]{1,80}\]\])/).map(part => {
    const m = part.match(/^\[\[(.+)\]\]$/);
    if (!m) return esc(part);
    const card = mentions[m[1]];
    return card
      ? `<a href="#/cards/${card.id}" class="card-mention" ${cardImageAttr(card)}>${esc(card.name)}</a>`
      : `<span class="card-mention-missing" title="${esc(t('mention.unknown'))}">${esc(part)}</span>`;
  }).join('');
}

// Typing "[[" in a textarea opens a card picker; choosing inserts [[Card name]]
function attachMentionAutocomplete(ta) {
  if (!ta || ta._mentions) return;
  ta._mentions = true;
  const box = document.createElement('div');
  box.className = 'mention-box';
  box.hidden = true;
  ta.insertAdjacentElement('afterend', box);
  let items = [], active = 0, timer = null, reqId = 0;

  const context = () => {
    const before = ta.value.slice(0, ta.selectionStart);
    const m = before.match(/\[\[([^\[\]\n]{0,40})$/);
    return m ? { query: m[1], start: before.length - m[1].length - 2 } : null;
  };
  const close = () => { box.hidden = true; items = []; };
  const render = () => {
    if (!items.length) { close(); return; }
    box.innerHTML = items.map((c, i) =>
      `<div class="mention-item ${i === active ? 'active' : ''}" data-i="${i}">
        ${cardName(c)} <span class="text-muted">${esc(tv('card_type', c.card_type))} · ${esc(c.number)}</span>
      </div>`).join('');
    box.hidden = false;
  };
  const choose = i => {
    const ctx = context();
    const card = items[i];
    if (!ctx || !card) return;
    const insert = `[[${card.name}]]`;
    const after = ta.value.slice(ta.selectionStart).replace(/^[^\[\]\n]*\]\]/, '');
    ta.value = ta.value.slice(0, ctx.start) + insert + after;
    const pos = ctx.start + insert.length;
    ta.setSelectionRange(pos, pos);
    ta.dispatchEvent(new Event('input'));
    close();
    ta.focus();
  };

  ta.addEventListener('input', () => {
    const ctx = context();
    clearTimeout(timer);
    if (!ctx || ctx.query.trim().length < 2) { close(); return; }
    timer = setTimeout(async () => {
      const my = ++reqId;
      try {
        const r = await API.get('/cards?' + new URLSearchParams({ q: ctx.query, per_page: 8, sort: 'name' }));
        if (my !== reqId) return;
        items = r.items; active = 0; render();
      } catch (_) { close(); }
    }, 200);
  });
  ta.addEventListener('keydown', e => {
    if (box.hidden) return;
    if (e.key === 'ArrowDown') { active = (active + 1) % items.length; render(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { active = (active - 1 + items.length) % items.length; render(); e.preventDefault(); }
    else if (e.key === 'Enter' || e.key === 'Tab') { choose(active); e.preventDefault(); }
    else if (e.key === 'Escape') { close(); }
  });
  box.addEventListener('mousedown', e => {
    const el = e.target.closest('.mention-item');
    if (el) { e.preventDefault(); choose(parseInt(el.dataset.i)); }
  });
  ta.addEventListener('blur', () => setTimeout(close, 150));
}

// ---------------------------------------------------------------------------
// Smart search syntax help (backend: app/smart_filter.py)
// ---------------------------------------------------------------------------
const SMART_KEYS = ['t', 's', 'n', 'm', 'x', 'name', '#', 'rp', 'l', 'h', 'mv', 'cv', 'hth', 'a', 'cx', 'xp', 'b', 'tu'];

function smartHelpButton(id) {
  return `<button type="button" class="btn btn-ghost btn-sm smart-help-btn" data-help="${id}" title="${esc(t('smart.title'))}">?</button>`;
}

function smartHelpBox(id) {
  return `<div class="smart-help" id="${id}" hidden>
    <div class="smart-help-intro">${t('smart.intro_html')}</div>
    <div class="smart-help-keys">${SMART_KEYS.map(k =>
      `<div><code>${esc(k)}</code> ${esc(t('smart.key.' + (k === '#' ? 'number' : k)))}</div>`).join('')}</div>
    <div class="smart-help-examples">${t('smart.examples_html')}</div>
  </div>`;
}

function wireSmartHelp(root) {
  root.querySelectorAll('.smart-help-btn').forEach(btn => btn.addEventListener('click', () => {
    const box = document.getElementById(btn.dataset.help);
    if (box) box.hidden = !box.hidden;
  }));
}

function smartErrorsHtml(errors) {
  if (!errors?.length) return '';
  return `<span class="smart-errors">⚠ ${esc(t('smart.ignored', { tokens: errors.map(e => e.token).join(', ') }))}</span>`;
}

function paginationHtml(page, pages, onNav) {
  if (pages <= 1) return '';
  return `
    <div class="pagination">
      <button class="btn btn-sm btn-ghost" ${page <= 1 ? 'disabled' : ''} data-pg="${page - 1}">◀ ${esc(t('common.prev'))}</button>
      <span class="page-info">${esc(t('common.page_of', { page, pages }))}</span>
      <button class="btn btn-sm btn-ghost" ${page >= pages ? 'disabled' : ''} data-pg="${page + 1}">${esc(t('common.next'))} ▶</button>
    </div>`;
}

// ---------------------------------------------------------------------------
// Lightbox
// ---------------------------------------------------------------------------
function openLightbox(url) {
  const overlay = document.createElement('div');
  overlay.className = 'lightbox-overlay';
  overlay.innerHTML = `
    <img src="${esc(url)}" alt="card full">
    <button class="lightbox-close" title="${esc(t('common.close'))}">✕</button>`;
  overlay.addEventListener('click', e => {
    if (e.target === overlay || e.target.classList.contains('lightbox-close')) overlay.remove();
  });
  document.body.appendChild(overlay);
}

// ---------------------------------------------------------------------------
// VIEW: Cards Browser
// ---------------------------------------------------------------------------
let cardFilters = { q: '', category: '', subtype: '', nation: '', module: '', sort: 'module', order: 'asc', page: 1, per_page: 50 };
// IDs of all cards matching the browser filters/sort, across pages (for prev/next navigation)
let cardNavList = [];
let cardNavReq = 0;  // guards against stale ids_only responses
let allNations = [];
let allModules = [];

// Keys are the canonical/normalized names returned by /api/nations (see utils.py normalize_nation)
const NATION_FLAGS = {
  'Australian':    '🇦🇺',
  'Austria':       '🇦🇹',
  'Canada':        '🇨🇦',
  'China':         '🇨🇳',
  'Commonwealth':  '🇬🇧',
  'Finland':       '🇫🇮',
  'France':        '🇫🇷',
  'German':        '🇩🇪',
  'Greece':        '🇬🇷',
  'Italian':       '🇮🇹',
  'Japan':         '🇯🇵',
  'New Zealand':   '🇳🇿',
  'North Korean':  '🇰🇵',
  'Norway':        '🇳🇴',
  'Poland':        '🇵🇱',
  'Russian':       '🇷🇺',
  'South Korean':  '🇰🇷',
  'UK':            '🇬🇧',
  'US':            '🇺🇸',
  'United Nations':'🇺🇳',
};

// Nations shown first in selectors, in this exact order
const NATION_PINNED = [
  'US', 'German', 'Russian', 'UK', 'Poland', 'Japan',
  'Australian', 'France', 'China', 'North Korean', 'South Korean',
  'Finland', 'Canada', 'Italian',
];

// Display names live in i18n (enum.nation.*), e.g. 'German' → 'Germany' / 'Alemania'
function nationLabel(n) {
  const flag = NATION_FLAGS[n] || '';
  const display = tv('nation', n);
  return flag ? `${flag} ${display}` : display;
}

function sortedNations(nations) {
  const pinnedSet = new Set(NATION_PINNED);
  const pinned = NATION_PINNED.filter(p => nations.includes(p));
  const rest = nations
    .filter(n => !pinnedSet.has(n))
    .sort((a, b) => tv('nation', a).localeCompare(tv('nation', b), I18N.lang));
  return [...pinned, ...rest];
}
let allCategories = ['Soldier','Mission','Objective','Weapon','Equipment','Skill','Service Record'];

register('cards', async function(subId) {
  if (subId) { await showCardDetail(subId); return; }
  showSpinner();
  if (!allModules.length) {
    try { const r = await API.get('/modules'); allModules = r.modules || []; } catch (_) {}
  }
  if (!allNations.length) {
    try { const r = await API.get('/nations'); allNations = r.nations || []; } catch (_) {}
  }
  renderCardsShell();
});

function sortIndicator(col, activeSort, activeOrder) {
  if (col !== activeSort) return '';
  return activeOrder === 'asc' ? ' ▲' : ' ▼';
}

function thSort(label, col, activeSort, activeOrder) {
  const active = col === activeSort ? ' sort-active' : '';
  return `<th class="sort-header${active}" data-sort="${col}">${esc(label)}${sortIndicator(col, activeSort, activeOrder)}</th>`;
}

// Render the Cards page shell (filters + stable containers) — called once on route entry.
// Filter changes only call refreshCardsTable() so the input never loses focus.
function renderCardsShell() {
  const catOptions = ['', ...allCategories].map(c =>
    `<option value="${esc(c)}" ${cardFilters.category === c ? 'selected' : ''}>${esc(c ? tv('card_type', c) : t('cards.all_categories'))}</option>`
  ).join('');
  const nationOptions = ['', ...sortedNations(allNations)].map(n =>
    `<option value="${esc(n)}" ${cardFilters.nation === n ? 'selected' : ''}>${esc(n ? nationLabel(n) : t('cards.all_nations'))}</option>`
  ).join('');
  const moduleOptions = ['', ...allModules].map(m =>
    `<option value="${esc(m)}" ${cardFilters.module === m ? 'selected' : ''}>${esc(m ? tv('module', m) : t('cards.all_modules'))}</option>`
  ).join('');

  setMain(`
    <h1 style="margin-bottom:16px">${esc(t('cards.title'))}</h1>
    <div class="filter-bar" style="flex-wrap:wrap;gap:6px">
      <input type="text" class="search-input" id="q-input" placeholder="${esc(t('cards.search_placeholder'))}" value="${esc(cardFilters.q)}" style="min-width:200px;flex:1">
      ${smartHelpButton('cards-smart-help')}
      <select id="cat-select">${catOptions}</select>
      <select id="nation-select">${nationOptions}</select>
      <select id="module-select">${moduleOptions}</select>
      <button class="btn btn-ghost btn-sm" id="reset-filters">${esc(t('common.reset'))}</button>
    </div>
    ${smartHelpBox('cards-smart-help')}
    <div id="cards-count" style="font-size:12px;color:var(--text-muted);margin-bottom:8px"></div>
    <div id="cards-results"></div>
    <div id="cards-pagination"></div>
  `);

  const main = document.getElementById('app-main');
  let debounce;
  wireSmartHelp(main);

  main.querySelector('#q-input').addEventListener('input', e => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      cardFilters.q = e.target.value;
      cardFilters.page = 1;
      refreshCardsTable();
    }, 300);
  });

  main.querySelector('#cat-select').addEventListener('change', e => {
    cardFilters.category = e.target.value;
    cardFilters.page = 1;
    refreshCardsTable();
  });

  main.querySelector('#nation-select').addEventListener('change', e => {
    cardFilters.nation = e.target.value;
    cardFilters.page = 1;
    refreshCardsTable();
  });

  main.querySelector('#module-select').addEventListener('change', e => {
    cardFilters.module = e.target.value;
    cardFilters.page = 1;
    refreshCardsTable();
  });

  main.querySelector('#reset-filters').addEventListener('click', () => {
    cardFilters = { q: '', category: '', subtype: '', nation: '', module: '', sort: 'module', order: 'asc', page: 1, per_page: 50 };
    // Reset dropdowns to match cleared filters
    main.querySelector('#q-input').value = '';
    main.querySelector('#cat-select').value = '';
    main.querySelector('#nation-select').value = '';
    main.querySelector('#module-select').value = '';
    refreshCardsTable();
  });

  refreshCardsTable();
}

// Update only the results table and pagination — does NOT touch the filter controls.
async function refreshCardsTable() {
  const params = new URLSearchParams();
  if (cardFilters.q) params.set('q', cardFilters.q);
  if (cardFilters.category) params.set('category', cardFilters.category);
  if (cardFilters.nation) params.set('nation', cardFilters.nation);
  if (cardFilters.module) params.set('module', cardFilters.module);
  params.set('page', cardFilters.page);
  params.set('per_page', cardFilters.per_page);
  params.set('sort', cardFilters.sort);
  params.set('order', cardFilters.order);

  const resultsDiv = document.getElementById('cards-results');
  const countDiv = document.getElementById('cards-count');
  const paginationDiv = document.getElementById('cards-pagination');
  if (!resultsDiv) return;

  let data;
  try {
    data = await API.get('/cards?' + params.toString());
  } catch (e) {
    resultsDiv.innerHTML = `<div class="alert alert-error">${esc(e.error || t('cards.load_failed'))}</div>`;
    return;
  }

  const { items, total, page, pages } = data;
  const s = cardFilters.sort, o = cardFilters.order;

  if (countDiv) countDiv.innerHTML = esc(t('cards.showing', {
    from: fmtNumber(total === 0 ? 0 : (page-1)*cardFilters.per_page+1),
    to: fmtNumber(Math.min(page*cardFilters.per_page,total)),
    total: fmtNumber(total),
  })) + ' ' + smartErrorsHtml(data.filter_errors);

  const rows = items.map(c => `
    <tr class="clickable" data-id="${c.id}">
      <td><span class="text-muted" style="font-size:11px">${esc(c.number)}</span></td>
      <td><span ${cardImageAttr(c)}>${esc(c.name)}</span>${trMarker(c)}</td>
      <td>${chipForCategory(c.card_type)}</td>
      <td>${SUBTYPE_CATS.has(c.card_type) ? esc(tv('card_subtype', c.card_subtype || '')) : ''}</td>
      <td>${esc(c.nation ? tv('nation', c.nation) : '—')}</td>
      <td>${esc(tv('module', c.module))}</td>
      <td style="text-align:right">${c.resource_cost != null ? c.resource_cost : ''}</td>
    </tr>`).join('');

  resultsDiv.innerHTML = `
    <div class="table-scroll">
    <table class="data-table">
      <thead>
        <tr>
          ${thSort('#','number',s,o)}
          ${thSort(t('col.name'),'name',s,o)}
          <th>${esc(t('col.type'))}</th><th>${esc(t('col.subtype'))}</th>
          ${thSort(t('col.nation'),'nation',s,o)}
          ${thSort(t('col.module'),'module',s,o)}
          ${thSort(t('stat.rp'),'resource_cost',s,o)}
        </tr>
      </thead>
      <tbody>${rows || `<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">${esc(t('cards.none'))}</td></tr>`}</tbody>
    </table>
    </div>`;

  if (paginationDiv) paginationDiv.innerHTML = paginationHtml(page, pages);

  // Sortable column headers
  resultsDiv.querySelectorAll('th.sort-header[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      if (cardFilters.sort === col) {
        cardFilters.order = cardFilters.order === 'asc' ? 'desc' : 'asc';
      } else {
        cardFilters.sort = col;
        cardFilters.order = 'asc';
      }
      cardFilters.page = 1;
      refreshCardsTable();
    });
  });

  // Persist full card ID order (all pages) for prev/next navigation in card detail
  cardNavList = items.map(c => c.id);
  const idParams = new URLSearchParams(params);
  idParams.delete('page'); idParams.delete('per_page'); idParams.set('ids_only', 'true');
  const navReq = ++cardNavReq;
  API.get('/cards?' + idParams.toString())
    .then(d => { if (navReq === cardNavReq) cardNavList = d.ids; })
    .catch(() => {});

  resultsDiv.querySelectorAll('tr[data-id]').forEach(row => {
    row.addEventListener('click', () => navigate('cards/' + row.dataset.id));
  });

  if (paginationDiv) paginationDiv.querySelectorAll('[data-pg]').forEach(btn => {
    btn.addEventListener('click', () => {
      cardFilters.page = parseInt(btn.dataset.pg);
      refreshCardsTable();
    });
  });
}

// ---------------------------------------------------------------------------
// VIEW: Card Detail
// ---------------------------------------------------------------------------
async function showCardDetail(idOrNumber) {
  showSpinner();
  let card;
  try {
    const data = await API.get('/cards/' + idOrNumber);
    card = data.card;
  } catch (e) {
    showError(e.error || t('cards.not_found'));
    return;
  }
  setPageTitle(card.name, t('nav.cards'));

  // Type → CSS theme class (sets --cd-accent / --cd-accent-bg)
  const TYPE_CLS = {
    Soldier: 'cd-t-soldier', Weapon: 'cd-t-weapon', Equipment: 'cd-t-equipment',
    Skill: 'cd-t-skill', 'Service Record': 'cd-t-sr',
    Mission: 'cd-t-mission', Objective: 'cd-t-objective',
    Situation: 'cd-t-situation', Hostile: 'cd-t-hostile',
  };
  const typeCls = TYPE_CLS[card.card_type] || '';

  // --- Prev / Next ---
  const navIdx = cardNavList.indexOf(card.id);
  const prevId = navIdx > 0 ? cardNavList[navIdx - 1] : null;
  const nextId = navIdx >= 0 && navIdx < cardNavList.length - 1 ? cardNavList[navIdx + 1] : null;
  // Keep the browser on the page containing this card when returning to the list
  if (navIdx >= 0) cardFilters.page = Math.floor(navIdx / cardFilters.per_page) + 1;
  const navPos = navIdx >= 0 ? `<span class="cd-nav-pos">${navIdx + 1} / ${cardNavList.length}</span>` : '';
  const prevBtn = prevId
    ? `<a href="#/cards/${prevId}" class="btn btn-ghost btn-sm">← ${esc(t('common.prev'))}</a>`
    : `<span class="btn btn-ghost btn-sm" style="opacity:.35;pointer-events:none">← ${esc(t('common.prev'))}</span>`;
  const nextBtn = nextId
    ? `<a href="#/cards/${nextId}" class="btn btn-ghost btn-sm">${esc(t('common.next'))} →</a>`
    : `<span class="btn btn-ghost btn-sm" style="opacity:.35;pointer-events:none">${esc(t('common.next'))} →</span>`;

  // --- Add to build ---
  const addBtn = builderState.missionCard
    ? `<button class="btn btn-primary btn-sm" id="add-to-build">+ ${esc(t('cd.add_to_build'))}</button>` : '';
  const editTrBtn = currentUser?.is_admin && I18N.lang !== 'en'
    ? `<a href="#/translations/${encodeURIComponent(card.number)}" class="btn btn-ghost btn-sm">${esc(t('cd.edit_translation'))}</a>` : '';

  // --- Eyebrow subtype ---
  const subtypeLabel = (() => {
    if (card.card_type === 'Mission')    return tv('card_subtype', card.mission_type || card.card_subtype || '');
    if (card.card_type === 'Objective') {
      return [card.objective_family, card.objective_mechanic].filter(Boolean).map(v => tv('card_subtype', v)).join(' · ');
    }
    return SUBTYPE_CATS.has(card.card_type) ? tv('card_subtype', card.card_subtype || '') : '';
  })();

  // --- Image ---
  const hasImage = !!card.image_url;
  const imageHtml = hasImage
    ? `<img src="${esc(card.image_url)}" alt="${esc(card.name)}" class="cd-image">`
    : `<div class="cd-image-placeholder"></div>`;

  const assocs = card.associations || [];

  // ---------------------------------------------------------------------------
  // Stat-section helpers
  // ---------------------------------------------------------------------------
  function vital(label, value) {
    if (value == null || value === '') return '';
    return `<div class="cd-vital"><div class="cd-vital-val">${esc(String(value))}</div><div class="cd-vital-lbl">${esc(label)}</div></div>`;
  }

  function cdTable(tbl, title) {
    if (!tbl) return '';
    const { headers, rows } = tbl;
    return `${title ? sectionLabel(title) : ''}
    <div class="cd-table-wrap">
      <table class="cd-table">
        <thead><tr>${headers.map(h => `<th>${esc(tv('table_header', h))}</th>`).join('')}</tr></thead>
        <tbody>${rows.map(row =>
          `<tr>${row.map(v => `<td>${esc(String(v))}</td>`).join('')}</tr>`
        ).join('')}</tbody>
      </table>
    </div>`;
  }

  function spawnTable(rows) {
    if (!rows?.length) return '';
    return `${sectionLabel(t('cd.hostile_spawn'))}
    <div class="cd-table-wrap">
      <table class="cd-table">
        <thead><tr><th>${esc(t('cd.team_rp'))}</th><th>${esc(t('cd.hostiles'))}</th></tr></thead>
        <tbody>${rows.map(r => {
          const label = r.range.endsWith('-') ? '≤ ' + r.range.slice(0, -1) : r.range;
          return `<tr><td>${label}</td><td>${r.count}</td></tr>`;
        }).join('')}</tbody>
      </table>
    </div>`;
  }

  function sectionLabel(text) {
    return `<div class="cd-section-label">${esc(text)}</div>`;
  }

  // ---------------------------------------------------------------------------
  // Type-specific stat blocks
  // ---------------------------------------------------------------------------
  let statsHtml = '';

  if (card.card_type === 'Soldier') {
    const hth = card.hth != null ? (card.hth >= 0 ? '+' : '') + card.hth : null;
    const HARDY_STYLE = {
      Cold: 'background:#18243e;color:#60a5fa;border:1px solid #1e3a6e',
      Hot:  'background:#2e1a08;color:#fb923c;border:1px solid #5e2e10',
    };
    statsHtml = `
      ${sectionLabel(t('cd.vitals'))}
      <div class="cd-vitals">
        ${vital(t('stat.hp'), card.health)}
        ${vital(t('stat.move'), card.movement)}
        ${vital(t('stat.cover'), card.cover)}
        ${vital(t('stat.loadout'), card.loadout)}
        ${hth != null ? vital(t('stat.hth'), hth) : ''}
        ${vital(t('stat.actions'), card.actions)}
        ${vital(t('stat.rp_cost'), card.resource_cost)}
      </div>
      ${(card.cx || card.xp || card.hardy_markers?.length) ? `<div class="cd-xp-row">
        ${card.cx ? `<span class="cd-badge cd-badge-cx" title="${esc(t('cd.cx_tip'))}">⚔ ${esc(t('stat.cx'))} ${card.cx}</span>` : ''}
        ${card.xp ? `<span class="cd-badge cd-badge-xp" title="${esc(t('cd.xp_tip'))}">★ ${esc(t('stat.xp'))} ${card.xp}</span>` : ''}
        ${(card.hardy_markers || []).map(h => {
          const lbl = h.modifier === '+' ? `+${h.count}` : `${h.count}×`;
          const style = HARDY_STYLE[h.type] || 'background:var(--surface2);color:var(--text-muted);border:1px solid var(--border)';
          const env = tv('hardy', h.type);
          return `<span class="cd-badge" style="${style}" title="${esc(t('cd.hardy_tip', { env }))}">${lbl} ${esc(t('cd.hardy', { env }))}</span>`;
        }).join('')}
      </div>` : ''}
      ${card.health_actions_table ? sectionLabel(t('cd.health_actions')) + cdTable(card.health_actions_table) : ''}
    `;

  } else if (card.card_type === 'Weapon') {
    statsHtml = `
      ${sectionLabel(t('cd.specifications'))}
      <div class="cd-vitals">
        ${vital(t('stat.rp_cost'), card.resource_cost)}
        ${card.loadout != null ? vital(t('stat.loadout'), card.loadout) : ''}
      </div>
      ${cdTable(card.weapon_range_table, t('cd.range'))}
      ${cdTable(card.weapon_mode_table, t('cd.fire_mode'))}
    `;

  } else if (card.card_type === 'Mission') {
    const mAttrs = [
      card.resources != null          ? { k: t('stat.rp_budget'),    v: card.resources } : null,
      card.time != null               ? { k: t('stat.turns'),        v: card.time } : null,
      card.objective_position != null ? { k: t('stat.obj_location'), v: card.objective_position } : null,
      card.loadout_modifier != null   ? { k: t('stat.loadout_mod'),  v: (card.loadout_modifier >= 0 ? '+' : '') + card.loadout_modifier } : null,
      card.action_cost_hth != null    ? { k: t('stat.hth_cost'),     v: card.action_cost_hth } : null,
    ].filter(Boolean);
    statsHtml = `
      ${sectionLabel(t('cd.mission_brief'))}
      <div class="cd-vitals">${mAttrs.map(a => vital(a.k, a.v)).join('')}</div>
    `;

  } else if (card.card_type === 'Objective') {
    const oAttrs = [
      card.entrance_cost != null   ? { k: t('stat.entry_cost'), v: card.entrance_cost } : null,
      card.action_cost_hth != null ? { k: t('stat.hth_cost'),   v: card.action_cost_hth } : null,
    ].filter(Boolean);
    statsHtml = `
      ${oAttrs.length ? `${sectionLabel(t('cd.costs'))}<div class="cd-vitals">${oAttrs.map(a => vital(a.k, a.v)).join('')}</div>` : ''}
      ${spawnTable(card.hostile_spawn_table)}
    `;

  } else {
    // Equipment, Skill, Service Record, Situation, Hostile, …
    const attrs = [
      card.resource_cost != null  ? { k: t('stat.rp_cost'),  v: card.resource_cost } : null,
      card.loadout != null        ? { k: t('stat.loadout'),  v: card.loadout } : null,
      card.health != null         ? { k: t('stat.hp'),       v: card.health } : null,
      card.movement != null       ? { k: t('stat.move'),     v: card.movement } : null,
      card.cover != null          ? { k: t('stat.cover'),    v: card.cover } : null,
      card.hth != null            ? { k: t('stat.hth'),      v: (card.hth >= 0 ? '+' : '') + card.hth } : null,
      card.actions != null        ? { k: t('stat.actions'),  v: card.actions } : null,
      card.resources != null      ? { k: t('stat.budget'),   v: card.resources + ' ' + t('stat.rp') } : null,
      card.time != null           ? { k: t('stat.turns'),    v: card.time } : null,
      card.noise != null          ? { k: t('stat.noise'),    v: card.noise } : null,
      card.support_cost != null   ? { k: t('stat.support'),  v: card.support_cost } : null,
      card.covert_cost != null    ? { k: t('stat.covert'),   v: card.covert_cost } : null,
      card.gain != null           ? { k: t('stat.gain'),     v: card.gain } : null,
      card.loss != null           ? { k: t('stat.loss'),     v: card.loss } : null,
      card.xp_value != null       ? { k: t('stat.xp_value'), v: card.xp_value } : null,
      card.hostile_count          ? { k: t('stat.count'),    v: card.hostile_count } : null,
    ].filter(Boolean);
    if (attrs.length) {
      statsHtml += `${sectionLabel(t('cd.stats'))}<div class="cd-vitals">${attrs.map(a => vital(a.k, a.v)).join('')}</div>`;
    }
    statsHtml += spawnTable(card.hostile_spawn_table);
    statsHtml += cdTable(card.weapon_range_table, t('cd.range'));
    statsHtml += cdTable(card.weapon_mode_table, t('cd.fire_mode'));
    if (card.health_actions_table) statsHtml += sectionLabel(t('cd.health_actions')) + cdTable(card.health_actions_table);
  }

  setMain(`
    <div class="cd-nav">
      <a href="#/cards" class="btn btn-ghost btn-sm">↩ ${esc(t('nav.cards'))}</a>
      ${addBtn}
      ${editTrBtn}
      <span style="flex:1"></span>
      ${navPos}
      ${prevBtn}
      ${nextBtn}
    </div>

    <div class="cd-wrap ${typeCls}">
      <div class="cd-header">
        <div class="cd-eyebrow">
          ${chipForCategory(card.card_type)}
          ${subtypeLabel ? `<span class="cd-eyebrow-sub">${esc(subtypeLabel)}</span>` : ''}
          ${card.nation ? `<span class="cd-eyebrow-sep">·</span><span class="cd-eyebrow-nation">${esc(tv('nation', card.nation))}</span>` : ''}
          <span class="cd-eyebrow-sep">·</span>
          <span class="cd-eyebrow-module">${esc(tv('module', card.module))}</span>
          <span class="cd-eyebrow-num">${esc(card.number)}</span>
        </div>
        <div class="cd-name-row">
          <h1 class="cd-name" ${card.name_en && card.name_en !== card.name ? `title="${esc(t('cd.original') + ': ' + card.name_en)}"` : ''}>${esc(card.name)}</h1>
          ${trMarker(card)}
          ${card.theater ? `<span class="cd-theater-tag">📍 ${esc(tv('theater', card.theater))}</span>` : ''}
        </div>
      </div>

      <div class="cd-body">
        <div class="cd-main">
          ${statsHtml ? `<div class="cd-section">${statsHtml}</div>` : ''}

          ${card.notes ? `<div class="cd-section">
            ${sectionLabel(t('cd.notes'))}
            <div class="cd-notes">${esc(card.notes)}</div>
            ${card.notes_en && card.notes_en !== card.notes ? `<details class="cd-original">
              <summary>${esc(t('cd.show_original'))}</summary>
              <div class="cd-notes">${esc(card.notes_en)}</div>
            </details>` : ''}
          </div>` : ''}

          ${assocs.length ? `<div class="cd-section">
            ${sectionLabel(t('cd.default_gear'))}
            <div class="cd-table-wrap">
              <table class="cd-table cd-assoc-table">
                <thead><tr><th>#</th><th>${esc(t('col.name'))}</th><th>${esc(t('col.type'))}</th><th>${esc(t('col.qty'))}</th></tr></thead>
                <tbody>
                  ${assocs.map(a => `
                    <tr class="clickable" data-id="${a.card.id}">
                      <td class="cd-assoc-num">${esc(a.card.number)}</td>
                      <td><span ${cardImageAttr(a.card)}>${esc(a.card.name)}</span></td>
                      <td>${chipForCategory(a.card.card_type)}</td>
                      <td>${a.quantity > 1 ? '×' + a.quantity : '—'}</td>
                    </tr>`).join('')}
                </tbody>
              </table>
            </div>
          </div>` : ''}
        </div>

        <div class="cd-aside">
          <div class="cd-image-wrap ${hasImage ? 'cd-has-image' : ''}">
            ${imageHtml}
          </div>
        </div>
      </div>
    </div>
  `);

  const imgEl = document.querySelector('.cd-image');
  if (imgEl) imgEl.addEventListener('click', () => openLightbox(card.image_url));

  document.querySelectorAll('.cd-assoc-table tr[data-id]').forEach(row =>
    row.addEventListener('click', () => navigate('cards/' + row.dataset.id)));

  const addBtnEl = document.getElementById('add-to-build');
  if (addBtnEl) {
    addBtnEl.addEventListener('click', () => {
      if (builderState.pickerMode === 'soldier') {
        addSoldierToBuilder(card);
        navigate('builder');
      } else if (builderState.pickerMode === 'gear') {
        addGearToBuilder(card, builderState.pickerTarget);
        navigate('builder');
      }
    });
  }
}

// ---------------------------------------------------------------------------
// VIEW: Squads List
// ---------------------------------------------------------------------------
// One list: everyone's published squads plus the user's own (drafts included).
// 'My Squads' narrows it to the user's own squads.
let squadFilters = { q: '', mine: false, liked: false, sort: 'updated_at', order: 'desc', page: 1, myModules: false };
// IDs of squads currently visible in the browser list (for prev/next navigation)
let squadNavList = [];

register('squads', async function(subId) {
  if (subId === 'new') { renderBuilder(null); return; }
  if (subId) { await showSquadDetail(parseInt(subId)); return; }
  showSpinner();
  renderSquadsShell();
});

function renderSquadsShell() {
  const newBtn = currentUser
    ? `<span style="display:flex;gap:6px">
        <button class="btn btn-ghost" id="import-squad-btn">${esc(t('io.import'))}</button>
        <button class="btn btn-primary" id="new-squad-btn">+ ${esc(t('squads.new'))}</button>
      </span>` : '';

  setMain(`
    <div class="flex justify-between items-center" style="margin-bottom:12px">
      <h1>${esc(t('squads.title'))}</h1>
      ${newBtn}
    </div>
    <div id="squads-list"></div>
  `);

  const main = document.getElementById('app-main');
  main.querySelector('#new-squad-btn')?.addEventListener('click', () => navigate('builder'));
  main.querySelector('#import-squad-btn')?.addEventListener('click', openImportDialog);
  renderSquadList(document.getElementById('squads-list'));
}

function _squadSortTh(label, col, f) {
  const active = f.sort === col;
  const arrow = active ? (f.order === 'asc' ? ' ▲' : ' ▼') : '';
  return `<th class="sort-header${active ? ' sort-active' : ''}" data-sort="${col}">${esc(label)}${arrow}</th>`;
}

async function renderSquadList(containerEl) {
  if (!containerEl) return;
  const f = squadFilters;
  const mine = f.mine && currentUser;
  const params = new URLSearchParams();
  if (mine) params.set('user_id', currentUser.id);
  if (f.liked && currentUser) params.set('liked', 'true');
  params.set('sort', f.sort);
  params.set('order', f.order);
  params.set('page', f.page);
  if (f.q) params.set('q', f.q);
  if (f.myModules && currentUser) params.set('my_modules', 'true');

  let data;
  try { data = await API.get('/squads?' + params.toString()); }
  catch (e) { containerEl.innerHTML = `<div class="alert alert-error">${esc(e.error||t('common.failed'))}</div>`; return; }

  const { items, total, page, pages } = data;
  const userBtns = currentUser ? `
    <button class="quick-filter ${f.liked ? 'active' : ''}" id="liked-filter">♥ ${esc(t('squads.liked_by_me'))}</button>
    <button class="quick-filter ${f.mine ? 'active-purple' : ''}" id="mine-filter">${esc(t('squads.tab_my'))}</button>
    <button class="quick-filter ${f.myModules ? 'active-blue' : ''}" id="my-modules-filter">${esc(t('squads.my_modules'))}</button>` : '';

  const rows = items.map(s => {
    const own = currentUser && s.owner && s.owner.id === currentUser.id;
    const draft = s.status === 'draft'
      ? ` <span class="badge badge-draft">${esc(tv('squad_status', s.status))}</span>` : '';
    return `
    <tr class="clickable" data-id="${s.id}">
      <td class="squad-edit-cell">${own ? `<button class="squad-edit-btn" data-edit="${s.id}" title="${esc(t('common.edit'))}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg></button>` : ''}</td>
      <td class="squad-name-cell"><strong class="ellipsis" title="${esc(s.name)}">${esc(s.name)}</strong>${draft}</td>
      <td>${esc(nationLabel(s.nation))}</td>
      <td>${s.mission ? `${cardName(s.mission)}${customMissionChip(s.mission)} <span class="text-muted">· ${s.mission.resources} ${esc(t('stat.rp'))}</span>` : '—'}</td>
      <td>${s.rp_total}</td>
      <td>${s.likes_count} ♥</td>
      <td>${own ? `<strong>${esc(s.owner.username)}</strong>` : esc(s.owner ? s.owner.username : '—')}</td>
      <td class="text-muted">${fmtDate(s.updated_at)}</td>
    </tr>`;
  }).join('');

  const _active = document.activeElement;
  const hadFocus = _active?.id === 'squads-q';
  const savedSel = hadFocus ? [_active.selectionStart, _active.selectionEnd] : null;
  containerEl.innerHTML = `
    <div class="filter-bar" style="margin-bottom:8px">
      <input type="text" class="search-input" id="squads-q" placeholder="${esc(t('squads.search_placeholder'))}" value="${esc(f.q)}" style="flex:1;min-width:160px">
      ${userBtns}
    </div>
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">${esc(tn('squads.count', total))}</div>
    <table class="data-table squads-table">
      <thead><tr>
        <th class="squad-edit-cell"></th>
        ${_squadSortTh(t('col.name'), 'name', f)}
        ${_squadSortTh(t('col.nation'), 'nation', f)}
        ${_squadSortTh(t('col.mission'), 'mission_name', f)}
        ${_squadSortTh(t('col.team_rp'), 'rp_total', f)}
        ${_squadSortTh(t('col.likes'), 'likes_count', f)}
        <th>${esc(t('col.owner'))}</th>
        ${_squadSortTh(t('col.updated'), 'updated_at', f)}
      </tr></thead>
      <tbody>${rows||`<tr><td colspan="8" style="text-align:center;color:var(--text-muted)">${esc(t(mine ? 'squads.none_mine' : 'squads.none_published'))}</td></tr>`}</tbody>
    </table>
    ${paginationHtml(page, pages)}`;

  const rerender = () => { f.page = 1; renderSquadList(containerEl); };
  const qInput = containerEl.querySelector('#squads-q');
  if (qInput) {
    if (hadFocus) { qInput.focus(); if (savedSel) qInput.setSelectionRange(savedSel[0], savedSel[1]); }
    qInput.addEventListener('input', e => {
      clearTimeout(qInput._t);
      qInput._t = setTimeout(() => { f.q = e.target.value; rerender(); }, 300);
    });
  }
  containerEl.querySelector('#mine-filter')?.addEventListener('click', () => { f.mine = !f.mine; rerender(); });
  containerEl.querySelector('#liked-filter')?.addEventListener('click', () => { f.liked = !f.liked; rerender(); });
  containerEl.querySelector('#my-modules-filter')?.addEventListener('click', () => { f.myModules = !f.myModules; rerender(); });
  containerEl.querySelectorAll('th.sort-header[data-sort]').forEach(th =>
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      if (f.sort === col) f.order = f.order === 'asc' ? 'desc' : 'asc';
      else { f.sort = col; f.order = ['name', 'nation', 'mission_name'].includes(col) ? 'asc' : 'desc'; }
      rerender();
    })
  );
  squadNavList = items.map(s => s.id);
  containerEl.querySelectorAll('tr[data-id]').forEach(row =>
    row.addEventListener('click', () => navigate('squads/' + row.dataset.id)));
  containerEl.querySelectorAll('[data-edit]').forEach(btn =>
    btn.addEventListener('click', e => {
      e.stopPropagation(); builderFromSquadList = true; navigate('builder/' + btn.dataset.edit);
    }));
  containerEl.querySelectorAll('[data-pg]').forEach(btn =>
    btn.addEventListener('click', () => { f.page = parseInt(btn.dataset.pg); renderSquadList(containerEl); }));
}

// ---------------------------------------------------------------------------
// Squad metrics (spec 12; G0 estimate computed by app/metrics.py)
// ---------------------------------------------------------------------------
const METRIC_KEYS = ['ranged_fire', 'close_assault', 'anti_armour', 'demolition', 'supplies',
                     'mobility', 'survivability', 'resilience', 'experience'];

function metricsRadarSvg(metrics) {
  const size = 280, c = size / 2, R = 88, n = METRIC_KEYS.length;
  const pt = (i, r) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
    return [c + r * Math.cos(a), c + r * Math.sin(a)];
  };
  const rings = [0.25, 0.5, 0.75, 1].map(f =>
    `<polygon class="mr-ring" points="${METRIC_KEYS.map((_, i) => pt(i, R * f).join(',')).join(' ')}"/>`).join('');
  const spokes = METRIC_KEYS.map((_, i) => { const [x, y] = pt(i, R); return `<line class="mr-spoke" x1="${c}" y1="${c}" x2="${x}" y2="${y}"/>`; }).join('');
  const shape = METRIC_KEYS.map((k, i) => pt(i, R * Math.max(0.02, metrics[k].score ?? 0)).join(',')).join(' ');
  const dots = METRIC_KEYS.map((k, i) => { const [x, y] = pt(i, R * Math.max(0.02, metrics[k].score ?? 0)); return `<circle class="mr-dot" cx="${x}" cy="${y}" r="2.5"/>`; }).join('');
  const labels = METRIC_KEYS.map((k, i) => {
    const [x, y] = pt(i, R + 16);
    const anchor = x < c - 6 ? 'end' : x > c + 6 ? 'start' : 'middle';
    return `<text class="mr-label" x="${x}" y="${y + 3}" text-anchor="${anchor}">${esc(t('metrics.' + k))}</text>`;
  }).join('');
  return `<svg class="metrics-radar" viewBox="0 0 ${size} ${size}" role="img" aria-label="${esc(t('metrics.title'))}">
    ${rings}${spokes}<polygon class="mr-shape" points="${shape}"/>${dots}${labels}</svg>`;
}

function metricsSectionHtml(m) {
  if (!m || !m.metrics) return '';
  const rows = METRIC_KEYS.map(k => {
    const v = m.metrics[k];
    const pct = v.score == null ? null : Math.round(v.score * 100);
    const raw = Number.isInteger(v.raw) ? v.raw : v.raw.toFixed(v.raw < 10 ? 2 : 1);
    return `<li class="metric-row" title="${esc(t('metrics.' + k + '_desc'))}\n${esc(v.detail || '')}">
      <span class="metric-name">${esc(t('metrics.' + k))}</span>
      <span class="metric-bar"><span class="metric-fill" style="width:${pct == null ? 0 : pct}%"></span></span>
      <span class="metric-val">${pct == null ? '–' : pct}</span>
      <span class="metric-raw">${esc(raw)}</span>
    </li>`;
  }).join('');
  const n = m.sample ? m.sample.n : 0;
  return `<div class="squad-metrics">
    <h2 style="margin-bottom:8px">${esc(t('metrics.title'))} <span class="metrics-badge">${esc(t('metrics.estimate'))}</span></h2>
    <div class="metrics-body">
      ${metricsRadarSvg(m.metrics)}
      <div class="metrics-list-wrap">
        <div class="metric-head"><span></span><span></span><span class="metric-val">${esc(t('metrics.col_score'))}</span><span class="metric-raw">${esc(t('metrics.col_raw'))}</span></div>
        <ul class="metrics-list">${rows}</ul>
      </div>
    </div>
    <p class="metrics-note text-muted">${esc(t('metrics.note', { n }))}</p>
  </div>`;
}

// ---------------------------------------------------------------------------
// VIEW: Squad Detail
// ---------------------------------------------------------------------------
async function showSquadDetail(squadId) {
  showSpinner();
  let squad, comments, commentMentions = {};
  try {
    const r = await API.get('/squads/' + squadId);
    squad = r.squad;
    const cr = await API.get('/squads/' + squadId + '/comments');
    comments = cr.items;
    commentMentions = cr.mentions || {};
  } catch (e) {
    showError(e.error || t('squad.not_found'));
    return;
  }

  setPageTitle(squad.name, t('nav.squads'));
  const isOwner = currentUser && currentUser.id === squad.owner.id;
  const isDraft = squad.status === 'draft';
  // One primary per view: Publish on an own draft, otherwise Edit on an own squad
  const editBtn = isOwner ? actionBtn({ id: 'edit-squad-btn', icon: 'edit', label: t('common.edit'), variant: isDraft ? 'ghost' : 'primary' }) : '';
  const deleteBtn = isOwner ? actionBtn({ id: 'delete-squad-btn', icon: 'trash', label: t('common.delete'), variant: 'danger' }) : '';
  const publishBtn = isOwner && isDraft ? actionBtn({ id: 'publish-btn', icon: 'publish', label: t('squad.publish'), variant: 'primary' }) : '';
  const draftBadge = isDraft ? `<span class="badge-draft">${esc(t('squad.draft_badge'))}</span>` : '';
  const copyBtn = currentUser
    ? actionBtn({ id: 'copy-squad-btn', icon: 'copy', label: t('squad.copy'), title: t('squad.copy_tip') }) : '';
  const basedOn = squad.parent
    ? `<div class="squad-based-on">${t('squad.based_on_html', {
        link: `<a href="#/squads/${squad.parent.id}">${esc(squad.parent.name)}</a>`,
        user: esc(squad.parent.owner.username) })}</div>` : '';
  const copiesInfo = squad.copies_count
    ? ` · <span class="text-muted">${esc(tn('squad.copies', squad.copies_count))}</span>` : '';
  // Export: one button opening a menu — each format with what it is for
  const exportItem = (fmt, label, tip) => `
    <button class="export-item" role="menuitem" data-export="${fmt}">
      <span class="export-item-label">${esc(label)}</span>
      <span class="export-item-tip">${esc(tip)}</span>
    </button>`;
  const exportBtns = `
    <div class="export-menu">
      <button type="button" class="btn btn-ghost" id="export-toggle" title="${esc(t('io.export'))}" aria-label="${esc(t('io.export'))}" aria-haspopup="menu" aria-expanded="false">${icon('download')}<span class="btn-label">${esc(t('io.export'))}</span><span class="btn-caret">${icon('down')}</span></button>
      <div class="export-menu-list" id="export-list" role="menu" hidden>
        ${exportItem('text', t('io.text'), t('io.text_tip'))}
        ${exportItem('csv', 'CSV', t('io.csv_tip'))}
        ${exportItem('tts', 'Tabletop Simulator', t('io.tts_tip'))}
      </div>
    </div>`;

  const likedClass = squad.liked_by_me ? 'liked' : '';
  const likeTitle = currentUser ? t('col.likes') : t('squad.login_to_like');
  const likeBtn = `
    <button type="button" class="btn btn-ghost like-btn ${likedClass}" id="like-btn" aria-pressed="${!!squad.liked_by_me}"
      title="${esc(likeTitle)}" aria-label="${esc(likeTitle)}" ${!currentUser ? 'disabled' : ''}>${icon('heart')}<span id="likes-count">${squad.likes_count}</span></button>`;

  // Minimal module set for soldiers + gear, any equivalent printing (app/required_modules.py)
  const requiredModules = (squad.required_modules || []).length ? `
    <span class="required-modules" title="${esc(t('squad.required_modules'))}">
      ${squad.required_modules.map(m => `<span class="chip">${esc(tv('module', m))}</span>`).join('')}
    </span>` : '';

  const soldiersHtml = squad.soldiers.map(ss => {
    const c = ss.card;
    const isPS = c.card_subtype === 'Player';
    const badgeHtml = chipForSubtype(c.card_subtype, c.card_type);

    const loadoutBar = (() => {
      if (!isPS || ss.effective_loadout == null) return '';
      const lm = ss.effective_loadout - (c.loadout || 0);
      const color = lm !== 0 ? ' color:var(--danger);' : '';
      const tip = lm !== 0
        ? `data-tooltip="${esc(t('squad.loadout_tip', { base: c.loadout, mod: (lm >= 0 ? '+' : '') + lm }))}"`
        : '';
      return `<div class="text-muted" style="font-size:12px;margin-bottom:6px;${color}" ${tip}>${esc(t('stat.loadout'))}: ${ss.gear_loadout_used}/${ss.effective_loadout}</div>`;
    })();

    const gearHtml = (() => {
      const _GEAR_TYPE_ORDER = { 'Weapon': 0, 'Equipment': 1, 'Skill': 2, 'Service Record': 3 };
      const _gearSort = (a, b) => {
        const ta = _GEAR_TYPE_ORDER[a.card.card_type] ?? 99;
        const tb = _GEAR_TYPE_ORDER[b.card.card_type] ?? 99;
        if (ta !== tb) return ta - tb;
        return a.card.name.localeCompare(b.card.name, I18N.lang);
      };
      const defaultGear = (ss.default_gear || []).slice().sort(_gearSort);
      const defaultGearNames = new Set(defaultGear.map(g => cardKey(g.card)));
      const sortedGear = ss.gear.slice().sort(_gearSort).filter(g => !defaultGearNames.has(cardKey(g.card)));
      const _gearRow = (g, showCost) => `
        <tr>
          <td><span ${cardImageAttr(g.card)}>${esc(g.card.name)}</span></td>
          <td class="text-muted">${esc(tv('card_type', g.card.card_type))}</td>
          ${showCost ? `<td class="text-muted">${g.card.resource_cost != null ? g.card.resource_cost + ' ' + esc(t('stat.rp')) : ''}</td>
          <td class="text-muted">${g.loadout_weight != null ? esc(t('stat.loadout_abbr')) + g.loadout_weight : ''}</td>
          ${g.quantity > 1 ? `<td>×${g.quantity}</td>` : '<td></td>'}` : ''}
        </tr>`;
      let out = '';
      if (sortedGear.length) {
        out += `<div class="default-gear-section">
          <div class="default-gear-label">${esc(t('squad.gear'))}</div>
          <table class="gear-table">${sortedGear.map(g => _gearRow(g, isPS)).join('')}</table>
        </div>`;
      }
      if (defaultGear.length) {
        out += `<div class="default-gear-section">
          <div class="default-gear-label">${esc(t('squad.included'))}</div>
          <table class="gear-table">${defaultGear.map(g => _gearRow(g, false)).join('')}</table>
        </div>`;
      }
      return out;
    })();

    return `
      <div class="soldier-card">
        <div class="soldier-card-header">
          <div>
            ${badgeHtml}
            <span class="soldier-name" ${cardImageAttr(c)}>${esc(c.name)}</span>
            <span class="soldier-number text-muted">(${esc(c.number)})</span>
          </div>
          <span class="text-muted" style="font-size:13px">${c.resource_cost != null ? c.resource_cost + ' ' + esc(t('stat.rp')) : ''}</span>
        </div>
        <div class="soldier-stats">
          ${c.health != null ? `<span>${esc(t('stat.hp'))} ${c.health}</span>` : ''}
          ${c.cover != null ? `<span>${esc(t('stat.cover'))} ${c.cover}</span>` : ''}
          ${c.movement != null ? `<span>${esc(t('stat.move'))} ${c.movement}</span>` : ''}
          ${c.hth != null ? `<span>${esc(t('stat.hth'))} ${c.hth >= 0 ? '+' : ''}${c.hth}</span>` : ''}
          ${!isPS && c.loadout != null ? `<span>${esc(t('stat.loadout'))} ${c.loadout}</span>` : ''}
        </div>
        ${loadoutBar}
        ${gearHtml}
      </div>`;
  }).join('');

  const commentsHtml = comments.map(cm => {
    const canEdit = currentUser && (currentUser.id === cm.author.id || currentUser.id === squad.owner.id);
    return `
      <div class="comment-item" data-cid="${cm.id}">
        <div class="comment-header">
          <span class="comment-author">${esc(cm.author.username)}</span>
          <span class="comment-date">${fmtDate(cm.created_at)}</span>
        </div>
        <div class="comment-body" data-raw="${esc(cm.body)}">${renderMentions(cm.body, commentMentions)}</div>
        ${canEdit ? `
          <div class="comment-actions">
            ${actionBtn({ icon: 'edit', label: t('common.edit'), cls: 'btn-sm edit-comment-btn', attrs: `data-cid="${cm.id}"` })}
            ${actionBtn({ icon: 'trash', label: t('common.delete'), variant: 'danger', cls: 'btn-sm delete-comment-btn', attrs: `data-cid="${cm.id}"` })}
          </div>` : ''}
      </div>`;
  }).join('');

  const commentForm = currentUser ? `
    <div class="comment-form">
      <textarea id="comment-input" placeholder="${esc(t('comments.placeholder'))}" rows="3"></textarea>
      <div class="text-muted mention-hint">${t('mention.hint_html')}</div>
      <div class="form-row">
        <button class="btn btn-primary" id="post-comment-btn">${esc(t('comments.post'))}</button>
      </div>
    </div>` : `<p class="text-muted mt-2">${t('comments.login_html')}</p>`;

  // Build prev/next navigation from the current squad browser list
  const squadNavIdx = squadNavList.indexOf(squad.id);
  const prevSqId = squadNavIdx > 0 ? squadNavList[squadNavIdx - 1] : null;
  const nextSqId = squadNavIdx >= 0 && squadNavIdx < squadNavList.length - 1 ? squadNavList[squadNavIdx + 1] : null;
  const prevSqBtn = actionBtn({ icon: 'prev', label: t('common.prev'), iconOnly: true, href: prevSqId ? '#/squads/' + prevSqId : '', disabled: !prevSqId });
  const nextSqBtn = actionBtn({ icon: 'next', label: t('common.next'), iconOnly: true, href: nextSqId ? '#/squads/' + nextSqId : '', disabled: !nextSqId });
  const squadNavPos = squadNavIdx >= 0 ? `<span class="tb-pager-pos">${squadNavIdx + 1} / ${squadNavList.length}</span>` : '';

  setMain(`
    ${pageToolbar(
      actionBtn({ icon: 'back', label: t('nav.squads'), href: '#/squads' }) +
        (squadNavIdx >= 0 ? `<span class="tb-pager">${prevSqBtn}${squadNavPos}${nextSqBtn}</span>` : ''),
      [likeBtn, copyBtn, exportBtns],
      [deleteBtn, editBtn, publishBtn])}

    <div class="squad-header">
      <h1 class="squad-title">${draftBadge} ${esc(squad.name)}</h1>
      <div class="squad-meta">
        ${esc(t('squad.by', { user: squad.owner.username }))} · ${fmtDate(squad.created_at)} · ${esc(nationLabel(squad.nation))}${requiredModules}${copiesInfo}
      </div>
      ${basedOn}
    </div>

    <div class="squad-info-row">
      <div class="squad-mission-box mission-primary">
        <div class="squad-box-label">${esc(t('col.mission'))}</div>
        ${squad.mission ? (() => {
          const m = squad.mission;
          const rp = squad.computed.rp_total;
          const budget = m.resources || 0;
          const rem = squad.computed.rp_remaining;
          const over = rem < 0;
          const pct = budget > 0 ? Math.min(100, Math.round(rp / budget * 100)) : 0;
          const subtitle = m.module ? esc(m.module) : null;
          const attrDefs = [
            m.time != null              ? [t('stat.turns'),       m.time] : null,
            m.objective_position != null ? [t('stat.obj_loc_short'), m.objective_position] : null,
            m.loadout_modifier != null  ? [t('stat.loadout'),     (m.loadout_modifier >= 0 ? '+' : '') + m.loadout_modifier] : null,
            m.action_cost_hth != null   ? [t('stat.hth_cost'),    m.action_cost_hth] : null,
          ].filter(Boolean);
          const chips = attrDefs.map(([k,v]) =>
            `<span class="mission-attr">${esc(k)} <strong>${v}</strong></span>`).join('');
          const MISSION_TYPE_COLOR = {
            'Raid':           '#b45309',
            'Airborne':       '#3730a3',
            'Shore Invasion': '#075985',
            'Holding Action': '#166534',
            'Hold the Line':  '#14532d',
            'Escape':         '#7c3aed',
          };
          const mtColor = MISSION_TYPE_COLOR[m.mission_type] || 'var(--text-muted)';
          const isFortified = squad.objectives?.some(o => o.objective_family === 'Fortification');
          return `
            <div class="mission-name">
              <span ${cardImageAttr(m)}>${esc(m.name)}</span>${customMissionChip(m)}
              ${m.nation ? `<span class="chip chip-mission" style="margin-left:6px;vertical-align:middle">${esc(tv('nation', m.nation))}</span>` : ''}
            </div>
            <div class="mission-meta-row">
              ${m.mission_type && m.mission_type !== 'Standard' ? `<span class="obj-type-badge" style="background:${mtColor}">${esc(tv('card_subtype', m.mission_type))}</span>` : ''}
              ${isFortified ? `<span class="obj-type-badge" style="background:#7f1d1d">${esc(tv('card_subtype', 'Fortification'))}</span>` : ''}
              ${m.theater ? `<span class="text-muted" style="font-size:12px">${esc(tv('theater', m.theater))}</span>` : ''}
            </div>
            ${m.module && !m.is_custom ? `<div class="mission-subtitle">${esc(tv('module', m.module))}</div>` : ''}
            <div class="mission-rp-track"><div class="mission-rp-fill ${over ? 'over' : ''}" style="width:${pct}%"></div></div>
            <div class="mission-rp-row">
              <span class="${over ? 'text-danger' : ''}">${rp} / ${budget} ${esc(t('stat.rp'))}</span>
              <span class="${over ? 'text-danger' : 'text-muted'}">${esc(over ? t('budget.over', { n: Math.abs(rem) }) : t('budget.remaining', { n: rem }))}</span>
            </div>
            ${chips ? `<div class="mission-attrs">${chips}</div>` : ''}`;
        })() : '<span class="text-muted">—</span>'}
      </div>
      <div class="squad-mission-box">
        <div class="squad-box-label">${esc(squad.objectives?.length > 1 ? t('squad.suggested_objectives') : t('squad.suggested_objective'))}</div>
        ${(() => {
          const OBJ_TYPE_COLOR = {
            'Eliminate Hostiles':     'var(--danger)',
            'Destroy Target':         '#b45309',
            'Keep Clear':             'var(--accent)',
            'Escape':                 '#7c3aed',
            'Kill Specified Hostile': '#0e7490',
          };
          // Badge text is an acronym of the (translated) label; full label goes in the tooltip.
          // "Keep Clear" → KC, single words → first 3 letters ("Escape" → ESC).
          const objBadge = (label, color, extraStyle = '') => {
            const words = label.split(/\s+/).filter(w => w && !/^(of|the|a|de|del|la|el|los|las)$/i.test(w));
            const abbr = words.length > 1 ? words.map(w => w[0]).join('') : (words[0] || '').slice(0, 3);
            return `<span class="obj-type-badge" style="background:${color}${extraStyle}" title="${esc(label)}">${esc(abbr.toUpperCase())}</span>`;
          };
          const OBJ_FAMILY_COLOR = {
            'Fallback':      '#92400e', 'Right Flank': '#166534', 'Shore':    '#075985',
            'Fortification': '#7f1d1d', 'Airborne':    '#3730a3', 'Embedded': '#4a044e',
          };
          const situationHtml = squad.situation ? `
            <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border)">
              <div class="squad-box-label" style="margin-bottom:4px">${esc(t('squad.situation'))}</div>
              <div style="font-size:13px"><span ${cardImageAttr(squad.situation)}>${esc(squad.situation.name)}</span>
              ${squad.situation.nation ? `<span class="chip chip-mission" style="margin-left:6px;vertical-align:middle">${esc(tv('nation', squad.situation.nation))}</span>` : ''}</div>
              ${squad.situation.module ? `<div class="mission-subtitle" style="margin-top:2px">${esc(tv('module', squad.situation.module))}</div>` : ''}
            </div>` : '';

          const objs = squad.objectives || [];
          if (!objs.length) {
            return `<div class="text-muted" style="font-size:13px;margin-top:4px">${esc(t('squad.no_objective'))}</div>${situationHtml}`;
          }
          const isSingle = objs.length === 1;
          const objsHtml = objs.map((o, idx) => {
            const typeColor = OBJ_TYPE_COLOR[o.objective_mechanic] || 'var(--text-muted)';
            const familyColor = o.objective_family ? (OBJ_FAMILY_COLOR[o.objective_family] || 'var(--text-muted)') : null;
            if (isSingle) {
              const attrDefs = [
                o.theater != null ? [t('stat.theater'), tv('theater', o.theater)] : null,
                o.entrance_cost != null ? [t('stat.entry_cost'), o.entrance_cost] : null,
                o.action_cost_hth != null ? [t('stat.hth_cost'), o.action_cost_hth] : null,
              ].filter(Boolean);
              const chips = attrDefs.map(([k,v]) =>
                `<span class="mission-attr">${esc(k)} <strong>${esc(v)}</strong></span>`).join('');
              return `<div class="mission-name">
                ${o.objective_mechanic ? objBadge(tv('card_subtype', o.objective_mechanic), typeColor) : ''}
                ${familyColor ? objBadge(tv('card_subtype', o.objective_family), familyColor) : ''}
                <span ${cardImageAttr(o)}>${esc(o.name)}</span>
                ${o.nation ? `<span class="chip chip-mission" style="margin-left:6px;vertical-align:middle">${esc(tv('nation', o.nation))}</span>` : ''}
              </div>
              ${o.module ? `<div class="mission-subtitle">${esc(tv('module', o.module))}</div>` : ''}
              ${chips ? `<div class="mission-attrs" style="margin-top:8px">${chips}</div>` : ''}`;
            } else {
              // Compact row — name + tiny badges only
              return `<div class="flex items-center obj-compact-row" style="${idx > 0 ? 'margin-top:6px;padding-top:6px;border-top:1px solid var(--border)' : ''}">
                <span style="font-size:13px"><span ${cardImageAttr(o)}>${esc(o.name)}</span></span>
                ${o.objective_mechanic ? objBadge(tv('card_subtype', o.objective_mechanic), typeColor, ';margin-left:6px;font-size:10px;padding:1px 5px') : ''}
              </div>`;
            }
          }).join('');
          return objsHtml + situationHtml;
        })()}
      </div>
    </div>

    <h2 style="margin-bottom:12px">${esc(t('squad.soldiers'))}</h2>
    <div class="soldiers-grid">${soldiersHtml || `<p class="text-muted">${esc(t('squad.no_soldiers'))}</p>`}</div>

    ${metricsSectionHtml(squad.metrics)}

    <div class="squad-author-notes">
      <h2 style="margin-bottom:8px">${esc(t('squad.strategy_notes'))}</h2>
      ${squad.notes
        ? `<div class="card-notes">${renderMentions(squad.notes, squad.mentions)}</div>`
        : `<p class="text-muted" style="font-size:13px;margin:0">${esc(t('squad.no_notes'))}</p>`}
    </div>

    <div class="comments-section">
      <h2 style="margin-bottom:10px">${esc(t('comments.title', { n: comments.length }))}</h2>
      <div id="comments-list">${commentsHtml || `<p class="text-muted">${esc(t('comments.none'))}</p>`}</div>
      ${commentForm}
    </div>
  `);

  attachMentionAutocomplete(document.getElementById('comment-input'));

  // Like button
  document.getElementById('like-btn')?.addEventListener('click', async () => {
    if (!currentUser) return;
    const btn = document.getElementById('like-btn');
    const isLiked = btn.classList.contains('liked');
    try {
      const res = isLiked
        ? await API.delete('/squads/' + squad.id + '/like')
        : await API.post('/squads/' + squad.id + '/like');
      btn.classList.toggle('liked', res.liked_by_me);
      btn.setAttribute('aria-pressed', String(!!res.liked_by_me));
      document.getElementById('likes-count').textContent = res.likes_count;
    } catch (e) { /* silent */ }
  });

  // Export menu: toggle, close on outside click / Escape / pick
  const exportToggle = document.getElementById('export-toggle');
  const exportList = document.getElementById('export-list');
  const setExportOpen = open => {
    exportList.hidden = !open;
    exportToggle.setAttribute('aria-expanded', String(open));
  };
  exportToggle.addEventListener('click', e => { e.stopPropagation(); setExportOpen(exportList.hidden); });
  const closeExport = e => {
    if (!document.body.contains(exportList)) {   // view re-rendered: drop the listeners
      document.removeEventListener('click', closeExport);
      document.removeEventListener('keydown', closeExport);
      return;
    }
    if (e.type === 'keydown' ? e.key === 'Escape' : !exportList.contains(e.target)) setExportOpen(false);
  };
  document.addEventListener('click', closeExport);
  document.addEventListener('keydown', closeExport);

  document.getElementById('copy-squad-btn')?.addEventListener('click', () => {
    pendingBuilderDraft = {
      refresh: true,   // squad payload has light card objects — re-fetch full details
      name: t('squad.copy_name', { name: squad.name }),
      nation: squad.nation,
      notes: squad.notes || '',
      mission: squad.mission,
      objectives: squad.objectives || [],
      situation: squad.situation,
      soldiers: squad.soldiers.map(ss => ({ card: ss.card, gear: ss.gear, default_gear: ss.default_gear })),
      parentSquadId: squad.id,
      parentName: squad.name,
    };
    navigate('builder');
  });

  document.querySelectorAll('[data-export]').forEach(btn =>
    btn.addEventListener('click', () => { setExportOpen(false); exportSquad(squad, btn.dataset.export); }));

  // Publish
  document.getElementById('publish-btn')?.addEventListener('click', async () => {
    try {
      await API.post('/squads/' + squad.id + '/publish');
      await showSquadDetail(squad.id);
    } catch (e) {
      const v = e.data?.validation;
      alert((e.error || t('squad.publish_failed')) + (v?.errors?.length ? '\n' + v.errors.map(x => x.message).join('\n') : ''));
    }
  });

  // Edit
  document.getElementById('edit-squad-btn')?.addEventListener('click', () => {
    navigate('builder/' + squad.id);
  });

  // Delete
  document.getElementById('delete-squad-btn')?.addEventListener('click', async () => {
    if (!confirm(t('squad.confirm_delete'))) return;
    try {
      await API.delete('/squads/' + squad.id);
      navigate('squads');
    } catch (e) { alert(e.error || t('squad.delete_failed')); }
  });

  // Post comment
  document.getElementById('post-comment-btn')?.addEventListener('click', async () => {
    const input = document.getElementById('comment-input');
    const body = input.value.trim();
    if (!body) return;
    try {
      await API.post('/squads/' + squad.id + '/comments', { body });
      await showSquadDetail(squad.id); // reload
    } catch (e) { alert(e.error || t('comments.post_failed')); }
  });

  // Edit/delete comments (delegated)
  document.getElementById('comments-list')?.addEventListener('click', async e => {
    const editBtn = e.target.closest('.edit-comment-btn');
    const delBtn = e.target.closest('.delete-comment-btn');
    const cid = (editBtn || delBtn)?.dataset.cid;
    if (!cid) return;

    if (delBtn) {
      if (!confirm(t('comments.confirm_delete'))) return;
      try {
        await API.delete('/squads/' + squad.id + '/comments/' + cid);
        await showSquadDetail(squad.id);
      } catch (e) { alert(e.error || t('common.failed')); }
    }
    if (editBtn) {
      const item = document.querySelector(`.comment-item[data-cid="${cid}"]`);
      const bodyEl = item.querySelector('.comment-body');
      const oldText = bodyEl.dataset.raw ?? bodyEl.textContent;
      const ta = document.createElement('textarea');
      ta.value = oldText;
      ta.rows = 3;
      ta.style.width = '100%';
      bodyEl.replaceWith(ta);
      attachMentionAutocomplete(ta);
      editBtn.innerHTML = `${icon('save')}<span class="btn-label">${esc(t('common.save'))}</span>`;
      editBtn.classList.replace('btn-ghost', 'btn-primary');
      editBtn.classList.remove('edit-comment-btn');
      editBtn.addEventListener('click', async () => {
        try {
          await API.put('/squads/' + squad.id + '/comments/' + cid, { body: ta.value.trim() });
          await showSquadDetail(squad.id);
        } catch (e) { alert(e.error || t('common.failed')); }
      });
    }
  });
}

// ---------------------------------------------------------------------------
// Reusable Card Table Component
// ---------------------------------------------------------------------------
// header = i18n key (resolved at render time so a language switch applies)
const CARD_TABLE_COLS = {
  number:            { header: '#', render: c => esc(c.number), sortKey: 'number' },
  name:              { header: 'col.name', render: c => `<span ${cardImageAttr(c)}>${esc(c.name)}</span>${trMarker(c)}`, sortKey: 'name' },
  subtype:           { header: 'col.type', render: c => chipForSubtype(c.card_subtype, c.card_type) },
  category:          { header: 'col.category', render: c => chipForCategory(c.card_type) },
  nation:            { header: 'col.nation', render: c => esc(c.nation ? tv('nation', c.nation) : '—'), sortKey: 'nation' },
  module:            { header: 'col.module', render: c => esc(tv('module', c.module)), sortKey: 'module' },
  rp:                { header: 'stat.rp', render: c => c.resource_cost != null ? String(c.resource_cost) : '', sortKey: 'resource_cost' },
  cx:                { header: 'stat.cx', render: c => c.cx ? String(c.cx) : '' },
  xp:                { header: 'stat.xp', render: c => c.xp ? String(c.xp) : '' },
  health:            { header: 'stat.hp', render: c => c.health != null ? String(c.health) : '' },
  loadout:           { header: 'stat.loadout', render: c => c.loadout != null ? String(c.loadout) : '' },
  movement:          { header: 'stat.move', render: c => c.movement != null ? String(c.movement) : '' },
  cover:             { header: 'stat.cover', render: c => c.cover != null ? String(c.cover) : '' },
  hth:               { header: 'stat.hth', render: c => c.hth != null ? (c.hth >= 0 ? '+' : '') + c.hth : '' },
  resources:         { header: 'stat.budget', render: c => c.resources != null ? c.resources + ' ' + esc(t('stat.rp')) : '' },
  time:              { header: 'stat.turns', render: c => c.time != null ? String(c.time) : '' },
  objective_position:{ header: 'stat.obj_at', render: c => c.objective_position != null ? String(c.objective_position) : '' },
  loadout_modifier:  { header: 'stat.loadout_mod', render: c => c.loadout_modifier != null ? (c.loadout_modifier >= 0 ? '+' : '') + c.loadout_modifier : '' },
  entrance_cost:     { header: 'stat.entry_cost', render: c => c.entrance_cost != null ? String(c.entrance_cost) : '', sortKey: 'entrance_cost' },
  action_cost_hth:   { header: 'stat.hth_cost', render: c => c.action_cost_hth != null ? String(c.action_cost_hth) : '', sortKey: 'action_cost_hth' },
};

const MODE_COLS = {
  mission:   ['number', 'name', 'subtype', 'module', 'resources', 'time', 'objective_position', 'loadout_modifier'],
  objective: ['number', 'name', 'subtype', 'module', 'entrance_cost', 'action_cost_hth'],
  situation: ['number', 'name', 'module', 'rp'],
  soldier:   ['number', 'name', 'subtype', 'nation', 'module', 'rp', 'cx', 'xp', 'health', 'loadout', 'movement', 'cover', 'hth'],
  gear:      ['number', 'name', 'category', 'nation', 'module', 'rp', 'loadout'],
};

function getModeColKeys() {
  return MODE_COLS[builderState.pickerMode] || ['number', 'name', 'rp'];
}

function renderCardTable(containerEl, items, opts = {}) {
  const { cols = ['number', 'name', 'rp'], onRowClick, sortKey, sortOrder = 'asc', onSort } = opts;
  const colDefs = cols.map(k => ({ key: k, ...(CARD_TABLE_COLS[k] || { header: k, render: () => '' }) }));

  const headCells = colDefs.map(col => {
    const isActive = col.sortKey && col.sortKey === sortKey;
    const indicator = isActive ? (sortOrder === 'asc' ? ' ▲' : ' ▼') : '';
    const cls = ['sort-header', col.sortKey ? 'sortable' : '', isActive ? 'sort-active' : ''].filter(Boolean).join(' ');
    const attr = col.sortKey ? `data-sort="${col.sortKey}"` : '';
    return `<th class="${cls}" ${attr}>${esc(t(col.header))}${indicator}</th>`;
  }).join('');

  const bodyRows = items.length
    ? items.map(c => {
        const cells = colDefs.map(col => `<td>${col.render ? col.render(c) : ''}</td>`).join('');
        return `<tr class="clickable" data-cid="${c.id}">${cells}</tr>`;
      }).join('')
    : `<tr><td colspan="${cols.length}" class="text-muted" style="text-align:center;padding:16px">${esc(t('cards.none'))}</td></tr>`;

  containerEl.innerHTML = `
    <div class="table-scroll">
      <table class="data-table picker-table">
        <thead><tr>${headCells}</tr></thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>`;

  if (onSort) {
    containerEl.querySelectorAll('th[data-sort]').forEach(th => {
      th.addEventListener('click', () => onSort(th.dataset.sort));
    });
  }

  if (onRowClick) {
    containerEl.querySelectorAll('tr[data-cid]').forEach(row => {
      row.addEventListener('click', () => {
        const card = items.find(c => String(c.id) === row.dataset.cid);
        if (card) onRowClick(card);
      });
    });
  }
}

// ---------------------------------------------------------------------------
// VIEW: Squad Builder
// ---------------------------------------------------------------------------
// Set by the squad list's edit pencil: the builder then shows a '← Squads' back button
let builderFromSquadList = false;

register('builder', async function(squadId) {
  const fromList = builderFromSquadList;
  builderFromSquadList = false;
  if (squadId) {
    // Load existing squad
    showSpinner();
    try {
      const data = await API.get('/squads/' + squadId);
      const sq = data.squad;
      builderState.squadId = sq.id;
      builderState.fromSquadList = fromList;
      builderState.parentSquadId = sq.parent?.id || null;
      builderState.parentName = sq.parent?.name || '';
      builderState.name = sq.name;
      builderState.missionCard = sq.mission;
      builderState.objectiveCards = sq.objectives || [];
      builderState.nation = sq.nation;
      builderState.notes = sq.notes || '';
      builderState.soldiers = sq.soldiers.map(ss => ({
        card: ss.card,
        gear: ss.gear.map(g => ({ card: g.card, quantity: g.quantity })),
        defaultGear: ss.default_gear || [],
      }));
    } catch (e) {
      showError(e.error || t('builder.load_failed'));
      return;
    }
  } else {
    // Fresh builder — always reset when navigating to #/builder without an ID,
    // unless an import / copy is waiting to be loaded
    resetBuilderState();
    if (pendingBuilderDraft) {
      const d = pendingBuilderDraft;
      pendingBuilderDraft = null;
      applyBuilderDraft(d);
      if (d.refresh) { showSpinner(); await refreshBuilderCards(); }
    }
  }
  builderState.pickerMode = null;
  renderBuilder();
});

// ---------------------------------------------------------------------------
// Import / export (backend: app/squad_io.py)
// ---------------------------------------------------------------------------
let pendingBuilderDraft = null;   // {name, nation, mission, objectives, situation, soldiers, notes?, parentSquadId?}

function applyBuilderDraft(d) {
  Object.assign(builderState, {
    squadId: null,
    name: d.name || '',
    missionCard: d.mission || null,
    objectiveCards: d.objectives || [],
    situationCard: d.situation || null,
    nation: d.nation || '',
    notes: d.notes || '',
    parentSquadId: d.parentSquadId || null,
    parentName: d.parentName || '',
    soldiers: (d.soldiers || []).map(s => ({
      card: s.card,
      gear: (s.gear || []).map(g => ({ card: g.card, quantity: g.quantity })),
      defaultGear: s.card.associations || s.default_gear || [],
    })),
  });
  sortSoldiers();
}

function downloadBlob(content, filename, type) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

async function exportSquad(squad, format) {
  const res = await fetch(`/api/squads/${squad.id}/export?format=${format}`, {
    headers: { 'X-Lang': I18N.lang }, credentials: 'same-origin',
  });
  if (!res.ok) { alert(t('common.failed')); return; }
  const body = await res.text();
  const slug = (squad.name || 'squad').replace(/[^A-Za-z0-9_-]+/g, '_');
  if (format === 'text') {
    try { await navigator.clipboard.writeText(body); alert(t('io.copied')); }
    catch (_) { downloadBlob(body, slug + '.txt', 'text/plain'); }
  } else if (format === 'csv') {
    downloadBlob(body, slug + '.csv', 'text/csv');
  } else {
    downloadBlob(body, slug + '.json', 'application/json');
    alert(res.headers.get('X-TTS-Warning') ? t('io.tts_no_images') : t('io.tts_saved'));
  }
}

function openImportDialog() {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <h2>${esc(t('io.import_title'))}</h2>
      <p class="text-muted" style="font-size:12px">${esc(t('io.import_hint'))}</p>
      <textarea id="import-content" rows="12" style="width:100%;font-family:monospace;font-size:12px"></textarea>
      <div style="display:flex;gap:6px;align-items:center;margin-top:8px;flex-wrap:wrap">
        <label class="btn btn-ghost btn-sm" style="margin:0">${esc(t('io.import_file'))}<input type="file" id="import-file" accept=".txt,.csv,text/plain,text/csv" style="display:none"></label>
        <span style="flex:1"></span>
        <button class="btn btn-ghost btn-sm" id="import-cancel">${esc(t('common.cancel'))}</button>
        <button class="btn btn-primary btn-sm" id="import-go">${esc(t('io.import_go'))}</button>
      </div>
      <div id="import-msg"></div>
    </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
  overlay.querySelector('#import-cancel').addEventListener('click', close);
  overlay.querySelector('#import-file').addEventListener('change', async e => {
    const f = e.target.files[0];
    if (f) overlay.querySelector('#import-content').value = await f.text();
  });
  overlay.querySelector('#import-go').addEventListener('click', async () => {
    const content = overlay.querySelector('#import-content').value;
    const msg = overlay.querySelector('#import-msg');
    try {
      const r = await API.post('/squads/import', { content });
      if (!r.draft.soldiers.length && !r.draft.mission) {
        msg.innerHTML = alertHtml([t('io.import_empty'), ...r.warnings].join(' · '));
        return;
      }
      if (r.warnings.length && !confirm(t('io.import_warnings') + '\n\n' + r.warnings.join('\n'))) return;
      pendingBuilderDraft = r.draft;
      close();
      if ((location.hash.slice(1) || '').replace(/^\//, '') === 'builder') route(); else navigate('builder');
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
  });
  overlay.querySelector('#import-content').focus();
}

function builderRpTotal() {
  let total = 0;
  for (const s of builderState.soldiers) {
    total += s.card.resource_cost || 0;
    for (const g of s.gear) {
      total += (g.card.resource_cost || 0) * g.quantity;
    }
  }
  return total;
}

const SUBTYPE_ORDER = { 'Player': 0, 'NPS': 1, 'Squad': 2, 'Team': 3, 'Vehicle': 4 };

function sortSoldiers() {
  builderState.soldiers.sort((a, b) => {
    const ao = SUBTYPE_ORDER[a.card.card_subtype] ?? 99;
    const bo = SUBTYPE_ORDER[b.card.card_subtype] ?? 99;
    if (ao !== bo) return ao - bo;
    return (b.card.resource_cost || 0) - (a.card.resource_cost || 0);
  });
}

// Re-fetch every card held in builderState so names/notes follow a language switch
async function refreshBuilderCards() {
  const fresh = async c => {
    if (!c?.id) return c;
    try { return (await API.get('/cards/' + c.id)).card; } catch (_) { return c; }
  };
  const bs = builderState;
  [bs.missionCard, bs.situationCard] = await Promise.all([fresh(bs.missionCard), fresh(bs.situationCard)]);
  bs.objectiveCards = await Promise.all(bs.objectiveCards.map(fresh));
  bs.soldiers = await Promise.all(bs.soldiers.map(async s => {
    const card = await fresh(s.card);
    const gear = await Promise.all(s.gear.map(async g => ({ ...g, card: await fresh(g.card) })));
    return { ...s, card, gear, defaultGear: card.associations || s.defaultGear };
  }));
}

function addSoldierToBuilder(card) {
  if (builderState.soldiers.some(s => s.card.id === card.id)) {
    alert(t('builder.soldier_already', { name: card.name }));
    return false;
  }
  builderState.soldiers.push({ card, gear: [], defaultGear: card.associations || [] });
  sortSoldiers();
  return true;
}

function addGearToBuilder(card, soldierIdx) {
  const soldier = builderState.soldiers[soldierIdx];
  if (!soldier) return false;
  // Block if already in pre-printed list (match by canonical English name, case-insensitive)
  const key = cardKey(card);
  if ((soldier.defaultGear || []).some(g => cardKey(g.card) === key)) {
    alert(t('builder.gear_preprinted', { name: card.name, soldier: soldier.card.name }));
    return false;
  }
  // A soldier cannot have the same skill twice (any copy of the same-named skill)
  if (card.card_type === 'Skill' &&
      soldier.gear.some(g => g.card.card_type === 'Skill' && cardKey(g.card) === key)) {
    alert(t('builder.skill_already', { name: card.name, soldier: soldier.card.name }));
    return false;
  }
  const existing = soldier.gear.find(g => g.card.id === card.id);
  if (existing) {
    existing.quantity += 1;
  } else {
    soldier.gear.push({ card, quantity: 1 });
  }
  return true;
}

function renderBuilder() {
  if (!currentUser) {
    setMain(`<div class="alert alert-warning">${t('builder.login_required_html')}</div>`);
    return;
  }
  setPageTitle(t(builderState.squadId ? 'builder.edit_title' : 'builder.new_title'));

  const _savedScrollY = document.querySelector('.builder-left')?.scrollTop ?? 0;
  const _savedPickerScrollY = document.querySelector('.builder-right')?.scrollTop ?? 0;
  const budget = builderState.missionCard?.resources || 0;
  const rpTotal = builderRpTotal();
  const rpRemaining = budget - rpTotal;
  const lm = builderState.missionCard?.loadout_modifier || 0;

  const budgetPct = budget > 0 ? Math.min(100, Math.round(rpTotal / budget * 100)) : 0;
  const budgetCls = rpRemaining < 0 ? 'over' : rpRemaining <= 10 ? 'warn' : '';

  const soldiersHtml = builderState.soldiers.map((s, idx) => {
    const c = s.card;
    const isPS = c.card_subtype === 'Player';
    const effectiveLoadout = isPS ? (c.loadout || 0) + lm : null;
    const gearLoadout = isPS ? s.gear.reduce((acc, g) => {
      if (['Weapon', 'Equipment'].includes(g.card.card_type)) {
        return acc + (g.card.loadout != null ? g.card.loadout : (g.card.resource_cost || 0)) * g.quantity;
      }
      return acc;
    }, 0) : 0;
    const loadPct = effectiveLoadout > 0 ? Math.min(100, Math.round(gearLoadout / effectiveLoadout * 100)) : 0;
    const loadCls = loadPct > 100 ? 'over' : loadPct >= 80 ? 'warn' : '';

    const gearItems = s.gear.map((g, gi) => {
      const unitRp = g.card.resource_cost != null ? g.card.resource_cost : 0;
      return `
      <div class="gear-item">
        <span ${cardImageAttr(g.card)} style="flex:1">${esc(g.card.name)}</span>
        <span class="text-muted" style="white-space:nowrap">${unitRp} ${esc(t('stat.rp'))}</span>
        ${g.quantity > 1 ? `<span class="gear-qty">×${g.quantity}</span>` : '<span></span>'}
        <button class="btn btn-icon remove-gear-btn" data-sidx="${idx}" data-gidx="${gi}" title="${esc(t('common.remove'))}" aria-label="${esc(t('common.remove'))}">${icon('close')}</button>
      </div>`;
    }).join('');

    const dg = s.defaultGear || [];
    const defaultGearHtml = dg.length > 0 ? `
      <div class="default-gear-section">
        <div class="default-gear-label">${esc(t('squad.included'))}:</div>
        ${dg.map(g => `
          <div class="gear-item gear-item-default">
            ${g.quantity > 1 ? `<span class="gear-qty">${g.quantity}×</span>` : ''}
            <span ${cardImageAttr(g.card)}>${esc(g.card.name)}</span>
            <span class="text-muted" style="font-size:11px">${esc(tv('card_type', g.card.card_type))}</span>
          </div>`).join('')}
      </div>` : '';

    return `
      <div class="soldier-slot">
        <div class="soldier-slot-header">
          <span>
            ${chipForSubtype(c.card_subtype, c.card_type)}
            <span class="soldier-slot-name" ${cardImageAttr(c)}>${esc(c.name)}</span>
            ${c.cx ? `<span class="badge-cx" title="${esc(t('cd.cx_tip'))}">${c.cx} ${esc(t('stat.cx'))}</span>` : ''}
            ${c.xp ? `<span class="badge-xp" title="${esc(t('cd.xp_tip'))}">${c.xp} ${esc(t('stat.xp'))}</span>` : ''}
          </span>
          <span>
            <span class="soldier-slot-cost text-muted">${c.resource_cost || 0} ${esc(t('stat.rp'))}</span>
            <button class="btn btn-icon remove-soldier-btn" data-sidx="${idx}" title="${esc(t('builder.remove_soldier'))}" aria-label="${esc(t('builder.remove_soldier'))}">${icon('close')}</button>
          </span>
        </div>
        ${isPS ? `
          <div class="gear-list">${gearItems}</div>
          <div class="bar-wrapper" style="margin-top:6px">
            <div class="bar-label">${esc(t('stat.loadout'))} ${gearLoadout}/${effectiveLoadout}</div>
            <div class="bar-track"><div class="bar-fill ${loadCls}" style="width:${loadPct}%"></div></div>
          </div>
          ${defaultGearHtml}
          <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
            <button class="btn btn-sm btn-ghost add-weapon-btn" data-sidx="${idx}">${icon('plus')}${esc(tv('card_type', 'Weapon'))}</button>
            <button class="btn btn-sm btn-ghost add-equip-btn" data-sidx="${idx}">${icon('plus')}${esc(tv('card_type', 'Equipment'))}</button>
            <button class="btn btn-sm btn-ghost add-skill-btn" data-sidx="${idx}">${icon('plus')}${esc(tv('card_type', 'Skill'))}</button>
            <button class="btn btn-sm btn-ghost add-sr-btn" data-sidx="${idx}">${icon('plus')}${esc(tv('card_type', 'Service Record'))}</button>
          </div>
        ` : (c.card_subtype === 'NPS' || c.card_subtype === 'Squad') ? `
          ${defaultGearHtml}
        ` : c.card_subtype !== 'Vehicle' ? `
          <div class="gear-list">${gearItems}</div>
          <div class="nps-gear-note" style="font-size:11px;margin-top:4px">${esc(t('builder.nps_not_counted'))}</div>
          ${defaultGearHtml}
          <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
            <button class="btn btn-sm btn-ghost add-nps-wpn-btn" data-sidx="${idx}">${icon('plus')}${esc(tv('card_type', 'Weapon'))}</button>
            <button class="btn btn-sm btn-ghost add-nps-eqp-btn" data-sidx="${idx}">${icon('plus')}${esc(tv('card_type', 'Equipment'))}</button>
            <button class="btn btn-sm btn-ghost add-nps-skl-btn" data-sidx="${idx}">${icon('plus')}${esc(tv('card_type', 'Skill'))}</button>
            <button class="btn btn-sm btn-ghost add-nps-act-btn" data-sidx="${idx}">${icon('plus')}${esc(tv('card_type', 'Action'))}</button>
          </div>
        ` : ''}
      </div>`;
  }).join('');

  setMain(`
    ${pageToolbar(
      // Cancel = leave: back to the list when opened from its edit pencil, else to the squad (or the list)
      actionBtn({ icon: 'close', label: t('common.cancel'),
        href: '#/squads' + (builderState.squadId && !builderState.fromSquadList ? '/' + builderState.squadId : '') }),
      [actionBtn({ id: 'builder-import-btn', icon: 'upload', label: t('io.import') }),
       actionBtn({ id: 'validate-btn', icon: 'validate', label: t('builder.validate') })],
      [actionBtn({ id: 'save-draft-btn', icon: 'save', label: t('builder.save_draft') }),
       actionBtn({ id: 'publish-squad-btn', icon: 'publish', label: t('squad.publish'), variant: 'primary' })])}
    <h1 class="page-title">${esc(t(builderState.squadId ? 'builder.edit_title' : 'builder.new_title'))}</h1>
    ${builderState.parentSquadId ? `<div class="squad-based-on">${t('squad.based_on_short_html', {
      link: `<a href="#/squads/${builderState.parentSquadId}">${esc(builderState.parentName || '#' + builderState.parentSquadId)}</a>` })}</div>` : ''}
    <div id="builder-validation"></div>
    <div class="builder-layout">
      <!-- LEFT -->
      <div class="builder-left">
        <div class="builder-section">
          <div class="builder-section-title">${esc(t('builder.squad_name'))}</div>
          <input type="text" id="squad-name" value="${esc(builderState.name)}" placeholder="${esc(t('builder.unnamed'))}" style="width:100%">
        </div>

        <div class="builder-section">
          <div class="builder-section-title">${esc(t('col.mission'))}</div>
          ${builderState.missionCard
            ? (() => {
                const mc = builderState.missionCard;
                const BUILDER_MISSION_COLOR = {
                  'Raid':'#b45309','Airborne':'#3730a3','Shore Invasion':'#075985',
                  'Holding Action':'#166534','Hold the Line':'#14532d','Escape':'#7c3aed',
                };
                const bmColor = BUILDER_MISSION_COLOR[mc.card_subtype];
                return `<div class="flex justify-between items-center">
                  <span>
                    ${bmColor ? `<span class="obj-type-badge" style="background:${bmColor}">${esc(tv('card_subtype', mc.card_subtype))}</span>` : ''}
                    <span ${cardImageAttr(mc)}><strong>${esc(mc.name)}</strong></span>${customMissionChip(mc)}
                  </span>
                  <span class="flex" style="gap:6px">
                    <button class="btn btn-sm btn-ghost" id="change-mission-btn">${esc(t('common.change'))}</button>
                    <button class="btn btn-sm btn-ghost" id="custom-mission-btn">${esc(t('builder.custom_mission'))}</button>
                  </span>
                </div>
                <div class="text-muted" style="font-size:12px;margin-top:4px">${esc([
                  mc.resources != null ? `${mc.resources} ${t('stat.rp')}` : null,
                  mc.time != null ? `${mc.time} ${t('stat.turns')}` : null,
                  mc.objective_position != null ? `${t('stat.obj_loc_short')}: ${mc.objective_position}` : null,
                  mc.loadout_modifier != null ? `${t('stat.loadout')}: ${mc.loadout_modifier >= 0 ? '+' : ''}${mc.loadout_modifier}` : null,
                ].filter(Boolean).join(' · '))}</div>`;
              })()
            : `<div class="flex" style="gap:6px;flex-wrap:wrap">
                <button class="btn btn-ghost" id="pick-mission-btn">${esc(t('builder.select_mission'))}</button>
                <button class="btn btn-ghost" id="custom-mission-btn">${esc(t('builder.custom_mission'))}</button>
              </div>`}
        </div>

        <div class="builder-section">
          <div class="builder-section-title">${esc(t('squad.suggested_objectives'))} <span class="text-muted">(${esc(t('common.optional'))})</span></div>
          ${builderState.objectiveCards.length > 0
            ? (() => {
                const isSingle = builderState.objectiveCards.length === 1;
                const rows = builderState.objectiveCards.map((oc, idx) => {
                  if (isSingle) {
                    const ocFamily = oc.objective_family || '';
                    const ocSubtype = oc.card_subtype || '';
                    const ocMechanic = ocFamily && ocSubtype.startsWith(ocFamily + ' / ')
                      ? ocSubtype.slice(ocFamily.length + 3) : (ocFamily ? '' : ocSubtype);
                    const attrs = [
                      oc.theater ? tv('theater', oc.theater) : null,
                      oc.entrance_cost != null ? `${t('stat.entry')}: ${oc.entrance_cost}` : null,
                      oc.action_cost_hth != null ? `${t('stat.hth')}: ${oc.action_cost_hth}` : null,
                    ].filter(Boolean).join(' · ');
                    const subtypeLabel = [ocFamily, ocMechanic].filter(Boolean).map(v => tv('card_subtype', v)).join(' · ');
                    return `<div class="flex justify-between items-center">
                      <span><span ${cardImageAttr(oc)}><strong>${esc(oc.name)}</strong></span></span>
                      <span style="display:flex;gap:4px">
                        <button class="btn btn-sm btn-ghost" data-change-obj="1">${esc(t('common.change'))}</button>
                        <button class="btn btn-icon remove-obj-btn" data-idx="${idx}" title="${esc(t('common.remove'))}" aria-label="${esc(t('common.remove'))}">${icon('close')}</button>
                      </span>
                    </div>
                    <div class="text-muted" style="font-size:11px;margin-top:3px">${esc([subtypeLabel, attrs].filter(Boolean).join(' · '))}</div>`;
                  } else {
                    return `<div class="flex justify-between items-center obj-compact-row">
                      <span style="font-size:13px"><span ${cardImageAttr(oc)}>${esc(oc.name)}</span></span>
                      <button class="btn btn-icon remove-obj-btn" data-idx="${idx}" title="${esc(t('common.remove'))}" aria-label="${esc(t('common.remove'))}">${icon('close')}</button>
                    </div>`;
                  }
                }).join('');
                const addMoreBtn = builderState.missionCard
                  ? `<button class="btn btn-ghost btn-sm" id="add-obj-btn" style="margin-top:6px">${icon('plus')}${esc(t('builder.add_another'))}</button>`
                  : '';
                return rows + addMoreBtn;
              })()
            : builderState.missionCard
              ? `<button class="btn btn-ghost" id="pick-obj-btn">${icon('plus')}${esc(t('builder.add_objective'))}</button>`
              : `<span class="text-muted">${esc(t('builder.mission_first'))}</span>`}
        </div>

        <div class="builder-section">
          <div class="builder-section-title">${esc(t('col.nation'))}</div>
          ${builderState.missionCard
            ? `<select id="nation-select" style="width:100%">
                <option value="">— ${esc(t('builder.select_nation'))} —</option>
                ${sortedNations(allNations).map(n => `<option value="${esc(n)}" ${builderState.nation===n?'selected':''}>${esc(nationLabel(n))}</option>`).join('')}
               </select>`
            : `<span class="text-muted">${esc(t('builder.mission_first'))}</span>`}
        </div>

        <div class="builder-section">
          <div class="builder-section-title">
            <span>${esc(t('squad.soldiers'))}</span>
            ${budget > 0 ? `
              <div class="bar-wrapper" style="margin-top:4px">
                <div class="bar-label">${esc(t('builder.budget_bar', { used: rpTotal, budget, status: rpRemaining >= 0 ? t('budget.remaining', { n: rpRemaining }) : t('budget.over_caps', { n: Math.abs(rpRemaining) }) }))}</div>
                <div class="bar-track"><div class="bar-fill ${budgetCls}" style="width:${budgetPct}%"></div></div>
              </div>` : ''}
          </div>
          ${soldiersHtml}
          ${builderState.missionCard
            ? `<button class="btn btn-ghost" id="add-soldier-btn" ${!builderState.nation ? `disabled title="${esc(t('builder.nation_first'))}"` : ''}>${icon('plus')}${esc(t('builder.add_soldier'))}</button>`
            : ''}
        </div>

        <div class="builder-section">
          <div class="builder-section-title">${esc(t('squad.strategy_notes'))}</div>
          <div class="text-muted" style="font-size:12px;margin-bottom:6px">${esc(t('builder.notes_hint'))} ${t('mention.hint_html')}</div>
          <textarea id="squad-notes" style="width:100%;min-height:100px;resize:vertical">${esc(builderState.notes)}</textarea>
        </div>
      </div>

      <!-- RIGHT: Card Picker -->
      <div class="builder-right" id="picker-panel">
        <div class="picker-title" id="picker-title">
          ${esc(builderState.pickerMode ? _pickerTitle(builderState.pickerMode) : t('picker.hint'))}
        </div>
        ${builderState.pickerMode ? renderPickerSearch() : ''}
        <div id="picker-results"></div>
      </div>
    </div>
  `);

  // Wire up left panel events
  const main = document.getElementById('app-main');

  main.querySelector('#squad-name')?.addEventListener('input', e => { builderState.name = e.target.value; });
  main.querySelector('#squad-notes')?.addEventListener('input', e => { builderState.notes = e.target.value; });
  attachMentionAutocomplete(main.querySelector('#squad-notes'));
  main.querySelector('#nation-select')?.addEventListener('change', e => {
    builderState.nation = e.target.value;
    builderState.soldiers = [];
    renderBuilder();
  });
  main.querySelector('#pick-mission-btn')?.addEventListener('click', () => { setPickerMode('mission'); renderBuilder(); });
  main.querySelector('#change-mission-btn')?.addEventListener('click', () => { setPickerMode('mission'); renderBuilder(); });
  main.querySelector('#custom-mission-btn')?.addEventListener('click', () => openCustomMissionDialog());
  main.querySelector('#pick-obj-btn')?.addEventListener('click', () => { setPickerMode('objective'); renderBuilder(); });
  main.querySelector('#add-obj-btn')?.addEventListener('click', () => { setPickerMode('objective'); renderBuilder(); });
  main.querySelector('[data-change-obj]')?.addEventListener('click', () => {
    builderState.objectiveCards = [];
    setPickerMode('objective');
    renderBuilder();
  });
  main.querySelectorAll('.remove-obj-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      builderState.objectiveCards.splice(parseInt(btn.dataset.idx), 1);
      renderBuilder();
    });
  });
  main.querySelector('#add-soldier-btn')?.addEventListener('click', () => { setPickerMode('soldier'); renderBuilder(); });

  // Gear buttons (delegated)
  main.querySelectorAll('.add-weapon-btn').forEach(btn => btn.addEventListener('click', () => {
    setPickerMode('gear', parseInt(btn.dataset.sidx), 'Weapon'); renderBuilder();
  }));
  main.querySelectorAll('.add-equip-btn').forEach(btn => btn.addEventListener('click', () => {
    setPickerMode('gear', parseInt(btn.dataset.sidx), 'Equipment'); renderBuilder();
  }));
  main.querySelectorAll('.add-skill-btn').forEach(btn => btn.addEventListener('click', () => {
    setPickerMode('gear', parseInt(btn.dataset.sidx), 'Skill'); renderBuilder();
  }));
  main.querySelectorAll('.add-sr-btn').forEach(btn => btn.addEventListener('click', () => {
    setPickerMode('gear', parseInt(btn.dataset.sidx), 'Service Record'); renderBuilder();
  }));
  main.querySelectorAll('.add-nps-wpn-btn').forEach(btn => btn.addEventListener('click', () => {
    setPickerMode('gear', parseInt(btn.dataset.sidx), 'Weapon'); renderBuilder();
  }));
  main.querySelectorAll('.add-nps-eqp-btn').forEach(btn => btn.addEventListener('click', () => {
    setPickerMode('gear', parseInt(btn.dataset.sidx), 'Equipment'); renderBuilder();
  }));
  main.querySelectorAll('.add-nps-skl-btn').forEach(btn => btn.addEventListener('click', () => {
    setPickerMode('gear', parseInt(btn.dataset.sidx), 'Skill'); renderBuilder();
  }));
  main.querySelectorAll('.add-nps-act-btn').forEach(btn => btn.addEventListener('click', () => {
    setPickerMode('gear', parseInt(btn.dataset.sidx), 'Action'); renderBuilder();
  }));

  // Remove soldier
  main.querySelectorAll('.remove-soldier-btn').forEach(btn => btn.addEventListener('click', () => {
    builderState.soldiers.splice(parseInt(btn.dataset.sidx), 1);
    renderBuilder();
  }));
  // Remove gear
  main.querySelectorAll('.remove-gear-btn').forEach(btn => btn.addEventListener('click', () => {
    const si = parseInt(btn.dataset.sidx), gi = parseInt(btn.dataset.gidx);
    builderState.soldiers[si].gear.splice(gi, 1);
    renderBuilder();
  }));

  // Draft / Publish / Validate
  main.querySelector('#save-draft-btn')?.addEventListener('click', () => saveSquad('draft'));
  main.querySelector('#publish-squad-btn')?.addEventListener('click', () => saveSquad('published'));
  main.querySelector('#validate-btn')?.addEventListener('click', validateSquad);
  main.querySelector('#builder-import-btn')?.addEventListener('click', openImportDialog);
  wireSmartHelp(main);

  // Restore scroll position (re-render must not jump the user back to the top)
  const _leftPanel = document.querySelector('.builder-left');
  if (_leftPanel) _leftPanel.scrollTop = _savedScrollY;

  // Load picker results and restore picker panel scroll after results render
  if (builderState.pickerMode) {
    loadPickerResults().then(() => {
      const _rightPanel = document.querySelector('.builder-right');
      if (_rightPanel) _rightPanel.scrollTop = _savedPickerScrollY;
    });
  }
}

function _pickerTitle(mode) {
  const titles = {
    mission: t('picker.mission'),
    objective: t('picker.objective'),
    situation: t('picker.situation'),
    soldier: t('picker.soldier'),
    gear: t('picker.gear', {
      cat: builderState.pickerGearCat ? tv('card_type', builderState.pickerGearCat) : t('squad.gear'),
      soldier: builderState.pickerTarget != null && builderState.soldiers[builderState.pickerTarget]
        ? builderState.soldiers[builderState.pickerTarget].card.name : tv('card_type', 'Soldier'),
    }),
  };
  return titles[mode] || '';
}

// Marks a user-made mission (module 'Custom') wherever a mission is shown
function customMissionChip(m) {
  return m?.is_custom
    ? ` <span class="chip chip-custom" title="${esc(t('mission.custom_hint'))}">${esc(t('mission.custom'))}</span>`
    : '';
}

// Custom mission: generic mission parameters → saved as a 'Custom' Mission card (CM-<id>)
// owned by the user and set as this squad's mission. No edit view (spec/08_squad_tools.md §6).
const CUSTOM_MISSION_TYPES = ['Standard', 'Raid', 'Holding Action', 'Hold the Line', 'Airborne', 'Shore Invasion'];
const CUSTOM_MISSION_THEATERS = ['Europe', 'Russia', 'North Africa', 'Mediterranean', 'Jungle', 'Far East'];

// opts.current: the mission currently selected (default: the squad builder's); opts.onSaved(card)
async function openCustomMissionDialog(opts = {}) {
  if (!currentUser) { alert(t('custom.login_required')); return; }
  const current = 'current' in opts ? opts.current : builderState.missionCard;
  const onSaved = opts.onSaved || (card => {
    builderState.missionCard = card;
    builderState.pickerMode = null;
    renderBuilder();
  });
  // A custom mission already selected → prefill. Its owner saves in place; renaming it creates a new one.
  let base = current?.is_custom ? current : null;
  if (base) { try { base = (await API.get('/cards/' + base.id)).card; } catch (_) {} }
  const editable = !!base && base.owner_user_id === currentUser.id;
  const theater = base ? (base.theater || 'Europe') : 'Europe';

  const optionList = (list, ns, sel) => list.map(v =>
    `<option value="${esc(v)}"${v === sel ? ' selected' : ''}>${esc(tv(ns, v))}</option>`).join('');
  const num = (id, label, attrs, v) => `<div class="form-field"><label for="${id}">${esc(label)}</label>` +
    `<input type="number" id="${id}" ${attrs} value="${v ?? ''}"></div>`;
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <h2>${esc(t('custom.title'))}</h2>
      <p class="text-muted" style="font-size:12px">${esc(t('custom.hint'))}</p>
      <form id="cm-form" class="custom-mission-form">
        <div class="form-field cm-wide"><label for="cm-name">${esc(t('custom.name'))}</label><input type="text" id="cm-name" maxlength="80" required value="${esc(base?.name_en ?? base?.name ?? '')}"></div>
        <div class="form-field"><label for="cm-type">${esc(t('custom.type'))}</label><select id="cm-type">${optionList(CUSTOM_MISSION_TYPES, 'card_subtype', base?.mission_type)}</select></div>
        <div class="form-field"><label for="cm-theater">${esc(t('stat.theater'))}</label><select id="cm-theater">${optionList(CUSTOM_MISSION_THEATERS, 'theater', theater)}</select></div>
        ${num('cm-rp', t('stat.rp_budget'), 'min="1" max="300" required', base?.resources)}
        ${num('cm-time', t('stat.turns'), 'min="1" max="50"', base?.time)}
        ${num('cm-obj', t('stat.obj_location'), 'min="1" max="20"', base?.objective_position)}
        ${num('cm-lm', t('stat.loadout_mod'), 'min="-10" max="10"', base ? (base.loadout_modifier ?? 0) : 0)}
        <div class="form-field cm-wide"><label for="cm-notes">${esc(t('custom.notes'))}</label><textarea id="cm-notes" rows="3" maxlength="1000" style="width:100%">${esc(base?.notes_en ?? base?.notes ?? '')}</textarea></div>
        <div id="cm-mode-hint" class="cm-wide text-muted" style="font-size:12px"></div>
        <div id="cm-msg" class="cm-wide"></div>
        <div class="cm-wide" style="display:flex;gap:6px;justify-content:flex-end">
          <button type="button" class="btn btn-ghost btn-sm" id="cm-cancel">${esc(t('common.cancel'))}</button>
          <button type="submit" class="btn btn-primary btn-sm" id="cm-submit"></button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  const $ = id => overlay.querySelector('#' + id);
  const originalName = $('cm-name').value.trim();
  // Save (update in place) only for the owner and while the name is unchanged
  const isSave = () => editable && $('cm-name').value.trim() === originalName;
  const syncMode = () => {
    $('cm-submit').textContent = t(isSave() ? 'common.save' : 'custom.create');
    $('cm-mode-hint').textContent = isSave() ? t('custom.save_hint')
      : (base ? t(editable ? 'custom.rename_hint' : 'custom.copy_hint') : '');
  };
  syncMode();
  $('cm-name').addEventListener('input', syncMode);
  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
  $('cm-cancel').addEventListener('click', close);
  $('cm-name').focus();
  $('cm-form').addEventListener('submit', async e => {
    e.preventDefault();
    const body = {
      name: $('cm-name').value, mission_type: $('cm-type').value, theater: $('cm-theater').value,
      resources: $('cm-rp').value, time: $('cm-time').value, objective_position: $('cm-obj').value,
      loadout_modifier: $('cm-lm').value, notes: $('cm-notes').value,
    };
    // Renamed own mission → new card; the server drops the old one if no squad uses it
    if (editable && !isSave()) body.replaces = base.id;
    try {
      const r = isSave()
        ? await API.put('/cards/custom-missions/' + base.id, body)
        : await API.post('/cards/custom-missions', body);
      close();
      onSaved(r.card);
    } catch (err) {
      $('cm-msg').innerHTML = alertHtml(err.error || t('common.failed'));
    }
  });
}

function setPickerMode(mode, target = null, gearCat = null) {
  builderState.pickerMode = mode;
  builderState.pickerTarget = target;
  builderState.pickerGearCat = gearCat;
  builderState.pickerSort = 'module';
  builderState.pickerOrder = 'asc';
  builderState.pickerPage = 1;
  builderState.pickerModule = '';
  builderState.pickerQ = '';
}

function renderPickerSearch() {
  const moduleOptions = ['', ...allModules].map(m =>
    `<option value="${esc(m)}" ${builderState.pickerModule === m ? 'selected' : ''}>${esc(m ? tv('module', m) : t('cards.all_modules'))}</option>`
  ).join('');
  return `
    <div class="filter-bar mb-2" style="flex-wrap:wrap;gap:6px">
      <input type="text" class="search-input" id="picker-q" placeholder="${esc(t('cards.search_placeholder'))}" value="${esc(builderState.pickerQ)}" style="flex:1;min-width:120px">
      ${smartHelpButton('picker-smart-help')}
      <select id="picker-module-select">${moduleOptions}</select>
    </div>
    ${smartHelpBox('picker-smart-help')}
    <div id="picker-errors"></div>`;
}

async function loadPickerResults() {
  const params = new URLSearchParams();
  params.set('per_page', '100');
  params.set('sort', builderState.pickerSort);
  params.set('order', builderState.pickerOrder);

  switch (builderState.pickerMode) {
    case 'mission':   params.set('category', 'Mission'); params.set('include_mine', 'true'); break;
    case 'objective': params.set('category', 'Objective'); break;
    case 'situation': params.set('category', 'Situation'); break;
    case 'soldier':   params.set('category', 'Soldier'); break;
    case 'gear':
      if (builderState.pickerGearCat) params.set('category', builderState.pickerGearCat);
      break;
  }

  if (builderState.nation && builderState.pickerMode !== 'mission') {
    params.set('nation', builderState.nation);
    params.set('nation_strict', 'true');
  }
  if (builderState.pickerQ) params.set('q', builderState.pickerQ);
  if (builderState.pickerModule) params.set('module', builderState.pickerModule);

  const resultsDiv = document.getElementById('picker-results');
  if (!resultsDiv) return;
  resultsDiv.innerHTML = '<div class="spinner-wrap"><div class="spinner"></div></div>';

  try {
    const data = await API.get('/cards?' + params.toString());
    const items = data.items;
    const cols = getModeColKeys();
    const errDiv = document.getElementById('picker-errors');
    if (errDiv) errDiv.innerHTML = smartErrorsHtml(data.filter_errors);

    renderCardTable(resultsDiv, items, {
      cols,
      sortKey: builderState.pickerSort === 'module' ? 'module' : builderState.pickerSort,
      sortOrder: builderState.pickerOrder,
      onSort: (key) => {
        if (builderState.pickerSort === key) {
          builderState.pickerOrder = builderState.pickerOrder === 'asc' ? 'desc' : 'asc';
        } else {
          builderState.pickerSort = key;
          builderState.pickerOrder = 'asc';
        }
        loadPickerResults();
      },
      onRowClick: async (card) => {
        // For mission/objective/situation/soldier we need the full detail object
        let fullCard = card;
        if (['mission', 'objective', 'situation', 'soldier'].includes(builderState.pickerMode)) {
          try { fullCard = (await API.get('/cards/' + card.id)).card; } catch (_) {}
        }
        switch (builderState.pickerMode) {
          case 'mission':
            builderState.missionCard = fullCard;
            builderState.pickerMode = null;
            break;
          case 'objective':
            if (!builderState.objectiveCards.find(o => o.id === fullCard.id)) {
              builderState.objectiveCards.push(fullCard);
            }
            renderBuilder();
            loadPickerResults();
            return;
          case 'situation':
            builderState.situationCard = fullCard;
            builderState.pickerMode = null;
            break;
          case 'soldier':
            if (addSoldierToBuilder(fullCard)) {
              renderBuilder();
              const newIdx = builderState.soldiers.findIndex(s => s.card.id === fullCard.id);
              const slots = document.querySelectorAll('.soldier-slot');
              if (slots[newIdx]) slots[newIdx].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
              return;
            }
            break;
          case 'gear':
            addGearToBuilder(fullCard, builderState.pickerTarget);
            break;
        }
        renderBuilder();
      },
    });

    // Mark already-selected objectives
    if (builderState.pickerMode === 'objective' && builderState.objectiveCards.length > 0) {
      const selectedIds = new Set(builderState.objectiveCards.map(o => o.id));
      resultsDiv.querySelectorAll('tr[data-id]').forEach(tr => {
        if (selectedIds.has(parseInt(tr.dataset.id))) tr.classList.add('picker-row-selected');
      });
    }

    // Wire picker search/filter inputs
    const qInput = document.getElementById('picker-q');
    if (qInput) {
      qInput.addEventListener('input', e => {
        clearTimeout(qInput._timer);
        qInput._timer = setTimeout(() => {
          builderState.pickerQ = e.target.value;
          loadPickerResults();
        }, 300);
      });
    }
    const modSel = document.getElementById('picker-module-select');
    if (modSel) {
      modSel.addEventListener('change', e => {
        builderState.pickerModule = e.target.value;
        loadPickerResults();
      });
    }
  } catch (e) {
    resultsDiv.innerHTML = `<div class="alert alert-error">${esc(e.error || t('cards.load_failed'))}</div>`;
  }
}

async function validateSquad() {
  const payload = buildSquadPayload();
  const div = document.getElementById('builder-validation');
  if (!div) return;
  div.innerHTML = '<div class="spinner-wrap"><div class="spinner"></div></div>';
  try {
    const result = await API.post('/squads/validate', payload);
    div.innerHTML = renderValidation(result);
  } catch (e) {
    div.innerHTML = alertHtml(e.error || t('builder.validation_error'));
  }
}

function resetBuilderState() {
  Object.assign(builderState, {
    squadId: null, fromSquadList: false, parentSquadId: null, parentName: '', name: '', missionCard: null, objectiveCards: [],
    situationCard: null, nation: '', notes: '', soldiers: [],
    pickerMode: null, pickerTarget: null, pickerGearCat: null,
    pickerSort: 'module', pickerOrder: 'asc', pickerPage: 1,
    pickerModule: '', pickerQ: '',
  });
}

async function saveSquad(status = 'draft') {
  const payload = buildSquadPayload(status);
  const div = document.getElementById('builder-validation');
  try {
    let result;
    if (builderState.squadId) {
      result = await API.put('/squads/' + builderState.squadId, payload);
    } else {
      result = await API.post('/squads/', payload);
    }
    const savedId = result.squad.id;
    resetBuilderState();
    navigate('squads/' + savedId);
  } catch (e) {
    if (div) {
      div.innerHTML = alertHtml(e.error || t('builder.save_failed'));
      if (e.data?.validation) div.innerHTML += renderValidation(e.data.validation);
    }
  }
}

function buildSquadPayload(status = 'draft') {
  return {
    name: builderState.name || t('builder.unnamed'),
    parent_squad_id: builderState.parentSquadId || null,
    mission_card_id: builderState.missionCard?.id || null,
    objective_card_ids: builderState.objectiveCards.map(o => o.id),
    situation_card_id: builderState.situationCard?.id || null,
    nation: builderState.nation,
    notes: builderState.notes,
    status,
    soldiers: builderState.soldiers.map((s, i) => ({
      card_id: s.card.id,
      sort_order: i,
      gear: s.gear.map(g => ({ card_id: g.card.id, quantity: g.quantity })),
    })),
  };
}

function renderValidation(v) {
  let html = '';
  if (v.errors && v.errors.length) {
    html += `<div class="alert alert-error"><strong>${esc(t('validation.errors'))}:</strong><ul>` +
      v.errors.map(e => `<li>${esc(e.message)}</li>`).join('') + '</ul></div>';
  }
  if (v.warnings && v.warnings.length) {
    html += `<div class="alert alert-warning"><strong>${esc(t('validation.warnings'))}:</strong><ul>` +
      v.warnings.map(w => `<li>${esc(w.message)}</li>`).join('') + '</ul></div>';
  }
  if (!v.errors?.length && !v.warnings?.length) {
    html += `<div class="alert alert-success">✓ ${esc(t('validation.valid'))}</div>`;
  }
  return html;
}

// ---------------------------------------------------------------------------
// VIEW: Profile
// ---------------------------------------------------------------------------
register('profile', async function() {
  if (!currentUser) { navigate('login'); return; }
  showSpinner();
  let profile;
  try {
    const p = await API.get('/profile/');
    profile = p;
  } catch (e) {
    showError(e.error || t('profile.load_failed'));
    return;
  }

  const ownedCount = profile.modules.filter(m => m.owned).length;

  setMain(`
    <h1 style="margin-bottom:20px">${esc(t('profile.title'))}</h1>

    <div class="profile-section">
      <h2>${esc(t('profile.account'))}</h2>
      <div class="form-field">
        <label>${esc(t('auth.username'))}</label>
        <div>${esc(profile.user.username)}</div>
      </div>
      <div class="form-field">
        <label>${esc(t('auth.email'))}</label>
        <div>${esc(profile.user.email)}</div>
      </div>
      <div class="form-field">
        <label>${esc(t('auth.full_name'))}</label>
        <input type="text" id="full-name" value="${esc(profile.user.full_name || '')}">
      </div>
      <div class="form-field">
        <label>${esc(t('header.language'))}</label>
        <select id="profile-lang">
          ${I18N.SUPPORTED.map(l => `<option value="${l}" ${l === I18N.lang ? 'selected' : ''}>${esc(I18N.NAMES[l])}</option>`).join('')}
        </select>
      </div>
      <button class="btn btn-primary" id="save-profile-btn">${esc(t('profile.save'))}</button>
      <div id="profile-msg"></div>
    </div>

    <div class="profile-section">
      <h2>${esc(t('profile.change_password'))}</h2>
      <div class="form-field"><label>${esc(t('profile.current_password'))}</label><input type="password" id="cur-pw" autocomplete="current-password"></div>
      ${newPasswordFields('new')}
      <button class="btn btn-primary" id="save-pw-btn">${esc(t('profile.update_password'))}</button>
      <div id="pw-msg"></div>
    </div>

    <div class="profile-section">
      <h2>${esc(t('profile.change_email'))}</h2>
      <div class="form-field"><label>${esc(t('profile.new_email'))}</label><input type="email" id="new-email" autocomplete="email"></div>
      <div class="form-field"><label>${esc(t('profile.current_password'))}</label><input type="password" id="email-pw" autocomplete="current-password"></div>
      <button class="btn btn-primary" id="save-email-btn">${esc(t('profile.change_email'))}</button>
      <div id="email-msg"></div>
    </div>

    <div class="profile-section">
      <h2>${esc(t('profile.sessions'))}</h2>
      <p class="text-muted" style="font-size:13px">${esc(t('profile.logout_all_intro'))}</p>
      <button class="btn btn-ghost" id="logout-all-btn">${esc(t('profile.logout_all'))}</button>
    </div>

    <div class="profile-section">
      <h2>${esc(t('nav.expansions'))}</h2>
      <p class="text-muted" style="font-size:13px">${esc(t('profile.expansions_intro', { owned: ownedCount, total: profile.modules.length }))}</p>
      <a class="btn btn-ghost" href="#/expansions">${esc(t('profile.manage_expansions'))}</a>
    </div>
  `);

  const main = document.getElementById('app-main');

  main.querySelector('#save-profile-btn')?.addEventListener('click', async () => {
    const fn = main.querySelector('#full-name').value.trim();
    const lang = main.querySelector('#profile-lang').value;
    const msg = main.querySelector('#profile-msg');
    try {
      await API.put('/profile/', { full_name: fn, language: lang });
      if (lang !== I18N.lang) { await changeLanguage(lang); return; }
      msg.innerHTML = alertHtml(t('profile.saved'), 'success');
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
  });

  main.querySelector('#save-pw-btn')?.addEventListener('click', async () => {
    const cp = main.querySelector('#cur-pw').value;
    const msg = main.querySelector('#pw-msg');
    const np = readNewPassword('new', msg);
    if (np === null) return;
    try {
      await API.put('/profile/password', { current_password: cp, new_password: np });
      msg.innerHTML = alertHtml(t('profile.password_updated'), 'success');
      ['#cur-pw', '#new-pw', '#new-pw2'].forEach(id => { main.querySelector(id).value = ''; });
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
  });

  main.querySelector('#save-email-btn')?.addEventListener('click', async () => {
    const msg = main.querySelector('#email-msg');
    try {
      const r = await API.put('/profile/email', {
        new_email: main.querySelector('#new-email').value.trim(),
        current_password: main.querySelector('#email-pw').value,
      });
      msg.innerHTML = alertHtml(r.message, 'success');
      main.querySelector('#email-pw').value = '';
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
  });

  main.querySelector('#logout-all-btn')?.addEventListener('click', async () => {
    if (!confirm(t('profile.logout_all_confirm'))) return;
    try { await API.post('/auth/logout-all'); } catch (_) {}
    currentUser = null;
    renderHeader();
    updateProfileLink();
    navigate('login');
  });
});

// ---------------------------------------------------------------------------
// VIEW: Translations (owner only — users.is_admin). See spec/07_i18n.md §4.3
// ---------------------------------------------------------------------------
const trState = {
  lang: I18N.SUPPORTED.find(l => l !== 'en'),
  type: '', module: '', status: 'missing', q: '', page: 1,
  navList: [],      // card numbers of the current list page (editor prev/next)
};
const _glossary = {};  // lang -> [{en, tr, note}]

async function loadGlossary(lang) {
  if (_glossary[lang]) return _glossary[lang];
  _glossary[lang] = [];
  try {
    const res = await fetch(`/static/i18n/glossary.${lang}.csv`, { cache: 'no-cache' });
    if (res.ok) {
      const lines = (await res.text()).split(/\r?\n/).slice(1).filter(l => l.trim());
      _glossary[lang] = lines.map(l => {
        const [en, tr, ...note] = l.split(',');
        return { en: (en || '').trim(), tr: (tr || '').trim(), note: note.join(',').trim() };
      }).filter(g => g.en);
    }
  } catch (_) {}
  return _glossary[lang];
}

function glossaryHits(glossary, ...texts) {
  const hay = texts.filter(Boolean).join('\n');
  return glossary.filter(g => new RegExp(`\\b${g.en.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i').test(hay));
}

function trStatusBadge(st) {
  return `<span class="tr-badge tr-badge-${st}">${esc(t('tr.status.' + st))}</span>`;
}

register('translations', async function(number) {
  if (!currentUser?.is_admin) { setMain(`<div class="alert alert-warning">${esc(t('tr.admin_only'))}</div>`); return; }
  if (!allModules.length) {
    try { const r = await API.get('/modules'); allModules = r.modules || []; } catch (_) {}
  }
  if (number) { await showTranslationEditor(decodeURIComponent(number)); return; }
  renderTranslationsShell();
});

function renderTranslationsShell() {
  const f = trState;
  const opt = (val, cur, label) => `<option value="${esc(val)}" ${val === cur ? 'selected' : ''}>${esc(label)}</option>`;
  setMain(`
    <div class="flex justify-between items-center" style="margin-bottom:12px;flex-wrap:wrap;gap:8px">
      <h1>${esc(t('tr.title'))}</h1>
      <div style="display:flex;gap:6px;align-items:center">
        <select id="tr-lang">${I18N.SUPPORTED.filter(l => l !== 'en').map(l => opt(l, f.lang, I18N.NAMES[l])).join('')}</select>
        <button class="btn btn-sm btn-ghost" id="tr-export">${esc(t('tr.export'))}</button>
        <label class="btn btn-sm btn-ghost" style="margin:0">${esc(t('tr.import'))}<input type="file" id="tr-import" accept=".json,application/json" style="display:none"></label>
      </div>
    </div>
    <div id="tr-stats" style="margin-bottom:12px"></div>
    <div id="tr-import-msg"></div>
    <div class="filter-bar" style="flex-wrap:wrap;gap:6px">
      <input type="text" class="search-input" id="tr-q" placeholder="${esc(t('tr.search_placeholder'))}" value="${esc(f.q)}" style="flex:1;min-width:180px">
      <select id="tr-status">
        ${opt('', f.status, t('tr.all_statuses'))}
        ${['missing', 'stale', 'draft', 'reviewed'].map(st => opt(st, f.status, t('tr.status.' + st))).join('')}
      </select>
      <select id="tr-type">${['', ...allCategories].map(c => opt(c, f.type, c ? tv('card_type', c) : t('cards.all_categories'))).join('')}</select>
      <select id="tr-module">${['', ...allModules].map(m => opt(m, f.module, m ? tv('module', m) : t('cards.all_modules'))).join('')}</select>
    </div>
    <div id="tr-results"></div>
  `);

  const main = document.getElementById('app-main');
  const reload = () => { f.page = 1; refreshTranslationsList(); };
  main.querySelector('#tr-lang').addEventListener('change', e => { f.lang = e.target.value; refreshTranslationStats(); reload(); });
  main.querySelector('#tr-status').addEventListener('change', e => { f.status = e.target.value; reload(); });
  main.querySelector('#tr-type').addEventListener('change', e => { f.type = e.target.value; reload(); });
  main.querySelector('#tr-module').addEventListener('change', e => { f.module = e.target.value; reload(); });
  let debounce;
  main.querySelector('#tr-q').addEventListener('input', e => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { f.q = e.target.value; reload(); }, 300);
  });
  main.querySelector('#tr-export').addEventListener('click', async () => {
    try {
      const data = await API.get('/translations/export?lang=' + f.lang);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `card_translations.${f.lang}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { alert(e.error || t('common.failed')); }
  });
  main.querySelector('#tr-import').addEventListener('change', async e => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    const msg = document.getElementById('tr-import-msg');
    let entries;
    try { entries = JSON.parse(await file.text()); } catch (_) { msg.innerHTML = alertHtml(t('tr.import_invalid')); return; }
    const fmt = r => t('tr.import_report', {
      inserted: r.inserted, updated: r.updated, unchanged: r.unchanged,
      kept: r.kept_reviewed.length, unknown: r.unknown_numbers.length, invalid: r.invalid.length,
    });
    try {
      const dry = (await API.post('/translations/import?dry_run=true', entries)).report;
      if (!confirm(t('tr.import_confirm') + '\n\n' + fmt(dry))) return;
      const res = (await API.post('/translations/import', entries)).report;
      msg.innerHTML = alertHtml(fmt(res), 'success');
      refreshTranslationStats();
      refreshTranslationsList();
    } catch (err) { msg.innerHTML = alertHtml(err.error || t('common.failed')); }
  });

  refreshTranslationStats();
  refreshTranslationsList();
}

async function refreshTranslationStats() {
  const div = document.getElementById('tr-stats');
  if (!div) return;
  try {
    const s = await API.get('/translations/stats?lang=' + trState.lang);
    const all = Object.values(s.total).reduce((a, b) => a + b, 0) || 1;
    const pct = st => (s.total[st] / all * 100).toFixed(1);
    div.innerHTML = `
      <div class="tr-progress">
        ${['reviewed', 'draft', 'stale', 'missing'].map(st => `<div class="tr-progress-${st}" style="width:${pct(st)}%"></div>`).join('')}
      </div>
      <div class="tr-progress-legend">
        ${['reviewed', 'draft', 'stale', 'missing'].map(st =>
          `${trStatusBadge(st)} ${fmtNumber(s.total[st])}`).join(' &nbsp; ')}
      </div>`;
  } catch (e) { div.innerHTML = alertHtml(e.error || t('common.failed')); }
}

async function refreshTranslationsList() {
  const div = document.getElementById('tr-results');
  if (!div) return;
  const f = trState;
  const params = new URLSearchParams({ lang: f.lang, page: f.page, per_page: 50 });
  if (f.status) params.set('status', f.status);
  if (f.type) params.set('type', f.type);
  if (f.module) params.set('module', f.module);
  if (f.q) params.set('q', f.q);
  let data;
  try { data = await API.get('/translations?' + params); }
  catch (e) { div.innerHTML = alertHtml(e.error || t('common.failed')); return; }

  f.navList = data.items.map(i => i.number);
  const rows = data.items.map(i => `
    <tr class="clickable" data-number="${esc(i.number)}">
      <td class="text-muted" style="font-size:11px">${esc(i.number)}</td>
      <td><span ${cardImageAttr(i)}>${esc(i.name_en)}</span></td>
      <td>${esc(i.translations.name?.value || '')}</td>
      <td>${chipForCategory(i.card_type)}</td>
      <td>${trStatusBadge(i.status)}</td>
    </tr>`).join('');
  div.innerHTML = `
    <div style="font-size:12px;color:var(--text-muted);margin:8px 0">${esc(tn('tr.count', data.total))}</div>
    <div class="table-scroll">
      <table class="data-table">
        <thead><tr><th>#</th><th>${esc(t('tr.english'))}</th><th>${esc(I18N.NAMES[f.lang])}</th><th>${esc(t('col.type'))}</th><th>${esc(t('col.status'))}</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">${esc(t('cards.none'))}</td></tr>`}</tbody>
      </table>
    </div>
    ${paginationHtml(data.page, data.pages)}`;
  div.querySelectorAll('tr[data-number]').forEach(row =>
    row.addEventListener('click', () => navigate('translations/' + encodeURIComponent(row.dataset.number))));
  div.querySelectorAll('[data-pg]').forEach(btn =>
    btn.addEventListener('click', () => { f.page = parseInt(btn.dataset.pg); refreshTranslationsList(); }));
}

async function showTranslationEditor(number) {
  showSpinner();
  const f = trState;
  let item;
  try {
    const data = await API.get('/translations?' + new URLSearchParams({ lang: f.lang, number }));
    item = data.items.find(i => i.number === number);
  } catch (e) { showError(e.error || t('common.failed')); return; }
  if (!item) { showError(t('cards.not_found')); return; }
  const glossary = await loadGlossary(f.lang);
  const hits = glossaryHits(glossary, item.name_en, item.notes_en);
  const tr = item.translations;
  const staleNote = fld => tr[fld]?.stale ? `<div class="alert alert-warning" style="margin:4px 0">${esc(t('tr.stale_note'))}</div>` : '';

  const navIdx = f.navList.indexOf(number);
  const prev = navIdx > 0 ? f.navList[navIdx - 1] : null;
  const next = navIdx >= 0 && navIdx < f.navList.length - 1 ? f.navList[navIdx + 1] : null;
  const navBtn = (num, label) => num
    ? `<a href="#/translations/${encodeURIComponent(num)}" class="btn btn-ghost btn-sm">${label}</a>`
    : `<span class="btn btn-ghost btn-sm" style="opacity:.35;pointer-events:none">${label}</span>`;

  setMain(`
    <div class="cd-nav">
      <a href="#/translations" class="btn btn-ghost btn-sm">↩ ${esc(t('tr.title'))}</a>
      <a href="#/cards/${item.id}" class="btn btn-ghost btn-sm">${esc(t('tr.view_card'))}</a>
      <span style="flex:1"></span>
      ${navBtn(prev, '← ' + esc(t('common.prev')))}
      ${navBtn(next, esc(t('common.next')) + ' →')}
    </div>
    <div class="tr-editor">
      <div class="tr-editor-source">
        <div class="cd-eyebrow">${chipForCategory(item.card_type)} <span class="cd-eyebrow-num">${esc(item.number)}</span> ${trStatusBadge(item.status)}</div>
        <div class="tr-label">${esc(t('tr.english'))}</div>
        <h2>${esc(item.name_en)}</h2>
        ${item.notes_en ? `<div class="cd-notes">${esc(item.notes_en)}</div>` : ''}
        ${hits.length ? `<div class="tr-glossary">
          <div class="tr-label">${esc(t('tr.glossary'))}</div>
          ${hits.map(g => `<div><strong>${esc(g.en)}</strong> → ${esc(g.tr)}${g.note ? ` <span class="text-muted">(${esc(g.note)})</span>` : ''}</div>`).join('')}
        </div>` : ''}
        ${item.image_url ? `<img src="${esc(item.image_url)}" alt="" class="tr-editor-image">` : ''}
      </div>
      <div class="tr-editor-target">
        <div class="tr-label">${esc(I18N.NAMES[f.lang])} — ${esc(t('col.name'))} ${tr.name ? trStatusBadge(tr.name.stale ? 'stale' : tr.name.status) : ''}</div>
        ${staleNote('name')}
        <input type="text" id="tr-name" value="${esc(tr.name?.value || '')}" placeholder="${esc(item.name_en)}" style="width:100%">
        ${item.notes_en ? `
          <div class="tr-label" style="margin-top:14px">${esc(I18N.NAMES[f.lang])} — ${esc(t('cd.notes'))} ${tr.notes ? trStatusBadge(tr.notes.stale ? 'stale' : tr.notes.status) : ''}</div>
          ${staleNote('notes')}
          <textarea id="tr-notes" rows="${Math.min(20, Math.max(5, item.notes_en.split('\n').length + 2))}" style="width:100%" placeholder="${esc(item.notes_en)}">${esc(tr.notes?.value || '')}</textarea>` : ''}
        <div style="display:flex;gap:6px;margin-top:12px;flex-wrap:wrap">
          <button class="btn btn-primary" id="tr-save-reviewed">${esc(t('tr.save_reviewed'))}</button>
          <button class="btn btn-ghost" id="tr-save-draft">${esc(t('tr.save_draft'))}</button>
        </div>
        <div class="text-muted" style="font-size:12px;margin-top:6px">${esc(t('tr.save_hint'))}</div>
        <div id="tr-msg"></div>
      </div>
    </div>
  `);

  const save = async status => {
    const body = { lang: f.lang, status, name: document.getElementById('tr-name').value };
    const notesEl = document.getElementById('tr-notes');
    if (notesEl) body.notes = notesEl.value;
    const msg = document.getElementById('tr-msg');
    try {
      await API.put('/translations/' + encodeURIComponent(number), body);
      if (next && status === 'reviewed') { navigate('translations/' + encodeURIComponent(next)); return; }
      await showTranslationEditor(number);
      document.getElementById('tr-msg').innerHTML = alertHtml(t('profile.saved'), 'success');
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
  };
  document.getElementById('tr-save-reviewed').addEventListener('click', () => save('reviewed'));
  document.getElementById('tr-save-draft').addEventListener('click', () => save('draft'));
}

// ---------------------------------------------------------------------------
// Auth views (spec/06_ui.md §Auth). Emailed links land on #/verify|reset|confirm-email/<token>.
// ---------------------------------------------------------------------------
const PASSWORD_MIN_LENGTH = 15;   // keep in sync with PASSWORD_MIN_LENGTH (app/config.py); server enforces it

function authForm(title, body) {
  setMain(`
    <div class="auth-form-wrapper">
      <h1>${esc(title)}</h1>
      <div id="auth-msg"></div>
      ${body}
    </div>`);
  return document.getElementById('auth-msg');
}

function authFooter(html) {
  return `<div class="auth-form-footer mt-2" style="text-align:center;font-size:13px">${html}</div>`;
}

const loginLink = () => `<a href="#/login">${esc(t('header.login'))}</a>`;

// Token from an emailed link: kept in memory, removed from the address bar + history
function takeToken(view, token) {
  if (token) history.replaceState(null, '', `#/${view}`);
  return token || '';
}

// New password + repeat; returns the password, or null after showing the problem in `msg`
function newPasswordFields(prefix, labelKey = 'profile.new_password') {
  return `
    <div class="form-field"><label>${esc(t(labelKey))}</label>
      <input type="password" id="${prefix}-pw" autocomplete="new-password" maxlength="128">
      <div class="text-muted" style="font-size:12px;margin-top:4px">${esc(t('auth.password_hint', { n: PASSWORD_MIN_LENGTH }))}</div></div>
    <div class="form-field"><label>${esc(t('auth.password_repeat'))}</label>
      <input type="password" id="${prefix}-pw2" autocomplete="new-password" maxlength="128"></div>`;
}

function readNewPassword(prefix, msg) {
  const pw = document.getElementById(`${prefix}-pw`).value;
  if (pw !== document.getElementById(`${prefix}-pw2`).value) {
    msg.innerHTML = alertHtml(t('auth.password_mismatch'));
    return null;
  }
  return pw;
}

function onEnter(id, fn) {
  document.getElementById(id).addEventListener('keydown', e => { if (e.key === 'Enter') fn(); });
}

// ---------------------------------------------------------------------------
// VIEW: Login
// ---------------------------------------------------------------------------
register('login', function() {
  const msg = authForm(t('header.login'), `
    <div class="form-field"><label>${esc(t('auth.login_id'))}</label><input type="text" id="login-user" autocomplete="username"></div>
    <div class="form-field"><label>${esc(t('auth.password'))}</label><input type="password" id="login-pw" autocomplete="current-password"></div>
    <label style="display:flex;gap:6px;align-items:center;font-size:13px"><input type="checkbox" id="login-remember"> ${esc(t('auth.remember'))}</label>
    <button class="btn btn-primary" id="login-btn" style="width:100%;margin-top:8px">${esc(t('header.login'))}</button>
    ${authFooter(`<a href="#/forgot">${esc(t('auth.forgot_link'))}</a>`)}
    ${authFooter(`${esc(t('auth.no_account'))} <a href="#/register">${esc(t('header.register'))}</a>`)}`);

  const doLogin = async () => {
    const login = document.getElementById('login-user').value.trim();
    try {
      const data = await API.post('/auth/login', {
        login,
        password: document.getElementById('login-pw').value,
        remember: document.getElementById('login-remember').checked,
      });
      currentUser = data.user;
      await applyUserLanguage();
      renderHeader();
      updateProfileLink();
      navigate('squads');
    } catch (e) {
      if (e.data?.code !== 'email_unverified') { msg.innerHTML = alertHtml(e.error || t('auth.login_failed')); return; }
      msg.innerHTML = `<div class="alert alert-warning">${esc(e.error)}
        <div class="mt-2"><button class="btn btn-sm btn-ghost" id="resend-btn">${esc(t('auth.resend'))}</button></div></div>`;
      msg.querySelector('#resend-btn').addEventListener('click', async () => {
        try { const r = await API.post('/auth/verify/resend', { login }); msg.innerHTML = alertHtml(r.message, 'info'); }
        catch (e2) { msg.innerHTML = alertHtml(e2.error || t('common.failed')); }
      });
    }
  };

  document.getElementById('login-btn').addEventListener('click', doLogin);
  onEnter('login-pw', doLogin);
});

// ---------------------------------------------------------------------------
// VIEW: Register — no session until the emailed link confirms the address
// ---------------------------------------------------------------------------
register('register', function() {
  const msg = authForm(t('auth.create_account'), `
    <div class="form-field"><label>${esc(t('auth.username'))}</label><input type="text" id="reg-user" autocomplete="username" maxlength="30"></div>
    <div class="form-field"><label>${esc(t('auth.email'))}</label><input type="email" id="reg-email" autocomplete="email"></div>
    <div class="form-field"><label>${esc(t('auth.full_name'))} <span class="text-muted">(${esc(t('common.optional'))})</span></label><input type="text" id="reg-name" autocomplete="name"></div>
    ${newPasswordFields('reg', 'auth.password')}
    <button class="btn btn-primary" id="reg-btn" style="width:100%;margin-top:8px">${esc(t('auth.create_account'))}</button>
    ${authFooter(`${esc(t('auth.have_account'))} ${loginLink()}`)}`);

  document.getElementById('reg-btn').addEventListener('click', async () => {
    const password = readNewPassword('reg', msg);
    if (password === null) return;
    try {
      const data = await API.post('/auth/register', {
        username: document.getElementById('reg-user').value.trim(),
        email: document.getElementById('reg-email').value.trim(),
        full_name: document.getElementById('reg-name').value.trim(),
        password,
        language: I18N.lang,   // new accounts start with the language currently in use
      });
      authForm(t('auth.create_account'), `${alertHtml(data.message, 'success')}${authFooter(loginLink())}`);
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('auth.register_failed')); }
  });
});

// ---------------------------------------------------------------------------
// VIEW: Forgot password / Reset password
// ---------------------------------------------------------------------------
register('forgot', function() {
  const msg = authForm(t('auth.forgot_title'), `
    <p class="text-muted" style="font-size:13px">${esc(t('auth.forgot_intro'))}</p>
    <div class="form-field"><label>${esc(t('auth.email'))}</label><input type="email" id="forgot-email" autocomplete="email"></div>
    <button class="btn btn-primary" id="forgot-btn" style="width:100%;margin-top:8px">${esc(t('auth.send_link'))}</button>
    ${authFooter(loginLink())}`);

  const send = async () => {
    try {
      const r = await API.post('/auth/password/forgot', { email: document.getElementById('forgot-email').value.trim() });
      authForm(t('auth.forgot_title'), `${alertHtml(r.message, 'success')}${authFooter(loginLink())}`);
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
  };
  document.getElementById('forgot-btn').addEventListener('click', send);
  onEnter('forgot-email', send);
});

register('reset', function(rawToken) {
  const token = takeToken('reset', rawToken);
  if (!token) { navigate('forgot'); return; }
  const msg = authForm(t('auth.reset_title'), `
    ${newPasswordFields('reset')}
    <button class="btn btn-primary" id="reset-btn" style="width:100%;margin-top:8px">${esc(t('profile.update_password'))}</button>`);

  document.getElementById('reset-btn').addEventListener('click', async () => {
    const password = readNewPassword('reset', msg);
    if (password === null) return;
    try {
      const r = await API.post('/auth/password/reset', { token, password });
      currentUser = null;   // every session was revoked
      renderHeader();
      updateProfileLink();
      authForm(t('auth.reset_title'), `${alertHtml(r.message, 'success')}${authFooter(loginLink())}`);
    } catch (e) {
      msg.innerHTML = alertHtml(e.error || t('common.failed'));
      if (e.data?.code === 'token_invalid') msg.innerHTML += authFooter(`<a href="#/forgot">${esc(t('auth.forgot_link'))}</a>`);
    }
  });
});

// ---------------------------------------------------------------------------
// VIEW: Email confirmation links. Spent only on click (POST) — mail scanners prefetch GET links.
// ---------------------------------------------------------------------------
function tokenConfirmView(view, introKey, endpoint, onDone) {
  return function(rawToken) {
    const token = takeToken(view, rawToken);
    const title = t('auth.verify_title'), intro = t(introKey);
    const msg = authForm(title, token ? `
      <p class="text-muted" style="font-size:13px">${esc(intro)}</p>
      <button class="btn btn-primary" id="confirm-btn" style="width:100%;margin-top:8px">${esc(t('auth.confirm'))}</button>`
      : alertHtml(t('auth.link_invalid')));
    document.getElementById('confirm-btn')?.addEventListener('click', async () => {
      try {
        const r = await API.post(endpoint, { token });
        authForm(title, `${alertHtml(t('auth.email_confirmed'), 'success')}${authFooter(onDone(r))}`);
      } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
    });
  };
}

register('verify', tokenConfirmView('verify', 'auth.verify_intro', '/auth/verify', () => loginLink()));

register('confirm-email', tokenConfirmView('confirm-email', 'auth.confirm_email_intro', '/profile/email/confirm', r => {
    if (currentUser) currentUser.email = r.email;
    return currentUser ? `<a href="#/profile">${esc(t('nav.profile'))}</a>` : loginLink();
  }));

// ---------------------------------------------------------------------------
// 404
// ---------------------------------------------------------------------------
register('404', function() {
  setMain(`<div class="alert alert-warning">${t('app.not_found_html')}</div>`);
});

// ---------------------------------------------------------------------------
// Nation list (static)
// ---------------------------------------------------------------------------
// Nations are loaded from /api/nations during boot() into allNations (normalized, deduplicated)
