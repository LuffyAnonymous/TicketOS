// ─── STATE ────────────────────────────────────────────────
let latestOrders = [], eventTotals = [];
let currentRole = 'viewer', currentUser = '';
let activeStatusFilter = null;
let latestCustomers = [];
let schedulerRunning = false;
let lastSyncTime = '-';

const SOURCES = [
  { key: 'monitor_liveticketgroup',   label: 'LiveTicketGroup',   icon: '🎟️', desc: 'Automatic new order monitoring',  type: 'Auto'   },
  { key: 'monitor_ticketshop',        label: 'Ticketshop',        icon: '🛒', desc: 'Manual verification only',        type: 'Manual' },
  { key: 'monitor_footballticketnet', label: 'FootballTicketNet', icon: '⚽', desc: 'FTN delivery order scraper',      type: 'Auto'   },
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
  dashboardPage:  {title:'Operations Center', sub:'Real-time logistics and broker automation console'},
  ordersPage:     {title:'Orders Workspace',  sub:'Unified workspace for order tracking and audit trails'},
  customersPage:  {title:'Customer CRM',     sub:'Operational client directory and purchase log analytics'},
  platformsPage:  {title:'Platform Health',   sub:'Manage and inspect automated adapters, cookies, and verification schedules'},
  alertsPage:     {title:'Alerts Center',    sub:'Unresolved scraper warnings, login failures, and inventory anomalies'},
  reportsPage:    {title:'Reports Deck',     sub:'Download formatted Excel summaries for accounting and logistics management'},
  settingsPage:   {title:'Configuration',    sub:'Configure bot behaviour and user members list'},
};

function switchPage(pageId, navEl) {
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  
  const pg = document.getElementById(pageId); if(pg) pg.classList.add('active');
  
  // Set sidebar selection styling
  if(!navEl) {
    navEl = document.querySelector(`.nav-item[data-page="${pageId}"]`);
  }
  if(navEl) navEl.classList.add('active');
  
  const meta = PAGE_META[pageId]||{};
  setText('topbarTitle', meta.title||'');
  setText('topbarSub',   meta.sub||'');
  
  closeDrawer();
  closeCustomerDrawer();
  
  if (pageId === 'customersPage') {
    refreshCustomersList();
  }
  if (pageId === 'platformsPage') {
    loadPlatformCards();
  }
}

// ─── BOT & SCHEDULER CONTROLS ─────────────────────────────
async function toggleMasterMonitoring() {
  const chk = document.getElementById('masterToggle');
  try {
    await api(`/api/${chk.checked?'start':'stop'}`, {method:'POST'});
    showToast(`Daemon ${chk.checked?'started':'stopped'} ✅`);
    await refresh();
  } catch(e) { chk.checked=!chk.checked; showToast('Error: '+e.message); }
}

async function triggerCheckNow() {
  const btn = document.getElementById('btnCheckNow'); if(!btn) return;
  btn.textContent='↻ Checking…'; btn.disabled=true;
  try { 
    await api('/api/sync/live-ticket-group',{method:'POST'}); 
    showToast('Sync check completed successfully ✅'); 
    await fullRefresh(); 
  }
  catch(e){ 
    showToast('Error: '+e.message); 
    console.error("Manual Check Error:", e);
  }
  finally{ btn.textContent='↻ Sync Now'; btn.disabled=false; }
}

async function triggerManualSync(platform) {
  showToast(`Initiating manual sync check for ${platform}...`);
  try {
    await api('/api/sync/live-ticket-group', { method: 'POST' });
    showToast(`Successfully synchronized ${platform} ✅`);
    await fullRefresh();
  } catch(e) {
    showToast(`Sync failed: ${e.message}`);
  }
}

// ─── OPS CENTER RENDERS ─────────────────────────────

function formatLastSync(lastSyncStr) {
  if (!lastSyncStr || lastSyncStr === '-' || lastSyncStr === 'Never') {
    return 'Last sync: Never';
  }
  const timeMatch = lastSyncStr.match(/(\d{2}):(\d{2})/);
  if (timeMatch) {
    return `Last sync: ${timeMatch[1]}:${timeMatch[2]}`;
  }
  return `Last sync: ${lastSyncStr}`;
}

async function toggleScheduler(action) {
  if (action === 'stop') {
    if (!confirm("Stop all automatic platform checks?")) {
      return;
    }
  }
  
  try {
    const res = await api(`/api/${action}`, { method: 'POST' });
    if (res.ok || res.message) {
      showToast(res.message || `Scheduler ${action}ped successfully`);
      await refresh();
    } else {
      showToast(`Error: ${res.error || 'Failed to update scheduler'}`);
    }
  } catch (e) {
    showToast(`Error: ${e.message}`);
  }
}

