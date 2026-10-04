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
  objectiveCard: null,
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
  renderHeader();
  updateProfileLink();
  route();
}

function renderHeader() {
  const nav = document.getElementById('header-auth');
  if (currentUser) {
    nav.innerHTML = `
      <span class="username">${esc(currentUser.username)}</span>
      <button class="btn btn-sm btn-ghost" id="logout-btn">Logout</button>`;
    nav.querySelector('#logout-btn').addEventListener('click', doLogout);
  } else {
    nav.innerHTML = `
      <a href="#/login" class="btn btn-sm btn-ghost">Login</a>
      <a href="#/register" class="btn btn-sm btn-primary">Register</a>`;
  }
}

function updateProfileLink() {
  const link = document.getElementById('nav-profile');
  if (link) link.style.display = currentUser ? '' : 'none';
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
    Hostile: 'chip-hostile',
  };
  return `<span class="chip ${map[cat] || ''}">${esc(cat)}</span>`;
}

function chipForSubtype(subtype) {
  if (subtype === 'Player') return `<span class="chip chip-ps">PS</span>`;
  if (subtype === 'NPS') return `<span class="chip chip-nps">NPS</span>`;
  return subtype ? `<span class="chip">${esc(subtype)}</span>` : '';
}

function fmtDate(iso) {
  if (!iso) return '';
  return iso.slice(0, 10);
}

function cardImageAttr(card) {
  if (!card || !card.image_url) return '';
  return `data-card-image-url="${esc(card.image_url)}"`;
}

function paginationHtml(page, pages, onNav) {
  if (pages <= 1) return '';
  return `
    <div class="pagination">
      <button class="btn btn-sm btn-ghost" ${page <= 1 ? 'disabled' : ''} data-pg="${page - 1}">◀ Prev</button>
      <span class="page-info">Page ${page} of ${pages}</span>
      <button class="btn btn-sm btn-ghost" ${page >= pages ? 'disabled' : ''} data-pg="${page + 1}">Next ▶</button>
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
    <button class="lightbox-close" title="Close">✕</button>`;
  overlay.addEventListener('click', e => {
    if (e.target === overlay || e.target.classList.contains('lightbox-close')) overlay.remove();
  });
  document.body.appendChild(overlay);
}

