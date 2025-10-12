// ==================== 今汐控制台前端 ====================

// 全局状态
const state = {
  bots: [],
  selectedBotIds: [],
  groups: [],
  stats: null,
  permissions: null,
  config: null,
  theme: localStorage.getItem('theme') || 'light',
  sortBy: 'days', sortDir: 'asc', filter: 'all', keyword: ''
};

// 工具
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
function showToast(message, type='info'){
  const c=$('#toast-container'); if(!c) return;
  const n=document.createElement('div');
  n.className=`toast toast-${type}`;
  n.textContent=message;
  c.appendChild(n);
  setTimeout(()=>n.classList.add('show'),10);
  setTimeout(()=>{ n.classList.remove('show'); setTimeout(()=>n.remove(),300);},3000);
}
function showLoading(show=true){ const o=$('#loading-overlay'); if(o) o.classList.toggle('hidden', !show); }
function formatDate(s){ if(!s) return '-'; try{ const d=new Date(s); return d.toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});}catch{return s;}}
function daysRemaining(s){ try{ const e=new Date(s), n=new Date(); e.setHours(0,0,0,0); n.setHours(0,0,0,0); return Math.round((e-n)/86400000);}catch{return 0;} }
function getStatusLabel(days){ if(days<0) return '<span class="status-badge status-expired">已到期</span>'; if(days===0) return '<span class="status-badge status-today">今日到期</span>'; if(days<=7) return '<span class="status-badge status-soon">即将到期</span>'; return '<span class="status-badge status-active">有效</span>'; }
function maskCode(code){ if(!code) return ''; return String(code).slice(0,4)+'****'+String(code).slice(-4); }
function normalizeUnit(u){ const x=String(u||'天'); if(['d','day','天'].includes(x)) return '天'; if(['m','month','月'].includes(x)) return '月'; if(['y','year','年'].includes(x)) return '年'; return '天'; }

// API
async function apiCall(path, options={}){
  const token = localStorage.getItem('auth_token') || '';
  const headers = {'Content-Type':'application/json', ...(options.headers||{})};
  if(token) headers['Authorization'] = `Bearer ${token}`;
  const resp = await fetch(`/member_renewal${path}`, { ...options, headers });
  if(!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
  const ct = resp.headers.get('content-type')||'';
  return ct.includes('application/json') ? resp.json() : resp.text();
}

// 登录
async function handleLogin(){
  const t=($('#login-token')?.value||'').trim();
  if(!t || t.length!==6){ showToast('请输入6位验证码','error'); return; }
  try{
    showLoading(true);
    const r=await apiCall('/auth/login',{method:'POST', body: JSON.stringify({ token:t, user_id:'admin' })});
    if(r.success){
      localStorage.setItem('auth_token', t);
      showToast('登录成功','success');
      $('#login-page').style.display='none';
      $('#app').classList.remove('hidden');
      await init();
    }
  } catch(e){ showToast(`登录失败: ${e.message}`,'error'); }
  finally{ showLoading(false);} }

// 主题
function toggleTheme(){
  state.theme = state.theme==='light' ? 'dark':'light';
  document.body.setAttribute('data-theme', state.theme);
  localStorage.setItem('theme', state.theme);
  const i=$('#theme-toggle .icon');
  if(i) i.textContent = state.theme==='light' ? '🌞' : '🌙';
}

// Tab
function switchTab(tab){
  $$('.nav-item').forEach(i=>i.classList.toggle('active', i.dataset.tab===tab));
  $$('.tab-content').forEach(c=>c.classList.toggle('active', c.id===`tab-${tab}`));
  if(tab==='renewal') loadRenewalData();
  else if(tab==='stats') loadStatsData();
  else if(tab==='permissions') loadPermissions();
  else if(tab==='config') loadConfig();
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
  } catch(e){ showToast(`加载仪表盘失败: ${e.message}`,'error'); }
}