function renderOpsHealth(health, state) {
  const grid = document.getElementById('opsHealthGrid');
  if (!grid) return;

  function pill(name, statusKey, sub) {
    let mod, dot, label;
    switch (statusKey) {
      case 'running':     mod='ok';    dot='green';  label='Running';     break;
      case 'connected':   mod='ok';    dot='green';  label='Connected';   break;
      case 'disabled':    mod='off';   dot='gray';   label='Disabled';    break;
      case 'error':       mod='error'; dot='red';    label='Error';       break;
      case 'stopped':     mod='error'; dot='red';    label='Stopped';     break;
      case 'warning':     mod='warn';  dot='orange'; label='Warning';     break;
      case 'waiting':     mod='idle';  dot='blue';   label='Standby';     break;
      case 'disconnected':mod='error'; dot='red';    label='Disconnected';break;
      case 'unavailable': mod='warn';  dot='orange'; label='Status unavailable'; break;
      default:            mod='idle';  dot='blue';   label=statusKey||'Unknown';
    }
    return `<div class="ops-service-pill ${mod}">
      <div class="ops-service-name">${esc(name)}</div>
      <div class="ops-service-status"><span class="ops-dot ${dot}"></span>${label}</div>
      <div class="ops-service-sub">${esc(sub)}</div>
    </div>`;
  }

  // Health API failed check
  const ltgStatus = (health && !health._failed) ? health.liveticketgroup : 'unavailable';
  const ftnStatus = (health && !health._failed) ? health.footballticketnet : 'unavailable';
  const tgStatus  = (health && !health._failed) ? (health.telegram === 'connected' ? 'connected' : 'disconnected') : 'unavailable';
  const invStatus = (health && !health._failed) ? (health.mismatches > 0 ? 'warning' : 'running') : 'unavailable';

  const ltgSub = (health && !health._failed) ? (health.liveticketgroup === 'running' ? 'Syncing normally' : health.liveticketgroup === 'disabled' ? 'Toggled off' : 'Check credentials') : 'Status unavailable';
  const ftnSub = (health && !health._failed) ? (health.footballticketnet === 'running' ? 'Syncing normally' : health.footballticketnet === 'disabled' ? 'Toggled off' : 'Login failed') : 'Status unavailable';
  const invSub = (health && !health._failed) ? (health.mismatches > 0 ? `${health.mismatches} order${health.mismatches!==1?'s':''} missing` : 'No issues') : 'Status unavailable';
  const tgSub  = (health && !health._failed) ? (health.telegram === 'connected' ? 'Alerts active' : 'Token missing') : 'Status unavailable';

  // Scheduler Pill rendering (State API status)
  let schMod = 'idle', schDot = 'blue', schLabel = 'Unknown';
  let schSub = 'Scheduler state unavailable';
  let btnHtml = '';
  const canControl = (currentRole === 'admin' || currentRole === 'staff');

  if (state && !state._failed) {
    const schStatus = (state.scheduler && state.scheduler.status) ? state.scheduler.status : 'Stopped';
    schLabel = schStatus;
    
    if (schStatus === 'Running') {
      schMod = 'ok';
      schDot = 'green';
      schSub = 'Automatic checks are active';
      if (canControl) {
        btnHtml = `<button class="btn btn-secondary btn-sm" style="margin-top:5px; font-size:10.5px; padding:2px 8px; width:100%;" onclick="toggleScheduler('stop')">Stop Scheduler</button>`;
      }
    } else if (schStatus === 'Stopped') {
      schMod = 'off';
      schDot = 'gray';
      schSub = 'Automatic checks are paused';
      if (canControl) {
        btnHtml = `<button class="btn btn-primary btn-sm" style="margin-top:5px; font-size:10.5px; padding:2px 8px; width:100%;" onclick="toggleScheduler('start')">Start Scheduler</button>`;
      }
    } else if (schStatus === 'Starting') {
      schMod = 'idle';
      schDot = 'blue';
      schSub = 'Scheduler is starting...';
      if (canControl) {
        btnHtml = `<button class="btn btn-secondary btn-sm" style="margin-top:5px; font-size:10.5px; padding:2px 8px; width:100%;" disabled>Starting...</button>`;
      }
    } else if (schStatus === 'Stopping') {
      schMod = 'warn';
      schDot = 'orange';
      schSub = 'Scheduler is stopping...';
      if (canControl) {
        btnHtml = `<button class="btn btn-secondary btn-sm" style="margin-top:5px; font-size:10.5px; padding:2px 8px; width:100%;" disabled>Stopping...</button>`;
      }
    } else {
      schMod = 'idle';
      schDot = 'blue';
      schSub = 'Status unknown';
    }
  } else {
    // state._failed
    schLabel = 'Unknown';
    schMod = 'idle';
    schDot = 'gray';
    schSub = 'Scheduler state unavailable';
  }

  const schedulerPill = `<div class="ops-service-pill ${schMod}">
    <div class="ops-service-name">Scheduler</div>
    <div class="ops-service-status"><span class="ops-dot ${schDot}"></span>${schLabel}</div>
    <div class="ops-service-sub">${esc(schSub)}</div>
    ${btnHtml}
  </div>`;

  grid.innerHTML = [
    pill('LiveTicketGroup',   ltgStatus,   ltgSub),
    pill('FootballTicketNet', ftnStatus,   ftnSub),
    pill('Inventory Check',   invStatus,   invSub),
    schedulerPill,
    pill('Telegram',          tgStatus,    tgSub),
    `<div class="ops-service-pill ok">
      <div class="ops-service-name">Database</div>
      <div class="ops-service-status"><span class="ops-dot green"></span>Healthy</div>
      <div class="ops-service-sub">SQLite connected</div>
    </div>`
  ].join('');
}

function renderOpsActivity(feed) {
  const container = document.getElementById('opsActivityFeed');
  if (!container) return;
  if (!feed || feed._failed) {
    container.innerHTML = `<div class="ops-feed-item"><div class="ops-feed-time">—</div><div class="ops-feed-body"><div class="ops-feed-msg" style="color:var(--red);">Activity feed unavailable</div></div></div>`;
    return;
  }
  if (!feed.length) {
    container.innerHTML = `<div class="ops-feed-item"><div class="ops-feed-time">—</div><div class="ops-feed-body"><div class="ops-feed-msg" style="color:var(--muted);">No recent events</div></div></div>`;
    return;
  }
  container.innerHTML = feed.map(item => {
    const lvl = (item.level || 'INFO').toUpperCase();
    const src = item.source ? esc(item.source) : '';
    // Truncate very long messages
    let msg = esc(item.message || '');
    if (msg.length > 120) msg = msg.slice(0, 120) + '…';
    return `<div class="ops-feed-item">
      <div class="ops-feed-time">${esc(item.time || '—')}</div>
      <div class="ops-feed-body">
        <div class="ops-feed-msg">${msg}</div>
        ${src ? `<div class="ops-feed-src">${src}</div>` : ''}
      </div>
      <div class="ops-feed-lvl ${lvl}">${lvl}</div>
    </div>`;
  }).join('');
}

function renderOpsAttention(alerts) {
  const container = document.getElementById('opsAttentionList');
  if (!container) return;
  if (!alerts || alerts._failed) {
    container.innerHTML = `<div class="ops-all-clear" style="color:var(--red); border-color:var(--red);">Unable to load alerts</div>`;
    return;
  }
  const errors = alerts.filter(a => a.severity === 'error' || a.severity === 'warning');
  // Update scraper errors badge for Alerts page count
  setText('statScraperErrors', errors.filter(a => a.severity === 'error').length);
  if (!errors.length) {
    container.innerHTML = `<div class="ops-all-clear">✓ All systems healthy</div>`;
    return;
  }
  container.innerHTML = errors.map(a => `
    <div class="ops-alert-item ${a.severity === 'warning' ? 'warn' : ''}">
      <div class="ops-alert-platform">${esc(a.platform || 'System')}</div>
      <div class="ops-alert-msg">${esc(a.message)}</div>
      <div class="ops-alert-action">${esc(a.suggested_action || '')}</div>
    </div>
  `).join('');
}

// Legacy aliases kept for any remaining references in other pages
function renderDashboardHealth(health) { renderOpsHealth(health); }
function renderDashboardActivity(feed) { renderOpsActivity(feed); }

