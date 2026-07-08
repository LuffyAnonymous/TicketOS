import time
import threading
from datetime import datetime
import extensions as context
from core.helpers import clean_text, parse_sale_datetime, normalize_event_name, standardize_status, to_number, parse_event_datetime
from services.telegram_service import send_telegram
from database import get_db, DBOrder, DBOrderAlert, DBEvent

def check_all_platforms_once(seen_keys):
    all_rows = []
    mon = context.state.settings
    errors = []
    for adapter in context.platform_adapters:
        try:
            if not mon.get(f"monitor_{adapter.source_name.lower()}", True): continue
            rows, _ = adapter.fetch_orders()
            all_rows.extend(rows)
            context.state.log(f"{adapter.source_name}: scraped {len(rows)} orders")
        except Exception as e:
            err_msg = str(e)
            context.state.log(f"{adapter.source_name} scraper error: {err_msg}")
            errors.append(f"{adapter.source_name}: {err_msg}")

    db = get_db(); current_keys = set(); now = datetime.now()
    if not db: return errors

    try:
        # Step 1: Normalize event names across the batch
        event_name_map = {}
        for r in all_rows:
            name, d = normalize_event_name(r.get("event")), parse_event_datetime(r.get("event_date"))
            if name and d: event_name_map[(r.get("source"), d)] = name
        
        for r in all_rows:
            source, oid = clean_text(r.get("source", "")), clean_text(r.get("id", ""))
            if not source or not oid: continue
            key = f"{source}::{oid}"; current_keys.add(key)
            
            e_date = parse_event_datetime(r.get("event_date"))
            s_date = parse_sale_datetime(r.get("sale_date"))
            ev_name = normalize_event_name(r.get("event"))
            
            if not ev_name: ev_name = "Unknown Event"
            
            # Validation: Prevent saving backend errors as event names
            invalid_keywords = ["Exception", "Refresh token", "System.Web", "TokenManager", "stack trace"]
            if any(k.lower() in ev_name.lower() for k in invalid_keywords):
                context.state.log(f"Invalid event name detected (contains error text) for order {oid}. Skipping.")
                continue

            dbo = db.query(DBOrder).filter(DBOrder.platform == source, DBOrder.order_number == oid).first()
            pod = dbo.pod_status if dbo else "Pending"
            dash_status = standardize_status(r.get("status"), source=source, resale_status=r.get("resale_status"), pod_status=pod)
            
            if not dbo:
                dbo = DBOrder(
                    platform=source, order_number=oid, event_name=ev_name, event_date=e_date,
                    customer_name=r.get("customer"), sale_date=s_date, raw_status=r.get("status"),
                    resale_status=r.get("resale_status"), normalized_status=dash_status,
                    total_value=r.get("total_price"), currency=r.get("currency", "£"), quantity=r.get("quantity", 1),
                    is_visible_on_platform=True, last_seen_at=datetime.utcnow(), is_past_event=(e_date and e_date < now) or False
                )
                db.add(dbo); db.flush()
                
                # Fetch full details immediately for the Telegram alert
                try:
                    adapter = next((a for a in context.platform_adapters if a.source_name == source), None)
                    if adapter:
                        details = adapter.fetch_order_details(oid)
                        if details:
                            for k, v in details.items():
                                if hasattr(dbo, k) and v is not None: setattr(dbo, k, v)
                            if dbo.billing_full_name: dbo.customer_name = dbo.billing_full_name
                            if dbo.total_amount is not None: dbo.total_value = dbo.total_amount
                            dbo.normalized_status = standardize_status(dbo.raw_status, source=source, resale_status=dbo.resale_status, pod_status=dbo.pod_status)
                            dbo.details_fetched_at = datetime.utcnow()
                            db.flush()
                            # Final validation check after details fetch
                            if any(k.lower() in str(dbo.event_name).lower() for k in invalid_keywords):
                                dbo.event_name = "Unknown Event"
                except Exception as e:
                    if "session expired" in str(e).lower():
                        raise e  # Propagate to halt sync and show clean UI message
                    context.state.log(f"Failed to fetch details for new order {oid}: {e}")

                # Excel Exporter integration for LiveTicketGroup
                if source == "LiveTicketGroup":
                    try:
                        from platforms.liveticketgroup.customer_scraper import scrape_customer_details
                        from services.excel_exporter import export_customer_details
                        cust_details = scrape_customer_details(oid)
                        if cust_details:
                            export_customer_details(cust_details)
                    except Exception as excel_err:
                        context.state.log(f"Excel Exporter failed for order {oid}: {excel_err}")

                # Clean text-only NEW order alert matching exactly user request
                msg = (
                    f"🟢 NEW ORDER\n\n"
                    f"Source: {source}\n"
                    f"Event: {dbo.event_name or '-'}\n"
                    f"Date: {dbo.sale_date.strftime('%Y-%m-%d %H:%M:%S') if dbo.sale_date else '-'}\n"
                    f"Order Number: {oid}\n"
                    f"Name: {dbo.customer_name or '-'}"
                )
                db.add(DBOrderAlert(platform=source, order_number=oid, event_name=dbo.event_name, alert_type="new_order", alert_message=msg))
                send_telegram(msg); context.state.log(f"{source}: detected NEW order {oid}")
            else:
                if ev_name: dbo.event_name = ev_name
                dbo.raw_status = r.get("status"); dbo.resale_status = r.get("resale_status")
                dbo.normalized_status = dash_status
                dbo.is_visible_on_platform = True; dbo.last_seen_at = datetime.utcnow()
                dbo.is_past_event = (e_date and e_date < now) or False
                if r.get("total_price") is not None: dbo.total_value = r.get("total_price")
                if r.get("currency"): dbo.currency = r.get("currency")
                if r.get("quantity"): dbo.quantity = r.get("quantity")

            if ev_name:
                ev = db.query(DBEvent).filter(DBEvent.platform == source, DBEvent.event_name == ev_name).first()
                if not ev: 
                    db.add(DBEvent(platform=source, event_name=ev_name, event_date=e_date, is_past_event=dbo.is_past_event))
                    db.flush()
                else: 
                    ev.event_date = e_date; ev.is_past_event = dbo.is_past_event
        
        # Step 2: Detect disappeared orders
        disappeared = db.query(DBOrder).filter(DBOrder.platform == "LiveTicketGroup", DBOrder.is_visible_on_platform == True, DBOrder.is_past_event == False).all()
        for dbo in disappeared:
            if f"{dbo.platform}::{dbo.order_number}" not in current_keys:
                dbo.is_visible_on_platform = False
                if dbo.normalized_status not in ("completed", "cancelled", "resold"):
                    dbo.normalized_status = "completed"
                    context.state.log(f"Platform Order {dbo.order_number} disappeared → marked COMPLETED")
        
        db.commit()
    except Exception as e:
        db.rollback(); context.state.log(f"Sync Error: {e}")
        errors.append(f"Database Error: {str(e)}")
    finally:
        db.close()
    
    return errors

def execute_check_cycle(seen_keys):
    context.state.set_last_check()
    check_all_platforms_once(seen_keys)

def bot_worker():
    context.state.running = True
    context.state.log("Bot worker started (DB-only mode)")
    try:
        while not context.state.stop_event.is_set():
            seen = context.state.load_seen_orders()
            execute_check_cycle(seen)
            interval = int(context.state.settings.get("interval_minutes", 30)) * 60
            for _ in range(interval):
                if context.state.stop_event.is_set(): break
                time.sleep(1)
    finally:
        context.state.running = False; context.state.log("Bot stopped")