// 续费
async function loadRenewalData(){
  try{
    showLoading(true);
    const data=await apiCall('/data');
    state.groups = Object.entries(data)
      .filter(([k,v])=>k!=='generatedCodes'&&typeof v==='object')
      .map(([gid,info])=>{ const d=daysRemaining(info.expiry); let s='active'; if(d<0)s='expired'; else if(d===0)s='today'; else if(d<=7)s='soon'; return { gid, ...info, days:d, status:s };});
    ensureRenewalBotSelector();
    renderGroupsTable();
    const codes=await apiCall('/codes');
    renderCodes(codes);
  } catch(e){ showToast(`加载续费数据失败: ${e.message}`,'error'); }
  finally{ showLoading(false);} }

function renderGroupsTable(){
  const tbody=$('#groups-table-body'); if(!tbody) return;
  let list=[...state.groups];
  if(state.filter!=='all') list=list.filter(g=>g.status===state.filter);
  if(state.keyword) list=list.filter(g=>String(g.gid).includes(state.keyword));
  const dir=state.sortDir==='asc'?1:-1;
  list.sort((a,b)=>{
    if(state.sortBy==='group') return String(a.gid).localeCompare(String(b.gid))*dir;
    if(state.sortBy==='status') return String(a.status).localeCompare(String(b.status))*dir;
    if(state.sortBy==='expiry') return String(a.expiry||'').localeCompare(String(b.expiry||''))*dir;
    if(state.sortBy==='days') return (a.days-b.days)*dir;
    return 0;
  });
  tbody.innerHTML = list.length? list.map(g=>`
    <tr>
      <td><input type="checkbox" class="group-checkbox" data-gid="${g.gid}"></td>
      <td>${g.gid}</td>
      <td>${getStatusLabel(g.days)}</td>
      <td>${formatDate(g.expiry)}</td>
      <td>${g.days}</td>
      <td>
        <button class="btn-action btn-remind" data-gid="${g.gid}">提醒</button>
        <button class="btn-action btn-extend" data-gid="${g.gid}">+7天</button>
        <button class="btn-action btn-leave" data-gid="${g.gid}">退群</button>
      </td>
    </tr>`).join('') : '<tr><td colspan="6" class="text-center">暂无数据</td></tr>';
}

function renderCodes(codes){
  const el=$('#codes-list'); if(!el) return;
  const arr=Object.entries(codes||{});
  el.innerHTML = arr.length? arr.map(([code,meta])=>`<div class="code-card"><div class="code-info"><div class="code-value">${maskCode(code)}</div><div class="code-meta">${meta.length}${meta.unit} · 可用${meta.max_use||1}次</div></div><button class="btn-copy" data-code="${code}">复制</button></div>`).join('') : '<div class="empty-state">暂无可用续费码</div>';
}

// 统计（精简）
async function loadStatsData(){
  try{
    showLoading(true);
    const today=await apiCall('/stats/today');
    state.stats={today};
    renderStatsOverviewAll(today);
    renderBotList();
  } catch(e){ showToast(`加载统计失败: ${e.message}`,'error'); }
  finally{ showLoading(false);} }

function renderStatsOverviewAll(today){
  try{
    const bots=today.bots||{}; let total=0, gsum=0, psum=0;
    Object.values(bots).forEach(s=>{ if(!s) return; total+=s.total_sent||0; gsum+=(s.group?.count)||0; psum+=(s.private?.count)||0;});
    (document.getElementById('stats-today-total')).textContent = String(total);
    (document.getElementById('stats-group-total')).textContent = String(gsum);
    (document.getElementById('stats-private-total')).textContent = String(psum);
  } catch{}
}

function renderBotList(){
  let list=document.getElementById('bot-list');
  if(!list){ const tab=$('#tab-stats'); if(!tab) return; const panel=document.createElement('div'); panel.className='panel'; panel.innerHTML='<h3 class="panel-title">机器人列表</h3><div id="bot-list" class="bot-list"></div>'; tab.appendChild(panel); list=document.getElementById('bot-list'); }
  list.innerHTML = (state.bots||[]).length? state.bots.map(b=>`<div class="bot-list-item" data-bot="${b.bot_id}"><div><div class="title">${b.bot_name||('Bot '+b.bot_id)}</div><div class="status">${b.bot_id}${b.is_online?' · 在线':''}</div></div><div class="icon">›</div></div>`).join('') : '<div class="empty-state">未配置机器人</div>';
  list.querySelectorAll('.bot-list-item').forEach(el=> el.addEventListener('click', ()=> showBotStatsModal(el.getAttribute('data-bot'))));
}

