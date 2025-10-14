// ==================== Membership 控制台（UTF-8） ====================

// 全局状态
const state = {
  groups: [],
  stats: null,
  permissions: null,
  config: null,
  theme: localStorage.getItem('theme') || 'light',
  filter: 'all',
  keyword: '',
  statsSort: 'total_desc',
  statsKeyword: ''
};

// 工具函数
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
function showToast(message, type='info'){
  const c=$('#toast-container'); if(!c) return;
  const n=document.createElement('div');
  n.className=`toast toast-${type}`;
  n.textContent=String(message||'');
  c.appendChild(n);
  setTimeout(()=>n.classList.add('show'),10);
  setTimeout(()=>{ n.classList.remove('show'); setTimeout(()=>n.remove(), 250); }, 2500);
}
function showLoading(show=true){ const o=$('#loading-overlay'); if(o) o.classList.toggle('hidden', !show); }
function formatDate(s){ if(!s) return '-'; try{ const d=new Date(s); return d.toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});}catch{return s;}}
function daysRemaining(s){ try{ const e=new Date(s), n=new Date(); e.setHours(0,0,0,0); n.setHours(0,0,0,0); return Math.round((e-n)/86400000);}catch{return 0;} }
function getStatusLabel(days){ if(days<0) return '<span class="status-badge status-expired">已到期</span>'; if(days===0) return '<span class="status-badge status-today">今日到期</span>'; if(days<=7) return '<span class="status-badge status-soon">即将到期</span>'; return '<span class="status-badge status-active">有效</span>'; }
async function copyText(text){ try{ if(navigator.clipboard?.writeText){ await navigator.clipboard.writeText(String(text||'')); return true; } }catch{} try{ const ta=document.createElement('textarea'); ta.value=String(text||''); ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta); ta.focus(); ta.select(); const ok=document.execCommand('copy'); ta.remove(); return !!ok; }catch{} return false; }

