// ==================== 今汐控制台前端（UTF-8） ====================

// 全局状态
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
function normalizeUnit(u){ const x=String(u||'').trim().toLowerCase(); if(['d','day','天'].includes(x)) return '天'; if(['m','month','月'].includes(x)) return '月'; if(['y','year','年'].includes(x)) return '年'; return '天'; }
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
  } catch(e){ showToast('登录失败: '+(e&&e.message?e.message:e),'error'); }
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
  } catch(e){ showToast('加载仪表盘失败: '+(e&&e.message?e.message:e),'error'); }
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
  } catch(e){ showToast('加载续费数据失败: '+(e&&e.message?e.message:e),'error'); }
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

// 统计（读取 /member_renewal/stats/today 并仅展示今天）
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
    // 过滤
    const kw = (state.statsKeyword||'').trim();
    if(kw){
      rows = rows.filter(r=> r.id.includes(kw) || Object.keys(r.gT).some(k=>k.includes(kw)) || Object.keys(r.pT).some(k=>k.includes(kw)) );
    }
    // 排序
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
    </tr>`).join('') : '<tr><td colspan="6" class="text-center">无数据</td></tr>';
  }catch{}
}

// 新的手风琴式权限列表渲染
function renderPermissionsList(){
  const wrap=document.getElementById('permissions-list');
  if(!wrap) return;
  const data = state.permissions || {};
  const sub = (data.sub_plugins||{});
  const plugins = Object.keys(sub).sort((a,b)=>a.localeCompare(b));
  if(!plugins.length && !data.top){ wrap.innerHTML = '<div class="empty-state">💤 暂无权限数据</div>'; return; }
  
  const optLevel = (v)=>`<option value="all" ${v==='all'?'selected':''}>所有人</option>
    <option value="member" ${v==='member'?'selected':''}>群成员</option>
    <option value="admin" ${v==='admin'?'selected':''}>群管理</option>
    <option value="owner" ${v==='owner'?'selected':''}>群主</option>
    <option value="superuser" ${v==='superuser'?'selected':''}>超级用户</option>`;
  const optScene = (v)=>`<option value="all" ${v==='all'?'selected':''}>全部</option>
    <option value="group" ${v==='group'?'selected':''}>群聊</option>
    <option value="private" ${v==='private'?'selected':''}>私聊</option>`;
  const toCSV=(arr)=>Array.isArray(arr)?arr.join(','):(arr||'');
  const from=(x)=> (x && typeof x==='object')?x:{};
  const esc=(s)=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  // 全局权限块（顶上一个总的控制）
  const globalTop = from(data.top);
  const gWl = from(globalTop.whitelist);
  const gBl = from(globalTop.blacklist);
  const globalHTML = `
    <div id="perm-global" class="perm-global-block panel" style="margin-bottom: 16px;">
      <div class="panel-header" style="display:flex;align-items:center;justify-content:space-between;">
        <div style="font-weight:600;">🌐 全局权限</div>
        <label class="perm-field">
          <input type="checkbox" class="perm-enabled" ${globalTop.enabled===false?'':'checked'}>
          <span>默认启用</span>
        </label>
      </div>
      <div class="panel-body">
        <div class="perm-plugin-inline-config">
          <label class="perm-field">
            <span>👤 默认权限等级</span>
            <select class="perm-level">${optLevel(String(globalTop.level||'all'))}</select>
          </label>
          <label class="perm-field">
            <span>💬 默认使用场景</span>
            <select class="perm-scene">${optScene(String(globalTop.scene||'all'))}</select>
          </label>
        </div>
        <div class="perm-lists-section" style="margin-top:8px;">
          <div class="perm-list-group">
            <label class="perm-list-label">🤍 白名单用�?/label>
            <input type="text" class="perm-list-input perm-wl-users" placeholder="用户ID，多个用逗号分隔" value="${esc(toCSV(gWl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">🤍 白名单群�?/label>
            <input type="text" class="perm-list-input perm-wl-groups" placeholder="群号，多个用逗号分隔" value="${esc(toCSV(gWl.groups))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">🖤 黑名单用�?/label>
            <input type="text" class="perm-list-input perm-bl-users" placeholder="用户ID，多个用逗号分隔" value="${esc(toCSV(gBl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">🖤 黑名单群�?/label>
            <input type="text" class="perm-list-input perm-bl-groups" placeholder="群号，多个用逗号分隔" value="${esc(toCSV(gBl.groups))}">
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
    
    // 命令列表HTML - 改用插件样式的网格布局
    const cmdRows = Object.keys(cmds).sort((a,b)=>a.localeCompare(b)).map(cn=>{
      const c=from(cmds[cn]);
      const cwl=from(c.whitelist);
      const cbl=from(c.blacklist);
      return `<div class="perm-command-item" data-command="${esc(cn)}">
        <div class="perm-command-header">
          <div class="perm-command-name">📌 ${esc(cn)}</div>
          <div class="perm-command-inline-config">
            <label class="perm-field">
              <input type="checkbox" class="perm-enabled" ${c.enabled===false?'':'checked'}>
              <span>启用</span>
            </label>
            <label class="perm-field">
              <span>👤 等级</span>
              <select class="perm-level">${optLevel(String(c.level||'all'))}</select>
            </label>
            <label class="perm-field">
              <span>💬 场景</span>
              <select class="perm-scene">${optScene(String(c.scene||'all'))}</select>
            </label>
          </div>
        </div>
        <div class="perm-command-lists">
          <div class="perm-list-group">
            <label class="perm-list-label">✅ 白名单用户</label>
            <input type="text" class="perm-list-input perm-wl-users" placeholder="多个用逗号分隔" value="${esc(toCSV(cwl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">✅ 白名单群组</label>
            <input type="text" class="perm-list-input perm-wl-groups" placeholder="多个用逗号分隔" value="${esc(toCSV(cwl.groups))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">⛔ 黑名单用户</label>
            <input type="text" class="perm-list-input perm-bl-users" placeholder="多个用逗号分隔" value="${esc(toCSV(cbl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">⛔ 黑名单群组</label>
            <input type="text" class="perm-list-input perm-bl-groups" placeholder="多个用逗号分隔" value="${esc(toCSV(cbl.groups))}">
          </div>
        </div>
      </div>`;
    }).join('');
    
    return `<div class="perm-accordion-item" data-plugin="${esc(pn)}">
      <div class="perm-accordion-header" data-index="${index}">
        <div class="perm-accordion-title">
          <span class="perm-accordion-icon">▶️</span>
          <span>🔌 ${esc(pn)}</span>
        </div>
        <label class="perm-field" onclick="event.stopPropagation()">
          <input type="checkbox" class="perm-enabled" ${top.enabled===false?'':'checked'}>
          <span>启用插件</span>
        </label>
      </div>
      <div class="perm-accordion-content">
        <div class="perm-accordion-body">
          <div class="perm-plugin-inline-config">
            <label class="perm-field">
              <span>👤 默认权限等级</span>
              <select class="perm-level">${optLevel(String(top.level||'all'))}</select>
            </label>
            <label class="perm-field">
              <span>💬 默认使用场景</span>
              <select class="perm-scene">${optScene(String(top.scene||'all'))}</select>
            </label>
          </div>
          
          <div class="perm-lists-section">
            <div class="perm-list-group">
              <label class="perm-list-label">✅ 白名单用户</label>
              <input type="text" class="perm-list-input perm-wl-users" placeholder="多个ID用逗号分隔" value="${esc(toCSV(wl.users))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">✅ 白名单群组</label>
              <input type="text" class="perm-list-input perm-wl-groups" placeholder="多个群号用逗号分隔" value="${esc(toCSV(wl.groups))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">⛔ 黑名单用户</label>
              <input type="text" class="perm-list-input perm-bl-users" placeholder="多个ID用逗号分隔" value="${esc(toCSV(bl.users))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">⛔ 黑名单群组</label>
              <input type="text" class="perm-list-input perm-bl-groups" placeholder="多个群号用逗号分隔" value="${esc(toCSV(bl.groups))}">
            </div>
          </div>
          
          ${Object.keys(cmds).length ? `
            <div class="perm-commands-section">
              <div class="perm-commands-title">🎯 命令权限配置 (${Object.keys(cmds).length}个命令)</div>
              <div class="perm-commands-list">${cmdRows}</div>
            </div>
          ` : '<div class="empty-state" style="padding: 40px 20px;">💤 该插件暂无命令</div>'}
        </div>
      </div>
    </div>`;
  });
  
  const pluginsHTML = rows.join('') || '<div class="empty-state">暂无子插�?/div>';
  wrap.innerHTML = globalHTML + pluginsHTML;
  
  // 绑定手风琴点击事件
  wrap.querySelectorAll('.perm-accordion-header').forEach(header => {
    header.addEventListener('click', function(e) {
      const item = this.closest('.perm-accordion-item');
      const content = item.querySelector('.perm-accordion-content');
      const isActive = this.classList.contains('active');
      
      // 关闭所有其他项
      wrap.querySelectorAll('.perm-accordion-header').forEach(h => {
        h.classList.remove('active');
        h.closest('.perm-accordion-item').querySelector('.perm-accordion-content').classList.remove('active');
      });
      
      // 切换当前项
      if (!isActive) {
        this.classList.add('active');
        content.classList.add('active');
      }
    });
  });
}

