from datetime import datetime, timedelta, timezone
from functools import wraps
import jwt
from flask import jsonify, request, redirect, url_for, g
from config import JWT_SECRET, JWT_ALGORITHM, ACCESS_COOKIE_NAME, INACTIVITY_MINUTES, REMEMBER_DAYS
from core.users import get_user

def make_token(user, remember=False):
    now = datetime.now(timezone.utc)
    inactivity_exp = now + timedelta(minutes=INACTIVITY_MINUTES)
    absolute_exp = now + timedelta(days=REMEMBER_DAYS if remember else 1)

    payload = {
        "sub": user["username"],
        "role": user.get("role", "member"),
        "remember": bool(remember),
        "iat": int(now.timestamp()),
        "inactive_until": int(inactivity_exp.timestamp()),
        "exp": int(absolute_exp.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def clear_auth_cookie(response):
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    return response


def set_auth_cookie(response, token, remember=False):
    max_age = REMEMBER_DAYS * 24 * 60 * 60 if remember else None
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        token,
        httponly=True,
        samesite="Lax",
        secure=False,
        max_age=max_age,
        path="/"
    )
    return response


def get_current_auth():
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        return None

    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        return None

    now_ts = int(datetime.now(timezone.utc).timestamp())
    inactive_until = int(payload.get("inactive_until", 0))
    if now_ts > inactive_until:
        return None

    username = payload.get("sub", "")
    user = get_user(username)
    if not user or not user.get("is_active", True):
        return None

    return {"user": user, "payload": payload}


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        auth = get_current_auth()
        if not auth:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login_page"))

        g.current_user = auth["user"]
        g.current_role = auth["user"].get("role", "member")
        g.remember_login = bool(auth["payload"].get("remember", False))
        g.refresh_auth_cookie = True
        return view_func(*args, **kwargs)
    return wrapper


def admin_required_api(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        auth = get_current_auth()
        if not auth:
            return jsonify({"error": "Unauthorized"}), 401
        if auth["user"].get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403

        g.current_user = auth["user"]
        g.current_role = "admin"
        g.remember_login = bool(auth["payload"].get("remember", False))
        g.refresh_auth_cookie = True
        return view_func(*args, **kwargs)
    return wrapper
