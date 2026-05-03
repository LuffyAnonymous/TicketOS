import threading
from datetime import datetime
from flask import jsonify, request, render_template, redirect, url_for, g, make_response
import extensions as context
from config import APP_TITLE, INACTIVITY_MINUTES, REMEMBER_DAYS, PLATFORM_CONFIGS
from core.auth import login_required, admin_required_api, get_current_auth, make_token, set_auth_cookie, clear_auth_cookie
from core.users import load_users, safe_user_view, verify_user, add_user, reset_user_password, update_user_role, toggle_user_active, delete_user, normalize_username
from core.helpers import clean_text, parse_sale_datetime
from core.storage import cache_order_details, load_order_details_cache
from services.cache_service import launch_auto_cache_if_needed
from services.aggregation import build_event_totals_from_cache
from services.order_service import execute_check_cycle, bot_worker, is_sleep_window
from services.telegram_service import send_telegram
from platforms.liveticketgroup import get_ltg_order_details

def register_routes(app):
    def maybe_refresh_token(response):
        refresh = getattr(g, "refresh_auth_cookie", False)
        user = getattr(g, "current_user", None)
        remember = getattr(g, "remember_login", False)

        if refresh and user:
            token = make_token(user, remember=remember)
            set_auth_cookie(response, token, remember=remember)

        return response

    app.after_request(maybe_refresh_token)

    @app.route('/favicon.ico')
    def favicon():
        return "", 204

    @app.post("/api/check-order-status")
    @login_required
    def api_check_order_status():
        data = request.get_json(force=True, silent=True) or {}
        platform_name = data.get("platform", "").strip()
        event_name = data.get("event_name", "").strip()

        if not platform_name or not event_name:
            return jsonify({"error": "Platform and event name are required."}), 400

        context.state.log(f"Manual check: Platform={platform_name}, Event={event_name}")

        from platforms.registry import platform_adapters
        adapter = next((a for a in platform_adapters if a.source_name == platform_name), None)
        if not adapter:
            context.state.log(f"Manual check: Platform '{platform_name}' not found.")
            return jsonify({"error": f"Platform '{platform_name}' not found or not enabled."}), 400

        try:
            # This will use the deep scraper for FTN if it's the FTN adapter
            rows = adapter.fetch_orders_by_event(event_name)
            context.state.log(f"Manual check: {len(rows)} orders found for event '{event_name}' on {platform_name}")
        except Exception as e:
            context.state.log(f"Manual check FAILED for {platform_name}: {repr(e)}")
            return jsonify({"error": f"Failed to fetch orders: {str(e)}"}), 500

        from core.helpers import standardize_status
        from config import ORDER_STATUS_STATE_FILE, ORDER_STATUS_ALERTS_FILE
        from core.storage import load_json_file, save_json_file
        from services.telegram_service import send_telegram

        status_state = load_json_file(ORDER_STATUS_STATE_FILE, {})
        status_state_changed = False
        history = load_json_file(ORDER_STATUS_ALERTS_FILE, {})
        changed = False

        grouped = {
            "processed": [],
            "cancelled": [],
            "submitted": [],
            "resold": []
        }

        for row in rows:
            raw_status = clean_text(row.get("status", ""))
            resale_raw = clean_text(row.get("resale_status", ""))
            order_id = clean_text(row.get("id", ""))
            
            # Map for dashboard cards
            dash_status = standardize_status(raw_status, source=platform_name, resale_status=resale_raw)
            
            # Category for the search results table (user wants to see real status)
            cat = dash_status
            if cat == "pending":
                if "process" in raw_status.lower():
                    cat = "processed"
                else:
                    cat = "submitted"

            row["dashboard_status"] = dash_status
            grouped[cat].append(row)
            
            # Update persistent state
            key = f"{platform_name}::{order_id}"
            old_data = status_state.get(key, {})
            
            # If it's visible, it's 'pending' unless cancelled/resold.
            new_status = dash_status
            
            if not old_data or old_data.get("order_status") != new_status:
                status_state[key] = {
                    "order_number": order_id,
                    "event_name":   row.get("event", event_name),
                    "event_date":   row.get("event_date", "-"),
                    "customer":     row.get("customer", "-"),
                    "sale_date":    row.get("sale_date", "-"),
                    "order_status": new_status,
                    "source":       platform_name,
                    "last_seen":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                status_state_changed = True
                context.state.log(f"Manual search: updating tracking for {key} → {new_status}")
            else:
                status_state[key]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Alert logic
            alert_type = None
            if dash_status == "cancelled":
                alert_type = "cancelled"
            elif dash_status == "resold":
                alert_type = "resold"

            if alert_type:
                hist_key = f"{platform_name}_{order_id}_{event_name}_{alert_type}"
                if not history.get(hist_key):
                    if alert_type == "cancelled":
                        msg = (
                            f"❌ ORDER CANCELLED\n"
                            f"Platform: {platform_name}\n"
                            f"Order: {order_id}\n"
                            f"Event: {event_name}\n"
                            f"Status: {raw_status}"
                        )
                    else:
                        msg = (
                            f"🔁 ORDER RESOLD / RESALE\n"
                            f"Platform: {platform_name}\n"
                            f"Order: {order_id}\n"
                            f"Event: {event_name}\n"
                            f"Status: {raw_status}"
                        )
                    
                    send_telegram(msg)
                    history[hist_key] = True
                    changed = True

        if status_state_changed:
            save_json_file(ORDER_STATUS_STATE_FILE, status_state)
        if changed:
            save_json_file(ORDER_STATUS_ALERTS_FILE, history)

        for cat_list in grouped.values():
            for r in cat_list:
                context.state.upsert_sent_order_row(r)

        return jsonify({
            "success": True,
            "platform": platform_name,
            "event": event_name,
            "results": grouped
        })


    @app.get("/login")
    def login_page():
        auth = get_current_auth()
        if auth:
            return redirect(url_for("index"))
        return render_template("login.html", title=f"{APP_TITLE} - Login")


    @app.post("/login")
    def login_submit():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        remember = request.form.get("remember_me") == "on"

        user = verify_user(username, password)
        if not user:
            response = make_response(render_template(
                "login.html",
                title=f"{APP_TITLE} - Login",
                error="Invalid username or password"
            ))
            clear_auth_cookie(response)
            return response

        token = make_token(user, remember=remember)
        response = make_response(redirect(url_for("index")))
        set_auth_cookie(response, token, remember=remember)
        return response


    @app.get("/logout")
    def logout():
        response = make_response(redirect(url_for("login_page")))
        clear_auth_cookie(response)
        return response


    @app.get("/")
    @login_required
    def index():
        return render_template("index.html", title=APP_TITLE, current_user=g.current_user.get("username", ""))


    @app.get("/api/state")
    @login_required
    def api_state():
        users = load_users()
        user_list = [safe_user_view(u) for u in users]
        try:
            launch_auto_cache_if_needed(context.state.current_order_rows)
        except Exception as e:
            context.state.log(f"Auto-cache launch error: {e}")
        try:
            from config import TICKETSSHOP_RESULTS_FILE
            from core.storage import load_json_file
            ts_cache = load_json_file(TICKETSSHOP_RESULTS_FILE, {})
        except:
            ts_cache = {}
        try:
            from config import ORDER_STATUS_STATE_FILE
            from core.storage import load_json_file
            order_states = load_json_file(ORDER_STATUS_STATE_FILE, {})
        except:
            order_states = {}

        from core.helpers import standardize_status
        orders = []
        for r in context.state.current_order_rows:
            order_copy = dict(r)
            source = clean_text(order_copy.get("source", "Unknown"))
            order_id = str(order_copy.get("id"))
            key = f"{source}::{order_id}"
            
            if "liveticketgroup" in source.lower():
                ts_info = ts_cache.get(order_id)
                if isinstance(ts_info, dict):
                    order_copy["ticketsshop_status"] = ts_info.get("status", "unchecked")
                else:
                    order_copy["ticketsshop_status"] = ts_info if ts_info else "unchecked"
                    
            # Use persistent status_state if available, else standardize current row
            std_status = "pending"
            if key in order_states:
                std_status = order_states[key].get("order_status", "pending")
            else:
                std_status = standardize_status(
                    order_copy.get("status", ""),
                    source=source,
                    resale_status=order_copy.get("resale_status")
                )
                
            order_copy["dashboard_status"] = std_status
            orders.append(order_copy)

        return jsonify({
            "summary": context.state.summary(),
            "logs": context.state.logs[-250:],
            "orders": orders,
            "sent_orders": context.state.sent_order_rows,
            "members": user_list,
            "current_user": g.current_user.get("username", ""),
            "current_role": g.current_user.get("role", "member"),
            "inactivity_minutes": INACTIVITY_MINUTES,
            "remember_days": REMEMBER_DAYS,
            "enabled_platforms": [k for k, v in PLATFORM_CONFIGS.items() if v.get("enabled", False)],
            "cache_running": context.AUTO_CACHE_MANAGER["running"],
        })


    @app.get("/api/chart-data")
    @login_required
    def api_chart_data():
        hour_counts = {}
        day_counts = {}

        for row in context.state.current_order_rows:
            sale_date = clean_text(row.get("sale_date", ""))
            dt = parse_sale_datetime(sale_date)
            if dt is None:
                continue

            hour_key = dt.strftime("%H:00")
            day_key = dt.strftime("%d-%m-%Y")

            hour_counts[hour_key] = hour_counts.get(hour_key, 0) + 1
            day_counts[day_key] = day_counts.get(day_key, 0) + 1

        hour_labels = [f"{h:02d}:00" for h in range(24)]
        hour_values = [hour_counts.get(label, 0) for label in hour_labels]

        sorted_days = sorted(day_counts.keys(), key=lambda d: datetime.strptime(d, "%d-%m-%Y"))
        day_labels = sorted_days[-14:]
        day_values = [day_counts[d] for d in day_labels]

        return jsonify({
            "hourly": {"labels": hour_labels, "values": hour_values},
            "daily": {"labels": day_labels, "values": day_values},
        })


    @app.get("/api/event-totals")
    @login_required
    def api_event_totals():
        try:
            totals = build_event_totals_from_cache(context.state.current_order_rows)
            return jsonify({"ok": True, "totals": totals})
        except Exception as e:
            return jsonify({"error": str(e)}), 500


    @app.get("/api/order-details/<source>/<order_id>")
    @login_required
    def api_order_details(source, order_id):
        try:
            if source == "LiveTicketGroup":
                details = get_ltg_order_details(order_id)
                cache_order_details(source, order_id, details)
                return jsonify({"ok": True, "details": details})

            if source == "FootballTicketNet":
                cache = load_order_details_cache()
                details = cache.get(f"{source}::{order_id}")
                if details:
                    return jsonify({"ok": True, "details": details})

                for row in context.state.current_order_rows:
                    if clean_text(row.get("source")) == source and clean_text(row.get("id")) == clean_text(order_id):
                        details = {
                            "event": row.get("event", "-"),
                            "league": row.get("league", "-"),
                            "venue": row.get("venue", "-"),
                            "event_date": row.get("event_date", "-"),
                            "status": row.get("status", "-"),
                            "customer_name": row.get("customer", "-"),
                            "customer_phone": row.get("phone", "-"),
                            "area": row.get("category", "-"),
                            "category": row.get("category", "-"),
                            "section": "-",
                            "row": "-",
                            "seating": "-",
                            "allocation": row.get("ticket_type", "-"),
                            "delivery": row.get("delivery_status", row.get("status", "-")),
                            "shipping": row.get("delivery_status", row.get("status", "-")),
                            "quantity": row.get("quantity", "0"),
                            "ticket_type": row.get("ticket_type", "-"),
                            "price": row.get("price_per_ticket", "0"),
                            "price_per_ticket": row.get("price_per_ticket", "0"),
                            "total_price": row.get("total_price", "0"),
                            "restrictions": "-",
                            "notes": row.get("comments", "-"),
                            "sale_date": row.get("sale_date", "-"),
                            "processed_on": "-",
                            "attendees": [],
                            "line_items": [[
                                row.get("category", "-"),
                                "-",
                                "-",
                                "-",
                                row.get("ticket_type", "-"),
                                row.get("delivery_status", row.get("status", "-")),
                                row.get("quantity", "0"),
                            ]],
                        }
                        cache_order_details(source, order_id, details)
                        return jsonify({"ok": True, "details": details})

                return jsonify({"error": f"No cached details found for FTN order: {order_id}"}), 404

            return jsonify({"error": f"Order details not implemented yet for source: {source}"}), 400

        except Exception as e:
            import traceback
            traceback.print_exc()
            context.state.log(f"Order details error for {source} #{order_id}: {e}")
            return jsonify({"error": str(e)}), 500

    @app.post("/api/start")
    @login_required
    def api_start():
        if context.state.running:
            return jsonify({"ok": True, "message": "Already running"})
        context.state.stop_event.clear()
        context.state.running = True
        context.state.worker_thread = threading.Thread(target=bot_worker, daemon=True)
        context.state.worker_thread.start()
        context.state.log("Start button pressed")
        return jsonify({"ok": True})


    @app.post("/api/stop")
    @login_required
    def api_stop():
        context.state.stop_event.set()
        context.state.running = False
        context.state.log("Stop button pressed")
        return jsonify({"ok": True})


    @app.post("/api/check-now")
    @login_required
    def api_check_now():
        def worker():
            seen_orders = context.state.load_seen_orders()
            try:
                if context.state.settings.get("sleep_window_enabled", False) and is_sleep_window():
                    context.state.log("Manual check skipped because sleep window is active")
                    return
                execute_check_cycle(seen_orders)
                context.state.log("Manual check finished")
            except Exception as e:
                context.state.log(f"Manual check failed: {e}")

        threading.Thread(target=worker, daemon=True).start()
        return jsonify({"ok": True})


    @app.post("/api/check-ticketsshop-listings")
    @login_required
    def api_check_ticketsshop():
        try:
            from config import TICKETSSHOP_RESULTS_FILE
            from core.storage import load_json_file, save_json_file
            from services.inventory_service import check_ticketsshop_bulk
            from services.telegram_service import send_telegram

            context.state.log("Ticketsshop check started...")

            results_cache = load_json_file(TICKETSSHOP_RESULTS_FILE, {})
            if not isinstance(results_cache, dict):
                results_cache = {}

            from core.helpers import is_event_expired

            all_rows = context.state.current_order_rows

            # Only check active LTG orders
            ltg_rows = [
                r for r in all_rows
                if r.get("source") == "LiveTicketGroup"
                and not is_event_expired(r.get("event_date", ""))
            ]

            # Check all orders (not just missing ones) so we can detect listed→missing transitions
            to_check = ltg_rows[:10]

            if not to_check:
                context.state.log("Ticketsshop check: no active LTG orders to check.")
                send_telegram(
                    "✅ TICKETSSHOP CHECK COMPLETE\n"
                    "All pending orders are listed.\n"
                    "No missing listings found."
                )
                return jsonify({"ok": True, "checked": 0, "listed": [], "missing": []})

            check_results = check_ticketsshop_bulk(to_check)
            listed_orders = check_results.get("listed", [])
            missing_orders = check_results.get("missing", [])

            for order in listed_orders:
                order_id = str(order.get("id"))
                event_name = str(order.get("event"))
                # Cache key = order_id only (unique per order)
                cache_key = order_id
                old_entry = results_cache.get(cache_key, {})
                old_status = old_entry.get("status") if isinstance(old_entry, dict) else old_entry

                # Alert only if status changed from non-listed to listed
                if old_status != "listed":
                    send_telegram(
                        f"✅ ORDER LISTED IN TICKETSHOP\n\n"
                        f"Live Order: {order_id}\n"
                        f"Event: {event_name}"
                    )
                    context.state.log(f"Ticketsshop: listed alert sent for order {order_id}")

                results_cache[cache_key] = {
                    "status": "listed",
                    "order_id": order_id,
                    "event": event_name,
                    "date": datetime.now().strftime("%Y-%m-%d")
                }

            for order in missing_orders:
                order_id = str(order.get("id"))
                event_name = str(order.get("event"))
                cache_key = order_id
                old_entry = results_cache.get(cache_key, {})
                old_status = old_entry.get("status") if isinstance(old_entry, dict) else old_entry

                # ALWAYS alert if:
                #   a) Never seen before (no cache entry)
                #   b) Previously listed, now missing  ← status change exception
                #   c) Previously missing (re-alert in case user missed it)
                should_alert = True
                if old_status == "missing":
                    # Already alerted as missing before — only re-alert if previously listed
                    should_alert = False  # suppress exact-same re-alert

                # Exception: was listed, now missing → always alert
                if old_status == "listed":
                    should_alert = True

                if should_alert:
                    send_telegram(
                        f"⚠️ ORDER NOT LISTED IN TICKETSHOP\n\n"
                        f"Live Order: {order_id}\n"
                        f"Event: {event_name}\n\n"
                        f"Action: Please check/list this order in Ticketshop."
                    )
                    context.state.log(f"Ticketsshop: missing alert sent for order {order_id} (was: {old_status})")

                results_cache[cache_key] = {
                    "status": "missing",
                    "order_id": order_id,
                    "event": event_name,
                    "date": datetime.now().strftime("%Y-%m-%d")
                }

            save_json_file(TICKETSSHOP_RESULTS_FILE, results_cache)
            context.state.log(f"Ticketsshop check done. Listed: {len(listed_orders)}, Missing: {len(missing_orders)}")

            return jsonify({
                "ok": True,
                "checked": len(to_check),
                "listed": [str(o.get("id")) for o in listed_orders],
                "missing": [str(o.get("id")) for o in missing_orders]
            })
        except Exception as e:
            import traceback
            err_trace = traceback.format_exc()
            context.state.log(f"Ticketsshop API Error: {str(e)}")
            print(f"Ticketsshop API Error:\n{err_trace}")
            return jsonify({"error": str(e), "trace": err_trace}), 500


    @app.post("/api/settings")
    @login_required
    def api_settings():
        data = request.get_json(force=True, silent=True) or {}
        try:
            context.state.settings["interval_minutes"] = max(1, int(data.get("interval_minutes", 30)))
            context.state.save_settings()
            context.state.log("Settings saved")
            return jsonify({"ok": True})
        except Exception:
            return jsonify({"error": "Invalid settings payload"}), 400


    @app.post("/api/toggle-setting")
    @login_required
    def api_toggle_setting():
        data = request.get_json(force=True, silent=True) or {}
        name = data.get("name", "")
        allowed = {
            "sleep_window_enabled",
            "monitor_liveticketgroup",
            "monitor_ticketshop",
            "monitor_footballticketnet",
            "monitor_fanpass",
            "monitor_tixstock",
        }
        if name not in allowed:
            return jsonify({"error": "Invalid setting name"}), 400
        context.state.settings[name] = not bool(context.state.settings.get(name))
        context.state.save_settings()
        context.state.log(f"Toggled {name} -> {context.state.settings[name]}")
        return jsonify({"ok": True})


    @app.get("/api/platform-states")
    @login_required
    def api_get_platform_states():
        keys = [
            "monitor_liveticketgroup",
            "monitor_ticketshop",
            "monitor_footballticketnet",
            "monitor_fanpass",
            "monitor_tixstock",
        ]
        return jsonify({k: context.state.settings.get(k, False) for k in keys})


    @app.post("/api/platform-states")
    @login_required
    def api_set_platform_states():
        data = request.get_json(force=True, silent=True) or {}
        allowed = {
            "monitor_liveticketgroup",
            "monitor_ticketshop",
            "monitor_footballticketnet",
            "monitor_fanpass",
            "monitor_tixstock",
        }
        updated = []
        for key, val in data.items():
            if key in allowed:
                context.state.settings[key] = bool(val)
                updated.append(key)
        if updated:
            context.state.save_settings()
            context.state.log(f"Platform states updated: {updated}")
        return jsonify({"ok": True, "updated": updated})


    @app.post("/api/users/add")
    @admin_required_api
    def api_users_add():
        data = request.get_json(force=True, silent=True) or {}
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        role = data.get("role", "member").strip()

        try:
            add_user(username, password, role=role)
            context.state.log(f"New member added -> {username}")
            return jsonify({"ok": True})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.post("/api/users/reset-password")
    @admin_required_api
    def api_users_reset_password():
        data = request.get_json(force=True, silent=True) or {}
        username = data.get("username", "").strip()
        new_password = data.get("password", "").strip()

        try:
            reset_user_password(username, new_password)
            context.state.log(f"Password reset -> {username}")
            return jsonify({"ok": True})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.post("/api/users/change-role")
    @admin_required_api
    def api_users_change_role():
        data = request.get_json(force=True, silent=True) or {}
        username = data.get("username", "").strip()
        role = data.get("role", "").strip()

        try:
            update_user_role(username, role)
            context.state.log(f"Role changed -> {username} ({role})")
            return jsonify({"ok": True})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.post("/api/users/toggle-active")
    @admin_required_api
    def api_users_toggle_active():
        data = request.get_json(force=True, silent=True) or {}
        username = data.get("username", "").strip()

        try:
            is_active = toggle_user_active(username)
            context.state.log(f"User active toggled -> {username} ({is_active})")
            return jsonify({"ok": True, "is_active": is_active})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400


    @app.post("/api/users/delete")
    @admin_required_api
    def api_users_delete():
        data = request.get_json(force=True, silent=True) or {}
        username = data.get("username", "").strip()

        if normalize_username(username).lower() == normalize_username(g.current_user.get("username", "")).lower():
            return jsonify({"error": "You cannot delete your own logged-in account"}), 400

        try:
            delete_user(username)
            context.state.log(f"User deleted -> {username}")
            return jsonify({"ok": True})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400




    @app.get("/api/recent-sent")
    @login_required
    def api_recent_sent():
        rows = context.state.sent_order_rows[:10]
        return jsonify({"ok": True, "rows": rows})

    @app.post("/api/test-order-telegram")
    @login_required
    def api_test_order_telegram():
        try:
            send_telegram("✅ Order alert Telegram test message")
            context.state.set_last_alert()
            context.state.log("Order test message sent")
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/api/check-footballticketnet-orders")
    @login_required
    def api_check_ftn():
        def worker():
            seen_orders = context.state.load_seen_orders()
            try:
                from services.order_service import execute_check_cycle
                execute_check_cycle(seen_orders)
                context.state.log("Manual FTN check finished")
            except Exception as e:
                context.state.log(f"Manual FTN check failed: {e}")

        threading.Thread(target=worker, daemon=True).start()
        return jsonify({"ok": True})

