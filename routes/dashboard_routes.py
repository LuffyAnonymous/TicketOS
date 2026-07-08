import jwt
from flask import Blueprint, jsonify, render_template, g, request
from sqlalchemy import or_, func
from config import JWT_SECRET
from database import get_db, DBOrder
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
    return jsonify({
        "current_user": g.current_user["username"],
        "current_role": g.current_user["role"],
        "summary": context.state.summary() if context.state else {},
        "members": [safe_user_view(u) for u in load_users()]
    })

@dashboard_bp.route("/api/db-health", methods=["GET"])
def api_db_health():
    db = get_db()
    if not db:
        return jsonify({"database": "json", "connected": False, "orders_count": 0})
    try:
        count = db.query(DBOrder).count()
        return jsonify({"database": "postgresql", "connected": True, "orders_count": count})
    except Exception as e:
        return jsonify({"database": "json", "connected": False, "orders_count": 0, "error": str(e)})
    finally:
        db.close()

@dashboard_bp.route("/api/dashboard/stats", methods=["GET"])
@login_required
def api_get_dashboard_stats():
    db = get_db()
    if not db:
        return jsonify({"total": 0, "pending": 0, "cancelled": 0, "resold": 0, "completed": 0})
    try:
        total = db.query(DBOrder).filter(DBOrder.normalized_status != "cancelled").count()
        pending = db.query(DBOrder).filter(DBOrder.normalized_status == "pending").count()
        cancelled = db.query(DBOrder).filter(DBOrder.normalized_status == "cancelled").count()
        resold = db.query(DBOrder).filter(or_(DBOrder.normalized_status == "resold", DBOrder.normalized_status == "presold")).count()
        completed = db.query(DBOrder).filter(or_(DBOrder.normalized_status == "completed", DBOrder.normalized_status == "processed")).count()
        return jsonify({"total": total, "pending": pending, "cancelled": cancelled, "resold": resold, "completed": completed})
    except Exception:
        return jsonify({"total": 0, "pending": 0, "cancelled": 0, "resold": 0, "completed": 0})
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
