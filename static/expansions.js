// ---------------------------------------------------------------------------
// My Expansions — the user's collection: which expansions (card modules) they own.
// The squad generator and the card pickers only use cards from owned expansions.
// Backend: GET /api/profile/expansions, PUT /api/profile/modules. Uses app.js helpers.
// ---------------------------------------------------------------------------
const expState = { items: [], filter: 'all', q: '', dirty: false };

register('expansions', async function () {
  if (!requireLogin()) return;
  showSpinner();
  try {
    const r = await API.get('/profile/expansions');
    expState.items = r.expansions;
  } catch (e) {
    showError(e.error || t('profile.load_failed'));
    return;
  }
  expState.filter = 'all'; expState.q = ''; expState.dirty = false;
  renderExpansions();
});

function expVisible() {
  const q = expState.q.trim().toLowerCase();
  return expState.items.filter(it => {
    if (expState.filter === 'owned' && !it.owned) return false;
    if (expState.filter === 'missing' && it.owned) return false;
    if (!q) return true;
    const hay = [it.module, tv('module', it.module), ...it.nations.map(n => tv('nation', n))].join(' ').toLowerCase();
    return hay.includes(q);
  });
}

function renderExpansions() {
  const total = expState.items.length;
  setMain(`
    <div class="exp-page">
      <h1 class="page-title" style="margin-bottom:10px">${esc(t('exp.title'))}</h1>
      <p class="text-muted exp-intro">${esc(t('exp.intro'))}</p>
      <div class="exp-bar">
        <div class="exp-summary" id="exp-summary"></div>
        <input type="search" id="exp-q" class="exp-search" placeholder="${esc(t('exp.search'))}" value="${esc(expState.q)}">
        <div class="gen-seg exp-filter" role="radiogroup">
          ${[['all', 'exp.f_all'], ['owned', 'exp.f_owned'], ['missing', 'exp.f_missing']].map(([v, k]) =>
            `<label class="gen-seg-item"><input type="radio" name="exp-f" value="${v}" ${expState.filter === v ? 'checked' : ''}><span>${esc(t(k))}</span></label>`).join('')}
        </div>
        <div class="exp-actions">
          <button type="button" class="btn btn-sm btn-ghost" id="exp-all">${esc(t('exp.select_all'))}</button>
          <button type="button" class="btn btn-sm btn-ghost" id="exp-none">${esc(t('exp.select_none'))}</button>
        </div>
      </div>
      <div class="exp-grid" id="exp-grid"></div>
      <div class="exp-save-bar">
        <button type="button" class="btn btn-primary" id="exp-save">${icon('save')}<span>${esc(t('exp.save'))}</span></button>
        <span class="text-muted" id="exp-dirty"></span>
        <div id="exp-msg"></div>
      </div>
    </div>`);
  if (!total) { document.getElementById('exp-grid').innerHTML = `<p class="text-muted">${esc(t('exp.no_data'))}</p>`; return; }
  const main = document.getElementById('app-main');
  drawExpansionGrid();

  main.querySelector('#exp-q').addEventListener('input', e => { expState.q = e.target.value; drawExpansionGrid(); });
  main.querySelectorAll('input[name=exp-f]').forEach(r => r.addEventListener('change', () => { expState.filter = r.value; drawExpansionGrid(); }));
  const setAll = on => { expVisible().forEach(it => { it.owned = on; }); markExpDirty(); drawExpansionGrid(); };
  main.querySelector('#exp-all').addEventListener('click', () => setAll(true));
  main.querySelector('#exp-none').addEventListener('click', () => setAll(false));
  main.querySelector('#exp-save').addEventListener('click', async () => {
    const owned = expState.items.filter(it => it.owned).map(it => it.module);
    const msg = main.querySelector('#exp-msg');
    try {
      await API.put('/profile/modules', { owned_modules: owned });
      expState.dirty = false;
      msg.innerHTML = alertHtml(tn('exp.saved', owned.length), 'success');
      markExpDirty(false);
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
  });
  markExpDirty(false);
}

function markExpDirty(on = true) {
  expState.dirty = on;
  const el = document.getElementById('exp-dirty');
  if (el) el.textContent = on ? t('exp.unsaved') : '';
  if (on) document.getElementById('exp-msg')?.replaceChildren();     // a new edit clears the "saved" message
}

function drawExpansionGrid() {
  const grid = document.getElementById('exp-grid');
  const list = expVisible();
  const owned = expState.items.filter(it => it.owned).length;
  document.getElementById('exp-summary').innerHTML = `<strong>${esc(t('exp.summary', { owned, total: expState.items.length }))}</strong>`;
  if (!list.length) { grid.innerHTML = `<p class="text-muted">${esc(t('exp.none'))}</p>`; return; }
  grid.innerHTML = list.map(it => {
    const idx = expState.items.indexOf(it);
    const facts = [tn('exp.cards', it.cards), it.player_soldiers ? tn('exp.ps', it.player_soldiers) : '',
                   it.missions ? tn('exp.missions', it.missions) : ''].filter(Boolean).join(' · ');
    return `<label class="exp-item ${it.owned ? 'is-owned' : ''}">
      <input type="checkbox" data-i="${idx}" ${it.owned ? 'checked' : ''}>
      <span class="exp-body">
        <span class="exp-name">${esc(tv('module', it.module))}</span>
        <span class="exp-facts">${esc(facts)}</span>
        ${it.nations.length ? `<span class="exp-nations">${it.nations.map(n => `<span class="chip">${esc(tv('nation', n))}</span>`).join(' ')}</span>` : ''}
      </span>
    </label>`;
  }).join('');
  grid.querySelectorAll('input[type=checkbox]').forEach(cb => cb.addEventListener('change', () => {
    expState.items[parseInt(cb.dataset.i)].owned = cb.checked;
    cb.closest('.exp-item').classList.toggle('is-owned', cb.checked);
    markExpDirty();
    const n = expState.items.filter(it => it.owned).length;
    document.getElementById('exp-summary').innerHTML = `<strong>${esc(t('exp.summary', { owned: n, total: expState.items.length }))}</strong>`;
  }));
}
