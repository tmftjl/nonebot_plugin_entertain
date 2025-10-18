// ==================== 今汐控制台前端（UTF-8） ====================

// 全局状态
const state = {
  groups: [],
  stats: null,
  permissions: null,
  config: null,
  schemas: null,
  pluginNames: {},
  commandNames: {},  // 命令中文名: {plugin: {command: displayName}}
  theme: localStorage.getItem('theme') || 'light',
  sortBy: 'days', sortDir: 'asc', filter: 'all', keyword: '',
  statsSort: 'total_desc', // total_desc | total_asc | bot_asc | bot_desc | group_desc | private_desc
  statsKeyword: '',
  // 分页状态
  pagination: {
    currentPage: 1,
    pageSize: 20,
    totalItems: 0,
    totalPages: 0
  }
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
// 即将到期阈值：默认 7 天；从系统配置动态读取覆盖
let SOON_THRESHOLD_DAYS = 7;
function getStatusLabel(days){ if(days<0) return '<span class="status-badge status-expired">已到期</span>'; if(days===0) return '<span class="status-badge status-today">今日到期</span>'; if(days<=SOON_THRESHOLD_DAYS) return '<span class="status-badge status-soon">即将到期</span>'; return '<span class="status-badge status-active">有效</span>'; }
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
  const headers = {'Content-Type':'application/json', ...(options.headers||{})};
  const resp = await fetch(`/member_renewal${path}`, { ...options, headers });
  if(!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
  const ct = resp.headers.get('content-type')||'';
  return ct.includes('application/json') ? resp.json() : resp.text();
}

// 主题切换在下方已增强版本实现，此处移除重复定义

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
      .map(([gid,info])=>{ const d=daysRemaining(info.expiry); let s='active'; if(d<0)s='expired'; else if(d===0)s='today'; else if(d<=SOON_THRESHOLD_DAYS)s='soon'; return { gid, ...info, days:d, status:s };});
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
      .map(([gid,info])=>{ const d=daysRemaining(info.expiry); let s='active'; if(d<0)s='expired'; else if(d===0)s='today'; else if(d<=SOON_THRESHOLD_DAYS)s='soon'; return { gid, ...info, days:d, status:s };});
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

  // 分页计算
  state.pagination.totalItems = list.length;
  state.pagination.totalPages = Math.ceil(list.length / state.pagination.pageSize) || 1;

  // 确保当前页在有效范围内
  if (state.pagination.currentPage > state.pagination.totalPages) {
    state.pagination.currentPage = state.pagination.totalPages;
  }
  if (state.pagination.currentPage < 1) {
    state.pagination.currentPage = 1;
  }

  // 获取当前页的数据
  const startIndex = (state.pagination.currentPage - 1) * state.pagination.pageSize;
  const endIndex = startIndex + state.pagination.pageSize;
  const pageList = list.slice(startIndex, endIndex);

  tbody.innerHTML = pageList.length? pageList.map(g=>`
    <tr>
      <td><input type="checkbox" class="group-checkbox" data-gid="${g.gid}"></td>
      <td>${g.gid}</td>
      <td>${getStatusLabel(g.days)}</td>
      <td>${formatDate(g.expiry)}</td>
      <td>${g.days}</td>
      <td>
        <button class="btn-action btn-remind" data-gid="${g.gid}">提醒</button>
        <button class="btn-action btn-extend" data-gid="${g.gid}">+30天</button>
        <button class="btn-action btn-leave" data-gid="${g.gid}">退群</button>
      </td>
    </tr>`).join('') : '<tr><td colspan="6" class="text-center">暂无数据</td></tr>';

  // 更新分页控件
  updatePaginationControls();
}

function renderCodes(codes){
  const el=$('#codes-list'); if(!el) return;
  const arr=Object.entries(codes||{});
  el.innerHTML = arr.length? arr.map(([code,meta])=>`<div class="code-card"><div class="code-info"><div class="code-value">${maskCode(code)}</div><div class="code-meta">${meta.length}${meta.unit} · 可用${meta.max_use||1}次</div></div><button class="btn-copy" data-code="${code}">复制</button></div>`).join('') : '<div class="empty-state">暂无可用续费码</div>';
}

// 更新分页控件
function updatePaginationControls() {
  const { currentPage, totalPages, totalItems, pageSize } = state.pagination;

  // 更新信息文本
  const infoText = $('#pagination-info-text');
  if (infoText) {
    const start = (currentPage - 1) * pageSize + 1;
    const end = Math.min(currentPage * pageSize, totalItems);
    infoText.textContent = totalItems > 0
      ? `共 ${totalItems} 条记录，显示 ${start}-${end}`
      : '共 0 条记录';
  }

  // 更新按钮状态
  const firstBtn = $('#pagination-first');
  const prevBtn = $('#pagination-prev');
  const nextBtn = $('#pagination-next');
  const lastBtn = $('#pagination-last');

  if (firstBtn) firstBtn.disabled = currentPage <= 1;
  if (prevBtn) prevBtn.disabled = currentPage <= 1;
  if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
  if (lastBtn) lastBtn.disabled = currentPage >= totalPages;

  // 更新页码显示
  const pagesContainer = $('#pagination-pages');
  if (pagesContainer) {
    const pages = [];
    const maxVisible = 5; // 最多显示5个页码按钮

    if (totalPages <= maxVisible) {
      // 总页数少，显示所有页码
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      // 总页数多，智能显示页码
      if (currentPage <= 3) {
        pages.push(1, 2, 3, 4, '...', totalPages);
      } else if (currentPage >= totalPages - 2) {
        pages.push(1, '...', totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
      } else {
        pages.push(1, '...', currentPage - 1, currentPage, currentPage + 1, '...', totalPages);
      }
    }

    pagesContainer.innerHTML = pages.map(page => {
      if (page === '...') {
        return '<span class="pagination-ellipsis">...</span>';
      }
      const active = page === currentPage ? 'active' : '';
      return `<button class="pagination-page ${active}" data-page="${page}">${page}</button>`;
    }).join('');
  }
}

// 分页跳转函数
function goToPage(page) {
  const { totalPages } = state.pagination;
  if (page < 1) page = 1;
  if (page > totalPages) page = totalPages;
  state.pagination.currentPage = page;
  renderGroupsTable();
}

function changePageSize(size) {
  state.pagination.pageSize = parseInt(size) || 20;
  state.pagination.currentPage = 1; // 重置到第一页
  renderGroupsTable();
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
    const bots=today.bots||{}; let total=0, gsum=0, psum=0, gcount=0, pcount=0;
    Object.values(bots).forEach(s=>{
      if(!s) return;
      total+=s.total_sent||0;
      const gTargets = s.group?.targets || {};
      const pTargets = s.private?.targets || {};
      gsum+=(s.group?.count)||0;
      psum+=(s.private?.count)||0;
      gcount += Object.keys(gTargets).length;
      pcount += Object.keys(pTargets).length;
    });
    (document.getElementById('stats-today-total')).textContent = String(total);
    (document.getElementById('stats-group-total')).textContent = String(gsum);
    (document.getElementById('stats-private-total')).textContent = String(psum);
    (document.getElementById('stats-group-count')).textContent = String(gcount);
    (document.getElementById('stats-private-count')).textContent = String(pcount);
  } catch{}
}

