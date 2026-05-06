// ─── STATE ────────────────────────────────────────────────
let latestOrders = [], eventTotals = [];
let currentRole = 'member', currentUser = '';
let activeStatusFilter = null;
let accordionOpenKeys = new Set();

const SOURCES = [
  { key: 'monitor_liveticketgroup',   label: 'LiveTicketGroup',   icon: '🎟️', desc: 'Automatic new order monitoring',  type: 'Auto'   },
  { key: 'monitor_ticketshop',        label: 'Ticketshop',        icon: '🛒', desc: 'Manual verification only',        type: 'Manual' },
  { key: 'monitor_footballticketnet', label: 'FootballTicketNet', icon: '⚽', desc: 'FTN delivery order scraper',      type: 'Auto'   },
  { key: 'monitor_fanpass',           label: 'Fanpass',           icon: '🎫', desc: 'Fanpass order monitoring',        type: 'Auto'   },
  { key: 'monitor_tixstock',          label: 'Tixstock',          icon: '📦', desc: 'Tixstock order monitoring',       type: 'Auto'   },
];

// ─── UTILS ────────────────────────────────────────────────
function esc(v) { return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function showToast(msg) {
  const c = document.getElementById('toastContainer'); if (!c) return;
  const t = document.createElement('div'); t.className='toast show'; t.textContent=msg; c.appendChild(t);
  setTimeout(()=>{t.classList.remove('show');setTimeout(()=>t.remove(),300);},3500);
}
async function api(path,opts={}) {
  try {
    const res = await fetch(path,{headers:{'Content-Type':'application/json'},...opts});
    if (res.status===401){location.href='/login';throw new Error('Unauthorized');}
    const data = await res.json();
    if (!res.ok) throw new Error(data.error||'Request failed');
    return data;
  } catch(e) { throw e; }
}
function setText(id,val){const el=document.getElementById(id);if(el)el.textContent=val;}

// ─── NAVIGATION ───────────────────────────────────────────
const PAGE_META = {
  dashboardPage:  {title:'Dashboard',   sub:'Live order monitoring across all platforms'},
  ordersPage:     {title:'Orders',      sub:'All orders grouped by event and source'},
  pastEventsPage: {title:'Past Events', sub:'Historical data for completed events'},
  sourcesPage:    {title:'Sources',     sub:'Platform monitoring controls'},
  settingsPage:   {title:'Settings',    sub:'Configure bot behaviour and users'},
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
    await api(`/api/${chk.checked?'start':'stop'}`, {method:'POST'});
    showToast(`Monitoring ${chk.checked?'started':'stopped'} ✅`);
    await refresh();
  } catch(e) { chk.checked=!chk.checked; showToast('Error: '+e.message); }
}
async function triggerCheckNow() {
  const btn = document.getElementById('btnCheckNow'); if(!btn) return;
  btn.textContent='↻ Checking…'; btn.disabled=true;
  try { 
    await api('/api/sync/live-ticket-group',{method:'POST'}); 
    showToast('Check completed successfully ✅'); 
    await fullRefresh(); 
  }
  catch(e){ 
    showToast('Error syncing LTG: '+e.message); 
    console.error("Check Now Error:", e);
  }
  finally{ btn.textContent='↻ Check Now'; btn.disabled=false; }
}

// ─── PLATFORM TOGGLES ─────────────────────────────────────
async function toggleSourceClick(key) {
  const track=document.getElementById('toggle-'+key);
  if(!track) return;
  const isOn = track.dataset.on==='true';
  const newOn = !isOn;
  try {
    await api('/api/platform-states',{method:'POST',body:JSON.stringify({[key]:newOn})});
    showToast(`${key.replace('monitor_','')} updated ✅`);
    await refresh();
  } catch(e) { showToast('Error: '+e.message); }
}
function renderSourcesTable(settings) {
  const body=document.getElementById('sourcesTableBody'); if(!body) return;
  body.innerHTML=SOURCES.map(src=>{
    const on = settings[src.key]!==false;
    return `<tr>
      <td><div class="source-cell" style="display:flex;gap:12px;align-items:center;">
        <div class="source-icon" style="background:${on?'#dbeafe':'#f3f4f6'};width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;">${src.icon}</div>
        <div><div style="font-weight:700;">${esc(src.label)}</div><div style="font-size:12px;color:var(--muted);">${esc(src.desc)}</div></div>
      </div></td>
      <td class="cell-muted">${esc(src.desc)}</td>
      <td><span class="badge badge-${src.type==='Auto'?'blue':'gray'}">${src.type}</span></td>
      <td>
        <label class="toggle">
          <input type="checkbox" ${on?'checked':''} onchange="toggleSourceClick('${src.key}')" id="toggle-${src.key}" data-on="${on}">
          <span class="toggle-slider"></span>
        </label>
      </td>
    </tr>`;
  }).join('');
}

