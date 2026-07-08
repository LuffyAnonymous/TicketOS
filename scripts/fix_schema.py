import os
import sys
sys.path.append(os.getcwd())
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
load_dotenv()
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)
with engine.connect() as conn:
    print("Checking and fixing database schema...")
    
    # 1. Check orders table
    try:
        conn.execute(text("SELECT event_date FROM orders LIMIT 1"))
        print("Column event_date exists in orders")
    except Exception:
        # conn.rollback()
        print("Attempting to add event_date to orders")
        try:
            conn.execute(text("ALTER TABLE orders ADD COLUMN event_date TIMESTAMP"))
            # conn.commit()
            print("Successfully added event_date to orders")
        except Exception as e:
            print(f"Failed to add column: {e}")

    # 2. Re-create all tables just in case
    from database import Base
    Base.metadata.create_all(bind=engine)
    print("Base.metadata.create_all(bind=engine) executed")
    
    print("Schema fix complete.")
