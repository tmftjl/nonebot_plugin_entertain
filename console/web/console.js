// ==================== 浠婃睈鎺у埗鍙板墠绔紙UTF-8锛?====================

// 鍏ㄥ眬鐘舵€?
const state = {
  groups: [],
  stats: null,
  permissions: null,
  config: null,
  schemas: null,
  pluginNames: {},
  commandNames: {},  // 鍛戒护涓枃鍚? {plugin: {command: displayName}}
  theme: localStorage.getItem('theme') || 'light',
  sortBy: 'days', sortDir: 'asc', filter: 'all', keyword: '',
  statsSort: 'total_desc', // total_desc | total_asc | bot_asc | bot_desc | group_desc | private_desc
  statsKeyword: '',
  // 鍒嗛〉鐘舵€?  pagination: {
    currentPage: 1,
    pageSize: 20,
    totalItems: 0,
    totalPages: 0
  }
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
// 鍗冲皢鍒版湡闃堝€硷細榛樿 7 澶╋紱浠庣郴缁熼厤缃姩鎬佽鍙栬鐩?let SOON_THRESHOLD_DAYS = 7;
function getStatusLabel(days){ if(days<0) return '<span class="status-badge status-expired">宸插埌鏈?/span>'; if(days===0) return '<span class="status-badge status-today">浠婃棩鍒版湡</span>'; if(days<=SOON_THRESHOLD_DAYS) return '<span class="status-badge status-soon">鍗冲皢鍒版湡</span>'; return '<span class="status-badge status-active">鏈夋晥</span>'; }
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
  const headers = {'Content-Type':'application/json', ...(options.headers||{})};
  const resp = await fetch(`/member_renewal${path}`, { ...options, headers });
  if(!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
  const ct = resp.headers.get('content-type')||'';
  return ct.includes('application/json') ? resp.json() : resp.text();
}

// 涓婚鍒囨崲鍦ㄤ笅鏂瑰凡澧炲己鐗堟湰瀹炵幇锛屾澶勭Щ闄ら噸澶嶅畾涔?

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
      .map(([gid,info])=>{ const d=daysRemaining(info.expiry); let s='active'; if(d<0)s='expired'; else if(d===0)s='today'; else if(d<=SOON_THRESHOLD_DAYS)s='soon'; return { gid, ...info, days:d, status:s };});
    $('#stat-active-groups').textContent=state.groups.length;
    $('#stat-valid-members').textContent=state.groups.filter(g=>g.status==='active').length;
    $('#stat-expiring-soon').textContent=state.groups.filter(g=>g.status==='soon'||g.status==='today').length;
    $('#stat-expired').textContent=state.groups.filter(g=>g.status==='expired').length;
  } catch(e){ showToast('鍔犺浇浠〃鐩樺け璐? '+(e&&e.message?e.message:e),'error'); }
}

// 缁垂
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
  } catch(e){ showToast('鍔犺浇缁垂鏁版嵁澶辫触: '+(e&&e.message?e.message:e),'error'); }
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

  // 鍒嗛〉璁＄畻
  state.pagination.totalItems = list.length;
  state.pagination.totalPages = Math.ceil(list.length / state.pagination.pageSize) || 1;

  // 纭繚褰撳墠椤靛湪鏈夋晥鑼冨洿鍐?
  if (state.pagination.currentPage > state.pagination.totalPages) {
    state.pagination.currentPage = state.pagination.totalPages;
  }
  if (state.pagination.currentPage < 1) {
    state.pagination.currentPage = 1;
  }

  // 鑾峰彇褰撳墠椤电殑鏁版嵁
  const startIndex = (state.pagination.currentPage - 1) * state.pagination.pageSize;
  const endIndex = startIndex + state.pagination.pageSize;
  const pageList = list.slice(startIndex, endIndex);

  tbody.innerHTML = pageList.length? pageList.map(g=>`
    <tr>
      <td><input type="checkbox" class="group-checkbox" data-gid="${g.gid}" data-id="${g.id}"></td>
      <td>${g.gid}</td>
      <td>${getStatusLabel(g.days)}</td>
      <td>${formatDate(g.expiry)}</td>
      <td>${g.days}</td>
      <td>
        <button class="btn-action btn-remind" data-gid="${g.gid}">鎻愰啋</button>
        <button class="btn-action btn-extend" data-gid="${g.gid}">+30澶?/button>
        <button class="btn-action btn-leave" data-gid="${g.gid}">閫€缇?/button>
      </td>
    </tr>`).join('') : '<tr><td colspan="6" class="text-center">鏆傛棤鏁版嵁</td></tr>';

  // 鏇存柊鍒嗛〉鎺т欢
  updatePaginationControls();
}

function renderCodes(codes){
  const el=$('#codes-list'); if(!el) return;
  const arr=Object.entries(codes||{});
  el.innerHTML = arr.length? arr.map(([code,meta])=>`<div class="code-card"><div class="code-info"><div class="code-value">${maskCode(code)}</div><div class="code-meta">${meta.length}${meta.unit} 路 鍙敤${meta.max_use||1}娆?/div></div><button class="btn-copy" data-code="${code}">澶嶅埗</button></div>`).join('') : '<div class="empty-state">鏆傛棤鍙敤缁垂鐮?/div>';
}

