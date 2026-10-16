// ---------------------------------------------------------------------------
// Squad generator — form + result view (spec/13_squad_generator.md). Uses app.js helpers.
// Backend: app/generator.py (/api/generator/options, /api/generator/generate).
// ---------------------------------------------------------------------------
Object.assign(ICON_PATHS, {
  dice:    '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1" fill="currentColor"/><circle cx="15.5" cy="15.5" r="1" fill="currentColor"/><circle cx="12" cy="12" r="1" fill="currentColor"/><circle cx="15.5" cy="8.5" r="1" fill="currentColor"/><circle cx="8.5" cy="15.5" r="1" fill="currentColor"/>',
  lock:    '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  unlock:  '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.5-2"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/>',
  box:     '<path d="M21 8 12 3 3 8v8l9 5 9-5Z"/><path d="m3 8 9 5 9-5"/><path d="M12 13v8"/>',
});

const GEN_STORE = 'wf.generator.form.v1';
const GEN_TWISTS = ['interesting', 'challenge', 'one_hero', 'all_squad', 'no_mg', 'light_spender'];
const GEN_TYPES = ['NPS', 'Squad', 'Vehicle', 'Team'];
const GEN_ENEMY_CODE = { German: 'GE', Japan: 'JP', Russian: 'RU', US: 'US', USMC: 'US', UK: 'UK', Italian: 'IT',
  France: 'FR', Poland: 'PL', Canada: 'CA', Australian: 'AU', China: 'CN', Finland: 'FI', Norway: 'NO' };

function genDefaultForm() {
  return {
    nation: 'random', mission: 'random', objective: 'random',
    players: '', enemy: 'auto', level: 'frontline',
    quality: 'optimal', variety: 50, twist: '', more: '', less: '',
    spend: 'auto', maxRp: '',
    types: { NPS: true, Squad: true, Vehicle: false, Team: true },
    maxSoldiers: '', include: [], exclude: [], seed: '',
  };
}

let gen = { opts: null, form: genDefaultForm(), result: null, busy: false, error: null, locks: new Set(), open: new Set(['brief']) };

function genLoadForm() {
  try {
    const saved = JSON.parse(localStorage.getItem(GEN_STORE) || 'null');
    if (saved && typeof saved === 'object') gen.form = Object.assign(genDefaultForm(), saved, { types: Object.assign(genDefaultForm().types, saved.types || {}) });
  } catch (_) { gen.form = genDefaultForm(); }
}
function genSaveForm() { try { localStorage.setItem(GEN_STORE, JSON.stringify(gen.form)); } catch (_) {} }

register('generator', async function () {
  showSpinner();
  try {
    gen.opts = await API.get('/generator/options');
  } catch (e) {
    showError(e.error || t('gen.load_failed'));
    return;
  }
  genLoadForm();
  gen.result = null; gen.error = null; gen.locks = new Set(); gen.resumeName = null;
  const resumed = takeResume('generator');              // work parked by the save button before the login
  if (resumed) { gen.form = resumed.form; gen.result = resumed.result; gen.locks = new Set(resumed.locks || []); gen.resumeName = resumed.name; }
  // Drop remembered picks that are no longer offered (module unchecked in the profile, etc.)
  const nations = gen.opts.nations.map(n => n.code);
  if (gen.form.nation !== 'random' && !nations.includes(gen.form.nation)) gen.form.nation = 'random';
  if (gen.form.mission !== 'random' && !gen.opts.missions.some(m => String(m.id) === String(gen.form.mission))) gen.form.mission = 'random';
  if (gen.form.objective !== 'random' && !gen.opts.objectives.some(o => String(o.id) === String(gen.form.objective))) gen.form.objective = 'random';
  renderGenerator();
});

// ---------------------------------------------------------------------------
// Page shell
// ---------------------------------------------------------------------------
function renderGenerator() {
  const c = gen.opts.collection;
  const all = c.owned_modules === c.total_modules;
  setMain(`
    <div class="gen-page">
      <div class="gen-head">
        <h1 class="page-title">${esc(t('gen.title'))}</h1>
        <p class="gen-sub">${esc(t('gen.subtitle'))}</p>
      </div>
      <div class="gen-collection">
        <span class="gen-collection-ico">${icon('box')}</span>
        <span class="gen-collection-text"><strong>${esc(t('gen.collection', { owned: c.owned_modules, total: c.total_modules }))}</strong>
          ${all ? `<span class="text-muted"> — ${esc(t('gen.collection_all'))}</span>` : `<span class="text-muted"> — ${esc(t('gen.collection_only'))}</span>`}</span>
        <a class="btn btn-sm btn-ghost" href="#/expansions">${esc(t('gen.edit_modules'))}</a>
      </div>
      <div class="gen-layout">
        <form class="gen-form" id="gen-form" autocomplete="off" onsubmit="return false"></form>
        <section class="gen-result" id="gen-result" aria-live="polite"></section>
      </div>
    </div>`);
  renderGenForm();
  renderGenResult();
}

