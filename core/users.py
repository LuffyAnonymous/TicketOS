from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from config import ADMIN_USERNAME, ADMIN_PASSWORD
from database import get_db, DBUser

def load_users():
    """
    Returns a list of dicts representing all users from the database.
    """
    db = get_db()
    if not db:
        return []
    try:
        users = db.query(DBUser).all()
        return [{
            "username": u.username,
            "password_hash": u.password_hash,
            "role": u.role,
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else "-",
            "is_active": u.is_active
        } for u in users]
    except Exception as e:
        print(f"Error loading users from database: {e}")
        return []
    finally:
        db.close()

def save_users(users):
    """
    Deprecated. No-op since users are written directly to the database.
    """
    pass

def ensure_admin_user():
    """
    Ensures that the default admin user exists in the database.
    """
    db = get_db()
    if not db:
        return
    try:
        exists = db.query(DBUser).filter(DBUser.username == ADMIN_USERNAME).first()
        if not exists:
            # Hash the ADMIN_PASSWORD (which is validated to be secure)
            db.add(DBUser(
                username=ADMIN_USERNAME,
                password_hash=generate_password_hash(ADMIN_PASSWORD),
                role="admin",
                is_active=True
            ))
            db.commit()
    except Exception as e:
        print(f"Error ensuring admin user in database: {e}")
    finally:
        db.close()

def normalize_username(username):
    return (username or "").strip()

def get_user(username):
    """
    Returns a dictionary for a specific user if found, else None.
    """
    db = get_db()
    if not db:
        return None
    try:
        uname = normalize_username(username).lower()
        u = db.query(DBUser).filter(DBUser.username.ilike(uname)).first()
        if u:
            return {
                "username": u.username,
                "password_hash": u.password_hash,
                "role": u.role,
                "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else "-",
                "is_active": u.is_active
            }
        return None
    except Exception as e:
        print(f"Error getting user: {e}")
        return None
    finally:
        db.close()

def safe_user_view(user):
    return {
        "username": user.get("username", ""),
        "role": user.get("role", "member"),
        "created_at": user.get("created_at", "-"),
        "is_active": bool(user.get("is_active", True)),
    }

def add_user(username, password, role="member"):
    """
    Registers a new user in the database.
    """
    username = normalize_username(username)
    password = (password or "").strip()

    if not username or not password:
        raise ValueError("Username and password are required")
        
    db = get_db()
    if not db:
        raise RuntimeError("Database not available")
    try:
        exists = db.query(DBUser).filter(DBUser.username.ilike(username)).first()
        if exists:
            raise ValueError("Username already exists")

        db.add(DBUser(
            username=username,
            password_hash=generate_password_hash(password),
            role=role if role in {"admin", "member"} else "member",
            is_active=True
        ))
        db.commit()
    finally:
        db.close()

def update_user_role(username, new_role):
    if new_role not in {"admin", "member"}:
        raise ValueError("Invalid role")

    db = get_db()
    if not db:
        raise RuntimeError("Database not available")
    try:
        u = db.query(DBUser).filter(DBUser.username.ilike(normalize_username(username))).first()
        if not u:
            raise ValueError("User not found")
        u.role = new_role
        db.commit()
    finally:
        db.close()

def reset_user_password(username, new_password):
    new_password = (new_password or "").strip()
    if not new_password:
        raise ValueError("Password is required")

    db = get_db()
    if not db:
        raise RuntimeError("Database not available")
    try:
        u = db.query(DBUser).filter(DBUser.username.ilike(normalize_username(username))).first()
        if not u:
            raise ValueError("User not found")
        u.password_hash = generate_password_hash(new_password)
        db.commit()
    finally:
        db.close()

def toggle_user_active(username):
    db = get_db()
    if not db:
        raise RuntimeError("Database not available")
    try:
        u = db.query(DBUser).filter(DBUser.username.ilike(normalize_username(username))).first()
        if not u:
            raise ValueError("User not found")
        u.is_active = not u.is_active
        is_active = u.is_active
        db.commit()
        return is_active
    finally:
        db.close()

def delete_user(username):
    uname = normalize_username(username)
    if uname.lower() == ADMIN_USERNAME.lower():
        raise ValueError("Default admin cannot be deleted")

    db = get_db()
    if not db:
        raise RuntimeError("Database not available")
    try:
        u = db.query(DBUser).filter(DBUser.username.ilike(uname)).first()
        if not u:
            raise ValueError("User not found")
        db.delete(u)
        db.commit()
    finally:
        db.close()

def verify_user(username, password):
    db = get_db()
    if not db:
        return None
    try:
        uname = normalize_username(username).lower()
        u = db.query(DBUser).filter(DBUser.username.ilike(uname)).first()
        if not u:
            return None
        if not u.is_active:
            return None
        if check_password_hash(u.password_hash, password or ""):
            return {
                "username": u.username,
                "role": u.role,
                "is_active": u.is_active
            }
        return None
    except Exception as e:
        print(f"Error verifying user: {e}")
        return None
    finally:
        db.close()