// 鏇存柊鍒嗛〉鎺т欢
function updatePaginationControls() {
  const { currentPage, totalPages, totalItems, pageSize } = state.pagination;

  // 鏇存柊淇℃伅鏂囨湰
  const infoText = $('#pagination-info-text');
  if (infoText) {
    const start = (currentPage - 1) * pageSize + 1;
    const end = Math.min(currentPage * pageSize, totalItems);
    infoText.textContent = totalItems > 0
      ? `鍏?${totalItems} 鏉¤褰曪紝鏄剧ず ${start}-${end}`
      : '鍏?0 鏉¤褰?;
  }

  // 鏇存柊鎸夐挳鐘舵€?
  const firstBtn = $('#pagination-first');
  const prevBtn = $('#pagination-prev');
  const nextBtn = $('#pagination-next');
  const lastBtn = $('#pagination-last');

  if (firstBtn) firstBtn.disabled = currentPage <= 1;
  if (prevBtn) prevBtn.disabled = currentPage <= 1;
  if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
  if (lastBtn) lastBtn.disabled = currentPage >= totalPages;

  // 鏇存柊椤电爜鏄剧ず
  const pagesContainer = $('#pagination-pages');
  if (pagesContainer) {
    const pages = [];
    const maxVisible = 5; // 鏈€澶氭樉绀?涓〉鐮佹寜閽?

    if (totalPages <= maxVisible) {
      // 鎬婚〉鏁板皯锛屾樉绀烘墍鏈夐〉鐮?
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      // 鎬婚〉鏁板锛屾櫤鑳芥樉绀洪〉鐮?
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

// 鍒嗛〉璺宠浆鍑芥暟
function goToPage(page) {
  const { totalPages } = state.pagination;
  if (page < 1) page = 1;
  if (page > totalPages) page = totalPages;
  state.pagination.currentPage = page;
  renderGroupsTable();
}

function changePageSize(size) {
  state.pagination.pageSize = parseInt(size) || 20;
  state.pagination.currentPage = 1; // 閲嶇疆鍒扮涓€椤?
  renderGroupsTable();
}

// 缁熻锛堣鍙?/member_renewal/stats/today 骞朵粎灞曠ず浠婂ぉ锛?
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
  } catch(e){ showToast('鍔犺浇缁熻澶辫触: '+(e&&e.message?e.message:e),'error'); }
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

    if(!rows.length) {
      container.innerHTML = '<div class="empty-state">馃摥 鏆傛棤鏁版嵁</div>';
      return;
    }

    // 娓叉煋鎵嬮鐞村紡Bot鍒楄〃
    const formatTargets = (targets) => {
      const entries = Object.entries(targets||{});
      if(!entries.length) return '<div class="empty-state-mini">鏆傛棤鏁版嵁</div>';

      // 鎸夋秷鎭暟閲忔帓搴?
      entries.sort((a, b) => b[1] - a[1]);

      // 濡傛灉鏁伴噺澶锛屽彧鏄剧ず鍓?0涓紝鍏朵粬鐨勬姌鍙?
      const showLimit = 10;
      const mainEntries = entries.slice(0, showLimit);
      const moreEntries = entries.slice(showLimit);

      let html = mainEntries.map(([id, count])=>
        `<div class="stats-target-item"><span class="id">${id}</span><span class="count">${count}</span></div>`
      ).join('');

      if(moreEntries.length > 0) {
        const moreCount = moreEntries.reduce((sum, [, count]) => sum + count, 0);
        html += `<div class="stats-target-more">... 杩樻湁 ${moreEntries.length} 涓璞?(鍏?${moreCount} 鏉℃秷鎭?</div>`;
      }

      return html;
    };

    const html = rows.map((bot, index)=>`
      <div class="stats-bot-item">
        <div class="stats-bot-header" data-index="${index}">
          <div class="stats-bot-title">
            <span class="stats-bot-icon">鈻讹笍</span>
            <span>馃 Bot ${bot.id}</span>
          </div>
          <div class="stats-bot-summary">
            <span>鎬昏: <strong>${bot.total}</strong></span>
            <span>缇よ亰: <strong>${bot.gCount}</strong> (${Object.keys(bot.gT).length}涓兢)</span>
            <span>绉佽亰: <strong>${bot.pCount}</strong> (${Object.keys(bot.pT).length}浜?</span>
          </div>
        </div>
        <div class="stats-bot-content">
          <div class="stats-bot-body">
            <div class="stats-targets-grid">
              <div class="stats-target-section">
                <div class="stats-target-title">馃懃 缇よ亰娑堟伅璇︽儏 (鍏?{Object.keys(bot.gT).length}涓兢)</div>
                <div class="stats-target-list">
                  ${formatTargets(bot.gT)}
                </div>
              </div>
              <div class="stats-target-section">
                <div class="stats-target-title">馃挰 绉佽亰娑堟伅璇︽儏 (鍏?{Object.keys(bot.pT).length}浜?</div>
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

    // 缁戝畾鎵嬮鐞寸偣鍑讳簨浠?
    container.querySelectorAll('.stats-bot-header').forEach(header => {
      header.addEventListener('click', function() {
        const item = this.closest('.stats-bot-item');
        const content = item.querySelector('.stats-bot-content');
        const isActive = this.classList.contains('active');

        // 鍏抽棴鍏朵粬椤?
        container.querySelectorAll('.stats-bot-header').forEach(h => {
          h.classList.remove('active');
          const c = h.closest('.stats-bot-item').querySelector('.stats-bot-content');
          c.classList.remove('active');
        });

        // 鍒囨崲褰撳墠椤?
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

// 鏂扮殑鎵嬮鐞村紡鏉冮檺鍒楄〃娓叉煋
function renderPermissionsList(){
  const wrap=document.getElementById('permissions-list');
  if(!wrap) return;
  const data = state.permissions || {};
  const sub = (data.sub_plugins||{});
  const plugins = Object.keys(sub).sort((a,b)=>a.localeCompare(b));
  if(!plugins.length && !data.top){ wrap.innerHTML = '<div class="empty-state">馃挙 鏆傛棤鏉冮檺鏁版嵁</div>'; return; }
  
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

  // 鍏ㄥ眬鏉冮檺鍧楋紙椤朵笂涓€涓€荤殑鎺у埗锛?
  const globalTop = from(data.top);
  const gWl = from(globalTop.whitelist);
  const gBl = from(globalTop.blacklist);
  const globalHTML = `
    <div id="perm-global" class="perm-global-block panel" style="margin-bottom: 16px;">
      <div class="panel-header" style="display:flex;align-items:center;justify-content:space-between;">
        <div style="font-weight:600;">馃寪 鍏ㄥ眬鏉冮檺</div>
        <label class="perm-field">
          <input type="checkbox" class="perm-enabled" ${globalTop.enabled===false?'':'checked'}>
          <span>榛樿鍚敤</span>
        </label>
      </div>
      <div class="panel-body">
        <div class="perm-plugin-inline-config">
          <label class="perm-field">
            <span>馃懁 榛樿鏉冮檺绛夌骇</span>
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
      // 鑾峰彇鍛戒护鐨勪腑鏂囧悕
      const cmdDisplay = (state.commandNames && state.commandNames[pn] && state.commandNames[pn][cn]) || cn;
      return `<div class="perm-command-item" data-command="${esc(cn)}">
        <div class="perm-command-header">
          <div class="perm-command-name">馃搶 ${esc(cmdDisplay)}</div>
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
    
    const display = state.pluginNames[pn] || pn;
    return `<div class="perm-accordion-item" data-plugin="${esc(pn)}">
      <div class="perm-accordion-header" data-index="${index}">
        <div class="perm-accordion-title">
          <span class="perm-accordion-icon">鈻讹笍</span>
          <span>馃攲 ${esc(display)}</span>
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
              <span>馃懁 榛樿鏉冮檺绛夌骇</span>
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
              <div class="perm-commands-title">馃幆 鍛戒护鏉冮檺閰嶇疆 (${Object.keys(cmds).length}涓懡浠?</div>
              <div class="perm-commands-list">${cmdRows}</div>
            </div>
          ` : '<div class="empty-state" style="padding: 40px 20px;">馃挙 璇ユ彃浠舵殏鏃犲懡浠?/div>'}
        </div>
      </div>
    </div>`;
  });
  
  const pluginsHTML = rows.join('') || '<div class="empty-state">鏆傛棤瀛愭彃锟?/div>';
  wrap.innerHTML = globalHTML + pluginsHTML;
  
  // 缁戝畾鎵嬮鐞寸偣鍑讳簨浠讹紙鍔ㄦ€侀珮搴︼紝閬垮厤鍐呭杩囬暱琚鍒囷級
  wrap.querySelectorAll('.perm-accordion-header').forEach(header => {
    header.addEventListener('click', function() {
      const item = this.closest('.perm-accordion-item');
      const content = item.querySelector('.perm-accordion-content');
      const isActive = this.classList.contains('active');

      // 鍏抽棴鎵€鏈夊叾浠栭」骞堕噸缃珮搴?      wrap.querySelectorAll('.perm-accordion-header').forEach(h => {
        h.classList.remove('active');
        const c = h.closest('.perm-accordion-item').querySelector('.perm-accordion-content');
        c.classList.remove('active');
        c.style.maxHeight = '0px';
      });

      // 鎵撳紑褰撳墠椤瑰苟鏍规嵁鍐呭璁＄畻楂樺害
      if (!isActive) {
        this.classList.add('active');
        content.classList.add('active');
        // 鍏堟竻绌哄啀璇诲彇 scrollHeight 浠ヨЕ鍙戞纭绠?        content.style.maxHeight = 'none';
        const target = content.scrollHeight;
        content.style.maxHeight = target + 'px';
      }
    });
  });
}

