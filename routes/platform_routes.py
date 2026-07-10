import threading
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from database import get_db, DBOrder, DBPlatform, DBAppEvent, engine, Base, init_db
import extensions as context
from routes.auth_routes import login_required, role_required
from services.order_service import bot_worker

platform_bp = Blueprint('platform', __name__)

@platform_bp.route("/api/start", methods=["POST"])
@role_required(["admin", "staff"])
def api_start_bot():
    if not context.scheduler:
        return jsonify({"ok": False, "error": "Scheduler not initialized"})
    started = context.scheduler.start()
    if started:
        return jsonify({"ok": True, "message": "Scheduler started"})
    return jsonify({"ok": True, "message": "Scheduler is already running"})

@platform_bp.route("/api/stop", methods=["POST"])
@role_required(["admin", "staff"])
def api_stop_bot():
    if not context.scheduler:
        return jsonify({"ok": False, "error": "Scheduler not initialized"})
    context.scheduler.stop()
    return jsonify({"ok": True, "message": "Scheduler stopped"})

@platform_bp.route("/api/sync/live-ticket-group", methods=["POST"])
@role_required(["admin", "staff"])
def api_sync_ltg():
    if not context.scheduler:
        return jsonify({"ok": False, "error": "Scheduler not initialized"})
    try:
        success = context.scheduler.run_sync_once(manual=True)
        if success:
            return jsonify({"ok": True, "message": "Successfully synchronized all orders"})
        else:
            history = context.scheduler.job_history
            last_err = history[-1]["message"] if history else "Unknown sync error"
            return jsonify({"ok": False, "error": last_err})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@platform_bp.route("/api/scheduler/pause", methods=["POST"])
@role_required(["admin", "staff"])
def api_scheduler_pause():
    if not context.scheduler:
        return jsonify({"ok": False, "error": "Scheduler not initialized"})
    context.scheduler.pause()
    return jsonify({"ok": True, "message": "Scheduler paused"})

@platform_bp.route("/api/scheduler/resume", methods=["POST"])
@role_required(["admin", "staff"])
def api_scheduler_resume():
    if not context.scheduler:
        return jsonify({"ok": False, "error": "Scheduler not initialized"})
    context.scheduler.resume()
    return jsonify({"ok": True, "message": "Scheduler resumed"})

@platform_bp.route("/api/scheduler/status", methods=["GET"])
@login_required
def api_scheduler_status():
    if not context.scheduler:
        return jsonify({"ok": False, "error": "Scheduler not initialized"})
    return jsonify({
        "running": context.state.running,
        "paused": context.scheduler.paused,
        "last_run_time": context.scheduler.last_run_time or "-",
        "last_run_status": context.scheduler.last_run_status,
        "job_history": context.scheduler.job_history
    })

@platform_bp.route("/api/platforms", methods=["GET"])
@login_required
def api_get_platforms():
    """Return per-platform operational info + enabled state from DB."""
    db = get_db()
    if not db:
        return jsonify([])
    try:
        platform_names = ["LiveTicketGroup", "FootballTicketNet", "Ticketshop"]
        result = []
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        for name in platform_names:
            # Get or create DBPlatform row
            p_row = db.query(DBPlatform).filter(DBPlatform.name == name).first()
            if not p_row:
                p_row = DBPlatform(name=name, is_enabled=True)
                db.add(p_row)
                db.commit()

            # Orders synced today
            orders_today = db.query(DBOrder).filter(
                DBOrder.platform == name,
                DBOrder.sale_date >= today_start
            ).count()

            # Last successful sync — use scheduler data or last seen order
            last_sync = "-"
            if context.scheduler and context.scheduler.last_run_time:
                last_sync = context.scheduler.last_run_time

            # Last error for this platform (last 48h)
            two_days_ago = datetime.utcnow() - timedelta(hours=48)
            last_err_row = db.query(DBAppEvent).filter(
                DBAppEvent.level == "ERROR",
                DBAppEvent.source.ilike(f"%{name.lower().replace(' ', '')}%"),
                DBAppEvent.created_at >= two_days_ago
            ).order_by(DBAppEvent.created_at.desc()).first()
            last_error = last_err_row.message[:80] if last_err_row else None
            last_error_time = last_err_row.created_at.strftime("%Y-%m-%d %H:%M") if last_err_row else None

            # Session / cookie status
            settings = context.state.settings if context.state else {}
            key = name.lower().replace(" ", "")
            session_ok = settings.get(f"{key}_session_ok", True)

            result.append({
                "name": name,
                "is_enabled": p_row.is_enabled,
                "orders_today": orders_today,
                "last_sync": last_sync,
                "last_error": last_error,
                "last_error_time": last_error_time,
                "session_status": "Active" if session_ok else "Invalid",
            })

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@platform_bp.route("/api/platforms/<name>/toggle", methods=["POST"])
@role_required(["admin", "staff"])
def api_toggle_platform(name):
    """Enable or disable a platform by name. State persisted in DBPlatform."""
    db = get_db()
    if not db:
        return jsonify({"ok": False, "error": "Database not connected"}), 500
    try:
        p_row = db.query(DBPlatform).filter(DBPlatform.name == name).first()
        if not p_row:
            return jsonify({"ok": False, "error": f"Platform '{name}' not found"}), 404
        p_row.is_enabled = not p_row.is_enabled
        db.commit()
        state = "enabled" if p_row.is_enabled else "disabled"
        return jsonify({"ok": True, "name": name, "is_enabled": p_row.is_enabled, "message": f"{name} {state}"})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()


@platform_bp.route("/api/platform-states", methods=["POST"])
@role_required(["admin", "staff"])
def api_save_platform_states():
    context.state.settings.update(request.json or {})
    context.state.save_settings()
    return jsonify({"ok": True})

@platform_bp.route("/api/system/reset", methods=["POST"])
@role_required(["admin"])
def api_system_reset():
    try:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        init_db()
        context.state.log("System reset complete. All old data cleared.")
        return jsonify({"ok": True, "message": "System reset successfully"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@platform_bp.route("/api/test-order-telegram", methods=["POST"])
@role_required(["admin", "staff"])
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@platform_bp.route("/api/system/check-ticketsshop", methods=["POST"])
@role_required(["admin", "staff"])
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