// 从UI收集权限配置（适配新的手风琴结构）
function collectPermissionsFromUI(){
  const wrap=document.getElementById('permissions-list');
  if(!wrap){
    try{ const txt=$('#permissions-json')?.value||'{}'; return JSON.parse(txt); }catch{ return {}; }
  }
  const out={ top: { enabled:true, level:'all', scene:'all', whitelist:{users:[],groups:[]}, blacklist:{users:[],groups:[]} }, sub_plugins: {} };
  // 收集全局(top)设置
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
    
    // 获取插件顶级配置
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
    
    // 获取命令配置
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
  } catch(e){ showToast('加载权限失败: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false);} }
async function savePermissions(){
  try{
    const cfg = collectPermissionsFromUI();
    showLoading(true);
    await apiCall('/permissions',{method:'PUT', body: JSON.stringify(cfg)});
    showToast('权限配置已保存','success');
    state.permissions=cfg;
    const ta=$('#permissions-json'); if(ta) ta.value=JSON.stringify(cfg,null,2);
  } catch(e){ showToast('保存失败: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false);} }
async function loadConfig(){ try{ showLoading(true); const c=await apiCall('/config'); state.config=c; $('#config-json').value = JSON.stringify(c, null, 2); } catch(e){ showToast('加载配置失败: '+(e&&e.message?e.message:e),'error'); } finally{ showLoading(false);} }
async function saveConfig(){ try{ const txt=$('#config-json').value; const cfg=JSON.parse(txt||'{}'); showLoading(true); await apiCall('/config',{method:'PUT', body: JSON.stringify(cfg)}); showToast('配置已保存','success'); state.config=cfg; } catch(e){ showToast('保存失败: '+(e&&e.message?e.message:e),'error'); } finally{ showLoading(false);} }

async function remindGroups(groupIds){ if(!Array.isArray(groupIds)||!groupIds.length) return; for(const gid of groupIds){ await apiCall('/remind_multi',{method:'POST', body: JSON.stringify({ group_id: gid })}); } }
async function leaveGroups(groupIds){ if(!Array.isArray(groupIds)||!groupIds.length) return; for(const gid of groupIds){ await apiCall('/leave_multi',{method:'POST', body: JSON.stringify({ group_id: gid })}); } }

// 事件绑定
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
          await remindGroups([gid]); showToast(`已向群 ${gid} 发送提醒`,'success');
        } else if(btn.classList.contains('btn-extend')){
          await apiCall('/extend',{method:'POST', body: JSON.stringify({ group_id: gid, length:7, unit:'天'})});
          showToast(`已为群 ${gid} 延长7天`,'success'); await loadRenewalData();
        } else if(btn.classList.contains('btn-leave')){
          if(!confirm(`确认让机器人退出群 ${gid}?`)) return; await leaveGroups([gid]);
          showToast(`已退出群 ${gid}`,'success'); await loadRenewalData();
        }
      } catch(err){ showToast('操作失败: '+(err&&err.message?err.message:err),'error'); }
    });
  }
  $('#codes-list')?.addEventListener('click', async (e)=>{ const btn=e.target.closest('.btn-copy'); if(!btn) return; const code=btn.dataset.code||''; const ok=await copyText(code); showToast(ok?'续费码已复制':'复制失败', ok?'success':'error'); });

  // 统计筛选/排序控件
  const kw = document.createElement('input'); kw.id='stats-keyword'; kw.className='input'; kw.placeholder='按 Bot过滤';
  const sel = document.createElement('select'); sel.id='stats-sort'; sel.className='input'; sel.innerHTML = `
    <option value="total_desc">按总发送(降序)</option>
    <option value="total_asc">按总发送(升序)</option>
    <option value="bot_asc">按Bot(升序)</option>
    <option value="bot_desc">按Bot(降序)</option>
    <option value="group_desc">按群聊数(降序)</option>
    <option value="private_desc">按私聊数(降序)</option>`;
  const statsTab = document.getElementById('tab-stats');
  if(statsTab){ const panel = statsTab.querySelector('.panel .table-container'); if(panel){ const bar=document.createElement('div'); bar.className='toolbar'; bar.style.margin='0 0 8px 0'; bar.appendChild(kw); bar.appendChild(sel); panel.parentElement.insertBefore(bar, panel); } }
  $('#stats-keyword')?.addEventListener('input', e=>{ state.statsKeyword=e.target.value.trim(); renderStatsDetails(state.stats?.today||{}); });
  $('#stats-sort')?.addEventListener('change', e=>{ state.statsSort=e.target.value; renderStatsDetails(state.stats?.today||{}); });
}