// 浠嶶I鏀堕泦鏉冮檺閰嶇疆锛堥€傞厤鏂扮殑鎵嬮鐞寸粨鏋勶級
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
    
    // 鑾峰彇鎻掍欢椤剁骇閰嶇疆
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
    
    // 鑾峰彇鍛戒护閰嶇疆
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
  } catch(e){ showToast('鍔犺浇鏉冮檺澶辫触: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false);} }
async function savePermissions(){
  try{
    const cfg = collectPermissionsFromUI();
    showLoading(true);
    await apiCall('/permissions',{method:'PUT', body: JSON.stringify(cfg)});
    showToast('鏉冮檺閰嶇疆宸蹭繚瀛?,'success');
    state.permissions=cfg;
    const ta=$('#permissions-json'); if(ta) ta.value=JSON.stringify(cfg,null,2);
  } catch(e){ showToast('淇濆瓨澶辫触: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false);} }
// 閰嶇疆绠＄悊鐩稿叧
let currentActiveConfigTab = null;

// 閰嶇疆椤逛腑鏂囨弿杩版槧灏?
const CONFIG_DESCRIPTIONS = {
  // 閫氱敤閰嶇疆鎻忚堪
  'enabled': '鏄惁鍚敤姝ら厤缃」',
  'enable': '鏄惁鍚敤姝ゅ姛鑳?,
  'debug': '鏄惁寮€鍚皟璇曟ā寮?,
  'log_level': '鏃ュ織杈撳嚭绾у埆',
  'max_retry': '鏈€澶ч噸璇曟鏁?,
  'timeout': '瓒呮椂鏃堕棿锛堢锛?,
  'interval': '鎵ц闂撮殧锛堢锛?,
  'port': '鏈嶅姟绔彛鍙?,
  'host': '鏈嶅姟涓绘満鍦板潃',
  'api_key': 'API瀵嗛挜',
  'secret_key': '瀵嗛挜',
  'token': '璁块棶浠ょ墝',
  'url': '鎺ュ彛鍦板潃',
  'path': '鏂囦欢璺緞',
  'prefix': '鍛戒护鍓嶇紑',
  'suffix': '鍛戒护鍚庣紑',
  'max_length': '鏈€澶ч暱搴?,
  'min_length': '鏈€灏忛暱搴?,
  'cache_time': '缂撳瓨鏃堕棿锛堢锛?,
  'rate_limit': '閫熺巼闄愬埗锛堟/绉掞級',

  // 鏍规嵁瀹為檯閰嶇疆娣诲姞鏇村鎻忚堪
  'whitelist': '鐧藉悕鍗曞垪琛?,
  'blacklist': '榛戝悕鍗曞垪琛?,
  'admin_list': '绠＄悊鍛樺垪琛?,
  'superusers': '瓒呯骇鐢ㄦ埛鍒楄〃',
};

// 鑾峰彇閰嶇疆椤圭殑涓枃鎻忚堪
function getConfigDescription(key) {
  // 鍏堟煡鎵剧簿纭尮閰?
  if (CONFIG_DESCRIPTIONS[key]) {
    return CONFIG_DESCRIPTIONS[key];
  }

  // 灏濊瘯妯＄硦鍖归厤
  const lowerKey = key.toLowerCase();
  for (const [k, v] of Object.entries(CONFIG_DESCRIPTIONS)) {
    if (lowerKey.includes(k)) {
      return v;
    }
  }

  // 濡傛灉娌℃湁鎻忚堪锛岃繑鍥炴牸寮忓寲鐨刱ey
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
    showToast('鍔犺浇閰嶇疆澶辫触: '+(e&&e.message?e.message:e),'error');
  } finally{
    showLoading(false);
  }
}

// 娓叉煋鏍囩椤靛鑸拰鍐呭
function renderConfigTabs() {
  const navContainer = $('#config-tabs-nav');
  const contentContainer = $('#config-tabs-content');

  if (!navContainer || !contentContainer) return;

  const configs = state.config || {};
  const configKeys = Object.keys(configs).sort((a, b) => a.localeCompare(b));

  if (configKeys.length === 0) {
    navContainer.innerHTML = '<div class="empty-state">鏆傛棤閰嶇疆椤?/div>';
    contentContainer.innerHTML = '<div class="empty-state">鏆傛棤閰嶇疆鏁版嵁</div>';
    return;
  }

  // 娓叉煋涓绘爣绛惧鑸?
  const tabsHtml = configKeys.map(key => {
    // 浼樺厛浣跨敤 schema 鐨?title锛屾渶鍚庣敤 key
    const schema = (state.schemas && state.schemas[key]) || {};
    const label = schema.title || key;
    return `
      <div class="config-tab-item" data-config-key="${escapeHtml(key)}">
        ${escapeHtml(label)}
      </div>
    `;
  }).join('');
  navContainer.innerHTML = tabsHtml;

  // 娓叉煋鎵€鏈夋爣绛鹃〉鍐呭
  const contentsHtml = configKeys.map(key => {
    const configData = configs[key];
    const subKeys = getConfigSubKeys(configData, key);
    // 涓烘覆鏌撴鎻掍欢鐨勮〃鍗曚复鏃惰缃?Schema 涓婁笅鏂?
    const __prevSchemaCtx = (typeof schemaContextPlugin !== 'undefined') ? schemaContextPlugin : null;
    window.schemaContextPlugin = key;

    // 濡傛灉鏈夊涓瓙閰嶇疆椤癸紝浣跨敤浜岀骇鏍囩椤?
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
      // 鍗曚釜閰嶇疆椤癸紝鐩存帴灞曠ず
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

  // 缁戝畾涓绘爣绛剧偣鍑讳簨浠?
  navContainer.querySelectorAll('.config-tab-item').forEach(tab => {
    tab.addEventListener('click', () => {
      const key = tab.getAttribute('data-config-key');
      switchConfigTab(key);
    });
  });

  // 缁戝畾瀛愭爣绛剧偣鍑讳簨浠?
  contentContainer.querySelectorAll('.config-sub-tabs-nav').forEach(subNav => {
    subNav.querySelectorAll('.config-sub-tab-item').forEach(subTab => {
      subTab.addEventListener('click', () => {
        const subKey = subTab.getAttribute('data-sub-key');
        const section = subTab.closest('.config-content-section');
        switchConfigSubTab(section, subKey);
      });
    });
  });

  // 榛樿婵€娲荤涓€涓爣绛?
  if (configKeys.length > 0) {
    switchConfigTab(configKeys[0]);
  }
}

// 鑾峰彇閰嶇疆鐨勫瓙閿?
function getConfigSubKeys(data, parentKey) {
  if (typeof data !== 'object' || data === null) return [parentKey];
  if (Array.isArray(data)) return [parentKey];

  const keys = Object.keys(data);
  // 濡傛灉瀵硅薄鐨勫€奸兘鏄璞＄被鍨嬶紙宓屽閰嶇疆锛夛紝鍒欎綔涓哄瓙鏍囩
  const allObjectValues = keys.every(k => typeof data[k] === 'object' && data[k] !== null && !Array.isArray(data[k]));

  // Don't create sub-tabs, always render as nested sections within a single view
  // This allows the nested section CSS styling to work properly
  return [parentKey];
}

// 鑾峰彇瀛愰厤缃暟鎹?
function getSubConfigData(data, subKey, parentKey) {
  if (subKey === parentKey) return data;
  return data[subKey] || {};
}

// 鍒囨崲瀛愭爣绛鹃〉
function switchConfigSubTab(section, subKey) {
  // 鏇存柊瀛愭爣绛炬縺娲荤姸鎬?
  section.querySelectorAll('.config-sub-tab-item').forEach(tab => {
    tab.classList.toggle('active', tab.getAttribute('data-sub-key') === subKey);
  });

  // 鏇存柊瀛愬唴瀹规樉绀?
  section.querySelectorAll('.config-sub-content').forEach(content => {
    content.classList.toggle('active', content.getAttribute('data-sub-key') === subKey);
  });
}

// 鍒囨崲鏍囩椤?
function switchConfigTab(configKey) {
  currentActiveConfigTab = configKey;

  // 鏇存柊鏍囩婵€娲荤姸鎬?
  $$('.config-tab-item').forEach(tab => {
    tab.classList.toggle('active', tab.getAttribute('data-config-key') === configKey);
  });

  // 鏇存柊鍐呭鏄剧ず
  $$('.config-content-section').forEach(section => {
    const isActive = section.getAttribute('data-config-key') === configKey;
    section.classList.toggle('active', isActive);

    // 濡傛灉鏈夊瓙鏍囩椤碉紝婵€娲荤涓€涓?
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
      <span class="config-section-icon">馃搵</span>
      <span class="config-section-title">鍒楄〃閰嶇疆</span>
    </div>`;

    data.forEach((item, index) => {
      if (typeof item === 'object' && item !== null) {
        html += `<div class="config-array-item">
          <div class="config-array-header">
            <span class="config-array-label">椤圭洰 ${index + 1}</span>
          </div>
          <div class="config-array-body">
            ${renderConfigForm(item, `${parentKey}[${index}]`)}
          </div>
        </div>`;
      } else {
        html += renderConfigField(`${parentKey}[${index}]`, item, `椤圭洰 ${index + 1}`);
      }
    });
    html += `</div>`;
  } else {
    // 瀵硅薄绫诲瀷
    const entries = Object.entries(data);
    entries.forEach(([key, value]) => {
      const fullKey = parentKey ? `${parentKey}.${key}` : key;

      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        // 宓屽瀵硅薄锛屽垱寤烘姌鍙犲尯鍩?
        html += `<div class="config-nested-section">
          <div class="config-nested-header">
            <span class="config-nested-icon">馃搧</span>
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
    // 浣跨敤缇庤鐨勫紑鍏?
    inputHtml = `
      <label class="config-switch">
        <input type="checkbox" data-config-key="${escapedKey}" ${value ? 'checked' : ''}>
        <span class="config-switch-slider"></span>
        <span class="config-switch-label">${value ? '宸插惎鐢? : '宸茬鐢?}</span>
      </label>
    `;
  } else if (type === 'number') {
    inputHtml = `
      <input type="number"
             class="config-input"
             data-config-key="${escapedKey}"
             value="${value}"
             placeholder="璇疯緭鍏ユ暟瀛?>
    `;
  } else if (Array.isArray(value)) {
    inputHtml = `
      <input type="text"
             class="config-input"
             data-config-key="${escapedKey}"
             value="${escapeHtml(value.join(', '))}"
             placeholder="澶氫釜鍊肩敤閫楀彿鍒嗛殧">
      <div class="config-field-hint">澶氫釜鍊艰鐢ㄩ€楀彿鍒嗛殧</div>
    `;
  } else {
    // 瀛楃涓茬被鍨?
    const valueStr = String(value || '');
    if (valueStr.length > 50) {
      inputHtml = `
        <textarea class="config-textarea"
                  data-config-key="${escapedKey}"
                  rows="3"
                  placeholder="璇疯緭鍏?{description}">${escapeHtml(valueStr)}</textarea>
      `;
    } else {
      inputHtml = `
        <input type="text"
               class="config-input"
               data-config-key="${escapedKey}"
               value="${escapeHtml(valueStr)}"
               placeholder="璇疯緭鍏?{description}">
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

// 淇濆瓨褰撳墠鏍囩椤电殑閰嶇疆
async function saveCurrentConfig() {
  if (!currentActiveConfigTab) {
    showToast('璇烽€夋嫨瑕佷繚瀛樼殑閰嶇疆椤?, 'warning');
    return;
  }

  try {
    showLoading(true);

    // 鏌ユ壘褰撳墠婵€娲绘爣绛鹃〉鐨勫唴瀹瑰尯鍩?
    const section = document.querySelector(`.config-content-section[data-config-key="${currentActiveConfigTab}"]`);
    if (!section) return;

    const inputs = section.querySelectorAll('[data-config-key]');
    const updatedConfig = JSON.parse(JSON.stringify(state.config[currentActiveConfigTab]));

    inputs.forEach(input => {
      const fullKey = input.getAttribute('data-config-key');
      const path = fullKey.split(/[.\[\]]+/).filter(Boolean);

      let value;
      if (input.type === 'checkbox') {
        value = input.checked;
      } else if (input.type === 'number') {
        value = parseFloat(input.value) || 0;
      } else {
        value = input.value;
        // 灏濊瘯瑙ｆ瀽涓烘暟缁?
        if (value.includes(',')) {
          const arr = value.split(',').map(s => s.trim()).filter(Boolean);
          if (arr.length > 0) value = arr;
        }
      }

      // 璁剧疆宓屽鍊?
      setNestedValue(updatedConfig, path.join('.'), value);
    });

    // 鏇存柊閰嶇疆
    const newConfig = {...state.config};
    newConfig[currentActiveConfigTab] = updatedConfig;

    // 淇濆瓨鍒版湇鍔″櫒
    await apiCall('/config', {method: 'PUT', body: JSON.stringify(newConfig)});

    state.config = newConfig;
    showToast(`閰嶇疆 "${currentActiveConfigTab}" 宸蹭繚瀛樺苟閲嶆柊鍔犺浇`, 'success');

    await loadConfig();
    // 閲嶆柊鍒囨崲鍒板綋鍓嶆爣绛?
    setTimeout(() => switchConfigTab(currentActiveConfigTab), 100);
  } catch(e) {
    showToast('淇濆瓨澶辫触: ' + (e && e.message ? e.message : e), 'error');
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
  if(!ids.length){ showToast('璇峰厛鍕鹃€夎閫氱煡鐨勭兢','warning'); return; }
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
  if(!ids.length){ showToast('鏈€夋嫨浠讳綍缇?,'warning'); return; }
  const text = ($('#notify-text')?.value||'').trim();
  const imgs = await filesToBase64List($('#notify-images'));
  if(!text && (!imgs || !imgs.length)){ showToast('璇峰～鍐欐枃鏈垨閫夋嫨鍥剧墖','warning'); return; }

  // 绔嬪嵆鍏抽棴寮圭獥,闃叉閲嶅鐐瑰嚮
  closeModal('notify-modal');

  try{
    showLoading(true);
    await apiCall('/notify', { method:'POST', body: JSON.stringify({ group_ids: ids, text, images: imgs }) });
    showToast(`宸插悜 ${ids.length} 涓兢鍙戦€侀€氱煡`,'success');
  }catch(e){
    showToast('鍙戦€佸け璐? '+(e&&e.message?e.message:e),'error');
  }finally{
    showLoading(false);
  }
}

// 璇诲彇绯荤粺閰嶇疆涓殑鈥滀复杩戝埌鏈熼槇鍊?澶?鈥濋厤缃?async function loadSoonThreshold(){
  try{
    const cfg = await apiCall('/config');
    // system 鍖哄煙鍐呰鍙?member_renewal_soon_threshold_days
    const sys = (cfg && cfg.system) ? cfg.system : cfg; // 鍏煎浠呰繑鍥?system 鐨勬儏鍐?    const v = sys && (sys.member_renewal_soon_threshold_days ?? sys['member_renewal_soon_threshold_days']);
    if(typeof v === 'number' && isFinite(v) && v >= 0){
      SOON_THRESHOLD_DAYS = v;
    }
  }catch{
    // 澶辫触淇濈暀榛樿 7 澶?    SOON_THRESHOLD_DAYS = 7;
  }
}

async function openManualExtendModal(){
  const ids = selectedRecordIds();
  const idEl = $("#extend-group-id");
  const infoEl = $("#extend-selected-info");
  const curEl = $("#extend-current-info");
  if(ids.length){
    const g = (state.groups||[]).find(x=> String(x.id)===String(ids[0]));
    idEl.value = g ? String(g.gid) : "";
    if(infoEl) infoEl.textContent = `已选择 ${ids.length} 个群，将按所选记录续费；未选择则按输入群号新增`;
    if(g && g.expiry){ curEl.textContent = `当前到期：${formatDate(g.expiry)}`; } else { curEl.textContent = ""; }
    const botInput = document.getElementById("extend-bot-id");
    if(botInput){ botInput.value = (g && g.managed_by_bot) ? String(g.managed_by_bot) : ""; }
  } else {
    idEl.value = "";
    if(infoEl) infoEl.textContent = "未选择群，可在下方输入群号进行新增";
    if(curEl) curEl.textContent = "";
    const botInput = document.getElementById("extend-bot-id");
    if(botInput){ botInput.value = ""; }
  }
  $("#extend-length").value = "30";
  $("#extend-unit").value = "天";
  try{ const last = localStorage.getItem("extend_renewer")||""; if(last) $("#extend-renewer").value = last; }catch{}
  const remarkEl = document.getElementById("extend-remark"); if(remarkEl) remarkEl.value = "";
  openModal("extend-modal");
}

async function submitManualExtend(){
  const inputId = ($('#extend-group-id')?.value||'').trim();
  let ids = selectedRecordIds();
  const length = parseInt(($('#extend-length')?.value||'').trim());
  const unit = ($('#extend-unit')?.value||'澶?);
  const managed_by_bot = ($('#extend-bot-id')?.value||'').trim();
  const renewed_by = ($('#extend-renewer')?.value||'').trim();
  if(!ids.length && !inputId){ showToast('请先选择群，或填写群号','warning'); return; }
  if(!length || isNaN(length) || length<=0){ showToast('璇疯緭鍏ユ纭殑鏃堕暱','warning'); return; }

  // 绔嬪嵆鍏抽棴寮圭獥,闃叉閲嶅鐐瑰嚮
  closeModal('extend-modal');

  try{
    showLoading(true);
    if(ids.length){
      for(const rid of ids){
        const body = { id: rid, length, unit };
        if(managed_by_bot) body.managed_by_bot = managed_by_bot;
        if(renewed_by) body.renewed_by = renewed_by;
        if(remark) body.remark = remark;
        await apiCall('/extend',{ method:'POST', body: JSON.stringify(body) });
      }
    } else {
      const gid = parseInt(inputId);
      if(!gid){ showToast('群号无效','warning'); return; }
      const body = { group_id: gid, length, unit };
      if(managed_by_bot) body.managed_by_bot = managed_by_bot;
      if(renewed_by) body.renewed_by = renewed_by;
      if(remark) body.remark = remark;
      await apiCall('/extend',{ method:'POST', body: JSON.stringify(body) });
    }
    showToast(`宸插鐞?${ids.length} 涓兢锛?${length}${unit}`,'success');
    // 璁颁綇缁垂浜?    try{ if(renewed_by) localStorage.setItem('extend_renewer', renewed_by); }catch{}
    await loadRenewalData();
  }catch(e){
    showToast('鎿嶄綔澶辫触: '+(e&&e.message?e.message:e),'error');
  }finally{
    showLoading(false);
  }
}

// 浜嬩欢缁戝畾
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

  // 鍒嗛〉鎺т欢浜嬩欢
  $('#pagination-first')?.addEventListener('click', () => goToPage(1));
  $('#pagination-prev')?.addEventListener('click', () => goToPage(state.pagination.currentPage - 1));
  $('#pagination-next')?.addEventListener('click', () => goToPage(state.pagination.currentPage + 1));
  $('#pagination-last')?.addEventListener('click', () => goToPage(state.pagination.totalPages));
  $('#pagination-size-select')?.addEventListener('change', e => changePageSize(e.target.value));

  // 椤电爜鐐瑰嚮浜嬩欢锛堜娇鐢ㄤ簨浠跺鎵橈級
  $('#pagination-pages')?.addEventListener('click', e => {
    if (e.target.classList.contains('pagination-page')) {
      const page = parseInt(e.target.dataset.page);
      if (page) goToPage(page);
    }
  });

  const tbl=$('#groups-table-body');
  if(tbl){
    tbl.addEventListener('click', async (e)=>{
      const btn=e.target.closest('.btn-action'); if(!btn) return; const gid=parseInt(btn.dataset.gid); const g=(state.groups||[]).find(x=> String(x.gid)===String(gid)); const rid=g&&g.id;
      try{
        if(btn.classList.contains('btn-remind')){
          await remindGroups([gid]); showToast(`宸插悜缇?${gid} 鍙戦€佹彁閱抈,'success');
        } else if(btn.classList.contains('btn-extend')){
          if(!rid){ showToast('记录ID缺失，无法续费','error'); return; } await apiCall('/extend',{method:'POST', body: JSON.stringify({ id: rid, length:30, unit:'天'})});
          showToast(`宸蹭负缇?${gid} 寤堕暱30澶ー,'success'); await loadRenewalData();
        } else if(btn.classList.contains('btn-leave')){
          if(!confirm(`纭璁╂満鍣ㄤ汉閫€鍑虹兢 ${gid}?`)) return; await leaveGroups([gid]);
          showToast(`宸查€€鍑虹兢 ${gid}`,'success'); await loadRenewalData();
        }
      } catch(err){ showToast('鎿嶄綔澶辫触: '+(err&&err.message?err.message:err),'error'); }
    });
  }
  $('#codes-list')?.addEventListener('click', async (e)=>{ const btn=e.target.closest('.btn-copy'); if(!btn) return; const code=btn.dataset.code||''; const ok=await copyText(code); showToast(ok?'缁垂鐮佸凡澶嶅埗':'澶嶅埗澶辫触', ok?'success':'error'); });

  // 缁熻绛涢€?鎺掑簭鎺т欢
  const kw = document.createElement('input'); kw.id='stats-keyword'; kw.className='input'; kw.placeholder='馃攳 鎸塀ot杩囨护';
  const sel = document.createElement('select'); sel.id='stats-sort'; sel.className='input'; sel.innerHTML = `
    <option value="total_desc">馃搳 鎸夋€诲彂閫?闄嶅簭)</option>
    <option value="total_asc">馃搳 鎸夋€诲彂閫?鍗囧簭)</option>
    <option value="bot_asc">馃 鎸塀ot(鍗囧簭)</option>
    <option value="bot_desc">馃 鎸塀ot(闄嶅簭)</option>
    <option value="group_desc">馃懃 鎸夌兢鑱婃暟(闄嶅簭)</option>
    <option value="private_desc">馃挰 鎸夌鑱婃暟(闄嶅簭)</option>`;
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

  // 閰嶇疆琛ㄥ崟涓殑寮€鍏冲垏鎹簨浠讹紙浣跨敤浜嬩欢濮旀墭锛?
  document.addEventListener('change', (e) => {
    if (e.target.matches('.config-switch input[type="checkbox"]')) {
      const label = e.target.closest('.config-switch').querySelector('.config-switch-label');
      if (label) {
        label.textContent = e.target.checked ? '宸插惎鐢? : '宸茬鐢?;
      }
    }
  });
}

// 鐢熸垚缁垂鐮?
async function generateCode(){
  const btn=$('#generate-code-btn'); if(btn && btn.dataset.busy==='1') return; if(btn){ btn.dataset.busy='1'; btn.setAttribute('disabled','disabled'); }
  const length=parseInt($("#renewal-length").value)||30; let unit=$("#renewal-unit")?.value||"澶?; unit = normalizeUnit(unit);
  try{ showLoading(true); const r=await apiCall('/generate',{method:'POST', body: JSON.stringify({ length, unit })}); showToast(`缁垂鐮佸凡鐢熸垚: ${r.code}`,'success'); await loadRenewalData(); }
  catch(e){ showToast('鐢熸垚澶辫触: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false); if(btn){ delete btn.dataset.busy; btn.removeAttribute('disabled'); } }
}

// 鏉冮檺JSON寮圭獥
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
  }catch(e){ showToast('JSON 淇濆瓨澶辫触: '+(e&&e.message?e.message:e),'error'); }
  finally{ showLoading(false); }
}

// 鍒濆鍖?
async function init(){
  document.body.setAttribute('data-theme', state.theme);
  const i=document.querySelector('#theme-toggle .icon');
  if(i) i.textContent = state.theme==='light' ? '馃尀' : '馃寵';
  // 鍏堝姞杞界郴缁熼厤缃殑鈥滀复杩戝埌鏈熼槇鍊?澶?鈥?  await loadSoonThreshold();
  await loadDashboard();
  
  // 娣诲姞椤甸潰鍔犺浇鍔ㄧ敾
  animatePageLoad();
}

// 椤甸潰鍔犺浇鍔ㄧ敾
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

window.switchTab = switchTab;
window.runScheduledTask = async function(){
  try{
    showLoading(true);
    const r=await apiCall('/job/run',{method:'POST'});
    showToast(`鉁?妫€鏌ュ畬鎴愶紒鎻愰啋 ${r.reminded} 涓兢锛岄€€鍑?${r.left} 涓兢`,'success');
  } catch(e){
    showToast('鉂?鎵ц澶辫触: '+(e&&e.message?e.message:e),'error');
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

// 鎺у埗鍙版杩庝俊鎭?
console.log('%c馃尭 浠婃睈绠＄悊鎺у埗鍙?, 'font-size: 24px; color: #667eea; font-weight: bold;');
console.log('%c鉁?娆㈣繋浣跨敤鐜颁唬鍖栫鐞嗙晫闈?, 'font-size: 14px; color: #6366f1;');
console.log('%c蹇嵎閿彁绀?\n  Ctrl+K: 鎼滅储\n  Ctrl+R: 鍒锋柊\n  Ctrl+D: 鍒囨崲涓婚\n  ESC: 鍏抽棴寮圭獥', 'font-size: 12px; color: #94a3b8; line-height: 1.8;');