function ensureStatsDetailModal(){ if($('#stats-detail-modal')) return; const m=document.createElement('div'); m.id='stats-detail-modal'; m.className='modal hidden'; m.innerHTML='<div class="modal-dialog"><div class="modal-header"><h3 id="stats-detail-title">机器人详情</h3><button class="modal-close" id="stats-detail-close">×</button></div><div class="modal-body"><div class="stats-overview"><div class="stat-box"><div class="stat-box-label">群聊总数</div><div id="stats-detail-group-total" class="stat-box-value">-</div></div><div class="stat-box"><div class="stat-box-label">私聊总数</div><div id="stats-detail-private-total" class="stat-box-value">-</div></div></div><div class="panel" style="margin-top:12px;"><h3 class="panel-title">群消息数</h3><div id="stats-detail-groups" class="ranking-list"></div></div></div><div class="modal-footer"><button id="stats-detail-ok" class="btn btn-primary">关闭</button></div></div>'; document.body.appendChild(m); $('#stats-detail-close').addEventListener('click', closeStatsDetailModal); $('#stats-detail-ok').addEventListener('click', closeStatsDetailModal); }
function showBotStatsModal(botId){ ensureStatsDetailModal(); const s=state.stats?.today?.bots?.[botId]; const name=(state.bots.find(b=>String(b.bot_id)===String(botId))?.bot_name)||('Bot '+botId); $('#stats-detail-title').textContent = `${name} (${botId})`; $('#stats-detail-group-total').textContent = s?.group?.count || 0; $('#stats-detail-private-total').textContent = s?.private?.count || 0; const targets=s?.group?.targets||{}; const sorted=Object.entries(targets).sort((a,b)=>b[1]-a[1]); $('#stats-detail-groups').innerHTML = sorted.map(([gid,count],i)=>`<div class="ranking-item"><div class="rank-number">${i+1}</div><div class="rank-info"><div class="rank-name">群 ${gid}</div><div class="rank-value">${count} 条</div></div></div>`).join(''); $('#stats-detail-modal').classList.remove('hidden'); }
function closeStatsDetailModal(){ $('#stats-detail-modal')?.classList.add('hidden'); }

// 权限/配置
async function loadPermissions(){ try{ showLoading(true); const p=await apiCall('/permissions'); state.permissions=p; const ta=$('#permissions-json'); if(ta) ta.value=JSON.stringify(p,null,2); } catch(e){ showToast(`加载权限失败: ${e.message}`,'error'); } finally{ showLoading(false);} }
async function savePermissions(){ try{ const txt=$('#permissions-json').value; const cfg=JSON.parse(txt||'{}'); showLoading(true); await apiCall('/permissions',{method:'PUT', body: JSON.stringify(cfg)}); showToast('权限配置已保存','success'); state.permissions=cfg; } catch(e){ showToast(`保存失败: ${e.message}`,'error'); } finally{ showLoading(false);} }
async function loadConfig(){ try{ showLoading(true); const c=await apiCall('/config'); state.config=c; $('#config-json').value = JSON.stringify(c, null, 2); } catch(e){ showToast(`加载配置失败: ${e.message}`,'error'); } finally{ showLoading(false);} }
async function saveConfig(){ try{ const txt=$('#config-json').value; const cfg=JSON.parse(txt||'{}'); showLoading(true); await apiCall('/config',{method:'PUT', body: JSON.stringify(cfg)}); showToast('配置已保存','success'); state.config=cfg; } catch(e){ showToast(`保存失败: ${e.message}`,'error'); } finally{ showLoading(false);} }

// Bots
async function loadBots(){ try{ const r=await apiCall('/bots/config'); state.bots=r.bots||[]; } catch(e){ showToast(`加载机器人列表失败: ${e.message}`,'error'); } }

