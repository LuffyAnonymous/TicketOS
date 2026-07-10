import jwt
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, render_template, g, request
from sqlalchemy import or_, func
from config import JWT_SECRET
from database import get_db, DBOrder, DBAppEvent
import extensions as context
from routes.auth_routes import login_required
from core.users import load_users, safe_user_view

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route("/")
def index():
    token = request.cookies.get("token")
    if not token:
        return render_template("login.html")
    try:
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return render_template("index.html")
    except Exception:
        return render_template("login.html")

@dashboard_bp.route("/api/state", methods=["GET"])
@login_required
def api_state():
    scheduler_status = "Stopped"
    if context.scheduler:
        scheduler_status = getattr(context.scheduler, "_status", "Stopped")
        if scheduler_status == "Running" and not context.state.running:
            scheduler_status = "Stopped"
    return jsonify({
        "current_user": g.current_user["username"],
        "current_role": g.current_user["role"],
        "summary": context.state.summary() if context.state else {},
        "members": [safe_user_view(u) for u in load_users()],
        "scheduler": {
            "status": scheduler_status
        }
    })


@dashboard_bp.route("/api/db-health", methods=["GET"])
def api_db_health():
    db = get_db()
    if not db:
        return jsonify({"database": "json", "connected": False, "orders_count": 0})
    try:
        count = db.query(DBOrder).count()
        from database import get_engine_type
        return jsonify({"database": get_engine_type(), "connected": True, "orders_count": count})
    except Exception as e:
        return jsonify({"database": "json", "connected": False, "orders_count": 0, "error": str(e)})
    finally:
        db.close()

@dashboard_bp.route("/api/dashboard/stats", methods=["GET"])
@login_required
def api_get_dashboard_stats():
    db = get_db()
    stats = {
        "today_orders": 0,
        "pending": 0,
        "completed": 0,
        "cancelled": 0,
        "revenue": 0.0,
        "currency": "£",
        "active_platforms": 0,
        "last_sync_time": "-",
        "scraper_errors": 0
    }

    # 1. Last Sync Time
    if context.scheduler and context.scheduler.last_run_time:
        stats["last_sync_time"] = context.scheduler.last_run_time
    elif context.state and "last_check_time" in context.state.settings:
        stats["last_sync_time"] = context.state.settings["last_check_time"]

    # 2. Scraper Errors (last 24 hours)
    if db:
        try:
            from datetime import datetime, timedelta
            from database import DBAppEvent
            one_day_ago = datetime.utcnow() - timedelta(days=1)
            stats["scraper_errors"] = db.query(DBAppEvent).filter(
                DBAppEvent.level == "ERROR",
                DBAppEvent.created_at >= one_day_ago
            ).count()
        except:
            pass

    if not db:
        return jsonify(stats)

    try:
        from datetime import datetime, time as datetime_time
        # 3. Today's orders count
        today_start = datetime.combine(datetime.today(), datetime_time.min)
        stats["today_orders"] = db.query(DBOrder).filter(DBOrder.sale_date >= today_start).count()

        # 4. Status counts
        stats["pending"] = db.query(DBOrder).filter(DBOrder.normalized_status == "pending").count()
        stats["completed"] = db.query(DBOrder).filter(DBOrder.normalized_status == "completed").count()
        stats["cancelled"] = db.query(DBOrder).filter(DBOrder.normalized_status == "cancelled").count()

        # 5. Revenue
        revenue_val = db.query(func.sum(DBOrder.total_value)).filter(DBOrder.normalized_status != "cancelled").scalar()
        stats["revenue"] = float(revenue_val) if revenue_val is not None else 0.0

        # 6. Active platforms
        stats["active_platforms"] = db.query(DBOrder.platform).distinct().count()

        return jsonify(stats)
    except Exception:
        return jsonify(stats)
    finally:
        db.close()

@dashboard_bp.route("/api/events/active", methods=["GET"])
@login_required
def api_get_events_active():
    db = get_db()
    if not db:
        return jsonify([])
    try:
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
            "status": "Active"
        } for r in events])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@dashboard_bp.route("/api/customers", methods=["GET"])