// ---------------------------------------------------------------------------
// VIEW: Cards Browser
// ---------------------------------------------------------------------------
let cardFilters = { q: '', category: '', subtype: '', nation: '', module: '', sort: 'module', order: 'asc', page: 1, per_page: 50 };
let allNations = [];
let allModules = [];
let allCategories = ['Soldier','Weapon','Equipment','Skill','Service Record','Mission',
  'Objective','Situation','Hostile','Action','Event','Location','Fortification','Other'];

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
    `<option value="${esc(c)}" ${cardFilters.category === c ? 'selected' : ''}>${c || 'All categories'}</option>`
  ).join('');
  const nationOptions = ['', ...allNations].map(n =>
    `<option value="${esc(n)}" ${cardFilters.nation === n ? 'selected' : ''}>${n || 'All nations'}</option>`
  ).join('');
  const moduleOptions = ['', ...allModules].map(m =>
    `<option value="${esc(m)}" ${cardFilters.module === m ? 'selected' : ''}>${m || 'All modules'}</option>`
  ).join('');

  setMain(`
    <h1 style="margin-bottom:16px">Cards</h1>
    <div class="filter-bar" style="flex-wrap:wrap;gap:6px">
      <input type="text" id="q-input" placeholder="Search name / notes…" value="${esc(cardFilters.q)}" style="min-width:200px;flex:1">
      <select id="cat-select">${catOptions}</select>
      <select id="nation-select">${nationOptions}</select>
      <select id="module-select">${moduleOptions}</select>
      <button class="btn btn-ghost btn-sm" id="reset-filters">Reset</button>
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
    resultsDiv.innerHTML = `<div class="alert alert-error">${esc(e.error || 'Failed to load cards.')}</div>`;
    return;
  }

  const { items, total, page, pages } = data;
  const s = cardFilters.sort, o = cardFilters.order;

  if (countDiv) countDiv.textContent =
    `Showing ${total === 0 ? 0 : (page-1)*cardFilters.per_page+1}–${Math.min(page*cardFilters.per_page,total)} of ${total}`;

  const rows = items.map(c => `
    <tr class="clickable" data-id="${c.id}">
      <td><span class="text-muted" style="font-size:11px">${esc(c.number)}</span></td>
      <td><span ${cardImageAttr(c)}>${esc(c.name)}</span></td>
      <td>${chipForCategory(c.card_category)}</td>
      <td>${esc(c.card_subtype || '')}</td>
      <td>${esc(c.nation || '—')}</td>
      <td>${esc(c.module)}</td>
      <td style="text-align:right">${c.resource_cost != null ? c.resource_cost : ''}</td>
    </tr>`).join('');

  resultsDiv.innerHTML = `
    <div class="table-scroll">
    <table class="data-table">
      <thead>
        <tr>
          ${thSort('#','number',s,o)}
          ${thSort('Name','name',s,o)}
          <th>Category</th><th>Subtype</th>
          ${thSort('Nation','nation',s,o)}
          ${thSort('Module','module',s,o)}
          ${thSort('RP','resource_cost',s,o)}
        </tr>
      </thead>
      <tbody>${rows || '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">No cards found.</td></tr>'}</tbody>
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
    showError(e.error || 'Card not found.');
    return;
  }

  const stats = [
    ['RP Cost', card.resource_cost],
    ['Health', card.health],
    ['Movement', card.movement],
    ['Cover', card.cover],
    ['Loadout', card.loadout],
    ['HtH', card.hth != null ? (card.hth >= 0 ? '+' : '') + card.hth : null],
    ['Actions', card.actions],
    ['Budget (RP)', card.resources],
    ['Turns', card.time],
    ['Obj. at #', card.objective_location],
    ['Loadout Mod', card.loadout_modifier != null ? (card.loadout_modifier >= 0 ? '+' : '') + card.loadout_modifier : null],
    ['Entrance Cost', card.entrance_cost],
    ['HtH Cost', card.action_cost_hth],
    ['Reinforcements', card.reinforcements],
    ['XP Value', card.xp_value],
    ['Count', card.hostile_count],
    ['Noise', card.noise],
    ['Support Cost', card.support_cost],
    ['Covert Cost', card.covert_cost],
    ['Gain', card.gain],
    ['Loss', card.loss],
  ].filter(([, v]) => v != null && v !== '');

  const statItems = stats.map(([label, val]) => `
    <div class="stat-item">
      <div class="stat-label">${esc(label)}</div>
      <div class="stat-value">${esc(String(val))}</div>
    </div>`).join('');

  const imagePanel = card.image_url
    ? `<div class="card-image-panel">
        <img src="${esc(card.image_url)}" alt="${esc(card.name)}" class="card-full-img">
       </div>`
    : `<div class="card-image-panel">
        <div class="card-image-placeholder"></div>
       </div>`;

  const addBtn = builderState.missionCard
    ? `<button class="btn btn-primary mt-2" id="add-to-build">+ Add to current build</button>` : '';

  setMain(`
    <div style="margin-bottom:12px">
      <a href="#/cards" class="btn btn-ghost btn-sm">← Back to Cards</a>
    </div>
    <div class="card-detail-layout">
      ${imagePanel}
      <div class="card-stats-panel">
        <div class="card-header-bar">
          ${esc(card.number)} · ${chipForCategory(card.card_category)} ${chipForSubtype(card.card_subtype)}
          ${card.nation ? `· <span class="chip">${esc(card.nation)}</span>` : ''}
          · <span class="text-muted" style="font-size:12px">${esc(card.module)}</span>
        </div>
        <div class="card-name">${esc(card.name)}</div>
        <div class="stat-grid">${statItems || '<span class="text-muted">No numeric stats.</span>'}</div>
        ${card.notes ? `<div class="card-notes">${esc(card.notes)}</div>` : ''}
        ${addBtn}
      </div>
    </div>
  `);

  const imgEl = document.querySelector('.card-full-img');
  if (imgEl) imgEl.addEventListener('click', () => openLightbox(card.image_url));

  const addBtn2 = document.getElementById('add-to-build');
  if (addBtn2) {
    addBtn2.addEventListener('click', () => {
      // Add card to builder based on current picker mode
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
let mySquadFilters = { sort: 'created_at', order: 'desc', page: 1 };
let communityFilters = { liked: false, sort: 'created_at', order: 'desc', page: 1 };

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
    ? `<button class="btn btn-primary" id="new-squad-btn">+ New Squad</button>` : '';
  const myTab = currentUser
    ? `<button class="tab-btn ${squadsActiveTab === 'my' ? 'active' : ''}" data-tab="my">My Squads</button>` : '';

  setMain(`
    <div class="flex justify-between items-center" style="margin-bottom:12px">
      <h1>Squads</h1>
      ${newBtn}
    </div>
    <div class="tabs" style="margin-bottom:16px">
      ${myTab}
      <button class="tab-btn ${squadsActiveTab === 'community' ? 'active' : ''}" data-tab="community">Community</button>
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

async function renderMySquads(containerEl) {
  const f = mySquadFilters;
  const params = new URLSearchParams();
  params.set('user_id', currentUser.id);
  params.set('sort', f.sort);
  params.set('order', f.order);
  params.set('page', f.page);

  let data;
  try { data = await API.get('/squads?' + params.toString()); }
  catch (e) { containerEl.innerHTML = `<div class="alert alert-error">${esc(e.error||'Failed.')}</div>`; return; }

  const { items, total, page, pages } = data;
  const rows = items.map(s => `
    <tr class="clickable" data-id="${s.id}">
      <td><strong>${esc(s.name)}</strong></td>
      <td>${esc(s.nation)}</td>
      <td>${esc(s.mission ? s.mission.name : '—')}</td>
      <td>${s.rp_total}</td>
      <td><span class="${s.status === 'draft' ? 'badge badge-draft' : 'badge badge-ok'}">${s.status}</span></td>
      <td class="text-muted">${fmtDate(s.updated_at)}</td>
    </tr>`).join('');

  containerEl.innerHTML = `
    <div class="filter-bar" style="margin-bottom:8px">
      <select id="my-sort-select">
        <option value="created_at" ${f.sort==='created_at'?'selected':''}>Newest</option>
        <option value="updated_at" ${f.sort==='updated_at'?'selected':''}>Recently edited</option>
        <option value="name" ${f.sort==='name'?'selected':''}>Name A–Z</option>
        <option value="rp_total" ${f.sort==='rp_total'?'selected':''}>RP Total</option>
      </select>
    </div>
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">${total} squad${total!==1?'s':''}</div>
    <table class="data-table">
      <thead><tr><th>Name</th><th>Nation</th><th>Mission</th><th>RP</th><th>Status</th><th>Updated</th></tr></thead>
      <tbody>${rows||'<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">No squads yet. Build one!</td></tr>'}</tbody>
    </table>
    ${paginationHtml(page, pages)}`;

  containerEl.querySelector('#my-sort-select')?.addEventListener('change', e => {
    f.sort = e.target.value;
    f.order = e.target.value === 'name' ? 'asc' : 'desc';
    f.page = 1;
    renderMySquads(containerEl);
  });
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

  let data;
  try { data = await API.get('/squads?' + params.toString()); }
  catch (e) { containerEl.innerHTML = `<div class="alert alert-error">${esc(e.error||'Failed.')}</div>`; return; }

  const { items, total, page, pages } = data;
  const likedBtn = currentUser ? `
    <button class="quick-filter ${f.liked ? 'active' : ''}" id="liked-filter">♥ Liked by me</button>` : '';

  const rows = items.map(s => `
    <tr class="clickable" data-id="${s.id}">
      <td><strong>${esc(s.name)}</strong></td>
      <td>${esc(s.nation)}</td>
      <td>${esc(s.mission ? s.mission.name : '—')}</td>
      <td>${s.rp_total}</td>
      <td>${s.likes_count} ♥</td>
      <td>${esc(s.owner ? s.owner.username : '—')}</td>
      <td class="text-muted">${fmtDate(s.created_at)}</td>
    </tr>`).join('');

  containerEl.innerHTML = `
    <div class="filter-bar" style="margin-bottom:8px">
      ${likedBtn}
      <select id="comm-sort-select">
        <option value="created_at" ${f.sort==='created_at'?'selected':''}>Newest</option>
        <option value="likes_count" ${f.sort==='likes_count'?'selected':''}>Most Liked</option>
        <option value="rp_total" ${f.sort==='rp_total'?'selected':''}>RP Total</option>
        <option value="name" ${f.sort==='name'?'selected':''}>Name A–Z</option>
      </select>
    </div>
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">${total} published squad${total!==1?'s':''}</div>
    <table class="data-table">
      <thead><tr><th>Name</th><th>Nation</th><th>Mission</th><th>RP</th><th>Likes</th><th>Owner</th><th>Date</th></tr></thead>
      <tbody>${rows||'<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">No published squads yet.</td></tr>'}</tbody>
    </table>
    ${paginationHtml(page, pages)}`;

  containerEl.querySelector('#liked-filter')?.addEventListener('click', () => {
    f.liked = !f.liked; f.page = 1; renderCommunitySquads(containerEl);
  });
  containerEl.querySelector('#comm-sort-select')?.addEventListener('change', e => {
    f.sort = e.target.value;
    f.order = e.target.value === 'name' ? 'asc' : 'desc';
    f.page = 1;
    renderCommunitySquads(containerEl);
  });
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
    showError(e.error || 'Squad not found.');
    return;
  }

  const isOwner = currentUser && currentUser.id === squad.owner.id;
  const isDraft = squad.status === 'draft';
  const editBtn = isOwner ? `<button class="btn btn-sm btn-ghost" id="edit-squad-btn">Edit</button>` : '';
  const deleteBtn = isOwner ? `<button class="btn btn-sm btn-danger" id="delete-squad-btn">Delete</button>` : '';
  const publishBtn = isOwner && isDraft ? `<button class="btn btn-sm btn-primary" id="publish-btn">Publish</button>` : '';
  const draftBadge = isDraft ? `<span class="badge-draft">DRAFT</span>` : '';

  const likedClass = squad.liked_by_me ? 'liked' : '';
  const likeDisabled = !currentUser ? 'disabled title="Log in to like"' : '';
  const likeBtn = `
    <button class="like-btn ${likedClass}" id="like-btn" ${likeDisabled}>
      ♥ <span id="likes-count">${squad.likes_count}</span>
    </button>`;

  const soldiersHtml = squad.soldiers.map(ss => {
    const c = ss.card;
    const isPS = c.card_subtype === 'Player';
    const badgeHtml = chipForSubtype(c.card_subtype);

    const loadoutBar = isPS ? (() => {
      const pct = ss.effective_loadout > 0
        ? Math.min(100, Math.round(ss.gear_loadout_used / ss.effective_loadout * 100)) : 0;
      const cls = pct > 100 ? 'over' : pct >= 80 ? 'warn' : '';
      return `
        <div class="bar-wrapper">
          <div class="bar-label">Loadout: ${ss.gear_loadout_used}/${ss.effective_loadout}</div>
          <div class="bar-track"><div class="bar-fill ${cls}" style="width:${pct}%"></div></div>
        </div>`;
    })() : '';

    const gearHtml = (() => {
      const ps_gear = isPS ? ss.gear : [];
      const nps_gear = isPS ? [] : ss.gear;
      let out = '';
      if (ps_gear.length) {
        out += `<div class="gear-section-label">Gear</div>
          <table class="gear-table">` +
          ps_gear.map(g => `
            <tr>
              <td><span ${cardImageAttr(g.card)}>${esc(g.card.name)}</span></td>
              <td class="text-muted">${esc(g.card.card_category)}</td>
              <td class="text-muted">${g.card.resource_cost != null ? g.card.resource_cost + ' RP' : ''}</td>
              <td class="text-muted">${g.loadout_weight != null ? 'L' + g.loadout_weight : '(no load)'}</td>
              ${g.quantity > 1 ? `<td>×${g.quantity}</td>` : '<td></td>'}
            </tr>`).join('') +
          `</table>`;
      }
      if (nps_gear.length) {
        out += `<div class="gear-section-label">Available cards <span class="nps-gear-note">(not counted in budget)</span></div>
          <table class="gear-table">` +
          nps_gear.map(g => `
            <tr>
              <td><span ${cardImageAttr(g.card)}>${esc(g.card.name)}</span></td>
              <td class="text-muted">${esc(g.card.card_category)}</td>
            </tr>`).join('') +
          `</table>`;
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
          <span class="text-muted" style="font-size:13px">${c.resource_cost != null ? c.resource_cost + ' RP' : ''}</span>
        </div>
        <div class="soldier-stats">
          ${c.health != null ? `<span>HP ${c.health}</span>` : ''}
          ${c.cover != null ? `<span>Cover ${c.cover}</span>` : ''}
          ${c.movement != null ? `<span>Move ${c.movement}</span>` : ''}
          ${c.hth != null ? `<span>HtH ${c.hth >= 0 ? '+' : ''}${c.hth}</span>` : ''}
          ${c.loadout != null ? `<span>Loadout ${c.loadout}</span>` : ''}
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
            <button class="btn btn-sm btn-ghost edit-comment-btn" data-cid="${cm.id}">Edit</button>
            <button class="btn btn-sm btn-danger delete-comment-btn" data-cid="${cm.id}">Delete</button>
          </div>` : ''}
      </div>`;
  }).join('');

  const commentForm = currentUser ? `
    <div class="comment-form">
      <textarea id="comment-input" placeholder="Add a comment…" rows="3"></textarea>
      <div class="form-row">
        <button class="btn btn-primary" id="post-comment-btn">Post comment</button>
      </div>
    </div>` : `<p class="text-muted mt-2"><a href="#/login">Log in</a> to comment.</p>`;

  setMain(`
    <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
      <a href="#/squads" class="btn btn-ghost btn-sm">← Squads</a>
      ${editBtn} ${deleteBtn} ${publishBtn}
    </div>

    <div class="squad-header">
      <div class="squad-title">${draftBadge} ${esc(squad.name)}</div>
      <div class="squad-meta">
        By ${esc(squad.owner.username)} · ${fmtDate(squad.created_at)} · ${esc(squad.nation)}
      </div>
      <div style="margin-top:8px">${likeBtn}</div>
    </div>

    <div class="squad-mission-box">
      <div><strong>Mission:</strong>
        <span ${cardImageAttr(squad.mission)}>${esc(squad.mission ? squad.mission.name : '—')}</span>
        ${squad.mission ? `· Budget: <strong>${squad.mission.resources} RP</strong>` : ''}
      </div>
      ${squad.objective ? `<div><strong>Objective:</strong> ${esc(squad.objective.name)}</div>` : ''}
      ${squad.situation ? `<div><strong>Situation:</strong> ${esc(squad.situation.name)}</div>` : ''}
      <div style="margin-top:8px">
        <strong>Squad RP:</strong> ${squad.computed.rp_total}
        &nbsp;·&nbsp; <strong>Remaining:</strong>
        <span class="${squad.computed.rp_remaining < 0 ? 'text-danger' : 'text-success'}">
          ${squad.computed.rp_remaining} RP
        </span>
      </div>
    </div>

    <h2 style="margin-bottom:12px">Soldiers</h2>
    ${soldiersHtml || '<p class="text-muted">No soldiers.</p>'}

    ${squad.notes ? `<div class="card-notes mt-3"><strong>Notes</strong><br>${esc(squad.notes)}</div>` : ''}

    <div class="comments-section">
      <h2 style="margin-bottom:10px">Comments (${comments.length})</h2>
      <div id="comments-list">${commentsHtml || '<p class="text-muted">No comments yet.</p>'}</div>
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
      alert((e.error || 'Publish failed.') + (v?.errors?.length ? '\n' + v.errors.map(x => x.message).join('\n') : ''));
    }
  });

  // Edit
  document.getElementById('edit-squad-btn')?.addEventListener('click', () => {
    navigate('builder/' + squad.id);
  });

  // Delete
  document.getElementById('delete-squad-btn')?.addEventListener('click', async () => {
    if (!confirm('Delete this squad?')) return;
    try {
      await API.delete('/squads/' + squad.id);
      navigate('squads');
    } catch (e) { alert(e.error || 'Failed to delete.'); }
  });

  // Post comment
  document.getElementById('post-comment-btn')?.addEventListener('click', async () => {
    const input = document.getElementById('comment-input');
    const body = input.value.trim();
    if (!body) return;
    try {
      await API.post('/squads/' + squad.id + '/comments', { body });
      await showSquadDetail(squad.id); // reload
    } catch (e) { alert(e.error || 'Failed to post comment.'); }
  });

  // Edit/delete comments (delegated)
  document.getElementById('comments-list')?.addEventListener('click', async e => {
    const editBtn = e.target.closest('.edit-comment-btn');
    const delBtn = e.target.closest('.delete-comment-btn');
    const cid = (editBtn || delBtn)?.dataset.cid;
    if (!cid) return;

    if (delBtn) {
      if (!confirm('Delete this comment?')) return;
      try {
        await API.delete('/squads/' + squad.id + '/comments/' + cid);
        await showSquadDetail(squad.id);
      } catch (e) { alert(e.error || 'Failed.'); }
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
      editBtn.textContent = 'Save';
      editBtn.classList.remove('edit-comment-btn');
      editBtn.addEventListener('click', async () => {
        try {
          await API.put('/squads/' + squad.id + '/comments/' + cid, { body: ta.value.trim() });
          await showSquadDetail(squad.id);
        } catch (e) { alert(e.error || 'Failed.'); }
      });
    }
  });
}

