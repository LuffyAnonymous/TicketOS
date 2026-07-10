import os
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, Numeric, UniqueConstraint, ForeignKey, text, or_, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from config import DATABASE_URL

Base = declarative_base()

DB_ENGINE_TYPE = "sqlite"

def get_engine_type():
    global DB_ENGINE_TYPE
    return DB_ENGINE_TYPE

class DBUser(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default='member')
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

class DBSettings(Base):
    __tablename__ = 'settings'
    key = Column(String(100), primary_key=True)
    value = Column(JSON)

class DBPlatform(Base):
    __tablename__ = 'platforms'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DBEvent(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    platform = Column(String(100))
    event_name = Column(Text, nullable=False)
    event_date = Column(DateTime, nullable=True)
    is_past_event = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint('platform', 'event_name', name='_platform_event_uc'),)

class DBOrder(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    platform = Column(String(100), nullable=False)
    order_number = Column(String(100), nullable=False)
    event_name = Column(Text)
    event_date = Column(DateTime)
    customer_name = Column(String(500))
    mobile_number = Column(String(500))
    email = Column(String(500))
    sale_date = Column(DateTime)
    raw_status = Column(String(255))
    resale_status = Column(String(255))
    dashboard_status = Column(String(100)) # Keep it for backwards compatibility if needed, but adding normalized_status
    normalized_status = Column(String(100)) # pending, cancelled, resold, completed
    ticketshop_status = Column(String(100), default='unchecked')
    category = Column(Text)
    section = Column(Text)
    row_name = Column(Text)
    seat_number = Column(Text)
    seat_details = Column(Text)
    quantity = Column(Integer)
    total_value = Column(Numeric(12, 2))
    currency = Column(String(20))
    list_price_per_ticket = Column(Numeric(12, 2))
    shipping_type = Column(Text)
    shipping_amount = Column(Numeric(12, 2))
    total_amount = Column(Numeric(12, 2))
    billing_full_name = Column(String(500))
    billing_mobile = Column(String(500))
    pod_status = Column(String(255))
    delivery_status = Column(String(255))
    ticket_links_submitted = Column(Boolean, default=False)
    broker_name = Column(String(500))
    source_url = Column(Text)
    is_visible_on_platform = Column(Boolean, default=True)
    is_past_event = Column(Boolean, default=False)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    details_fetched_at = Column(DateTime)
    raw_payload = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint('platform', 'order_number', name='_platform_order_uc'),)

class DBOrderAlert(Base):
    __tablename__ = 'order_alerts'
    id = Column(Integer, primary_key=True)
    platform = Column(String(100), nullable=False)
    order_number = Column(String(100), nullable=False)
    event_name = Column(Text)
    alert_type = Column(String(100))
    alert_message = Column(Text)
    sent_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('platform', 'order_number', 'alert_type', name='_alert_uc'),)

class DBTicketshopCheck(Base):
    __tablename__ = 'ticketshop_checks'
    id = Column(Integer, primary_key=True)
    live_order_number = Column(String(100), nullable=False)
    event_name = Column(Text)
    previous_status = Column(String(100))
    current_status = Column(String(100))
    checked_at = Column(DateTime, default=datetime.utcnow)

class DBOrderStatusCheck(Base):
    __tablename__ = 'order_status_checks'
    id = Column(Integer, primary_key=True)
    platform = Column(String(100))
    event_name = Column(Text)
    checked_at = Column(DateTime, default=datetime.utcnow)
    total_orders = Column(Integer, default=0)
    pending_count = Column(Integer, default=0)
    cancelled_count = Column(Integer, default=0)
    resold_count = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    items = relationship("DBOrderStatusCheckItem", backref="check", cascade="all, delete-orphan")

class DBOrderStatusCheckItem(Base):
    __tablename__ = 'order_status_check_items'
    id = Column(Integer, primary_key=True)
    check_id = Column(Integer, ForeignKey('order_status_checks.id', ondelete='CASCADE'))
    order_number = Column(String(100))
    customer_name = Column(String(500))
    sale_date = Column(DateTime)
    raw_status = Column(String(255))
    resale_status = Column(String(255))
    normalized_status = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

class DBAppEvent(Base):
    __tablename__ = 'app_events'
    id = Column(Integer, primary_key=True)
    level = Column(String(50))
    source = Column(String(100))
    message = Column(Text)
    details = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    try:
        return SessionLocal()
    except Exception:
        return None

def test_db_connection():
    db = get_db()
    if not db: return False
    try:
        db.execute(text("SELECT 1"))
        return True
    except: return False
    finally: db.close()

def init_db():
    global engine, SessionLocal, DB_ENGINE_TYPE
    
    is_pg = False
    if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
        is_pg = True
        
    is_connected = False
    try:
        if DATABASE_URL:
            temp_engine = create_engine(DATABASE_URL)
            with temp_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            is_connected = True
            engine = temp_engine
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            if is_pg:
                DB_ENGINE_TYPE = "postgresql"
            else:
                DB_ENGINE_TYPE = "sqlite"
    except Exception as e:
        is_connected = False
        print(f"Database connection to {DATABASE_URL} failed: {e}")

    if not is_connected:
        print("\nSwitching to fallback local SQLite database...")
        db_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "order_ticket_db.sqlite")
        sqlite_url = f"sqlite:///{db_file}"
        engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        DB_ENGINE_TYPE = "sqlite"

    Base.metadata.create_all(bind=engine)
    
    db = get_db()
    if db:
        try:
            # Add initial platforms if missing
            for p_name in ["LiveTicketGroup", "FootballTicketNet", "Ticketshop", "Fanpass", "Tixstock"]:
                exists = db.query(DBPlatform).filter(DBPlatform.name == p_name).first()
                if not exists:
                    db.add(DBPlatform(name=p_name))
            db.commit()
            
            # Migrate existing users.json to DB
            from config import USERS_FILE
            from core.storage import load_json_file
            if os.path.exists(USERS_FILE):
                users_data = load_json_file(USERS_FILE, [])
                if users_data:
                    for u in users_data:
                        exists = db.query(DBUser).filter(DBUser.username == u.get("username")).first()
                        if not exists:
                            db.add(DBUser(
                                username=u.get("username"),
                                password_hash=u.get("password_hash"),
                                role=u.get("role", "member"),
                                is_active=u.get("is_active", True)
                            ))
                    db.commit()
                    
            # Migrate existing combined_alert_settings.json to DB
            from config import SETTINGS_FILE
            if os.path.exists(SETTINGS_FILE):
                try:
                    with open(SETTINGS_FILE, "r") as f:
                        settings_data = json.load(f)
                    if settings_data and isinstance(settings_data, dict):
                        for k, v in settings_data.items():
                            exists = db.query(DBSettings).filter(DBSettings.key == k).first()
                            if not exists:
                                db.add(DBSettings(key=k, value=v))
                        db.commit()
                except Exception as se:
                    print(f"Error migrating settings: {se}")
        except Exception as e:
            print(f"Error seeding platforms or migrating files: {e}")
        finally:
            db.close()