@login_required
def api_get_customers():
    db = get_db()
    if not db:
        return jsonify([])
    try:
        orders = db.query(DBOrder).all()
        profiles = {}
        
        for o in orders:
            email = (o.email or "").strip().lower()
            mobile = (o.mobile_number or "").strip()
            name = (o.customer_name or "").strip()
            
            if not name or name == "-":
                continue
                
            key = None
            if email and email not in ("n/a", "none", ""):
                key = f"email:{email}"
            elif mobile and mobile not in ("n/a", "none", ""):
                key = f"mobile:{mobile.lower()}"
            else:
                key = f"name:{name.lower()}"
                
            val = float(o.total_value) if o.total_value is not None else 0.0
            
            if key not in profiles:
                profiles[key] = {
                    "key": key,
                    "name": o.customer_name or o.billing_full_name or "-",
                    "email": o.email or "N/A",
                    "phone": o.mobile_number or o.billing_mobile or "N/A",
                    "total_orders": 0,
                    "lifetime_spend": 0.0,
                    "currency": o.currency or "£",
                    "last_purchase_date": None,
                    "events": {},
                    "platforms": set(),
                    "orders": []
                }
                
            p = profiles[key]
            
            if p["email"] in ("N/A", "") and o.email:
                p["email"] = o.email
            if p["phone"] in ("N/A", "") and o.mobile_number:
                p["phone"] = o.mobile_number
            if p["name"] in ("-", "") and (o.customer_name or o.billing_full_name):
                p["name"] = o.customer_name or o.billing_full_name
                
            p["total_orders"] += 1
            p["lifetime_spend"] += val
            
            if o.platform:
                p["platforms"].add(o.platform)
            if o.event_name and o.event_name != "-":
                p["events"][o.event_name] = p["events"].get(o.event_name, 0) + 1
            if o.sale_date:
                if not p["last_purchase_date"] or o.sale_date > p["last_purchase_date"]:
                    p["last_purchase_date"] = o.sale_date
                    
            p["orders"].append({
                "order_number": o.order_number,
                "platform": o.platform,
                "event_name": o.event_name or "-",
                "sale_date": o.sale_date.strftime("%Y-%m-%d %H:%M:%S") if o.sale_date else "-",
                "quantity": o.quantity or 1,
                "total_value": str(o.total_value or 0),
                "currency": o.currency or "£",
                "normalized_status": o.normalized_status or "pending"
            })
            
        customer_list = []
        search_query = request.args.get("search", "").lower().strip()
        
        for p in profiles.values():
            fav_event = "-"
            if p["events"]:
                fav_event = max(p["events"], key=p["events"].get)
                
            if search_query:
                in_name = search_query in p["name"].lower()
                in_email = search_query in p["email"].lower()
                in_phone = search_query in p["phone"].lower()
                if not (in_name or in_email or in_phone):
                    continue
                    
            customer_list.append({
                "key": p["key"],
                "name": p["name"],
                "email": p["email"],
                "phone": p["phone"],
                "total_orders": p["total_orders"],
                "lifetime_spend": round(p["lifetime_spend"], 2),
                "currency": p["currency"],
                "last_purchase_date": p["last_purchase_date"].strftime("%Y-%m-%d %H:%M:%S") if p["last_purchase_date"] else "-",
                "favorite_event": fav_event,
                "platforms": ", ".join(p["platforms"]),
                "orders": p["orders"]
            })
            
        return jsonify(customer_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@dashboard_bp.route("/api/dashboard/health", methods=["GET"])
@login_required
def api_dashboard_health():
    db = get_db()
    if not db:
        return jsonify({"error": "Database not connected"}), 500
    try:
        from database import DBPlatform
        # Determine mismatch count
        mismatches = db.query(DBOrder).filter(
            DBOrder.platform == "LiveTicketGroup",
            DBOrder.ticketshop_status == "missing",
            DBOrder.is_past_event == False
        ).count()

        # Read enabled state from DB (authoritative source)
        def platform_enabled(name):
            row = db.query(DBPlatform).filter(DBPlatform.name == name).first()
            return row.is_enabled if row else True

        ltg_enabled = platform_enabled("LiveTicketGroup")
        ftn_enabled = platform_enabled("FootballTicketNet")
        ticketshop_enabled = platform_enabled("Ticketshop")

        ltg_status = "running" if ltg_enabled else "disabled"
        ftn_status = "running" if ftn_enabled else "disabled"
        ticketshop_status = "waiting" if ticketshop_enabled else "disabled"

        if context.scheduler:
            # Override with actual scheduler run failure statuses if any
            history = context.scheduler.job_history
            for job in reversed(history):
                msg_lower = job.get("message", "").lower()
                if "liveticketgroup" in msg_lower and ltg_status == "running" and job.get("status") in ("error", "Failed"):
                    ltg_status = "error"
                if "footballticketnet" in msg_lower and ftn_status == "running" and job.get("status") in ("error", "Failed"):
                    ftn_status = "error"

        from config import ORDER_BOT_TOKEN, ORDER_CHAT_ID
        telegram_status = "connected" if (ORDER_BOT_TOKEN and ORDER_CHAT_ID) else "disconnected"

        return jsonify({
            "liveticketgroup": ltg_status,
            "footballticketnet": ftn_status,
            "ticketshop": ticketshop_status,
            "mismatches": mismatches,
            "telegram": telegram_status
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@dashboard_bp.route("/api/dashboard/activity", methods=["GET"])
@login_required
def api_dashboard_activity():
    db = get_db()
    if not db:
        return jsonify({"error": "Database not connected"}), 500
    try:
        # Exclude werkzeug HTTP access logs — they are noise, not operations events
        events = db.query(DBAppEvent).filter(
            DBAppEvent.source.notin_(["werkzeug", "root"])
        ).order_by(DBAppEvent.created_at.desc()).limit(40).all()

        feed = []
        for e in events:
            feed.append({
                "sort_ts": e.created_at.isoformat(),
                "time": e.created_at.strftime("%H:%M"),
                "date": e.created_at.strftime("%b %d"),
                "message": e.message,
                "level": e.level,
                "source": e.source
            })

        if context.scheduler:
            for job in context.scheduler.job_history[-15:]:
                try:
                    job_dt = datetime.strptime(job["timestamp"], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    job_dt = datetime.now()
                feed.append({
                    "sort_ts": job_dt.isoformat(),
                    "time": job_dt.strftime("%H:%M"),
                    "date": job_dt.strftime("%b %d"),
                    "message": f"Sync {job['status']}: {job['message']}",
                    "level": "INFO" if job["status"] == "Success" else "ERROR",
                    "source": "scheduler"
                })

        # Sort by ISO timestamp string — correct across months and days
        feed.sort(key=lambda x: x["sort_ts"], reverse=True)
        return jsonify(feed[:25])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@dashboard_bp.route("/api/dashboard/alerts", methods=["GET"])
@login_required
def api_dashboard_alerts():
    db = get_db()
    if not db:
        return jsonify({"error": "Database not connected"}), 500
    try:
        alerts = []
        
        # 1. Platform Mismatch Alerts
        mismatches = db.query(DBOrder).filter(
            DBOrder.platform == "LiveTicketGroup",
            DBOrder.ticketshop_status == "missing",
            DBOrder.is_past_event == False
        ).all()
        if mismatches:
            alerts.append({
                "severity": "warning",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "platform": "Inventory Validation",
                "message": f"{len(mismatches)} LiveTicketGroup orders are missing from Ticketshop listings.",
                "suggested_action": "Manually check Ticketshop in Platform Sources page."
            })
            
        # 2. Scraper Failure Alerts
        if context.scheduler:
            history = context.scheduler.job_history
            for job in history:
                if job.get("status") in ("error", "Failed"):
                    msg = job.get("message", "")
                    platform = "LiveTicketGroup" if "liveticketgroup" in msg.lower() else "FootballTicketNet" if "footballticketnet" in msg.lower() else "Scheduler"
                    alerts.append({
                        "severity": "error",
                        "timestamp": job.get("timestamp"),
                        "platform": platform,
                        "message": f"Platform sync failed: {msg}",
                        "suggested_action": "Check platform configuration credentials or browser logs."
                    })
                    
        # 3. Missing Telegram Alert
        from config import ORDER_BOT_TOKEN, ORDER_CHAT_ID
        if not (ORDER_BOT_TOKEN and ORDER_CHAT_ID):
            alerts.append({
                "severity": "error",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "platform": "Telegram Connection",
                "message": "Telegram Bot Token or Chat ID is missing from environment variables.",
                "suggested_action": "Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env file."
            })
            
        # 4. Recent Database Errors from App Events
        recent_errs = db.query(DBAppEvent).filter(
            DBAppEvent.level == "ERROR",
            DBAppEvent.created_at >= datetime.utcnow() - timedelta(hours=24)
        ).all()
        for err in recent_errs:
            alerts.append({
                "severity": "error",
                "timestamp": err.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "platform": err.source or "System",
                "message": err.message,
                "suggested_action": "Review application trace log details."
            })
            
        return jsonify(alerts)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@dashboard_bp.route("/health", methods=["GET"])
def public_health():
    from sqlalchemy import text
    db = get_db()
    if not db:
        return jsonify({"status": "unhealthy"}), 503
    try:
        db.execute(text("SELECT 1"))
        return jsonify({"status": "healthy"}), 200
    except Exception:
        return jsonify({"status": "unhealthy"}), 503
    finally:
        db.close()