// 续费页机器人多选
function ensureRenewalBotSelector(){ const tab=$('#tab-renewal'); if(!tab) return; if(!$('#btn-choose-bots')){ const host=tab.querySelector('.panel:nth-of-type(2)'); if(host){ const wrap=document.createElement('div'); wrap.className='bot-multi-select'; wrap.innerHTML='<button id="btn-choose-bots" class="btn">选择机器人</button><div id="selected-bots" class="bot-chips"></div>'; host.insertBefore(wrap, host.querySelector('.toolbar')); } } ensureBotSelectModal(); renderSelectedBotsChips(); }
function ensureBotSelectModal(){ if($('#bot-select-modal')) return; const m=document.createElement('div'); m.id='bot-select-modal'; m.className='modal hidden'; m.innerHTML='<div class="modal-dialog"><div class="modal-header"><h3>选择机器人</h3><button class="modal-close" id="bot-select-close">×</button></div><div class="modal-body"><div id="bot-select-list" class="bot-select-list"></div></div><div class="modal-footer"><button id="bot-select-cancel" class="btn btn-secondary">取消</button><button id="bot-select-ok" class="btn btn-primary">确定</button></div></div>'; document.body.appendChild(m); $('#bot-select-cancel').addEventListener('click', closeBotSelectModal); $('#bot-select-close').addEventListener('click', closeBotSelectModal); $('#bot-select-ok').addEventListener('click', confirmBotSelection); $('#btn-choose-bots')?.addEventListener('click', openBotSelectModal); }
function openBotSelectModal(){ const box=$('#bot-select-list'); if(box){ const ids=new Set(state.selectedBotIds||[]); box.innerHTML=(state.bots||[]).map(b=>`<label class="bot-select-item"><input type="checkbox" value="${b.bot_id}" ${ids.has(String(b.bot_id))?'checked':''}><div><div class="name">${b.bot_name||('Bot '+b.bot_id)} ${b.is_online?'<span style="color:#67C23A;font-size:12px;">(在线)</span>':''}</div><div class="meta">${b.bot_id}</div></div></label>`).join(''); } $('#bot-select-modal')?.classList.remove('hidden'); }
function closeBotSelectModal(){ $('#bot-select-modal')?.classList.add('hidden'); }
function confirmBotSelection(){ const box=$('#bot-select-list'); if(!box) return; const checks=Array.from(box.querySelectorAll('input[type="checkbox"]')); state.selectedBotIds = checks.filter(c=>c.checked).map(c=>String(c.value)); renderSelectedBotsChips(); closeBotSelectModal(); }
function renderSelectedBotsChips(){ const wrap=$('#selected-bots'); if(!wrap) return; const ids=state.selectedBotIds||[]; if(!ids.length){ wrap.innerHTML='<div class="empty-state" style="padding:4px 0;">未选择机器人</div>'; return; } const map=new Map((state.bots||[]).map(b=>[String(b.bot_id), b])); wrap.innerHTML = ids.map(id=>{ const b=map.get(String(id)); const name=b?.bot_name||('Bot '+id); return `<span class="bot-chip" data-id="${id}">${name} <span class="remove">×</span></span>`; }).join(''); wrap.querySelectorAll('.bot-chip .remove').forEach(el=> el.addEventListener('click', ()=>{ const id=el.parentElement?.getAttribute('data-id'); state.selectedBotIds = (state.selectedBotIds||[]).filter(x=>String(x)!==String(id)); renderSelectedBotsChips(); })); }
async function remindGroups(groupIds){ if(!Array.isArray(groupIds)||!groupIds.length) return; if(!state.selectedBotIds?.length){ showToast('请先选择机器人','warning'); return;} for(const gid of groupIds){ await apiCall('/remind_multi',{method:'POST', body: JSON.stringify({ group_id: gid, bot_ids: state.selectedBotIds })}); } }
async function leaveGroups(groupIds){ if(!Array.isArray(groupIds)||!groupIds.length) return; if(!state.selectedBotIds?.length){ showToast('请先选择机器人','warning'); return;} for(const gid of groupIds){ await apiCall('/leave_multi',{method:'POST', body: JSON.stringify({ group_id: gid, bot_ids: state.selectedBotIds })}); } }

