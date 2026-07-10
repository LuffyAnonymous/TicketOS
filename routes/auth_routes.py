import os
import jwt
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, g, make_response
from functools import wraps
from config import JWT_SECRET, REMEMBER_DAYS
from core.users import verify_user as check_user, add_user, update_user_role, reset_user_password, toggle_user_active, delete_user, load_users, safe_user_view
from database import get_db, DBAppEvent

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("token")
        if not token:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            g.current_user = data
        except Exception:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.cookies.get("token")
            if not token:
                return jsonify({"error": "Unauthorized"}), 401
            try:
                data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
                g.current_user = data
            except Exception:
                return jsonify({"error": "Unauthorized"}), 401
                
            user_role = g.current_user.get("role", "viewer").lower()
            if user_role not in [r.lower() for r in allowed_roles]:
                return jsonify({"error": "Forbidden - Insufficient permissions"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

@auth_bp.route("/login")
def login():
    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    resp = make_response(render_template("login.html"))
    resp.delete_cookie("token")
    return resp

@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    db = get_db()
    try:
        data = request.json or {}
        u, p, rem = data.get("username"), data.get("password"), data.get("remember", False)
        user = check_user(u, p)
        if user:
            exp = datetime.utcnow() + timedelta(days=REMEMBER_DAYS if rem else 1)
            token = jwt.encode({"username": u, "role": user["role"], "exp": exp}, JWT_SECRET, algorithm="HS256")
            resp = jsonify({"ok": True, "role": user["role"]})
            resp.set_cookie("token", token, httponly=True, samesite="Strict", max_age=int(timedelta(days=REMEMBER_DAYS if rem else 1).total_seconds()))
            
            if db:
                db.add(DBAppEvent(
                    level="INFO",
                    source="auth",
                    message=f"User {u} successfully logged in",
                    details={"action": "login", "username": u, "status": "success", "role": user["role"]}
                ))
                db.commit()
            return resp
            
        if db:
            db.add(DBAppEvent(
                level="WARNING",
                source="auth",
                message=f"Failed login attempt for username: {u}",
                details={"action": "login", "username": u, "status": "failure"}
            ))
            db.commit()
        return jsonify({"error": "Invalid credentials"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if db:
            db.close()

@auth_bp.route("/api/users/add", methods=["POST"])
@role_required(["admin"])
def api_add_user():
    try:
        data = request.json or {}
        username = data.get("username")
        password = data.get("password")
        role = data.get("role", "viewer")
        add_user(username, password, role)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route("/api/users/change-role", methods=["POST"])
@role_required(["admin"])
def api_change_role():
    try:
        data = request.json or {}
        username = data.get("username")
        role = data.get("role")
        update_user_role(username, role)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route("/api/users/reset-password", methods=["POST"])
@role_required(["admin"])
def api_reset_password():
    try:
        data = request.json or {}
        username = data.get("username")
        password = data.get("password")
        reset_user_password(username, password)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route("/api/users/toggle-active", methods=["POST"])
@role_required(["admin"])
def api_toggle_active():
    try:
        data = request.json or {}
        username = data.get("username")
        toggle_user_active(username)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route("/api/users/delete", methods=["POST"])
@role_required(["admin"])
def api_delete_user():
    try:
        data = request.json or {}
        username = data.get("username")
        delete_user(username)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