// ---------------------------------------------------------------------------
// Reusable Card Table Component
// ---------------------------------------------------------------------------
const CARD_TABLE_COLS = {
  number:            { header: '#', render: c => esc(c.number), sortKey: 'number' },
  name:              { header: 'Name', render: c => `<span ${cardImageAttr(c)}>${esc(c.name)}</span>`, sortKey: 'name' },
  subtype:           { header: 'Type', render: c => chipForSubtype(c.card_subtype) },
  category:          { header: 'Category', render: c => chipForCategory(c.card_category) },
  nation:            { header: 'Nation', render: c => esc(c.nation || '—'), sortKey: 'nation' },
  module:            { header: 'Module', render: c => esc(c.module), sortKey: 'module' },
  rp:                { header: 'RP', render: c => c.resource_cost != null ? String(c.resource_cost) : '', sortKey: 'resource_cost' },
  health:            { header: 'HP', render: c => c.health != null ? String(c.health) : '' },
  loadout:           { header: 'Loadout', render: c => c.loadout != null ? String(c.loadout) : '' },
  movement:          { header: 'Move', render: c => c.movement != null ? String(c.movement) : '' },
  cover:             { header: 'Cover', render: c => c.cover != null ? String(c.cover) : '' },
  hth:               { header: 'HtH', render: c => c.hth != null ? (c.hth >= 0 ? '+' : '') + c.hth : '' },
  resources:         { header: 'Budget', render: c => c.resources != null ? String(c.resources) : '' },
  time:              { header: 'Turns', render: c => c.time != null ? String(c.time) : '' },
  objective_location:{ header: 'Obj@', render: c => c.objective_location != null ? String(c.objective_location) : '' },
  loadout_modifier:  { header: 'LM', render: c => c.loadout_modifier != null ? (c.loadout_modifier >= 0 ? '+' : '') + c.loadout_modifier : '' },
};