// ─── EVENT TOTALS ─────────────────────────────────────────
async function refreshEventTotals() {
  try { 
    eventTotals = await api('/api/events/active'); 
    renderActiveEvents(eventTotals); 
  }
  catch(e){ 
    console.error('Failed to fetch active events:', e); 
    const body=document.getElementById('activeEventsBody'); 
    if(body) body.innerHTML=`<tr><td colspan="6"><div class="empty-state" style="color:red">Error loading events: ${esc(e.message)}</div></td></tr>`;
  }
}
function renderActiveEvents(totals) {
  const body=document.getElementById('activeEventsBody'); if(!body) return;
  const q=(document.getElementById('eventSearch')?.value||'').toLowerCase();
  const filtered = q ? totals.filter(t=>(t.event_name||'').toLowerCase().includes(q)) : totals;
  if(!filtered.length){ body.innerHTML=`<tr><td colspan="6"><div class="empty-state">No active events found</div></td></tr>`; return; }
  body.innerHTML=filtered.map(t=>`<tr style="cursor:pointer" onclick='openOrdersForEvent(${JSON.stringify(t.event_name)},${JSON.stringify(t.platform)})'>
    <td><strong>${esc(t.event_name)}</strong></td>
    <td>${esc(t.platform)}</td>
    <td>${t.order_count||0}</td>
    <td>${t.ticket_count||0}</td>
    <td>${t.currency||'£'}${Number(t.total_value||0).toFixed(2)}</td>
    <td><span class="badge badge-green">Healthy</span></td>
  </tr>`).join('');
}
function openOrdersForEvent(ev,src) {
  activeStatusFilter=null;
  switchPage('ordersPage',document.querySelector('.nav-item[data-page="ordersPage"]'));
  setTimeout(()=>{ accordionOpenKeys.add(`${ev}|||${src}`); renderAccordionWithFilter(latestOrders,null); },100);
}

// ─── ORDERS ACCORDION ─────────────────────────────────────
function filterOrdersByStatus(status) {
  activeStatusFilter=status;
  switchPage('ordersPage',document.querySelector('.nav-item[data-page="ordersPage"]'));
  setTimeout(()=>renderAccordionWithFilter(latestOrders,status),100);
}
function clearOrdersFilter() { activeStatusFilter=null; renderAccordionWithFilter(latestOrders,null); }
function renderAccordionWithFilter(orders, statusFilter) {
  const badge = document.getElementById('ordersFilterBadge');
  const label = document.getElementById('ordersFilterLabel');
  if (badge && label) {
    if (statusFilter) { badge.style.display = 'flex'; label.textContent = statusFilter; label.className = `badge badge-${statusBadgeClass(statusFilter)}`; }
    else { badge.style.display = 'none'; }
  }
  const filtered = statusFilter ? orders.filter(r => {
    const s = (r.normalized_status || '').toLowerCase();
    if (statusFilter.toLowerCase() === 'resold') return s === 'resold' || s === 'presold';
    return s === statusFilter.toLowerCase();
  }) : orders;
  renderAccordion(filtered);
}
function statusBadgeClass(s){
  s=(s||'').toLowerCase();
  if(s==='cancelled') return 'red';
  if(s==='resold') return 'orange';
  if(s==='completed') return 'green';
  return 'blue';
}
function groupByEventSource(orders) {
  const map={};
  for(const r of orders){
    const ev = r.event_name || '-';
    const k=`${ev}|||${r.platform}`;
    if(!map[k]) map[k]={event:ev,source:r.platform,event_date:r.event_date||'-',orders:[]};
    map[k].orders.push(r);
  }
  return Object.values(map).sort((a,b)=>b.orders.length-a.orders.length);
}
function renderAccordion(orders) {
  const container=document.getElementById('ordersAccordion'); if(!container) return;
  const groups=groupByEventSource(orders);
  if(!groups.length){ container.innerHTML=`<div class="empty-state">No Orders</div>`; return; }
  container.innerHTML=groups.map(g=>{
    const k=`${g.event}|||${g.source}`;
    const isOpen=accordionOpenKeys.has(k);
    return `<div class="accordion-item ${isOpen?'open':''}" data-key="${esc(k)}">
      <div class="accordion-head" onclick="toggleAccordionItem(this.parentElement)">
        <div><div class="accordion-event-name">${esc(g.event)}</div><div class="accordion-meta">${esc(g.source)} · ${g.orders.length} orders · ${esc(g.event_date)}</div></div>
        <span class="accordion-chevron">▼</span>
      </div>
      <div class="accordion-body">
        <div class="table-wrap"><table>
          <thead><tr><th>ID</th><th>Customer</th><th>Qty</th><th>Price</th><th>Status</th></tr></thead>
          <tbody>${g.orders.map(r=>{
            const price = (r.total_value !== null && r.total_value !== undefined) ? (r.currency || '£') + Number(r.total_value).toFixed(2) : '-';
            return `<tr>
              <td><button class="order-id-btn" onclick='openDrawer(${JSON.stringify(r.platform)},${JSON.stringify(r.order_number)},${JSON.stringify(r.event_name)})'>${esc(r.order_number)}</button></td>
              <td>${esc(r.customer_name||'-')}</td>
              <td>${esc(r.quantity||'-')}</td>
              <td>${esc(price)}</td>
              <td><span class="badge ${statusBadgeClass(r.normalized_status)}">${esc(r.normalized_status||'Pending')}</span></td>
            </tr>`}).join('')}</tbody>
        </table></div>
      </div>
    </div>`;
  }).join('');
}
function toggleAccordionItem(el) {
  const k=el.dataset.key;
  if(el.classList.toggle('open')) accordionOpenKeys.add(k); else accordionOpenKeys.delete(k);
}

