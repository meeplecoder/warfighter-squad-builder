// ---------------------------------------------------------------------------
// Campaign designer — list, detail, editor (spec/09_campaigns.md). Uses app.js helpers.
// ---------------------------------------------------------------------------
const CAMPAIGN_FLOWS = ['linear', 'branching', 'free'];
const CAMPAIGN_LINK_CONDS = ['success', 'failure', 'always', 'choice'];
const CAMPAIGN_PERSISTENCE = ['xp', 'wounds', 'skills', 'gear', 'soldiers', 'casualties'];
// Quick-add rule blocks: a title + a hint shown as placeholder (no rules text imposed)
const CAMPAIGN_RULE_TEMPLATES = ['between', 'experience', 'casualties', 'hostiles', 'special', 'victory'];
const CAMPAIGN_MISSION_TEXTS = ['briefing', 'requirements', 'setup', 'victory', 'rewards', 'debrief'];

let campaignsActiveTab = 'community';
let campaignFilters = { my: { q: '', page: 1 }, community: { q: '', page: 1 } };
let campaignState = null;   // editor state

register('campaigns', async function(sub, action) {
  if (sub === 'new') { openCampaignEditor(null); return; }
  if (sub && action === 'edit') { openCampaignEditor(parseInt(sub)); return; }
  if (sub) { await showCampaignDetail(parseInt(sub)); return; }
  if (!currentUser) campaignsActiveTab = 'community';
  renderCampaignsShell();
});

// ---------------------------------------------------------------------------
// List
// ---------------------------------------------------------------------------
function renderCampaignsShell() {
  const myTab = currentUser
    ? `<button class="tab-btn ${campaignsActiveTab === 'my' ? 'active' : ''}" data-tab="my">${esc(t('campaigns.tab_my'))}</button>` : '';
  setMain(`
    <div class="flex justify-between items-center" style="margin-bottom:12px">
      <h1>${esc(t('campaigns.title'))}</h1>
      ${currentUser ? `<button class="btn btn-primary" id="new-campaign-btn">+ ${esc(t('campaigns.new'))}</button>` : ''}
    </div>
    <p class="text-muted" style="margin:-4px 0 12px;font-size:13px">${esc(t('campaigns.lead'))}</p>
    <div class="tabs" style="margin-bottom:16px">
      ${myTab}
      <button class="tab-btn ${campaignsActiveTab === 'community' ? 'active' : ''}" data-tab="community">${esc(t('campaigns.tab_community'))}</button>
    </div>
    <div id="campaigns-tab-content"></div>`);
  const main = document.getElementById('app-main');
  main.querySelector('#new-campaign-btn')?.addEventListener('click', () => navigate('campaigns/new'));
  main.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => {
    campaignsActiveTab = btn.dataset.tab;
    main.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === campaignsActiveTab));
    loadCampaignList();
  }));
  loadCampaignList();
}