const MODE_COLS = {
  mission:   ['number', 'name', 'nation', 'module', 'rp', 'resources', 'time', 'objective_location', 'loadout_modifier'],
  objective: ['number', 'name', 'module', 'rp'],
  situation: ['number', 'name', 'module', 'rp'],
  soldier:   ['number', 'name', 'subtype', 'nation', 'module', 'rp', 'health', 'loadout', 'movement', 'cover', 'hth'],
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
    return `<th class="${cls}" ${attr}>${esc(col.header)}${indicator}</th>`;
  }).join('');

  const bodyRows = items.length
    ? items.map(c => {
        const cells = colDefs.map(col => `<td>${col.render ? col.render(c) : ''}</td>`).join('');
        return `<tr class="clickable" data-cid="${c.id}">${cells}</tr>`;
      }).join('')
    : `<tr><td colspan="${cols.length}" class="text-muted" style="text-align:center;padding:16px">No cards found.</td></tr>`;

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
      builderState.objectiveCard = sq.objective;
      builderState.nation = sq.nation;
      builderState.notes = sq.notes || '';
      builderState.soldiers = sq.soldiers.map(ss => ({
        card: ss.card,
        gear: ss.gear.map(g => ({ card: g.card, quantity: g.quantity })),
        defaultGear: ss.default_gear || [],
      }));
    } catch (e) {
      showError(e.error || 'Failed to load squad.');
      return;
    }
  } else {
    // Fresh builder — always reset when navigating to #/builder without an ID
    resetBuilderState();
  }
  builderState.pickerMode = builderState.missionCard ? null : 'mission';
  renderBuilder();
});