// ---------------------------------------------------------------------------
// Form
// ---------------------------------------------------------------------------
function genNationOptions() {
  const f = gen.form;
  return `<option value="random" ${f.nation === 'random' ? 'selected' : ''}>🎲 ${esc(t('gen.random'))}</option>` +
    gen.opts.nations.map(n => `<option value="${esc(n.code)}" ${f.nation === n.code ? 'selected' : ''}>${esc(tv('nation', n.code))} (${n.player_soldiers})</option>`).join('');
}

function genMissionList() {
  const f = gen.form;
  return gen.opts.missions.filter(m => f.nation === 'random' || !m.nation_base || m.nation_base === f.nation);
}

function genMissionOptions() {
  const f = gen.form;
  const list = genMissionList();
  const groups = {};
  list.forEach(m => { (groups[m.theater || '—'] = groups[m.theater || '—'] || []).push(m); });
  const opt = m => `<option value="${m.id}" ${String(f.mission) === String(m.id) ? 'selected' : ''}>${esc(m.name)} — ${m.resources ?? '?'} ${esc(t('stat.rp'))}${m.time ? ` · ${m.time} ${esc(t('gen.turns'))}` : ''}</option>`;
  return `<option value="random" ${f.mission === 'random' ? 'selected' : ''}>🎲 ${esc(t('gen.random'))}</option>` +
    Object.keys(groups).sort().map(g => `<optgroup label="${esc(tv('theater', g))}">${groups[g].map(opt).join('')}</optgroup>`).join('');
}

function genObjectiveList() {
  const f = gen.form;
  const m = f.mission === 'random' ? null : gen.opts.missions.find(x => String(x.id) === String(f.mission));
  let list = gen.opts.objectives;
  if (m) {
    const want = { 'Holding Action': 'Fallback', 'Hold the Line': 'Right Flank' }[m.mission_type];
    list = list.filter(o => want ? o.family === want : !['Fallback', 'Right Flank'].includes(o.family));
    const same = list.filter(o => o.theater === m.theater);
    if (same.length) list = same;
  }
  return list;
}

function genObjectiveOptions() {
  const f = gen.form;
  return `<option value="random" ${f.objective === 'random' ? 'selected' : ''}>🎲 ${esc(t('gen.random_fit'))}</option>` +
    genObjectiveList().map(o => `<option value="${o.id}" ${String(f.objective) === String(o.id) ? 'selected' : ''}>${esc(o.name)}${o.mechanic ? ` — ${esc(tv('card_subtype', o.mechanic))}` : ''}</option>`).join('');
}

function genSelect(key, label, optionsHtml, hint) {
  return `<div class="form-field gen-field"><label for="gf-${key}">${esc(label)}</label>
    <select id="gf-${key}" data-f="${key}">${optionsHtml}</select>
    ${hint ? `<div class="gen-hint">${esc(hint)}</div>` : ''}</div>`;
}

function genSeg(key, label, items, value, hint) {
  return `<div class="form-field gen-field"><label>${esc(label)}</label>
    <div class="gen-seg" role="radiogroup">${items.map(([v, text]) =>
      `<label class="gen-seg-item"><input type="radio" name="gf-${key}" data-f="${key}" value="${esc(v)}" ${String(value) === String(v) ? 'checked' : ''}><span>${esc(text)}</span></label>`).join('')}</div>
    ${hint ? `<div class="gen-hint">${esc(hint)}</div>` : ''}</div>`;
}

function genSection(id, title, badge, body) {
  return `<details class="gen-sec" data-sec="${id}" ${gen.open.has(id) ? 'open' : ''}>
    <summary><span class="gen-sec-title">${esc(title)}</span>${badge ? `<span class="gen-sec-badge">${esc(badge)}</span>` : ''}</summary>
    <div class="gen-sec-body">${body}</div></details>`;
}