function renderAlertsPage(alerts) {
  const container = document.getElementById('alertsListContainer');
  if (!container) return;
  if (!alerts || !alerts.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon" style="color:var(--green); opacity:0.8;">🟢</div>
        <div class="empty-title">All Systems Healthy</div>
        <div class="empty-sub">No active failures or inventory mismatches reported</div>
      </div>
    `;
    return;
  }
  container.innerHTML = alerts.map(a => `
    <div class="alert-card-item ${a.severity}">
      <div class="alert-card-header">
        <span class="alert-card-platform">🚨 ${esc(a.platform)}</span>
        <span class="alert-card-time">${esc(a.timestamp)}</span>
      </div>
      <div class="alert-card-msg">${esc(a.message)}</div>
      <div class="alert-card-action">
        <span>Suggested action: <strong>${esc(a.suggested_action)}</strong></span>
        <button class="btn btn-secondary btn-sm" onclick="showToast('Acknowledge alert')">Acknowledge</button>
      </div>
    </div>
  `).join('');
}


// ─── FILTER & RENDER ORDERS ───────────────────────────────

let currentOrdersPage = 1;
let currentOrdersPerPage = 25;
let ordersSortBy = 'id';
let ordersSortDir = 'desc';
let selectedOrder = null;

// Debounce helper
function debounce(func, wait) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

const applyOrdersFiltersDebounced = debounce(() => {
  currentOrdersPage = 1;
  refresh();
}, 400);

function filterOrdersByStatus(status) {
  activeStatusFilter = status;
  const statusEl = document.getElementById('filterStatus');
  if (statusEl) statusEl.value = status || '';
  
  // Clear other filter inputs
  const gqEl = document.getElementById('filterGlobalQuery');
  const platformEl = document.getElementById('filterPlatform');
  const startEl = document.getElementById('filterStartDate');
  const endEl = document.getElementById('filterEndDate');
  const eventEl = document.getElementById('filterEvent');
  const customerEl = document.getElementById('filterCustomer');
  
  if (gqEl) gqEl.value = '';
  if (platformEl) platformEl.value = '';
  if (startEl) startEl.value = '';
  if (endEl) endEl.value = '';
  if (eventEl) eventEl.value = '';
  if (customerEl) customerEl.value = '';
  
  currentOrdersPage = 1;
  switchPage('ordersPage', document.querySelector('.nav-item[data-page="ordersPage"]'));
  refresh();
}

function clearOrdersFilter() {
  activeStatusFilter = null;
  resetOrdersFilters();
}

function applyOrdersFilters() {
  activeStatusFilter = null;
  currentOrdersPage = 1;
  refresh();
}

function resetOrdersFilters() {
  activeStatusFilter = null;
  currentOrdersPage = 1;
  
  const gqEl = document.getElementById('filterGlobalQuery');
  const platformEl = document.getElementById('filterPlatform');
  const statusEl = document.getElementById('filterStatus');
  const startEl = document.getElementById('filterStartDate');
  const endEl = document.getElementById('filterEndDate');
  const eventEl = document.getElementById('filterEvent');
  const customerEl = document.getElementById('filterCustomer');
  
  if (gqEl) gqEl.value = '';
  if (platformEl) platformEl.value = '';
  if (statusEl) statusEl.value = '';
  if (startEl) startEl.value = '';
  if (endEl) endEl.value = '';
  if (eventEl) eventEl.value = '';
  if (customerEl) customerEl.value = '';
  
  refresh();
}

function refreshOrdersTable() {
  refresh();
}

function formatStatusWithIcon(s) {
  s = (s || '').toLowerCase();
  const label = s.charAt(0).toUpperCase() + s.slice(1);
  if (s === 'completed') return `<span class="badge badge-green">🟢 ${label}</span>`;
  if (s === 'cancelled') return `<span class="badge badge-red">🔴 ${label}</span>`;
  if (s === 'resold') return `<span class="badge badge-orange">♻️ ${label}</span>`;
  return `<span class="badge badge-blue">⏳ ${label}</span>`; // pending
}

function formatTimelineMessage(msg) {
  if (!msg) return '';
  const msgLower = msg.toLowerCase();
  
  // Status changes
  const statusMatch = msg.match(/status updated from (.*?) to (.*?) by (.*)/i);
  if (statusMatch) {
    return `🔄 Status changed: <strong>${esc(statusMatch[1])}</strong> ➔ <strong>${esc(statusMatch[2])}</strong> by <strong>${esc(statusMatch[3])}</strong>`;
  }
  
  // New order
  if (msgLower.includes('new order detected') || msgLower.includes('new order synced')) {
    return `📥 New order detected & imported to database`;
  }
  
  // Telegram alerts
  if (msgLower.includes('sent alert to telegram') || msgLower.includes('telegram notification')) {
    return `✈️ Telegram alert sent to operations channel`;
  }
  
  // Sync runs
  if (msgLower.includes('sync triggered') || msgLower.includes('sync started')) {
    return `⚡ Platform synchronization started`;
  }
  
  if (msgLower.includes('sync completed') || msgLower.includes('sync finished')) {
    return `✓ Platform synchronization completed`;
  }
  
  // Default clean fallback
  return esc(msg);
}

function renderOrdersWorkspaceTable(orders) {
  const body = document.getElementById('ordersWorkspaceTableBody');
  if (!body) return;
  if (!orders.length) {
    body.innerHTML = `<tr><td colspan="10"><div class="empty-state">No matching orders found</div></td></tr>`;
    return;
  }
  
  body.innerHTML = orders.map(o => {
    const cost = (o.list_price_per_ticket || 0) * (o.quantity || 1) + (o.shipping_amount || 0);
    const payout = o.total_value || 0;
    const profit = payout - cost;
    const profitText = (o.currency || '£') + Number(o.profit || profit || 0).toFixed(2);
    const profitStyle = (o.profit || profit) > 0 ? 'color:var(--green); font-weight:700;' : ((o.profit || profit) < 0 ? 'color:var(--red);' : '');
    
    const priceText = (o.currency || '£') + Number(o.total_value || 0).toFixed(2);
    
    const customerHtml = `
      <div><strong>${esc(o.customer_name || '-')}</strong></div>
      <div style="font-size:11px; color:var(--muted);">${esc(o.email || '-')}</div>
    `;
    
    const eventHtml = `
      <div><strong>${esc(o.event_name || '-')}</strong></div>
      <div style="font-size:11px; color:var(--muted);">${esc(o.event_date || '-')}</div>
    `;
    
    const isSelected = selectedOrder && selectedOrder.platform === o.platform && selectedOrder.order_number === o.order_number;
    const rowClass = `clickable-row ${isSelected ? 'active-row' : ''}`;
    
    return `
      <tr class="${rowClass}" onclick="handleOrderRowClick(event, '${esc(o.platform)}', '${esc(o.order_number)}', '${esc(o.event_name)}')">
        <td style="font-family:monospace; font-weight:700;">#${esc(o.order_number)}</td>
        <td><span class="badge badge-gray">${esc(o.platform)}</span></td>
        <td>${customerHtml}</td>
        <td>${eventHtml}</td>
        <td>${o.quantity || 1}</td>
        <td>${priceText}</td>
        <td style="${profitStyle}">${profitText}</td>
        <td>${formatStatusWithIcon(o.normalized_status)}</td>
        <td style="font-family:monospace; font-size:11px;">${esc(o.sale_date || '-')}</td>
        <td style="font-family:monospace; font-size:11px;">${esc(o.last_updated || '-')}</td>
      </tr>
    `;
  }).join('');
}

function handleOrderRowClick(event, platform, orderNumber, eventName) {
  // Prevent drawer toggle if clicking inside select or inputs
  if (event.target.tagName === 'SELECT' || event.target.tagName === 'INPUT' || event.target.tagName === 'BUTTON') {
    return;
  }
  openDrawer(platform, orderNumber, eventName);
}

// Sorting headers
function handleSortClick(field) {
  if (ordersSortBy === field) {
    ordersSortDir = ordersSortDir === 'asc' ? 'desc' : 'asc';
  } else {
    ordersSortBy = field;
    ordersSortDir = 'desc';
  }
  
  // Highlight active header
  document.querySelectorAll('th.sortable').forEach(th => {
    th.classList.remove('asc', 'desc');
  });
  const activeTh = document.getElementById(`th-${field}`);
  if (activeTh) activeTh.classList.add(ordersSortDir);
  
  currentOrdersPage = 1;
  refresh();
}

// Pagination controls
function changePerPageLimit() {
  const el = document.getElementById('pagPerPage');
  if (el) {
    currentOrdersPerPage = parseInt(el.value) || 25;
    currentOrdersPage = 1;
    refresh();
  }
}

function ordersPrevPage() {
  if (currentOrdersPage > 1) {
    currentOrdersPage--;
    refresh();
  }
}

function ordersNextPage() {
  currentOrdersPage++;
  refresh();
}

// Collapsible advanced lookup tools
function toggleAdvancedLookupPanel() {
  const panel = document.getElementById('advancedLookupPanel');
  if (panel) {
    panel.classList.toggle('hidden');
  }
}

async function runAdvancedPlatformLookup() {
  const platform = document.getElementById('lookupPlatform').value;
  const eventName = document.getElementById('lookupEvent').value;
  if (!eventName) {
    showToast("Please enter an event name to check");
    return;
  }
  
  const btn = document.getElementById('btnRunLookup');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Scanning...';
  }
  
  try {
    const res = await api('/api/check-order-status', {
      method: 'POST',
      body: JSON.stringify({ platform, eventName })
    });
    
    const wrap = document.getElementById('lookupResultsWrap');
    const body = document.getElementById('lookupResultsBody');
    if (wrap && body) {
      wrap.classList.remove('hidden');
      if (res.ok && res.results && res.results.length) {
        body.innerHTML = res.results.map(r => `
          <tr>
            <td style="font-family:monospace;">#${esc(r.id)}</td>
            <td>${esc(r.customer || '-')}</td>
            <td>${esc(r.sale_date || '-')}</td>
            <td><span class="badge badge-gray">${esc(r.status || 'Pending')}</span></td>
          </tr>
        `).join('');
      } else {
        body.innerHTML = `<tr><td colspan="4"><div class="empty-state">No matching orders found on platform</div></td></tr>`;
      }
    }
  } catch(e) {
    showToast(`Scan failed: ${e.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Run Platform Scan';
    }
  }
}

