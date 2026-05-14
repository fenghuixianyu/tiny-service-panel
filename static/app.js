let direction = localStorage.tspDirection || 'desc';
let allUnits = [];
const pendingUnits = new Set();
let hideNoisy = localStorage.tspHideNoisy !== '0';
let favoritesOnly = localStorage.tspFavoritesOnly === '1';
let stateFilter = localStorage.tspStateFilter || 'all';
let bootFilter = localStorage.tspBootFilter || 'all';
let zoneFilter = localStorage.tspZoneFilter || 'all';
const SEARCH_SCOPE_KEYS = ['unit','description','note','state','boot','shield'];
let searchScopes = new Set((localStorage.tspSearchScopes || SEARCH_SCOPE_KEYS.join(',')).split(',').filter(Boolean));
if(!searchScopes.size) searchScopes = new Set(SEARCH_SCOPE_KEYS);
let problemFirst = localStorage.tspProblemFirst !== '0';
const $ = id => document.getElementById(id);

const BOOT_LABELS = {
  'enabled': '已自启',
  'enabled-runtime': '临时自启',
  'disabled': '未自启',
  'static': 'static',
  'indirect': 'indirect',
  'generated': 'generated',
  'transient': 'transient',
  'alias': 'alias',
  'masked': '已屏蔽',
  'masked-runtime': '临时屏蔽',
  'linked': 'linked',
  'linked-runtime': 'linked-runtime',
  'unknown': '未知',
};
const BOOT_ENABLED = new Set(['enabled','enabled-runtime','linked','linked-runtime']);
const BOOT_DISABLED = new Set(['disabled']);
const BOOT_MASKED = new Set(['masked','masked-runtime']);
const BOOT_LOCKED = new Set(['static','indirect','generated','transient','alias']);

