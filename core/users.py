from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from config import USERS_FILE, ADMIN_USERNAME, ADMIN_PASSWORD
from core.storage import load_json_file, save_json_file

def load_users():
    data = load_json_file(USERS_FILE, [])
    return data if isinstance(data, list) else []


def save_users(users):
    save_json_file(USERS_FILE, users)


def ensure_admin_user():
    users = load_users()
    if users:
        return
    users.append({
        "username": ADMIN_USERNAME,
        "password_hash": generate_password_hash(ADMIN_PASSWORD),
        "role": "admin",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_active": True
    })
    save_users(users)


def normalize_username(username):
    return (username or "").strip()


def get_user(username):
    uname = normalize_username(username).lower()
    for user in load_users():
        if normalize_username(user.get("username", "")).lower() == uname:
            return user
    return None


def safe_user_view(user):
    return {
        "username": user.get("username", ""),
        "role": user.get("role", "member"),
        "created_at": user.get("created_at", "-"),
        "is_active": bool(user.get("is_active", True)),
    }


def add_user(username, password, role="member"):
    username = normalize_username(username)
    password = (password or "").strip()

    if not username or not password:
        raise ValueError("Username and password are required")
    if get_user(username):
        raise ValueError("Username already exists")

    users = load_users()
    users.append({
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": role if role in {"admin", "member"} else "member",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_active": True
    })
    save_users(users)


def update_user_role(username, new_role):
    if new_role not in {"admin", "member"}:
        raise ValueError("Invalid role")

    users = load_users()
    found = False
    for user in users:
        if normalize_username(user.get("username", "")).lower() == normalize_username(username).lower():
            user["role"] = new_role
            found = True
            break

    if not found:
        raise ValueError("User not found")

    save_users(users)


def reset_user_password(username, new_password):
    new_password = (new_password or "").strip()
    if not new_password:
        raise ValueError("Password is required")

    users = load_users()
    found = False
    for user in users:
        if normalize_username(user.get("username", "")).lower() == normalize_username(username).lower():
            user["password_hash"] = generate_password_hash(new_password)
            found = True
            break

    if not found:
        raise ValueError("User not found")

    save_users(users)


def toggle_user_active(username):
    users = load_users()
    found = None
    for user in users:
        if normalize_username(user.get("username", "")).lower() == normalize_username(username).lower():
            user["is_active"] = not bool(user.get("is_active", True))
            found = user
            break

    if not found:
        raise ValueError("User not found")

    save_users(users)
    return bool(found.get("is_active", True))


def delete_user(username):
    uname = normalize_username(username)
    users = load_users()

    if uname.lower() == ADMIN_USERNAME.lower():
        raise ValueError("Default admin cannot be deleted")

    filtered = [u for u in users if normalize_username(u.get("username", "")).lower() != uname.lower()]
    if len(filtered) == len(users):
        raise ValueError("User not found")

    save_users(filtered)


def verify_user(username, password):
    user = get_user(username)
    if not user:
        return None
    if not user.get("is_active", True):
        return None
    if check_password_hash(user.get("password_hash", ""), password or ""):
        return user
    return None
