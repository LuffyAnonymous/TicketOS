import os
import jwt
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, g, make_response
from functools import wraps
from config import JWT_SECRET, REMEMBER_DAYS
from core.users import verify_user as check_user, add_user, update_user_role, reset_user_password, toggle_user_active, delete_user, load_users, safe_user_view

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
    try:
        data = request.json or {}
        u, p, rem = data.get("username"), data.get("password"), data.get("remember", False)
        user = check_user(u, p)
        if user:
            exp = datetime.utcnow() + timedelta(days=REMEMBER_DAYS if rem else 1)
            token = jwt.encode({"username": u, "role": user["role"], "exp": exp}, JWT_SECRET, algorithm="HS256")
            resp = jsonify({"ok": True, "role": user["role"]})
            resp.set_cookie("token", token, httponly=True, samesite="Strict", max_age=int(timedelta(days=REMEMBER_DAYS if rem else 1).total_seconds()))
            return resp
        return jsonify({"error": "Invalid credentials"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route("/api/users/add", methods=["POST"])
@login_required
def api_add_user():
    if g.current_user.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    try:
        data = request.json or {}
        username = data.get("username")
        password = data.get("password")
        role = data.get("role", "member")
        add_user(username, password, role)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@auth_bp.route("/api/users/change-role", methods=["POST"])
@login_required
def api_change_role():
    if g.current_user.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
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
@login_required
def api_reset_password():
    if g.current_user.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
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
@login_required
def api_toggle_active():
    if g.current_user.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
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
@login_required
def api_delete_user():
    if g.current_user.get("role") != "admin":
        return jsonify({"error": "Admin access required"}), 403
    try:
        data = request.json or {}
        username = data.get("username")
        delete_user(username)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