function mb(n){ return `${Number(n||0).toFixed(1)} MB`; }
function gbFromKb(kb){ return `${(Number(kb||0)/1024/1024).toFixed(1)}G`; }
function humanUptime(seconds){
  seconds = Number(seconds||0);
  const d = Math.floor(seconds/86400), h = Math.floor(seconds%86400/3600), m = Math.floor(seconds%3600/60);
  if(d) return `${d}天 ${h}小时`;
  if(h) return `${h}小时 ${m}分`;
  return `${m}分钟`;
}
function esc(s){ return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function jsArg(s){ return JSON.stringify(String(s??'')).replace(/</g,'\\u003c'); }
function showLogin(msg=''){
  $('appShell').hidden = true;
  $('loginPanel').hidden = false;
  $('loginError').hidden = !msg;
  $('loginError').textContent = msg;
  setTimeout(()=>$('loginPassword').focus(), 30);
}
function showApp(authEnabled=false){
  $('loginPanel').hidden = true;
  $('appShell').hidden = false;
  $('logout').hidden = !authEnabled;
}
async function api(url,opts={}){
  const {skipAuth=false, ...fetchOpts} = opts || {};
  const r = await fetch(url, {credentials:'same-origin', ...fetchOpts});
  const text = await r.text();
  let data = null;
  try{ data = text ? JSON.parse(text) : {}; }catch{ data = null; }
  if(r.status === 401 && !skipAuth){
    showLogin('请先登录');
    throw new Error((data && data.error) || '需要登录');
  }
  if(!r.ok) throw new Error((data && data.error) || text || `HTTP ${r.status}`);
  return data ?? {};
}
function stateClass(u){ if(u.active==='active') return 'active'; if(u.active==='failed'||u.sub==='failed') return 'failed'; if(u.active==='activating') return 'warn'; return 'inactive'; }
function primaryAction(u){ return u.active==='active' ? {name:'stop', label:'停止', cls:'danger'} : {name:'start', label:'启动', cls:'ok'}; }
function isProblem(u){ return ['failed','activating','deactivating','reloading'].includes(u.active) || ['failed','auto-restart'].includes(u.sub); }
function matchesState(u){
  if(stateFilter==='active') return u.active==='active';
  if(stateFilter==='inactive') return u.active==='inactive';
  if(stateFilter==='problem') return isProblem(u);
  return true;
}
function bootState(u){ return u.unit_file_state || 'unknown'; }
function bootLabel(u){ return BOOT_LABELS[bootState(u)] || bootState(u); }
function bootClass(u){
  const s = bootState(u);
  if(BOOT_ENABLED.has(s)) return 'enabled';
  if(BOOT_DISABLED.has(s)) return 'disabled';
  if(BOOT_MASKED.has(s)) return 'masked';
  if(BOOT_LOCKED.has(s)) return 'locked';
  return 'unknown';
}
function bootAction(u){
  const s = bootState(u);
  if(s === 'disabled') return {name:'enable', label:'开自启', cls:'ok'};
  if(s === 'enabled' || s === 'enabled-runtime') return {name:'disable', label:'关自启', cls:''};
  return null;
}
function matchesBoot(u){
  const s = bootState(u);
  if(bootFilter === 'enabled') return BOOT_ENABLED.has(s);
  if(bootFilter === 'disabled') return BOOT_DISABLED.has(s);
  if(bootFilter === 'masked') return BOOT_MASKED.has(s);
  if(bootFilter === 'locked') return BOOT_LOCKED.has(s) || s === 'unknown';
  return true;
}
function matchesZone(u){
  const cat = u.shield_category || (u.noisy ? 'base' : 'normal');
  if(zoneFilter === 'normal') return !u.noisy;
  if(zoneFilter === 'shielded') return !!u.noisy;
  if(zoneFilter === 'all') return true;
  return cat === zoneFilter;
}
function searchTextFor(u){
  const parts = [];
  if(searchScopes.has('unit')) parts.push(u.unit || '', u.display_unit || '');
  if(searchScopes.has('description')) parts.push(u.description || '');
  if(searchScopes.has('note')) parts.push(u.note || '');
  if(searchScopes.has('state')) parts.push(u.active || '', u.sub || '');
  if(searchScopes.has('boot')) parts.push(bootLabel(u), bootState(u));
  if(searchScopes.has('shield')) parts.push(u.noisy ? '屏蔽区' : '常用区', u.shield_label || '', u.shield_category || '');
  return parts.join(' ').toLowerCase();
}
function saveSearchScopes(){
  localStorage.tspSearchScopes = SEARCH_SCOPE_KEYS.filter(k=>searchScopes.has(k)).join(',');
}
function syncScopeInputs(){
  document.querySelectorAll('[data-scope]').forEach(el=>{ el.checked = searchScopes.has(el.dataset.scope); });
}

function displayName(u){ return u.note ? `${u.unit}（${u.note}）` : u.unit; }
function findUnit(unit){ return allUnits.find(u=>u.unit===unit); }
function toast(msg, bad=false){ const t=$('toast'); t.textContent=msg; t.className='toast '+(bad?'bad':''); t.hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>t.hidden=true,4200); }

async function loadSummary(){
  const s = await api('/api/summary');
  $('host').textContent = s.hostname;
  $('uptime').textContent = humanUptime(s.uptime && s.uptime.seconds);
  $('mem').textContent = `${s.memory.used_mb}/${s.memory.total_mb} MB · ${s.memory.used_percent}%`;
  const sw = s.swap || {used_mb:0,total_mb:0,used_percent:0};
  $('swap').textContent = sw.total_mb ? `${sw.used_mb}/${sw.total_mb} MB · ${sw.used_percent}%` : '0 MB / 未启用';
  $('load').textContent = s.load.join(' / ');
  $('disk').textContent = s.disk_root.use_percent || '-';
  const rb = s.reboot_required || {required:false, package_count:0};
  $('reboot').textContent = rb.required ? `建议重启${rb.package_count ? ' · '+rb.package_count+'项' : ''}` : '无需重启';
  $('reboot').className = rb.required ? 'warn-text' : 'good-text';
  renderDisks(s.disks || []);
}

