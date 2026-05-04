-- init_db.sql

CREATE TABLE IF NOT EXISTS platforms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(100),
    event_name TEXT NOT NULL,
    event_date TIMESTAMP,
    is_past_event BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, event_name)
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(100) NOT NULL,
    order_number VARCHAR(100) NOT NULL,
    event_name TEXT,
    event_date TIMESTAMP,
    customer_name VARCHAR(500),
    mobile_number VARCHAR(500),
    email VARCHAR(500),
    sale_date TIMESTAMP,
    raw_status VARCHAR(255),
    resale_status VARCHAR(255),
    dashboard_status VARCHAR(100),
    ticketshop_status VARCHAR(100) DEFAULT 'unchecked',
    category TEXT,
    section TEXT,
    row_name TEXT,
    seat_number TEXT,
    seat_details TEXT,
    quantity INTEGER,
    total_value NUMERIC(12, 2),
    currency VARCHAR(20),
    list_price_per_ticket NUMERIC(12, 2),
    shipping_method TEXT,
    shipping_price NUMERIC(12, 2),
    total_amount NUMERIC(12, 2),
    billing_full_name VARCHAR(500),
    billing_mobile VARCHAR(500),
    pod_status VARCHAR(255),
    delivery_status VARCHAR(255),
    ticket_links_submitted BOOLEAN DEFAULT FALSE,
    broker_name VARCHAR(500),
    source_url TEXT,
    is_visible_on_platform BOOLEAN DEFAULT TRUE,
    is_past_event BOOLEAN DEFAULT FALSE,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details_fetched_at TIMESTAMP,
    raw_payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, order_number)
);

CREATE TABLE IF NOT EXISTS order_alerts (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(100) NOT NULL,
    order_number VARCHAR(100) NOT NULL,
    event_name TEXT,
    alert_type VARCHAR(100),
    alert_message TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, order_number, alert_type)
);

CREATE TABLE IF NOT EXISTS app_events (
    id SERIAL PRIMARY KEY,
    level VARCHAR(50),
    source VARCHAR(100),
    message TEXT,
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ticketshop_checks (
    id SERIAL PRIMARY KEY,
    live_order_number VARCHAR(100) NOT NULL,
    event_name TEXT,
    previous_status VARCHAR(100),
    current_status VARCHAR(100),
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_status_checks (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(100),
    event_name TEXT,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_orders INTEGER DEFAULT 0,
    pending_count INTEGER DEFAULT 0,
    cancelled_count INTEGER DEFAULT 0,
    resold_count INTEGER DEFAULT 0,
    completed_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS order_status_check_items (
    id SERIAL PRIMARY KEY,
    check_id INTEGER REFERENCES order_status_checks(id) ON DELETE CASCADE,
    order_number VARCHAR(100),
    customer_name VARCHAR(500),
    sale_date TIMESTAMP,
    raw_status VARCHAR(255),
    resale_status VARCHAR(255),
    dashboard_status VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Initial platforms
INSERT INTO platforms (name) VALUES 
('LiveTicketGroup'), 
('FootballTicketNet'), 
('Ticketshop'), 
('Fanpass'), 
('Tixstock') 
ON CONFLICT (name) DO NOTHING;
