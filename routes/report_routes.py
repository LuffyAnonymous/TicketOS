import io
from datetime import datetime
from flask import Blueprint, send_file, request, jsonify, g
from sqlalchemy import or_, func
from database import get_db, DBOrder, DBAppEvent
from routes.auth_routes import role_required
import extensions as context
from services.excel_exporter import create_styled_workbook, workbook_to_bytes

report_bp = Blueprint('report', __name__)

@report_bp.route("/api/reports/orders", methods=["GET"])
@role_required(["admin", "staff"])
def export_orders_report():
    db = get_db()
    if not db:
        return jsonify({"error": "Database not connected"}), 500
    try:
        username = g.current_user.get("username", "Unknown")
        query = db.query(DBOrder)
        
        # Apply current filters if specified
        platform = request.args.get("platform")
        if platform:
            query = query.filter(DBOrder.platform == platform)
        status = request.args.get("status")
        if status:
            query = query.filter(DBOrder.normalized_status == status)
            
        # Date range filters
        start_date_str = request.args.get("start_date")
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                query = query.filter(func.date(DBOrder.sale_date) >= start_date)
            except:
                pass
        end_date_str = request.args.get("end_date")
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                query = query.filter(func.date(DBOrder.sale_date) <= end_date)
            except:
                pass

        # Legacy date filter
        date_str = request.args.get("date")
        if date_str:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                query = query.filter(func.date(DBOrder.sale_date) == target_date)
            except:
                pass

        event = request.args.get("event")
        if event:
            query = query.filter(DBOrder.event_name.ilike(f"%{event}%"))

        customer = request.args.get("customer")
        if customer:
            search_pattern = f"%{customer}%"
            query = query.filter(
                or_(
                    DBOrder.customer_name.like(search_pattern),
                    DBOrder.email.like(search_pattern),
                    DBOrder.mobile_number.like(search_pattern)
                )
            )

        q = request.args.get("q")
        if q:
            search_pattern = f"%{q}%"
            query = query.filter(
                or_(
                    DBOrder.order_number.like(search_pattern),
                    DBOrder.customer_name.like(search_pattern),
                    DBOrder.email.like(search_pattern),
                    DBOrder.mobile_number.like(search_pattern),
                    DBOrder.event_name.like(search_pattern)
                )
            )
            
        orders = query.order_by(DBOrder.id.desc()).all()
        
        # Audit Log
        db.add(DBAppEvent(
            level="INFO",
            source="report",
            message=f"User {username} exported Orders report",
            details={"action": "export", "report": "orders", "username": username, "filters": request.args.to_dict()}
        ))
        db.commit()
        
        headers = ["Order ID", "Platform", "Event Name", "Event Date", "Customer Name", "Email", "Phone", "Quantity", "Total Value", "Currency", "Status", "Sale Date"]
        rows = []
        for o in orders:
            rows.append([
                o.order_number,
                o.platform,
                o.event_name or "-",
                o.event_date.strftime("%Y-%m-%d %H:%M:%S") if o.event_date else "-",
                o.customer_name or "-",
                o.email or "-",
                o.mobile_number or "-",
                o.quantity or 1,
                float(o.total_value) if o.total_value is not None else 0.0,
                o.currency or "£",
                o.normalized_status or "pending",
                o.sale_date.strftime("%Y-%m-%d %H:%M:%S") if o.sale_date else "-"
            ])
            
        wb = create_styled_workbook([{
            "title": "Orders Report",
            "headers": headers,
            "rows": rows
        }])
        
        buf = workbook_to_bytes(wb)
        filename = f"orders_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@report_bp.route("/api/reports/customers", methods=["GET"])
@role_required(["admin", "staff"])
def export_customers_report():
    db = get_db()
    if not db:
        return jsonify({"error": "Database not connected"}), 500
    try:
        username = g.current_user.get("username", "Unknown")
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
                    "name": o.customer_name or o.billing_full_name or "-",
                    "email": o.email or "N/A",
                    "phone": o.mobile_number or o.billing_mobile or "N/A",
                    "total_orders": 0,
                    "lifetime_spend": 0.0,
                    "currency": o.currency or "£",
                    "last_purchase_date": None,
                    "events": {},
                    "platforms": set()
                }
                
            p = profiles[key]
            if p["email"] in ("N/A", "") and o.email: p["email"] = o.email
            if p["phone"] in ("N/A", "") and o.mobile_number: p["phone"] = o.mobile_number
            if p["name"] in ("-", "") and (o.customer_name or o.billing_full_name): p["name"] = o.customer_name or o.billing_full_name
            
            p["total_orders"] += 1
            p["lifetime_spend"] += val
            if o.platform: p["platforms"].add(o.platform)
            if o.event_name and o.event_name != "-":
                p["events"][o.event_name] = p["events"].get(o.event_name, 0) + 1
            if o.sale_date:
                if not p["last_purchase_date"] or o.sale_date > p["last_purchase_date"]:
                    p["last_purchase_date"] = o.sale_date
                    
        # Audit Log
        db.add(DBAppEvent(
            level="INFO",
            source="report",
            message=f"User {username} exported Customers CRM report",
            details={"action": "export", "report": "customers", "username": username}
        ))
        db.commit()
        
        headers = ["Customer Name", "Email", "Phone", "Platform Sources", "Total Orders", "Lifetime Spend (£)", "Last Purchase Date", "Favorite Event"]
        rows = []
        for p in profiles.values():
            fav_event = "-"
            if p["events"]:
                fav_event = max(p["events"], key=p["events"].get)
                
            rows.append([
                p["name"],
                p["email"],
                p["phone"],
                ", ".join(p["platforms"]),
                p["total_orders"],
                round(p["lifetime_spend"], 2),
                p["last_purchase_date"].strftime("%Y-%m-%d %H:%M:%S") if p["last_purchase_date"] else "-",
                fav_event
            ])
            
        wb = create_styled_workbook([{
            "title": "Customers Summary",
            "headers": headers,
            "rows": rows
        }])
        
        buf = workbook_to_bytes(wb)
        filename = f"customers_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@report_bp.route("/api/reports/customer-history/<customer_key>", methods=["GET"])