function renderDisks(disks){
  const items = disks.slice(0, 6);
  $('diskHint').textContent = disks.length ? `${disks.length} 个挂载点` : '无数据';
  $('disks').innerHTML = items.map(d=>{
    const pct = parseInt(String(d.use_percent||'0').replace('%',''), 10) || 0;
    const cls = pct >= 90 ? 'danger' : pct >= 75 ? 'warn' : '';
    return `<div class="disk-item ${cls}"><div><strong>${esc(d.mount)}</strong><small>${esc(d.filesystem)} · ${esc(d.type)}</small></div><span>${esc(d.use_percent)} · ${gbFromKb(d.used_kb)}/${gbFromKb(d.size_kb)}</span></div>`;
  }).join('') || '<div class="disk-item"><div><strong>无磁盘数据</strong></div><span>-</span></div>';
}

function sortKey(u, key){
  const bootRank = {enabled:0,'enabled-runtime':0,disabled:1,static:2,indirect:2,generated:2,transient:2,alias:2,masked:3,'masked-runtime':3,unknown:4};
  if(key === 'memory') return [Number(u.rss_kb||0), u.unit||''];
  if(key === 'cpu') return [Number(u.cpu_percent||0), u.unit||''];
  if(key === 'name') return [String(u.unit||'')];
  if(key === 'state') return [String(u.active||''), String(u.sub||''), String(u.unit||'')];
  if(key === 'boot') return [bootRank[bootState(u)] ?? 5, String(u.unit||'')];
  return [Number(u.rss_kb||0), u.unit||''];
}
function cmpValue(a,b){
  if(typeof a === 'number' && typeof b === 'number') return a-b;
  return String(a).localeCompare(String(b));
}
function sortUnitsLocal(){
  const key = $('sort').value;
  const sign = direction === 'asc' ? 1 : -1;
  allUnits.sort((a,b)=>{
    const ka = sortKey(a,key), kb = sortKey(b,key);
    for(let i=0;i<Math.max(ka.length,kb.length);i++){
      const c = cmpValue(ka[i] ?? '', kb[i] ?? '');
      if(c) return c * sign;
    }
    return 0;
  });
}

function filteredRows(){
  const q = $('filter').value.toLowerCase().trim();
  const rows = allUnits.filter(u=>{
    if(hideNoisy && u.noisy && !u.favorite) return false;
    if(favoritesOnly && !u.favorite) return false;
    if(!matchesZone(u)) return false;
    if(!matchesState(u)) return false;
    if(!matchesBoot(u)) return false;
    if(!q) return true;
    return searchTextFor(u).includes(q);
  });
  if(problemFirst) rows.sort((a,b)=>Number(isProblem(b))-Number(isProblem(a)));
  return rows;
}

function renderBootButton(u, compact=false){
  if(pendingUnits.has(u.unit)) return '<button disabled>处理中</button>';
  const b = bootAction(u);
  if(!b) return compact ? '<button disabled>不可改自启</button>' : '<button disabled title="当前状态不可直接启用/禁用">自启</button>';
  return `<button class="${b.cls}" onclick='bootAct(${jsArg(u.unit)},${jsArg(b.name)})'>${b.label}</button>`;
}