function genChips(kind) {
  const list = gen.form[kind];
  return `<div class="gen-chips">${list.map((c, i) =>
    `<span class="chip gen-chip">${esc(c.name)} <button type="button" class="gen-chip-x" data-chip="${kind}" data-i="${i}" aria-label="${esc(t('common.remove'))}">×</button></span>`).join('')}</div>`;
}

function genPicker(kind, label, hint) {
  return `<div class="form-field gen-field gen-picker" data-picker="${kind}">
    <label>${esc(label)}</label>
    ${genChips(kind)}
    <input type="search" class="gen-pick-q" placeholder="${esc(t('gen.pick_placeholder'))}" data-picker-q="${kind}">
    <div class="gen-pick-results" data-picker-results="${kind}"></div>
    <div class="gen-hint">${esc(hint)}</div></div>`;
}

function genMetricOptions(selected) {
  return `<option value="">—</option>` + METRIC_KEYS.map(k => `<option value="${k}" ${selected === k ? 'selected' : ''}>${esc(t('metrics.' + k))}</option>`).join('');
}

function renderGenForm() {
  const f = gen.form;
  const nSet = (...keys) => keys.filter(k => k).length;
  const scenarioSet = nSet(f.players !== '', f.enemy !== 'auto', f.level !== 'frontline', f.objective !== 'random');
  const styleSet = nSet(f.quality !== 'optimal', f.more, f.less, f.spend !== 'auto');
  const consSet = nSet(f.include.length, f.exclude.length, f.maxSoldiers !== '', f.seed !== '',
    JSON.stringify(f.types) !== JSON.stringify(genDefaultForm().types));
  const good = f.quality === 'good_enough';

  const brief = genSelect('nation', t('gen.nation'), genNationOptions(), t('gen.nation_hint')) +
    genSelect('mission', t('gen.mission'), genMissionOptions(), t('gen.mission_hint', { n: genMissionList().length }));

  const scenario =
    genSelect('objective', t('gen.objective'), genObjectiveOptions(), t('gen.objective_hint')) +
    `<div class="form-field gen-field"><label for="gf-players">${esc(t('gen.players'))}</label>
       <input type="number" id="gf-players" data-f="players" min="1" max="6" value="${esc(f.players)}" placeholder="${esc(t('gen.auto'))}">
       <div class="gen-hint">${esc(t('gen.players_hint'))}</div></div>` +
    genSelect('enemy', t('gen.enemy'), `<option value="auto" ${f.enemy === 'auto' ? 'selected' : ''}>${esc(t('gen.auto'))}</option>` +
      gen.opts.enemy_nations.map(n => `<option value="${esc(n)}" ${f.enemy === n ? 'selected' : ''}>${esc(tv('nation', n))}</option>`).join('')) +
    genSeg('level', t('gen.level'), [['frontline', t('gen.level_f')], ['elite', t('gen.level_e')]], f.level);

  const style =
    genSeg('quality', t('gen.quality'), [['optimal', t('gen.q_optimal')], ['good_enough', t('gen.q_good')]], f.quality,
      good ? t('gen.q_good_hint') : t('gen.q_optimal_hint')) +
    (good ? `<div class="form-field gen-field"><label for="gf-variety">${esc(t('gen.variety'))} <span class="gen-val">${f.variety}</span></label>
        <input type="range" id="gf-variety" data-f="variety" min="0" max="100" step="5" value="${f.variety}">
        <div class="gen-range-labels"><span>${esc(t('gen.variety_lo'))}</span><span>${esc(t('gen.variety_hi'))}</span></div></div>` +
      genSelect('twist', t('gen.twist'), `<option value="">${esc(t('gen.twist.none'))}</option>` +
        GEN_TWISTS.map(k => `<option value="${k}" ${f.twist === k ? 'selected' : ''}>${esc(t('gen.twist.' + k))}</option>`).join(''),
        f.twist ? t('gen.twist.' + f.twist + '_hint') : '') : '') +
    `<div class="gen-pair">
       <div class="form-field gen-field"><label for="gf-more">${esc(t('gen.more'))}</label><select id="gf-more" data-f="more">${genMetricOptions(f.more)}</select></div>
       <div class="form-field gen-field"><label for="gf-less">${esc(t('gen.less'))}</label><select id="gf-less" data-f="less">${genMetricOptions(f.less)}</select></div>
     </div><div class="gen-hint" style="margin:-4px 0 10px">${esc(t('gen.emphasis_hint'))}</div>` +
    genSeg('spend', t('gen.spend'), [['auto', t('gen.spend_auto')], ['cap', t('gen.spend_cap')]], f.spend) +
    (f.spend === 'cap' ? `<div class="form-field gen-field"><label for="gf-maxRp">${esc(t('gen.max_rp'))}</label>
        <input type="number" id="gf-maxRp" data-f="maxRp" min="1" max="500" value="${esc(f.maxRp)}"></div>` : '');

  const cons =
    `<div class="form-field gen-field"><label>${esc(t('gen.types'))}</label><div class="gen-checks">${GEN_TYPES.map(k =>
      `<label class="gen-check"><input type="checkbox" data-type="${k}" ${f.types[k] ? 'checked' : ''}> ${esc(t('gen.type.' + k))}</label>`).join('')}</div>
     ${f.types.Vehicle ? `<div class="gen-hint">${esc(t('gen.vehicle_hint'))}</div>` : ''}</div>` +
    `<div class="form-field gen-field"><label for="gf-maxSoldiers">${esc(t('gen.max_soldiers'))}</label>
       <input type="number" id="gf-maxSoldiers" data-f="maxSoldiers" min="1" max="20" value="${esc(f.maxSoldiers)}" placeholder="8">
       <div class="gen-hint">${esc(t('gen.max_soldiers_hint'))}</div></div>` +
    genPicker('include', t('gen.include'), t('gen.include_hint')) +
    genPicker('exclude', t('gen.exclude'), t('gen.exclude_hint')) +
    `<div class="form-field gen-field"><label for="gf-seed">${esc(t('gen.seed'))}</label>
       <input type="text" id="gf-seed" data-f="seed" maxlength="32" value="${esc(f.seed)}" placeholder="${esc(t('gen.seed_placeholder'))}">
       <div class="gen-hint">${esc(t('gen.seed_hint'))}</div></div>`;

  const form = document.getElementById('gen-form');
  form.innerHTML = `
    <div class="gen-brief-title">${esc(t('gen.brief'))}</div>
    ${brief}
    <button type="button" class="btn btn-primary gen-go" id="gen-go" ${gen.busy ? 'disabled' : ''}>
      ${icon('dice')}<span>${esc(gen.busy ? t('gen.generating') : t('gen.generate'))}</span></button>
    <div class="gen-go-sub">${esc(f.nation === 'random' && f.mission === 'random' ? t('gen.surprise') : t('gen.go_hint'))}</div>
    ${genSection('scenario', t('gen.sec_scenario'), scenarioSet ? t('gen.n_set', { n: scenarioSet }) : '', scenario)}
    ${genSection('style', t('gen.sec_style'), styleSet ? t('gen.n_set', { n: styleSet }) : '', style)}
    ${genSection('constraints', t('gen.sec_constraints'), consSet ? t('gen.n_set', { n: consSet }) : '', cons)}
    <button type="button" class="btn btn-ghost btn-sm gen-reset" id="gen-reset">${esc(t('gen.reset'))}</button>`;
  wireGenForm(form);
}

