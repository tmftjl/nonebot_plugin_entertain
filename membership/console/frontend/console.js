// ==================== 浠婃睈控制台板墠绔紙UTF-8锛?====================

// 鍏ㄥ眬鐘舵€?
const state = {
  groups: [],
  stats: null,
  permissions: null,
  config: null,
  theme: localStorage.getItem('theme') || 'light', 
  sortBy: 'days', sortDir: 'asc', filter: 'all', keyword: '',
  statsSort: 'total_desc', // total_desc | total_asc | bot_asc | bot_desc | group_desc | private_desc
  statsKeyword: ''
};

// 宸ュ叿
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
function getStatusLabel(days){ if(days<0) return '<span class="status-badge status-expired">宸插埌鏈?/span>'; if(days===0) return '<span class="status-badge status-today">浠婃棩鍒版湡</span>'; if(days<=7) return '<span class="status-badge status-soon">鍗冲皢鍒版湡</span>'; return '<span class="status-badge status-active">鏈夋晥</span>'; }
function maskCode(code){ if(!code) return ''; return String(code).slice(0,4)+'****'+String(code).slice(-4); }
function normalizeUnit(u){ const x=String(u||'').trim().toLowerCase(); if(['d','day','澶?].includes(x)) return '澶?; if(['m','month','鏈?].includes(x)) return '鏈?; if(['y','year','骞?].includes(x)) return '骞?; return '澶?; }
async function copyText(text){
  try{
    if(navigator.clipboard && navigator.clipboard.writeText){
      await navigator.clipboard.writeText(text);
      return true;
    }
  }catch{}
  try{
    const ta=document.createElement('textarea');
    ta.value=String(text||'');
    ta.style.position='fixed'; ta.style.opacity='0'; ta.style.left='-9999px';
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    const ok=document.execCommand('copy');
    ta.remove();
    return !!ok;
  }catch{}
  return false;
}

// API
async function apiCall(path, options={}){
  const token = localStorage.getItem('auth_token') || '';
  const headers = {'Content-Type':'application/json', ...(options.headers||{})};
  if(token) headers['Authorization'] = `Bearer ${token}`;
  const resp = await fetch(`/membership${path}`, { ...options, headers });
  if(!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
  const ct = resp.headers.get('content-type')||'';
  return ct.includes('application/json') ? resp.json() : resp.text();
}

// 鐧诲綍
async function handleLogin(){
  const t=($('#login-token')?.value||'').trim();
  if(!t || t.length!==6){ showToast('璇疯緭鍏?浣嶉獙璇佺爜','error'); return; }
  try{
    showLoading(true);
    const r=await apiCall('/auth/login',{method:'POST', body: JSON.stringify({ token:t, user_id:'admin' })});
    if(r.success){
      localStorage.setItem('auth_token', t);
      showToast('鐧诲綍鎴愬姛','success');
      $('#login-page').style.display='none';
      $('#app').classList.remove('hidden');
      await init();
    }
  } catch(e){ showToast('鐧诲綍失败: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false);} }

// 涓婚
function toggleTheme(){
  state.theme = state.theme==='light' ? 'dark':'light';
  document.body.setAttribute('data-theme', state.theme);
  localStorage.setItem('theme', state.theme);
  const i=$('#theme-toggle .icon');
  if(i) i.textContent = state.theme==='light' ? '馃尀' : '馃寵';
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

// 浠〃鐩?
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
  } catch(e){ showToast('加载仪表失败 '+(e&&e.message?e.message:e),'error'); }
}

// 续费
async function loadRenewalData(){
  try{
    showLoading(true);
    const data=await apiCall('/data');
    state.groups = Object.entries(data)
      .filter(([k,v])=>k!=='generatedCodes'&&typeof v==='object')
      .map(([gid,info])=>{ const d=daysRemaining(info.expiry); let s='active'; if(d<0)s='expired'; else if(d===0)s='today'; else if(d<=7)s='soon'; return { gid, ...info, days:d, status:s };});
    renderGroupsTable();
    const codes=await apiCall('/codes');
    renderCodes(codes);
  } catch(e){ showToast('加载中续费鏁版嵁失败: '+(e&&e.message?e.message:e),'error'); }
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
        <button class="btn-action btn-extend" data-gid="${g.gid}">+7澶?/button>
        <button class="btn-action btn-leave" data-gid="${g.gid}">退群/button>
      </td>
    </tr>`).join('') : '<tr><td colspan="6" class="text-center">鏆傛棤鏁版嵁</td></tr>';
}

function renderCodes(codes){
  const el=$('#codes-list'); if(!el) return;
  const arr=Object.entries(codes||{});
  el.innerHTML = arr.length? arr.map(([code,meta])=>`<div class="code-card"><div class="code-info"><div class="code-value">${maskCode(code)}</div><div class="code-meta">${meta.length}${meta.unit} 路 鍙敤${meta.max_use||1}娆?/div></div><button class="btn-copy" data-code="${code}">复制</button></div>`).join('') : '<div class="empty-state">暂无可用续费码/div>';
}

// 统计锛堣鍙?/membership/stats/today 骞朵粎灞曠ず浠婂ぉ锛?
async function loadStatsData(){
  try{
    showLoading(true);
    let today = await apiCall('/stats/today');
    if(today && !today.bots && typeof today==='object'){
      const ks=Object.keys(today);
      if(ks.length===1 && today[ks[0]] && typeof today[ks[0]]==='object'){
        today = today[ks[0]];
      }
    }
    state.stats = { today };
    renderStatsOverviewAll(today);
    renderStatsDetails(today);
  } catch(e){ showToast('加载统计失败: '+(e&&e.message?e.message:e),'error'); }
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

function renderStatsDetails(today){
  try{
    const bots = today?.bots || {};
    const tbody = document.getElementById('stats-detail-body'); if(!tbody) return;
    let rows = Object.entries(bots).map(([id,s])=>{
      const g=s.group||{}; const p=s.private||{};
      return { id, total:s.total_sent||0, gCount:g.count||0, pCount:p.count||0, gT:g.targets||{}, pT:p.targets||{} };
    });
    // 杩囨护
    const kw = (state.statsKeyword||'').trim();
    if(kw){
      rows = rows.filter(r=> r.id.includes(kw) || Object.keys(r.gT).some(k=>k.includes(kw)) || Object.keys(r.pT).some(k=>k.includes(kw)) );
    }
    // 鎺掑簭
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
    </tr>`).join('') : '<tr><td colspan="6" class="text-center">暂无数据?/td></tr>';
  }catch{}
}

// 鏂扮殑鎵嬮鐞村紡权限鍒楄〃娓叉煋
function renderPermissionsList(){
  const wrap=document.getElementById('permissions-list');
  if(!wrap) return;
  const data = state.permissions || {};
  const sub = (data.sub_plugins||{});
  const plugins = Object.keys(sub).sort((a,b)=>a.localeCompare(b));
  if(!plugins.length && !data.top){ wrap.innerHTML = '<div class="empty-state">馃挙 鏆傛棤权限鏁版嵁</div>'; return; }
  
  const optLevel = (v)=>`<option value="all" ${v==='all'?'selected':''}>鎵€鏈変汉</option>
    <option value="member" ${v==='member'?'selected':''}>缇ゆ垚鍛?/option>
    <option value="admin" ${v==='admin'?'selected':''}>缇ょ鐞?/option>
    <option value="owner" ${v==='owner'?'selected':''}>缇や富</option>
    <option value="superuser" ${v==='superuser'?'selected':''}>瓒呯骇鐢ㄦ埛</option>`;
  const optScene = (v)=>`<option value="all" ${v==='all'?'selected':''}>鍏ㄩ儴</option>
    <option value="group" ${v==='group'?'selected':''}>缇よ亰</option>
    <option value="private" ${v==='private'?'selected':''}>绉佽亰</option>`;
  const toCSV=(arr)=>Array.isArray(arr)?arr.join(','):(arr||'');
  const from=(x)=> (x && typeof x==='object')?x:{};
  const esc=(s)=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  // 鍏ㄥ眬权限鍧楋紙椤朵笂涓€涓€荤殑控制台锛?
  const globalTop = from(data.top);
  const gWl = from(globalTop.whitelist);
  const gBl = from(globalTop.blacklist);
  const globalHTML = `
    <div id="perm-global" class="perm-global-block panel" style="margin-bottom: 16px;">
      <div class="panel-header" style="display:flex;align-items:center;justify-content:space-between;">
        <div style="font-weight:600;">馃寪 鍏ㄥ眬权限</div>
        <label class="perm-field">
          <input type="checkbox" class="perm-enabled" ${globalTop.enabled===false?'':'checked'}>
          <span>榛樿鍚敤</span>
        </label>
      </div>
      <div class="panel-body">
        <div class="perm-plugin-inline-config">
          <label class="perm-field">
            <span>馃懁 榛樿权限绛夌骇</span>
            <select class="perm-level">${optLevel(String(globalTop.level||'all'))}</select>
          </label>
          <label class="perm-field">
            <span>馃挰 榛樿浣跨敤鍦烘櫙</span>
            <select class="perm-scene">${optScene(String(globalTop.scene||'all'))}</select>
          </label>
        </div>
        <div class="perm-lists-section" style="margin-top:8px;">
          <div class="perm-list-group">
            <label class="perm-list-label">鉁?鐧藉悕鍗曠敤鎴?/label>
            <input type="text" class="perm-list-input perm-wl-users" placeholder="鐢ㄦ埛ID锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(gWl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">鉁?鐧藉悕鍗曠兢缁?/label>
            <input type="text" class="perm-list-input perm-wl-groups" placeholder="缇ゅ彿锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(gWl.groups))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">鉀?榛戝悕鍗曠敤鎴?/label>
            <input type="text" class="perm-list-input perm-bl-users" placeholder="鐢ㄦ埛ID锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(gBl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">鉀?榛戝悕鍗曠兢缁?/label>
            <input type="text" class="perm-list-input perm-bl-groups" placeholder="缇ゅ彿锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(gBl.groups))}">
          </div>
        </div>
      </div>
    </div>`;
  
  const rows = plugins.map((pn, index)=>{
    const node = from(sub[pn]);
    const top = from(node.top);
    const cmds = from(node.commands);
    const wl = from(top.whitelist);
    const bl = from(top.blacklist);
    
    // 鍛戒护鍒楄〃HTML - 鏀圭敤鎻掍欢鏍峰紡鐨勭綉鏍煎竷灞€
    const cmdRows = Object.keys(cmds).sort((a,b)=>a.localeCompare(b)).map(cn=>{
      const c=from(cmds[cn]);
      const cwl=from(c.whitelist);
      const cbl=from(c.blacklist);
      return `<div class="perm-command-item" data-command="${esc(cn)}">
        <div class="perm-command-header">
          <div class="perm-command-name">馃搶 ${esc(cn)}</div>
          <div class="perm-command-inline-config">
            <label class="perm-field">
              <input type="checkbox" class="perm-enabled" ${c.enabled===false?'':'checked'}>
              <span>鍚敤</span>
            </label>
            <label class="perm-field">
              <span>馃懁 绛夌骇</span>
              <select class="perm-level">${optLevel(String(c.level||'all'))}</select>
            </label>
            <label class="perm-field">
              <span>馃挰 鍦烘櫙</span>
              <select class="perm-scene">${optScene(String(c.scene||'all'))}</select>
            </label>
          </div>
        </div>
        <div class="perm-command-lists">
          <div class="perm-list-group">
            <label class="perm-list-label">鉁?鐧藉悕鍗曠敤鎴?/label>
            <input type="text" class="perm-list-input perm-wl-users" placeholder="澶氫釜鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(cwl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">鉁?鐧藉悕鍗曠兢缁?/label>
            <input type="text" class="perm-list-input perm-wl-groups" placeholder="澶氫釜鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(cwl.groups))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">鉀?榛戝悕鍗曠敤鎴?/label>
            <input type="text" class="perm-list-input perm-bl-users" placeholder="澶氫釜鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(cbl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">鉀?榛戝悕鍗曠兢缁?/label>
            <input type="text" class="perm-list-input perm-bl-groups" placeholder="澶氫釜鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(cbl.groups))}">
          </div>
        </div>
      </div>`;
    }).join('');
    
    return `<div class="perm-accordion-item" data-plugin="${esc(pn)}">
      <div class="perm-accordion-header" data-index="${index}">
        <div class="perm-accordion-title">
          <span class="perm-accordion-icon">鈻讹笍</span>
          <span>馃攲 ${esc(pn)}</span>
        </div>
        <label class="perm-field" onclick="event.stopPropagation()">
          <input type="checkbox" class="perm-enabled" ${top.enabled===false?'':'checked'}>
          <span>鍚敤鎻掍欢</span>
        </label>
      </div>
      <div class="perm-accordion-content">
        <div class="perm-accordion-body">
          <div class="perm-plugin-inline-config">
            <label class="perm-field">
              <span>馃懁 榛樿权限绛夌骇</span>
              <select class="perm-level">${optLevel(String(top.level||'all'))}</select>
            </label>
            <label class="perm-field">
              <span>馃挰 榛樿浣跨敤鍦烘櫙</span>
              <select class="perm-scene">${optScene(String(top.scene||'all'))}</select>
            </label>
          </div>
          
          <div class="perm-lists-section">
            <div class="perm-list-group">
              <label class="perm-list-label">鉁?鐧藉悕鍗曠敤鎴?/label>
              <input type="text" class="perm-list-input perm-wl-users" placeholder="澶氫釜ID鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(wl.users))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">鉁?鐧藉悕鍗曠兢缁?/label>
              <input type="text" class="perm-list-input perm-wl-groups" placeholder="澶氫釜缇ゅ彿鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(wl.groups))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">鉀?榛戝悕鍗曠敤鎴?/label>
              <input type="text" class="perm-list-input perm-bl-users" placeholder="澶氫釜ID鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(bl.users))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">鉀?榛戝悕鍗曠兢缁?/label>
              <input type="text" class="perm-list-input perm-bl-groups" placeholder="澶氫釜缇ゅ彿鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(bl.groups))}">
            </div>
          </div>
          
          ${Object.keys(cmds).length ? `
            <div class="perm-commands-section">
              <div class="perm-commands-title">馃幆 鍛戒护权限配置 (${Object.keys(cmds).length}涓懡浠?</div>
              <div class="perm-commands-list">${cmdRows}</div>
            </div>
          ` : '<div class="empty-state" style="padding: 40px 20px;">馃挙 璇ユ彃浠舵殏鏃犲懡浠?/div>'}
        </div>
      </div>
    </div>`;
  });
  
  const pluginsHTML = rows.join('') || '<div class="empty-state">鏆傛棤瀛愭彃锟?/div>';
  wrap.innerHTML = globalHTML + pluginsHTML;
  
  // 缁戝畾鎵嬮鐞寸偣鍑讳簨浠?
  wrap.querySelectorAll('.perm-accordion-header').forEach(header => {
    header.addEventListener('click', function(e) {
      const item = this.closest('.perm-accordion-item');
      const content = item.querySelector('.perm-accordion-content');
      const isActive = this.classList.contains('active');
      
      // 鍏抽棴鎵€鏈夊叾浠栭」
      wrap.querySelectorAll('.perm-accordion-header').forEach(h => {
        h.classList.remove('active');
        h.closest('.perm-accordion-item').querySelector('.perm-accordion-content').classList.remove('active');
      });
      
      // 鍒囨崲褰撳墠椤?
      if (!isActive) {
        this.classList.add('active');
        content.classList.add('active');
      }
    });
  });
}

// 浠嶶I鏀堕泦权限配置锛堥€傞厤鏂扮殑鎵嬮鐞寸粨鏋勶級
function collectPermissionsFromUI(){
  const wrap=document.getElementById('permissions-list');
  if(!wrap){
    try{ const txt=$('#permissions-json')?.value||'{}'; return JSON.parse(txt); }catch{ return {}; }
  }
  const out={ top: { enabled:true, level:'all', scene:'all', whitelist:{users:[],groups:[]}, blacklist:{users:[],groups:[]} }, sub_plugins: {} };
  // 鏀堕泦鍏ㄥ眬(top)璁剧疆
  try{
    const g = document.getElementById('perm-global') || wrap;
    const gTop = {};
    const sv=(s)=> String(s||'').split(',').map(x=>x.trim()).filter(Boolean);
    gTop.enabled = g.querySelector('.perm-enabled')?.checked ?? true;
    gTop.level = g.querySelector('.perm-level')?.value || 'all';
    gTop.scene = g.querySelector('.perm-scene')?.value || 'all';
    const wl={ users:[], groups:[] }, bl={ users:[], groups:[] };
    wl.users = sv(g.querySelector('.perm-wl-users')?.value);
    wl.groups = sv(g.querySelector('.perm-wl-groups')?.value);
    bl.users = sv(g.querySelector('.perm-bl-users')?.value);
    bl.groups = sv(g.querySelector('.perm-bl-groups')?.value);
    gTop.whitelist = wl; gTop.blacklist = bl;
    out.top = gTop;
  }catch{}
  wrap.querySelectorAll('.perm-accordion-item').forEach(item=>{
    const pn = item.getAttribute('data-plugin')||'';
    if(!pn) return;
    const node = {};
    const top={};
    
    // 鑾峰彇鎻掍欢椤剁骇配置
    const header = item.querySelector('.perm-accordion-header');
    const body = item.querySelector('.perm-accordion-body');
    
    top.enabled = header.querySelector('.perm-enabled')?.checked ?? true;
    top.level = body.querySelector('.perm-plugin-inline-config .perm-level')?.value || 'all';
    top.scene = body.querySelector('.perm-plugin-inline-config .perm-scene')?.value || 'all';
    
    const wl={ users:[], groups:[] }, bl={ users:[], groups:[] };
    const sv=(s)=> String(s||'').split(',').map(x=>x.trim()).filter(Boolean);
    
    const listsSection = body.querySelector('.perm-lists-section');
    if(listsSection) {
      wl.users = sv(listsSection.querySelector('.perm-list-group:nth-child(1) .perm-wl-users')?.value);
      wl.groups = sv(listsSection.querySelector('.perm-list-group:nth-child(2) .perm-wl-groups')?.value);
      bl.users = sv(listsSection.querySelector('.perm-list-group:nth-child(3) .perm-bl-users')?.value);
      bl.groups = sv(listsSection.querySelector('.perm-list-group:nth-child(4) .perm-bl-groups')?.value);
    }
    
    top.whitelist = wl;
    top.blacklist = bl;
    node.top = top;
    
    // 鑾峰彇鍛戒护配置
    const cmds={};
    body.querySelectorAll('.perm-command-item').forEach(cmdEl=>{
      const cn = cmdEl.getAttribute('data-command')||'';
      if(!cn) return;
      const c={};
      c.enabled = cmdEl.querySelector('.perm-command-inline-config .perm-enabled')?.checked ?? true;
      c.level = cmdEl.querySelector('.perm-command-inline-config .perm-level')?.value || 'all';
      c.scene = cmdEl.querySelector('.perm-command-inline-config .perm-scene')?.value || 'all';
      
      const cwl={ users:[], groups:[] }, cbl={ users:[], groups:[] };
      const cmdLists = cmdEl.querySelector('.perm-command-lists');
      if(cmdLists) {
        const groups = cmdLists.querySelectorAll('.perm-list-group');
        cwl.users = sv(groups[0]?.querySelector('.perm-wl-users')?.value);
        cwl.groups = sv(groups[1]?.querySelector('.perm-wl-groups')?.value);
        cbl.users = sv(groups[2]?.querySelector('.perm-bl-users')?.value);
        cbl.groups = sv(groups[3]?.querySelector('.perm-bl-groups')?.value);
      }
      
      c.whitelist = cwl;
      c.blacklist = cbl;
      cmds[cn] = c;
    });
    
    if(Object.keys(cmds).length) node.commands = cmds;
    out.sub_plugins[pn] = node;
  });
  return out;
}

async function loadPermissions(){
  try{
    showLoading(true);
    const p=await apiCall('/permissions');
    state.permissions=p;
    const ta=$('#permissions-json'); if(ta) ta.value=JSON.stringify(p,null,2);
    renderPermissionsList();
  } catch(e){ showToast('加载中权限失败: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false);} }
async function savePermissions(){
  try{
    const cfg = collectPermissionsFromUI();
    showLoading(true);
    await apiCall('/permissions',{method:'PUT', body: JSON.stringify(cfg)});
    showToast('权限配置宸蹭繚瀛?,'success');
    state.permissions=cfg;
    const ta=$('#permissions-json'); if(ta) ta.value=JSON.stringify(cfg,null,2);
  } catch(e){ showToast('淇濆瓨失败: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false);} }
async function loadConfig(){ try{ showLoading(true); const c=await apiCall('/config'); state.config=c; $('#config-json').value = JSON.stringify(c, null, 2); } catch(e){ showToast('加载中配置失败: '+(e&&e.message?e.message:e),'error'); } finally{ showLoading(false);} }
async function saveConfig(){ try{ const txt=$('#config-json').value; const cfg=JSON.parse(txt||'{}'); showLoading(true); await apiCall('/config',{method:'PUT', body: JSON.stringify(cfg)}); showToast('配置宸蹭繚瀛?,'success'); state.config=cfg; } catch(e){ showToast('淇濆瓨失败: '+(e&&e.message?e.message:e),'error'); } finally{ showLoading(false);} }

async function remindGroups(groupIds){ if(!Array.isArray(groupIds)||!groupIds.length) return; for(const gid of groupIds){ await apiCall('/remind_multi',{method:'POST', body: JSON.stringify({ group_id: gid })}); } }
async function leaveGroups(groupIds){ if(!Array.isArray(groupIds)||!groupIds.length) return; for(const gid of groupIds){ await apiCall('/leave_multi',{method:'POST', body: JSON.stringify({ group_id: gid })}); } }

// 浜嬩欢缁戝畾
function bindEvents(){
  $('#login-btn')?.addEventListener('click', handleLogin);
  $('#login-token')?.addEventListener('keypress', e=>{ if(e.key==='Enter') handleLogin(); });
  $('#theme-toggle')?.addEventListener('click', toggleTheme);
  $$('.nav-item').forEach(i=> i.addEventListener('click', e=>{ e.preventDefault(); switchTab(i.dataset.tab);}));
  $('#generate-code-btn')?.addEventListener('click', generateCode);
  $('#save-permissions-btn')?.addEventListener('click', savePermissions);
  $('#open-permissions-json-btn')?.addEventListener('click', openPermJsonModal);
  $('#perm-json-close')?.addEventListener('click', closePermJsonModal);
  $('#perm-json-cancel')?.addEventListener('click', closePermJsonModal);
  $('#perm-json-save')?.addEventListener('click', savePermJson);
  $('#save-config-btn')?.addEventListener('click', saveConfig);
  $('#group-search')?.addEventListener('input', e=>{ state.keyword=e.target.value.trim(); renderGroupsTable(); });
  $('#status-filter')?.addEventListener('change', e=>{ state.filter=e.target.value; renderGroupsTable(); });
  $('#select-all')?.addEventListener('change', e=> $$('.group-checkbox').forEach(cb=> cb.checked=e.target.checked));
  $('#refresh-btn')?.addEventListener('click', ()=>{ const active=$('.nav-item.active'); if(active) switchTab(active.dataset.tab); });
  const tbl=$('#groups-table-body');
  if(tbl){
    tbl.addEventListener('click', async (e)=>{
      const btn=e.target.closest('.btn-action'); if(!btn) return; const gid=parseInt(btn.dataset.gid);
      try{
        if(btn.classList.contains('btn-remind')){
          await remindGroups([gid]); showToast(`宸插悜缇?${gid} 鍙戦€佹彁閱抈,'success');
        } else if(btn.classList.contains('btn-extend')){
          await apiCall('/extend',{method:'POST', body: JSON.stringify({ group_id: gid, length:7, unit:'澶?})});
          showToast(`宸蹭负缇?${gid} 寤堕暱7澶ー,'success'); await loadRenewalData();
        } else if(btn.classList.contains('btn-leave')){
          if(!confirm(`纭璁╂満鍣ㄤ汉閫€鍑虹兢 ${gid}?`)) return; await leaveGroups([gid]);
          showToast(`宸查€€鍑虹兢 ${gid}`,'success'); await loadRenewalData();
        }
      } catch(err){ showToast('鎿嶄綔失败: '+(err&&err.message?err.message:err),'error'); }
    });
  }
  $('#codes-list')?.addEventListener('click', async (e)=>{ const btn=e.target.closest('.btn-copy'); if(!btn) return; const code=btn.dataset.code||''; const ok=await copyText(code); showToast(ok?'续费鐮佸凡复制':'复制失败', ok?'success':'error'); });

  // 统计绛涢€?鎺掑簭鎺т欢
  const kw = document.createElement('input'); kw.id='stats-keyword'; kw.className='input'; kw.placeholder='鎸?Bot杩囨护';
  const sel = document.createElement('select'); sel.id='stats-sort'; sel.className='input'; sel.innerHTML = `
    <option value="total_desc">鎸夋€诲彂閫?闄嶅簭)</option>
    <option value="total_asc">鎸夋€诲彂閫?鍗囧簭)</option>
    <option value="bot_asc">鎸塀ot(鍗囧簭)</option>
    <option value="bot_desc">鎸塀ot(闄嶅簭)</option>
    <option value="group_desc">鎸夌兢鑱婃暟(闄嶅簭)</option>
    <option value="private_desc">鎸夌鑱婃暟(闄嶅簭)</option>`;
  const statsTab = document.getElementById('tab-stats');
  if(statsTab){ const panel = statsTab.querySelector('.panel .table-container'); if(panel){ const bar=document.createElement('div'); bar.className='toolbar'; bar.style.margin='0 0 8px 0'; bar.appendChild(kw); bar.appendChild(sel); panel.parentElement.insertBefore(bar, panel); } }
  $('#stats-keyword')?.addEventListener('input', e=>{ state.statsKeyword=e.target.value.trim(); renderStatsDetails(state.stats?.today||{}); });
  $('#stats-sort')?.addEventListener('change', e=>{ state.statsSort=e.target.value; renderStatsDetails(state.stats?.today||{}); });
}

// 鐢熸垚续费鐮?
async function generateCode(){
  const btn=$('#generate-code-btn'); if(btn && btn.dataset.busy==='1') return; if(btn){ btn.dataset.busy='1'; btn.setAttribute('disabled','disabled'); }
  const length=parseInt($("#renewal-length").value)||30; let unit=$("#renewal-unit")?.value||"澶?; unit = normalizeUnit(unit);
  try{ showLoading(true); const r=await apiCall('/generate',{method:'POST', body: JSON.stringify({ length, unit })}); showToast(`续费鐮佸凡鐢熸垚: ${r.code}`,'success'); await loadRenewalData(); }
  catch(e){ showToast('鐢熸垚失败: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false); if(btn){ delete btn.dataset.busy; btn.removeAttribute('disabled'); } }
}

// 权限JSON寮圭獥
function openPermJsonModal(){
  const modal=document.getElementById('perm-json-modal');
  if(!modal) return;
  const ta=document.getElementById('permissions-json');
  if(ta){ ta.value = JSON.stringify(state.permissions || {}, null, 2); }
  modal.classList.remove('hidden');
}
function closePermJsonModal(){
  const modal=document.getElementById('perm-json-modal');
  if(modal) modal.classList.add('hidden');
}
async function savePermJson(){
  try{
    const ta=document.getElementById('permissions-json');
    const txt = ta && 'value' in ta ? ta.value : '{}';
    const cfg = JSON.parse(txt || '{}');
    showLoading(true);
    await apiCall('/permissions',{method:'PUT', body: JSON.stringify(cfg)});
    state.permissions = cfg;
    renderPermissionsList();
    showToast('JSON 宸蹭繚瀛?,'success');
    closePermJsonModal();
  }catch(e){ showToast('JSON 淇濆瓨失败: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false); }
}

// 鍒濆鍖?
async function init(){
  document.body.setAttribute('data-theme', state.theme);
  const i=document.querySelector('#theme-toggle .icon');
  if(i) i.textContent = state.theme==='light' ? '馃尀' : '馃寵';
  await loadDashboard();
  
  // 娣诲姞椤甸潰加载中鍔ㄧ敾
  animatePageLoad();
}

// 椤甸潰加载中鍔ㄧ敾
function animatePageLoad() {
  const cards = document.querySelectorAll('.stat-card');
  cards.forEach((card, index) => {
    card.style.opacity = '0';
    card.style.transform = 'translateY(30px)';
    setTimeout(() => {
      card.style.transition = 'all 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
      card.style.opacity = '1';
      card.style.transform = 'translateY(0)';
    }, index * 100);
  });
}

// 娣诲姞鍗＄墖鐐瑰嚮娉㈢汗鏁堟灉
function addRippleEffect(e) {
  const card = e.currentTarget;
  const ripple = document.createElement('span');
  const rect = card.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  const x = e.clientX - rect.left - size / 2;
  const y = e.clientY - rect.top - size / 2;
  
  ripple.style.cssText = `
    position: absolute;
    width: ${size}px;
    height: ${size}px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.3);
    left: ${x}px;
    top: ${y}px;
    pointer-events: none;
    animation: ripple 0.6s ease-out;
  `;
  
  card.style.position = 'relative';
  card.style.overflow = 'hidden';
  card.appendChild(ripple);
  
  setTimeout(() => ripple.remove(), 600);
}

// 娣诲姞CSS鍔ㄧ敾
if (!document.getElementById('ripple-animation')) {
  const style = document.createElement('style');
  style.id = 'ripple-animation';
  style.textContent = `
    @keyframes ripple {
      from {
        transform: scale(0);
        opacity: 1;
      }
      to {
        transform: scale(2);
        opacity: 0;
      }
    }
  `;
  document.head.appendChild(style);
}

// 澧炲己涓婚鍒囨崲鍔ㄧ敾
function toggleTheme(){
  const oldTheme = state.theme;
  state.theme = state.theme==='light' ? 'dark':'light';
  
  // 娣诲姞鍒囨崲鍔ㄧ敾
  document.body.style.transition = 'background 0.5s ease, color 0.5s ease';
  document.body.setAttribute('data-theme', state.theme);
  localStorage.setItem('theme', state.theme);
  
  const i=$('#theme-toggle .icon');
  if(i) {
    i.style.transform = 'rotate(360deg)';
    i.style.transition = 'transform 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
    setTimeout(() => {
      i.textContent = state.theme==='light' ? '馃尀' : '馃寵';
      i.style.transform = 'rotate(0deg)';
    }, 300);
  }
  
  // 鏄剧ず鍒囨崲鎻愮ず
  showToast(`宸插垏鎹㈠埌${state.theme==='light'?'浜壊':'鏆楄壊'}涓婚 鉁╜, 'success');
}

// 澧炲己鍒锋柊鎸夐挳鍔ㄧ敾
function enhanceRefreshButton() {
  const btn = $('#refresh-btn');
  if (btn) {
    btn.addEventListener('click', () => {
      const icon = btn.querySelector('.icon');
      if (icon) {
        icon.style.animation = 'spin 0.8s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
        setTimeout(() => {
          icon.style.animation = '';
        }, 800);
      }
    });
  }
}

// 涓虹粺璁″崱鐗囨坊鍔犱氦浜掓晥鏋?
function enhanceStatCards() {
  const cards = document.querySelectorAll('.stat-card');
  cards.forEach(card => {
    card.addEventListener('click', addRippleEffect);
    
    // 娣诲姞鎮仠鏁板瓧璺冲姩鏁堟灉
    card.addEventListener('mouseenter', () => {
      const value = card.querySelector('.stat-value');
      if (value && value.textContent !== '-') {
        value.style.transform = 'scale(1.1)';
        value.style.transition = 'transform 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
      }
    });
    
    card.addEventListener('mouseleave', () => {
      const value = card.querySelector('.stat-value');
      if (value) {
        value.style.transform = 'scale(1)';
      }
    });
  });
}

// 琛ㄦ牸琛屽姩鐢?
function animateTableRows() {
  const rows = document.querySelectorAll('.data-table tbody tr');
  rows.forEach((row, index) => {
    if (row.cells.length > 1) {
      row.style.opacity = '0';
      row.style.transform = 'translateX(-20px)';
      setTimeout(() => {
        row.style.transition = 'all 0.4s ease-out';
        row.style.opacity = '1';
        row.style.transform = 'translateX(0)';
      }, index * 50);
    }
  });
}

// 澧炲己鎸夐挳鐐瑰嚮鍙嶉
function enhanceButtons() {
  document.querySelectorAll('.btn').forEach(btn => {
    btn.addEventListener('click', function(e) {
      this.style.transform = 'scale(0.95)';
      setTimeout(() => {
        this.style.transform = '';
      }, 150);
    });
  });
}

// 骞虫粦婊氬姩鍒伴《閮?
function smoothScrollToTop() {
  window.scrollTo({
    top: 0,
    behavior: 'smooth'
  });
}

// 鐩戝惉鏍囩椤靛垏鎹紝娣诲姞鍔ㄧ敾
const originalSwitchTab = switchTab;
switchTab = function(tab) {
  originalSwitchTab(tab);
  
  // 鍒囨崲鍔ㄧ敾
  const content = document.querySelector(`#tab-${tab}`);
  if (content) {
    content.style.animation = 'fadeInContent 0.4s ease-out';
  }
  
  // 婊氬姩鍒伴《閮?
  smoothScrollToTop();
  
  // 鏍规嵁涓嶅悓鏍囩椤垫坊鍔犵壒瀹氬姩鐢?
  setTimeout(() => {
    if (tab === 'renewal') {
      animateTableRows();
    } else if (tab === 'dashboard') {
      enhanceStatCards();
    }
  }, 100);
};

window.addEventListener('DOMContentLoaded', ()=>{
  // 鏃犺璇侊細鐩存帴鏄剧ず搴旂敤
  $('#app').classList.remove('hidden');
  const lp = document.getElementById('login-page'); if (lp) lp.style.display='none';
  
  init();
  bindEvents();
  
  // 澧炲己浜や簰鏁堟灉
  enhanceRefreshButton();
  enhanceStatCards();
  enhanceButtons();
  
  // 娣诲姞椤甸潰鍙鎬х洃鍚紝鍒囨崲鍥炴潵鏃跺埛鏂版暟鎹?
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      const activeTab = document.querySelector('.nav-item.active');
      if (activeTab) {
        const tab = activeTab.dataset.tab;
        if (tab === 'dashboard') {
          loadDashboard();
        }
      }
    }
  });
});

// ---- Override permissions UI for flat schema (top + sub_plugins) ----
const __legacy_renderPermissionsList = function(){
  const wrap=document.getElementById('permissions-list');
  if(!wrap) return;
  const data = state.permissions || {};
  const from=(x)=> (x && typeof x==='object')?x:{};
  const esc=(s)=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const toCSV=(arr)=>Array.isArray(arr)?arr.join(','):(arr||'');
  const optLevel = (v)=>`<option value="all" ${v==='all'?'selected':''}>鎵€鏈変汉</option>
    <option value="member" ${v==='member'?'selected':''}>缇ゆ垚鍛?/option>
    <option value="admin" ${v==='admin'?'selected':''}>缇ょ鐞?/option>
    <option value="owner" ${v==='owner'?'selected':''}>缇や富</option>
    <option value="superuser" ${v==='superuser'?'selected':''}>瓒呯骇鐢ㄦ埛</option>`;
  const optScene = (v)=>`<option value="all" ${v==='all'?'selected':''}>鍏ㄩ儴</option>
    <option value="group" ${v==='group'?'selected':''}>缇よ亰</option>
    <option value="private" ${v==='private'?'selected':''}>绉佽亰</option>`;

  const globalTop = from(data.top);
  const gWl = from(globalTop.whitelist);
  const gBl = from(globalTop.blacklist);

  const globalHTML = `
    <div id="perm-global" class="perm-global-block panel" style="margin-bottom: 16px;">
      <div class="panel-header" style="display:flex;align-items:center;justify-content:space-between;">
        <div style="font-weight:600;">馃寪 鍏ㄥ眬权限</div>
        <label class="perm-field">
          <input type="checkbox" class="perm-enabled" ${globalTop.enabled===false?'':'checked'}>
          <span>榛樿鍚敤</span>
        </label>
      </div>
      <div class="panel-body">
        <div class="perm-plugin-inline-config">
          <label class="perm-field">
            <span>馃懁 榛樿权限绛夌骇</span>
            <select class="perm-level">${optLevel(String(globalTop.level||'all'))}</select>
          </label>
          <label class="perm-field">
            <span>馃挰 榛樿浣跨敤鍦烘櫙</span>
            <select class="perm-scene">${optScene(String(globalTop.scene||'all'))}</select>
          </label>
        </div>
        <div class="perm-lists-section" style="margin-top:8px;">
          <div class="perm-list-group">
            <label class="perm-list-label">馃 鐧藉悕鍗曠敤鎴?/label>
            <input type="text" class="perm-list-input perm-wl-users" placeholder="鐢ㄦ埛ID锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(gWl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">馃 鐧藉悕鍗曠兢缁?/label>
            <input type="text" class="perm-list-input perm-wl-groups" placeholder="缇ゅ彿锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(gWl.groups))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">馃枻 榛戝悕鍗曠敤鎴?/label>
            <input type="text" class="perm-list-input perm-bl-users" placeholder="鐢ㄦ埛ID锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(gBl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">馃枻 榛戝悕鍗曠兢缁?/label>
            <input type="text" class="perm-list-input perm-bl-groups" placeholder="缇ゅ彿锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(gBl.groups))}">
          </div>
        </div>
      </div>
    </div>`;

  const sub = from(data.sub_plugins);
  const pluginNames = Object.keys(sub).sort((a,b)=>a.localeCompare(b));

  const rows = pluginNames.map((pn, index)=>{
    const node = from(sub[pn]);
    const top = from(node.top);
    const cmds = from(node.commands);
    const wl = from(top.whitelist);
    const bl = from(top.blacklist);

    const cmdRows = Object.keys(cmds||{}).sort((a,b)=>a.localeCompare(b)).map(cn=>{
      const c=from(cmds[cn]);
      const cwl=from(c.whitelist);
      const cbl=from(c.blacklist);
      return `<div class="perm-command-item" data-command="${esc(cn)}">
        <div class="perm-command-header">
          <div class="perm-command-name">馃搶 ${esc(cn)}</div>
          <div class="perm-command-inline-config">
            <label class="perm-field">
              <input type="checkbox" class="perm-enabled" ${c.enabled===false?'':'checked'}>
              <span>鍚敤</span>
            </label>
            <label class="perm-field">
              <span>馃懁 绛夌骇</span>
              <select class="perm-level">${optLevel(String(c.level||'all'))}</select>
            </label>
            <label class="perm-field">
              <span>馃挰 鍦烘櫙</span>
              <select class="perm-scene">${optScene(String(c.scene||'all'))}</select>
            </label>
          </div>
        </div>
        <div class="perm-command-lists">
          <div class="perm-list-group">
            <label class="perm-list-label">馃 鐧藉悕鍗曠敤鎴?/label>
            <input type="text" class="perm-list-input perm-wl-users" placeholder="澶氫釜鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(cwl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">馃 鐧藉悕鍗曠兢缁?/label>
            <input type="text" class="perm-list-input perm-wl-groups" placeholder="澶氫釜鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(cwl.groups))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">馃枻 榛戝悕鍗曠敤鎴?/label>
            <input type="text" class="perm-list-input perm-bl-users" placeholder="澶氫釜鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(cbl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">馃枻 榛戝悕鍗曠兢缁?/label>
            <input type="text" class="perm-list-input perm-bl-groups" placeholder="澶氫釜鐢ㄩ€楀彿鍒嗛殧" value="${esc(toCSV(cbl.groups))}">
          </div>
        </div>
      </div>`;
    }).join('');

    return `<div class="perm-accordion-item" data-plugin="${esc(pn)}">
      <div class="perm-accordion-header" data-index="${index}">
        <div class="perm-accordion-title">
          <span class="perm-accordion-icon">鈻讹笍</span>
          <span>馃攲 ${esc(pn)}</span>
        </div>
        <label class="perm-field" onclick="event.stopPropagation()">
          <input type="checkbox" class="perm-enabled" ${top.enabled===false?'':'checked'}>
          <span>榛樿鍚敤</span>
        </label>
      </div>
      <div class="perm-accordion-content">
        <div class="perm-accordion-body">
          <div class="perm-plugin-inline-config">
            <label class="perm-field">
              <span>馃懁 榛樿权限绛夌骇</span>
              <select class="perm-level">${optLevel(String(top.level||'all'))}</select>
            </label>
            <label class="perm-field">
              <span>馃挰 榛樿浣跨敤鍦烘櫙</span>
              <select class="perm-scene">${optScene(String(top.scene||'all'))}</select>
            </label>
          </div>
          <div class="perm-lists-section">
            <div class="perm-list-group">
              <label class="perm-list-label">馃 鐧藉悕鍗曠敤鎴?/label>
              <input type="text" class="perm-list-input perm-wl-users" placeholder="鐢ㄦ埛ID锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(wl.users))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">馃 鐧藉悕鍗曠兢缁?/label>
              <input type="text" class="perm-list-input perm-wl-groups" placeholder="缇ゅ彿锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(wl.groups))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">馃枻 榛戝悕鍗曠敤鎴?/label>
              <input type="text" class="perm-list-input perm-bl-users" placeholder="鐢ㄦ埛ID锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(bl.users))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">馃枻 榛戝悕鍗曠兢缁?/label>
              <input type="text" class="perm-list-input perm-bl-groups" placeholder="缇ゅ彿锛屽涓敤閫楀彿鍒嗛殧" value="${esc(toCSV(bl.groups))}">
            </div>
          </div>
          ${Object.keys(cmds||{}).length ? `
            <div class="perm-commands-section">
              <div class="perm-commands-title">馃搵 鍛戒护权限配置 (${Object.keys(cmds||{}).length}鏉″懡浠?</div>
              <div class="perm-commands-list">${cmdRows}</div>
            </div>
          ` : '<div class="empty-state" style="padding: 40px 20px;">馃挙 璇ユ彃浠舵殏鏃犲懡浠?/div>'}
        </div>
      </div>
    </div>`;
  });

  const pluginsHTML = rows.join('') || '<div class="empty-state">鏆傛棤瀛愭彃浠?/div>';
  wrap.innerHTML = globalHTML + pluginsHTML;

  // 鎶樺彔闈㈡澘浜や簰锛堜粎鎻掍欢鍧楋級
  wrap.querySelectorAll('.perm-accordion-header').forEach(header => {
    header.addEventListener('click', function(e) {
      const item = this.closest('.perm-accordion-item');
      const content = item.querySelector('.perm-accordion-content');
      const isActive = this.classList.contains('active');
      wrap.querySelectorAll('.perm-accordion-header').forEach(h => {
        h.classList.remove('active');
        h.closest('.perm-accordion-item')?.querySelector('.perm-accordion-content')?.classList.remove('active');
      });
      if (!isActive) {
        this.classList.add('active');
        content.classList.add('active');
      }
    });
  });
};

const __legacy_collectPermissionsFromUI = function(){
  const wrap=document.getElementById('permissions-list');
  if(!wrap){
    try{ const txt=$('#permissions-json')?.value||'{}'; return JSON.parse(txt); }catch{ return {}; }
  }
  const out={ top: { enabled:true, level:'all', scene:'all', whitelist:{users:[],groups:[]}, blacklist:{users:[],groups:[]} }, sub_plugins: {} };
  const sv=(s)=> String(s||'').split(',').map(x=>x.trim()).filter(Boolean);
  // 鍏ㄥ眬
  const g = document.getElementById('perm-global') || wrap;
  try{
    const gTop = {};
    gTop.enabled = g.querySelector('.perm-enabled')?.checked ?? true;
    gTop.level = g.querySelector('.perm-level')?.value || 'all';
    gTop.scene = g.querySelector('.perm-scene')?.value || 'all';
    const wl={ users:[], groups:[] }, bl={ users:[], groups:[] };
    wl.users = sv(g.querySelector('.perm-wl-users')?.value);
    wl.groups = sv(g.querySelector('.perm-wl-groups')?.value);
    bl.users = sv(g.querySelector('.perm-bl-users')?.value);
    bl.groups = sv(g.querySelector('.perm-bl-groups')?.value);
    gTop.whitelist = wl; gTop.blacklist = bl;
    out.top = gTop;
  }catch{}
  // 瀛愭彃浠?
  wrap.querySelectorAll('.perm-accordion-item').forEach(item=>{
    const pn = item.getAttribute('data-plugin')||''; if(!pn) return;
    const node = {};
    const header = item.querySelector('.perm-accordion-header');
    const body = item.querySelector('.perm-accordion-body');
    const top={};
    top.enabled = header.querySelector('.perm-enabled')?.checked ?? true;
    top.level = body.querySelector('.perm-plugin-inline-config .perm-level')?.value || 'all';
    top.scene = body.querySelector('.perm-plugin-inline-config .perm-scene')?.value || 'all';
    const wl={ users:[], groups:[] }, bl={ users:[], groups:[] };
    const listsSection = body.querySelector('.perm-lists-section');
    if(listsSection){
      wl.users = sv(listsSection.querySelector('.perm-wl-users')?.value);
      wl.groups = sv(listsSection.querySelector('.perm-wl-groups')?.value);
      bl.users = sv(listsSection.querySelector('.perm-bl-users')?.value);
      bl.groups = sv(listsSection.querySelector('.perm-bl-groups')?.value);
    }
    top.whitelist = wl; top.blacklist = bl; node.top = top;
    const cmds={};
    body.querySelectorAll('.perm-command-item').forEach(cmdEl=>{
      const cn = cmdEl.getAttribute('data-command')||''; if(!cn) return;
      const c={};
      c.enabled = cmdEl.querySelector('.perm-command-inline-config .perm-enabled')?.checked ?? true;
      c.level = cmdEl.querySelector('.perm-command-inline-config .perm-level')?.value || 'all';
      c.scene = cmdEl.querySelector('.perm-command-inline-config .perm-scene')?.value || 'all';
      const cwl={ users:[], groups:[] }, cbl={ users:[], groups:[] };
      const cmdLists = cmdEl.querySelector('.perm-command-lists');
      if(cmdLists){
        const groups = cmdLists.querySelectorAll('.perm-list-group');
        cwl.users = sv(groups[0]?.querySelector('.perm-wl-users')?.value);
        cwl.groups = sv(groups[1]?.querySelector('.perm-wl-groups')?.value);
        cbl.users = sv(groups[2]?.querySelector('.perm-bl-users')?.value);
        cbl.groups = sv(groups[3]?.querySelector('.perm-bl-groups')?.value);
      }
      c.whitelist = cwl; c.blacklist = cbl; cmds[cn] = c;
    });
    if(Object.keys(cmds).length) node.commands = cmds;
    out.sub_plugins[pn] = node;
  });
  return out;
};

window.switchTab = switchTab;
window.runScheduledTask = async function(){
  try{
    showLoading(true);
    const r=await apiCall('/job/run',{method:'POST'});
    showToast(`鉁?妫€鏌ュ畬鎴愶紒提醒 ${r.reminded} 涓兢锛岄€€鍑?${r.left} 涓兢`,'success');
  } catch(e){
    showToast('鎵ц失败: '+(e&&e.message?e.message:e),'error');
  } finally{
    showLoading(false);
  }
};

// 娣诲姞閿洏蹇嵎閿敮鎸?
document.addEventListener('keydown', (e) => {
  // Ctrl/Cmd + K: 鎼滅储
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const searchInput = document.querySelector('#group-search');
    if (searchInput) {
      searchInput.focus();
      searchInput.select();
    }
  }
  
  // Ctrl/Cmd + R: 鍒锋柊
  if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
    e.preventDefault();
    const refreshBtn = document.querySelector('#refresh-btn');
    if (refreshBtn) {
      refreshBtn.click();
    }
  }
  
  // Ctrl/Cmd + D: 鍒囨崲涓婚
  if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
    e.preventDefault();
    const themeBtn = document.querySelector('#theme-toggle');
    if (themeBtn) {
      themeBtn.click();
    }
  }
  
  // ESC: 鍏抽棴妯℃€佹
  if (e.key === 'Escape') {
    const modal = document.querySelector('.modal:not(.hidden)');
    if (modal) {
      closePermJsonModal();
    }
  }
});

// 控制台版杩庝俊鎭?
console.log('%c馃尭 浠婃睈绠＄悊控制台?, 'font-size: 24px; color: #667eea; font-weight: bold;');
console.log('%c鉁?娆㈣繋浣跨敤鐜颁唬鍖栫鐞嗙晫闈?, 'font-size: 14px; color: #6366f1;');
console.log('%c蹇嵎閿彁绀?\n  Ctrl+K: 鎼滅储\n  Ctrl+R: 鍒锋柊\n  Ctrl+D: 鍒囨崲涓婚\n  ESC: 鍏抽棴寮圭獥', 'font-size: 12px; color: #94a3b8; line-height: 1.8;');