// ─── DRAWERS ──────────────────────────────────────────────
async function openDrawer(source, orderId, eventName) {
  selectedOrder = { platform: source, order_number: orderId };
  
  // Highlight active row in table
  document.querySelectorAll('#ordersWorkspaceTableBody tr').forEach(row => {
    row.classList.remove('active-row');
  });
  const activeRow = Array.from(document.querySelectorAll('#ordersWorkspaceTableBody tr')).find(row => {
    return row.innerHTML.includes('#' + orderId) && row.innerHTML.includes(source);
  });
  if (activeRow) activeRow.classList.add('active-row');

  setText('drawerTitle', `Order #${orderId}`);
  setText('drawerSub', `${source} · ${eventName}`);
  const body = document.getElementById('drawerBody');
  body.innerHTML = `<div class="empty-state">Loading Details...</div>`;
  document.getElementById('orderDrawer').classList.remove('hidden');
  document.getElementById('drawerBackdrop').classList.remove('hidden');

  try {
    const [detailsRes, timelineRes] = await Promise.all([
      api(`/api/orders/${encodeURIComponent(source)}/${encodeURIComponent(orderId)}`),
      api(`/api/orders/${encodeURIComponent(source)}/${encodeURIComponent(orderId)}/timeline`).catch(() => [])
    ]);

    const d = detailsRes.data || {};
    
    let html = '';
    if (!detailsRes.ok && detailsRes.error) {
      html += `<div style="background:#fee2e2;color:#b91c1c;padding:8px;border-radius:var(--radius);margin-bottom:12px;font-size:11px;border:1px solid #fecaca;">
        <strong>⚠️ Warning:</strong> ${esc(detailsRes.error)}
      </div>`;
    }
    
    // Status update selector (RBAC check)
    let statusSelectorHtml = '';
    const canControl = (currentRole === 'admin' || currentRole === 'staff');
    if (canControl) {
      statusSelectorHtml = `
        <div class="form-group" style="margin:0; margin-top:8px;">
          <label class="form-label" style="font-size:9.5px; font-weight:700; text-transform:uppercase; color:var(--muted); margin-bottom:4px;">Update Status</label>
          <select class="form-input form-select" style="height:28px; padding:2px 8px; font-size:12px;" onchange="handleStatusChange(this, '${esc(source)}', '${esc(orderId)}')">
            <option value="pending" ${d.normalized_status === 'pending' ? 'selected' : ''}>⏳ Pending</option>
            <option value="completed" ${d.normalized_status === 'completed' ? 'selected' : ''}>🟢 Completed</option>
            <option value="cancelled" ${d.normalized_status === 'cancelled' ? 'selected' : ''}>🔴 Cancelled</option>
          </select>
        </div>
      `;
    } else {
      statusSelectorHtml = `
        <div class="form-group" style="margin:0; margin-top:8px;">
          <label class="form-label" style="font-size:9.5px; font-weight:700; text-transform:uppercase; color:var(--muted); margin-bottom:4px;">Current Status</label>
          <div style="margin-top:2px;">${formatStatusWithIcon(d.normalized_status)}</div>
        </div>
      `;
    }

    // Timeline list
    let timelineHtml = '<div class="empty-state" style="font-size:11px; padding:8px 0;">No logs recorded for this order</div>';
    if (timelineRes && timelineRes.length) {
      timelineHtml = `
        <div class="timeline-container">
          ${timelineRes.map(e => `
            <div class="timeline-item">
              <div class="timeline-dot ${e.level}"></div>
              <div class="timeline-line"></div>
              <div class="timeline-content">
                <span class="timeline-time">${esc(e.date)} ${esc(e.time)} [${esc(e.source)}]</span>
                <span class="timeline-message">${formatTimelineMessage(e.message)}</span>
              </div>
            </div>
          `).join('')}
        </div>
      `;
    }

    // Section 1: Quick Actions at the top
    html += `
      <div class="drawer-section" style="padding-top:0; border-bottom:1px solid var(--border); padding-bottom:12px; margin-bottom:12px;">
        <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px;">
          <button class="btn btn-secondary btn-sm" onclick="copyOrderDetailsToClipboard('${esc(orderId)}', '${esc(source)}', '${esc(eventName)}')">📋 Copy Order</button>
          ${d.source_url && d.source_url !== '-' ? `<a href="${esc(d.source_url)}" target="_blank" class="btn btn-secondary btn-sm" style="text-align:center; text-decoration:none;">↗ Open Source</a>` : ''}
          ${d.email && d.email !== '-' ? `<button class="btn btn-secondary btn-sm" onclick="exportCustomerHistory('${esc(d.email)}')">👥 Export Customer History</button>` : ''}
        </div>
        ${statusSelectorHtml}
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Order Section</div>
        <div class="detail-grid">
          ${field('Order ID', '#' + orderId)}
          ${field('Platform', source)}
          ${field('Event Name', eventName, true)}
          ${field('Event Date', d.event_date)}
          ${field('Quantity', d.quantity)}
          ${field('Sale Date', d.sale_date)}
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Customer Section</div>
        <div class="detail-grid">
          ${field('Full Name', d.customer_name)}
          ${field('Mobile', d.mobile_number)}
          ${field('Email', d.email)}
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Financial Section</div>
        <div class="detail-grid">
          ${field('List Price', (d.currency||'£') + Number(d.list_price || 0).toFixed(2))}
          ${field('Quantity', d.quantity)}
          ${field('Shipping', (d.currency||'£') + Number(d.shipping || 0).toFixed(2))}
          ${field('Total Value', (d.currency||'£') + Number(d.total_value || 0).toFixed(2), true)}
          ${field('Profit', (d.currency||'£') + Number(d.profit || 0).toFixed(2), true)}
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Delivery Section</div>
        <div class="detail-grid">
          ${field('POD Status', d.pod_status)}
          ${field('Delivery Status', d.delivery_status)}
          ${field('Broker Name', d.broker_name)}
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Timeline Section</div>
        ${timelineHtml}
      </div>
    `;
    body.innerHTML = html;
  } catch(e) {
    body.innerHTML = `<div class="empty-state" style="color:#b91c1c;">Error: ${esc(e.message)}</div>`;
  }
}