function wireGenForm(form) {
  const rerender = () => { genSaveForm(); renderGenForm(); };
  form.querySelectorAll('details.gen-sec').forEach(d => d.addEventListener('toggle', () => {
    d.open ? gen.open.add(d.dataset.sec) : gen.open.delete(d.dataset.sec);
  }));
  form.querySelectorAll('[data-f]').forEach(el => {
    const key = el.dataset.f;
    el.addEventListener(el.type === 'range' || el.type === 'text' || el.type === 'number' ? 'input' : 'change', () => {
      if (el.type === 'radio' && !el.checked) return;
      let v = el.type === 'range' ? parseInt(el.value) : el.value;
      gen.form[key] = v;
      if (key === 'variety') { el.closest('.gen-field').querySelector('.gen-val').textContent = v; genSaveForm(); return; }
      if (['players', 'maxRp', 'maxSoldiers', 'seed'].includes(key)) { genSaveForm(); return; }
      if (key === 'nation') {   // a mission of another nation no longer fits
        const m = gen.opts.missions.find(x => String(x.id) === String(gen.form.mission));
        if (m && m.nation_base && gen.form.nation !== 'random' && m.nation_base !== gen.form.nation) gen.form.mission = 'random';
      }
      if (key === 'mission') {   // an objective that does not fit the new mission is dropped
        if (!genObjectiveList().some(o => String(o.id) === String(gen.form.objective))) gen.form.objective = 'random';
      }
      if (key === 'quality' && v !== 'good_enough') gen.form.twist = '';
      if (key === 'more' && v && v === gen.form.less) gen.form.less = '';
      if (key === 'less' && v && v === gen.form.more) gen.form.more = '';
      rerender();
    });
  });
  form.querySelectorAll('[data-type]').forEach(el => el.addEventListener('change', () => {
    gen.form.types[el.dataset.type] = el.checked; rerender();
  }));
  form.querySelectorAll('[data-chip]').forEach(b => b.addEventListener('click', () => {
    gen.form[b.dataset.chip].splice(parseInt(b.dataset.i), 1); rerender();
  }));
  form.querySelectorAll('[data-picker-q]').forEach(inp => wireGenPicker(inp));
  form.querySelector('#gen-go').addEventListener('click', () => runGenerate());
  form.querySelector('#gen-reset').addEventListener('click', () => { gen.form = genDefaultForm(); gen.locks = new Set(); rerender(); });
}