// ─── DRAWER & PAST EVENTS ──────────────────────────────────
async function openDrawer(source,orderId,eventName) {
  setText('drawerTitle',`Order #${orderId}`);
  setText('drawerSub',`${source} · ${eventName}`);
  const body = document.getElementById('drawerBody');
  body.innerHTML=`<div class="empty-state">Loading Details...</div>`;
  document.getElementById('orderDrawer').classList.remove('hidden');
  document.getElementById('drawerBackdrop').classList.remove('hidden');
  
  try {
    const res = await api(`/api/orders/${encodeURIComponent(source)}/${encodeURIComponent(orderId)}`);
    const d = res.data || {};
    
    let html = '';
    if (!res.ok && res.error) {
      html += `<div style="background:#fee2e2;color:#b91c1c;padding:12px;border-radius:8px;margin-bottom:20px;font-size:13px;border:1px solid #fecaca;">
        <strong>⚠️ Warning:</strong> ${esc(res.error)}
      </div>`;
    }
    
    html += `
      <div class="drawer-section">
        <div class="drawer-section-title">Order Summary</div>
        <div class="detail-grid">
          ${field('List Price', (d.currency||'£')+d.list_price)}
          ${field('Quantity', d.quantity)}
          ${field('Shipping', d.shipping)}
          ${field('Total Amount', (d.currency||'£')+d.total_value, true)}
        </div>
      </div>
      <div class="drawer-section" style="margin-top:24px;">
        <div class="drawer-section-title">Billing Details</div>
        <div class="detail-grid">
          ${field('Full Name', d.customer_name)}
          ${field('Mobile', d.mobile_number)}
          ${field('Email', d.email)}
        </div>
      </div>
      <div class="drawer-section" style="margin-top:24px;">
        <div class="drawer-section-title">Logistics</div>
        <div class="detail-grid">
          ${field('Status', d.normalized_status)}
          ${field('POD Status', d.pod_status)}
          ${field('Delivery', d.delivery_status)}
          ${field('Broker', d.broker_name)}
        </div>
      </div>
      <div style="margin-top:24px;padding-top:16px;border-top:1px solid var(--border);font-size:12px;color:var(--muted);">
        Source URL: <a href="${esc(d.source_url)}" target="_blank" style="color:var(--primary);text-decoration:none;">Open Platform Page ↗</a>
      </div>
    `;
    body.innerHTML = html;
  } catch(e) {
    body.innerHTML = `<div class="empty-state" style="color:#b91c1c;">Error: ${esc(e.message)}</div>`;
  }
}
function field(l,v,full=false){ 
  const val = String(v ?? '');
  if (!val || val.includes('undefined') || val.includes('null') || val === '-') return '';
  return `<div class="detail-card ${full?'full':''}"><div class="detail-label">${esc(l)}</div><div class="detail-value">${esc(v)}</div></div>`;
}
function closeDrawer(){ document.getElementById('orderDrawer').classList.add('hidden'); document.getElementById('drawerBackdrop').classList.add('hidden'); }