// API
async function apiCall(path, options={}){
  const headers = {'Content-Type':'application/json', ...(options.headers||{})};
  const resp = await fetch(`/membership${path}`, { ...options, headers });
  if(!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
  const ct = resp.headers.get('content-type')||'';
  return ct.includes('application/json') ? resp.json() : resp.text();
}

// 主题
function toggleTheme(){
  state.theme = state.theme==='light' ? 'dark' : 'light';
  document.body.setAttribute('data-theme', state.theme);
  localStorage.setItem('theme', state.theme);
  const i=$('#theme-toggle .icon'); if(i) i.textContent = state.theme==='light' ? '🌞' : '🌙';
}

// 切换标签页
function switchTab(tab){
  $$('.nav-item').forEach(i=>i.classList.toggle('active', i.dataset.tab===tab));
  $$('.tab-content').forEach(c=>c.classList.toggle('active', c.id===`tab-${tab}`));
  if(tab==='dashboard') loadDashboard();
  if(tab==='renewal') loadRenewalData();
  if(tab==='stats') loadStatsData();
  if(tab==='permissions') loadPermissions();
  if(tab==='config') loadConfig();
}

// 仪表盘
async function loadDashboard(){
  try{
    const data=await apiCall('/data');
    state.groups = Object.entries(data)
      .filter(([k,v])=>k!=='generatedCodes'&&typeof v==='object')
      .map(([gid,info])=>{ const d=daysRemaining(info.expiry); let s='active'; if(d<0)s='expired'; else if(d===0)s='today'; else if(d<=7)s='soon'; return { gid, ...info, days:d, status:s };});
    $('#stat-active-groups').textContent=state.groups.length;
    $('#stat-valid-members').textContent=state.groups.filter(g=>g.status==='active').length;
    $('#stat-expiring-soon').textContent=state.groups.filter(g=>g.status==='soon'||g.status==='today').length;
    $('#stat-expired').textContent=state.groups.filter(g=>g.status==='expired').length;
  } catch(e){ showToast('加载仪表盘失败: '+(e?.message||e),'error'); }
}

// 会员续费
async function loadRenewalData(){
  try{
    showLoading(true);
    const data=await apiCall('/data');
    state.groups = Object.entries(data)
      .filter(([k,v])=>k!=='generatedCodes'&&typeof v==='object')
      .map(([gid,info])=>{ const d=daysRemaining(info.expiry); let s='active'; if(d<0)s='expired'; else if(d===0)s='today'; else if(d<=7)s='soon'; return { gid, ...info, days:d, status:s };});
    renderGroupsTable();
    renderCodes(await apiCall('/codes'));
  } catch(e){ showToast('加载续费数据失败: '+(e?.message||e),'error'); }
  finally{ showLoading(false); }
}

function renderGroupsTable(){
  const tbody=$('#groups-table-body'); if(!tbody) return;
  const kw = (state.keyword||'').trim();
  const filtered = state.groups.filter(g=>{
    if(state.filter==='active' && g.status!=='active') return false;
    if(state.filter==='soon' && !(g.status==='soon' || g.status==='today')) return false;
    if(state.filter==='expired' && g.status!=='expired') return false;
    if(kw && !String(g.gid).includes(kw)) return false;
    return true;
  });
  tbody.innerHTML = filtered.length ? filtered.map(g=>`<tr>
    <td><input type="checkbox" class="group-checkbox" data-gid="${g.gid}"></td>
    <td>${g.gid}</td>
    <td>${getStatusLabel(g.days)}</td>
    <td>${formatDate(g.expiry)}</td>
    <td>${g.days}</td>
    <td><button class="btn btn-sm" data-action="remind" data-gid="${g.gid}">提醒</button> <button class="btn btn-sm" data-action="leave" data-gid="${g.gid}">退群</button></td>
  </tr>`).join('') : '<tr><td colspan="6" class="text-center">暂无数据</td></tr>';
}

function renderCodes(codes){
  const el=$('#codes-list'); if(!el) return;
  const arr=Object.entries(codes||{});
  el.innerHTML = arr.length? arr.map(([code,meta])=>`<div class="code-card"><div class="code-info"><div class="code-value">${code}</div><div class="code-meta">${meta.length}${meta.unit} · 可用${meta.max_use||1}次</div></div><button class="btn-copy" data-code="${code}">复制</button></div>`).join('') : '<div class="empty-state">暂无续费码</div>';
}

async function generateCode(){
  try{
    const btn=$('#generate-code-btn'); if(btn){ if(btn.dataset.busy==='1') return; btn.dataset.busy='1'; btn.setAttribute('disabled','disabled'); }
    const length = parseInt(($('#gen-length')?.value||'1'),10) || 1;
    const unit = ($('#gen-unit')?.value||'天');
    const r = await apiCall('/generate',{method:'POST', body: JSON.stringify({ length, unit })});
    showToast('已生成：'+(r?.code||''),'success');
    renderCodes(await apiCall('/codes'));
    await copyText(r?.code||'');
  } catch(e){ showToast('生成失败: '+(e?.message||e),'error'); }
  finally{ const btn=$('#generate-code-btn'); if(btn){ btn.dataset.busy='0'; btn.removeAttribute('disabled'); } }
}

// 统计
async function loadStatsData(){
  try{
    showLoading(true);
    const today = await apiCall('/stats/today');
    const root = today?.bots? today : Object.values(today||{})[0] || {};
    state.stats = { today: root };
    renderStatsOverviewAll(root);
    renderStatsDetails(root);
  } catch(e){ showToast('加载统计失败: '+(e?.message||e),'error'); }
  finally{ showLoading(false); }
}

function renderStatsOverviewAll(today){
  try{
    const bots=today.bots||{}; let total=0, gsum=0, psum=0;
    Object.values(bots).forEach(s=>{ if(!s) return; total+=s.total_sent||0; gsum+=(s.group?.count)||0; psum+=(s.private?.count)||0;});
    (document.getElementById('stats-today-total')).textContent = String(total);
    (document.getElementById('stats-group-total')).textContent = String(gsum);
    (document.getElementById('stats-private-total')).textContent = String(psum);
  } catch{}
}

function renderStatsDetails(today){
  try{
    const bots = today?.bots || {};
    const tbody = document.getElementById('stats-detail-body'); if(!tbody) return;
    let rows = Object.entries(bots).map(([id,s])=>{
      const g=s.group||{}; const p=s.private||{};
      return { id, total:s.total_sent||0, gCount:g.count||0, pCount:p.count||0, gT:g.targets||{}, pT:p.targets||{} };
    });
    const kw = (state.statsKeyword||'').trim(); if(kw){ rows = rows.filter(r=> r.id.includes(kw) || Object.keys(r.gT).some(k=>k.includes(kw)) || Object.keys(r.pT).some(k=>k.includes(kw)) ); }
    switch(state.statsSort){
      case 'total_asc': rows.sort((a,b)=> a.total-b.total); break;
      case 'bot_asc': rows.sort((a,b)=> String(a.id).localeCompare(String(b.id))); break;
      case 'bot_desc': rows.sort((a,b)=> String(b.id).localeCompare(String(a.id))); break;
      case 'group_desc': rows.sort((a,b)=> (b.gCount-a.gCount)|| (b.total-a.total)); break;
      case 'private_desc': rows.sort((a,b)=> (b.pCount-a.pCount)|| (b.total-a.total)); break;
      case 'total_desc':
      default: rows.sort((a,b)=> b.total-a.total); break;
    }
    const fmt=(o)=>{ try{ const arr=Object.entries(o||{}); if(!arr.length) return '-'; return arr.map(([k,v])=>`${k}(${v})`).join(', ');}catch{return '-';} };
    tbody.innerHTML = rows.length? rows.map(r=>`<tr>
      <td>${r.id}</td>
      <td>${r.total}</td>
      <td>${r.gCount}</td>
      <td>${fmt(r.gT)}</td>
      <td>${r.pCount}</td>
      <td>${fmt(r.pT)}</td>
    </tr>`).join('') : '<tr><td colspan="6" class="text-center">暂无数据</td></tr>';
  }catch{}
}

// 权限（简单渲染 + JSON 编辑）
async function loadPermissions(){
  try{
    showLoading(true);
    const p = await apiCall('/permissions');
    state.permissions = p;
    const wrap=document.getElementById('permissions-list'); if(!wrap) return;
    wrap.innerHTML = `<pre class="json-view">${escapeHtml(JSON.stringify(p, null, 2))}</pre>`;
  } catch(e){ showToast('加载权限失败: '+(e?.message||e),'error'); }
  finally{ showLoading(false); }
}

function openPermJsonModal(){ const m=$('#perm-json-modal'); if(!m) return; const ta=$('#permissions-json'); if(ta) ta.value=JSON.stringify(state.permissions||{},null,2); m.classList.remove('hidden'); }
function closePermJsonModal(){ const m=$('#perm-json-modal'); if(m) m.classList.add('hidden'); }
async function savePermJson(){ try{ const txt=$('#permissions-json')?.value||'{}'; const data=JSON.parse(txt||'{}'); await apiCall('/permissions',{method:'PUT', body: JSON.stringify(data)}); showToast('已保存权限','success'); state.permissions=data; closePermJsonModal(); loadPermissions(); } catch(e){ showToast('保存失败: '+(e?.message||e),'error'); } }

// 配置
async function loadConfig(){ try{ showLoading(true); const c=await apiCall('/config'); state.config=c; const ta=$('#config-json'); if(ta) ta.value=JSON.stringify(c, null, 2); } catch(e){ showToast('加载配置失败: '+(e?.message||e),'error'); } finally{ showLoading(false);} }
async function saveConfig(){ try{ const txt=$('#config-json')?.value||'{}'; const cfg=JSON.parse(txt||'{}'); showLoading(true); await apiCall('/config',{method:'PUT', body: JSON.stringify(cfg)}); showToast('配置已更新','success'); state.config=cfg; } catch(e){ showToast('保存失败: '+(e?.message||e),'error'); } finally{ showLoading(false);} }

// 工具
function escapeHtml(s){ return String(s||'').replace(/[&<>]/g, c=>({ '&':'&amp;','<':'&lt;','>':'&gt;' })[c]); }

// 事件绑定
function bindEvents(){
  $('#theme-toggle')?.addEventListener('click', toggleTheme);
  $$('.nav-item').forEach(i=> i.addEventListener('click', e=>{ e.preventDefault(); switchTab(i.dataset.tab);}));
  $('#generate-code-btn')?.addEventListener('click', generateCode);
  $('#save-permissions-btn')?.addEventListener('click', savePermJson);
  $('#open-permissions-json-btn')?.addEventListener('click', openPermJsonModal);
  $('#perm-json-close')?.addEventListener('click', closePermJsonModal);
  $('#perm-json-cancel')?.addEventListener('click', closePermJsonModal);
  $('#perm-json-save')?.addEventListener('click', savePermJson);
  $('#save-config-btn')?.addEventListener('click', saveConfig);
  $('#group-search')?.addEventListener('input', e=>{ state.keyword=e.target.value.trim(); renderGroupsTable(); });
  $('#status-filter')?.addEventListener('change', e=>{ state.filter=e.target.value; renderGroupsTable(); });
  $('#refresh-btn')?.addEventListener('click', ()=>{ const active=$('.nav-item.active'); if(active) switchTab(active.dataset.tab); });
  // 复制续费码
  $('#codes-list')?.addEventListener('click', async (e)=>{ const btn=e.target.closest('.btn-copy'); if(!btn) return; const code=btn.dataset.code||btn.previousElementSibling?.textContent||''; const ok=await copyText(code); showToast(ok?'已复制续费码':'复制失败', ok?'success':'error'); });
  // 表格操作：提醒/退群
  $('#groups-table-body')?.addEventListener('click', async (e)=>{ const el=e.target.closest('button[data-action]'); if(!el) return; const gid=el.dataset.gid; try{ if(el.dataset.action==='remind'){ await apiCall('/remind_multi',{method:'POST', body: JSON.stringify({ group_id: gid, content: '本群会员即将到期，请尽快续费' })}); showToast('已发送提醒','success'); } else if(el.dataset.action==='leave'){ await apiCall('/leave_multi',{method:'POST', body: JSON.stringify({ group_id: gid })}); showToast('已退群','success'); loadRenewalData(); } } catch(err){ showToast('操作失败: '+(err?.message||err),'error'); } });
  // 统计筛选
  $('#stats-keyword')?.addEventListener('input', e=>{ state.statsKeyword=e.target.value.trim(); renderStatsDetails(state.stats?.today||{}); });
  $('#stats-sort')?.addEventListener('change', e=>{ state.statsSort=e.target.value; renderStatsDetails(state.stats?.today||{}); });
}

// 初始化
function init(){
  document.body.setAttribute('data-theme', state.theme);
  bindEvents();
  switchTab('dashboard');
}

document.addEventListener('DOMContentLoaded', init);