function copyOrderDetailsToClipboard(orderId, source, eventName) {
  const text = `Order Details:\nID: #${orderId}\nPlatform: ${source}\nEvent: ${eventName}`;
  navigator.clipboard.writeText(text).then(() => {
    showToast("Order details copied to clipboard ✅");
  }).catch(e => {
    showToast("Copy failed: " + e.message);
  });
}

function exportCustomerHistory(email) {
  window.location.href = `/api/reports/customer-history/${encodeURIComponent(email)}`;
}

async function handleStatusChange(select, platform, orderId) {
  const newStatus = select.value;
  if (newStatus === 'cancelled') {
    if (!confirm("Are you sure you want to cancel this order? This is a destructive state change!")) {
      select.value = select.dataset.original || 'pending';
      return;
    }
  }
  
  try {
    const res = await api(`/api/orders/${encodeURIComponent(platform)}/${encodeURIComponent(orderId)}/status`, {
      method: 'POST',
      body: JSON.stringify({ status: newStatus })
    });
    if (res.ok || res.message) {
      showToast(res.message || "Status updated successfully ✅");
      select.dataset.original = newStatus;
      await refresh();
      await openDrawer(platform, orderId, document.getElementById('drawerSub').textContent.split(' · ')[1]);
    } else {
      showToast(`Error: ${res.error || 'Failed to update status'}`);
    }
  } catch(e) {
    showToast(`Error: ${e.message}`);
  }
}

function field(l,v,full=false){ 
  const val = String(v ?? '');
  if (!val || val.includes('undefined') || val.includes('null') || val === '-') return '';
  return `<div class="detail-card ${full?'full':''}"><div class="detail-label">${esc(l)}</div><div class="detail-value">${esc(v)}</div></div>`;
}

function closeDrawer(){ 
  document.getElementById('orderDrawer').classList.add('hidden'); 
  if (document.getElementById('customerDrawer').classList.contains('hidden')) {
    document.getElementById('drawerBackdrop').classList.add('hidden'); 
  }
}

// ─── CUSTOMER PROFILE CRM DRAWER ───────────────────────────
function viewCustomerOrders(key) {
  const c = latestCustomers.find(item => item.key === key);
  if (!c) return;
  
  const drawer = document.getElementById('customerDrawer');
  const backdrop = document.getElementById('drawerBackdrop');
  if (!drawer || !backdrop) return;
  
  document.getElementById('customerDrawerTitle').textContent = c.name;
  document.getElementById('customerDrawerSub').textContent = `CRM Identifier: ${key}`;
  
  const avgSpend = c.total_orders > 0 ? (c.lifetime_spend / c.total_orders) : 0.0;
  
  const body = document.getElementById('customerDrawerBody');
  let historyHtml = c.orders.map(o => `
    <div style="border-bottom:1px solid var(--border); padding:6px 0;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-family:monospace; font-weight:700;">#${esc(o.order_number)}</span>
        ${formatStatusWithIcon(o.normalized_status)}
      </div>
      <div style="font-size:12px; font-weight:600; color:#fff; margin-top:2px;">${esc(o.event_name)}</div>
      <div style="display:flex; justify-content:space-between; font-size:10.5px; color:var(--muted); margin-top:2px;">
        <span>${esc(o.sale_date)} · Qty: ${o.quantity}</span>
        <span style="font-weight:700; color:#fff;">${o.currency}${Number(o.total_value).toFixed(2)}</span>
      </div>
    </div>
  `).join('');
  
  body.innerHTML = `
    <div class="drawer-section" style="padding-top:0;">
      <div class="drawer-section-title">Customer Metadata</div>
      <div class="detail-grid">
        ${field('Email Address', c.email)}
        ${field('Phone Number', c.phone)}
        ${field('Platform Source', c.platforms)}
        ${field('Last Order Date', c.last_purchase_date)}
      </div>
    </div>
    
    <div class="drawer-section">
      <div class="drawer-section-title">Value & Analytics</div>
      <div class="detail-grid">
        ${field('Total Orders', c.total_orders)}
        ${field('Lifetime Spend', c.currency + Number(c.lifetime_spend).toFixed(2))}
        ${field('Avg Order Value', c.currency + Number(avgSpend).toFixed(2))}
        ${field('Favorite Match', c.favorite_event)}
      </div>
    </div>
    
    <div class="drawer-section">
      <div class="drawer-section-title">Tags & Notes</div>
      <div style="padding:8px; border-radius:var(--radius); border:1px dashed var(--border); background:var(--bg-muted); margin-bottom:10px;">
        <div class="detail-label">Client Tags</div>
        <div style="display:flex; gap:4px; flex-wrap:wrap; margin-top:2px;">
          <span class="badge badge-blue">V.I.P Broker</span>
          <span class="badge badge-gray">Frequent Buyer</span>
        </div>
      </div>
      <div class="form-group" style="margin:0;">
        <label class="form-label">Internal Logistics Note</label>
        <textarea class="form-input" style="height:50px; font-size:11px; resize:none; background:var(--bg-muted); color:#fff; border:1px solid var(--border);" placeholder="Add instructions..."></textarea>
      </div>
    </div>
    
    <div class="drawer-section">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <div class="drawer-section-title" style="margin:0;">Purchase Timeline</div>
        <button class="btn btn-secondary btn-sm" onclick="exportCustomerHistoryExcel('${esc(key)}')">📥 Export</button>
      </div>
      <div style="display:flex; flex-direction:column; gap:6px;">
        ${historyHtml || '<div class="empty-state">No order history available</div>'}
      </div>
    </div>
  `;
  
  drawer.classList.remove('hidden');
  backdrop.classList.remove('hidden');
}

function closeCustomerDrawer() {
  const drawer = document.getElementById('customerDrawer');
  const backdrop = document.getElementById('drawerBackdrop');
  if (drawer) drawer.classList.add('hidden');
  if (backdrop && document.getElementById('orderDrawer').classList.contains('hidden')) {
    backdrop.classList.add('hidden');
  }
}

// ─── CRM LOADER ───────────────────────────────────────────
async function refreshCustomersList() {
  const q = document.getElementById('crmSearch')?.value || '';
  try {
    latestCustomers = await api(`/api/customers?search=${encodeURIComponent(q)}`);
    renderCustomers(latestCustomers);
  } catch (e) {
    console.error('Failed to load customer profiles:', e);
  }
}