function renderTableRows(rows){
  return rows.map(u=>{
    const p = primaryAction(u);
    const pending = pendingUnits.has(u.unit);
    return `
    <tr class="${u.favorite?'fav':''} ${u.noisy?'noisy':''}">
      <td class="unit"><div class="unit-wrap">
        <div class="unit-main"><strong>${esc(u.display_unit||displayName(u))}</strong><small>${esc(u.unit)}${u.noisy?' · '+esc(u.shield_label||'屏蔽区'):''}</small></div>
        <button class="quick ${p.cls}" ${pending?'disabled':''} onclick='act(${jsArg(u.unit)},${jsArg(p.name)})'>${pending?'处理中':p.label}</button>
      </div></td>
      <td class="num memcol">${mb(u.memory_mb)}</td>
      <td><span class="state ${stateClass(u)}">${esc(u.active)}/${esc(u.sub)}</span></td>
      <td><span class="boot ${bootClass(u)}">${esc(bootLabel(u))}</span></td>
      <td class="num cpucol">${Number(u.cpu_percent||0).toFixed(1)}%</td>
      <td class="num">${u.process_count||0}</td>
      <td class="desc">${esc(u.description||'')}</td>
      <td><div class="actions">
        <button class="ok" ${pending?'disabled':''} onclick='act(${jsArg(u.unit)},"start")'>启动</button>
        <button ${pending?'disabled':''} onclick='act(${jsArg(u.unit)},"restart")'>重启</button>
        <button class="danger" ${pending?'disabled':''} onclick='act(${jsArg(u.unit)},"stop")'>停止</button>
        ${renderBootButton(u)}
        <button class="fav-btn ${u.favorite?'on':''}" onclick='toggleFavorite(${jsArg(u.unit)})'>${u.favorite?'取消收藏':'收藏'}</button>
        <button onclick='editNote(${jsArg(u.unit)},${jsArg(u.note||'')})'>备注</button>
        <button onclick='showStatus(${jsArg(u.unit)})'>状态</button>
        <button onclick='showLogs(${jsArg(u.unit)})'>日志</button>
      </div></td>
    </tr>`;
  }).join('') || '<tr><td colspan="8" class="empty">没有匹配的服务</td></tr>';
}

function renderMobileCards(rows){
  return rows.map(u=>{
    const p = primaryAction(u);
    const pending = pendingUnits.has(u.unit);
    return `
    <article class="unit-card ${u.favorite?'fav':''} ${u.noisy?'noisy':''}">
      <div class="card-title"><div><strong>${esc(u.display_unit||displayName(u))}</strong><small>${esc(u.description||u.unit)}${u.noisy?' · '+esc(u.shield_label||'屏蔽区'):''}</small></div><button class="star ${u.favorite?'on':''}" onclick='toggleFavorite(${jsArg(u.unit)})'>${u.favorite?'★':'☆'}</button></div>
      <div class="card-meta">
        <span class="state ${stateClass(u)}">运行 ${esc(u.active)}/${esc(u.sub)}</span>
        <span class="boot ${bootClass(u)}">自启 ${esc(bootLabel(u))}</span>
      </div>
      <div class="card-stats"><span class="hot-stat mem">内存 ${mb(u.memory_mb)}</span><span class="hot-stat cpu">CPU ${Number(u.cpu_percent||0).toFixed(1)}%</span></div>
      <div class="card-actions primary">
        <button class="${p.cls}" ${pending?'disabled':''} onclick='act(${jsArg(u.unit)},${jsArg(p.name)})'>${pending?'处理中':p.label}</button>
        <button ${pending?'disabled':''} onclick='act(${jsArg(u.unit)},"restart")'>重启</button>
        ${renderBootButton(u, true)}
      </div>
      <div class="card-actions secondary">
        <button onclick='showStatus(${jsArg(u.unit)})'>状态</button>
        <button onclick='showLogs(${jsArg(u.unit)})'>日志</button>
        <button onclick='editNote(${jsArg(u.unit)},${jsArg(u.note||'')})'>备注</button>
        <button class="fav-btn ${u.favorite?'on':''}" onclick='toggleFavorite(${jsArg(u.unit)})'>${u.favorite?'取消收藏':'收藏'}</button>
      </div>
    </article>`;
  }).join('') || '<div class="empty mobile-empty">没有匹配的服务</div>';
}

function render(){
  $('hideNoisy').classList.toggle('on', hideNoisy);
  $('hideNoisy').textContent = '隐藏系统项';
  $('favoritesOnly').classList.toggle('on', favoritesOnly);
  $('problemFirst').classList.toggle('on', problemFirst);
  $('stateFilter').value = stateFilter;
  $('bootFilter').value = bootFilter;
  $('zoneFilter').value = zoneFilter;
  syncScopeInputs();
  $('dir').textContent = direction === 'desc' ? '降序' : '升序';
  const rows = filteredRows();
  const problemCount = allUnits.filter(isProblem).length;
  $('listCount').textContent = `${rows.length}/${allUnits.length} 项${problemCount ? ' · 异常 '+problemCount : ''}`;
  $('units').innerHTML = renderTableRows(rows);
  $('mobileUnits').innerHTML = renderMobileCards(rows);
}