@role_required(["admin", "staff"])
def export_customer_history_report(customer_key):
    db = get_db()
    if not db:
        return jsonify({"error": "Database not connected"}), 500
    try:
        username = g.current_user.get("username", "Unknown")
        orders = db.query(DBOrder).all()
        target_profile = None
        
        for o in orders:
            email = (o.email or "").strip().lower()
            mobile = (o.mobile_number or "").strip()
            name = (o.customer_name or "").strip()
            if not name or name == "-":
                continue
                
            key = None
            if email and email not in ("n/a", "none", ""): key = f"email:{email}"
            elif mobile and mobile not in ("n/a", "none", ""): key = f"mobile:{mobile.lower()}"
            else: key = f"name:{name.lower()}"
            
            if key == customer_key:
                val = float(o.total_value) if o.total_value is not None else 0.0
                if not target_profile:
                    target_profile = {
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
                
                tp = target_profile
                if tp["email"] in ("N/A", "") and o.email: tp["email"] = o.email
                if tp["phone"] in ("N/A", "") and o.mobile_number: tp["phone"] = o.mobile_number
                
                tp["total_orders"] += 1
                tp["lifetime_spend"] += val
                if o.platform: tp["platforms"].add(o.platform)
                if o.event_name and o.event_name != "-":
                    tp["events"][o.event_name] = tp["events"].get(o.event_name, 0) + 1
                if o.sale_date:
                    if not tp["last_purchase_date"] or o.sale_date > tp["last_purchase_date"]:
                        tp["last_purchase_date"] = o.sale_date
                        
                tp["orders"].append([
                    o.order_number,
                    o.platform,
                    o.event_name or "-",
                    o.sale_date.strftime("%Y-%m-%d %H:%M:%S") if o.sale_date else "-",
                    o.quantity or 1,
                    val,
                    o.currency or "£",
                    o.normalized_status or "pending"
                ])
                
        if not target_profile:
            return jsonify({"error": "Customer not found"}), 404
            
        # Audit Log
        db.add(DBAppEvent(
            level="INFO",
            source="report",
            message=f"User {username} exported Customer history report for key: {customer_key}",
            details={"action": "export", "report": "customer_history", "customer_key": customer_key, "username": username}
        ))
        db.commit()
            
        fav_event = "-"
        if target_profile["events"]:
            fav_event = max(target_profile["events"], key=target_profile["events"].get)
            
        summary_headers = ["Customer Name", "Email", "Phone", "Platform Sources", "Total Orders", "Lifetime Spend (£)", "Last Purchase Date", "Favorite Event"]
        summary_rows = [[
            target_profile["name"],
            target_profile["email"],
            target_profile["phone"],
            ", ".join(target_profile["platforms"]),
            target_profile["total_orders"],
            round(target_profile["lifetime_spend"], 2),
            target_profile["last_purchase_date"].strftime("%Y-%m-%d %H:%M:%S") if target_profile["last_purchase_date"] else "-",
            fav_event
        ]]
        
        orders_headers = ["Order ID", "Platform", "Event Name", "Sale Date", "Quantity", "Total Spend", "Currency", "Status"]
        
        wb = create_styled_workbook([
            {
                "title": "Customer Summary",
                "headers": summary_headers,
                "rows": summary_rows
            },
            {
                "title": "Order Details",
                "headers": orders_headers,
                "rows": target_profile["orders"]
            }
        ])
        
        buf = workbook_to_bytes(wb)
        safe_name = "".join(x for x in target_profile["name"] if x.isalnum() or x in " -_").strip()
        filename = f"history_{safe_name.replace(' ', '_')}.xlsx"
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@report_bp.route("/api/reports/revenue", methods=["GET"])
@role_required(["admin", "staff"])
def export_revenue_report():
    db = get_db()
    if not db:
        return jsonify({"error": "Database not connected"}), 500
    try:
        username = g.current_user.get("username", "Unknown")
        orders = db.query(DBOrder).all()
        
        total_orders = 0
        total_rev = 0.0
        completed_rev = 0.0
        pending_rev = 0.0
        cancelled_rev = 0.0
        
        daily_rev = {}
        event_rev = {}
        
        for o in orders:
            total_orders += 1
            val = float(o.total_value) if o.total_value is not None else 0.0
            
            if o.normalized_status == "completed":
                completed_rev += val
                total_rev += val
            elif o.normalized_status == "pending":
                pending_rev += val
                total_rev += val
            elif o.normalized_status == "cancelled":
                cancelled_rev += val
                
            if o.normalized_status != "cancelled":
                day_str = o.sale_date.strftime("%Y-%m-%d") if o.sale_date else "Unknown Date"
                if day_str not in daily_rev:
                    daily_rev[day_str] = {"orders": 0, "value": 0.0}
                daily_rev[day_str]["orders"] += 1
                daily_rev[day_str]["value"] += val
                
                ev_name = o.event_name or "-"
                plt = o.platform or "-"
                key = (ev_name, plt)
                if key not in event_rev:
                    event_rev[key] = {"orders": 0, "value": 0.0}
                event_rev[key]["orders"] += 1
                event_rev[key]["value"] += val
                
        # Audit Log
        db.add(DBAppEvent(
            level="INFO",
            source="report",
            message=f"User {username} exported Revenue report",
            details={"action": "export", "report": "revenue", "username": username}
        ))
        db.commit()
        
        summary_headers = ["Metric", "Value"]
        summary_rows = [
            ["Total Active Orders", total_orders],
            ["Total Active Revenue (£)", round(total_rev, 2)],
            ["Completed Sales Revenue (£)", round(completed_rev, 2)],
            ["Pending Sales Revenue (£)", round(pending_rev, 2)],
            ["Cancelled Sales Revenue (£)", round(cancelled_rev, 2)]
        ]
        
        daily_headers = ["Sale Date", "Orders Count", "Sales Value (£)"]
        daily_rows = [
            [d, daily_rev[d]["orders"], round(daily_rev[d]["value"], 2)]
            for d in sorted(daily_rev.keys(), reverse=True)
        ]
        
        event_headers = ["Event Name", "Platform Source", "Orders Count", "Event Revenue (£)"]
        event_rows = [
            [k[0], k[1], event_rev[k]["orders"], round(event_rev[k]["value"], 2)]
            for k in sorted(event_rev.keys(), key=lambda x: event_rev[x]["value"], reverse=True)
        ]
        
        wb = create_styled_workbook([
            {
                "title": "Revenue Summary",
                "headers": summary_headers,
                "rows": summary_rows
            },
            {
                "title": "Daily Revenue",
                "headers": daily_headers,
                "rows": daily_rows
            },
            {
                "title": "Event Revenue",
                "headers": event_headers,
                "rows": event_rows
            }
        ])
        
        buf = workbook_to_bytes(wb)
        filename = f"revenue_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@report_bp.route("/api/reports/platforms", methods=["GET"])
@role_required(["admin", "staff"])
def export_platforms_report():
    db = get_db()
    if not db:
        return jsonify({"error": "Database not connected"}), 500
    try:
        username = g.current_user.get("username", "Unknown")
        orders = db.query(DBOrder).all()
        platforms_stats = {}
        
        for o in orders:
            p = o.platform or "Unknown"
            if p not in platforms_stats:
                platforms_stats[p] = {"total": 0, "completed": 0, "pending": 0, "cancelled": 0, "revenue": 0.0}
                
            platforms_stats[p]["total"] += 1
            val = float(o.total_value) if o.total_value is not None else 0.0
            
            if o.normalized_status == "completed":
                platforms_stats[p]["completed"] += 1
                platforms_stats[p]["revenue"] += val
            elif o.normalized_status == "pending":
                platforms_stats[p]["pending"] += 1
                platforms_stats[p]["revenue"] += val
            elif o.normalized_status == "cancelled":
                platforms_stats[p]["cancelled"] += 1
                
        # Audit Log
        db.add(DBAppEvent(
            level="INFO",
            source="report",
            message=f"User {username} exported Platform performance report",
            details={"action": "export", "report": "platforms", "username": username}
        ))
        db.commit()
        
        headers = ["Platform Source", "Total Orders", "Completed Orders", "Pending Orders", "Cancelled Orders", "Active Revenue (£)", "Last Sync Time"]
        rows = []
        for plt_name, p in platforms_stats.items():
            last_run = "-"
            if context.scheduler and context.scheduler.last_run_time:
                last_run = context.scheduler.last_run_time
            elif context.state and "last_check_time" in context.state.settings:
                last_run = context.state.settings["last_check_time"]
                
            rows.append([
                plt_name,
                p["total"],
                p["completed"],
                p["pending"],
                p["cancelled"],
                round(p["revenue"], 2),
                last_run
            ])
            
        wb = create_styled_workbook([{
            "title": "Platform Performance",
            "headers": headers,
            "rows": rows
        }])
        
        buf = workbook_to_bytes(wb)
        filename = f"platforms_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