function builderRpTotal() {
  let total = 0;
  for (const s of builderState.soldiers) {
    total += s.card.resource_cost || 0;
    if (s.card.card_subtype === 'Player') {
      for (const g of s.gear) {
        total += (g.card.resource_cost || 0) * g.quantity;
      }
    }
  }
  return total;
}

function addSoldierToBuilder(card) {
  if (builderState.soldiers.some(s => s.card.id === card.id)) {
    alert(card.name + ' is already in this squad.');
    return false;
  }
  builderState.soldiers.push({ card, gear: [], defaultGear: card.associations || [] });
  return true;
}

function addGearToBuilder(card, soldierIdx) {
  const soldier = builderState.soldiers[soldierIdx];
  if (!soldier) return false;
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
    setMain(`<div class="alert alert-warning">Please <a href="#/login">log in</a> to build squads.</div>`);
    return;
  }

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
      if (['Weapon', 'Equipment'].includes(g.card.card_category)) {
        return acc + (g.card.loadout != null ? g.card.loadout : (g.card.resource_cost || 0)) * g.quantity;
      }
      return acc;
    }, 0) : 0;
    const loadPct = effectiveLoadout > 0 ? Math.min(100, Math.round(gearLoadout / effectiveLoadout * 100)) : 0;
    const loadCls = loadPct > 100 ? 'over' : loadPct >= 80 ? 'warn' : '';

    const gearItems = s.gear.map((g, gi) => `
      <div class="gear-item">
        <span ${cardImageAttr(g.card)}>${esc(g.card.name)}</span>
        <span class="text-muted">${g.card.resource_cost || 0} RP</span>
        <button class="btn btn-icon remove-gear-btn" data-sidx="${idx}" data-gidx="${gi}" title="Remove">✕</button>
      </div>`).join('');

    const dg = s.defaultGear || [];
    const defaultGearHtml = dg.length > 0 ? `
      <div class="default-gear-section">
        <div class="default-gear-label">Pre-printed (included)</div>
        ${dg.map(g => `
          <div class="gear-item gear-item-default">
            ${g.quantity > 1 ? `<span class="gear-qty">${g.quantity}×</span>` : ''}
            <span ${cardImageAttr(g.card)}>${esc(g.card.name)}</span>
            <span class="text-muted" style="font-size:11px">${g.card.card_category}</span>
          </div>`).join('')}
      </div>` : '';

    return `
      <div class="soldier-slot">
        <div class="soldier-slot-header">
          <span>
            ${chipForSubtype(c.card_subtype)}
            <span class="soldier-slot-name" ${cardImageAttr(c)}>${esc(c.name)}</span>
          </span>
          <span>
            <span class="soldier-slot-cost text-muted">${c.resource_cost || 0} RP</span>
            <button class="btn btn-icon remove-soldier-btn" data-sidx="${idx}" title="Remove soldier">✕</button>
          </span>
        </div>
        ${isPS || c.card_subtype !== 'Vehicle' ? `
          <div class="gear-list">${gearItems}</div>
          ${isPS ? `
            <div class="bar-wrapper" style="margin-top:6px">
              <div class="bar-label">Loadout ${gearLoadout}/${effectiveLoadout}</div>
              <div class="bar-track"><div class="bar-fill ${loadCls}" style="width:${loadPct}%"></div></div>
            </div>` : `<div class="nps-gear-note" style="font-size:11px;margin-top:4px">Cards below not counted in budget</div>`}
          ${defaultGearHtml}
          <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
            ${isPS ? `
              <button class="btn btn-sm btn-ghost add-weapon-btn" data-sidx="${idx}">+ Weapon</button>
              <button class="btn btn-sm btn-ghost add-equip-btn" data-sidx="${idx}">+ Equipment</button>
              <button class="btn btn-sm btn-ghost add-skill-btn" data-sidx="${idx}">+ Skill</button>
              <button class="btn btn-sm btn-ghost add-sr-btn" data-sidx="${idx}">+ Service Record</button>
            ` : `
              <button class="btn btn-sm btn-ghost add-nps-wpn-btn" data-sidx="${idx}">+ Weapon</button>
              <button class="btn btn-sm btn-ghost add-nps-eqp-btn" data-sidx="${idx}">+ Equipment</button>
              <button class="btn btn-sm btn-ghost add-nps-skl-btn" data-sidx="${idx}">+ Skill</button>
              <button class="btn btn-sm btn-ghost add-nps-act-btn" data-sidx="${idx}">+ Action</button>
            `}
          </div>` : ''}
      </div>`;
  }).join('');

  setMain(`
    <div class="builder-actions">
      <button class="btn btn-ghost btn-sm" id="save-draft-btn">Save as Draft</button>
      <button class="btn btn-primary" id="publish-squad-btn">Publish</button>
      <button class="btn btn-ghost btn-sm" id="validate-btn">Validate</button>
      ${builderState.squadId ? `<a href="#/squads/${builderState.squadId}" class="btn btn-ghost btn-sm">Cancel</a>` : ''}
    </div>
    <div id="builder-validation"></div>
    <div class="builder-layout">
      <!-- LEFT -->
      <div class="builder-left">
        <div class="builder-section">
          <div class="builder-section-title">Squad Name</div>
          <input type="text" id="squad-name" value="${esc(builderState.name)}" placeholder="Unnamed Squad" style="width:100%">
        </div>

        <div class="builder-section">
          <div class="builder-section-title">Mission</div>
          ${builderState.missionCard
            ? `<div class="flex justify-between items-center">
                <span ${cardImageAttr(builderState.missionCard)}><strong>${esc(builderState.missionCard.name)}</strong></span>
                <button class="btn btn-sm btn-ghost" id="change-mission-btn">Change</button>
               </div>
               <div class="text-muted" style="font-size:12px;margin-top:4px">
                 Budget: ${budget} RP
                 ${lm !== 0 ? `· Loadout Mod: ${lm >= 0 ? '+' : ''}${lm}` : ''}
               </div>`
            : `<button class="btn btn-ghost" id="pick-mission-btn">Select a Mission…</button>`}
        </div>

        <div class="builder-section">
          <div class="builder-section-title">Objective <span class="text-muted">(optional)</span></div>
          ${builderState.objectiveCard
            ? `<div class="flex justify-between items-center">
                <span ${cardImageAttr(builderState.objectiveCard)}>${esc(builderState.objectiveCard.name)}</span>
                <button class="btn btn-sm btn-ghost" id="change-obj-btn">Change</button>
               </div>`
            : builderState.missionCard
              ? `<button class="btn btn-ghost" id="pick-obj-btn">Select an Objective…</button>`
              : `<span class="text-muted">Select a mission first.</span>`}
        </div>

        <div class="builder-section">
          <div class="builder-section-title">Nation</div>
          ${builderState.missionCard
            ? `<select id="nation-select" style="width:100%">
                <option value="">— Select nation —</option>
                ${NATIONS.map(n => `<option value="${esc(n)}" ${builderState.nation===n?'selected':''}>${esc(n)}</option>`).join('')}
               </select>`
            : `<span class="text-muted">Select a mission first.</span>`}
        </div>

        <div class="builder-section">
          <div class="builder-section-title">
            <span>Soldiers</span>
            ${budget > 0 ? `
              <div class="bar-wrapper" style="margin-top:4px">
                <div class="bar-label">Budget: ${rpTotal}/${budget} RP (${rpRemaining >= 0 ? rpRemaining + ' remaining' : Math.abs(rpRemaining) + ' OVER'})</div>
                <div class="bar-track"><div class="bar-fill ${budgetCls}" style="width:${budgetPct}%"></div></div>
              </div>` : ''}
          </div>
          ${soldiersHtml}
          ${builderState.missionCard
            ? `<button class="btn btn-ghost" id="add-soldier-btn">+ Add Soldier</button>`
            : ''}
        </div>

        <div class="builder-section">
          <div class="builder-section-title">Notes</div>
          <textarea id="squad-notes" style="width:100%;min-height:60px">${esc(builderState.notes)}</textarea>
        </div>
      </div>

      <!-- RIGHT: Card Picker -->
      <div class="builder-right" id="picker-panel">
        <div class="picker-title" id="picker-title">
          ${builderState.pickerMode ? _pickerTitle(builderState.pickerMode) : 'Select a section on the left to pick cards.'}
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
  main.querySelector('#nation-select')?.addEventListener('change', e => { builderState.nation = e.target.value; });
  main.querySelector('#pick-mission-btn')?.addEventListener('click', () => { setPickerMode('mission'); renderBuilder(); });
  main.querySelector('#change-mission-btn')?.addEventListener('click', () => { setPickerMode('mission'); renderBuilder(); });
  main.querySelector('#pick-obj-btn')?.addEventListener('click', () => { setPickerMode('objective'); renderBuilder(); });
  main.querySelector('#change-obj-btn')?.addEventListener('click', () => { setPickerMode('objective'); renderBuilder(); });
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

  // Load picker results
  if (builderState.pickerMode) loadPickerResults();
}

function _pickerTitle(mode) {
  const titles = {
    mission: 'Select a Mission',
    objective: 'Select an Objective',
    situation: 'Select a Situation',
    soldier: 'Add a Soldier',
    gear: `Add ${builderState.pickerGearCat || 'Gear'} to ${
      builderState.pickerTarget != null && builderState.soldiers[builderState.pickerTarget]
        ? builderState.soldiers[builderState.pickerTarget].card.name : 'Soldier'}`,
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
    `<option value="${esc(m)}" ${builderState.pickerModule === m ? 'selected' : ''}>${m || 'All modules'}</option>`
  ).join('');
  return `
    <div class="filter-bar mb-2" style="flex-wrap:wrap;gap:6px">
      <input type="text" id="picker-q" placeholder="Search…" value="${esc(builderState.pickerQ)}" style="flex:1;min-width:120px">
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
        if (['mission', 'objective', 'situation'].includes(builderState.pickerMode)) {
          try { fullCard = (await API.get('/cards/' + card.id)).card; } catch (_) {}
        }
        switch (builderState.pickerMode) {
          case 'mission':
            builderState.missionCard = fullCard;
            builderState.pickerMode = null;
            break;
          case 'objective':
            builderState.objectiveCard = fullCard;
            builderState.pickerMode = null;
            break;
          case 'situation':
            builderState.situationCard = fullCard;
            builderState.pickerMode = null;
            break;
          case 'soldier':
            if (addSoldierToBuilder(fullCard)) builderState.pickerMode = null;
            break;
          case 'gear':
            addGearToBuilder(fullCard, builderState.pickerTarget);
            break;
        }
        renderBuilder();
      },
    });

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
    resultsDiv.innerHTML = `<div class="alert alert-error">${esc(e.error || 'Failed to load cards.')}</div>`;
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
    div.innerHTML = alertHtml(e.error || 'Validation error.');
  }
}