function renderCustomers(customers) {
  const body = document.getElementById('crmTableBody');
  if (!body) return;
  if (!customers.length) {
    body.innerHTML = `<tr><td colspan="8"><div class="empty-state">No customer profiles found</div></td></tr>`;
    return;
  }
  
  body.innerHTML = customers.map(c => `
    <tr style="cursor:pointer" onclick="viewCustomerOrders('${esc(c.key)}')" title="Click to view full purchase history">
      <td><strong>👤 ${esc(c.name)}</strong></td>
      <td>${esc(c.email)}</td>
      <td>${esc(c.phone)}</td>
      <td><span class="badge badge-gray">${esc(c.platforms)}</span></td>
      <td><span class="badge badge-blue">${c.total_orders}</span></td>
      <td><strong>${c.currency}${Number(c.lifetime_spend).toFixed(2)}</strong></td>
      <td>${esc(c.last_purchase_date)}</td>
      <td><span class="badge badge-green">${esc(c.favorite_event)}</span></td>
    </tr>
  `).join('');
}

// ─── QUICK STATUS SEARCH ──────────────────────────────────
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
      <td>${formatStatusWithIcon(r.status)}</td>
    </tr>`).join('');
  } catch(e) {
    body.innerHTML = `<tr><td colspan="4"><div class="empty-state" style="color:#b91c1c;">Error: ${esc(e.message)}</div></td></tr>`;
  }
}

// ─── TICKETSHOP VERIFICATION ──────────────────────────────
async function checkTicketsshopOrders() {
  const btn = document.getElementById('btnTicketsshop');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner" style="display:inline-block;width:12px;height:12px;border:2px solid #fff;border-radius:50%;border-top-color:transparent;animation:spin 1s linear infinite;margin-right:6px;"></span> Checking...';
  }
  showToast("Ticketshop scan started. Firing updates...");
  
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
      await refresh();
    } else {
      showToast(`❌ Error: ${res.error || 'Failed to check Ticketshop'}`);
    }
  } catch(e) {
    showToast(`❌ Exception: ${e.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = 'Scan Listings Now';
    }
  }
}

