/* =====================================================================
   Warfighter Squad Builder — SPA (vanilla JS, hash router)
   ===================================================================== */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let currentUser = null;

const builderState = {
  squadId: null,       // null = new squad
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
  updateActiveNav(key);
  const handler = routes[key] || routes['404'];
  if (handler) handler(...rest);
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
      <span class="username">${esc(currentUser.username)}</span>
      <button class="btn btn-sm btn-ghost" id="logout-btn">${esc(t('header.logout'))}</button>`;
    nav.querySelector('#logout-btn').addEventListener('click', doLogout);
  } else {
    nav.innerHTML = `
      ${langSelect}
      <a href="#/login" class="btn btn-sm btn-ghost">${esc(t('header.login'))}</a>
      <a href="#/register" class="btn btn-sm btn-primary">${esc(t('header.register'))}</a>`;
  }
  nav.querySelector('#lang-select').addEventListener('change', e => changeLanguage(e.target.value));
}

function updateProfileLink() {
  const link = document.getElementById('nav-profile');
  if (link) link.style.display = currentUser ? '' : 'none';
  const trLink = document.getElementById('nav-translations');
  if (trLink) trLink.style.display = currentUser?.is_admin ? '' : 'none';
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

function cardImageAttr(card) {
  if (!card || !card.image_url) return '';
  return `data-card-image-url="${esc(card.image_url)}"`;
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
// Card Image Hover Tooltip
// ---------------------------------------------------------------------------
let thumbTimer = null;
let thumbVisible = false;
let lastMouse = { x: 0, y: 0 };
const thumb = document.getElementById('card-thumb');

function showThumb(url) {
  thumb.innerHTML = `<img src="${esc(url)}" alt="card">`;
  thumb.style.display = 'block';
  thumbVisible = true;
  positionThumb();
}

function hideThumb() {
  thumb.style.display = 'none';
  thumbVisible = false;
}

function positionThumb() {
  const { x, y } = lastMouse;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const w = 160 + 2;  // thumb width + border
  const h = 240;       // estimated height

  let left = x + 16;
  let top = y - h / 2;

  if (left + w > vw - 8) left = x - w - 8;
  if (top < 8) top = 8;
  if (top + h > vh - 8) top = vh - h - 8;

  thumb.style.left = left + 'px';
  thumb.style.top = top + 'px';
}

document.addEventListener('mousemove', e => {
  lastMouse = { x: e.clientX, y: e.clientY };
  if (thumbVisible) positionThumb();
});

document.addEventListener('mouseover', e => {
  const el = e.target.closest('[data-card-image-url]');
  clearTimeout(thumbTimer);
  if (!el || !el.dataset.cardImageUrl) { hideThumb(); return; }
  const url = el.dataset.cardImageUrl;
  thumbTimer = setTimeout(() => showThumb(url), 200);
});

document.addEventListener('mouseout', e => {
  const to = e.relatedTarget;
  if (!to || !to.closest('[data-card-image-url]')) {
    clearTimeout(thumbTimer);
    hideThumb();
  }
});

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
      <input type="text" id="q-input" placeholder="${esc(t('cards.search_placeholder'))}" value="${esc(cardFilters.q)}" style="min-width:200px;flex:1">
      <select id="cat-select">${catOptions}</select>
      <select id="nation-select">${nationOptions}</select>
      <select id="module-select">${moduleOptions}</select>
      <button class="btn btn-ghost btn-sm" id="reset-filters">${esc(t('common.reset'))}</button>
    </div>
    <div id="cards-count" style="font-size:12px;color:var(--text-muted);margin-bottom:8px"></div>
    <div id="cards-results"></div>
    <div id="cards-pagination"></div>
  `);

  const main = document.getElementById('app-main');
  let debounce;

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

  if (countDiv) countDiv.textContent = t('cards.showing', {
    from: fmtNumber(total === 0 ? 0 : (page-1)*cardFilters.per_page+1),
    to: fmtNumber(Math.min(page*cardFilters.per_page,total)),
    total: fmtNumber(total),
  });

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
let squadsActiveTab = 'community';  // 'my' | 'community'
let mySquadFilters = { q: '', sort: 'updated_at', order: 'desc', page: 1, myModules: false };
let communityFilters = { q: '', liked: false, sort: 'created_at', order: 'desc', page: 1, myModules: false };
// IDs of squads currently visible in the browser list (for prev/next navigation)
let squadNavList = [];

