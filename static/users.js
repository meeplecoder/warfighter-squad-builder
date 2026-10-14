// ---------------------------------------------------------------------------
// Users — admin-only: list every account, enable / disable / delete it, edit any field (never read a password).
// Backend: /api/admin/users. Uses app.js helpers (register, setMain, API, icon, t, esc, ...).
// ---------------------------------------------------------------------------
const usersState = { items: [], q: '', status: 'all' };

register('users', async function (id) {
  if (!requireLogin()) return;
  if (!isAdmin()) { setMain(`<div class="alert alert-warning">${esc(t('tr.admin_only'))}</div>`); return; }
  if (id) return showUserDetail(parseInt(id, 10));
  showSpinner();
  try {
    usersState.items = (await API.get('/admin/users')).users;
  } catch (e) { showError(e.error || t('common.failed')); return; }
  renderUsers();
});

function userStatusBadge(st) {
  return `<span class="user-badge user-badge-${esc(st)}">${esc(t('users.status.' + st))}</span>`;
}

function usersVisible() {
  const q = usersState.q.trim().toLowerCase();
  return usersState.items.filter(u => {
    if (usersState.status !== 'all' && u.status !== usersState.status) return false;
    return !q || [u.username, u.full_name, u.email].some(v => (v || '').toLowerCase().includes(q));
  });
}

function renderUsers() {
  setMain(`
    <h1 class="page-title" style="margin-bottom:10px">${esc(t('users.title'))}</h1>
    <div class="exp-bar">
      <div class="exp-summary" id="users-summary"></div>
      <input type="search" id="users-q" class="exp-search" placeholder="${esc(t('users.search'))}" value="${esc(usersState.q)}">
      <div class="gen-seg exp-filter" role="radiogroup">
        ${[['all', 'users.f_all'], ['pending', 'users.f_pending'], ['enabled', 'users.f_enabled'], ['disabled', 'users.f_disabled']].map(([v, k]) =>
          `<label class="gen-seg-item"><input type="radio" name="users-f" value="${v}" ${usersState.status === v ? 'checked' : ''}><span>${esc(t(k))}</span></label>`).join('')}
      </div>
    </div>
    <div id="users-msg"></div>
    <div id="users-table"></div>`);
  const main = document.getElementById('app-main');
  drawUsers();
  main.querySelector('#users-q').addEventListener('input', e => { usersState.q = e.target.value; drawUsers(); });
  main.querySelectorAll('input[name=users-f]').forEach(r => r.addEventListener('change', () => { usersState.status = r.value; drawUsers(); }));
}

