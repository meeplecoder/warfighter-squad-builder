// Bug reports — admin-only table of every report submitted from the header form. Backend: GET /api/feedback.
register('bugreports', async function () {
  if (!requireLogin()) return;
  if (!isAdmin()) { setMain(`<div class="alert alert-warning">${esc(t('tr.admin_only'))}</div>`); return; }
  showSpinner();
  let reports;
  try { reports = (await API.get('/feedback')).reports; } catch (e) { showError(e.error || t('common.failed')); return; }
  const STATUSES = ['open', 'closed', 'dismissed'];
  const rows = reports.map(r => `<tr>
      <td style="white-space:nowrap">#${r.id}</td>
      <td class="user-date" style="white-space:nowrap">${esc(fmtDate(r.created_at))}</td>
      <td>${esc(r.username)}</td>
      <td>${esc(t('fb.kind.' + r.kind))}</td>
      <td class="text-muted">${esc(r.page || '')}</td>
      <td style="white-space:pre-wrap;word-break:break-word">${esc(r.text)}</td>
      <td><select class="bug-status" data-id="${r.id}" aria-label="${esc(t('bugs.status'))}">${STATUSES.map(s =>
        `<option value="${s}"${s === r.status ? ' selected' : ''}>${esc(t('bugs.status.' + s))}</option>`).join('')}</select></td>
    </tr>`).join('');
  setMain(`
    <h1 class="page-title" style="margin-bottom:10px">${esc(t('bugs.title'))}</h1>
    <div class="exp-summary"><strong>${esc(t('bugs.count', { n: reports.length }))}</strong></div>
    ${reports.length ? `<div class="table-scroll"><table class="data-table"><thead><tr>
      ${['id', 'date', 'user', 'type', 'page', 'text', 'status'].map(k => `<th>${esc(t('bugs.' + k))}</th>`).join('')}
    </tr></thead><tbody>${rows}</tbody></table></div>` : `<p class="text-muted">${esc(t('bugs.empty'))}</p>`}`);
  document.querySelectorAll('.bug-status').forEach(sel => sel.addEventListener('change', async () => {
    const prev = reports.find(r => String(r.id) === sel.dataset.id);
    try {
      await API.put('/feedback/' + sel.dataset.id, { status: sel.value });
      prev.status = sel.value;
    } catch (e) {
      sel.value = prev.status;
      showError(e.error || t('common.failed'));
    }
  }));
});