// 事件绑定（带防抖）
function bindEvents(){
  $('#login-btn')?.addEventListener('click', handleLogin);
  $('#login-token')?.addEventListener('keypress', e=>{ if(e.key==='Enter') handleLogin(); });
  $('#theme-toggle')?.addEventListener('click', toggleTheme);
  $$('.nav-item').forEach(i=> i.addEventListener('click', e=>{ e.preventDefault(); switchTab(i.dataset.tab);}));
  $('#generate-code-btn')?.addEventListener('click', generateCode);
  $('#save-permissions-btn')?.addEventListener('click', savePermissions);
  $('#save-config-btn')?.addEventListener('click', saveConfig);
  $('#group-search')?.addEventListener('input', e=>{ state.keyword=e.target.value.trim(); renderGroupsTable(); });
  $('#status-filter')?.addEventListener('change', e=>{ state.filter=e.target.value; renderGroupsTable(); });
  $('#select-all')?.addEventListener('change', e=> $$('.group-checkbox').forEach(cb=> cb.checked=e.target.checked));
  $('#refresh-btn')?.addEventListener('click', ()=>{ const active=$('.nav-item.active'); if(active) switchTab(active.dataset.tab); });
  const tbl=$('#groups-table-body');
  if(tbl){
    tbl.addEventListener('click', async (e)=>{
      const btn=e.target.closest('.btn-action'); if(!btn) return; const gid=parseInt(btn.dataset.gid);
      if(btn.dataset.busy==='1') return; btn.dataset.busy='1'; btn.setAttribute('disabled','disabled');
      try{
        if(btn.classList.contains('btn-remind')){
          await remindGroups([gid]); showToast(`已向群 ${gid} 发送提醒`,'success');
        } else if(btn.classList.contains('btn-extend')){
          await apiCall('/extend',{method:'POST', body: JSON.stringify({ group_id: gid, length:7, unit:'天'})});
          showToast(`已为群 ${gid} 延长7天`,'success'); await loadRenewalData();
        } else if(btn.classList.contains('btn-leave')){
          if(!confirm(`确认让所选机器人退出群 ${gid}?`)) return; await leaveGroups([gid]);
          showToast(`已退出群 ${gid}`,'success'); await loadRenewalData();
        }
      } catch(err){ showToast(`操作失败: ${err.message}`,'error'); }
      finally{ delete btn.dataset.busy; btn.removeAttribute('disabled'); }
    });
  }
  $('#codes-list')?.addEventListener('click', async (e)=>{ const btn=e.target.closest('.btn-copy'); if(!btn) return; try{ await navigator.clipboard.writeText(btn.dataset.code||''); showToast('续费码已复制','success'); } catch { showToast('复制失败','error'); } });
}

// 生成续费码（防重复）
async function generateCode(){
  const btn=$('#generate-code-btn'); if(btn && btn.dataset.busy==='1') return; if(btn){ btn.dataset.busy='1'; btn.setAttribute('disabled','disabled'); }
  const length=parseInt($('#renewal-length').value)||30; let unit=$('#renewal-unit')?.value||'天'; unit = normalizeUnit(unit);
  try{ showLoading(true); const r=await apiCall('/generate',{method:'POST', body: JSON.stringify({ length, unit })}); showToast(`续费码已生成: ${r.code}`,'success'); await loadRenewalData(); }
  catch(e){ showToast(`生成失败: ${e.message}`,'error'); }
  finally{ showLoading(false); if(btn){ delete btn.dataset.busy; btn.removeAttribute('disabled'); } }
}

// 初始化
async function init(){ document.body.setAttribute('data-theme', state.theme); const i=$('#theme-toggle .icon'); if(i) i.textContent = state.theme==='light'?'🌞':'🌙'; await loadBots(); ensureRenewalBotSelector(); await loadDashboard(); }
window.addEventListener('DOMContentLoaded', ()=>{
  // 无认证：直接显示应用
  $('#app').classList.remove('hidden');
  const lp = document.getElementById('login-page'); if (lp) lp.style.display='none';
  init();
  bindEvents();
});
window.switchTab = switchTab;
window.runScheduledTask = async function(){ try{ showLoading(true); const r=await apiCall('/job/run',{method:'POST'}); showToast(`检查完成 提醒${r.reminded}个群，退出${r.left}个群`,'success'); } catch(e){ showToast(`执行失败: ${e.message}`,'error'); } finally{ showLoading(false);} };

