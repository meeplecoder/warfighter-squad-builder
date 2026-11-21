// Bug reports — admin-only table of every report submitted from the header form. Backend: GET /api/feedback.
register('bugreports', async function () {
  if (!requireLogin()) return;
  if (!isAdmin()) { setMain(`<div class="alert alert-warning">${esc(t('tr.admin_only'))}</div>`); return; }
  showSpinner();
  let reports;
  try { reports = (await API.get('/feedback')).reports; } catch (e) { showError(e.error || t('common.failed')); return; }
  const rows = reports.map(r => `<tr>
      <td class="user-date" style="white-space:nowrap">${esc(fmtDate(r.created_at))}</td>
      <td>${esc(r.username)}</td>
      <td>${esc(t('fb.kind.' + r.kind))}</td>
      <td class="text-muted">${esc(r.page || '')}</td>
      <td style="white-space:pre-wrap;word-break:break-word">${esc(r.text)}</td>
    </tr>`).join('');
  setMain(`
    <h1 class="page-title" style="margin-bottom:10px">${esc(t('bugs.title'))}</h1>
    <div class="exp-summary"><strong>${esc(t('bugs.count', { n: reports.length }))}</strong></div>
    ${reports.length ? `<div class="table-scroll"><table class="data-table"><thead><tr>
      ${['date', 'user', 'type', 'page', 'text'].map(k => `<th>${esc(t('bugs.' + k))}</th>`).join('')}
    </tr></thead><tbody>${rows}</tbody></table></div>` : `<p class="text-muted">${esc(t('bugs.empty'))}</p>`}`);
});
