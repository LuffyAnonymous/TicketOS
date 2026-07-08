import threading
from flask import Blueprint, jsonify, request
from database import get_db, DBOrder, engine, Base, init_db
import extensions as context
from routes.auth_routes import login_required
from services.order_service import bot_worker

platform_bp = Blueprint('platform', __name__)

@platform_bp.route("/api/start", methods=["POST"])
@login_required
def api_start_bot():
    if context.state.running:
        return jsonify({"ok": True, "message": "Already running"})
    context.state.stop_event.clear()
    context.state.worker_thread = threading.Thread(target=bot_worker, daemon=True)
    context.state.worker_thread.start()
    return jsonify({"ok": True, "message": "Bot started"})

@platform_bp.route("/api/stop", methods=["POST"])
@login_required
def api_stop_bot():
    context.state.stop_event.set()
    return jsonify({"ok": True})

@platform_bp.route("/api/sync/live-ticket-group", methods=["POST"])
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

@platform_bp.route("/api/platform-states", methods=["POST"])
@login_required
def api_save_platform_states():
    context.state.settings.update(request.json or {})
    context.state.save_settings()
    return jsonify({"ok": True})

@platform_bp.route("/api/system/reset", methods=["POST"])
@login_required
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@platform_bp.route("/api/system/check-ticketsshop", methods=["POST"])
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