function resetBuilderState() {
  Object.assign(builderState, {
    squadId: null, name: '', missionCard: null, objectiveCard: null,
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
      div.innerHTML = alertHtml(e.error || 'Save failed.');
      if (e.data?.validation) div.innerHTML += renderValidation(e.data.validation);
    }
  }
}

function buildSquadPayload(status = 'draft') {
  return {
    name: builderState.name || 'Unnamed Squad',
    mission_card_id: builderState.missionCard?.id || null,
    objective_card_id: builderState.objectiveCard?.id || null,
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
    html += '<div class="alert alert-error"><strong>Errors:</strong><ul>' +
      v.errors.map(e => `<li>${esc(e.message)}</li>`).join('') + '</ul></div>';
  }
  if (v.warnings && v.warnings.length) {
    html += '<div class="alert alert-warning"><strong>Warnings:</strong><ul>' +
      v.warnings.map(w => `<li>${esc(w.message)}</li>`).join('') + '</ul></div>';
  }
  if (!v.errors?.length && !v.warnings?.length) {
    html += '<div class="alert alert-success">✓ Squad is valid.</div>';
  }
  return html;
}

// ---------------------------------------------------------------------------
// VIEW: Profile
// ---------------------------------------------------------------------------
register('profile', async function() {
  if (!currentUser) { navigate('login'); return; }
  showSpinner();
  let profile, mySquads;
  try {
    const p = await API.get('/profile/');
    profile = p;
    const sq = await API.get('/squads?user_id=' + currentUser.id + '&per_page=50');
    mySquads = sq;
  } catch (e) {
    showError(e.error || 'Failed to load profile.');
    return;
  }

  const moduleItems = profile.modules.map(m => `
    <label class="module-item">
      <input type="checkbox" name="module" value="${esc(m.module)}" ${m.owned ? 'checked' : ''}>
      ${esc(m.module)}
    </label>`).join('');

  const squadRows = mySquads.items.map(s => `
    <tr class="clickable" data-id="${s.id}">
      <td>${esc(s.name)}</td>
      <td>${esc(s.nation)}</td>
      <td>${esc(s.mission?.name || '—')}</td>
      <td>${s.rp_total} RP</td>
      <td>${s.status === 'draft' ? '<span class="badge-draft">DRAFT</span>' : 'Published'}</td>
      <td>${fmtDate(s.created_at)}</td>
    </tr>`).join('');

  setMain(`
    <h1 style="margin-bottom:20px">My Profile</h1>

    <div class="profile-section">
      <h2>Account</h2>
      <div class="form-field">
        <label>Username</label>
        <div>${esc(profile.user.username)}</div>
      </div>
      <div class="form-field">
        <label>Email</label>
        <div>${esc(profile.user.email)}</div>
      </div>
      <div class="form-field">
        <label>Full name</label>
        <input type="text" id="full-name" value="${esc(profile.user.full_name || '')}">
      </div>
      <button class="btn btn-primary" id="save-profile-btn">Save profile</button>
      <div id="profile-msg"></div>
    </div>

    <div class="profile-section">
      <h2>Change Password</h2>
      <div class="form-field"><label>Current password</label><input type="password" id="cur-pw"></div>
      <div class="form-field"><label>New password</label><input type="password" id="new-pw"></div>
      <button class="btn btn-primary" id="save-pw-btn">Update password</button>
      <div id="pw-msg"></div>
    </div>

    <div class="profile-section">
      <h2>Owned Modules</h2>
      <div class="module-actions">
        <button class="btn btn-sm btn-ghost" id="select-all-btn">Select All</button>
        <button class="btn btn-sm btn-ghost" id="deselect-all-btn">Deselect All</button>
      </div>
      <div class="module-list">${moduleItems}</div>
      <button class="btn btn-primary mt-2" id="save-modules-btn">Save module selection</button>
      <div id="modules-msg"></div>
    </div>

    <div class="profile-section">
      <h2>My Squads</h2>
      <table class="data-table">
        <thead><tr><th>Name</th><th>Nation</th><th>Mission</th><th>RP</th><th>Status</th><th>Date</th></tr></thead>
        <tbody>${squadRows || '<tr><td colspan="6" class="text-muted">No squads yet.</td></tr>'}</tbody>
      </table>
    </div>
  `);

  const main = document.getElementById('app-main');

  main.querySelector('#save-profile-btn')?.addEventListener('click', async () => {
    const fn = main.querySelector('#full-name').value.trim();
    const msg = main.querySelector('#profile-msg');
    try {
      await API.put('/profile/', { full_name: fn });
      msg.innerHTML = alertHtml('Saved!', 'success');
    } catch (e) { msg.innerHTML = alertHtml(e.error || 'Failed.'); }
  });

  main.querySelector('#save-pw-btn')?.addEventListener('click', async () => {
    const cp = main.querySelector('#cur-pw').value;
    const np = main.querySelector('#new-pw').value;
    const msg = main.querySelector('#pw-msg');
    try {
      await API.put('/profile/password', { current_password: cp, new_password: np });
      msg.innerHTML = alertHtml('Password updated!', 'success');
      main.querySelector('#cur-pw').value = '';
      main.querySelector('#new-pw').value = '';
    } catch (e) { msg.innerHTML = alertHtml(e.error || 'Failed.'); }
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
      msg.innerHTML = alertHtml(`Saved ${owned.length} modules.`, 'success');
    } catch (e) { msg.innerHTML = alertHtml(e.error || 'Failed.'); }
  });

  main.querySelectorAll('tr[data-id]').forEach(row => {
    row.addEventListener('click', () => navigate('squads/' + row.dataset.id));
  });
});