// ─── ORDER STATUS SEARCH ────────────────────────────────────
async function checkOrderStatus() {
  const p = document.getElementById('statusPlatformSelect').value;
  const ev = document.getElementById('statusEventInput').value;
  const resDiv = document.getElementById('statusResults');
  const body = document.getElementById('statusResultsBody');
  if (!p || !ev) { showToast("Platform and Event Name required"); return; }
  
  resDiv.classList.remove('hidden');
  body.innerHTML = `<tr><td colspan="4"><div class="empty-state">Searching...</div></td></tr>`;
  try {
    const res = await api('/api/check-order-status', {method:'POST', body:JSON.stringify({platform:p, eventName:ev})});
    if (!res.ok) throw new Error(res.error);
    if (!res.results || !res.results.length) { body.innerHTML = `<tr><td colspan="4"><div class="empty-state">No matching orders found</div></td></tr>`; return; }
    
    body.innerHTML = res.results.map(r => `<tr>
      <td><strong>${esc(r.id)}</strong></td>
      <td>${esc(r.customer || '-')}</td>
      <td>${esc(r.sale_date || '-')}</td>
      <td><span class="badge ${statusBadgeClass(r.status)}">${esc(r.status || 'Pending')}</span></td>
    </tr>`).join('');
  } catch(e) {
    body.innerHTML = `<tr><td colspan="4"><div class="empty-state" style="color:#b91c1c;">Error: ${esc(e.message)}</div></td></tr>`;
  }
}

// ─── REFRESH LOGIC ─────────────────────────────────────────
async function refresh() {
  try {
    const data = await api('/api/state');
    currentRole=data.current_role||'member'; currentUser=data.current_user||'';
    setText('sidebarUsername',currentUser); setText('sidebarRole',currentRole);
    const av=document.getElementById('avatarInitial'); if(av) av.textContent=(currentUser[0]||'A').toUpperCase();
    const running=!!data.summary?.running;
    const pill=document.getElementById('botStatusPill'); if(pill) pill.className=`status-pill ${running?'running':'stopped'}`;
    setText('botStatusText',running?'Running':'Stopped');
    const mt=document.getElementById('masterToggle'); if(mt && mt!==document.activeElement) mt.checked=running;
    renderSourcesTable(data.summary?.settings||{});
  } catch(e) { console.error('Refresh state failed', e); }

  try {
    const stats = await api('/api/dashboard/stats');
    setText('statTotal', stats.total||0); setText('statPending', stats.pending||0);
    setText('statCancelled', stats.cancelled||0); setText('statResold', stats.resold||0);
    setText('statCompleted', stats.completed||0);
  } catch(e) {
    console.error('Failed to fetch dashboard stats:', e);
    showToast('Failed to load dashboard statistics.');
    setText('statTotal', 'Error'); setText('statPending', 'Error');
    setText('statCancelled', 'Error'); setText('statResold', 'Error');
    setText('statCompleted', 'Error');
  }

  try {
    latestOrders = await api('/api/orders');
    renderAccordionWithFilter(latestOrders, activeStatusFilter);
  } catch(e) {
    console.error('Failed to fetch orders:', e);
    const container=document.getElementById('ordersAccordion'); 
    if(container) container.innerHTML=`<div class="empty-state" style="color:red">Error loading orders: ${esc(e.message)}</div>`;
  }
}

async function fullRefresh(){ await refresh(); await refreshEventTotals(); }
fullRefresh();
setInterval(fullRefresh, 8000);
window.checkOrderStatus = checkOrderStatus;
window.switchPage = switchPage;
window.toggleMasterMonitoring = toggleMasterMonitoring;
window.triggerCheckNow = triggerCheckNow;
window.filterOrdersByStatus = filterOrdersByStatus;
window.clearOrdersFilter = clearOrdersFilter;
window.openDrawer = openDrawer;
window.closeDrawer = closeDrawer;
window.toggleAccordionItem = toggleAccordionItem;
window.toggleSourceClick = toggleSourceClick;

async function checkTicketsshopOrders() {
  const btn = document.getElementById('btnTicketsshop');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" style="display:inline-block;width:12px;height:12px;border:2px solid #fff;border-radius:50%;border-top-color:transparent;animation:spin 1s linear infinite;margin-right:6px;"></span> Checking...';
  }
  showToast("Ticketshop scan started. This may take a few minutes...");
  
  try {
    const res = await api('/api/system/check-ticketsshop', { method: 'POST' });
    if (res.ok) {
      if (res.message) {
        showToast(`✅ ${res.message}`);
      } else {
        const msg = `Scan complete! Listed: ${res.listed}, Missing: ${res.missing}`;
        showToast(msg);
        if (res.missing > 0) {
          showToast(`⚠️ Alert sent to Telegram for ${res.missing} missing orders.`);
        }
      }
    } else {
      showToast(`❌ Error: ${res.error || 'Failed to check Ticketshop'}`);
    }
  } catch(e) {
    showToast(`❌ Exception: ${e.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = 'Check Listings';
    }
  }
}
window.checkTicketsshopOrders = checkTicketsshopOrders;