// ─── PLATFORM CARDS ───────────────────────────────────────
async function loadPlatformCards() {
  const container = document.getElementById('platformCardsContainer');
  if (!container) return;
  container.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const platforms = await api('/api/platforms');
    if (!platforms.length) {
      container.innerHTML = '<div class="empty-state">No platforms configured</div>';
      return;
    }
    const icons = { LiveTicketGroup: '🎟️', FootballTicketNet: '⚽', Ticketshop: '🛒' };
    const verifyHints = {
      LiveTicketGroup: 'Adapter using credentials from .env file.',
      FootballTicketNet: 'Session managed via automated browser profile.',
      Ticketshop: 'Manual verification mode — no scraper credentials required.'
    };
    const isSyncable = { LiveTicketGroup: true, FootballTicketNet: true, Ticketshop: false };

    container.innerHTML = platforms.map(p => {
      const enabled = p.is_enabled;
      const icon = icons[p.name] || '🔌';
      const statusClass = enabled ? 'badge-green' : 'badge-gray';
      const statusLabel = enabled ? 'Enabled' : 'Disabled';
      const lastErr = p.last_error
        ? `<div class="summary-stat-row"><span class="summary-stat-label">Last Error</span><span class="summary-stat-value" style="color:var(--orange); font-size:11px; max-width:200px; overflow:hidden; white-space:nowrap; text-overflow:ellipsis;" title="${esc(p.last_error)}">${esc(p.last_error_time)} — ${esc(p.last_error)}</span></div>`
        : `<div class="summary-stat-row"><span class="summary-stat-label">Last Error</span><span class="summary-stat-value" style="color:var(--green);">None</span></div>`;
      const syncBtn = isSyncable[p.name]
        ? `<button class="btn btn-primary btn-sm" onclick="triggerManualSync('${esc(p.name)}')">↻ Sync Now</button>`
        : `<button class="btn btn-secondary btn-sm" disabled title="Manual scan only">↻ Sync Now</button>`;
      return `
        <div class="card" style="opacity:${enabled ? 1 : 0.6};">
          <div class="card-header">
            <div class="card-title">${icon} ${esc(p.name)}</div>
            <div style="display:flex; align-items:center; gap:10px;">
              <span class="badge ${statusClass}">${statusLabel}</span>
              <label class="toggle" title="Enable or disable this platform">
                <input type="checkbox" ${enabled ? 'checked' : ''} onchange="togglePlatform('${esc(p.name)}', this)">
                <span class="toggle-slider"></span>
              </label>
            </div>
          </div>
          <div class="card-body">
            <div class="summary-stat-list" style="margin-bottom:12px;">
              <div class="summary-stat-row">
                <span class="summary-stat-label">Current Status</span>
                <span class="summary-stat-value" style="color:${enabled ? 'var(--green)' : 'var(--muted)'}">${enabled ? 'Running' : 'Disabled'}</span>
              </div>
              <div class="summary-stat-row">
                <span class="summary-stat-label">Last Successful Sync</span>
                <span class="summary-stat-value">${esc(p.last_sync || '—')}</span>
              </div>
              <div class="summary-stat-row">
                <span class="summary-stat-label">Orders Synced Today</span>
                <span class="summary-stat-value">${p.orders_today}</span>
              </div>
              <div class="summary-stat-row">
                <span class="summary-stat-label">Session Status</span>
                <span class="summary-stat-value" style="color:${p.session_status === 'Active' ? 'var(--green)' : 'var(--orange)'}">${esc(p.session_status)}</span>
              </div>
              ${lastErr}
            </div>
            <div style="display:flex; gap:6px;">
              ${syncBtn}
              <button class="btn btn-secondary btn-sm" onclick="showToast('${esc(verifyHints[p.name] || 'No credential info available.')}')">Verify Credentials</button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch(e) {
    container.innerHTML = `<div class="empty-state" style="color:#b91c1c;">Failed to load platforms: ${esc(e.message)}</div>`;
  }
}

async function togglePlatform(name, checkbox) {
  const originalState = !checkbox.checked; // before toggle
  try {
    const res = await api(`/api/platforms/${encodeURIComponent(name)}/toggle`, { method: 'POST' });
    showToast(`${name} ${res.is_enabled ? 'enabled ✅' : 'disabled ⏸️'}`);
    // Reload cards to reflect new DB state cleanly
    await loadPlatformCards();
    // Update health widget too
    const health = await api('/api/dashboard/health');
    renderOpsHealth(health);
  } catch(e) {
    checkbox.checked = originalState; // revert on failure
    showToast(`Failed to toggle ${name}: ${e.message}`);
  }
}

// ─── SETTINGS ACTIONS ─────────────────────────────────────
async function saveIntervalSettings() {
  const val = parseInt(document.getElementById('settingsInterval').value);
  if (!val || val < 1) { showToast("Invalid check interval"); return; }
  try {
    await api('/api/platform-states', { method: 'POST', body: JSON.stringify({ interval_minutes: val }) });
    showToast("Check interval updated successfully ✅");
    await refresh();
  } catch (e) { showToast("Failed: " + e.message); }
}

async function toggleSetting(key) {
  const val = document.getElementById('sleepToggle')?.checked;
  try {
    await api('/api/platform-states', { method: 'POST', body: JSON.stringify({ [key]: val }) });
    showToast("Daemon setting updated ✅");
    await refresh();
  } catch(e) { showToast("Failed to toggle setting"); }
}

// ─── REFRESH CONTROLLER ───────────────────────────────
async function refresh() {
  const [state, stats, health, feed, alerts] = await Promise.all([
    api('/api/state').catch(e => { console.error("state api failed:", e); return { _failed: true }; }),
    api('/api/dashboard/stats').catch(e => { console.error("stats api failed:", e); return { _failed: true }; }),
    api('/api/dashboard/health').catch(e => { console.error("health api failed:", e); return { _failed: true }; }),
    api('/api/dashboard/activity').catch(e => { console.error("activity api failed:", e); return { _failed: true }; }),
    api('/api/dashboard/alerts').catch(e => { console.error("alerts api failed:", e); return { _failed: true }; })
  ]);

  // Handle State
  if (state && !state._failed) {
    currentRole = state.current_role || 'viewer';
    currentUser = state.current_user || '';
    schedulerRunning = (state.scheduler && state.scheduler.status === 'Running');
    lastSyncTime = (stats && !stats._failed) ? (stats.last_sync_time || '-') : '-';
    setText('sidebarUsername', currentUser);
    setText('sidebarRole', currentRole);
    const av = document.getElementById('avatarInitial');
    if (av) av.textContent = (currentUser[0] || 'A').toUpperCase();
    const running = schedulerRunning;
    const pill = document.getElementById('botStatusPill');
    if (pill) pill.className = `status-pill ${running ? 'running' : 'stopped'}`;
    setText('botStatusText', running ? 'Running' : 'Stopped');
    const mt = document.getElementById('masterToggle');
    if (mt && mt !== document.activeElement) mt.checked = running;
    renderMembersTable(state.members || []);
  } else {
    // State API failure fallback
    schedulerRunning = false;
    currentRole = 'viewer';
    const pill = document.getElementById('botStatusPill');
    if (pill) pill.className = `status-pill stopped`;
    setText('botStatusText', 'Unknown');
    const mt = document.getElementById('masterToggle');
    if (mt) mt.checked = false;
  }

  // Handle Stats Today bar and Last Sync header
  if (stats && !stats._failed) {
    setText('statTodayOrders', stats.today_orders ?? '—');
    setText('statRevenue', (stats.currency || '£') + Number(stats.revenue || 0).toFixed(2));
    setText('statPending',     stats.pending     ?? '—');
    setText('statCancelled',   stats.cancelled   ?? '—');
    setText('statCompleted',   stats.completed   ?? '—');
    
    const lastSyncFormatted = formatLastSync(stats.last_sync_time);
    setText('topbarLastSync', lastSyncFormatted);
  } else {
    // Stats API failure fallback
    setText('statTodayOrders', '—');
    setText('statRevenue', '—');
    setText('statPending', '—');
    setText('statCancelled', '—');
    setText('statCompleted', '—');
    setText('topbarLastSync', 'Last sync: Unknown');
  }

  // Handle inventory issues stat from health API
  if (health && !health._failed) {
    setText('statMismatches', health.mismatches ?? 0);
  } else {
    setText('statMismatches', '—');
  }

  // Render Ops Center sections
  renderOpsHealth(health, state);
  renderOpsActivity(feed);
  renderOpsAttention(alerts);

  // Render Alerts Center page (fallback is internally handled inside renderAlertsPage)
  renderAlertsPage(alerts);

  // Load orders (independent — page-specific)
  try {
    const params = getOrdersParams();
    const res = await api(`/api/orders?${params.toString()}`);
    
    // Update active filter badge count
    updateActiveFilterBadgeCount();

    // Render pagination labels
    const total = res.total || 0;
    setText('pagTotal', total);
    const start = total === 0 ? 0 : (currentOrdersPage - 1) * currentOrdersPerPage + 1;
    const end = Math.min(currentOrdersPage * currentOrdersPerPage, total);
    setText('pagStart', start);
    setText('pagEnd', end);
    
    // Disable/enable pagination buttons
    const prevBtn = document.getElementById('btnPrevPage');
    const nextBtn = document.getElementById('btnNextPage');
    if (prevBtn) prevBtn.disabled = currentOrdersPage <= 1;
    if (nextBtn) nextBtn.disabled = end >= total;
    
    renderOrdersWorkspaceTable(res.orders || []);
  } catch(e) {
    console.error('Failed to fetch orders:', e);
    const body = document.getElementById('ordersWorkspaceTableBody');
    if (body) {
      body.innerHTML = `<tr><td colspan="10"><div class="empty-state" style="color:var(--red);">Orders API unavailable: ${esc(e.message)}</div></td></tr>`;
    }
  }

  if (document.getElementById('customersPage')?.classList.contains('active')) {
    refreshCustomersList();
  }
}



// ─── USER ADMINISTRATION ─────────────────────────────────
function renderMembersTable(members) {
  const body = document.getElementById('membersBody');
  if (!body) return;
  
  const addMemberCard = document.getElementById('newUsername')?.closest('.card');
  if (addMemberCard) {
    addMemberCard.style.display = currentRole === 'admin' ? 'block' : 'none';
  }
  
  if (!members.length) {
    body.innerHTML = `<tr><td colspan="4"><div class="empty-state">No members found</div></td></tr>`;
    return;
  }
  
  body.innerHTML = members.map(u => {
    const isSelf = u.username === currentUser;
    const statusBadge = u.is_active ? '<span class="badge badge-green">Active</span>' : '<span class="badge badge-red">Inactive</span>';
    
    let actionsHtml = '';
    if (currentRole === 'admin') {
      actionsHtml = `
        <div style="display:flex; gap:6px;">
          <select class="form-select form-select-sm" onchange="changeMemberRole('${esc(u.username)}', this.value)" ${isSelf ? 'disabled' : ''} style="padding:2px 6px; font-size:11px; height:22px; background:var(--bg-muted); border:1px solid var(--border); color:var(--text); border-radius:var(--radius);">
            <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
            <option value="staff" ${u.role === 'staff' ? 'selected' : ''}>Staff</option>
            <option value="viewer" ${u.role === 'viewer' ? 'selected' : ''}>Viewer</option>
          </select>
          <button class="btn btn-secondary btn-sm" onclick="resetMemberPassword('${esc(u.username)}')" style="padding:2px 4px; font-size:11px; height:22px;">Reset</button>
          <button class="btn btn-sm ${u.is_active ? 'btn-secondary' : 'btn-primary'}" onclick="toggleMemberActive('${esc(u.username)}')" ${isSelf ? 'disabled' : ''} style="padding:2px 4px; font-size:11px; height:22px;">
            ${u.is_active ? 'Suspend' : 'Activate'}
          </button>
          <button class="btn btn-secondary btn-sm" onclick="deleteMember('${esc(u.username)}')" ${isSelf ? 'disabled' : ''} style="padding:2px 4px; font-size:11px; height:22px; background-color:#fee2e2; color:#b91c1c; border-color:#fecaca;">Delete</button>
        </div>
      `;
    } else {
      actionsHtml = `<span style="font-size:11px; color:var(--muted)">No actions available</span>`;
    }
    
    return `
      <tr>
        <td><strong>${esc(u.username)}</strong> ${isSelf ? '<span class="badge badge-blue">You</span>' : ''}</td>
        <td><span class="badge badge-gray" style="text-transform:capitalize">${esc(u.role)}</span></td>
        <td>${statusBadge}</td>
        <td>${actionsHtml}</td>
      </tr>
    `;
  }).join('');
}

async function addMember() {
  const uEl = document.getElementById('newUsername');
  const pEl = document.getElementById('newPassword');
  const rEl = document.getElementById('newRole');
  if (!uEl || !pEl || !rEl) return;
  
  const username = uEl.value.trim();
  const password = pEl.value;
  const role = rEl.value;
  
  if (!username || !password) {
    showToast("Username and Password are required");
    return;
  }
  
  try {
    await api('/api/users/add', {
      method: 'POST',
      body: JSON.stringify({ username, password, role })
    });
    showToast(`Member ${username} added successfully ✅`);
    uEl.value = '';
    pEl.value = '';
    await refresh();
  } catch (e) {
    showToast("Failed to add member: " + e.message);
  }
}

async function changeMemberRole(username, role) {
  try {
    await api('/api/users/change-role', {
      method: 'POST',
      body: JSON.stringify({ username, role })
    });
    showToast(`Role of ${username} updated to ${role} ✅`);
    await refresh();
  } catch (e) {
    showToast("Failed to change role: " + e.message);
  }
}

async function resetMemberPassword(username) {
  const newPass = prompt(`Enter new password for user ${username}:`);
  if (newPass === null) return;
  if (!newPass.trim()) {
    showToast("Password cannot be empty");
    return;
  }
  try {
    await api('/api/users/reset-password', {
      method: 'POST',
      body: JSON.stringify({ username, password: newPass.trim() })
    });
    showToast(`Password for ${username} reset successfully ✅`);
  } catch (e) {
    showToast("Failed to reset password: " + e.message);
  }
}

async function toggleMemberActive(username) {
  try {
    await api('/api/users/toggle-active', {
      method: 'POST',
      body: JSON.stringify({ username })
    });
    showToast(`Active state of ${username} toggled ✅`);
    await refresh();
  } catch (e) {
    showToast("Failed to toggle state: " + e.message);
  }
}

async function deleteMember(username) {
  if (!confirm(`Are you sure you want to delete user ${username}? This cannot be undone.`)) return;
  try {
    await api('/api/users/delete', {
      method: 'POST',
      body: JSON.stringify({ username })
    });
    showToast(`User ${username} deleted successfully ✅`);
    await refresh();
  } catch (e) {
    showToast("Failed to delete user: " + e.message);
  }
}

// ─── EXPORT TRIGGERS ──────────────────────────────────────
function exportOrdersExcel() {
  const params = getOrdersParams();
  // Remove page and per_page limits to export all filtered matches
  params.delete('page');
  params.delete('per_page');
  window.location.href = `/api/reports/orders?${params.toString()}`;
}

function exportCustomersExcel() {
  window.location.href = '/api/reports/customers';
}

function exportCustomerHistoryExcel(key) {
  window.location.href = `/api/reports/customer-history/${encodeURIComponent(key)}`;
}

function exportRevenueExcel() {
  window.location.href = '/api/reports/revenue';
}

function exportPlatformsExcel() {
  window.location.href = '/api/reports/platforms';
}

async function fullRefresh(){ await refresh(); }
fullRefresh();
setInterval(fullRefresh, 8000);

// Redesigned Orders Workspace Helper Functions
function getOrdersParams() {
  const params = new URLSearchParams();
  
  const q = document.getElementById('filterGlobalQuery')?.value;
  const platform = document.getElementById('filterPlatform')?.value;
  const status = document.getElementById('filterStatus')?.value;
  const start_date = document.getElementById('filterStartDate')?.value;
  const end_date = document.getElementById('filterEndDate')?.value;
  const event = document.getElementById('filterEvent')?.value;
  const customer = document.getElementById('filterCustomer')?.value;
  
  if (q) params.append('q', q);
  if (platform) params.append('platform', platform);
  const effectiveStatus = activeStatusFilter || status;
  if (effectiveStatus) params.append('status', effectiveStatus);
  if (start_date) params.append('start_date', start_date);
  if (end_date) params.append('end_date', end_date);
  if (event) params.append('event', event);
  if (customer) params.append('customer', customer);
  
  params.append('page', currentOrdersPage);
  params.append('per_page', currentOrdersPerPage);
  params.append('sort_by', ordersSortBy);
  params.append('sort_dir', ordersSortDir);
  
  return params;
}

function updateActiveFilterBadgeCount() {
  let count = 0;
  const q = document.getElementById('filterGlobalQuery')?.value;
  const platform = document.getElementById('filterPlatform')?.value;
  const status = document.getElementById('filterStatus')?.value;
  const start_date = document.getElementById('filterStartDate')?.value;
  const end_date = document.getElementById('filterEndDate')?.value;
  const event = document.getElementById('filterEvent')?.value;
  const customer = document.getElementById('filterCustomer')?.value;
  
  if (q) count++;
  if (platform) count++;
  if (activeStatusFilter || status) count++;
  if (start_date) count++;
  if (end_date) count++;
  if (event) count++;
  if (customer) count++;
  
  const badge = document.getElementById('activeFiltersBadge');
  if (badge) {
    if (count > 0) {
      badge.style.display = 'inline-flex';
      badge.textContent = count;
    } else {
      badge.style.display = 'none';
    }
  }
}

// Global Bindings
window.checkOrderStatus = checkOrderStatus;
window.switchPage = switchPage;
window.toggleMasterMonitoring = toggleMasterMonitoring;
window.triggerCheckNow = triggerCheckNow;
window.filterOrdersByStatus = filterOrdersByStatus;
window.clearOrdersFilter = clearOrdersFilter;
window.applyOrdersFilters = applyOrdersFilters;
window.resetOrdersFilters = resetOrdersFilters;
window.openDrawer = openDrawer;
window.closeDrawer = closeDrawer;
window.toggleSetting = toggleSetting;
window.saveIntervalSettings = saveIntervalSettings;
window.triggerManualSync = triggerManualSync;
window.checkTicketsshopOrders = checkTicketsshopOrders;
window.viewCustomerOrders = viewCustomerOrders;
window.closeCustomerDrawer = closeCustomerDrawer;
window.addMember = addMember;
window.changeMemberRole = changeMemberRole;
window.resetMemberPassword = resetMemberPassword;
window.toggleMemberActive = toggleMemberActive;
window.deleteMember = deleteMember;
window.exportOrdersExcel = exportOrdersExcel;
window.exportCustomersExcel = exportCustomersExcel;
window.exportCustomerHistoryExcel = exportCustomerHistoryExcel;
window.exportRevenueExcel = exportRevenueExcel;
window.exportPlatformsExcel = exportPlatformsExcel;
window.loadPlatformCards = loadPlatformCards;
window.togglePlatform = togglePlatform;
window.toggleScheduler = toggleScheduler;

// Sprint 2 Workspace Bindings
window.applyOrdersFiltersDebounced = applyOrdersFiltersDebounced;
window.refreshOrdersTable = refreshOrdersTable;
window.handleOrderRowClick = handleOrderRowClick;
window.handleSortClick = handleSortClick;
window.changePerPageLimit = changePerPageLimit;
window.ordersPrevPage = ordersPrevPage;
window.ordersNextPage = ordersNextPage;
window.toggleAdvancedLookupPanel = toggleAdvancedLookupPanel;
window.runAdvancedPlatformLookup = runAdvancedPlatformLookup;
window.copyOrderDetailsToClipboard = copyOrderDetailsToClipboard;
window.exportCustomerHistory = exportCustomerHistory;
window.handleStatusChange = handleStatusChange;


