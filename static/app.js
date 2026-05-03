// ─── STATE ────────────────────────────────────────────────
let latestOrders = [], eventTotals = [];
let currentRole = 'member', currentUser = '';
let manualResultGroups = null;
let activeStatusFilter = null;   // persists across refreshes
let accordionOpenKeys = new Set(); // which accordions are open

const SOURCES = [
  { key: 'monitor_liveticketgroup',   label: 'LiveTicketGroup',   icon: '🎟️', desc: 'Automatic new order monitoring',  type: 'Auto'   },
  { key: 'monitor_ticketshop',        label: 'Ticketshop',        icon: '🛒', desc: 'Manual verification only',        type: 'Manual' },
  { key: 'monitor_footballticketnet', label: 'FootballTicketNet', icon: '⚽', desc: 'FTN delivery order scraper',      type: 'Auto'   },
  { key: 'monitor_fanpass',           label: 'Fanpass',           icon: '🎫', desc: 'Fanpass order monitoring',        type: 'Auto'   },
  { key: 'monitor_tixstock',          label: 'Tixstock',          icon: '📦', desc: 'Tixstock order monitoring',       type: 'Auto'   },
];

// ─── UTILS ────────────────────────────────────────────────
function esc(v) {
  return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function parseDate(s) {
  if (!s) return null;
  const m = String(s).match(/^(\d{2})-(\d{2})-(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (!m) return null;
  return new Date(+m[3],+m[2]-1,+m[1],+m[4],+m[5],+(m[6]||0));
}
function showToast(msg) {
  const c = document.getElementById('toastContainer'); if (!c) return;
  const t = document.createElement('div'); t.className='toast'; t.textContent=msg; c.appendChild(t);
  requestAnimationFrame(()=>t.classList.add('show'));
  setTimeout(()=>{t.classList.remove('show');setTimeout(()=>t.remove(),300);},3500);
}
async function api(path,opts={}) {
  const res = await fetch(path,{headers:{'Content-Type':'application/json'},...opts});
  if (res.status===401){location.href='/login';throw new Error('Unauthorized');}
  const data = await res.json();
  if (!res.ok) throw new Error(data.error||'Request failed');
  return data;
}
function setText(id,val){const el=document.getElementById(id);if(el)el.textContent=val;}

// ─── NAVIGATION ───────────────────────────────────────────
const PAGE_META = {
  dashboardPage: {title:'Dashboard',  sub:'Live order monitoring across all platforms'},
  ordersPage:    {title:'Orders',     sub:'All orders grouped by event and source'},
  sourcesPage:   {title:'Sources',    sub:'Platform monitoring controls'},
  settingsPage:  {title:'Settings',   sub:'Configure bot behaviour and users'},
};
function switchPage(pageId, navEl) {
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  const pg = document.getElementById(pageId); if(pg) pg.classList.add('active');
  if(navEl) navEl.classList.add('active');
  const meta = PAGE_META[pageId]||{};
  setText('topbarTitle', meta.title||'');
  setText('topbarSub',   meta.sub||'');
}

// ─── BOT CONTROLS ─────────────────────────────────────────
async function toggleMasterMonitoring() {
  const chk = document.getElementById('masterToggle');
  try {
    if(chk.checked) await api('/api/start',{method:'POST'});
    else            await api('/api/stop', {method:'POST'});
    await refresh();
  } catch(e) { chk.checked=!chk.checked; showToast('Error: '+e.message); }
}
async function triggerCheckNow() {
  const btn = document.getElementById('btnCheckNow'); if(!btn) return;
  btn.textContent='↻ Checking…'; btn.disabled=true;
  try { await api('/api/check-now',{method:'POST'}); showToast('Check triggered ✅'); setTimeout(fullRefresh,2500); }
  catch(e){ showToast('Error: '+e.message); }
  finally{ btn.textContent='↻ Check Now'; btn.disabled=false; }
}

// ─── PLATFORM TOGGLES ─────────────────────────────────────
async function toggleSourceClick(key) {
  const track=document.getElementById('toggle-'+key);
  const knob =document.getElementById('knob-'+key);
  if(!track||!knob) return;
  const isOn = track.dataset.on==='true';
  const newOn = !isOn;
  track.style.background = newOn?'#2563eb':'#6b7280';
  knob.style.left         = newOn?'22px':'2px';
  track.dataset.on = String(newOn);
  try {
    await api('/api/platform-states',{method:'POST',body:JSON.stringify({[key]:newOn})});
    showToast(key.replace('monitor_','').replace(/_/g,' ')+(newOn?' enabled ✅':' disabled'));
  } catch(e) {
    track.style.background = newOn?'#6b7280':'#2563eb';
    knob.style.left         = newOn?'2px':'22px';
    track.dataset.on = String(isOn);
    showToast('Error: '+e.message);
  }
}
function renderSourcesTable(settings) {
  const body=document.getElementById('sourcesTableBody'); if(!body) return;
  body.innerHTML=SOURCES.map(src=>{
    const on = settings[src.key]!==false;
    return `<tr>
      <td><div class="source-cell">
        <div class="source-icon" style="background:${on?'#dbeafe':'#f3f4f6'}">${src.icon}</div>
        <div><div class="source-name">${esc(src.label)}</div><div class="source-desc">${esc(src.desc)}</div></div>
      </div></td>
      <td class="cell-muted">${esc(src.desc)}</td>
      <td><span class="badge badge-${src.type==='Auto'?'blue':'gray'}">${src.type}</span></td>
      <td><div onclick="toggleSourceClick('${src.key}')" id="toggle-${src.key}" data-on="${on}"
        style="position:relative;display:inline-block;width:44px;height:24px;border-radius:24px;
          background:${on?'#2563eb':'#6b7280'};cursor:pointer;transition:background 0.2s;border:1px solid rgba(0,0,0,0.1);">
        <div id="knob-${src.key}" style="position:absolute;width:18px;height:18px;background:#fff;border-radius:50%;
          top:2px;left:${on?'22px':'2px'};transition:left 0.2s;box-shadow:0 1px 4px rgba(0,0,0,0.35);"></div>
      </div></td>
    </tr>`;
  }).join('');
}

// ─── SETTINGS ─────────────────────────────────────────────
async function toggleSetting(name) {
  try { await api('/api/toggle-setting',{method:'POST',body:JSON.stringify({name})}); await refresh(); }
  catch(e){ showToast('Error: '+e.message); }
}
async function saveIntervalSettings() {
  const v=document.getElementById('settingsInterval')?.value; if(!v) return;
  try { await api('/api/settings',{method:'POST',body:JSON.stringify({interval_minutes:v})}); showToast('Settings saved ✅'); }
  catch(e){ showToast('Error: '+e.message); }
}

// ─── EVENT TOTALS ─────────────────────────────────────────
async function refreshEventTotals() {
  try { const res=await api('/api/event-totals'); eventTotals=res.totals||[]; renderActiveEvents(eventTotals); }
  catch(e){ console.warn('event-totals',e); }
}
function renderActiveEvents(totals) {
  const body=document.getElementById('activeEventsBody'); if(!body) return;
  const q=(document.getElementById('eventSearch')?.value||'').toLowerCase();
  const filtered=q?totals.filter(t=>(t.event||'').toLowerCase().includes(q)||(t.source||'').toLowerCase().includes(q)):totals;
  if(!filtered.length){
    body.innerHTML=`<tr><td colspan="6"><div class="empty-state"><div class="empty-icon">📭</div><div>No events found</div></div></td></tr>`;
    return;
  }
  body.innerHTML=filtered.map(t=>`<tr style="cursor:pointer"
    onclick="openOrdersForEvent(${JSON.stringify(t.event)},${JSON.stringify(t.source)})">
    <td><strong>${esc(t.event)}</strong></td>
    <td>${esc(t.source)}</td>
    <td>${t.orders_count||0}</td>
    <td>${t.total_quantity||0}</td>
    <td>£${Number(t.total_price||0).toFixed(2)}</td>
    <td><span class="badge ${t.needs_attention?'badge-red':'badge-green'}">${t.needs_attention?'Attention':'Healthy'}</span></td>
  </tr>`).join('');
}
function filterEvents(){ renderActiveEvents(eventTotals); }
function openOrdersForEvent(ev,src) {
  activeStatusFilter=null;
  switchPage('ordersPage',document.querySelector('.nav-item[data-page="ordersPage"]'));
  setTimeout(()=>{ accordionOpenKeys.add(`${ev}|||${src}`); renderAccordionWithFilter(latestOrders,null); },100);
}

// ─── STAT CARD FILTER ─────────────────────────────────────
function filterOrdersByStatus(status) {
  activeStatusFilter=status;
  switchPage('ordersPage',document.querySelector('.nav-item[data-page="ordersPage"]'));
  setTimeout(()=>renderAccordionWithFilter(latestOrders,status),100);
}
function clearOrdersFilter() {
  activeStatusFilter=null;
  renderAccordionWithFilter(latestOrders,null);
}
function renderAccordionWithFilter(orders, statusFilter) {
  // Update filter badge
  const badge = document.getElementById('ordersFilterBadge');
  const label = document.getElementById('ordersFilterLabel');
  if (badge && label) {
    if (statusFilter) {
      badge.style.display = 'flex';
      label.textContent = statusFilter;
      label.className = `badge badge-${statusBadgeClass(statusFilter)}`;
    } else {
      badge.style.display = 'none';
    }
  }

  const filtered = statusFilter
    ? orders.filter(r => {
        const s = (r.dashboard_status || '').toLowerCase();
        return s === statusFilter.toLowerCase();
      })
    : orders;

  renderAccordion(filtered);
}
function statusBadgeClass(s){
  if(s==='cancelled') return 'red';
  if(s==='resold')    return 'orange';
  if(s==='completed') return 'green';
  return 'blue';
}

// ─── ORDERS ACCORDION ─────────────────────────────────────
function groupByEventSource(orders) {
  const map={};
  for(const r of orders){
    const k=`${r.event}|||${r.source}`;
    if(!map[k]) map[k]={event:r.event,source:r.source,event_date:r.event_date||'-',orders:[]};
    map[k].orders.push(r);
  }
  return Object.values(map).sort((a,b)=>b.orders.length-a.orders.length);
}

function renderAccordion(orders) {
  const container=document.getElementById('ordersAccordion'); if(!container) return;
  const groups=groupByEventSource(orders);
  if(!groups.length){
    container.innerHTML=`<div class="empty-state"><div class="empty-icon">🗂️</div><div class="empty-title">No Orders</div><div class="empty-sub">No orders match current filter</div></div>`;
    return;
  }
  container.innerHTML=groups.map(g=>{
    const k=`${g.event}|||${g.source}`;
    const isOpen=accordionOpenKeys.has(k);
    const rows=g.orders.slice().sort((a,b)=>(parseDate(b.sale_date)||0)-(parseDate(a.sale_date)||0));
    return `<div class="accordion-item ${isOpen?'open':''}" data-key="${esc(k)}">
      <div class="accordion-head" onclick="toggleAccordionItem(this.parentElement)">
        <div>
          <div class="accordion-event-name">${esc(g.event)}</div>
          <div class="accordion-meta">${esc(g.source)} · ${g.orders.length} order${g.orders.length!==1?'s':''} · ${esc(g.event_date)}</div>
        </div>
        <span class="accordion-chevron">▼</span>
      </div>
      <div class="accordion-body">
        <div class="table-wrap"><table>
          <thead><tr><th>ID</th><th>Customer</th><th>Qty</th><th>Price</th><th>Sale Date</th><th>Status</th><th>Source</th></tr></thead>
          <tbody>${rows.map(r=>`<tr>
            <td><button class="order-id-btn" onclick="openDrawer(${JSON.stringify(r.source)},${JSON.stringify(r.id)},${JSON.stringify(r.event)})">${esc(r.id)}</button></td>
            <td>${esc(r.customer||'-')}</td>
            <td>${esc(r.quantity||'-')}</td>
            <td>${r.total_price?'£'+esc(r.total_price):'-'}</td>
            <td>${esc(r.sale_date||'-')}</td>
            <td><span class="badge ${statusClass(r.dashboard_status)}">${esc(r.status||'Pending')}</span></td>
            <td class="cell-muted">${esc(r.source||'-')}</td>
          </tr>`).join('')}</tbody>
        </table></div>
      </div>
    </div>`;
  }).join('');
}

function toggleAccordionItem(el) {
  const k=el.dataset.key;
  const wasOpen=el.classList.contains('open');
  el.classList.toggle('open');
  if(wasOpen) accordionOpenKeys.delete(k);
  else        accordionOpenKeys.add(k);
}

function statusClass(s){
  s=(s||'').toLowerCase();
  if(s==='cancelled') return 'badge-red';
  if(s==='resold')    return 'badge-orange';
  if(s==='completed') return 'badge-green';
  return 'badge-gray'; // Pending
}

// ─── ORDER DRAWER ─────────────────────────────────────────
async function openDrawer(source,orderId,eventName) {
  // Do NOT collapse accordion — just open the drawer
  setText('drawerTitle',`Order #${orderId}`);
  setText('drawerSub',`${source} · ${eventName}`);
  document.getElementById('drawerBody').innerHTML=`<div class="empty-state"><div class="empty-icon">⏳</div><div>Loading…</div></div>`;
  document.getElementById('orderDrawer').classList.remove('hidden');
  document.getElementById('drawerBackdrop').classList.remove('hidden');
  try {
    const res=await api(`/api/order-details/${encodeURIComponent(source)}/${encodeURIComponent(orderId)}`);
    const d=res.details||{};
    document.getElementById('drawerBody').innerHTML=`
      <div class="detail-grid">
        ${field('Platform',    source)}
        ${field('Order #',     orderId)}
        ${field('Event',       d.event_name||eventName)}
        ${field('Customer',    d.customer_name)}
        ${field('Mobile',      d.customer_phone)}
        ${field('Status',      d.status)}
        ${d.resale_status ? field('Resale Status', d.resale_status) : ''}
        ${field('Sale Date',   d.sale_date)}
        ${field('Event Date',  d.event_date)}
        ${field('Quantity',    d.quantity)}
        ${field('Price/Ticket',d.price_per_ticket?'£'+d.price_per_ticket:null)}
        ${field('Total Price', d.total_price?'£'+d.total_price:null)}
        ${field('Area',        d.area)}
        ${field('Shipping',    d.shipping)}
        ${field('Venue',       d.venue)}
        ${d.ticketshop_status ? field('Ticketshop Status', d.ticketshop_status) : ''}
      </div>
      ${d.attendees&&d.attendees.length?`
        <div class="drawer-section">
          <div class="drawer-section-title">Attendees</div>
          <div>${d.attendees.map(a=>`<span class="badge badge-gray" style="margin:2px">${esc(a)}</span>`).join('')}</div>
        </div>`:''}
    `;
  } catch(e){
    document.getElementById('drawerBody').innerHTML=`<div class="empty-state"><div class="empty-icon">❌</div><div>${esc(e.message)}</div></div>`;
  }
}
function field(label,value){
  if(value==null||value===''||value===undefined) return '';
  return `<div class="detail-card"><div class="detail-label">${esc(label)}</div><div class="detail-value">${esc(value||'—')}</div></div>`;
}
function closeDrawer(){
  document.getElementById('orderDrawer').classList.add('hidden');
  document.getElementById('drawerBackdrop').classList.add('hidden');
}

// ─── ORDER STATUS SEARCH ──────────────────────────────────
async function checkOrderStatus() {
  const platform=document.getElementById('statusPlatformSelect')?.value;
  const eventName=document.getElementById('statusEventInput')?.value?.trim();
  if(!eventName){showToast('Please enter an event name');return;}
  const btn=document.getElementById('btnCheckStatus');
  if(btn){btn.textContent='Checking…';btn.disabled=true;}
  try {
    const data=await api('/api/check-order-status',{method:'POST',body:JSON.stringify({platform,event_name:eventName})});
    const g=data.results||{};
    manualResultGroups=[
      {label:'Processed', items:g.processed||[],cls:'badge-gray'},
      {label:'Submitted', items:g.submitted||[],cls:'badge-gray'},
      {label:'Resold',    items:g.resold||[],   cls:'badge-orange'},
      {label:'Cancelled', items:g.cancelled||[],cls:'badge-red'},
    ];
    const total=manualResultGroups.reduce((s,g)=>s+g.items.length,0);
    document.getElementById('statusResultsFilters').innerHTML=
      [{label:'All',cls:''}].concat(manualResultGroups).map(g=>
        `<button class="btn btn-secondary btn-sm" onclick="filterManual('${g.label}')">${g.label} (${g.label==='All'?total:(g.items||[]).length})</button>`
      ).join('');
    document.getElementById('statusResults').classList.remove('hidden');
    filterManual('All');
    showToast(`Found ${total} order(s) ✅`);
  } catch(e){showToast('Error: '+e.message);}
  if(btn){btn.textContent='Check Status';btn.disabled=false;}
}
function filterManual(type){
  const body=document.getElementById('statusResultsBody');
  if(!body||!manualResultGroups) return;
  const groups=type==='All'?manualResultGroups:manualResultGroups.filter(g=>g.label===type);
  let html='';
  for(const g of groups) for(const r of g.items||[]){
    html+=`<tr>
      <td><button class="order-id-btn" onclick="openDrawer(${JSON.stringify(r.source||'')},${JSON.stringify(r.id||'')},${JSON.stringify(r.event||'')})">${esc(r.id||'-')}</button></td>
      <td>${esc(r.customer||'-')}</td>
      <td>${esc(r.sale_date||'-')}</td>
      <td><span class="badge ${g.cls}">${esc(r.status||g.label)}</span></td>
    </tr>`;
  }
  body.innerHTML=html||`<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:20px">No results</td></tr>`;
}

// ─── TICKETSHOP ───────────────────────────────────────────
async function checkTicketsshopOrders(){
  const btn=document.getElementById('btnTicketsshop');
  if(btn){btn.textContent='Checking…';btn.disabled=true;}
  try {
    const res=await api('/api/check-ticketsshop-listings',{method:'POST'});
    showToast(`Done ✅  Listed: ${(res.listed||[]).length}  |  Missing: ${(res.missing||[]).length}`);
  } catch(e){showToast('Error: '+e.message);}
  if(btn){btn.textContent='Check Listings';btn.disabled=false;}
}

// ─── MEMBERS ──────────────────────────────────────────────
function renderMembers(members){
  const body=document.getElementById('membersBody'); if(!body) return;
  if(!members.length){body.innerHTML=`<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:16px">No members</td></tr>`;return;}
  body.innerHTML=members.map(m=>{
    const isSelf=m.username===currentUser;
    const actions=currentRole==='admin'?`
      <div class="inline-actions">
        <button class="btn btn-secondary btn-sm" onclick="changeRole('${esc(m.username)}','${m.role==='admin'?'member':'admin'}')">${m.role==='admin'?'Make Member':'Make Admin'}</button>
        <button class="btn btn-secondary btn-sm" onclick="resetPwPrompt('${esc(m.username)}')">Reset PW</button>
        ${!isSelf?`<button class="btn btn-danger btn-sm" onclick="deleteMember('${esc(m.username)}')">Delete</button>`:''}
      </div>`:'<span class="cell-muted">View only</span>';
    return `<tr>
      <td>${esc(m.username)}</td>
      <td><span class="badge ${m.role==='admin'?'badge-red':'badge-gray'}">${esc(m.role)}</span></td>
      <td><span class="${m.is_active?'text-green':'cell-muted'}">${m.is_active?'Active':'Disabled'}</span></td>
      <td>${actions}</td>
    </tr>`;
  }).join('');
}
async function addMember(){
  const u=document.getElementById('newUsername')?.value?.trim();
  const p=document.getElementById('newPassword')?.value?.trim();
  const r=document.getElementById('newRole')?.value;
  if(!u||!p){showToast('Username and password required');return;}
  try {
    await api('/api/users/add',{method:'POST',body:JSON.stringify({username:u,password:p,role:r})});
    document.getElementById('newUsername').value='';
    document.getElementById('newPassword').value='';
    showToast(`${u} added ✅`); await refresh();
  } catch(e){showToast('Error: '+e.message);}
}
async function changeRole(u,role){
  try{await api('/api/users/change-role',{method:'POST',body:JSON.stringify({username:u,role})});await refresh();}
  catch(e){showToast(e.message);}
}
async function resetPwPrompt(u){
  const pw=prompt(`New password for ${u}:`); if(!pw) return;
  try{await api('/api/users/reset-password',{method:'POST',body:JSON.stringify({username:u,password:pw})});showToast('Password reset ✅');}
  catch(e){showToast(e.message);}
}
async function deleteMember(u){
  if(!confirm(`Delete user "${u}"?`)) return;
  try{await api('/api/users/delete',{method:'POST',body:JSON.stringify({username:u})});await refresh();}
  catch(e){showToast(e.message);}
}

// ─── MAIN REFRESH ─────────────────────────────────────────
async function refresh() {
  try {
    const data=await api('/api/state');
    currentRole=data.current_role||'member';
    currentUser=data.current_user||'';
    latestOrders=data.orders||[];

    const uname=currentUser||'User';
    setText('sidebarUsername',uname);
    setText('sidebarRole',currentRole);
    const av=document.getElementById('avatarInitial');
    if(av) av.textContent=(uname[0]||'?').toUpperCase();

    const running=!!data.summary?.running;
    const pill=document.getElementById('botStatusPill');
    if(pill) pill.className=`status-pill ${running?'running':'stopped'}`;
    setText('botStatusText',running?'Running':'Stopped');
    const mt=document.getElementById('masterToggle');
    if(mt&&mt!==document.activeElement) mt.checked=running;

    const s=data.summary||{};
    setText('statTotal',    s.order_count     ??0);
    setText('statPending',  s.pending_count   ??0);
    setText('statCancelled',s.cancelled_count ??0);
    setText('statResold',   s.resold_count    ??0);
    setText('statCompleted',s.processed_count ??0);

    const settings=s.settings||{};
    const sleepEl=document.getElementById('sleepToggle');
    if(sleepEl) sleepEl.checked=!!settings.sleep_window_enabled;
    const intEl=document.getElementById('settingsInterval');
    if(intEl&&document.activeElement!==intEl) intEl.value=settings.interval_minutes??30;

    renderSourcesTable(settings);
    renderMembers(data.members||[]);

    // Re-render orders WITHOUT resetting filter or open state
    if(activeStatusFilter!==undefined){
      renderAccordionWithFilter(latestOrders, activeStatusFilter);
    } else {
      renderAccordion(latestOrders);
    }

  } catch(e){ console.error('refresh error',e); }
}

async function fullRefresh(){
  await refresh();
  await refreshEventTotals();
}

// ─── INIT ─────────────────────────────────────────────────
fullRefresh();
setInterval(fullRefresh, 7000);
