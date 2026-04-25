let hourChartInstance = null;
let dayChartInstance = null;
let latestOrdersData = [];
let latestSentData = [];
let currentRole = "member";
let currentUser = "";
let selectedEvent = null;
let selectedSource = null;
let orderDetailsCache = {};

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (res.status === 401) { window.location.href = "/login"; throw new Error("Unauthorized"); }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function esc(v) { return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;"); }
function parseDate(dateText) {
  if (!dateText) return null;
  const m = String(dateText).match(/^(\d{2})-(\d{2})-(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (!m) return null;
  const [,dd,mm,yyyy,hh,min,ss] = m;
  return new Date(Number(yyyy), Number(mm)-1, Number(dd), Number(hh), Number(min), Number(ss||0));
}
function updateGreeting(){ const el=document.getElementById('greetingText'); if(!el) return; const h=new Date().getHours(); let greeting='Good evening'; if(h>=5 && h<12) greeting='Good morning'; else if(h>=12 && h<18) greeting='Good afternoon'; el.textContent=greeting+' 👋'; }
function setStatusText(status){ const hero=document.getElementById('heroStatus'); if(hero) hero.textContent=status||'Stopped'; }
function setSleepButtons(on){ ['sleepToggleSettings'].forEach(id=>{ const el=document.getElementById(id); if(!el) return; el.textContent=on?'Sleep 12AM: ON':'Sleep 12AM: OFF'; el.classList.toggle('active',!!on); }); }

function statusBadge(status){ const s=String(status||'Pending').toLowerCase(); let cls='status-pill pending'; let label=status||'Pending'; if(s.includes('cancel')) cls='status-pill cancelled'; else if(s.includes('process')||s.includes('complete')) cls='status-pill processed'; return `<span class="${cls}">${esc(label)}</span>`; }
function getDetail(source,id){ return orderDetailsCache[`${source}::${id}`]||{}; }
function qtyFor(row){ const d=getDetail(row.source,row.id); return Number(d.quantity||0)||0; }
function totalFor(row){ const d=getDetail(row.source,row.id); const total=Number(String(d.total_price||0).replace(/[^0-9.]/g,'')); if(total>0) return total; const ppt=Number(String(d.price_per_ticket||0).replace(/[^0-9.]/g,'')); const q=qtyFor(row); return ppt>0&&q>0? ppt*q : 0; }
function orderStatus(row){ const d=getDetail(row.source,row.id); return d.status || row.status || 'Pending'; }

function renderSourceBreakdown(sourceCounts){ const el=document.getElementById('sourceBreakdown'); if(!el) return; const entries=Object.entries(sourceCounts||{}); el.innerHTML=entries.length?entries.map(([s,c])=>`<div class="source-chip"><span>${esc(s)}</span><strong>${c}</strong></div>`).join(''):'<div class="muted">No sources yet</div>'; }

function groupOrdersByEventSource(orders){
  const grouped={};
  for(const row of orders||[]){
    const event=row.event||'Unknown Event';
    const source=row.source||'Unknown';
    const key=`${event}|||${source}`;
    if(!grouped[key]) grouped[key]={key,event,source,event_date: row.event_date||'-', orders:[], orders_count:0};
    grouped[key].orders.push(row);
    grouped[key].orders_count += 1;
    const currentDate=parseDate(grouped[key].event_date);
    const rowDate=parseDate(row.event_date);
    if(!currentDate && row.event_date) grouped[key].event_date=row.event_date;
    else if(currentDate && rowDate && rowDate<currentDate) grouped[key].event_date=row.event_date;
  }
  return Object.values(grouped).sort((a,b)=>b.orders_count-a.orders_count || a.event.localeCompare(b.event) || a.source.localeCompare(b.source));
}

function renderActiveEvents(totals) {
  const body = document.getElementById('activeEventsBody');
  if(!body) return;
  if(!totals || !totals.length) {
    body.innerHTML = '<tr><td colspan="6" class="muted">No active events yet</td></tr>';
    return;
  }
  body.innerHTML = totals.map(t => {
    const statusHtml = t.needs_attention 
        ? '<span class="status-pill cancelled">Needs Attention</span>' 
        : '<span class="status-pill processed">Healthy</span>';
    return `<tr style="cursor:pointer;" onclick="openOrdersTab('${esc(t.event)}','${esc(t.source)}')">
      <td style="font-weight: 700;">${esc(t.event)}</td>
      <td>${esc(t.source)}</td>
      <td>${t.orders_count}</td>
      <td>${t.total_quantity}</td>
      <td>£${t.total_price.toFixed(2)}</td>
      <td>${statusHtml}</td>
    </tr>`;
  }).join('');
}

function renderRecentSent(rows){ 
  const body = document.getElementById('recentSentBody'); 
  if(!body) return; 
  if(!rows.length){ 
    body.innerHTML='<tr><td colspan="3" class="muted">No recent sent orders</td></tr>'; 
    return; 
  } 
  body.innerHTML = rows.map(r => `<tr>
    <td><button class="order-link-btn" onclick="openOrderDrawer('${encodeURIComponent(r.source||'')}','${encodeURIComponent(r.id||'')}','${encodeURIComponent(r.event||'')}')">${esc(r.id||'-')}</button></td>
    <td>${esc(r.event||'-')}</td>
    <td>${esc(r.source||'-')}</td>
  </tr>`).join(''); 
}

function toggleAccordion(id) {
  const body = document.getElementById(id);
  if(body) {
    body.classList.toggle('hidden');
  }
}

function renderEventAccordion(groups) {
  const container = document.getElementById('ordersEventAccordion');
  if(!container) return;
  if(!groups || !groups.length) {
    container.innerHTML = '<div class="muted">No orders found.</div>';
    return;
  }

  container.innerHTML = groups.map((g, i) => {
    const bodyId = `accordion-body-${i}`;
    
    let ordersHtml = `
      <div class="table-wrap short-table" style="border: none; max-height: none;">
        <table>
          <thead>
            <tr><th>ID</th><th>Customer</th><th>Quantity</th><th>Total Price</th><th>Sale Date</th><th>Status</th><th>Source</th></tr>
          </thead>
          <tbody>
            ${g.orders.slice().sort((a,b)=>(parseDate(b.sale_date)||0)-(parseDate(a.sale_date)||0)).map(r => `
              <tr>
                <td><button class="order-link-btn" onclick="openOrderDrawer('${encodeURIComponent(r.source||'')}','${encodeURIComponent(r.id||'')}','${encodeURIComponent(r.event||'')}')">${esc(r.id)}</button></td>
                <td>${esc(r.customer||'-')}</td>
                <td>${esc(qtyFor(r))}</td>
                <td>£${Number(totalFor(r)).toFixed(2)}</td>
                <td>${esc(r.sale_date||'-')}</td>
                <td>${statusBadge(orderStatus(r))}</td>
                <td>${esc(r.source||'-')}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;

    const isExpanded = selectedEvent === g.event && selectedSource === g.source;
    
    return `
      <div class="accordion-item" style="border: 1px solid var(--border); border-radius: 12px; margin-bottom: 12px; background: var(--card); overflow: hidden;">
        <div class="accordion-header" style="padding: 16px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; background: var(--table-head);" onclick="toggleAccordion('${bodyId}')">
          <div style="font-weight: 700; font-size: 16px;">${esc(g.event)} <span style="font-size: 13px; font-weight: normal; color: var(--muted);">→ ${esc(g.source)} (${g.orders_count} orders)</span></div>
          <div style="color: var(--muted);">▼</div>
        </div>
        <div id="${bodyId}" class="${isExpanded ? '' : 'hidden'}" style="border-top: 1px solid var(--border);">
          ${ordersHtml}
        </div>
      </div>
    `;
  }).join('');
}

function renderCustomerAnalytics(orders){ const body=document.getElementById('customersBody'); if(!body) return; if(!orders.length){ body.innerHTML='<tr><td colspan="5" class="muted">No customer data</td></tr>'; return; } const map={}; for(const r of orders){ const c=(r.customer||'Unknown').trim()||'Unknown'; if(!map[c]) map[c]={customer:c,totalOrders:0,events:new Set(),platforms:new Set(),nextEventDateText:'-',nextEventDate:null}; map[c].totalOrders++; map[c].events.add(r.event||'Unknown'); map[c].platforms.add(r.source||'Unknown'); const d=parseDate(r.event_date); if(d && (!map[c].nextEventDate || d<map[c].nextEventDate)){ map[c].nextEventDate=d; map[c].nextEventDateText=r.event_date||'-'; }} const rows=Object.values(map).sort((a,b)=>b.totalOrders-a.totalOrders); body.innerHTML=rows.map(r=>`<tr><td>${esc(r.customer)}</td><td>${r.totalOrders}</td><td>${r.events.size}</td><td>${esc(Array.from(r.platforms).join(', '))}</td><td>${esc(r.nextEventDateText)}</td></tr>`).join(''); }
function renderActivity(orders){ const body=document.getElementById('activityBody'); if(!body) return; if(!orders.length){ body.innerHTML='<tr><td colspan="3" class="muted">No activity</td></tr>'; return; } const uniq={}; for(const r of orders){ const key=`${r.source}|||${r.event}`; const parsed=parseDate(r.event_date); if(!uniq[key] || (parsed && (!uniq[key].parsed || parsed<uniq[key].parsed))){ uniq[key]={source:r.source,event:r.event,event_date:r.event_date,parsed}; } } const rows=Object.values(uniq).sort((a,b)=>{ if(!a.parsed&&!b.parsed) return 0; if(!a.parsed) return 1; if(!b.parsed) return -1; return a.parsed-b.parsed;}); body.innerHTML=rows.map(r=>`<tr><td>${esc(r.source)}</td><td>${esc(r.event)}</td><td>${esc(r.event_date)}</td></tr>`).join(''); }
function roleBadge(role){ const cls=role==='admin'?'role-admin':'role-member'; return `<span class="role-badge ${cls}">${esc(role)}</span>`; }
function statusUserBadge(active){ return active?'<span class="status-active">Active</span>':'<span class="status-disabled">Disabled</span>'; }
function renderMembers(members){ const body=document.getElementById('membersBody'); if(!body) return; if(!members.length){ body.innerHTML='<tr><td colspan="5" class="muted">No members</td></tr>'; return; } body.innerHTML=members.map(m=>{ const isSelf=m.username===currentUser; const toggleLabel=m.is_active?'Disable':'Enable'; const nextRole=m.role==='admin'?'member':'admin'; const roleLabel=m.role==='admin'?'Make Member':'Make Admin'; const actions=currentRole==='admin'?`<div class="inline-actions"><button class="btn btn-secondary btn-small" onclick="changeRole('${esc(m.username)}','${nextRole}')">${roleLabel}</button><button class="btn btn-warning btn-small" onclick="resetPasswordPrompt('${esc(m.username)}')">Reset PW</button><button class="btn btn-secondary btn-small" onclick="toggleUserActive('${esc(m.username)}')">${toggleLabel}</button>${!isSelf&&m.username.toLowerCase()!=='admin'?`<button class="btn btn-danger btn-small" onclick="deleteUser('${esc(m.username)}')">Delete</button>`:''}</div>`:'<span class="muted">View only</span>'; return `<tr><td>${esc(m.username)}</td><td>${roleBadge(m.role)}</td><td>${statusUserBadge(m.is_active)}</td><td>${esc(m.created_at||'-')}</td><td>${actions}</td></tr>`; }).join(''); }

function renderHourChart(labels, values){ const c=document.getElementById('hourChart'); if(!c) return; if(hourChartInstance) hourChartInstance.destroy(); hourChartInstance=new Chart(c,{type:'bar',data:{labels,datasets:[{label:'Orders',data:values,borderWidth:1}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,ticks:{precision:0}}}}}); }
function renderDayChart(labels, values){ const c=document.getElementById('dayChart'); if(!c) return; if(dayChartInstance) dayChartInstance.destroy(); dayChartInstance=new Chart(c,{type:'line',data:{labels,datasets:[{label:'Orders',data:values,fill:false,tension:0.25,borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,ticks:{precision:0}}}}}); }

function openDrawerShell(title, subtitle, bodyHtml){ const drawer=document.getElementById('orderDrawer'), backdrop=document.getElementById('orderDrawerBackdrop'); document.getElementById('drawerOrderTitle').textContent=title; document.getElementById('drawerOrderSub').textContent=subtitle; document.getElementById('orderDrawerBody').innerHTML=bodyHtml; drawer.classList.remove('hidden'); backdrop.classList.remove('hidden'); document.body.classList.add('drawer-open'); }
function closeOrderDrawer(){ document.getElementById('orderDrawer').classList.add('hidden'); document.getElementById('orderDrawerBackdrop').classList.add('hidden'); document.body.classList.remove('drawer-open'); }
function renderLineItemsTable(items){ if(!items||!items.length) return '<div class="muted">No ticket rows found.</div>'; const rows=items.map(row=>`<tr>${row.map(cell=>`<td>${esc(cell)}</td>`).join('')}</tr>`).join(''); return `<div class="drawer-section"><div class="drawer-section-title">Ticket Rows</div><div class="drawer-table-wrap"><table><thead><tr><th>Category</th><th>Section</th><th>Row</th><th>Seating</th><th>Allocation</th><th>Shipping</th><th>Qty</th></tr></thead><tbody>${rows}</tbody></table></div></div>`; }
async function openOrderDrawer(source, orderId, eventName){ const s=decodeURIComponent(source||''), id=decodeURIComponent(orderId||''), ev=decodeURIComponent(eventName||''); openDrawerShell(`Order #${id}`, `${s} • ${ev||'Loading...'}`, `<div class="drawer-loading"><div class="drawer-spinner"></div><div>Loading order details...</div></div>`); try{ const res=await api(`/api/order-details/${encodeURIComponent(s)}/${encodeURIComponent(id)}`); const d=res.details||{}; orderDetailsCache[`${s}::${id}`]=d; const attendees=(d.attendees&&d.attendees.length)?d.attendees.map(n=>`<span class="attendee-pill">${esc(n)}</span>`).join(''):'<span class="muted">No attendees found.</span>'; document.getElementById('drawerOrderSub').textContent=`${s} • ${d.event||ev||'Order Details'}`; document.getElementById('orderDrawerBody').innerHTML=`<div class="detail-card-grid"><div class="detail-card"><div class="detail-label">Order Status</div><div class="detail-value">${esc(d.status||'Unknown')}</div></div><div class="detail-card"><div class="detail-label">Area / Section</div><div class="detail-value">${esc(d.area||'Unknown')}</div></div><div class="detail-card"><div class="detail-label">Quantity</div><div class="detail-value">${esc(d.quantity||'Unknown')}</div></div><div class="detail-card"><div class="detail-label">Price per Ticket</div><div class="detail-value">${esc(d.price_per_ticket||'Unknown')}</div></div><div class="detail-card"><div class="detail-label">Total Price</div><div class="detail-value">${esc(d.total_price||'Unknown')}</div></div><div class="detail-card"><div class="detail-label">Shipping</div><div class="detail-value">${esc(d.shipping||'Unknown')}</div></div><div class="detail-card"><div class="detail-label">Customer</div><div class="detail-value">${esc(d.customer_name||'Unknown')}</div></div><div class="detail-card"><div class="detail-label">Phone</div><div class="detail-value">${esc(d.customer_phone||'Unknown')}</div></div><div class="detail-card"><div class="detail-label">League</div><div class="detail-value">${esc(d.league||'Unknown')}</div></div><div class="detail-card"><div class="detail-label">Venue</div><div class="detail-value">${esc(d.venue||'Unknown')}</div></div><div class="detail-card"><div class="detail-label">Event Date</div><div class="detail-value">${esc(d.event_date||'Unknown')}</div></div></div><div class="drawer-section"><div class="drawer-section-title">Attendees</div><div class="attendee-list">${attendees}</div></div>${renderLineItemsTable(d.line_items||[])}`; refreshDerivedViews(); } catch(e){ document.getElementById('orderDrawerBody').innerHTML=`<div class="drawer-error"><div class="drawer-error-title">Failed to load order details</div><div>${esc(e.message||'Unknown error')}</div></div>`; }}

function openOrdersTab(eventName = null, sourceName = null) {
  if (eventName && sourceName) {
    selectedEvent = eventName;
    selectedSource = sourceName;
    refreshDerivedViews();
  }
  const links = document.querySelectorAll('.nav-link');
  const pages = document.querySelectorAll('.tab-page');
  pages.forEach(p => p.classList.remove('active'));
  links.forEach(l => l.classList.remove('active'));
  document.getElementById('ordersTab').classList.add('active');
  const navLink = document.querySelector('.nav-link[data-tab="ordersTab"]');
  if (navLink) navLink.classList.add('active');
}

async function refreshCharts(){ try{ const data=await api('/api/chart-data'); renderHourChart(data.hourly.labels, data.hourly.values); renderDayChart(data.daily.labels, data.daily.values);}catch(e){console.error(e);} }
function refreshDerivedViews() {
  const groups = groupOrdersByEventSource(latestOrdersData);
  renderEventAccordion(groups);
  renderCustomerAnalytics(latestOrdersData);
  renderActivity(latestOrdersData);
}

async function refresh(){
  const data=await api('/api/state');
  currentRole=data.current_role||'member'; 
  currentUser=data.current_user||''; 
  latestOrdersData=data.orders||[]; 
  const now = new Date();
  latestSentData = (data.sent_orders || []).filter(r => {
    const d = parseDate(r.sale_date);
    if (!d) return true;
    return (now - d) <= 24 * 60 * 60 * 1000;
  });
  document.getElementById('totalOrdersCount').textContent=data.summary.order_count??0;
  document.getElementById('processedOrdersCount').textContent=data.summary.processed_count??0;
  document.getElementById('cancelledOrdersCount').textContent=data.summary.cancelled_count??0;
  document.getElementById('pendingOrdersCount').textContent=data.summary.pending_count??0;
  document.getElementById('sessionStatus').textContent=data.summary.session_status||'-';
  
  const h=document.getElementById('liveSessionStatus'); if(h) h.textContent=data.summary.session_status||'-';
  const lastO=document.getElementById('lastOrder'); if(lastO) lastO.textContent=data.summary.last_order_info||'-';
  
  document.getElementById('currentUserName').textContent=currentUser||'-';
  
  const inact=document.getElementById('inactivityInfo'); if(inact) inact.textContent=`${data.inactivity_minutes||20} min inactivity`;
  const interval=document.getElementById('intervalMinutesSettings'); if(interval) interval.value=data.summary.settings?.interval_minutes??30;
  
  const monitoringToggle = document.getElementById('monitoringToggle');
  const statusText = document.getElementById('monitoringStatusText');
  if(monitoringToggle && statusText) {
    monitoringToggle.checked = data.summary.running;
    if(data.summary.running) {
      statusText.innerText = "Monitoring ON";
      statusText.style.color = "#10b981";
    } else {
      statusText.innerText = "Monitoring OFF";
      statusText.style.color = "var(--muted)";
    }
  }
  
  setStatusText(data.summary.status||'Stopped'); setSleepButtons(data.summary.settings?.sleep_window_enabled); renderSourceBreakdown(data.summary.source_counts||{}); renderRecentSent(latestSentData); renderMembers(data.members||[]); refreshDerivedViews();
  
  try {
    const totalsResponse = await api('/api/event-totals');
    if (totalsResponse.ok) {
        renderActiveEvents(totalsResponse.totals);
    }
  } catch (e) {
    console.error("Failed to load event totals", e);
  }
}

async function startBot(){ try{ await api('/api/start',{method:'POST'}); await fullRefresh(); }catch(e){ alert(e.message);} }
async function stopBot(){ try{ await api('/api/stop',{method:'POST'}); await fullRefresh(); }catch(e){ alert(e.message);} }
async function checkNow(){ try{ await api('/api/check-now',{method:'POST'}); setTimeout(fullRefresh,1000);}catch(e){ alert(e.message);} }

async function toggleMonitoring() {
  const toggle = document.getElementById('monitoringToggle');
  if(toggle.checked) {
    await startBot();
  } else {
    await stopBot();
  }
}

async function checkTicketsshopOrders() {
  const btn = document.getElementById('btnCheckTicketsshop');
  if(!btn) return;
  const originalText = btn.innerHTML;
  btn.innerHTML = 'CHECKING...';
  btn.disabled = true;
  try {
    await api('/api/check-ticketsshop', {method:'POST'});
  } catch(e) {
    alert(`Error checking Ticketsshop: ${e.message}`);
  }
  btn.innerHTML = originalText;
  btn.disabled = false;
  setTimeout(fullRefresh, 1000);
}
async function toggleSetting(name){ try{ await api('/api/toggle-setting',{method:'POST', body:JSON.stringify({name})}); await refresh(); }catch(e){ alert(e.message);} }
async function saveSettingsFromSettings(){ try{ await api('/api/settings',{method:'POST',body:JSON.stringify({interval_minutes:document.getElementById('intervalMinutesSettings').value})}); await refresh(); }catch(e){ alert(e.message);} }
async function addMember(){ try{ if(currentRole!=='admin'){ alert('Admin access required'); return; } const username=document.getElementById('memberUsername').value.trim(); const password=document.getElementById('memberPassword').value.trim(); const role=document.getElementById('memberRole').value; if(!username||!password){ alert('Username and password are required'); return; } await api('/api/users/add',{method:'POST',body:JSON.stringify({username,password,role})}); document.getElementById('memberUsername').value=''; document.getElementById('memberPassword').value=''; document.getElementById('memberRole').value='member'; await refresh(); alert('Member added successfully'); }catch(e){ alert(e.message);} }
async function resetPasswordPrompt(username){ const password=prompt(`Enter new password for ${username}:`); if(!password) return; try{ await api('/api/users/reset-password',{method:'POST',body:JSON.stringify({username,password})}); alert('Password updated'); await refresh(); }catch(e){ alert(e.message);} }
async function changeRole(username, role){ try{ await api('/api/users/change-role',{method:'POST',body:JSON.stringify({username,role})}); await refresh(); }catch(e){ alert(e.message);} }
async function toggleUserActive(username){ try{ await api('/api/users/toggle-active',{method:'POST',body:JSON.stringify({username})}); await refresh(); }catch(e){ alert(e.message);} }
async function deleteUser(username){ if(!confirm(`Delete user ${username}?`)) return; try{ await api('/api/users/delete',{method:'POST',body:JSON.stringify({username})}); await refresh(); }catch(e){ alert(e.message);} }
function setTheme(theme){ if(theme==='dark'){ document.body.classList.add('dark'); localStorage.setItem('orderticketmonitor-theme','dark'); } else { document.body.classList.remove('dark'); localStorage.setItem('orderticketmonitor-theme','light'); }}
function loadTheme(){ setTheme(localStorage.getItem('orderticketmonitor-theme')||'light'); }
function setupTabs(){ const links=document.querySelectorAll('.nav-link'); const pages=document.querySelectorAll('.tab-page'); links.forEach(link=>link.addEventListener('click',e=>{ e.preventDefault(); links.forEach(l=>l.classList.remove('active')); pages.forEach(p=>p.classList.remove('active')); link.classList.add('active'); const page=document.getElementById(link.dataset.tab); if(page) page.classList.add('active'); })); }
async function fullRefresh(){ await refresh(); await refreshCharts(); }
loadTheme(); setupTabs(); updateGreeting(); fullRefresh(); setInterval(fullRefresh,4000); setInterval(updateGreeting,60000);
