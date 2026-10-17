// ---------------------------------------------------------------------------
// Statistics — admin-only: anonymous visitors / page views per day and per section (own counters, no tracker).
// Backend: /api/stats/report. Uses app.js helpers (register, setMain, API, t, tn, esc, ...).
// ---------------------------------------------------------------------------
const statsState = { days: 30 };

register('stats', async function () {
  if (!requireLogin()) return;
  if (!isAdmin()) { setMain(`<div class="alert alert-warning">${esc(t('tr.admin_only'))}</div>`); return; }
  showSpinner();
  let r;
  try { r = await API.get('/stats/report?days=' + statsState.days); }
  catch (e) { showError(e.error || t('common.failed')); return; }
  renderStats(r);
});

function statsChart(series) {
  const W = 720, H = 180, PAD = 22, n = series.length;
  const max = Math.max(1, ...series.map(s => Math.max(s.views, s.visitors)));
  const slot = (W - PAD) / n, bw = Math.max(1, slot * 0.38);
  const y = v => H - PAD - (v / max) * (H - PAD - 8);
  const bars = series.map((s, i) => {
    const x = PAD + i * slot + slot * 0.1;
    const tip = `${s.day}: ${s.visitors} ${t('stats.visitors')}, ${s.views} ${t('stats.views')}`;
    return `<g><title>${esc(tip)}</title>
      <rect x="${x.toFixed(1)}" y="${y(s.views).toFixed(1)}" width="${bw.toFixed(1)}" height="${(H - PAD - y(s.views)).toFixed(1)}" fill="var(--border)"/>
      <rect x="${(x + bw).toFixed(1)}" y="${y(s.visitors).toFixed(1)}" width="${bw.toFixed(1)}" height="${(H - PAD - y(s.visitors)).toFixed(1)}" fill="var(--accent)"/></g>`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" class="stats-chart" role="img" aria-label="${esc(t('stats.daily'))}">
    <line x1="${PAD}" y1="${H - PAD}" x2="${W}" y2="${H - PAD}" stroke="var(--border)"/>
    <text x="0" y="12" font-size="10" fill="var(--text-muted)">${max}</text>
    ${bars}
    <text x="${PAD}" y="${H - 6}" font-size="10" fill="var(--text-muted)">${esc(series[0].day)}</text>
    <text x="${W}" y="${H - 6}" font-size="10" text-anchor="end" fill="var(--text-muted)">${esc(series[n - 1].day)}</text>
  </svg>`;
}

function renderStats(r) {
  const sum = k => r.series.reduce((a, s) => a + s[k], 0);
  const today = r.series[r.series.length - 1];
  const kpi = (label, value, sub = '') =>
    `<div class="stats-kpi"><div class="stats-kpi-v">${value}</div><div class="stats-kpi-l">${esc(label)}</div>${sub ? `<div class="stats-kpi-s">${sub}</div>` : ''}</div>`;
  const top = Math.max(1, ...r.routes.map(x => x.views));
  const routeRows = r.routes.map(x => `<tr><td>${esc(t('stats.route.' + x.route))}</td>
      <td class="stats-bar-cell"><span class="stats-bar" style="width:${Math.round(x.views / top * 100)}%"></span></td>
      <td style="text-align:right">${x.views}</td></tr>`).join('');
  setMain(`
    <h1 class="page-title" style="margin-bottom:10px">${esc(t('stats.title'))}</h1>
    <div class="gen-seg" role="radiogroup" style="margin-bottom:14px">
      ${[7, 30, 90].map(d => `<label class="gen-seg-item"><input type="radio" name="stats-days" value="${d}" ${r.days === d ? 'checked' : ''}><span>${esc(t('stats.range_' + d))}</span></label>`).join('')}
    </div>
    <div class="stats-kpis">
      ${kpi(t('stats.visitors'), sum('visitors'), esc(t('stats.today')) + ': ' + today.visitors)}
      ${kpi(t('stats.views'), sum('views'), esc(t('stats.today')) + ': ' + today.views)}
      ${kpi(t('stats.signups'), sum('signups'))}
      ${kpi(t('stats.squads'), sum('squads'))}
    </div>
    <h3 style="margin:18px 0 6px">${esc(t('stats.daily'))}</h3>
    ${statsChart(r.series)}
    <div class="stats-legend"><span><i style="background:var(--accent)"></i>${esc(t('stats.visitors'))}</span><span><i style="background:var(--border)"></i>${esc(t('stats.views'))}</span></div>
    <h3 style="margin:18px 0 6px">${esc(t('stats.sections'))} · ${esc(t('stats.last_n', { n: r.days }))}</h3>
    <div class="table-scroll"><table class="data-table"><tbody>${routeRows || `<tr><td style="color:var(--text-muted)">${esc(t('stats.none'))}</td></tr>`}</tbody></table></div>
    <h3 style="margin:18px 0 6px">${esc(t('stats.totals'))}</h3>
    <div class="stats-kpis">
      ${kpi(t('stats.users'), r.totals.users)}${kpi(t('nav.squads'), r.totals.squads)}${kpi(t('stats.campaigns'), r.totals.campaigns)}
    </div>
    <p class="text-muted" style="margin-top:16px;font-size:.85rem">${esc(t('stats.note'))}</p>`);
  document.querySelectorAll('input[name=stats-days]').forEach(i => i.addEventListener('change', () => {
    statsState.days = parseInt(i.value, 10);
    routes.stats();
  }));
}