register('squads', async function(subId) {
  if (subId === 'new') { renderBuilder(null); return; }
  if (subId) { await showSquadDetail(parseInt(subId)); return; }
  // Default to 'my' tab when logged in, 'community' otherwise
  if (currentUser && squadsActiveTab !== 'my') squadsActiveTab = squadsActiveTab;
  if (!currentUser) squadsActiveTab = 'community';
  showSpinner();
  renderSquadsShell();
});

function renderSquadsShell() {
  const newBtn = currentUser
    ? `<button class="btn btn-primary" id="new-squad-btn">+ ${esc(t('squads.new'))}</button>` : '';
  const myTab = currentUser
    ? `<button class="tab-btn ${squadsActiveTab === 'my' ? 'active' : ''}" data-tab="my">${esc(t('squads.tab_my'))}</button>` : '';

  setMain(`
    <div class="flex justify-between items-center" style="margin-bottom:12px">
      <h1>${esc(t('squads.title'))}</h1>
      ${newBtn}
    </div>
    <div class="tabs" style="margin-bottom:16px">
      ${myTab}
      <button class="tab-btn ${squadsActiveTab === 'community' ? 'active' : ''}" data-tab="community">${esc(t('squads.tab_community'))}</button>
    </div>
    <div id="squads-tab-content"></div>
  `);

  const main = document.getElementById('app-main');
  main.querySelector('#new-squad-btn')?.addEventListener('click', () => navigate('builder'));
  main.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      squadsActiveTab = btn.dataset.tab;
      main.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === squadsActiveTab));
      loadSquadsTab();
    });
  });

  loadSquadsTab();
}

async function loadSquadsTab() {
  const contentDiv = document.getElementById('squads-tab-content');
  if (!contentDiv) return;
  contentDiv.innerHTML = '<div class="spinner" style="margin:24px auto"></div>';

  if (squadsActiveTab === 'my' && currentUser) {
    await renderMySquads(contentDiv);
  } else {
    await renderCommunitySquads(contentDiv);
  }
}

function _squadSortTh(label, col, f) {
  const active = f.sort === col;
  const arrow = active ? (f.order === 'asc' ? ' ▲' : ' ▼') : '';
  return `<th class="sort-header${active ? ' sort-active' : ''}" data-sort="${col}">${esc(label)}${arrow}</th>`;
}