// Card search for "must include" / "exclude": soldiers and weapons only (what the engine picks from)
function wireGenPicker(inp) {
  const kind = inp.dataset.pickerQ;
  const box = inp.closest('.gen-picker').querySelector('[data-picker-results]');
  let timer = null, seq = 0;
  inp.addEventListener('input', () => {
    clearTimeout(timer);
    const q = inp.value.trim();
    if (q.length < 2) { box.innerHTML = ''; return; }
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const nat = gen.form.nation !== 'random' ? `&nation=${encodeURIComponent(gen.form.nation)}` : '';
        const r = await API.get(`/cards?q=${encodeURIComponent(q)}&per_page=30${nat}`);
        if (mine !== seq) return;
        const items = r.items.filter(c => ['Soldier', 'Weapon'].includes(c.card_type)).slice(0, 8);
        box.innerHTML = items.length ? items.map(c => `<button type="button" class="gen-pick-item" data-id="${c.id}">
            <span>${esc(c.name)}</span><span class="text-muted">${esc(tv('card_subtype', c.card_subtype || c.card_type))}${c.resource_cost != null ? ` · ${c.resource_cost} ${esc(t('stat.rp'))}` : ''}</span></button>`).join('')
          : `<div class="gen-hint">${esc(t('gen.pick_none'))}</div>`;
        box.querySelectorAll('.gen-pick-item').forEach(b => b.addEventListener('click', () => {
          const c = items.find(x => String(x.id) === b.dataset.id);
          if (!gen.form[kind].some(x => x.id === c.id)) gen.form[kind].push({ id: c.id, name: c.name, type: c.card_type });
          genSaveForm(); renderGenForm();
        }));
      } catch (_) { box.innerHTML = ''; }
    }, 250);
  });
}

// ---------------------------------------------------------------------------
// Running a generation
// ---------------------------------------------------------------------------
function genBody(extra = {}) {
  const f = gen.form;
  const types = GEN_TYPES.filter(k => f.types[k]);
  const emphasis = {};
  if (f.more) emphasis[f.more] = 1;
  if (f.less) emphasis[f.less] = -1;
  const lockedIds = [...gen.locks];
  return Object.assign({
    nation: f.nation,
    mission_card_id: f.mission === 'random' ? null : parseInt(f.mission),
    objective_card_id: f.objective === 'random' ? null : parseInt(f.objective),
    players: f.players === '' ? null : parseInt(f.players),
    enemy_nation: f.enemy === 'auto' ? null : f.enemy,
    hostile_level: f.level,
    quality: f.quality,
    variety: f.variety / 100,
    twist: f.twist || null,
    emphasis,
    spend: { type: f.spend, max_rp: f.maxRp === '' ? null : parseInt(f.maxRp) },
    include: [...new Set([...f.include.map(c => c.id), ...lockedIds])],
    exclude: f.exclude.map(c => c.id),
    soldier_types: types,
    max_soldiers: f.maxSoldiers === '' ? null : parseInt(f.maxSoldiers),
    seed: f.seed,
  }, extra);
}

