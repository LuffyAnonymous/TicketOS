# TicketOS — Ticket Sales Operations Dashboard

TicketOS is a central business intelligence and monitoring dashboard for managing ticket sales operations. It automates order synchronization, tracks customer purchase histories, generates operational reports, and alerts managers to important platform changes.

---

##  How to Run Locally

### Prerequisites
* Python 3.10+
* Google Chrome or Chromium (for Playwright browser automation)

### 1. Set Up Virtual Environment
```bash
python -m venv venv
# On Windows PowerShell:
venv\Scripts\Activate.ps1
# On Linux/macOS:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and fill in the values:
```bash
cp .env.example .env
```
Ensure you set secure values for `ADMIN_PASSWORD` and `JWT_SECRET`!

### 4. Launch Application
```bash
python app.py
```
Open `http://127.0.0.1:5000` in your web browser and log in with your configured admin credentials.

---

##  Running with Docker

Docker simplifies VPS deployment by packaging all Chromium and library dependencies automatically.

### Build and Run with Docker Compose
```bash
docker-compose up -d --build
```
This boots the app on port `5000` and creates a persistent volume `ticketos-data` to preserve the SQLite database, configurations, and logs.

---

## ⚙️ Environment Variables Config

| Variable | Description | Required | Example |
| :--- | :--- | :---: | :--- |
| `PORT` | Listening port for the Flask app server | No | `5000` |
| `ADMIN_USERNAME` | Administrator account login name | Yes | `admin` |
| `ADMIN_PASSWORD` | Administrator account login password | Yes | `MySecurePassword123!` |
| `JWT_SECRET` | Secret key used to sign session cookies | Yes | `ab4382...e01` |
| `TELEGRAM_BOT_TOKEN` | Bot token for dispatching scraper alerts | Yes | `123456:ABC-DEF` |
| `TELEGRAM_CHAT_ID` | Telegram chat/group ID for alerts | Yes | `-987654321` |
| `LTG_USERNAME` | LiveTicketGroup username/email | Yes | `ltg_manager` |
| `LTG_PASSWORD` | LiveTicketGroup login password | Yes | `my_ltg_pass` |
| `FTN_USERNAME` | FootballTicketNet email/username | Yes | `ftn_manager` |
| `FTN_PASSWORD` | FootballTicketNet login password | Yes | `my_ftn_pass` |
| `DATABASE_URL` | Production PostgreSQL connection URL | No | `postgresql://user:pass@host:5432/db` |

---

## Production Readiness Checklist
1. **Password Enforcement**: Ensure `ADMIN_PASSWORD` is changed from `admin123`.
2. **Secrets Rotation**: Set a cryptographically secure value (e.g. 64 hex characters) for `JWT_SECRET` in production.
3. **Telegram Channel**: Verify that your Telegram bot is added to your target channel/group and has messaging permissions.
4. **SSL/TLS Certificate**: Always serve TicketOS behind Nginx, Caddy, or Cloudflare Tunnel with HTTPS enabled.

---

##  Database Backups

### 1. SQLite Backup (Default Local Deployment)
SQLite stores all data in a single file `order_ticket_db.sqlite`. To back it up, run a cron job to copy the file safely:
```bash
# Every night at 2 AM
0 2 * * * cp /app/order_ticket_db.sqlite /backups/db_$(date +\%F).sqlite
```

### 2. PostgreSQL Backup (Production Recommended)
For production databases, use `pg_dump` to create logical backups:
```bash
# Every night at 2 AM
0 2 * * * pg_dump -d $DATABASE_URL -F c -b -v -f /backups/db_$(date +\%F).dump
```

---

## ☁️ VPS Deployment Notes

### Using Nginx Reverse Proxy
To deploy on a standard Ubuntu VPS, configure Nginx as a reverse proxy to forward traffic to your Flask app or Docker container running on port `5000`:

```nginx
server {
    listen 80;
    server_name ticketos.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name ticketos.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/ticketos.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ticketos.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