// ---------------------------------------------------------------------------
// VIEW: Login
// ---------------------------------------------------------------------------
register('login', function() {
  setMain(`
    <div class="auth-form-wrapper">
      <h1>Login</h1>
      <div id="login-msg"></div>
      <div class="form-field"><label>Username</label><input type="text" id="login-user" autocomplete="username"></div>
      <div class="form-field"><label>Password</label><input type="password" id="login-pw" autocomplete="current-password"></div>
      <button class="btn btn-primary" id="login-btn" style="width:100%;margin-top:8px">Login</button>
      <div class="auth-form-footer mt-2" style="text-align:center;font-size:13px">
        No account? <a href="#/register">Register</a>
      </div>
    </div>`);

  const doLogin = async () => {
    const username = document.getElementById('login-user').value.trim();
    const password = document.getElementById('login-pw').value;
    const msg = document.getElementById('login-msg');
    try {
      const data = await API.post('/auth/login', { username, password });
      currentUser = data.user;
      renderHeader();
      updateProfileLink();
      navigate('squads');
    } catch (e) { msg.innerHTML = alertHtml(e.error || 'Login failed.'); }
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
      <h1>Create Account</h1>
      <div id="reg-msg"></div>
      <div class="form-field"><label>Username</label><input type="text" id="reg-user" autocomplete="username"></div>
      <div class="form-field"><label>Email</label><input type="email" id="reg-email" autocomplete="email"></div>
      <div class="form-field"><label>Full name <span class="text-muted">(optional)</span></label><input type="text" id="reg-name"></div>
      <div class="form-field"><label>Password</label><input type="password" id="reg-pw" autocomplete="new-password"></div>
      <button class="btn btn-primary" id="reg-btn" style="width:100%;margin-top:8px">Create Account</button>
      <div class="auth-form-footer mt-2" style="text-align:center;font-size:13px">
        Already have an account? <a href="#/login">Login</a>
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
      currentUser = data.user;
      renderHeader();
      updateProfileLink();
      navigate('profile');
    } catch (e) { msg.innerHTML = alertHtml(e.error || 'Registration failed.'); }
  });
});

// ---------------------------------------------------------------------------
// 404
// ---------------------------------------------------------------------------
register('404', function() {
  setMain('<div class="alert alert-warning">Page not found. <a href="#/cards">Go to Cards</a></div>');
});

// ---------------------------------------------------------------------------
// Nation list (static)
// ---------------------------------------------------------------------------
const NATIONS = [
  'US','UK','Russian','German','Poland','USMC','Japan','Australian','France','China',
  'US Airborne','UK Airborne','German Airborne','German SS','German Afrika Korps',
  'North Korean (KW)','China (KW)','South Korean (KW)','United Nations (KW)',
  'Finland','Canada','Norway','Commonwealth','Japan SNLF','UK Desert Rats',
  'Italian','Italian Regio Esercito','Free French','Vichy French','German Alpine',
  'New Zealand','Greece','Italian Partisans','Italian Airborne','Italian Cavalry',
  'UK LRDG','UK Med','UK Gurkhas',
  'US Clergy','UK Clergy','RU Clergy','PO Clergy',
  'US Undead','UK Undead','Russian Undead','Poland Undead','German Undead','Japan Undead',
];