function drawUsers() {
  const list = usersVisible();
  document.getElementById('users-summary').innerHTML = `<strong>${esc(tn('users.count', list.length))}</strong>`;
  const rows = list.map(u => {
    const isAdminAcc = u.role === 'admin';
    const toggle = u.status === 'disabled' || u.status === 'pending'
      ? (u.status === 'pending'
        ? userIconBtn('enable', 'validate', t('users.approve'), u.id)
        : userIconBtn('enable', 'validate', t('users.enable'), u.id))
      : userIconBtn('disable', 'ban', t('users.disable'), u.id);
    return `<tr data-id="${u.id}">
      <td><a href="#/users/${u.id}" class="user-link">${esc(u.username)}</a>${isAdminAcc ? ` <span class="role-chip role-admin">${esc(t('role.admin'))}</span>` : ''}</td>
      <td>${esc(u.full_name || '')}</td>
      <td class="user-email">${esc(u.email)}</td>
      <td>${userStatusBadge(u.status)}</td>
      <td class="user-date">${esc(fmtDate(u.created_at))}</td>
      <td class="user-actions">${isAdminAcc ? '' : toggle + userIconBtn('delete', 'trash', t('common.delete'), u.id, true)}</td>
    </tr>`;
  }).join('');
  document.getElementById('users-table').innerHTML = `
    <div class="table-scroll"><table class="data-table users-table">
      <thead><tr><th>${esc(t('auth.username'))}</th><th>${esc(t('auth.full_name'))}</th><th>${esc(t('auth.email'))}</th>
        <th>${esc(t('col.status'))}</th><th>${esc(t('users.registered'))}</th><th></th></tr></thead>
      <tbody>${rows || `<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">${esc(t('users.none'))}</td></tr>`}</tbody>
    </table></div>`;
  document.querySelectorAll('#users-table [data-act]').forEach(b =>
    b.addEventListener('click', () => userRowAction(b.dataset.act, parseInt(b.dataset.id, 10))));
}

function userIconBtn(act, ic, label, id, danger = false) {
  return `<button type="button" class="btn-icon ${danger ? 'btn-icon-danger' : ''}" data-act="${act}" data-id="${id}" title="${esc(label)}" aria-label="${esc(label)}">${icon(ic)}</button>`;
}

async function userRowAction(act, id) {
  const u = usersState.items.find(x => x.id === id);
  if (!u) return;
  const msg = document.getElementById('users-msg');
  try {
    if (act === 'delete') {
      if (!confirm(t('users.confirm_delete', { name: u.username, squads: u.squads, campaigns: u.campaigns }))) return;
      await API.delete('/admin/users/' + id);
      usersState.items = usersState.items.filter(x => x.id !== id);
    } else {
      if (act === 'disable' && !confirm(t('users.confirm_disable', { name: u.username }))) return;
      const r = await API.put('/admin/users/' + id, { status: act === 'disable' ? 'disabled' : 'enabled' });
      Object.assign(u, r.user);
    }
    msg.innerHTML = '';
    drawUsers();
  } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
}

async function showUserDetail(id) {
  showSpinner();
  let u;
  try { u = (await API.get('/admin/users/' + id)).user; }
  catch (e) { showError(e.error || t('common.failed')); return; }
  const isAdminAcc = u.role === 'admin';
  setPageTitle(t('nav.users'), u.username);
  setMain(`
    <div class="flex" style="align-items:center;gap:12px;margin-bottom:14px">
      <a href="#/users" class="btn btn-ghost btn-sm">${icon('back')}<span>${esc(t('users.title'))}</span></a>
      <h1 class="page-title" style="margin:0">${esc(u.username)}</h1> ${userStatusBadge(u.status)}
    </div>
    <div class="profile-section user-detail">
      <div class="form-field"><label>${esc(t('auth.username'))}</label>
        <input type="text" id="ud-username" maxlength="30" value="${esc(u.username)}" ${isAdminAcc ? 'disabled' : ''}></div>
      <div class="form-field"><label>${esc(t('auth.full_name'))}</label>
        <input type="text" id="ud-name" maxlength="100" value="${esc(u.full_name || '')}"></div>
      <div class="form-field"><label>${esc(t('auth.email'))}</label>
        <input type="email" id="ud-email" maxlength="254" value="${esc(u.email)}"></div>
      <div class="form-field"><label>${esc(t('col.status'))}</label>
        <select id="ud-status" ${isAdminAcc ? 'disabled' : ''}>
          ${['pending', 'enabled', 'disabled'].map(s => `<option value="${s}" ${u.status === s ? 'selected' : ''}>${esc(t('users.status.' + s))}</option>`).join('')}
        </select></div>
      <div class="form-field"><label>${esc(t('header.language'))}</label>
        <select id="ud-lang">
          <option value="">—</option>
          ${I18N.SUPPORTED.map(l => `<option value="${l}" ${u.language === l ? 'selected' : ''}>${esc(I18N.NAMES[l])}</option>`).join('')}
        </select></div>
      <div class="form-field"><label>${esc(t('users.avatar'))}</label>
        <input type="text" id="ud-avatar" maxlength="500" value="${esc(u.avatar_url || '')}"></div>

      <h2 style="margin-top:18px">${esc(t('users.set_password'))}</h2>
      <p class="text-muted" style="font-size:13px;margin:0 0 8px">${esc(t('users.password_note'))}</p>
      <div class="form-field"><label>${esc(t('profile.new_password'))}</label>
        <input type="password" id="ud-pw" autocomplete="new-password" maxlength="128"></div>
      <div class="form-field"><label>${esc(t('auth.password_repeat'))}</label>
        <input type="password" id="ud-pw2" autocomplete="new-password" maxlength="128"></div>

      <dl class="user-facts">
        <dt>${esc(t('users.registered'))}</dt><dd>${esc(fmtDate(u.created_at))}</dd>
        <dt>${esc(t('users.email_verified'))}</dt><dd>${u.email_verified_at ? esc(fmtDate(u.email_verified_at)) : '—'}</dd>
        <dt>${esc(t('users.password_changed'))}</dt><dd>${u.password_changed_at ? esc(fmtDate(u.password_changed_at)) : (u.has_password ? '—' : esc(t('users.no_password')))}</dd>
        <dt>${esc(t('users.content'))}</dt><dd>${esc(tn('users.squads', u.squads))} · ${esc(tn('users.campaigns', u.campaigns))}</dd>
      </dl>

      <div class="flex" style="gap:8px;margin-top:14px">
        <button class="btn btn-primary" id="ud-save">${icon('save')}<span>${esc(t('common.save'))}</span></button>
        ${isAdminAcc ? '' : `<button class="btn btn-danger-ghost" id="ud-delete">${icon('trash')}<span>${esc(t('common.delete'))}</span></button>`}
      </div>
      <div id="ud-msg" style="margin-top:10px"></div>
    </div>`);

  const msg = document.getElementById('ud-msg');
  document.getElementById('ud-save').addEventListener('click', async () => {
    const pw = document.getElementById('ud-pw').value;
    if (pw && pw !== document.getElementById('ud-pw2').value) { msg.innerHTML = alertHtml(t('auth.password_mismatch')); return; }
    const body = {
      full_name: document.getElementById('ud-name').value,
      email: document.getElementById('ud-email').value,
      language: document.getElementById('ud-lang').value,
      avatar_url: document.getElementById('ud-avatar').value,
    };
    if (!isAdminAcc) { body.username = document.getElementById('ud-username').value; body.status = document.getElementById('ud-status').value; }
    if (pw) body.password = pw;
    try {
      await API.put('/admin/users/' + id, body);
      showUserDetail(id).then(() => {
        const m = document.getElementById('ud-msg');
        if (m) m.innerHTML = alertHtml(t('profile.saved'), 'success');
      });
    } catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
  });
  document.getElementById('ud-delete')?.addEventListener('click', async () => {
    if (!confirm(t('users.confirm_delete', { name: u.username, squads: u.squads, campaigns: u.campaigns }))) return;
    try { await API.delete('/admin/users/' + id); navigate('users'); }
    catch (e) { msg.innerHTML = alertHtml(e.error || t('common.failed')); }
  });
}
