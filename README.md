# TicketOS

> A centralized operations platform for football ticket businesses.

TicketOS is an internal operations dashboard that centralizes ticket orders, customer management, platform monitoring, reporting, and automation across multiple ticket resale platforms.

Instead of logging into several supplier websites throughout the day, TicketOS provides one place to monitor your entire ticket operation.

---

# Why TicketOS?

Managing ticket sales across multiple supplier platforms quickly becomes difficult.

Different websites.
Different order systems.
Different customer lists.
Different reports.

TicketOS solves this by bringing everything together into a single dashboard.

---

# Features

## Multi-Platform Integration

Currently supports:

- ✅ LiveTicketGroup
- ✅ FootballTicketNet

Designed to support additional platforms in the future.

Examples:

- StubHub
- Viagogo
- Fanpass
- Ticombo
- TicketSwap

---

## Operations Center

View your business health in one place.

Monitor:

- Today's Orders
- Revenue
- Platform Status
- Last Synchronization
- Active Alerts
- Scraper Health
- Inventory Validation

---

## Order Management

Track every order from one dashboard.

Features:

- Order history
- Search
- Filters
- Platform source
- Customer details
- Order status
- Event information

---

## Customer CRM

Build customer profiles automatically from existing orders.

Includes:

- Customer history
- Lifetime spend
- Total orders
- Last purchase
- Favorite events
- Platform source

---

## Platform Health

Monitor every connected platform.

Features:

- Enable / Disable platforms
- Session status
- Cookie status
- Last successful sync
- Last error
- Manual Sync
- Credential verification

---

## Telegram Notifications

Receive instant notifications when new orders arrive.

Example:

```
🟢 New Order

Date: 2026-07-09 13:28

Platform:
FootballTicketNet

Event:
Liverpool vs Manchester City

Customer:
John Smith

Quantity:
2

Price:
£150.00
```

Duplicate notifications are automatically prevented.

---

## Reports

Generate Excel reports directly from the dashboard.

Available reports:

- Orders
- Customers
- Customer History
- Revenue
- Platform Summary

---

## Security

- JWT Authentication
- Password Hashing
- Role-Based Access

Roles:

- Admin
- Staff
- Viewer

---

## Logging

TicketOS keeps a structured application log.

Tracks:

- Platform errors
- Login attempts
- Synchronization history
- Export activity
- System events

---

## Automation

Automates repetitive operational tasks.

Examples:

- Order synchronization
- Platform monitoring
- Inventory validation
- Telegram alerts
- Scheduled checks

---

# Technology

Backend

- Python
- Flask
- SQLAlchemy
- Playwright
- curl-cffi

Database

- SQLite
- PostgreSQL (supported)

Frontend

- HTML
- CSS
- JavaScript

Deployment

- Docker
- Docker Compose

---

# Roadmap

Planned features include:

- More ticket platforms
- Profit analytics
- Customer lifetime value
- Revenue dashboard
- Inventory intelligence
- Automated workflows
- Email notifications
- Slack integration
- WhatsApp notifications
- API access

---

# Screenshots

_Add dashboard screenshots here._

---

# Installation

```bash
git clone https://github.com/LuffyAnonymous/OrderTicketNotification.git

cd OrderTicketNotification

python -m venv venv

venv\Scripts\activate

pip install -r requirements.txt

python app.py
```

Open:

```
http://127.0.0.1:5000
```

---

# Environment Variables

Create a `.env` file.

Example:

```
DATABASE_URL=
JWT_SECRET=

LTG_USERNAME=
LTG_PASSWORD=

FTN_USERNAME=
FTN_PASSWORD=

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

# Project Status

TicketOS is actively developed and used internally.

The platform continues to evolve with new integrations, automation features, reporting capabilities, and operational tools.

---

# License

Private software.

Not licensed for public redistribution without permission.

---

# Contact

If you're interested in using TicketOS for your own ticket operations or would like to discuss licensing or collaboration, feel free to get in touch.