async function loadCampaignList() {
  const box = document.getElementById('campaigns-tab-content');
  if (!box) return;
  const mine = campaignsActiveTab === 'my' && currentUser;
  const f = campaignFilters[mine ? 'my' : 'community'];
  const params = new URLSearchParams({ page: f.page, sort: 'updated_at' });
  if (mine) params.set('user_id', currentUser.id);
  if (f.q) params.set('q', f.q);
  let data;
  try { data = await API.get('/campaigns?' + params); }
  catch (e) { box.innerHTML = alertHtml(e.error || t('common.failed')); return; }
  const rows = data.items.map(c => `
    <tr class="clickable" data-id="${c.id}">
      <td><strong>${esc(c.name)}</strong>${c.summary ? `<div class="text-muted" style="font-size:12px">${esc(c.summary)}</div>` : ''}</td>
      <td>${c.nation ? esc(nationLabel(c.nation)) : '—'}</td>
      <td>${esc(c.theater || '—')}</td>
      <td>${c.mission_count}</td>
      <td>${esc(t('campaign.flow.' + c.flow_type))}</td>
      ${mine ? `<td><span class="badge ${c.status === 'draft' ? 'badge-draft' : 'badge-ok'}">${esc(tv('squad_status', c.status))}</span></td>`
             : `<td class="text-muted">${esc(c.owner.username)}</td>`}
      <td class="text-muted">${fmtDate(c.updated_at)}</td>
    </tr>`).join('');
  const hadFocus = document.activeElement?.id === 'campaign-q';
  box.innerHTML = `
    <div class="filter-bar" style="margin-bottom:8px">
      <input type="text" class="search-input" id="campaign-q" placeholder="${esc(t('campaigns.search_placeholder'))}" value="${esc(f.q)}" style="flex:1;min-width:160px">
    </div>
    <table class="data-table">
      <thead><tr>
        <th>${esc(t('col.name'))}</th><th>${esc(t('col.nation'))}</th><th>${esc(t('stat.theater'))}</th>
        <th>${esc(t('campaign.missions'))}</th><th>${esc(t('campaign.flow'))}</th>
        <th>${esc(t(mine ? 'col.status' : 'campaign.author'))}</th><th>${esc(t('col.updated'))}</th>
      </tr></thead>
      <tbody>${rows || `<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">${esc(t(mine ? 'campaigns.none_mine' : 'campaigns.none'))}</td></tr>`}</tbody>
    </table>
    ${paginationHtml(data.page, data.pages)}`;
  const q = box.querySelector('#campaign-q');
  if (hadFocus) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  q.addEventListener('input', e => {
    clearTimeout(q._t);
    q._t = setTimeout(() => { f.q = e.target.value; f.page = 1; loadCampaignList(); }, 300);
  });
  box.querySelectorAll('tr[data-id]').forEach(r => r.addEventListener('click', () => navigate('campaigns/' + r.dataset.id)));
  box.querySelectorAll('[data-pg]').forEach(b => b.addEventListener('click', () => { f.page = parseInt(b.dataset.pg); loadCampaignList(); }));
}

// ---------------------------------------------------------------------------
// Detail
// ---------------------------------------------------------------------------
function campaignText(text, mentions) {
  return text ? `<div class="campaign-text">${renderMentions(text, mentions)}</div>` : '';
}

function missionLabel(m, i) {
  return [m.code || String(i + 1), m.title || t('campaign.untitled_mission')].join(' · ');
}

async function showCampaignDetail(id) {
  showSpinner();
  let c;
  try { c = (await API.get('/campaigns/' + id)).campaign; }
  catch (e) { setMain(alertHtml(e.error || t('common.failed'))); return; }
  const mine = currentUser && currentUser.id === c.owner.id;
  const s = c.settings || {};
  const force = s.force || {};
  const byId = Object.fromEntries(c.missions.map((m, i) => [m.key, { m, i }]));

  const info = [
    c.nation ? [t('col.nation'), nationLabel(c.nation)] : null,
    c.theater ? [t('stat.theater'), c.theater] : null,
    c.enemy ? [t('campaign.enemy'), c.enemy] : null,
    c.period ? [t('campaign.period'), c.period] : null,
    [t('campaign.missions'), c.missions.length],
    [t('campaign.flow'), t('campaign.flow.' + c.flow_type)],
    force.squad_size ? [t('campaign.squad_size'), force.squad_size] : null,
  ].filter(Boolean).map(([k, v]) => `<span class="mission-attr">${esc(k)} <strong>${esc(v)}</strong></span>`).join('');

  const carries = CAMPAIGN_PERSISTENCE.filter(k => (s.persistence || {})[k]);
  const forceHtml = (force.restrictions || force.replacements || carries.length) ? `
    <section class="campaign-section">
      <h2>${esc(t('campaign.sec.force'))}</h2>
      ${carries.length ? `<div class="campaign-carry"><span class="text-muted">${esc(t('campaign.carry_over'))}:</span>
        ${carries.map(k => `<span class="chip">${esc(t('campaign.persist.' + k))}</span>`).join('')}</div>` : ''}
      ${force.restrictions ? `<h3>${esc(t('campaign.restrictions'))}</h3>${campaignText(force.restrictions, c.mentions)}` : ''}
      ${force.replacements ? `<h3>${esc(t('campaign.replacements'))}</h3>${campaignText(force.replacements, c.mentions)}` : ''}
    </section>` : '';

  const rulesHtml = (s.rules || []).length ? `
    <section class="campaign-section">
      <h2>${esc(t('campaign.sec.rules'))}</h2>
      ${s.rules.map(r => `${r.title ? `<h3>${esc(r.title)}</h3>` : ''}${campaignText(r.body, c.mentions)}`).join('')}
    </section>` : '';

  const condIcon = { success: '✔', failure: '✖', always: '→', choice: '⇄' };
  const missionsHtml = c.missions.map((m, i) => {
    const card = m.mission;
    const out = c.links.filter(l => l.from === m.key);
    const stats = card ? [
      `${m.rp_override ?? card.resources} ${t('stat.rp')}${m.rp_override != null ? ` <span class="text-muted">(${card.resources})</span>` : ''}`,
      card.time != null || m.time_override != null ? `${m.time_override ?? card.time} ${t('stat.turns')}` : null,
      card.objective_position != null ? `${t('stat.obj_loc_short')}: ${card.objective_position}` : null,
      `${t('stat.loadout')}: ${(v => (v >= 0 ? '+' : '') + v)(m.loadout_override ?? card.loadout_modifier ?? 0)}`,
    ].filter(Boolean).join(' · ') : '';
    const branches = c.flow_type === 'branching' ? `
      <div class="campaign-branches">
        ${m.is_entry ? `<span class="chip chip-entry">${esc(t('campaign.entry'))}</span>` : ''}
        ${out.length ? out.map(l => {
          const target = byId[l.to];
          return `<a class="campaign-branch cond-${l.condition}" href="#campaign-m-${esc(l.to)}">${condIcon[l.condition]} ${esc(t('campaign.cond.' + l.condition))}${l.label ? ` (${esc(l.label)})` : ''} → ${esc(target ? missionLabel(target.m, target.i) : '?')}</a>`;
        }).join('') : `<span class="chip">${esc(t('campaign.end'))}</span>`}
      </div>` : '';
    return `
      <article class="campaign-mission" id="campaign-m-${esc(m.key)}">
        <div class="campaign-mission-head">
          <span class="campaign-mission-code">${esc(m.code || String(i + 1))}</span>
          <h3>${esc(m.title || t('campaign.untitled_mission'))}</h3>
        </div>
        ${card ? `<div class="campaign-mission-card"><span ${cardImageAttr(card)}><a href="#/cards/${card.id}">${esc(card.name)}</a></span>${customMissionChip(card)}
          ${card.mission_type && card.mission_type !== 'Standard' ? `<span class="obj-type-badge" style="margin-left:6px">${esc(tv('card_subtype', card.mission_type))}</span>` : ''}
          <span class="text-muted" style="font-size:12px;margin-left:6px">${stats}</span></div>` : ''}
        ${m.objective ? `<div class="campaign-mission-meta"><span class="text-muted">${esc(t('campaign.objective'))}:</span>
          <span ${cardImageAttr(m.objective)}><a href="#/cards/${m.objective.id}">${esc(m.objective.name)}</a></span></div>` : ''}
        ${m.situation ? `<div class="campaign-mission-meta"><span class="text-muted">${esc(t('squad.situation'))}:</span>
          <span ${cardImageAttr(m.situation)}><a href="#/cards/${m.situation.id}">${esc(m.situation.name)}</a></span></div>` : ''}
        ${m.squad ? `<div class="campaign-mission-meta"><span class="text-muted">${esc(t('campaign.squad'))}:</span>
          <a href="#/squads/${m.squad.id}">${esc(m.squad.name)}</a> <span class="text-muted">· ${m.squad.rp_total} ${esc(t('stat.rp'))}</span></div>` : ''}
        ${CAMPAIGN_MISSION_TEXTS.map(f => m[f] ? `<h4>${esc(t('campaign.m.' + f))}</h4>${campaignText(m[f], c.mentions)}` : '').join('')}
        ${branches}
      </article>`;
  }).join('');

  const outcomes = s.outcomes || [];
  const resolutionHtml = (s.scoring || outcomes.length) ? `
    <section class="campaign-section">
      <h2>${esc(t('campaign.sec.resolution'))}</h2>
      ${campaignText(s.scoring, c.mentions)}
      ${outcomes.length ? `<table class="data-table" style="margin-top:8px">
        <thead><tr><th>${esc(t('campaign.outcome'))}</th><th>${esc(t('campaign.condition'))}</th><th>${esc(t('campaign.epilogue'))}</th></tr></thead>
        <tbody>${outcomes.map(o => `<tr><td><strong>${esc(o.label || '')}</strong></td><td>${esc(o.condition || '')}</td><td>${o.epilogue ? renderMentions(o.epilogue, c.mentions) : ''}</td></tr>`).join('')}</tbody>
      </table>` : ''}
    </section>` : '';

  setMain(`
    <div class="campaign-detail">
      <div class="flex justify-between items-center" style="gap:8px;flex-wrap:wrap">
        <div>
          <a href="#/campaigns" class="text-muted" style="font-size:12px">← ${esc(t('campaigns.title'))}</a>
          <h1 style="margin:4px 0">${esc(c.name)}
            ${c.status === 'draft' ? `<span class="badge badge-draft" style="vertical-align:middle">${esc(tv('squad_status', 'draft'))}</span>` : ''}</h1>
          <div class="text-muted" style="font-size:12px">${esc(t('campaign.by', { user: c.owner.username }))} · ${fmtDate(c.updated_at)}</div>
        </div>
        ${mine ? `<span class="flex" style="gap:6px">
          <button class="btn btn-ghost" id="campaign-edit-btn">${esc(t('common.edit'))}</button>
          <button class="btn btn-ghost" id="campaign-delete-btn">${esc(t('common.delete'))}</button></span>` : ''}
      </div>
      ${c.summary ? `<p class="campaign-summary">${esc(c.summary)}</p>` : ''}
      <div class="mission-attrs" style="margin:8px 0">${info}</div>
      ${c.modules.length ? `<div class="campaign-carry"><span class="text-muted">${esc(t('campaign.modules'))}:</span>
        ${c.modules.map(mod => `<span class="chip">${esc(tv('module', mod))}</span>`).join('')}</div>` : ''}
      ${c.intro ? `<section class="campaign-section campaign-intro">${campaignText(c.intro, c.mentions)}</section>` : ''}
      ${forceHtml}
      ${rulesHtml}
      <section class="campaign-section">
        <h2>${esc(t('campaign.sec.missions'))}</h2>
        <p class="text-muted" style="font-size:12px">${esc(t('campaign.flow_hint.' + c.flow_type))}</p>
        ${missionsHtml || `<p class="text-muted">${esc(t('campaign.no_missions'))}</p>`}
      </section>
      ${resolutionHtml}
    </div>`);
  const main = document.getElementById('app-main');
  main.querySelector('#campaign-edit-btn')?.addEventListener('click', () => navigate(`campaigns/${c.id}/edit`));
  main.querySelector('#campaign-delete-btn')?.addEventListener('click', async () => {
    if (!confirm(t('campaign.confirm_delete', { name: c.name }))) return;
    try { await API.delete('/campaigns/' + c.id); navigate('campaigns'); }
    catch (e) { alert(e.error || t('common.failed')); }
  });
  main.querySelectorAll('a[href^="#campaign-m-"]').forEach(a => a.addEventListener('click', e => {
    e.preventDefault();
    document.getElementById(a.getAttribute('href').slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));
}

// ---------------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------------
let _campaignKeySeq = 0;
const newMissionKey = () => 'n' + (++_campaignKeySeq) + '-' + Date.now().toString(36);

function emptyCampaignMission() {
  return { key: newMissionKey(), code: '', title: '', mission: null, situation: null, objective: null, squad: null,
           rp_override: null, time_override: null, loadout_override: null, is_entry: false,
           briefing: '', requirements: '', setup: '', victory: '', rewards: '', debrief: '', _open: true };
}

async function openCampaignEditor(id) {
  if (!currentUser) { navigate('campaigns'); return; }
  showSpinner();
  let c = null;
  if (id) {
    try { c = (await API.get('/campaigns/' + id)).campaign; }
    catch (e) { setMain(alertHtml(e.error || t('common.failed'))); return; }
    if (c.owner.id !== currentUser.id) { navigate('campaigns/' + id); return; }
  }
  let mySquads = [];
  try { mySquads = (await API.get(`/squads?user_id=${currentUser.id}&per_page=200&sort=name&order=asc`)).items; } catch (_) {}
  const s = c?.settings || {};
  campaignState = {
    id: c?.id || null, status: c?.status || 'draft', mySquads,
    name: c?.name || '', summary: c?.summary || '', intro: c?.intro || '', nation: c?.nation || '',
    theater: c?.theater || '', enemy: c?.enemy || '', period: c?.period || '', flow_type: c?.flow_type || 'linear',
    force: { squad_size: s.force?.squad_size ?? 8, restrictions: s.force?.restrictions || '', replacements: s.force?.replacements || '' },
    persistence: s.persistence || { xp: true, wounds: true, skills: true, soldiers: true, casualties: true, gear: false },
    rules: (s.rules || []).map(r => ({ title: r.title || '', body: r.body || '' })),
    scoring: s.scoring || '',
    outcomes: (s.outcomes || []).map(o => ({ label: o.label || '', condition: o.condition || '', epilogue: o.epilogue || '' })),
    missions: (c?.missions || []).map(m => ({ ...m, briefing: m.briefing || '', requirements: m.requirements || '',
      setup: m.setup || '', victory: m.victory || '', rewards: m.rewards || '', debrief: m.debrief || '',
      code: m.code || '', title: m.title || '', _open: false })),
    links: (c?.links || []).map(l => ({ from: l.from, to: l.to, condition: l.condition, label: l.label || '' })),
  };
  if (!campaignState.missions.length) campaignState.missions.push(emptyCampaignMission());
  renderCampaignEditor();
}

function ceField(label, html, wide = false) {
  return `<div class="form-field${wide ? ' ce-wide' : ''}"><label>${esc(label)}</label>${html}</div>`;
}
function ceInput(path, value, attrs = '') {
  return `<input type="text" data-ce="${path}" value="${esc(value ?? '')}" ${attrs}>`;
}
function ceNumber(path, value, attrs = '') {
  return `<input type="number" data-ce="${path}" value="${value ?? ''}" ${attrs}>`;
}
function ceArea(path, value, rows = 3, placeholder = '') {
  return `<textarea data-ce="${path}" rows="${rows}" placeholder="${esc(placeholder)}" class="ce-mentions">${esc(value ?? '')}</textarea>`;
}

function renderCampaignMissionEditor(m, i) {
  const st = campaignState;
  const card = m.mission;
  const p = `missions.${i}`;
  const others = st.missions.map((o, j) => `<option value="${esc(o.key)}">${esc(missionLabel(o, j))}</option>`).join('');
  const links = st.links.map((l, li) => ({ l, li })).filter(x => x.l.from === m.key);
  const squadOpts = [`<option value="">${esc(t('campaign.no_squad'))}</option>`]
    .concat((m.squad && !st.mySquads.some(s => s.id === m.squad.id)) ? [`<option value="${m.squad.id}" selected>${esc(m.squad.name)}</option>`] : [])
    .concat(st.mySquads.map(s => `<option value="${s.id}" ${m.squad?.id === s.id ? 'selected' : ''}>${esc(s.name)}</option>`)).join('');
  return `
    <div class="ce-mission ${m._open ? 'open' : ''}" data-mi="${i}">
      <div class="ce-mission-head">
        <button class="btn btn-sm btn-ghost ce-toggle" data-act="toggle" data-mi="${i}">${m._open ? '▾' : '▸'}</button>
        <strong class="ce-mission-title">${esc(missionLabel(m, i))}</strong>
        ${card ? `<span class="text-muted" style="font-size:12px">${cardName(card)}${customMissionChip(card)}</span>`
               : `<span class="text-danger" style="font-size:12px">${esc(t('campaign.no_card'))}</span>`}
        ${st.flow_type === 'branching' && m.is_entry ? `<span class="chip chip-entry">${esc(t('campaign.entry'))}</span>` : ''}
        <span style="flex:1"></span>
        <button class="btn btn-sm btn-ghost" data-act="up" data-mi="${i}" ${i === 0 ? 'disabled' : ''} title="${esc(t('campaign.move_up'))}">↑</button>
        <button class="btn btn-sm btn-ghost" data-act="down" data-mi="${i}" ${i === st.missions.length - 1 ? 'disabled' : ''} title="${esc(t('campaign.move_down'))}">↓</button>
        <button class="btn btn-sm btn-ghost" data-act="dup" data-mi="${i}" title="${esc(t('campaign.duplicate'))}">⧉</button>
        <button class="btn btn-sm btn-ghost" data-act="del" data-mi="${i}" title="${esc(t('common.delete'))}">✕</button>
      </div>
      ${m._open ? `
      <div class="ce-mission-body ce-grid">
        ${ceField(t('campaign.m.code'), ceInput(`${p}.code`, m.code, 'maxlength="20" placeholder="1"'))}
        ${ceField(t('campaign.m.title'), ceInput(`${p}.title`, m.title, 'maxlength="120"'))}
        ${ceField(t('col.mission'), `<div class="flex" style="gap:6px;flex-wrap:wrap;align-items:center">
            ${card ? `<span ${cardImageAttr(card)}><strong>${esc(card.name)}</strong></span>${customMissionChip(card)}
              <span class="text-muted" style="font-size:12px">${card.resources} ${esc(t('stat.rp'))}${card.time != null ? ` · ${card.time} ${esc(t('stat.turns'))}` : ''}</span>` : ''}
            <button class="btn btn-sm btn-ghost" data-act="pick-mission" data-mi="${i}">${esc(t(card ? 'common.change' : 'builder.select_mission'))}</button>
            <button class="btn btn-sm btn-ghost" data-act="custom-mission" data-mi="${i}">${esc(t('builder.custom_mission'))}</button>
          </div>`, true)}
        ${ceField(t('campaign.objective'), `<div class="flex" style="gap:6px;align-items:center">
            ${m.objective ? `<span class="chip" ${cardImageAttr(m.objective)}>${esc(m.objective.name)} <a href="#" data-act="del-obj" data-mi="${i}">✕</a></span>` : ''}
            <button class="btn btn-sm btn-ghost" data-act="pick-obj" data-mi="${i}">${esc(t(m.objective ? 'common.change' : 'campaign.add_objective'))}</button>
          </div>`)}
        ${ceField(t('squad.situation'), `<div class="flex" style="gap:6px;align-items:center">
            ${m.situation ? `<span class="chip" ${cardImageAttr(m.situation)}>${esc(m.situation.name)} <a href="#" data-act="del-sit" data-mi="${i}">✕</a></span>` : ''}
            <button class="btn btn-sm btn-ghost" data-act="pick-sit" data-mi="${i}">${esc(t(m.situation ? 'common.change' : 'campaign.add_situation'))}</button>
          </div>`)}
        ${ceField(t('campaign.squad'), `<select data-ce-squad="${i}">${squadOpts}</select>`)}
        ${ceField(t('campaign.m.rp_override'), ceNumber(`${p}.rp_override`, m.rp_override, `min="1" max="300" placeholder="${card?.resources ?? ''}"`))}
        ${ceField(t('campaign.m.time_override'), ceNumber(`${p}.time_override`, m.time_override, `min="1" max="50" placeholder="${card?.time ?? ''}"`))}
        ${ceField(t('campaign.m.loadout_override'), ceNumber(`${p}.loadout_override`, m.loadout_override, `min="-10" max="10" placeholder="${card?.loadout_modifier ?? ''}"`))}
        ${st.flow_type === 'branching' ? ceField(t('campaign.entry'), `<label class="ce-check"><input type="checkbox" data-ce-bool="${p}.is_entry" ${m.is_entry ? 'checked' : ''}> ${esc(t('campaign.entry_hint'))}</label>`) : ''}
        ${CAMPAIGN_MISSION_TEXTS.filter(f => f !== 'requirements' || st.flow_type !== 'linear').map(f =>
          ceField(t('campaign.m.' + f), ceArea(`${p}.${f}`, m[f], f === 'briefing' || f === 'debrief' ? 4 : 2, t('campaign.m.' + f + '_hint')), true)).join('')}
        ${st.flow_type === 'branching' ? ceField(t('campaign.next'), `
          <div class="ce-links">
            ${links.map(({ l, li }) => `<div class="ce-link-row">
              <select data-ce-link="${li}.condition">${CAMPAIGN_LINK_CONDS.map(cnd => `<option value="${cnd}" ${l.condition === cnd ? 'selected' : ''}>${esc(t('campaign.cond.' + cnd))}</option>`).join('')}</select>
              <span>→</span>
              <select data-ce-link="${li}.to">${others.replace(`value="${esc(l.to)}"`, `value="${esc(l.to)}" selected`)}</select>
              <input type="text" data-ce-link="${li}.label" value="${esc(l.label)}" placeholder="${esc(t('campaign.link_label'))}" maxlength="120">
              <button class="btn btn-sm btn-ghost" data-act="del-link" data-li="${li}">✕</button>
            </div>`).join('') || `<div class="text-muted" style="font-size:12px">${esc(t('campaign.no_links'))}</div>`}
            <button class="btn btn-sm btn-ghost" data-act="add-link" data-mi="${i}">+ ${esc(t('campaign.add_link'))}</button>
          </div>`, true) : ''}
      </div>` : ''}
    </div>`;
}

function renderCampaignEditor(errors = []) {
  const st = campaignState;
  const nationOpts = [`<option value="">—</option>`].concat(sortedNations(allNations).map(n =>
    `<option value="${esc(n)}" ${st.nation === n ? 'selected' : ''}>${esc(nationLabel(n))}</option>`)).join('');
  setMain(`
    <div class="campaign-editor">
      <div class="flex justify-between items-center" style="gap:8px;flex-wrap:wrap;margin-bottom:12px">
        <h1>${esc(t(st.id ? 'campaign.edit_title' : 'campaign.new_title'))}</h1>
        <span class="flex" style="gap:6px">
          <button class="btn btn-ghost" data-act="cancel">${esc(t('common.cancel'))}</button>
          <button class="btn btn-ghost" data-act="save-draft">${esc(t('campaign.save_draft'))}</button>
          <button class="btn btn-primary" data-act="publish">${esc(t(st.status === 'published' ? 'campaign.save_published' : 'campaign.publish'))}</button>
        </span>
      </div>
      <div id="ce-errors">${errors.length ? alertHtml(errors.join(' · ')) : ''}</div>

      <section class="ce-section">
        <h2>1 · ${esc(t('campaign.sec.overview'))}</h2>
        <div class="ce-grid">
          ${ceField(t('col.name'), ceInput('name', st.name, 'maxlength="120"'), true)}
          ${ceField(t('campaign.summary'), ceInput('summary', st.summary, `maxlength="500" placeholder="${esc(t('campaign.summary_hint'))}"`), true)}
          ${ceField(t('col.nation'), `<select data-ce="nation">${nationOpts}</select>`)}
          ${ceField(t('stat.theater'), ceInput('theater', st.theater, `placeholder="${esc(t('campaign.theater_hint'))}"`))}
          ${ceField(t('campaign.enemy'), ceInput('enemy', st.enemy, `placeholder="${esc(t('campaign.enemy_hint'))}"`))}
          ${ceField(t('campaign.period'), ceInput('period', st.period, `placeholder="${esc(t('campaign.period_hint'))}"`))}
          ${ceField(t('campaign.intro'), ceArea('intro', st.intro, 6, t('campaign.intro_hint')), true)}
        </div>
      </section>

      <section class="ce-section">
        <h2>2 · ${esc(t('campaign.sec.force'))}</h2>
        <div class="ce-grid">
          ${ceField(t('campaign.squad_size'), ceNumber('force.squad_size', st.force.squad_size, 'min="1" max="30"'))}
          ${ceField(t('campaign.carry_over'), `<div class="ce-checks">${CAMPAIGN_PERSISTENCE.map(k =>
            `<label class="ce-check"><input type="checkbox" data-ce-bool="persistence.${k}" ${st.persistence[k] ? 'checked' : ''}> ${esc(t('campaign.persist.' + k))}</label>`).join('')}</div>`, true)}
          ${ceField(t('campaign.restrictions'), ceArea('force.restrictions', st.force.restrictions, 2, t('campaign.restrictions_hint')), true)}
          ${ceField(t('campaign.replacements'), ceArea('force.replacements', st.force.replacements, 2, t('campaign.replacements_hint')), true)}
        </div>
      </section>

      <section class="ce-section">
        <h2>3 · ${esc(t('campaign.sec.rules'))}</h2>
        <p class="text-muted" style="font-size:12px">${esc(t('campaign.rules_hint'))}</p>
        ${st.rules.map((r, i) => `<div class="ce-rule">
          <div class="flex" style="gap:6px">${ceInput(`rules.${i}.title`, r.title, `maxlength="120" placeholder="${esc(t('campaign.rule_title'))}" style="flex:1"`)}
            <button class="btn btn-sm btn-ghost" data-act="del-rule" data-ri="${i}">✕</button></div>
          ${ceArea(`rules.${i}.body`, r.body, 3, r._hint || '')}
        </div>`).join('')}
        <div class="flex" style="gap:6px;flex-wrap:wrap;margin-top:6px">
          <button class="btn btn-sm btn-ghost" data-act="add-rule">+ ${esc(t('campaign.add_rule'))}</button>
          ${CAMPAIGN_RULE_TEMPLATES.map(k => `<button class="btn btn-sm btn-ghost" data-act="add-rule" data-tpl="${k}">+ ${esc(t('campaign.tpl.' + k))}</button>`).join('')}
        </div>
      </section>

      <section class="ce-section">
        <h2>4 · ${esc(t('campaign.sec.missions'))}</h2>
        <div class="ce-flow">
          ${CAMPAIGN_FLOWS.map(f => `<label class="ce-flow-opt ${st.flow_type === f ? 'active' : ''}">
            <input type="radio" name="ce-flow" value="${f}" ${st.flow_type === f ? 'checked' : ''}>
            <strong>${esc(t('campaign.flow.' + f))}</strong><span class="text-muted">${esc(t('campaign.flow_hint.' + f))}</span></label>`).join('')}
        </div>
        <div id="ce-missions">${st.missions.map(renderCampaignMissionEditor).join('')}</div>
        <button class="btn btn-ghost" data-act="add-mission" style="margin-top:8px">+ ${esc(t('campaign.add_mission'))}</button>
      </section>

      <section class="ce-section">
        <h2>5 · ${esc(t('campaign.sec.resolution'))}</h2>
        ${ceField(t('campaign.scoring'), ceArea('scoring', st.scoring, 3, t('campaign.scoring_hint')), true)}
        <label class="text-muted" style="font-size:12px">${esc(t('campaign.outcomes'))}</label>
        ${st.outcomes.map((o, i) => `<div class="ce-outcome">
          ${ceInput(`outcomes.${i}.label`, o.label, `maxlength="120" placeholder="${esc(t('campaign.outcome'))}"`)}
          ${ceInput(`outcomes.${i}.condition`, o.condition, `maxlength="300" placeholder="${esc(t('campaign.condition_hint'))}"`)}
          <button class="btn btn-sm btn-ghost" data-act="del-outcome" data-oi="${i}">✕</button>
          ${ceArea(`outcomes.${i}.epilogue`, o.epilogue, 2, t('campaign.epilogue_hint'))}
        </div>`).join('')}
        <button class="btn btn-sm btn-ghost" data-act="add-outcome" style="margin-top:6px">+ ${esc(t('campaign.add_outcome'))}</button>
      </section>
    </div>`);
  bindCampaignEditor();
}

function ceSetPath(path, value) {
  const parts = path.split('.');
  let obj = campaignState;
  for (let k = 0; k < parts.length - 1; k++) obj = obj[parts[k]];
  obj[parts[parts.length - 1]] = value;
}

function bindCampaignEditor() {
  const main = document.getElementById('app-main');
  const st = campaignState;
  main.querySelectorAll('[data-ce]').forEach(el => el.addEventListener('input', () => {
    const v = el.type === 'number' ? (el.value === '' ? null : el.value) : el.value;
    ceSetPath(el.dataset.ce, v);
    if (/^missions\.\d+\.(code|title)$/.test(el.dataset.ce)) {
      const i = +el.dataset.ce.split('.')[1];
      const head = main.querySelector(`.ce-mission[data-mi="${i}"] .ce-mission-title`);
      if (head) head.textContent = missionLabel(st.missions[i], i);
    }
  }));
  main.querySelectorAll('[data-ce-bool]').forEach(el => el.addEventListener('change', () => {
    ceSetPath(el.dataset.ceBool, el.checked);
    if (el.dataset.ceBool.endsWith('.is_entry')) renderCampaignEditor();
  }));
  main.querySelectorAll('[data-ce-squad]').forEach(el => el.addEventListener('change', () => {
    const m = st.missions[+el.dataset.ceSquad];
    const sq = st.mySquads.find(s => String(s.id) === el.value);
    m.squad = el.value ? (sq ? { id: sq.id, name: sq.name } : m.squad) : null;
  }));
  main.querySelectorAll('[data-ce-link]').forEach(el => el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', () => {
    const [li, f] = el.dataset.ceLink.split('.');
    st.links[+li][f] = el.value;
  }));
  main.querySelectorAll('input[name="ce-flow"]').forEach(el => el.addEventListener('change', () => {
    st.flow_type = el.value;
    if (el.value === 'branching' && st.missions.length && !st.missions.some(m => m.is_entry)) st.missions[0].is_entry = true;
    renderCampaignEditor();
  }));
  main.querySelectorAll('.ce-mentions').forEach(attachMentionAutocomplete);
  main.querySelectorAll('[data-act]').forEach(el => el.addEventListener('click', e => {
    e.preventDefault();
    campaignEditorAction(el.dataset.act, el.dataset);
  }));
}

function campaignEditorAction(act, d) {
  const st = campaignState;
  const i = d.mi != null ? +d.mi : null;
  const m = i != null ? st.missions[i] : null;
  switch (act) {
    case 'cancel': navigate(st.id ? 'campaigns/' + st.id : 'campaigns'); return;
    case 'save-draft': saveCampaign('draft'); return;
    case 'publish': saveCampaign('published'); return;
    case 'toggle': m._open = !m._open; break;
    case 'up': case 'down': {
      const j = act === 'up' ? i - 1 : i + 1;
      [st.missions[i], st.missions[j]] = [st.missions[j], st.missions[i]];
      break;
    }
    case 'dup': {
      const copy = { ...m, key: newMissionKey(), is_entry: false, _open: true,
                     title: m.title ? `${m.title} (${t('campaign.copy')})` : '' };
      st.missions.splice(i + 1, 0, copy);
      break;
    }
    case 'del':
      if (st.missions.length > 1 && !confirm(t('campaign.confirm_delete_mission', { name: missionLabel(m, i) }))) return;
      st.missions.splice(i, 1);
      st.links = st.links.filter(l => l.from !== m.key && l.to !== m.key);
      break;
    case 'add-mission': st.missions.push(emptyCampaignMission()); break;
    case 'pick-mission':
      openCampaignCardPicker('Mission', card => { m.mission = card; renderCampaignEditor(); }); return;
    case 'custom-mission':
      openCustomMissionDialog({ current: m.mission, onSaved: card => { m.mission = card; renderCampaignEditor(); } }); return;
    case 'pick-obj':
      openCampaignCardPicker('Objective', card => {
        m.objective = card;
        renderCampaignEditor();
      }); return;
    case 'del-obj': m.objective = null; break;
    case 'pick-sit': openCampaignCardPicker('Situation', card => { m.situation = card; renderCampaignEditor(); }); return;
    case 'del-sit': m.situation = null; break;
    case 'add-link': {
      const next = st.missions[i + 1] || m;
      st.links.push({ from: m.key, to: next.key, condition: 'success', label: '' });
      break;
    }
    case 'del-link': st.links.splice(+d.li, 1); break;
    case 'add-rule':
      st.rules.push(d.tpl ? { title: t('campaign.tpl.' + d.tpl), body: '', _hint: t('campaign.tpl_hint.' + d.tpl) } : { title: '', body: '' });
      break;
    case 'del-rule': st.rules.splice(+d.ri, 1); break;
    case 'add-outcome': st.outcomes.push({ label: '', condition: '', epilogue: '' }); break;
    case 'del-outcome': st.outcomes.splice(+d.oi, 1); break;
    default: return;
  }
  renderCampaignEditor();
}

async function saveCampaign(status) {
  const st = campaignState;
  const body = {
    status, name: st.name, summary: st.summary, intro: st.intro, nation: st.nation, theater: st.theater,
    enemy: st.enemy, period: st.period, flow_type: st.flow_type,
    settings: { force: st.force, persistence: st.persistence, scoring: st.scoring,
                rules: st.rules.map(({ title, body }) => ({ title, body })), outcomes: st.outcomes },
    missions: st.missions.map(m => ({
      key: m.key, code: m.code, title: m.title, mission_card_id: m.mission?.id || null,
      situation_card_id: m.situation?.id || null, objective_card_id: m.objective?.id || null,
      squad_id: m.squad?.id || null, rp_override: m.rp_override, time_override: m.time_override,
      loadout_override: m.loadout_override, is_entry: !!m.is_entry,
      briefing: m.briefing, requirements: m.requirements, setup: m.setup, victory: m.victory,
      rewards: m.rewards, debrief: m.debrief,
    })),
    links: st.flow_type === 'branching' ? st.links : [],
  };
  try {
    const r = st.id ? await API.put('/campaigns/' + st.id, body) : await API.post('/campaigns', body);
    navigate('campaigns/' + r.campaign.id);
  } catch (e) {
    renderCampaignEditor(e.data?.errors || [e.error || t('common.failed')]);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

// Small searchable card picker (modal) — any catalog card of a type; missions include your custom ones
function openCampaignCardPicker(category, onPick) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <h2>${esc(t('campaign.pick.' + category))}</h2>
      <input type="text" class="search-input" id="cp-q" placeholder="${esc(t('campaign.pick_search'))}" style="width:100%">
      <div id="cp-results" class="cp-results"><div class="spinner" style="margin:16px auto"></div></div>
      <div style="display:flex;justify-content:flex-end;margin-top:8px">
        <button class="btn btn-ghost btn-sm" id="cp-cancel">${esc(t('common.cancel'))}</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
  overlay.querySelector('#cp-cancel').addEventListener('click', close);
  const q = overlay.querySelector('#cp-q');
  const results = overlay.querySelector('#cp-results');
  let items = [], req = 0;
  const load = async () => {
    const my = ++req;
    const params = new URLSearchParams({ category, q: q.value, per_page: 30, sort: 'name' });
    if (category === 'Mission') params.set('include_mine', 'true');
    try {
      const data = await API.get('/cards?' + params);
      if (my !== req) return;
      items = data.items;
      results.innerHTML = items.length ? items.map((c, i) => `
        <div class="cp-row" data-i="${i}">
          <strong ${cardImageAttr(c)}>${esc(c.name)}</strong>${customMissionChip(c)}
          <span class="text-muted">${esc(tv('module', c.module))}${c.resources != null ? ` · ${c.resources} ${esc(t('stat.rp'))}` : ''}${c.objective_mechanic ? ` · ${esc(tv('card_subtype', c.objective_mechanic))}` : ''}</span>
        </div>`).join('') : `<div class="text-muted" style="padding:12px">${esc(t('campaign.pick_none'))}</div>`;
      results.querySelectorAll('.cp-row').forEach(row => row.addEventListener('click', async () => {
        let card = items[+row.dataset.i];
        try { card = (await API.get('/cards/' + card.id)).card; } catch (_) {}
        close();
        onPick(card);
      }));
    } catch (e) { results.innerHTML = alertHtml(e.error || t('common.failed')); }
  };
  q.addEventListener('input', () => { clearTimeout(q._t); q._t = setTimeout(load, 250); });
  q.focus();
  load();
}
