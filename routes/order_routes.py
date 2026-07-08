from datetime import datetime
from flask import Blueprint, jsonify, request
from database import get_db, DBOrder
from routes.auth_routes import login_required
from core.helpers import standardize_status

order_bp = Blueprint('order', __name__)

@order_bp.route("/api/orders", methods=["GET"])
@login_required
def api_get_orders():
    db = get_db()
    if not db:
        return jsonify([])
    try:
        orders = db.query(DBOrder).order_by(DBOrder.id.desc()).all()
        return jsonify([{
            "id": o.id, "order_number": o.order_number, "platform": o.platform, "event_name": o.event_name or "-",
            "event_date": o.event_date.strftime("%Y-%m-%d %H:%M:%S") if o.event_date else "-",
            "customer_name": o.customer_name or "-", "quantity": o.quantity or 1,
            "total_value": str(o.total_value or 0), "currency": o.currency or "£",
            "normalized_status": o.normalized_status or "pending", "sale_date": o.sale_date.strftime("%Y-%m-%d %H:%M:%S") if o.sale_date else "-"
        } for o in orders])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@order_bp.route("/api/orders/<platform>/<order_number>", methods=["GET"])
@login_required
def api_get_order_details(platform, order_number):
    db = get_db()
    if not db:
        return jsonify({"ok": False, "error": "Database not available"}), 200
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
                        if not dbo:
                            dbo = DBOrder(platform=platform, order_number=order_number)
                            db.add(dbo)
                        for k, v in details.items():
                            if hasattr(dbo, k) and v is not None:
                                setattr(dbo, k, v)
                        if dbo.billing_full_name:
                            dbo.customer_name = dbo.billing_full_name
                        if dbo.total_amount is not None:
                            dbo.total_value = dbo.total_amount
                        dbo.normalized_status = standardize_status(dbo.raw_status, source=platform, resale_status=dbo.resale_status, pod_status=dbo.pod_status)
                        dbo.details_fetched_at = datetime.utcnow()
                        db.commit()
                    else:
                        error_msg = "Order details not found on platform"
                except Exception as e:
                    error_msg = f"Scraping error: {str(e)}"
        
        if not dbo:
            return jsonify({"ok": False, "error": error_msg or "Order not found"}), 200
        
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
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200
    finally:
        db.close()

@order_bp.route("/api/orders/search", methods=["GET"])
@login_required
def api_orders_search():
    db = get_db()
    if not db:
        return jsonify([])
    try:
        platform = request.args.get("platform")
        event_name = request.args.get("event_name")
        query = db.query(DBOrder)
        if platform:
            query = query.filter(DBOrder.platform == platform)
        if event_name:
            query = query.filter(DBOrder.event_name.ilike(f"%{event_name}%"))
        orders = query.all()
        return jsonify([{
            "id": o.order_number, "customer": o.customer_name or "-",
            "sale_date": o.sale_date.strftime("%Y-%m-%d %H:%M:%S") if o.sale_date else "-",
            "status": o.normalized_status or "Pending"
        } for o in orders])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@order_bp.route("/api/check-order-status", methods=["POST"])
@login_required
def api_check_order_status():
    data = request.json or {}
    platform = data.get("platform")
    event_name = data.get("eventName")
    if not platform or not event_name:
        return jsonify({"ok": False, "error": "Platform and Event Name required"})
    
    from platforms.registry import platform_adapters
    adapter = next((a for a in platform_adapters if a.source_name == platform), None)
    if not adapter:
        return jsonify({"ok": False, "error": f"Adapter for {platform} not found"})
    
    try:
        if hasattr(adapter, "fetch_orders_by_event"):
            rows = adapter.fetch_orders_by_event(event_name)
        else:
            rows, _ = adapter.fetch_orders()
            if rows:
                rows = [r for r in rows if event_name.lower() in str(r.get("event", "")).lower()]
        
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