async function renderMySquads(containerEl) {
  const f = mySquadFilters;
  const params = new URLSearchParams();
  params.set('user_id', currentUser.id);
  params.set('sort', f.sort);
  params.set('order', f.order);
  params.set('page', f.page);
  if (f.q) params.set('q', f.q);
  if (f.myModules) params.set('my_modules', 'true');

  let data;
  try { data = await API.get('/squads?' + params.toString()); }
  catch (e) { containerEl.innerHTML = `<div class="alert alert-error">${esc(e.error||t('common.failed'))}</div>`; return; }

  const { items, total, page, pages } = data;
  const rows = items.map(s => `
    <tr class="clickable" data-id="${s.id}">
      <td><strong>${esc(s.name)}</strong></td>
      <td>${esc(nationLabel(s.nation))}</td>
      <td>${s.mission ? `${esc(s.mission.name)} <span class="text-muted">· ${s.mission.resources} ${esc(t('stat.rp'))}</span>` : '—'}</td>
      <td>${s.rp_total}</td>
      <td>${s.likes_count} ♥</td>
      <td><span class="${s.status === 'draft' ? 'badge badge-draft' : 'badge badge-ok'}">${esc(tv('squad_status', s.status))}</span></td>
      <td class="text-muted">${fmtDate(s.updated_at)}</td>
    </tr>`).join('');

  const _myActive = document.activeElement;
  const hadFocus = _myActive?.id === 'my-q';
  const savedSel = hadFocus ? [_myActive.selectionStart, _myActive.selectionEnd] : null;
  containerEl.innerHTML = `
    <div class="filter-bar" style="margin-bottom:8px">
      <input type="text" id="my-q" placeholder="${esc(t('squads.search_placeholder'))}" value="${esc(f.q)}" style="flex:1;min-width:160px">
      <button class="quick-filter ${f.myModules ? 'active-accent' : ''}" id="my-modules-filter-my">${esc(t('squads.my_modules'))}</button>
    </div>
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">${esc(tn('squads.count', total))}</div>
    <table class="data-table">
      <thead><tr>
        ${_squadSortTh(t('col.name'), 'name', f)}
        ${_squadSortTh(t('col.nation'), 'nation', f)}
        ${_squadSortTh(t('col.mission'), 'mission_name', f)}
        ${_squadSortTh(t('col.team_rp'), 'rp_total', f)}
        ${_squadSortTh(t('col.likes'), 'likes_count', f)}
        <th>${esc(t('col.status'))}</th>
        ${_squadSortTh(t('col.updated'), 'updated_at', f)}
      </tr></thead>
      <tbody>${rows||`<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">${esc(t('squads.none_mine'))}</td></tr>`}</tbody>
    </table>
    ${paginationHtml(page, pages)}`;

  const qInput = containerEl.querySelector('#my-q');
  if (qInput) {
    if (hadFocus) { qInput.focus(); if (savedSel) qInput.setSelectionRange(savedSel[0], savedSel[1]); }
    qInput.addEventListener('input', e => {
      clearTimeout(qInput._t);
      qInput._t = setTimeout(() => { f.q = e.target.value; f.page = 1; renderMySquads(containerEl); }, 300);
    });
  }
  containerEl.querySelector('#my-modules-filter-my')?.addEventListener('click', () => {
    f.myModules = !f.myModules; f.page = 1; renderMySquads(containerEl);
  });
  containerEl.querySelectorAll('th.sort-header[data-sort]').forEach(th =>
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      if (f.sort === col) f.order = f.order === 'asc' ? 'desc' : 'asc';
      else { f.sort = col; f.order = ['name', 'nation', 'mission_name'].includes(col) ? 'asc' : 'desc'; }
      f.page = 1; renderMySquads(containerEl);
    })
  );
  squadNavList = items.map(s => s.id);
  containerEl.querySelectorAll('tr[data-id]').forEach(row =>
    row.addEventListener('click', () => navigate('squads/' + row.dataset.id)));
  containerEl.querySelectorAll('[data-pg]').forEach(btn =>
    btn.addEventListener('click', () => { f.page = parseInt(btn.dataset.pg); renderMySquads(containerEl); }));
}

async function renderCommunitySquads(containerEl) {
  const f = communityFilters;
  const params = new URLSearchParams();
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
  const likedBtn = currentUser ? `
    <button class="quick-filter ${f.liked ? 'active' : ''}" id="liked-filter">♥ ${esc(t('squads.liked_by_me'))}</button>` : '';
  const myModulesBtn = currentUser ? `
    <button class="quick-filter ${f.myModules ? 'active-accent' : ''}" id="my-modules-filter-comm">${esc(t('squads.my_modules'))}</button>` : '';

  const rows = items.map(s => `
    <tr class="clickable" data-id="${s.id}">
      <td><strong>${esc(s.name)}</strong></td>
      <td>${esc(nationLabel(s.nation))}</td>
      <td>${s.mission ? `${esc(s.mission.name)} <span class="text-muted">· ${s.mission.resources} ${esc(t('stat.rp'))}</span>` : '—'}</td>
      <td>${s.rp_total}</td>
      <td>${s.likes_count} ♥</td>
      <td>${esc(s.owner ? s.owner.username : '—')}</td>
      <td class="text-muted">${fmtDate(s.created_at)}</td>
    </tr>`).join('');

  const _commActive = document.activeElement;
  const hadFocus = _commActive?.id === 'comm-q';
  const savedSel = hadFocus ? [_commActive.selectionStart, _commActive.selectionEnd] : null;
  containerEl.innerHTML = `
    <div class="filter-bar" style="margin-bottom:8px">
      <input type="text" id="comm-q" placeholder="${esc(t('squads.search_placeholder'))}" value="${esc(f.q)}" style="flex:1;min-width:160px">
      ${likedBtn}
      ${myModulesBtn}
    </div>
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">${esc(tn('squads.published_count', total))}</div>
    <table class="data-table">
      <thead><tr>
        ${_squadSortTh(t('col.name'), 'name', f)}
        ${_squadSortTh(t('col.nation'), 'nation', f)}
        ${_squadSortTh(t('col.mission'), 'mission_name', f)}
        ${_squadSortTh(t('col.team_rp'), 'rp_total', f)}
        ${_squadSortTh(t('col.likes'), 'likes_count', f)}
        <th>${esc(t('col.owner'))}</th>
        ${_squadSortTh(t('col.date'), 'created_at', f)}
      </tr></thead>
      <tbody>${rows||`<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">${esc(t('squads.none_published'))}</td></tr>`}</tbody>
    </table>
    ${paginationHtml(page, pages)}`;

  const qInput = containerEl.querySelector('#comm-q');
  if (qInput) {
    if (hadFocus) { qInput.focus(); if (savedSel) qInput.setSelectionRange(savedSel[0], savedSel[1]); }
    qInput.addEventListener('input', e => {
      clearTimeout(qInput._t);
      qInput._t = setTimeout(() => { f.q = e.target.value; f.page = 1; renderCommunitySquads(containerEl); }, 300);
    });
  }
  containerEl.querySelector('#liked-filter')?.addEventListener('click', () => {
    f.liked = !f.liked; f.page = 1; renderCommunitySquads(containerEl);
  });
  containerEl.querySelector('#my-modules-filter-comm')?.addEventListener('click', () => {
    f.myModules = !f.myModules; f.page = 1; renderCommunitySquads(containerEl);
  });
  containerEl.querySelectorAll('th.sort-header[data-sort]').forEach(th =>
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      if (f.sort === col) f.order = f.order === 'asc' ? 'desc' : 'asc';
      else { f.sort = col; f.order = ['name', 'nation', 'mission_name'].includes(col) ? 'asc' : 'desc'; }
      f.page = 1; renderCommunitySquads(containerEl);
    })
  );
  squadNavList = items.map(s => s.id);
  containerEl.querySelectorAll('tr[data-id]').forEach(row =>
    row.addEventListener('click', () => navigate('squads/' + row.dataset.id)));
  containerEl.querySelectorAll('[data-pg]').forEach(btn =>
    btn.addEventListener('click', () => { f.page = parseInt(btn.dataset.pg); renderCommunitySquads(containerEl); }));
}

// ---------------------------------------------------------------------------
// VIEW: Squad Detail
// ---------------------------------------------------------------------------
async function showSquadDetail(squadId) {
  showSpinner();
  let squad, comments;
  try {
    const r = await API.get('/squads/' + squadId);
    squad = r.squad;
    const cr = await API.get('/squads/' + squadId + '/comments');
    comments = cr.items;
  } catch (e) {
    showError(e.error || t('squad.not_found'));
    return;
  }

  const isOwner = currentUser && currentUser.id === squad.owner.id;
  const isDraft = squad.status === 'draft';
  const editBtn = isOwner ? `<button class="btn btn-sm btn-ghost" id="edit-squad-btn">${esc(t('common.edit'))}</button>` : '';
  const deleteBtn = isOwner ? `<button class="btn btn-sm btn-danger" id="delete-squad-btn">${esc(t('common.delete'))}</button>` : '';
  const publishBtn = isOwner && isDraft ? `<button class="btn btn-sm btn-primary" id="publish-btn">${esc(t('squad.publish'))}</button>` : '';
  const draftBadge = isDraft ? `<span class="badge-draft">${esc(t('squad.draft_badge'))}</span>` : '';

  const likedClass = squad.liked_by_me ? 'liked' : '';
  const likeDisabled = !currentUser ? `disabled title="${esc(t('squad.login_to_like'))}"` : '';
  const likeBtn = `
    <button class="like-btn ${likedClass}" id="like-btn" ${likeDisabled}>
      ♥ <span id="likes-count">${squad.likes_count}</span>
    </button>`;

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
        <div class="comment-body">${esc(cm.body)}</div>
        ${canEdit ? `
          <div class="comment-actions">
            <button class="btn btn-sm btn-ghost edit-comment-btn" data-cid="${cm.id}">${esc(t('common.edit'))}</button>
            <button class="btn btn-sm btn-danger delete-comment-btn" data-cid="${cm.id}">${esc(t('common.delete'))}</button>
          </div>` : ''}
      </div>`;
  }).join('');

  const commentForm = currentUser ? `
    <div class="comment-form">
      <textarea id="comment-input" placeholder="${esc(t('comments.placeholder'))}" rows="3"></textarea>
      <div class="form-row">
        <button class="btn btn-primary" id="post-comment-btn">${esc(t('comments.post'))}</button>
      </div>
    </div>` : `<p class="text-muted mt-2">${t('comments.login_html')}</p>`;

  // Build prev/next navigation from the current squad browser list
  const squadNavIdx = squadNavList.indexOf(squad.id);
  const prevSqId = squadNavIdx > 0 ? squadNavList[squadNavIdx - 1] : null;
  const nextSqId = squadNavIdx >= 0 && squadNavIdx < squadNavList.length - 1 ? squadNavList[squadNavIdx + 1] : null;
  const prevSqBtn = prevSqId ? `<a href="#/squads/${prevSqId}" class="btn btn-ghost btn-sm">← ${esc(t('common.prev'))}</a>` : `<span class="btn btn-ghost btn-sm" style="opacity:.35;cursor:default">← ${esc(t('common.prev'))}</span>`;
  const nextSqBtn = nextSqId ? `<a href="#/squads/${nextSqId}" class="btn btn-ghost btn-sm">${esc(t('common.next'))} →</a>` : `<span class="btn btn-ghost btn-sm" style="opacity:.35;cursor:default">${esc(t('common.next'))} →</span>`;
  const squadNavPos = squadNavIdx >= 0 ? `<span class="text-muted" style="font-size:12px">${squadNavIdx + 1} / ${squadNavList.length}</span>` : '';

  setMain(`
    <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <a href="#/squads" class="btn btn-ghost btn-sm">← ${esc(t('nav.squads'))}</a>
      ${editBtn} ${deleteBtn} ${publishBtn}
      <span style="flex:1"></span>
      ${squadNavPos}
      ${prevSqBtn}
      ${nextSqBtn}
    </div>

    <div class="squad-header">
      <div class="squad-title">${draftBadge} ${esc(squad.name)}</div>
      <div class="squad-meta">
        ${esc(t('squad.by', { user: squad.owner.username }))} · ${fmtDate(squad.created_at)} · ${esc(nationLabel(squad.nation))}
      </div>
      <div style="margin-top:8px">${likeBtn}</div>
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
              <span ${cardImageAttr(m)}>${esc(m.name)}</span>
              ${m.nation ? `<span class="chip chip-mission" style="margin-left:6px;vertical-align:middle">${esc(tv('nation', m.nation))}</span>` : ''}
            </div>
            <div class="mission-meta-row">
              ${m.mission_type && m.mission_type !== 'Standard' ? `<span class="obj-type-badge" style="background:${mtColor}">${esc(tv('card_subtype', m.mission_type))}</span>` : ''}
              ${isFortified ? `<span class="obj-type-badge" style="background:#7f1d1d">${esc(tv('card_subtype', 'Fortification'))}</span>` : ''}
              ${m.theater ? `<span class="text-muted" style="font-size:12px">${esc(tv('theater', m.theater))}</span>` : ''}
            </div>
            ${m.module ? `<div class="mission-subtitle">${esc(tv('module', m.module))}</div>` : ''}
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
                ${o.objective_mechanic ? `<span class="obj-type-badge" style="background:${typeColor}">${esc(tv('card_subtype', o.objective_mechanic))}</span>` : ''}
                ${familyColor ? `<span class="obj-type-badge" style="background:${familyColor}">${esc(tv('card_subtype', o.objective_family))}</span>` : ''}
                <span ${cardImageAttr(o)}>${esc(o.name)}</span>
                ${o.nation ? `<span class="chip chip-mission" style="margin-left:6px;vertical-align:middle">${esc(tv('nation', o.nation))}</span>` : ''}
              </div>
              ${o.module ? `<div class="mission-subtitle">${esc(tv('module', o.module))}</div>` : ''}
              ${chips ? `<div class="mission-attrs" style="margin-top:8px">${chips}</div>` : ''}`;
            } else {
              // Compact row — name + tiny badges only
              return `<div class="flex items-center obj-compact-row" style="${idx > 0 ? 'margin-top:6px;padding-top:6px;border-top:1px solid var(--border)' : ''}">
                <span style="font-size:13px"><span ${cardImageAttr(o)}>${esc(o.name)}</span></span>
                ${o.objective_mechanic ? `<span class="obj-type-badge" style="background:${typeColor};margin-left:6px;font-size:10px;padding:1px 5px">${esc(tv('card_subtype', o.objective_mechanic))}</span>` : ''}
              </div>`;
            }
          }).join('');
          return objsHtml + situationHtml;
        })()}
      </div>
    </div>

    ${(() => {
      // Collect modules from soldiers + all gear (not mission/objectives)
      const modSet = new Set();
      for (const ss of squad.soldiers) {
        if (ss.card?.module) modSet.add(ss.card.module);
        // Only explicitly added gear — default_gear is intrinsic to the soldier card
        for (const g of (ss.gear || [])) {
          if (g.card?.module) modSet.add(g.card.module);
        }
      }
      if (!modSet.size) return '';
      // Core Europe first, rest alphabetical
      const sorted = [
        ...[...modSet].filter(m => m === 'Core Europe'),
        ...[...modSet].filter(m => m !== 'Core Europe').sort(),
      ];
      return `<div class="required-modules">
        <span class="required-modules-label">${esc(t('squad.required_modules'))}</span>
        ${sorted.map(m => `<span class="chip">${esc(tv('module', m))}</span>`).join('')}
      </div>`;
    })()}

    <h2 style="margin-bottom:12px">${esc(t('squad.soldiers'))}</h2>
    <div class="soldiers-grid">${soldiersHtml || `<p class="text-muted">${esc(t('squad.no_soldiers'))}</p>`}</div>

    <div class="squad-author-notes">
      <h2 style="margin-bottom:8px">${esc(t('squad.strategy_notes'))}</h2>
      ${squad.notes
        ? `<div class="card-notes">${esc(squad.notes)}</div>`
        : `<p class="text-muted" style="font-size:13px;margin:0">${esc(t('squad.no_notes'))}</p>`}
    </div>

    <div class="comments-section">
      <h2 style="margin-bottom:10px">${esc(t('comments.title', { n: comments.length }))}</h2>
      <div id="comments-list">${commentsHtml || `<p class="text-muted">${esc(t('comments.none'))}</p>`}</div>
      ${commentForm}
    </div>
  `);

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
      document.getElementById('likes-count').textContent = res.likes_count;
    } catch (e) { /* silent */ }
  });

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
      const oldText = bodyEl.textContent;
      const ta = document.createElement('textarea');
      ta.value = oldText;
      ta.rows = 3;
      ta.style.width = '100%';
      bodyEl.replaceWith(ta);
      editBtn.textContent = t('common.save');
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
register('builder', async function(squadId) {
  if (squadId) {
    // Load existing squad
    showSpinner();
    try {
      const data = await API.get('/squads/' + squadId);
      const sq = data.squad;
      builderState.squadId = sq.id;
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
    // Fresh builder — always reset when navigating to #/builder without an ID
    resetBuilderState();
  }
  builderState.pickerMode = null;
  renderBuilder();
});

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
        <button class="btn btn-icon remove-gear-btn" data-sidx="${idx}" data-gidx="${gi}" title="${esc(t('common.remove'))}">✕</button>
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
            <button class="btn btn-icon remove-soldier-btn" data-sidx="${idx}" title="${esc(t('builder.remove_soldier'))}">✕</button>
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
            <button class="btn btn-sm btn-ghost add-weapon-btn" data-sidx="${idx}">+ ${esc(tv('card_type', 'Weapon'))}</button>
            <button class="btn btn-sm btn-ghost add-equip-btn" data-sidx="${idx}">+ ${esc(tv('card_type', 'Equipment'))}</button>
            <button class="btn btn-sm btn-ghost add-skill-btn" data-sidx="${idx}">+ ${esc(tv('card_type', 'Skill'))}</button>
            <button class="btn btn-sm btn-ghost add-sr-btn" data-sidx="${idx}">+ ${esc(tv('card_type', 'Service Record'))}</button>
          </div>
        ` : (c.card_subtype === 'NPS' || c.card_subtype === 'Squad') ? `
          ${defaultGearHtml}
        ` : c.card_subtype !== 'Vehicle' ? `
          <div class="gear-list">${gearItems}</div>
          <div class="nps-gear-note" style="font-size:11px;margin-top:4px">${esc(t('builder.nps_not_counted'))}</div>
          ${defaultGearHtml}
          <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
            <button class="btn btn-sm btn-ghost add-nps-wpn-btn" data-sidx="${idx}">+ ${esc(tv('card_type', 'Weapon'))}</button>
            <button class="btn btn-sm btn-ghost add-nps-eqp-btn" data-sidx="${idx}">+ ${esc(tv('card_type', 'Equipment'))}</button>
            <button class="btn btn-sm btn-ghost add-nps-skl-btn" data-sidx="${idx}">+ ${esc(tv('card_type', 'Skill'))}</button>
            <button class="btn btn-sm btn-ghost add-nps-act-btn" data-sidx="${idx}">+ ${esc(tv('card_type', 'Action'))}</button>
          </div>
        ` : ''}
      </div>`;
  }).join('');

  setMain(`
    <div class="builder-actions">
      <button class="btn btn-ghost btn-sm" id="save-draft-btn">${esc(t('builder.save_draft'))}</button>
      <button class="btn btn-primary" id="publish-squad-btn">${esc(t('squad.publish'))}</button>
      <button class="btn btn-ghost btn-sm" id="validate-btn">${esc(t('builder.validate'))}</button>
      ${builderState.squadId ? `<a href="#/squads/${builderState.squadId}" class="btn btn-ghost btn-sm">${esc(t('common.cancel'))}</a>` : ''}
    </div>
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
                    <span ${cardImageAttr(mc)}><strong>${esc(mc.name)}</strong></span>
                  </span>
                  <button class="btn btn-sm btn-ghost" id="change-mission-btn">${esc(t('common.change'))}</button>
                </div>
                <div class="text-muted" style="font-size:12px;margin-top:4px">${esc([
                  mc.resources != null ? `${mc.resources} ${t('stat.rp')}` : null,
                  mc.time != null ? `${mc.time} ${t('stat.turns')}` : null,
                  mc.objective_position != null ? `${t('stat.obj_loc_short')}: ${mc.objective_position}` : null,
                  mc.loadout_modifier != null ? `${t('stat.loadout')}: ${mc.loadout_modifier >= 0 ? '+' : ''}${mc.loadout_modifier}` : null,
                ].filter(Boolean).join(' · '))}</div>`;
              })()
            : `<button class="btn btn-ghost" id="pick-mission-btn">${esc(t('builder.select_mission'))}</button>`}
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
                        <button class="btn btn-sm btn-ghost remove-obj-btn" data-idx="${idx}" title="${esc(t('common.remove'))}" style="color:var(--text-muted)">✕</button>
                      </span>
                    </div>
                    <div class="text-muted" style="font-size:11px;margin-top:3px">${esc([subtypeLabel, attrs].filter(Boolean).join(' · '))}</div>`;
                  } else {
                    return `<div class="flex justify-between items-center obj-compact-row">
                      <span style="font-size:13px"><span ${cardImageAttr(oc)}>${esc(oc.name)}</span></span>
                      <button class="btn btn-sm btn-ghost remove-obj-btn" data-idx="${idx}" title="${esc(t('common.remove'))}" style="color:var(--text-muted)">✕</button>
                    </div>`;
                  }
                }).join('');
                const addMoreBtn = builderState.missionCard
                  ? `<button class="btn btn-ghost btn-sm" id="add-obj-btn" style="margin-top:6px">+ ${esc(t('builder.add_another'))}</button>`
                  : '';
                return rows + addMoreBtn;
              })()
            : builderState.missionCard
              ? `<button class="btn btn-ghost" id="pick-obj-btn">${esc(t('builder.add_objective'))}</button>`
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
            ? `<button class="btn btn-ghost" id="add-soldier-btn" ${!builderState.nation ? `disabled title="${esc(t('builder.nation_first'))}"` : ''}>+ ${esc(t('builder.add_soldier'))}</button>`
            : ''}
        </div>

        <div class="builder-section">
          <div class="builder-section-title">${esc(t('squad.strategy_notes'))}</div>
          <div class="text-muted" style="font-size:12px;margin-bottom:6px">${esc(t('builder.notes_hint'))}</div>
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
  main.querySelector('#nation-select')?.addEventListener('change', e => {
    builderState.nation = e.target.value;
    builderState.soldiers = [];
    renderBuilder();
  });
  main.querySelector('#pick-mission-btn')?.addEventListener('click', () => { setPickerMode('mission'); renderBuilder(); });
  main.querySelector('#change-mission-btn')?.addEventListener('click', () => { setPickerMode('mission'); renderBuilder(); });
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
      <input type="text" id="picker-q" placeholder="${esc(t('common.search'))}" value="${esc(builderState.pickerQ)}" style="flex:1;min-width:120px">
      <select id="picker-module-select">${moduleOptions}</select>
    </div>`;
}

async function loadPickerResults() {
  const params = new URLSearchParams();
  params.set('per_page', '100');
  params.set('sort', builderState.pickerSort);
  params.set('order', builderState.pickerOrder);

  switch (builderState.pickerMode) {
    case 'mission':   params.set('category', 'Mission'); break;
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
    squadId: null, name: '', missionCard: null, objectiveCards: [],
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

  const moduleItems = profile.modules.map(m => `
    <label class="module-item">
      <input type="checkbox" name="module" value="${esc(m.module)}" ${m.owned ? 'checked' : ''}>
      ${esc(tv('module', m.module))}
    </label>`).join('');

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
      <div class="form-field"><label>${esc(t('profile.current_password'))}</label><input type="password" id="cur-pw"></div>
      <div class="form-field"><label>${esc(t('profile.new_password'))}</label><input type="password" id="new-pw"></div>
      <button class="btn btn-primary" id="save-pw-btn">${esc(t('profile.update_password'))}</button>
      <div id="pw-msg"></div>
    </div>

    <div class="profile-section">
      <h2>${esc(t('profile.owned_modules'))}</h2>
      <div class="module-actions">
        <button class="btn btn-sm btn-ghost" id="select-all-btn">${esc(t('profile.select_all'))}</button>
        <button class="btn btn-sm btn-ghost" id="deselect-all-btn">${esc(t('profile.deselect_all'))}</button>
      </div>
      <div class="module-list">${moduleItems}</div>
      <button class="btn btn-primary mt-2" id="save-modules-btn">${esc(t('profile.save_modules'))}</button>
      <div id="modules-msg"></div>
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
    const np = main.querySelector('#new-pw').value;
    const msg = main.querySelector('#pw-msg');
    try {
      await API.put('/profile/password', { current_password: cp, new_password: np });
      msg.innerHTML = alertHtml(t('profile.password_updated'), 'success');
      main.querySelector('#cur-pw').value = '';
      main.querySelector('#new-pw').value = '';
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
  });

  main.querySelector('#select-all-btn')?.addEventListener('click', () => {
    main.querySelectorAll('.module-list input[type=checkbox]').forEach(cb => cb.checked = true);
  });
  main.querySelector('#deselect-all-btn')?.addEventListener('click', () => {
    main.querySelectorAll('.module-list input[type=checkbox]').forEach(cb => cb.checked = false);
  });

  main.querySelector('#save-modules-btn')?.addEventListener('click', async () => {
    const owned = [...main.querySelectorAll('.module-list input[type=checkbox]:checked')].map(cb => cb.value);
    const msg = main.querySelector('#modules-msg');
    try {
      await API.put('/profile/modules', { owned_modules: owned });
      msg.innerHTML = alertHtml(tn('profile.modules_saved', owned.length), 'success');
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
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
      <input type="text" id="tr-q" placeholder="${esc(t('tr.search_placeholder'))}" value="${esc(f.q)}" style="flex:1;min-width:180px">
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
// VIEW: Login
// ---------------------------------------------------------------------------
register('login', function() {
  setMain(`
    <div class="auth-form-wrapper">
      <h1>${esc(t('header.login'))}</h1>
      <div id="login-msg"></div>
      <div class="form-field"><label>${esc(t('auth.username'))}</label><input type="text" id="login-user" autocomplete="username"></div>
      <div class="form-field"><label>${esc(t('auth.password'))}</label><input type="password" id="login-pw" autocomplete="current-password"></div>
      <button class="btn btn-primary" id="login-btn" style="width:100%;margin-top:8px">${esc(t('header.login'))}</button>
      <div class="auth-form-footer mt-2" style="text-align:center;font-size:13px">
        ${esc(t('auth.no_account'))} <a href="#/register">${esc(t('header.register'))}</a>
      </div>
    </div>`);

  const doLogin = async () => {
    const username = document.getElementById('login-user').value.trim();
    const password = document.getElementById('login-pw').value;
    const msg = document.getElementById('login-msg');
    try {
      const data = await API.post('/auth/login', { username, password });
      currentUser = data.user;
      await applyUserLanguage();
      renderHeader();
      updateProfileLink();
      navigate('squads');
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('auth.login_failed')); }
  };

  document.getElementById('login-btn').addEventListener('click', doLogin);
  document.getElementById('login-pw').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
});

// ---------------------------------------------------------------------------
// VIEW: Register
// ---------------------------------------------------------------------------
register('register', function() {
  setMain(`
    <div class="auth-form-wrapper">
      <h1>${esc(t('auth.create_account'))}</h1>
      <div id="reg-msg"></div>
      <div class="form-field"><label>${esc(t('auth.username'))}</label><input type="text" id="reg-user" autocomplete="username"></div>
      <div class="form-field"><label>${esc(t('auth.email'))}</label><input type="email" id="reg-email" autocomplete="email"></div>
      <div class="form-field"><label>${esc(t('auth.full_name'))} <span class="text-muted">(${esc(t('common.optional'))})</span></label><input type="text" id="reg-name"></div>
      <div class="form-field"><label>${esc(t('auth.password'))}</label><input type="password" id="reg-pw" autocomplete="new-password"></div>
      <button class="btn btn-primary" id="reg-btn" style="width:100%;margin-top:8px">${esc(t('auth.create_account'))}</button>
      <div class="auth-form-footer mt-2" style="text-align:center;font-size:13px">
        ${esc(t('auth.have_account'))} <a href="#/login">${esc(t('header.login'))}</a>
      </div>
    </div>`);

  document.getElementById('reg-btn').addEventListener('click', async () => {
    const msg = document.getElementById('reg-msg');
    try {
      const data = await API.post('/auth/register', {
        username: document.getElementById('reg-user').value.trim(),
        email: document.getElementById('reg-email').value.trim(),
        full_name: document.getElementById('reg-name').value.trim(),
        password: document.getElementById('reg-pw').value,
      });
      // New accounts start with the language currently in use
      try { await API.put('/profile/', { language: I18N.lang }); data.user.language = I18N.lang; } catch (_) {}
      currentUser = data.user;
      renderHeader();
      updateProfileLink();
      navigate('profile');
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('auth.register_failed')); }
  });
});

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