async function runGenerate(extra = {}) {
  if (gen.busy) return;
  gen.busy = true; gen.error = null;
  document.getElementById('gen-go')?.setAttribute('disabled', '');
  renderGenResult();
  try {
    gen.result = await API.post('/generator/generate', genBody(extra));
  } catch (e) {
    gen.result = null;
    gen.error = e;
  }
  gen.busy = false;
  const btn = document.getElementById('gen-go');
  if (btn) { btn.removeAttribute('disabled'); btn.querySelector('span').textContent = t('gen.generate'); }
  renderGenResult();
  document.getElementById('gen-result')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

// ---------------------------------------------------------------------------
// Result
// ---------------------------------------------------------------------------
function genName(res) {
  const r = res.resolved;
  const code = n => GEN_ENEMY_CODE[n] || (n || '').slice(0, 2).toUpperCase();
  const theater = tv('theater', r.theater || '').replace('North Africa', 'N.Africa').replace('Norte de África', 'N.África');
  const d = new Date(), p = n => String(n).padStart(2, '0');
  const stamp = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  const versus = r.enemy_nation ? `${code(r.nation)}-v-${code(r.enemy_nation)}` : code(r.nation);
  return `${t('gen.name_prefix')} ${versus} ${theater} ${stamp}`.replace(/\s+/g, ' ').trim();
}

function genLockBtn(cardId) {
  const on = gen.locks.has(cardId);
  return `<button type="button" class="btn btn-icon gen-lock ${on ? 'on' : ''}" data-lock="${cardId}" title="${esc(t(on ? 'gen.unlock' : 'gen.lock'))}" aria-pressed="${on}">${icon(on ? 'lock' : 'unlock')}</button>`;
}

function genSoldierCard(s) {
  const c = s.card, isPS = c.card_subtype === 'Player';
  const lm = gen.result.mission.loadout_modifier || 0;
  const used = isPS ? s.gear.reduce((a, g) => a + (['Weapon', 'Equipment'].includes(g.card.card_type)
    ? (g.card.loadout != null ? g.card.loadout : (g.card.resource_cost || 0)) * g.quantity : 0), 0) : 0;
  const eff = isPS ? (c.loadout || 0) + lm : null;
  const gear = s.gear.map(g => `<tr>
      <td><span ${cardImageAttr(g.card)}>${esc(g.card.name)}</span></td>
      <td class="text-muted">${esc(tv('card_type', g.card.card_type))}</td>
      <td class="text-muted">${g.card.resource_cost != null ? g.card.resource_cost + ' ' + esc(t('stat.rp')) : ''}</td>
      <td>${g.quantity > 1 ? '×' + g.quantity : ''}</td>
      <td class="gen-lock-cell">${genLockBtn(g.card.id)}</td></tr>`).join('');
  return `<div class="soldier-card">
    <div class="soldier-card-header">
      <div>${chipForSubtype(c.card_subtype, c.card_type)}
        <span class="soldier-name" ${cardImageAttr(c)}>${esc(c.name)}</span>
        <span class="soldier-number text-muted">(${esc(c.number)})</span></div>
      <span class="gen-rp"><span class="text-muted" style="font-size:13px">${c.resource_cost != null ? c.resource_cost + ' ' + esc(t('stat.rp')) : ''}</span>${genLockBtn(c.id)}</span>
    </div>
    <div class="soldier-stats">
      ${c.health != null ? `<span>${esc(t('stat.hp'))} ${c.health}</span>` : ''}
      ${c.cover != null ? `<span>${esc(t('stat.cover'))} ${c.cover}</span>` : ''}
      ${c.movement != null ? `<span>${esc(t('stat.move'))} ${c.movement}</span>` : ''}
      ${c.hth != null ? `<span>${esc(t('stat.hth'))} ${c.hth >= 0 ? '+' : ''}${c.hth}</span>` : ''}
    </div>
    ${isPS ? `<div class="text-muted" style="font-size:12px;margin-bottom:6px">${esc(t('stat.loadout'))}: ${used}/${eff}</div>` : ''}
    ${gear ? `<div class="default-gear-section"><div class="default-gear-label">${esc(t('squad.gear'))}</div><table class="gear-table">${gear}</table></div>` : ''}
  </div>`;
}

function genWhy(w) {
  const c = gen.result.soldiers.find(s => s.card.id === w.card_id)?.card;
  if (!c || w.code === 'gear') return '';
  const p = w.params;
  const text = w.code === 'ps'
    ? t('gen.why_ps', { name: c.name, hp: p.health ?? '–', mv: p.movement ?? '–', load: p.loadout ?? '–' })
    : t('gen.why_support', { name: c.name, type: tv('card_subtype', p.type), hp: p.health ?? '–', act: p.actions ?? '–', rp: p.rp });
  return `<li>${esc(text)}</li>`;
}

function genCheckRow(ch) {
  const ico = { ok: '✓', weak: '⚠', missing: '✗', unknown: '?' }[ch.status];
  return `<li class="gen-check-row gen-check-${ch.status}"><span class="gen-check-ico">${ico}</span>
    <span>${esc(t('gen.check.' + ch.key, ch.params))}</span></li>`;
}

function renderGenResult() {
  const box = document.getElementById('gen-result');
  if (!box) return;
  if (gen.busy) { box.innerHTML = `<div class="spinner-wrap"><div class="spinner"></div></div>`; return; }
  if (gen.error) {
    const e = gen.error, code = e.data && e.data.code;
    const msg = code ? t('gen.err.' + code, (e.data && e.data.params) || {}) : (e.error || t('err.server'));
    box.innerHTML = `<div class="alert alert-error">${esc(msg)}</div>`;
    return;
  }
  const res = gen.result;
  if (!res) {
    box.innerHTML = `<div class="gen-empty">
      <div class="gen-empty-title">${esc(t('gen.empty_title'))}</div>
      <p>${esc(t('gen.empty_text'))}</p>
      <ol><li>${esc(t('gen.empty_1'))}</li><li>${esc(t('gen.empty_2'))}</li><li>${esc(t('gen.empty_3'))}</li></ol></div>`;
    return;
  }
  const r = res.resolved, sp = res.spend;
  const pct = Math.min(100, Math.round(sp.rp_used / sp.budget * 100));
  const optimal = r.quality === 'optimal';
  const band = sp.band ? `<span class="mission-attr">${esc(t('gen.band', { range: sp.band.range, n: sp.band.hostiles }))}</span>` : '';
  const objName = res.objective ? res.objective.name : t('gen.no_objective');
  box.innerHTML = `
    <div class="gen-result-head">
      <div class="gen-head-top">
        <span class="gen-fit gen-fit-${res.fitness.label}" title="${esc(t('gen.fitness_tip'))}">${esc(t('gen.fit.' + res.fitness.label))} <small>${Math.round(res.fitness.score * 100)}</small></span>
        <span class="chip chip-mission">${esc(tv('nation', r.nation))}</span>
        <span class="chip">${esc(t(optimal ? 'gen.q_optimal' : 'gen.q_good'))}${r.twist ? ' · ' + esc(t('gen.twist.' + r.twist)) : ''}</span>
        <span class="chip" title="${esc(t('gen.seed_hint'))}">${esc(t('gen.seed'))} ${esc(r.seed)}</span>
      </div>
      <div class="gen-brief-line">
        <div><span class="gen-k">${esc(t('gen.mission'))}</span> <strong ${cardImageAttr(res.mission)}>${esc(res.mission.name)}</strong>
          <span class="text-muted">· ${esc(tv('theater', r.theater || ''))} · ${res.mission.time ?? '?'} ${esc(t('gen.turns'))}</span></div>
        <div><span class="gen-k">${esc(t('gen.objective'))}</span> <strong ${res.objective ? cardImageAttr(res.objective) : ''}>${esc(objName)}</strong></div>
        <div><span class="gen-k">${esc(t('gen.enemy'))}</span> ${r.enemy_nation ? esc(tv('nation', r.enemy_nation)) : '—'} · ${esc(t(r.hostile_level === 'elite' ? 'gen.level_e' : 'gen.level_f'))}</div>
      </div>
      <div class="gen-rpbar"><div class="gen-rpfill ${pct > 100 ? 'over' : ''}" style="width:${pct}%"></div></div>
      <div class="gen-rpline"><span><strong>${sp.rp_used}</strong> / ${sp.budget} ${esc(t('stat.rp'))}${sp.target < sp.budget ? ` <span class="text-muted">(${esc(t('gen.target_cap', { n: sp.target }))})</span>` : ''}</span>${band}</div>
      <div class="gen-keep"><button type="button" class="btn btn-sm btn-ghost" id="gen-keep">${esc(t('gen.keep'))}</button></div>
    </div>

    <h2 class="gen-h2">${esc(t('squad.soldiers'))} <span class="text-muted gen-count">${res.soldiers.length}</span></h2>
    <div class="soldiers-grid gen-soldiers">${res.soldiers.map(genSoldierCard).join('')}</div>
    <div class="gen-lock-hint text-muted">${esc(t('gen.lock_hint'))}</div>

    ${metricsSectionHtml({ metrics: res.metrics.metrics, sample: res.metrics.sample })}

    <div class="gen-two">
      <div class="gen-box"><h3>${esc(t('gen.checks'))}</h3>
        <ul class="gen-list">${res.checks.map(genCheckRow).join('')}</ul></div>
      <div class="gen-box"><h3>${esc(t('gen.why'))}</h3>
        <ul class="gen-list">${res.why.map(genWhy).join('')}</ul></div>
    </div>
    ${res.warnings.length ? `<div class="alert alert-warning"><ul>${res.warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ul></div>` : ''}
    <p class="gen-modules text-muted">${icon('box')} ${esc(t('gen.built_from', { n: res.required_modules.length }))}
      ${res.required_modules.map(m => `<span class="chip">${esc(tv('module', m))}</span>`).join(' ')}</p>
    <p class="text-muted gen-engine">${esc(t('gen.engine_note'))}</p>

    <div class="gen-save">
      <div class="form-field gen-field" style="margin:0"><label for="gen-name">${esc(t('gen.squad_name'))}</label>
        <input type="text" id="gen-name" maxlength="120" value="${esc(gen.resumeName || genName(res))}" style="max-width:none;width:100%"></div>
      <div class="gen-actions">
        <button type="button" class="btn btn-ghost" id="gen-again">${icon('refresh')}<span>${esc(t(optimal ? 'gen.different' : 'gen.regenerate'))}</span></button>
        <button type="button" class="btn btn-ghost" id="gen-open">${icon('edit')}<span>${esc(t('gen.open_builder'))}</span></button>
        <button type="button" class="btn btn-primary" id="gen-save">${icon('save')}<span>${esc(t('gen.save_draft'))}</span></button>
      </div>
    </div>
    <div id="gen-save-msg"></div>`;
  wireGenResult(box, res);
}

function wireGenResult(box, res) {
  box.querySelectorAll('[data-lock]').forEach(b => b.addEventListener('click', () => {
    const id = parseInt(b.dataset.lock);
    gen.locks.has(id) ? gen.locks.delete(id) : gen.locks.add(id);
    box.querySelectorAll(`[data-lock="${id}"]`).forEach(x => {
      const on = gen.locks.has(id);
      x.classList.toggle('on', on); x.setAttribute('aria-pressed', on);
      x.innerHTML = icon(on ? 'lock' : 'unlock'); x.title = t(on ? 'gen.unlock' : 'gen.lock');
    });
  }));
  box.querySelector('#gen-keep')?.addEventListener('click', () => {
    const r = res.resolved;
    gen.form.nation = r.nation; gen.form.mission = String(r.mission_card_id);
    gen.form.objective = r.objective_card_id ? String(r.objective_card_id) : 'random';
    gen.form.seed = r.seed;
    genSaveForm(); renderGenForm();
  });
  box.querySelector('#gen-again').addEventListener('click', () => {
    const r = res.resolved;
    // Optimal always answers the same: "show a different one" switches to Good enough with a new seed
    if (r.quality === 'optimal') gen.form.quality = 'good_enough';
    gen.form.seed = '';
    // keep the resolved scenario so only the squad changes
    gen.form.nation = r.nation; gen.form.mission = String(r.mission_card_id);
    gen.form.objective = r.objective_card_id ? String(r.objective_card_id) : 'random';
    genSaveForm(); renderGenForm();
    runGenerate();
  });
  box.querySelector('#gen-open').addEventListener('click', () => {
    pendingBuilderDraft = {
      refresh: true,
      name: box.querySelector('#gen-name').value.trim(),
      nation: res.resolved.nation,
      notes: genFooter(res),
      mission: res.mission,
      objectives: res.objective ? [res.objective] : [],
      situation: null,
      soldiers: res.soldiers.map(s => ({ card: s.card, gear: s.gear, default_gear: s.default_gear })),
    };
    navigate('builder');
  });
  box.querySelector('#gen-save').addEventListener('click', async () => {
    if (!currentUser) {
      loginToSave('generator', '/generator', { form: gen.form, result: gen.result, locks: [...gen.locks], name: box.querySelector('#gen-name').value });
      return;
    }
    const btn = box.querySelector('#gen-save'), msg = box.querySelector('#gen-save-msg');
    btn.disabled = true;
    try {
      const out = await API.post('/squads', Object.assign({}, res.squad, {
        name: box.querySelector('#gen-name').value.trim() || genName(res),
        notes: genFooter(res), status: 'draft',
      }));
      navigate('squads/' + out.squad.id);
    } catch (e) {
      btn.disabled = false;
      msg.innerHTML = alertHtml(e.error || t('err.server'));
    }
  });
}

function genFooter(res) {
  const r = res.resolved;
  return t('gen.footer', { quality: t(r.quality === 'optimal' ? 'gen.q_optimal' : 'gen.q_good'), seed: r.seed, v: r.engine_version });
}
