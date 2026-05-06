import os
import json
import threading
from datetime import datetime, timedelta
from flask import jsonify, request, g, render_template
from functools import wraps
import jwt
from sqlalchemy import or_, func

from core.helpers import clean_text, parse_sale_datetime, standardize_status, normalize_event_name
from core.users import verify_user as check_user
import extensions as context
from config import JWT_SECRET, PLATFORM_CONFIGS, INACTIVITY_MINUTES, REMEMBER_DAYS
from database import get_db, DBPlatform, DBOrder, DBAppEvent, DBEvent, DBOrderAlert, DBTicketshopCheck, DBOrderStatusCheck, DBOrderStatusCheckItem
from services.order_service import bot_worker

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("token")
        if not token: return jsonify({"error": "Unauthorized"}), 401
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            g.current_user = data
        except: return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def register_routes(app):
    def log_route(msg):
        if context.state: context.state.log(f"API: {msg}")

    @app.route("/")
    def index():
        token = request.cookies.get("token")
        if not token: return render_template("login.html")
        try:
            jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            return render_template("index.html")
        except: return render_template("login.html")

    @app.route("/login")
    def login(): return render_template("login.html")

    @app.route("/logout")
    def logout():
        resp = app.make_response(render_template("login.html"))
        resp.delete_cookie("token")
        return resp

    @app.route("/api/login", methods=["POST"])
    def api_login():
        try:
            data = request.json
            u, p, rem = data.get("username"), data.get("password"), data.get("remember", False)
            user = check_user(u, p)
            if user:
                exp = datetime.utcnow() + timedelta(days=REMEMBER_DAYS if rem else 1)
                token = jwt.encode({"username": u, "role": user["role"], "exp": exp}, JWT_SECRET, algorithm="HS256")
                resp = jsonify({"ok": True, "role": user["role"]})
                resp.set_cookie("token", token, httponly=True, samesite="Strict", max_age=int(timedelta(days=REMEMBER_DAYS if rem else 1).total_seconds()))
                return resp
            return jsonify({"error": "Invalid credentials"}), 401
        except Exception as e: return jsonify({"error": str(e)}), 500

    @app.route("/api/start", methods=["POST"])
    @login_required
    def api_start_bot():
        if context.state.running: return jsonify({"ok": True, "message": "Already running"})
        context.state.stop_event.clear()
        context.state.worker_thread = threading.Thread(target=bot_worker, daemon=True)
        context.state.worker_thread.start()
        return jsonify({"ok": True, "message": "Bot started"})

    @app.route("/api/stop", methods=["POST"])
    @login_required
    def api_stop_bot():
        context.state.stop_event.set()
        return jsonify({"ok": True})

    @app.get("/api/state")
    @login_required
    def api_state():
        return jsonify({
            "current_user": g.current_user["username"],
            "current_role": g.current_user["role"],
            "summary": context.state.summary()
        })

    @app.get("/api/db-health")
    def api_db_health():
        db = get_db()
        if not db: return jsonify({"database": "json", "connected": False, "orders_count": 0})
        try:
            count = db.query(DBOrder).count()
            return jsonify({"database": "postgresql", "connected": True, "orders_count": count})
        except Exception as e:
            return jsonify({"database": "json", "connected": False, "orders_count": 0, "error": str(e)})
        finally: db.close()

    @app.get("/api/dashboard/stats")
    @login_required
    def api_get_dashboard_stats():
        db = get_db()
        if not db: return jsonify({"total": 0, "pending": 0, "cancelled": 0, "resold": 0, "completed": 0})
        try:
            total = db.query(DBOrder).filter(DBOrder.normalized_status != "cancelled").count()
            pending = db.query(DBOrder).filter(DBOrder.normalized_status == "pending").count()
            cancelled = db.query(DBOrder).filter(DBOrder.normalized_status == "cancelled").count()
            resold = db.query(DBOrder).filter(or_(DBOrder.normalized_status == "resold", DBOrder.normalized_status == "presold")).count()
            completed = db.query(DBOrder).filter(or_(DBOrder.normalized_status == "completed", DBOrder.normalized_status == "processed")).count()
            return jsonify({"total": total, "pending": pending, "cancelled": cancelled, "resold": resold, "completed": completed})
        except: return jsonify({"total": 0, "pending": 0, "cancelled": 0, "resold": 0, "completed": 0})
        finally: db.close()

    @app.get("/api/orders")
    @login_required
    def api_get_orders():
        db = get_db()
        if not db: return jsonify([])
        try:
            orders = db.query(DBOrder).order_by(DBOrder.id.desc()).all()
            return jsonify([{
                "id": o.id, "order_number": o.order_number, "platform": o.platform, "event_name": o.event_name or "-",
                "event_date": o.event_date.strftime("%Y-%m-%d %H:%M:%S") if o.event_date else "-",
                "customer_name": o.customer_name or "-", "quantity": o.quantity or 1,
                "total_value": str(o.total_value or 0), "currency": o.currency or "£",
                "normalized_status": o.normalized_status or "pending", "sale_date": o.sale_date.strftime("%Y-%m-%d %H:%M:%S") if o.sale_date else "-"
            } for o in orders])
        except Exception as e: return jsonify({"error": str(e)}), 500
        finally: db.close()

    @app.get("/api/events/active")
    @login_required
    def api_get_events_active():
        db = get_db()
        if not db: return jsonify([])
        try:
            # Group by event_name + platform
            # total_value sum excluding cancelled
            events = db.query(
                DBOrder.event_name, DBOrder.platform, DBOrder.event_date,
                func.count(DBOrder.id).label("order_count"),
                func.sum(DBOrder.quantity).label("ticket_count"),
                func.sum(func.coalesce(DBOrder.total_value, 0)).filter(DBOrder.normalized_status != "cancelled").label("total_value"),
                func.max(DBOrder.currency).label("currency")
            ).group_by(DBOrder.event_name, DBOrder.platform, DBOrder.event_date).all()
            
            return jsonify([{
                "event_name": r.event_name or "-", "source": r.platform, 
                "event_date": r.event_date.strftime("%Y-%m-%d %H:%M:%S") if r.event_date else "-", 
                "order_count": r.order_count, "ticket_count": int(r.ticket_count or 0), 
                "total_value": str(r.total_value or 0), "currency": r.currency or "£",
                "status": "Active" # Or whatever logic for status summary
            } for r in events])
        except Exception as e: return jsonify({"error": str(e)}), 500
        finally: db.close()

    @app.get("/api/orders/<platform>/<order_number>")
    @login_required
    def api_get_order_details(platform, order_number):
        db = get_db()
        if not db: return jsonify({"ok": False, "error": "Database not available"}), 200
        try:
            dbo = db.query(DBOrder).filter(DBOrder.platform == platform, DBOrder.order_number == order_number).first()
            error_msg = None
            if platform == "LiveTicketGroup" and (not dbo or not dbo.details_fetched_at):
                from platforms.liveticketgroup import get_ltg_adapter
                adapter = get_ltg_adapter()
                if adapter:
                    try:
                        details = adapter.fetch_order_details(order_number)
                        if details:
                            if not dbo: dbo = DBOrder(platform=platform, order_number=order_number); db.add(dbo)
                            for k, v in details.items():
                                if hasattr(dbo, k) and v is not None: setattr(dbo, k, v)
                            if dbo.billing_full_name: dbo.customer_name = dbo.billing_full_name
                            if dbo.total_amount is not None: dbo.total_value = dbo.total_amount
                            dbo.normalized_status = standardize_status(dbo.raw_status, source=platform, resale_status=dbo.resale_status, pod_status=dbo.pod_status)
                            dbo.details_fetched_at = datetime.utcnow(); db.commit()
                        else: error_msg = "Order details not found on platform"
                    except Exception as e: error_msg = f"Scraping error: {str(e)}"
            
            if not dbo: return jsonify({"ok": False, "error": error_msg or "Order not found"}), 200
            data = {
                "id": dbo.order_number, "platform": dbo.platform, "event_name": dbo.event_name or "-",
                "event_date": dbo.event_date.strftime("%Y-%m-%d %H:%M:%S") if dbo.event_date else "-",
                "customer_name": dbo.billing_full_name or dbo.customer_name or "-", "mobile_number": dbo.billing_mobile or dbo.mobile_number or "-",
                "email": dbo.email or "-", "sale_date": dbo.sale_date.strftime("%Y-%m-%d %H:%M:%S") if dbo.sale_date else "-",
                "normalized_status": dbo.normalized_status, "category": dbo.category or "-",
                "section": dbo.section or "-", "row_name": dbo.row_name or "-", "seat_number": dbo.seat_number or "-",
                "quantity": dbo.quantity or 1, "total_value": str(dbo.total_amount or dbo.total_value or 0),
                "list_price": str(dbo.list_price_per_ticket or 0), "shipping": f"{dbo.shipping_type or 'Unknown'} ({str(dbo.shipping_amount or 0)})",
                "currency": dbo.currency or "£", "delivery_status": dbo.delivery_status or "-", "pod_status": dbo.pod_status or "Pending",
                "broker_name": getattr(dbo, "broker_name", "-") or "-", "source_url": dbo.source_url or "-"
            }
            return jsonify({"ok": not error_msg, "error": error_msg, "data": data})
        except Exception as e: return jsonify({"ok": False, "error": str(e)}), 200
        finally: db.close()

    @app.get("/api/orders/search")
    @login_required
    def api_orders_search():
        db = get_db()
        if not db: return jsonify([])
        try:
            platform = request.args.get("platform")
            event_name = request.args.get("event_name")
            query = db.query(DBOrder)
            if platform: query = query.filter(DBOrder.platform == platform)
            if event_name: query = query.filter(DBOrder.event_name.ilike(f"%{event_name}%"))
            orders = query.all()
            return jsonify([{
                "id": o.order_number, "customer": o.customer_name or "-",
                "sale_date": o.sale_date.strftime("%Y-%m-%d %H:%M:%S") if o.sale_date else "-",
                "status": o.normalized_status or "Pending"
            } for o in orders])
        except Exception as e: return jsonify({"error": str(e)}), 500
        finally: db.close()

    @app.post("/api/check-order-status")
    @login_required
    def api_check_order_status():
        data = request.json
        platform = data.get("platform")
        event_name = data.get("eventName")
        if not platform or not event_name:
            return jsonify({"ok": False, "error": "Platform and Event Name required"})
        
        from platforms.registry import platform_adapters
        adapter = next((a for a in platform_adapters if a.source_name == platform), None)
        if not adapter: return jsonify({"ok": False, "error": f"Adapter for {platform} not found"})
        
        try:
            if hasattr(adapter, "fetch_orders_by_event"):
                rows = adapter.fetch_orders_by_event(event_name)
            else:
                rows, _ = adapter.fetch_orders()
                if rows: rows = [r for r in rows if event_name.lower() in str(r.get("event", "")).lower()]
            
            results = []
            if rows:
                for r in rows:
                    results.append({
                        "id": r.get("id"), "customer": r.get("customer"),
                        "sale_date": r.get("sale_date"), "status": r.get("status")
                    })
            return jsonify({"ok": True, "results": results})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    @app.post("/api/sync/live-ticket-group")
    @login_required
    def api_sync_ltg():
        try:
            from services.order_service import check_all_platforms_once
            errors = check_all_platforms_once(set())
            if errors:
                return jsonify({"ok": False, "error": " | ".join(errors)})
            return jsonify({"ok": True, "message": "Successfully synced LiveTicketGroup orders"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    @app.route("/api/platform-states", methods=["POST"])
    @login_required
    def api_save_platform_states():
        context.state.settings.update(request.json)
        context.state.save_settings()
        return jsonify({"ok": True})

    @app.post("/api/system/reset")
    @login_required
    def api_system_reset():
        from database import engine, Base
        try:
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            from database import init_db
            init_db()
            context.state.log("System reset complete. All old data cleared.")
            return jsonify({"ok": True, "message": "System reset successfully"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    @app.post("/api/test-order-telegram")
    @login_required
    def api_test_telegram():
        try:
            from services.telegram_service import send_telegram
            msg = (
                "🟢 NEW ORDER\n\n"
                "Source: LiveTicketGroup\n"
                "Event: Arsenal vs Chelsea (TEST)\n"
                "Date: 2026-05-15 20:00:00\n"
                "Order Number: TEST-12345\n"
                "Name: John Doe"
            )
            send_telegram(msg)
            return jsonify({"ok": True})
        except Exception as e: return jsonify({"error": str(e)}), 500

    @app.post("/api/system/check-ticketsshop")
    @login_required
    def api_check_ticketsshop():
        try:
            db = get_db()
            ltg_orders = db.query(DBOrder).filter(DBOrder.platform == "LiveTicketGroup").all()
            if not ltg_orders:
                return jsonify({"ok": True, "message": "No active LiveTicketGroup orders to check."})
                
            orders_to_check = [{"id": o.order_number, "event": o.event_name} for o in ltg_orders]
            
            from services.inventory_service import check_ticketsshop_bulk
            result = check_ticketsshop_bulk(orders_to_check)
            
            missing = result.get("missing", [])
            listed = result.get("listed", [])
            
            if missing:
                from services.telegram_service import send_telegram
                alert_lines = ["⚠️ TICKETSHOP MISSING ORDERS ALERT\n", "The following active LTG orders were NOT found on Ticketshop:\n"]
                for m in missing:
                    alert_lines.append(f"• {m['id']} - {m['event']}")
                send_telegram("\n".join(alert_lines))
                
            return jsonify({"ok": True, "listed": len(listed), "missing": len(missing), "missing_orders": missing})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})