async function refresh(showLoading=true){
  if(showLoading){
    $('units').innerHTML='<tr><td colspan="8" class="empty">加载中...</td></tr>';
    $('mobileUnits').innerHTML='<div class="empty mobile-empty">加载中...</div>';
  }
  await loadSummary().catch(e=>toast('仪表盘加载失败: '+e.message, true));
  const sort=$('sort').value, type=$('type').value;
  const data=await api(`/api/units?sort=${encodeURIComponent(sort)}&dir=${direction}&type=${encodeURIComponent(type)}`);
  allUnits=data.units;
  sortUnitsLocal();
  render();
}

async function refreshUnits(showLoading=false){
  if(showLoading){
    $('units').innerHTML='<tr><td colspan="8" class="empty">加载中...</td></tr>';
    $('mobileUnits').innerHTML='<div class="empty mobile-empty">加载中...</div>';
  }
  const type=$('type').value;
  const data=await api(`/api/units?sort=${encodeURIComponent($('sort').value)}&dir=${direction}&type=${encodeURIComponent(type)}`);
  allUnits=data.units;
  sortUnitsLocal();
  render();
}

async function act(unit, action){
  if(!confirm(`${action} ${unit}?`)) return;
  pendingUnits.add(unit);
  render();
  toast(`正在执行 ${action} ${unit} ...`);
  try{
    const res = await api('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({unit,action})});
    if(!res.ok){
      toast((res.stderr||res.error||'操作失败').slice(-600), true);
      pendingUnits.delete(unit);
      render();
      return;
    }
    toast(`${unit} ${action} 已提交`);
    setTimeout(()=>refreshUnits(false).catch(e=>toast('刷新失败: '+e.message,true)).finally(()=>{pendingUnits.delete(unit); render();}), 350);
  }catch(e){
    pendingUnits.delete(unit);
    render();
    toast(e.message || '操作失败', true);
  }
}

async function bootAct(unit, action){
  const text = action === 'enable'
    ? `确认让 ${unit} 开机自动启动？\n这不会立刻启动当前服务。`
    : `确认取消 ${unit} 开机自动启动？\n这不会立刻停止当前服务。`;
  if(!confirm(text)) return;
  pendingUnits.add(unit);
  render();
  toast(`正在${action === 'enable' ? '开启' : '关闭'} ${unit} 的开机自启 ...`);
  try{
    const res = await api('/api/boot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({unit,action})});
    if(!res.ok){
      toast((res.stderr||res.error||'自启操作失败').slice(-600), true);
      pendingUnits.delete(unit);
      render();
      return;
    }
    const u = findUnit(unit);
    if(u && res.unit_file_state){ u.unit_file_state = res.unit_file_state; u.boot_action = action === 'enable' ? 'disable' : 'enable'; }
    sortUnitsLocal();
    render();
    toast(`${unit} 自启状态已更新`);
    setTimeout(()=>refreshUnits(false).catch(e=>toast('刷新失败: '+e.message,true)).finally(()=>{pendingUnits.delete(unit); render();}), 250);
  }catch(e){
    pendingUnits.delete(unit);
    render();
    toast(e.message || '自启操作失败', true);
  }
}

async function toggleFavorite(unit){
  const u = findUnit(unit);
  const old = u ? u.favorite : false;
  if(u){ u.favorite = !old; render(); }
  try{
    const res=await api('/api/metadata',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'toggle_favorite',unit})});
    if(!res.ok) throw new Error(res.error||'收藏失败');
    if(u && typeof res.favorite === 'boolean') u.favorite = res.favorite;
    render();
  }catch(e){
    if(u){ u.favorite = old; render(); }
    toast(e.message||'收藏失败', true);
  }
}