function renderStatsDetails(today){
  try{
    const bots = today?.bots || {};
    const container = document.getElementById('stats-bots-accordion');
    if(!container) return;

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

    if(!rows.length) {
      container.innerHTML = '<div class="empty-state">📭 暂无数据</div>';
      return;
    }

    // 渲染手风琴式Bot列表
    const formatTargets = (targets) => {
      const entries = Object.entries(targets||{});
      if(!entries.length) return '<div class="empty-state-mini">暂无数据</div>';

      // 按消息数量排序
      entries.sort((a, b) => b[1] - a[1]);

      // 如果数量太多，只显示前10个，其他的折叠
      const showLimit = 10;
      const mainEntries = entries.slice(0, showLimit);
      const moreEntries = entries.slice(showLimit);

      let html = mainEntries.map(([id, count])=>
        `<div class="stats-target-item"><span class="id">${id}</span><span class="count">${count}</span></div>`
      ).join('');

      if(moreEntries.length > 0) {
        const moreCount = moreEntries.reduce((sum, [, count]) => sum + count, 0);
        html += `<div class="stats-target-more">... 还有 ${moreEntries.length} 个对象 (共 ${moreCount} 条消息)</div>`;
      }

      return html;
    };

    const html = rows.map((bot, index)=>`
      <div class="stats-bot-item">
        <div class="stats-bot-header" data-index="${index}">
          <div class="stats-bot-title">
            <span class="stats-bot-icon">▶️</span>
            <span>🤖 Bot ${bot.id}</span>
          </div>
          <div class="stats-bot-summary">
            <span>总计: <strong>${bot.total}</strong></span>
            <span>群聊: <strong>${bot.gCount}</strong> (${Object.keys(bot.gT).length}个群)</span>
            <span>私聊: <strong>${bot.pCount}</strong> (${Object.keys(bot.pT).length}人)</span>
          </div>
        </div>
        <div class="stats-bot-content">
          <div class="stats-bot-body">
            <div class="stats-targets-grid">
              <div class="stats-target-section">
                <div class="stats-target-title">👥 群聊消息详情 (共${Object.keys(bot.gT).length}个群)</div>
                <div class="stats-target-list">
                  ${formatTargets(bot.gT)}
                </div>
              </div>
              <div class="stats-target-section">
                <div class="stats-target-title">💬 私聊消息详情 (共${Object.keys(bot.pT).length}人)</div>
                <div class="stats-target-list">
                  ${formatTargets(bot.pT)}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `).join('');

    container.innerHTML = html;

    // 绑定手风琴点击事件
    container.querySelectorAll('.stats-bot-header').forEach(header => {
      header.addEventListener('click', function() {
        const item = this.closest('.stats-bot-item');
        const content = item.querySelector('.stats-bot-content');
        const isActive = this.classList.contains('active');

        // 关闭其他项
        container.querySelectorAll('.stats-bot-header').forEach(h => {
          h.classList.remove('active');
          const c = h.closest('.stats-bot-item').querySelector('.stats-bot-content');
          c.classList.remove('active');
        });

        // 切换当前项
        if (!isActive) {
          this.classList.add('active');
          content.classList.add('active');
        }
      });
    });
  } catch(err){
    console.error('renderStatsDetails error:', err);
  }
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
            <label class="perm-list-label">✅ 白名单用户</label>
            <input type="text" class="perm-list-input perm-wl-users" placeholder="用户ID，多个用逗号分隔" value="${esc(toCSV(gWl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">✅ 白名单群组</label>
            <input type="text" class="perm-list-input perm-wl-groups" placeholder="群号，多个用逗号分隔" value="${esc(toCSV(gWl.groups))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">⛔ 黑名单用户</label>
            <input type="text" class="perm-list-input perm-bl-users" placeholder="用户ID，多个用逗号分隔" value="${esc(toCSV(gBl.users))}">
          </div>
          <div class="perm-list-group">
            <label class="perm-list-label">⛔ 黑名单群组</label>
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
      // 获取命令的中文名
      const cmdDisplay = (state.commandNames && state.commandNames[pn] && state.commandNames[pn][cn]) || cn;
      return `<div class="perm-command-item" data-command="${esc(cn)}">
        <div class="perm-command-header">
          <div class="perm-command-name">📌 ${esc(cmdDisplay)}</div>
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
    
    const display = state.pluginNames[pn] || pn;
    return `<div class="perm-accordion-item" data-plugin="${esc(pn)}">
      <div class="perm-accordion-header" data-index="${index}">
        <div class="perm-accordion-title">
          <span class="perm-accordion-icon">▶️</span>
          <span>🔌 ${esc(display)}</span>
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
  
  // 绑定手风琴点击事件（动态高度，避免内容过长被裁切）
  wrap.querySelectorAll('.perm-accordion-header').forEach(header => {
    header.addEventListener('click', function() {
      const item = this.closest('.perm-accordion-item');
      const content = item.querySelector('.perm-accordion-content');
      const isActive = this.classList.contains('active');

      // 关闭所有其他项并重置高度
      wrap.querySelectorAll('.perm-accordion-header').forEach(h => {
        h.classList.remove('active');
        const c = h.closest('.perm-accordion-item').querySelector('.perm-accordion-content');
        c.classList.remove('active');
        c.style.maxHeight = '0px';
      });

      // 打开当前项并根据内容计算高度
      if (!isActive) {
        this.classList.add('active');
        content.classList.add('active');
        // 先清空再读取 scrollHeight 以触发正确计算
        content.style.maxHeight = 'none';
        const target = content.scrollHeight;
        content.style.maxHeight = target + 'px';
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
    const [p, commands, plugins]=await Promise.all([
      apiCall('/permissions'),
      apiCall('/commands').catch(()=>({})),
      apiCall('/plugins').catch(()=>({}))
    ]);
    state.permissions=p;
    state.commandNames=commands||{};
    state.pluginNames=plugins||{};
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
// 配置管理相关
let currentActiveConfigTab = null;

// 配置项中文描述映射
const CONFIG_DESCRIPTIONS = {
  // 通用配置描述
  'enabled': '是否启用此配置项',
  'enable': '是否启用此功能',
  'debug': '是否开启调试模式',
  'log_level': '日志输出级别',
  'max_retry': '最大重试次数',
  'timeout': '超时时间（秒）',
  'interval': '执行间隔（秒）',
  'port': '服务端口号',
  'host': '服务主机地址',
  'api_key': 'API密钥',
  'secret_key': '密钥',
  'token': '访问令牌',
  'url': '接口地址',
  'path': '文件路径',
  'prefix': '命令前缀',
  'suffix': '命令后缀',
  'max_length': '最大长度',
  'min_length': '最小长度',
  'cache_time': '缓存时间（秒）',
  'rate_limit': '速率限制（次/秒）',

  // 根据实际配置添加更多描述
  'whitelist': '白名单列表',
  'blacklist': '黑名单列表',
  'admin_list': '管理员列表',
  'superusers': '超级用户列表',
};

// 获取配置项的中文描述
function getConfigDescription(key) {
  // 先查找精确匹配
  if (CONFIG_DESCRIPTIONS[key]) {
    return CONFIG_DESCRIPTIONS[key];
  }

  // 尝试模糊匹配
  const lowerKey = key.toLowerCase();
  for (const [k, v] of Object.entries(CONFIG_DESCRIPTIONS)) {
    if (lowerKey.includes(k)) {
      return v;
    }
  }

  // 如果没有描述，返回格式化的key
  return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

async function loadConfig(){
  try{
    showLoading(true);
    const [schemas, c] = await Promise.all([
      apiCall('/config_schema').catch(()=>({})),
      apiCall('/config').catch(()=>({})),
    ]);
    state.schemas = schemas || {};
    state.config = c || {};
    renderConfigTabs();
  } catch(e){
    showToast('加载配置失败: '+(e&&e.message?e.message:e),'error');
  } finally{
    showLoading(false);
  }
}

// 渲染标签页导航和内容
function renderConfigTabs() {
  const navContainer = $('#config-tabs-nav');
  const contentContainer = $('#config-tabs-content');

  if (!navContainer || !contentContainer) return;

  const configs = state.config || {};
  const configKeys = Object.keys(configs).sort((a, b) => a.localeCompare(b));

  if (configKeys.length === 0) {
    navContainer.innerHTML = '<div class="empty-state">暂无配置项</div>';
    contentContainer.innerHTML = '<div class="empty-state">暂无配置数据</div>';
    return;
  }

  // 渲染主标签导航
  const tabsHtml = configKeys.map(key => {
    // 优先使用 schema 的 title，最后用 key
    const schema = (state.schemas && state.schemas[key]) || {};
    const label = schema.title || key;
    return `
      <div class="config-tab-item" data-config-key="${escapeHtml(key)}">
        ${escapeHtml(label)}
      </div>
    `;
  }).join('');
  navContainer.innerHTML = tabsHtml;

  // 渲染所有标签页内容
  const contentsHtml = configKeys.map(key => {
    const configData = configs[key];
    const subKeys = getConfigSubKeys(configData, key);
    // 为渲染此插件的表单临时设置 Schema 上下文
    const __prevSchemaCtx = (typeof schemaContextPlugin !== 'undefined') ? schemaContextPlugin : null;
    window.schemaContextPlugin = key;

    // 如果有多个子配置项，使用二级标签页
    if (subKeys.length > 1) {
      const subTabsHtml = subKeys.map(subKey => {
        const props = (state.schemas && state.schemas[key] && state.schemas[key].properties) || {};
        const title = (props && props[subKey] && props[subKey].title) ? props[subKey].title : subKey;
        return `
          <div class="config-sub-tab-item" data-sub-key="${escapeHtml(subKey)}">
            ${escapeHtml(title)}
          </div>`;
      }).join('');

      const subContentsHtml = subKeys.map(subKey => {
        const subData = getSubConfigData(configData, subKey, key);
        return `
          <div class="config-sub-content" data-sub-key="${escapeHtml(subKey)}">
            <div class="config-items-column">
              ${renderConfigForm(subData, `${key}.${subKey}`)}
            </div>
          </div>
        `;
      }).join('');

      const __section = `
        <div class="config-content-section" data-config-key="${escapeHtml(key)}">
          <div class="config-sub-tabs-nav">${subTabsHtml}</div>
          <div class="config-sub-tabs-content">${subContentsHtml}</div>
        </div>
      `;
      window.schemaContextPlugin = __prevSchemaCtx;
      return __section;
    } else {
      // 单个配置项，直接展示
      const __section = `
        <div class="config-content-section" data-config-key="${escapeHtml(key)}">
          <div class="config-items-column">
            ${renderConfigForm(configData, key)}
          </div>
        </div>
      `;
      window.schemaContextPlugin = __prevSchemaCtx;
      return __section;
    }
  }).join('');
  contentContainer.innerHTML = contentsHtml;

  // 绑定主标签点击事件
  navContainer.querySelectorAll('.config-tab-item').forEach(tab => {
    tab.addEventListener('click', () => {
      const key = tab.getAttribute('data-config-key');
      switchConfigTab(key);
    });
  });

  // 绑定子标签点击事件
  contentContainer.querySelectorAll('.config-sub-tabs-nav').forEach(subNav => {
    subNav.querySelectorAll('.config-sub-tab-item').forEach(subTab => {
      subTab.addEventListener('click', () => {
        const subKey = subTab.getAttribute('data-sub-key');
        const section = subTab.closest('.config-content-section');
        switchConfigSubTab(section, subKey);
      });
    });
  });

  // 默认激活第一个标签
  if (configKeys.length > 0) {
    switchConfigTab(configKeys[0]);
  }
}

// 获取配置的子键
function getConfigSubKeys(data, parentKey) {
  if (typeof data !== 'object' || data === null) return [parentKey];
  if (Array.isArray(data)) return [parentKey];

  const keys = Object.keys(data);
  // 如果对象的值都是对象类型（嵌套配置），则作为子标签
  const allObjectValues = keys.every(k => typeof data[k] === 'object' && data[k] !== null && !Array.isArray(data[k]));

  // Don't create sub-tabs, always render as nested sections within a single view
  // This allows the nested section CSS styling to work properly
  return [parentKey];
}

// 获取子配置数据
function getSubConfigData(data, subKey, parentKey) {
  if (subKey === parentKey) return data;
  return data[subKey] || {};
}

// 切换子标签页
function switchConfigSubTab(section, subKey) {
  // 更新子标签激活状态
  section.querySelectorAll('.config-sub-tab-item').forEach(tab => {
    tab.classList.toggle('active', tab.getAttribute('data-sub-key') === subKey);
  });

  // 更新子内容显示
  section.querySelectorAll('.config-sub-content').forEach(content => {
    content.classList.toggle('active', content.getAttribute('data-sub-key') === subKey);
  });
}

// 切换标签页
function switchConfigTab(configKey) {
  currentActiveConfigTab = configKey;

  // 更新标签激活状态
  $$('.config-tab-item').forEach(tab => {
    tab.classList.toggle('active', tab.getAttribute('data-config-key') === configKey);
  });

  // 更新内容显示
  $$('.config-content-section').forEach(section => {
    const isActive = section.getAttribute('data-config-key') === configKey;
    section.classList.toggle('active', isActive);

    // 如果有子标签页，激活第一个
    if (isActive) {
      const firstSubTab = section.querySelector('.config-sub-tab-item');
      if (firstSubTab) {
        const firstSubKey = firstSubTab.getAttribute('data-sub-key');
        switchConfigSubTab(section, firstSubKey);
      }
    }
  });
}

function renderConfigForm(data, parentKey = '') {
  if (typeof data !== 'object' || data === null) {
    return renderConfigField(parentKey, data);
  }

  let html = '';

  if (Array.isArray(data)) {
    html += `<div class="config-section">`;
    html += `<div class="config-section-header">
      <span class="config-section-icon">📋</span>
      <span class="config-section-title">列表配置</span>
    </div>`;

    data.forEach((item, index) => {
      if (typeof item === 'object' && item !== null) {
        html += `<div class="config-array-item">
          <div class="config-array-header">
            <span class="config-array-label">项目 ${index + 1}</span>
          </div>
          <div class="config-array-body">
            ${renderConfigForm(item, `${parentKey}[${index}]`)}
          </div>
        </div>`;
      } else {
        html += renderConfigField(`${parentKey}[${index}]`, item, `项目 ${index + 1}`);
      }
    });
    html += `</div>`;
  } else {
    // 对象类型
    const entries = Object.entries(data);
    entries.forEach(([key, value]) => {
      const fullKey = parentKey ? `${parentKey}.${key}` : key;

      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        // 嵌套对象，创建折叠区域
        html += `<div class="config-nested-section">
          <div class="config-nested-header">
            <span class="config-nested-icon">📁</span>
            <span class="config-nested-title">${escapeHtml(__schemaGetTitle(fullKey, key))}</span>
            <span class="config-nested-desc">${__schemaGetDescription(fullKey)}</span>
          </div>
          <div class="config-nested-body">
            ${renderConfigForm(value, fullKey)}
          </div>
        </div>`;
      } else {
        html += renderConfigField(fullKey, value, key);
      }
    });
  }

  return html;
}

// --- Schema helpers for Chinese titles/descriptions ---
function __schemaGetNode(fullKey){
  try{
    const plugin = (typeof schemaContextPlugin !== 'undefined' && schemaContextPlugin) ? schemaContextPlugin : currentActiveConfigTab;
    const root = (state.schemas && state.schemas[plugin]) || null;
    if(!root) return null;
    let rel = String(fullKey||'');
    if(rel.startsWith(plugin + '.')) rel = rel.slice(plugin.length + 1);
    rel = rel.replace(/\[[0-9]+\]/g,'');
    if(!rel) return root;
    const parts = rel.split('.').filter(Boolean);
    let node = root;
    for(const p of parts){
      const props = (node && node.properties) || {};
      if(!props || !props[p]) return null;
      node = props[p];
    }
    return node || null;
  }catch{ return null; }
}

function __schemaGetTitle(fullKey, fallback){
  const n = __schemaGetNode(fullKey);
  return (n && n.title) ? n.title : (fallback || fullKey);
}

function __schemaGetDescription(fullKey){
  const n = __schemaGetNode(fullKey);
  if(n && n.description) return n.description;
  return '';
}

function renderConfigField(fullKey, value, displayKey = null) {
  const last = (displayKey || fullKey.split('.').pop().split('[')[0]);
  const key = __schemaGetTitle(fullKey, last);
  const description = __schemaGetDescription(fullKey) || getConfigDescription(last);
  const escapedKey = escapeHtml(fullKey);
  const type = typeof value;

  let inputHtml = '';

  if (type === 'boolean') {
    // 使用美观的开关
    inputHtml = `
      <label class="config-switch">
        <input type="checkbox" data-config-key="${escapedKey}" ${value ? 'checked' : ''}>
        <span class="config-switch-slider"></span>
        <span class="config-switch-label">${value ? '已启用' : '已禁用'}</span>
      </label>
    `;
  } else if (type === 'number') {
    inputHtml = `
      <input type="number"
             class="config-input"
             data-config-key="${escapedKey}"
             value="${value}"
             placeholder="请输入数字">
    `;
  } else if (Array.isArray(value)) {
    inputHtml = `
      <input type="text"
             class="config-input"
             data-config-key="${escapedKey}"
             value="${escapeHtml(value.join(', '))}"
             placeholder="多个值用逗号分隔">
      <div class="config-field-hint">多个值请用逗号分隔</div>
    `;
  } else {
    // 字符串类型
    const valueStr = String(value || '');
    if (valueStr.length > 50) {
      inputHtml = `
        <textarea class="config-textarea"
                  data-config-key="${escapedKey}"
                  rows="3"
                  placeholder="请输入${description}">${escapeHtml(valueStr)}</textarea>
      `;
    } else {
      inputHtml = `
        <input type="text"
               class="config-input"
               data-config-key="${escapedKey}"
               value="${escapeHtml(valueStr)}"
               placeholder="请输入${description}">
      `;
    }
  }

  return `
    <div class="config-field-row">
      <div class="config-field-label">
        <span class="config-field-name">${escapeHtml(key)}</span>
        <span class="config-field-desc">${description}</span>
      </div>
      <div class="config-field-input">
        ${inputHtml}
      </div>
    </div>
  `;
}

// 保存当前标签页的配置
async function saveCurrentConfig() {
  if (!currentActiveConfigTab) {
    showToast('请选择要保存的配置项', 'warning');
    return;
  }

  try {
    showLoading(true);

    // 查找当前激活标签页的内容区域
    const section = document.querySelector(`.config-content-section[data-config-key="${currentActiveConfigTab}"]`);
    if (!section) return;

    const inputs = section.querySelectorAll('[data-config-key]');
    const updatedConfig = JSON.parse(JSON.stringify(state.config[currentActiveConfigTab]));

    inputs.forEach(input => {
      const fullKey = input.getAttribute('data-config-key');

      // 移除插件名前缀,得到相对路径
      let relativePath = fullKey;
      const prefix = `${currentActiveConfigTab}.`;
      if (relativePath.startsWith(prefix)) {
        relativePath = relativePath.slice(prefix.length);
      }

      const path = relativePath.split(/[.\[\]]+/).filter(Boolean);

      let value;
      if (input.type === 'checkbox') {
        value = input.checked;
      } else if (input.type === 'number') {
        value = parseFloat(input.value) || 0;
      } else {
        value = input.value;
        // 尝试解析为数组
        if (value.includes(',')) {
          const arr = value.split(',').map(s => s.trim()).filter(Boolean);
          if (arr.length > 0) value = arr;
        }
      }

      // 设置嵌套值
      setNestedValue(updatedConfig, path.join('.'), value);
    });

    // 更新配置
    const newConfig = {...state.config};
    newConfig[currentActiveConfigTab] = updatedConfig;

    // 保存到服务器
    await apiCall('/config', {method: 'PUT', body: JSON.stringify(newConfig)});

    state.config = newConfig;
    showToast(`配置 "${currentActiveConfigTab}" 已保存并重新加载`, 'success');

    await loadConfig();
    // 重新切换到当前标签
    setTimeout(() => switchConfigTab(currentActiveConfigTab), 100);
  } catch(e) {
    showToast('保存失败: ' + (e && e.message ? e.message : e), 'error');
  } finally {
    showLoading(false);
  }
}

function setNestedValue(obj, path, value) {
  const keys = path.split('.');
  let current = obj;

  for(let i = 0; i < keys.length - 1; i++) {
    const key = keys[i];
    if(!(key in current)) {
      current[key] = {};
    }
    current = current[key];
  }

  current[keys[keys.length - 1]] = value;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

async function remindGroups(groupIds, content=''){ if(!Array.isArray(groupIds)||!groupIds.length) return; for(const gid of groupIds){ const payload = { group_id: gid }; if(content) payload.content = content; await apiCall('/remind_multi',{method:'POST', body: JSON.stringify(payload)}); } }
async function leaveGroups(groupIds){ if(!Array.isArray(groupIds)||!groupIds.length) return; for(const gid of groupIds){ await apiCall('/leave_multi',{method:'POST', body: JSON.stringify({ group_id: gid })}); } }

function selectedGroupIds(){ return $$('.group-checkbox').filter(cb=>cb.checked).map(cb=> parseInt(cb.dataset.gid)); }
function selectedRecordIds(){
  const list = [];
  const sel = $$('.group-checkbox').filter(cb=>cb.checked);
  for(const cb of sel){
    const gid = cb && cb.dataset && cb.dataset.gid ? cb.dataset.gid : '';
    const g = (state.groups||[]).find(x=> String(x.gid)===String(gid));
    if(g && typeof g.id !== 'undefined') list.push(parseInt(g.id));
  }
  return list;
}

function openModal(id){ const m = document.getElementById(id); if(m) m.classList.remove('hidden'); }
function closeModal(id){ const m = document.getElementById(id); if(m) m.classList.add('hidden'); }

function openNotifyModal(){
  const ids = selectedGroupIds();
  if(!ids.length){ showToast('请先勾选要通知的群','warning'); return; }
  $('#notify-selected-count').textContent = String(ids.length);
  $('#notify-text').value = '';
  const file = $('#notify-images'); if(file) file.value = '';
  const pre = $('#notify-image-previews'); if(pre) pre.innerHTML = '';
  openModal('notify-modal');
}

async function filesToBase64List(fileInput){
  const files = (fileInput && fileInput.files) ? Array.from(fileInput.files) : [];
  const results = [];
  for(const f of files){
    const dataUrl = await new Promise(resolve => { const r = new FileReader(); r.onload = ()=>resolve(r.result||''); r.readAsDataURL(f); });
    results.push(String(dataUrl||''));
  }
  return results;
}

async function sendNotify(){
  const ids = selectedGroupIds();
  if(!ids.length){ showToast('未选择任何群','warning'); return; }
  const text = ($('#notify-text')?.value||'').trim();
  const imgs = await filesToBase64List($('#notify-images'));
  if(!text && (!imgs || !imgs.length)){ showToast('请填写文本或选择图片','warning'); return; }

  // 立即关闭弹窗,防止重复点击
  closeModal('notify-modal');

  try{
    showLoading(true);
    await apiCall('/notify', { method:'POST', body: JSON.stringify({ group_ids: ids, text, images: imgs }) });
    showToast(`已向 ${ids.length} 个群发送通知`,'success');
  }catch(e){
    showToast('发送失败: '+(e&&e.message?e.message:e),'error');
  }finally{
    showLoading(false);
  }
}

// 读取系统配置中的“临近到期阈值(天)”配置
async function loadSoonThreshold(){
  try{
    const cfg = await apiCall('/config');
    // system 区域内读取 member_renewal_soon_threshold_days
    const sys = (cfg && cfg.system) ? cfg.system : cfg; // 兼容仅返回 system 的情况
    const v = sys && (sys.member_renewal_soon_threshold_days ?? sys['member_renewal_soon_threshold_days']);
    if(typeof v === 'number' && isFinite(v) && v >= 0){
      SOON_THRESHOLD_DAYS = v;
    }
  }catch{
    // 失败保留默认 7 天
    SOON_THRESHOLD_DAYS = 7;
  }
}

async function openManualExtendModal(){
  const checkboxes = $$('.group-checkbox:checked');
  const idEl = $('#extend-group-id');
  const expiryEl = $('#extend-expiry-date');
  const curEl = $('#extend-current-info');
  const botInput = $('#extend-bot-id');
  const remarkInput = $('#extend-remark');
  const renewerInput = $('#extend-renewer');
  const titleEl = $('#extend-modal-title');
  const lengthEl = $('#extend-length');

  // 只允许选择一个群
  if(checkboxes.length > 1){
    showToast('只能选择一个群进行操作,请重新选择','warning');
    $$('.group-checkbox').forEach(cb => cb.checked = false);
    return;
  }

  if(checkboxes.length === 1){
    // 编辑模式 - 选中了一个群,填充所有信息
    const gid = checkboxes[0].dataset.gid;
    const g = (state.groups||[]).find(x=> String(x.gid)===String(gid));

    if(g){
      titleEl.textContent = '修改群信息';

      // 填充所有字段
      idEl.value = String(g.gid);

      // 转换到期时间为datetime-local格式
      if(g.expiry){
        try{
          const d = new Date(g.expiry);
          const year = d.getFullYear();
          const month = String(d.getMonth() + 1).padStart(2, '0');
          const day = String(d.getDate()).padStart(2, '0');
          const hour = String(d.getHours()).padStart(2, '0');
          const minute = String(d.getMinutes()).padStart(2, '0');
          expiryEl.value = `${year}-${month}-${day}T${hour}:${minute}`;
        }catch{
          expiryEl.value = '';
        }
      } else {
        expiryEl.value = '';
      }

      if(botInput && g.managed_by_bot){
        botInput.value = String(g.managed_by_bot);
      } else if(botInput) {
        botInput.value = '';
      }

      if(remarkInput && g.remark){
        remarkInput.value = String(g.remark);
      } else if(remarkInput) {
        remarkInput.value = '';
      }

      if(renewerInput && g.last_renewed_by){
        renewerInput.value = String(g.last_renewed_by);
      } else if(renewerInput) {
        // 尝试恢复上次保存的续费人
        try{
          const last = localStorage.getItem("extend_renewer")||"";
          if(last) renewerInput.value = last;
          else renewerInput.value = '';
        }catch{
          renewerInput.value = '';
        }
      }

      // 续费时长默认为0(修改模式)
      lengthEl.value = "0";

      if(g.expiry){
        curEl.textContent = `当前到期时间：${formatDate(g.expiry)} (剩余 ${g.days} 天)`;
        curEl.style.display = 'block';
      } else {
        curEl.textContent = '该群尚未设置到期时间';
        curEl.style.display = 'block';
      }
    }
  } else {
    // 新增模式
    titleEl.textContent = '新增群';

    idEl.value = "";
    expiryEl.value = "";

    if(botInput) botInput.value = "";
    if(remarkInput) remarkInput.value = "";

    // 新增模式默认30天
    lengthEl.value = "30";

    if(renewerInput){
      // 尝试恢复上次保存的续费人
      try{
        const last = localStorage.getItem("extend_renewer")||"";
        if(last) renewerInput.value = last;
      }catch{}
    }
    curEl.style.display = 'none';
  }

  // 重置单位
  $("#extend-unit").value = "天";

  openModal("extend-modal");
}

async function submitManualExtend(){
  const checkboxes = $$('.group-checkbox:checked');
  const inputId = ($('#extend-group-id')?.value||'').trim();
  const expiryDate = ($('#extend-expiry-date')?.value||'').trim();
  const length = parseInt(($('#extend-length')?.value||'0').trim()) || 0;
  const unit = ($('#extend-unit')?.value||'天');
  const managed_by_bot = ($('#extend-bot-id')?.value||'').trim();
  const renewed_by = ($('#extend-renewer')?.value||'').trim();
  const remark = ($('#extend-remark')?.value||'').trim();

  if(!inputId){
    showToast('请输入群号','warning');
    return;
  }

  const gid = parseInt(inputId);
  if(!gid){
    showToast('群号无效','warning');
    return;
  }

  const isEdit = checkboxes.length === 1;

  // 新增模式：群号、到期时间/续费时长、管理Bot、续费人都是必填
  if(!isEdit){
    if(!length && !expiryDate){
      showToast('新增群时必须填写到期时间或续费时长','warning');
      return;
    }
    if(!managed_by_bot){
      showToast('管理Bot为必填项','warning');
      return;
    }
    if(!renewed_by){
      showToast('续费人为必填项','warning');
      return;
    }
  }

  // 立即关闭弹窗,防止重复点击
  closeModal('extend-modal');

  try{
    showLoading(true);

    // 判断是编辑还是新增
    const isEdit = checkboxes.length === 1;
    const existingGroup = (state.groups||[]).find(x=> String(x.gid)===String(gid));

    const body = {};

    // 编辑模式: 使用ID进行更新
    if(isEdit && existingGroup && existingGroup.id !== undefined){
      body.id = existingGroup.id;
      body.group_id = gid;  // 允许修改群号

      // 处理到期时间
      if(length > 0){
        // 如果填了续费时长,则在原基础上续费
        body.length = length;
        body.unit = unit;
      } else if(expiryDate){
        // 如果没填续费时长但填了到期时间,直接设置到期时间
        try{
          const d = new Date(expiryDate);
          body.expiry = d.toISOString();
        }catch{
          showToast('到期时间格式错误','warning');
          return;
        }
      }

      if(managed_by_bot) body.managed_by_bot = managed_by_bot;
      if(renewed_by) body.renewed_by = renewed_by;
      if(remark) body.remark = remark;

      await apiCall('/extend', { method:'POST', body: JSON.stringify(body) });
      showToast(`已成功修改群 ${gid} 的信息`,'success');
    }
    // 新增模式
    else {
      body.group_id = gid;

      // 新增时必须有到期时间或续费时长
      if(length > 0){
        body.length = length;
        body.unit = unit;
      } else if(expiryDate){
        try{
          const d = new Date(expiryDate);
          body.expiry = d.toISOString();
        }catch{
          showToast('到期时间格式错误','warning');
          return;
        }
      } else {
        showToast('新增群时必须填写到期时间或续费时长','warning');
        return;
      }

      if(managed_by_bot) body.managed_by_bot = managed_by_bot;
      if(renewed_by) body.renewed_by = renewed_by;
      if(remark) body.remark = remark;

      await apiCall('/extend', { method:'POST', body: JSON.stringify(body) });
      showToast(`已成功新增群 ${gid}`,'success');
    }

    // 记住续费人
    try{ if(renewed_by) localStorage.setItem('extend_renewer', renewed_by); }catch{}

    // 清除选中状态
    $$('.group-checkbox').forEach(cb => cb.checked = false);

    await loadRenewalData();
  }catch(e){
    showToast('操作失败: '+(e&&e.message?e.message:e),'error');
  }finally{
    showLoading(false);
  }
}

// 事件绑定
function bindEvents(){
  $('#theme-toggle')?.addEventListener('click', toggleTheme);
  $$('.nav-item').forEach(i=> i.addEventListener('click', e=>{ e.preventDefault(); switchTab(i.dataset.tab);}));
  $('#generate-code-btn')?.addEventListener('click', generateCode);
  $('#save-permissions-btn')?.addEventListener('click', savePermissions);
  $('#open-permissions-json-btn')?.addEventListener('click', openPermJsonModal);
  $('#perm-json-close')?.addEventListener('click', closePermJsonModal);
  $('#perm-json-cancel')?.addEventListener('click', closePermJsonModal);
  $('#perm-json-save')?.addEventListener('click', savePermJson);
  $('#config-save-btn')?.addEventListener('click', saveCurrentConfig);
  $('#notify-open-btn')?.addEventListener('click', openNotifyModal);
  $('#notify-close')?.addEventListener('click', ()=>closeModal('notify-modal'));
  $('#notify-cancel')?.addEventListener('click', ()=>closeModal('notify-modal'));
  $('#notify-confirm')?.addEventListener('click', sendNotify);
  $('#manual-open-btn')?.addEventListener('click', openManualExtendModal);
  $('#extend-close')?.addEventListener('click', ()=>closeModal('extend-modal'));
  $('#extend-cancel')?.addEventListener('click', ()=>closeModal('extend-modal'));
  $('#extend-confirm')?.addEventListener('click', submitManualExtend);
  $('#group-search')?.addEventListener('input', e=>{ state.keyword=e.target.value.trim(); state.pagination.currentPage=1; renderGroupsTable(); });
  $('#status-filter')?.addEventListener('change', e=>{ state.filter=e.target.value; state.pagination.currentPage=1; renderGroupsTable(); });
  $('#select-all')?.addEventListener('change', e=> $$('.group-checkbox').forEach(cb=> cb.checked=e.target.checked));
  $('#refresh-btn')?.addEventListener('click', ()=>{ const active=$('.nav-item.active'); if(active) switchTab(active.dataset.tab); });

  // 分页控件事件
  $('#pagination-first')?.addEventListener('click', () => goToPage(1));
  $('#pagination-prev')?.addEventListener('click', () => goToPage(state.pagination.currentPage - 1));
  $('#pagination-next')?.addEventListener('click', () => goToPage(state.pagination.currentPage + 1));
  $('#pagination-last')?.addEventListener('click', () => goToPage(state.pagination.totalPages));
  $('#pagination-size-select')?.addEventListener('change', e => changePageSize(e.target.value));

  // 页码点击事件（使用事件委托）
  $('#pagination-pages')?.addEventListener('click', e => {
    if (e.target.classList.contains('pagination-page')) {
      const page = parseInt(e.target.dataset.page);
      if (page) goToPage(page);
    }
  });

  const tbl=$('#groups-table-body');
  if(tbl){
    tbl.addEventListener('click', async (e)=>{
      const btn=e.target.closest('.btn-action'); if(!btn) return; const gid=parseInt(btn.dataset.gid);
      try{
        if(btn.classList.contains('btn-remind')){
          await remindGroups([gid]); showToast(`已向群 ${gid} 发送提醒`,'success');
        } else if(btn.classList.contains('btn-extend')){
          // 改为使用 id 编辑，去掉按 group_id 编辑
          const g = (state.groups||[]).find(x=> String(x.gid)===String(gid));
          if(!g || typeof g.id === 'undefined'){
            showToast('该群记录缺少ID，无法直接续费，请使用“新增/编辑”','warning');
            return;
          }
          await apiCall('/extend',{method:'POST', body: JSON.stringify({ id: g.id, group_id: gid, length:30, unit:'天'})});
          showToast(`已为群 ${gid} 延长30天`,'success'); await loadRenewalData();
        } else if(btn.classList.contains('btn-leave')){
          if(!confirm(`确认让机器人退出群 ${gid}?`)) return; await leaveGroups([gid]);
          showToast(`已退出群 ${gid}`,'success'); await loadRenewalData();
        }
      } catch(err){ showToast('操作失败: '+(err&&err.message?err.message:err),'error'); }
    });
  }
  $('#codes-list')?.addEventListener('click', async (e)=>{ const btn=e.target.closest('.btn-copy'); if(!btn) return; const code=btn.dataset.code||''; const ok=await copyText(code); showToast(ok?'续费码已复制':'复制失败', ok?'success':'error'); });

  // 统计筛选/排序控件
  const kw = document.createElement('input'); kw.id='stats-keyword'; kw.className='input'; kw.placeholder='🔍 按Bot过滤';
  const sel = document.createElement('select'); sel.id='stats-sort'; sel.className='input'; sel.innerHTML = `
    <option value="total_desc">📊 按总发送(降序)</option>
    <option value="total_asc">📊 按总发送(升序)</option>
    <option value="bot_asc">🤖 按Bot(升序)</option>
    <option value="bot_desc">🤖 按Bot(降序)</option>
    <option value="group_desc">👥 按群聊数(降序)</option>
    <option value="private_desc">💬 按私聊数(降序)</option>`;
  const statsTab = document.getElementById('tab-stats');
  if(statsTab){
    const panel = statsTab.querySelector('.panel');
    if(panel){
      const bar=document.createElement('div');
      bar.className='toolbar';
      bar.style.margin='0 0 12px 0';
      bar.appendChild(kw);
      bar.appendChild(sel);
      const panelHeader = panel.querySelector('.panel-header');
      if(panelHeader){
        panelHeader.parentElement.insertBefore(bar, panelHeader.nextSibling);
      }
    }
  }
  $('#stats-keyword')?.addEventListener('input', e=>{ state.statsKeyword=e.target.value.trim(); renderStatsDetails(state.stats?.today||{}); });
  $('#stats-sort')?.addEventListener('change', e=>{ state.statsSort=e.target.value; renderStatsDetails(state.stats?.today||{}); });

  // 配置表单中的开关切换事件（使用事件委托）
  document.addEventListener('change', (e) => {
    if (e.target.matches('.config-switch input[type="checkbox"]')) {
      const label = e.target.closest('.config-switch').querySelector('.config-switch-label');
      if (label) {
        label.textContent = e.target.checked ? '已启用' : '已禁用';
      }
    }
  });
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
  // 先加载系统配置的"临近到期阈值(天)"
  await loadSoonThreshold();
  await loadDashboard();
}

// 增强主题切换
function toggleTheme(){
  state.theme = state.theme==='light' ? 'dark':'light';
  document.body.setAttribute('data-theme', state.theme);
  localStorage.setItem('theme', state.theme);

  const i=$('#theme-toggle .icon');
  if(i) {
    i.textContent = state.theme==='light' ? '🌞' : '🌙';
  }

  showToast(`已切换到${state.theme==='light'?'亮色':'暗色'}主题`, 'success');
}

// 事件绑定
window.runScheduledTask = async function(){
  try{
    showLoading(true);
    const r=await apiCall('/job/run',{method:'POST'});
    showToast(`检查完成！提醒 ${r.reminded} 个群，退出 ${r.left} 个群`,'success');
  } catch(e){
    showToast('执行失败: '+(e&&e.message?e.message:e),'error');
  } finally{
    showLoading(false);
  }
};

window.addEventListener('DOMContentLoaded', ()=>{
  init();
  bindEvents();

  // 添加页面可见性监听
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      const activeTab = document.querySelector('.nav-item.active');
      if (activeTab && activeTab.dataset.tab === 'dashboard') {
        loadDashboard();
      }
    }
  });
});

window.switchTab = switchTab;
