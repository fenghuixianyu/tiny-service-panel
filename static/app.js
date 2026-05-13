let direction = localStorage.tspDirection || 'desc';
let allUnits = [];
let hideNoisy = localStorage.tspHideNoisy !== '0';
let favoritesOnly = localStorage.tspFavoritesOnly === '1';
let stateFilter = localStorage.tspStateFilter || 'all';
const $ = id => document.getElementById(id);

function mb(n){ return `${Number(n||0).toFixed(1)} MB`; }
function esc(s){ return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
async function api(url,opts){ const r=await fetch(url,opts); if(!r.ok) throw new Error(await r.text()); return r.json(); }
function stateClass(u){ if(u.active==='active') return 'active'; if(u.active==='failed'||u.sub==='failed') return 'failed'; if(u.active==='activating') return 'warn'; return 'inactive'; }
function primaryAction(u){ return u.active==='active' ? {name:'stop', label:'停止', cls:'danger'} : {name:'start', label:'启动', cls:'ok'}; }
function isProblem(u){ return ['failed','activating','deactivating','reloading'].includes(u.active) || ['failed','auto-restart'].includes(u.sub); }
function matchesState(u){
  if(stateFilter==='active') return u.active==='active';
  if(stateFilter==='inactive') return u.active==='inactive';
  if(stateFilter==='problem') return isProblem(u);
  return true;
}
function displayName(u){ return u.note ? `${u.unit}（${u.note}）` : u.unit; }
function findUnit(unit){ return allUnits.find(u=>u.unit===unit); }
function toast(msg, bad=false){ const t=$('toast'); t.textContent=msg; t.className='toast '+(bad?'bad':''); t.hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>t.hidden=true,4200); }
function unitArg(s){ return esc(String(s)).replace(/'/g,'&#39;'); }

async function loadSummary(){
  const s = await api('/api/summary');
  $('host').textContent = s.hostname;
  $('mem').textContent = `${s.memory.used_mb}/${s.memory.total_mb} MB · ${s.memory.used_percent}%`;
  $('load').textContent = s.load.join(' / ');
  $('disk').textContent = s.disk_root.use_percent || '-';
}

function filteredRows(){
  const q = $('filter').value.toLowerCase().trim();
  return allUnits.filter(u=>{
    if(hideNoisy && u.noisy && !u.favorite) return false;
    if(favoritesOnly && !u.favorite) return false;
    if(!matchesState(u)) return false;
    if(!q) return true;
    return (u.unit+' '+u.description+' '+(u.note||'')).toLowerCase().includes(q);
  });
}

function render(){
  $('hideNoisy').classList.toggle('on', hideNoisy);
  $('hideNoisy').textContent = '隐藏系统项';
  $('favoritesOnly').classList.toggle('on', favoritesOnly);
  $('stateFilter').value = stateFilter;
  $('dir').textContent = direction === 'desc' ? '降序' : '升序';
  const rows = filteredRows();
  $('units').innerHTML = rows.map(u=>{
    const p = primaryAction(u);
    return `
    <tr class="${u.favorite?'fav':''} ${u.noisy?'noisy':''}">
      <td class="unit"><div class="unit-wrap">
        <div class="unit-main"><strong>${esc(u.display_unit||displayName(u))}</strong><small>${esc(u.unit)}</small></div>
        <button class="quick ${p.cls}" onclick="act('${unitArg(u.unit)}','${p.name}')">${p.label}</button>
      </div></td>
      <td class="num memcol">${mb(u.memory_mb)}</td>
      <td><span class="state ${stateClass(u)}">${esc(u.active)}/${esc(u.sub)}</span></td>
      <td class="num">${Number(u.cpu_percent||0).toFixed(1)}%</td>
      <td class="num">${u.process_count||0}</td>
      <td class="desc">${esc(u.description||'')}</td>
      <td><div class="actions">
        <button class="ok" onclick="act('${unitArg(u.unit)}','start')">启动</button>
        <button onclick="act('${unitArg(u.unit)}','restart')">重启</button>
        <button class="danger" onclick="act('${unitArg(u.unit)}','stop')">停止</button>
        <button class="star action-star ${u.favorite?'on':''}" onclick="toggleFavorite('${unitArg(u.unit)}')" title="收藏">${u.favorite?'★':'☆'}</button>
        <button onclick="editNote('${unitArg(u.unit)}','${esc(u.note||'')}')">备注</button>
        <button onclick="showStatus('${unitArg(u.unit)}')">状态</button>
        <button onclick="showLogs('${unitArg(u.unit)}')">日志</button>
      </div></td>
    </tr>`;
  }).join('') || '<tr><td colspan="7" class="empty">没有匹配的服务</td></tr>';
}

async function refresh(showLoading=true){
  if(showLoading) $('units').innerHTML='<tr><td colspan="7" class="empty">加载中...</td></tr>';
  await loadSummary().catch(e=>toast('仪表盘加载失败: '+e.message, true));
  const sort=$('sort').value, type=$('type').value;
  const data=await api(`/api/units?sort=${encodeURIComponent(sort)}&dir=${direction}&type=${encodeURIComponent(type)}`);
  allUnits=data.units;
  render();
}

async function act(unit, action){
  if(!confirm(`${action} ${unit}?`)) return;
  toast(`正在执行 ${action} ${unit} ...`);
  const res = await api('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({unit,action})});
  if(!res.ok){
    toast((res.stderr||res.error||'操作失败').slice(-600), true);
  }else{
    toast(`${unit} ${action} 已提交`);
  }
  setTimeout(()=>refresh(false).catch(e=>toast('刷新失败: '+e.message,true)), 900);
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
$('sort').onchange=()=>refresh(false);
$('type').onchange=()=>refresh();
$('stateFilter').onchange=()=>{stateFilter=$('stateFilter').value; localStorage.tspStateFilter=stateFilter; render();};
$('filter').oninput=render;
$('dir').onclick=()=>{direction=direction==='desc'?'asc':'desc'; localStorage.tspDirection=direction; refresh(false);};
$('hideNoisy').onclick=()=>{hideNoisy=!hideNoisy; localStorage.tspHideNoisy=hideNoisy?'1':'0'; render();};
$('favoritesOnly').onclick=()=>{favoritesOnly=!favoritesOnly; localStorage.tspFavoritesOnly=favoritesOnly?'1':'0'; render();};
refresh();