async function editNote(unit, oldNote){
  const u = findUnit(unit);
  const prevNote = u ? (u.note||'') : (oldNote||'');
  const prevDisplay = u ? u.display_unit : undefined;
  const note = prompt(`给 ${unit} 添加备注，留空则清除：`, prevNote);
  if(note === null) return;
  if(u){ u.note = note.trim(); u.display_unit = displayName(u); render(); }
  try{
    const res=await api('/api/metadata',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'note',unit,note})});
    if(!res.ok) throw new Error(res.error||'备注保存失败');
    toast(note.trim() ? '备注已保存' : '备注已清除');
  }catch(e){
    if(u){ u.note = prevNote; u.display_unit = prevDisplay; render(); }
    toast(e.message||'备注保存失败', true);
  }
}

async function showStatus(unit){
  const res=await api(`/api/status?unit=${encodeURIComponent(unit)}`);
  $('modal-title').textContent=`状态: ${unit}`; $('modal-body').textContent=res.text||res.error; $('modal').showModal();
}
async function showLogs(unit){
  const res=await api(`/api/logs?unit=${encodeURIComponent(unit)}&lines=160`);
  $('modal-title').textContent=`日志: ${unit}`; $('modal-body').textContent=res.text||res.error; $('modal').showModal();
}

$('refresh').onclick=()=>refresh(false);
$('sort').onchange=()=>{sortUnitsLocal(); render();};
$('type').onchange=()=>refresh();
$('stateFilter').onchange=()=>{stateFilter=$('stateFilter').value; localStorage.tspStateFilter=stateFilter; render();};
$('bootFilter').onchange=()=>{bootFilter=$('bootFilter').value; localStorage.tspBootFilter=bootFilter; render();};
$('zoneFilter').onchange=()=>{zoneFilter=$('zoneFilter').value; localStorage.tspZoneFilter=zoneFilter; render();};
document.querySelectorAll('[data-scope]').forEach(el=>{el.onchange=()=>{ if(el.checked) searchScopes.add(el.dataset.scope); else searchScopes.delete(el.dataset.scope); saveSearchScopes(); render(); };});
$('filter').oninput=render;
$('dir').onclick=()=>{direction=direction==='desc'?'asc':'desc'; localStorage.tspDirection=direction; sortUnitsLocal(); render();};
$('hideNoisy').onclick=()=>{hideNoisy=!hideNoisy; localStorage.tspHideNoisy=hideNoisy?'1':'0'; render();};
$('favoritesOnly').onclick=()=>{favoritesOnly=!favoritesOnly; localStorage.tspFavoritesOnly=favoritesOnly?'1':'0'; render();};
$('problemFirst').onclick=()=>{problemFirst=!problemFirst; localStorage.tspProblemFirst=problemFirst?'1':'0'; render();};


$('rebootBtn').onclick=async()=>{
  const host = $('host').textContent || 'server';
  if(!confirm(`确认重启服务器 ${host}？\n面板会短暂断开，SSH/网站也可能中断。`)) return;
  const typed = prompt('请输入 REBOOT 确认重启服务器：');
  if(typed !== 'REBOOT') { toast('已取消重启'); return; }
  try{
    toast('已发送重启请求，服务器即将断开...');
    await api('/api/system/reboot',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  }catch(e){
    toast(e.message || '重启请求失败', true);
  }
};

$('loginForm').onsubmit=async e=>{
  e.preventDefault();
  $('loginError').hidden = true;
  const password = $('loginPassword').value;
  const remember = $('rememberDevice').checked;
  try{
    const res = await api('/api/auth/login',{skipAuth:true,method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password,remember})});
    if(!res.ok) throw new Error(res.error||'登录失败');
    $('loginPassword').value = '';
    showApp(true);
    await refresh();
  }catch(err){
    $('loginError').textContent = err.message || '登录失败';
    $('loginError').hidden = false;
  }
};

$('logout').onclick=async()=>{
  await api('/api/auth/logout',{skipAuth:true,method:'POST'}).catch(()=>{});
  allUnits = [];
  showLogin('已退出登录');
};

async function init(){
  try{
    const auth = await api('/api/auth/status',{skipAuth:true});
    if(auth.enabled && !auth.authenticated){
      showLogin();
      return;
    }
    showApp(!!auth.enabled);
    await refresh();
  }catch(e){
    showApp(false);
    toast('初始化失败: '+e.message, true);
  }
}
init();
