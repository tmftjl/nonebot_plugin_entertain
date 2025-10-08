(() => {
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

  const toastBox = document.getElementById('toast');
  const loading = document.getElementById('loading');

  function showToast(msg, isErr = false) {
    const el = document.createElement('div');
    el.className = 'toast' + (isErr ? ' error' : '');
    el.textContent = String(msg ?? '');
    if (toastBox) toastBox.appendChild(el);
    else console[isErr ? 'error' : 'log'](msg);
    setTimeout(() => el.remove(), 3500);
  }
  function setLoading(v) { if (loading) loading.classList.toggle('hidden', !v); }

  function getQueryToken() {
    const p = new URLSearchParams(window.location.search);
    return p.get('token') || '';
  }
  function getToken() {
    const t = $('#token');
    return (t && t.value.trim()) || localStorage.getItem('mr_token') || getQueryToken();
  }
  function saveToken() {
    const t = $('#token');
    const v = (t && t.value.trim()) || '';
    localStorage.setItem('mr_token', v);
    showToast('Token 已保存');
  }

  async function api(path, opts = {}) {
    const t = getToken();
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (t) opts.headers['Authorization'] = 'Bearer ' + t;
    const qs = (!t ? ('?token=' + encodeURIComponent(getQueryToken())) : '');
    const r = await fetch('/member_renewal' + path + qs, opts);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const ctype = r.headers.get('content-type') || '';
    return ctype.includes('application/json') ? r.json() : r.text();
  }

  function maskCode(code) {
    if (!code) return '';
    const parts = String(code).split('-');
    if (parts.length < 2) return code;
    const head = parts[0];
    const tail = parts[1];
    return head + '-****' + tail.slice(-4);
  }

  function fmtDate(iso) {
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  }
  function daysRemain(iso) {
    try {
      const d = new Date(iso);
      const now = new Date();
      const ms = d.setHours(0,0,0,0) - now.setHours(0,0,0,0);
      return Math.round(ms / 86400000);
    } catch { return 0; }
  }

  const state = { raw: {}, list: [], sortBy: 'days', sortDir: 'asc', filter: 'all', keyword: '' };

  function buildList() {
    const rows = [];
    const raw = state.raw || {};
    for (const [k, v] of Object.entries(raw)) {
      if (k === 'generatedCodes' || typeof v !== 'object') continue;
      const expiry = v.expiry;
      const days = daysRemain(expiry);
      let status = v.status || 'active';
      if (days < 0) status = 'expired';
      else if (days === 0) status = 'today';
      else if (days <= 7) status = 'soon';
      rows.push({ group: k, expiry, days, status });
    }
    state.list = rows;
  }

  function applyFilterSort() {
    let arr = state.list.slice();
    if (state.filter === 'valid') arr = arr.filter(x => x.status !== 'expired');
    else if (state.filter !== 'all') arr = arr.filter(x => x.status === state.filter);
    if (state.keyword) arr = arr.filter(x => x.group.includes(state.keyword));
    const dir = state.sortDir === 'asc' ? 1 : -1;
    arr.sort((a,b) => {
      const f = state.sortBy;
      if (f === 'group') return (a.group.localeCompare(b.group)) * dir;
      if (f === 'status') return (a.status.localeCompare(b.status)) * dir;
      if (f === 'expiry') return ((a.expiry||'').localeCompare(b.expiry||'')) * dir;
      if (f === 'days') return (a.days - b.days) * dir;
      return 0;
    });
    return arr;
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = String(val);
  }

  function renderSummary() {
    const arr = state.list;
    const total = arr.length;
    const expired = arr.filter(x => x.status === 'expired').length;
    const today = arr.filter(x => x.status === 'today').length;
    const soon = arr.filter(x => x.status === 'soon').length + today;
    const active = total - expired - today - arr.filter(x => x.status === 'soon').length;
    setText('sumTotal', total);
    setText('sumActive', active);
    setText('sumSoon', soon);
    setText('sumExpired', expired);
  }

  function labelStatus(s) {
    if (s === 'expired') return '<span class="chip danger">已到期</span>';
    if (s === 'today') return '<span class="chip warn">今天到期</span>';
    if (s === 'soon') return '<span class="chip warn">即将到期</span>';
    return '<span class="chip ok">有效</span>';
  }

  function renderTable() {
    const tbody = $('#groups tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    const arr = applyFilterSort();
    for (const x of arr) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><input type="checkbox" data-gid="${x.group}"></td>
        <td>${x.group}</td>
        <td>${labelStatus(x.status)}</td>
        <td>${fmtDate(x.expiry)}</td>
        <td>${x.days}</td>
        <td>
          <button class="btn secondary" data-act="remind" data-gid="${x.group}">提醒</button>
          <button class="btn" data-act="extend7" data-gid="${x.group}">+7天</button>
          <button class="btn danger" data-act="leave" data-gid="${x.group}">退群</button>
        </td>
      `;
      tbody.appendChild(tr);
    }
  }

  function renderCodes() {
    const box = document.getElementById('codes');
    if (!box) return;
    box.innerHTML = '';
    const map = (state.raw && state.raw.generatedCodes) || {};
    const entries = Object.entries(map);
    const panel = document.getElementById('codesPanel');
    if (panel) panel.classList.toggle('hidden', entries.length === 0);
    for (const [code, meta] of entries) {
      const item = document.createElement('div');
      item.className = 'code-item';
      item.innerHTML = `
        <div>
          <div class="mask">${maskCode(code)}</div>
          <div class="meta">${meta.length}${meta.unit} · 生成于 ${fmtDate(meta.generated_time)}</div>
        </div>
        <div>
          <button class="btn secondary" data-copy="${code}">复制</button>
        </div>
      `;
      box.appendChild(item);
    }
  }

  function getSelected() {
    return $$('#groups tbody input[type="checkbox"]:checked').map(x => x.getAttribute('data-gid'));
  }

  async function doRemind(gid) {
    await api('/remind', { method: 'POST', body: JSON.stringify({ group_id: gid }) });
  }
  async function doLeave(gid) {
    await api('/leave', { method: 'POST', body: JSON.stringify({ group_id: gid }) });
  }
  async function doExtend(gid, length, unit) {
    await api('/extend', { method: 'POST', body: JSON.stringify({ group_id: gid, length, unit }) });
  }
  async function doGenerate(length, unit) {
    return api('/generate', { method: 'POST', body: JSON.stringify({ length, unit }) });
  }

  async function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
  }

  async function reload() {
    setLoading(true);
    try {
      const data = await api('/data');
      state.raw = data || {};
      buildList();
      renderSummary();
      renderTable();
      renderCodes();
    } catch (e) {
      showToast('加载失败: ' + (e && e.message ? e.message : e), true);
    } finally {
      setLoading(false);
    }
  }

  function bindEvents() {
    const rb = document.getElementById('refreshBtn');
    if (rb) rb.addEventListener('click', () => reload());
    const sf = document.getElementById('filter');
    if (sf) sf.addEventListener('change', (e) => { state.filter = e.target.value; renderTable(); });
    const ss = document.getElementById('search');
    if (ss) ss.addEventListener('input', (e) => { state.keyword = e.target.value.trim(); renderTable(); });
    const ca = document.getElementById('checkAll');
    if (ca) ca.addEventListener('change', (e) => { $$('#groups tbody input[type="checkbox"]').forEach(cb => cb.checked = e.target.checked); });
    $$('#groups thead th[data-sort]').forEach(th => {
      th.addEventListener('click', () => {
        const key = th.getAttribute('data-sort');
        if (state.sortBy === key) state.sortDir = (state.sortDir === 'asc' ? 'desc' : 'asc');
        else { state.sortBy = key; state.sortDir = 'asc'; }
        renderTable();
      });
    });
    const table = document.getElementById('groups');
    if (table) table.addEventListener('click', async (e) => {
      const btn = e.target.closest('button');
      if (!btn) return;
      const act = btn.getAttribute('data-act');
      const gid = btn.getAttribute('data-gid');
      try {
        if (act === 'remind') { await doRemind(gid); showToast('已提醒 ' + gid); }
        if (act === 'extend7') { await doExtend(gid, 7, '天'); showToast('已延长 7 天 · ' + gid); }
        if (act === 'leave') { await doLeave(gid); showToast('已退群 ' + gid); }
        reload();
      } catch (err) { showToast(err.message || err, true); }
    });
    const bRemind = document.getElementById('bulkRemind');
    if (bRemind) bRemind.addEventListener('click', async () => {
      const ids = getSelected();
      if (!ids.length) return showToast('未选择任何群');
      setLoading(true);
      try { for (const gid of ids) await doRemind(gid); showToast('已提醒 ' + ids.length + ' 个群'); reload(); }
      catch (e) { showToast(e.message || e, true); setLoading(false); }
    });
    const bLeave = document.getElementById('bulkLeave');
    if (bLeave) bLeave.addEventListener('click', async () => {
      const ids = getSelected();
      if (!ids.length) return showToast('未选择任何群');
      if (!confirm('确认退出选中的 ' + ids.length + ' 个群？')) return;
      setLoading(true);
      try { for (const gid of ids) await doLeave(gid); showToast('已退群 ' + ids.length + ' 个群'); reload(); }
      catch (e) { showToast(e.message || e, true); setLoading(false); }
    });
    const bExtend = document.getElementById('bulkExtend');
    if (bExtend) bExtend.addEventListener('click', async () => {
      const ids = getSelected();
      if (!ids.length) return showToast('未选择任何群');
      const length = parseInt($('#bulkLen')?.value || '0', 10);
      const unit = $('#bulkUnit')?.value || '天';
      setLoading(true);
      try { for (const gid of ids) await doExtend(gid, length, unit); showToast('已延长 ' + ids.length + ' 个群'); reload(); }
      catch (e) { showToast(e.message || e, true); setLoading(false); }
    });
    const gen = document.getElementById('gen');
    if (gen) gen.addEventListener('click', async () => {
      try {
        const length = parseInt($('#len')?.value || '0', 10);
        const unit = $('#unit')?.value || '天';
        const r = await doGenerate(length, unit);
        await copyText(r.code);
        showToast('已生成并复制：' + r.code.slice(0, 8) + '…');
        reload();
      } catch (e) { showToast(e.message || e, true); }
    });
    const codes = document.getElementById('codes');
    if (codes) codes.addEventListener('click', async (e) => {
      const btn = e.target.closest('button[data-copy]');
      if (!btn) return;
      const code = btn.getAttribute('data-copy');
      try { await copyText(code); showToast('已复制续费码'); }
      catch { showToast('复制失败', true); }
    });
    const saveBtn = document.getElementById('saveToken');
    if (saveBtn) saveBtn.addEventListener('click', saveToken);
  }

  async function main() {
    const t = localStorage.getItem('mr_token') || getQueryToken();
    const tok = document.getElementById('token');
    if (tok) tok.value = t;
    // 优化筛选项：仅展示 全部/有效/已过期
    const sf = document.getElementById('filter');
    if (sf) {
      sf.innerHTML = '<option value="all">全部</option>' +
                     '<option value="valid">有效</option>' +
                     '<option value="expired">已过期</option>';
    }
    bindEvents();
    reload();
  }

  window.addEventListener('DOMContentLoaded', main);
})();