// 生成续费码
async function generateCode(){
  const btn=$('#generate-code-btn'); if(btn && btn.dataset.busy==='1') return; if(btn){ btn.dataset.busy='1'; btn.setAttribute('disabled','disabled'); }
  const length=parseInt($("#renewal-length").value)||30; let unit=$("#renewal-unit")?.value||"天"; unit = normalizeUnit(unit);
  try{ showLoading(true); const r=await apiCall('/generate',{method:'POST', body: JSON.stringify({ length, unit })}); showToast(`续费码已生成: ${r.code}`,'success'); await loadRenewalData(); }
  catch(e){ showToast('生成失败: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false); if(btn){ delete btn.dataset.busy; btn.removeAttribute('disabled'); } }
}

// 权限JSON弹窗
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
    showToast('JSON 已保存','success');
    closePermJsonModal();
  }catch(e){ showToast('JSON 保存失败: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false); }
}

// 初始化
async function init(){
  document.body.setAttribute('data-theme', state.theme);
  const i=document.querySelector('#theme-toggle .icon');
  if(i) i.textContent = state.theme==='light' ? '🌞' : '🌙';
  await loadDashboard();
  
  // 添加页面加载动画
  animatePageLoad();
}

// 页面加载动画
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

// 添加卡片点击波纹效果
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

// 添加CSS动画
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

// 增强主题切换动画
function toggleTheme(){
  const oldTheme = state.theme;
  state.theme = state.theme==='light' ? 'dark':'light';
  
  // 添加切换动画
  document.body.style.transition = 'background 0.5s ease, color 0.5s ease';
  document.body.setAttribute('data-theme', state.theme);
  localStorage.setItem('theme', state.theme);
  
  const i=$('#theme-toggle .icon');
  if(i) {
    i.style.transform = 'rotate(360deg)';
    i.style.transition = 'transform 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
    setTimeout(() => {
      i.textContent = state.theme==='light' ? '🌞' : '🌙';
      i.style.transform = 'rotate(0deg)';
    }, 300);
  }
  
  // 显示切换提示
  showToast(`已切换到${state.theme==='light'?'亮色':'暗色'}主题 ✨`, 'success');
}

// 增强刷新按钮动画
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

// 为统计卡片添加交互效果
function enhanceStatCards() {
  const cards = document.querySelectorAll('.stat-card');
  cards.forEach(card => {
    card.addEventListener('click', addRippleEffect);
    
    // 添加悬停数字跳动效果
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

// 表格行动画
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

// 增强按钮点击反馈
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

// 平滑滚动到顶部
function smoothScrollToTop() {
  window.scrollTo({
    top: 0,
    behavior: 'smooth'
  });
}

// 监听标签页切换，添加动画
const originalSwitchTab = switchTab;
switchTab = function(tab) {
  originalSwitchTab(tab);
  
  // 切换动画
  const content = document.querySelector(`#tab-${tab}`);
  if (content) {
    content.style.animation = 'fadeInContent 0.4s ease-out';
  }
  
  // 滚动到顶部
  smoothScrollToTop();
  
  // 根据不同标签页添加特定动画
  setTimeout(() => {
    if (tab === 'renewal') {
      animateTableRows();
    } else if (tab === 'dashboard') {
      enhanceStatCards();
    }
  }, 100);
};

window.addEventListener('DOMContentLoaded', ()=>{
  // 无认证：直接显示应用
  $('#app').classList.remove('hidden');
  const lp = document.getElementById('login-page'); if (lp) lp.style.display='none';
  
  init();
  bindEvents();
  
  // 增强交互效果
  enhanceRefreshButton();
  enhanceStatCards();
  enhanceButtons();
  
  // 添加页面可见性监听，切换回来时刷新数据
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
  const optLevel = (v)=>`<option value="all" ${v==='all'?'selected':''}>所有人</option>
    <option value="member" ${v==='member'?'selected':''}>群成员</option>
    <option value="admin" ${v==='admin'?'selected':''}>群管理</option>
    <option value="owner" ${v==='owner'?'selected':''}>群主</option>
    <option value="superuser" ${v==='superuser'?'selected':''}>超级用户</option>`;
  const optScene = (v)=>`<option value="all" ${v==='all'?'selected':''}>全部</option>
    <option value="group" ${v==='group'?'selected':''}>群聊</option>
    <option value="private" ${v==='private'?'selected':''}>私聊</option>`;

  const globalTop = from(data.top);
  const gWl = from(globalTop.whitelist);
  const gBl = from(globalTop.blacklist);

  const globalHTML = `
    <div id="perm-global" class="perm-global-block panel" style="margin-bottom: 16px;">
      <div class="panel-header" style="display:flex;align-items:center;justify-content:space-between;">
        <div style="font-weight:600;">🌐 全局权限</div>
        <label class="perm-field">
          <input type="checkbox" class="perm-enabled" ${globalTop.enabled===false?'':'checked'}>
          <span>默认启用</span>
        </label>
      </div>
      <div class="panel-body">
        <div class="perm-plugin-inline-config">
          <label class="perm-field">
            <span>👤 默认权限等级</span>
            <select class="perm-level">${optLevel(String(globalTop.level||'all'))}</select>
          </label>
          <label class="perm-field">
            <span>💬 默认使用场景</span>
            <select class="perm-scene">${optScene(String(globalTop.scene||'all'))}</select>
          </label>
        </div>
        <div class="perm-lists-section" style="margin-top:8px;">
          <div class="perm-list-group">
            <label class="perm-list-label">🤍 白名单用户</label>
            <input type="text" class="perm-list-input perm-wl-users" placeholder="用户ID，多个用逗号分隔" value="${esc(toCSV(gWl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">🤍 白名单群组</label>
            <input type="text" class="perm-list-input perm-wl-groups" placeholder="群号，多个用逗号分隔" value="${esc(toCSV(gWl.groups))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">🖤 黑名单用户</label>
            <input type="text" class="perm-list-input perm-bl-users" placeholder="用户ID，多个用逗号分隔" value="${esc(toCSV(gBl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">🖤 黑名单群组</label>
            <input type="text" class="perm-list-input perm-bl-groups" placeholder="群号，多个用逗号分隔" value="${esc(toCSV(gBl.groups))}">
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
          <div class="perm-command-name">📌 ${esc(cn)}</div>
          <div class="perm-command-inline-config">
            <label class="perm-field">
              <input type="checkbox" class="perm-enabled" ${c.enabled===false?'':'checked'}>
              <span>启用</span>
            </label>
            <label class="perm-field">
              <span>👤 等级</span>
              <select class="perm-level">${optLevel(String(c.level||'all'))}</select>
            </label>
            <label class="perm-field">
              <span>💬 场景</span>
              <select class="perm-scene">${optScene(String(c.scene||'all'))}</select>
            </label>
          </div>
        </div>
        <div class="perm-command-lists">
          <div class="perm-list-group">
            <label class="perm-list-label">🤍 白名单用户</label>
            <input type="text" class="perm-list-input perm-wl-users" placeholder="多个用逗号分隔" value="${esc(toCSV(cwl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">🤍 白名单群组</label>
            <input type="text" class="perm-list-input perm-wl-groups" placeholder="多个用逗号分隔" value="${esc(toCSV(cwl.groups))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">🖤 黑名单用户</label>
            <input type="text" class="perm-list-input perm-bl-users" placeholder="多个用逗号分隔" value="${esc(toCSV(cbl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">🖤 黑名单群组</label>
            <input type="text" class="perm-list-input perm-bl-groups" placeholder="多个用逗号分隔" value="${esc(toCSV(cbl.groups))}">
          </div>
        </div>
      </div>`;
    }).join('');

    return `<div class="perm-accordion-item" data-plugin="${esc(pn)}">
      <div class="perm-accordion-header" data-index="${index}">
        <div class="perm-accordion-title">
          <span class="perm-accordion-icon">▶️</span>
          <span>🔌 ${esc(pn)}</span>
        </div>
        <label class="perm-field" onclick="event.stopPropagation()">
          <input type="checkbox" class="perm-enabled" ${top.enabled===false?'':'checked'}>
          <span>默认启用</span>
        </label>
      </div>
      <div class="perm-accordion-content">
        <div class="perm-accordion-body">
          <div class="perm-plugin-inline-config">
            <label class="perm-field">
              <span>👤 默认权限等级</span>
              <select class="perm-level">${optLevel(String(top.level||'all'))}</select>
            </label>
            <label class="perm-field">
              <span>💬 默认使用场景</span>
              <select class="perm-scene">${optScene(String(top.scene||'all'))}</select>
            </label>
          </div>
          <div class="perm-lists-section">
            <div class="perm-list-group">
              <label class="perm-list-label">🤍 白名单用户</label>
              <input type="text" class="perm-list-input perm-wl-users" placeholder="用户ID，多个用逗号分隔" value="${esc(toCSV(wl.users))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">🤍 白名单群组</label>
              <input type="text" class="perm-list-input perm-wl-groups" placeholder="群号，多个用逗号分隔" value="${esc(toCSV(wl.groups))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">🖤 黑名单用户</label>
              <input type="text" class="perm-list-input perm-bl-users" placeholder="用户ID，多个用逗号分隔" value="${esc(toCSV(bl.users))}">
            </div>
            <div class="perm-list-group">
              <label class="perm-list-label">🖤 黑名单群组</label>
              <input type="text" class="perm-list-input perm-bl-groups" placeholder="群号，多个用逗号分隔" value="${esc(toCSV(bl.groups))}">
            </div>
          </div>
          ${Object.keys(cmds||{}).length ? `
            <div class="perm-commands-section">
              <div class="perm-commands-title">📋 命令权限配置 (${Object.keys(cmds||{}).length}条命令)</div>
              <div class="perm-commands-list">${cmdRows}</div>
            </div>
          ` : '<div class="empty-state" style="padding: 40px 20px;">💤 该插件暂无命令</div>'}
        </div>
      </div>
    </div>`;
  });

  const pluginsHTML = rows.join('') || '<div class="empty-state">暂无子插件</div>';
  wrap.innerHTML = globalHTML + pluginsHTML;

  // 折叠面板交互（仅插件块）
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
  // 全局
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
  // 子插件
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
    showToast(`✅ 检查完成！提醒 ${r.reminded} 个群，退出 ${r.left} 个群`,'success');
  } catch(e){
    showToast('❌ 执行失败: '+(e&&e.message?e.message:e),'error');
  } finally{
    showLoading(false);
  }
};

// 添加键盘快捷键支持
document.addEventListener('keydown', (e) => {
  // Ctrl/Cmd + K: 搜索
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const searchInput = document.querySelector('#group-search');
    if (searchInput) {
      searchInput.focus();
      searchInput.select();
    }
  }
  
  // Ctrl/Cmd + R: 刷新
  if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
    e.preventDefault();
    const refreshBtn = document.querySelector('#refresh-btn');
    if (refreshBtn) {
      refreshBtn.click();
    }
  }
  
  // Ctrl/Cmd + D: 切换主题
  if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
    e.preventDefault();
    const themeBtn = document.querySelector('#theme-toggle');
    if (themeBtn) {
      themeBtn.click();
    }
  }
  
  // ESC: 关闭模态框
  if (e.key === 'Escape') {
    const modal = document.querySelector('.modal:not(.hidden)');
    if (modal) {
      closePermJsonModal();
    }
  }
});

// 控制台欢迎信息
console.log('%c🌸 今汐管理控制台', 'font-size: 24px; color: #667eea; font-weight: bold;');
console.log('%c✨ 欢迎使用现代化管理界面', 'font-size: 14px; color: #6366f1;');
console.log('%c快捷键提示:\n  Ctrl+K: 搜索\n  Ctrl+R: 刷新\n  Ctrl+D: 切换主题\n  ESC: 关闭弹窗', 'font-size: 12px; color: #94a3b8; line-height: 1.8;');
