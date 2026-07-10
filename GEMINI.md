# TicketOS

## Project Vision

TicketOS is an internal operations platform for football ticket businesses.

Its goal is to centralize daily operations across multiple ticket resale platforms.

The software is designed for staff who spend all day managing:

- orders
- customers
- inventory
- platform health
- reports
- automation

This is NOT a generic admin dashboard.

Every screen should help staff complete work faster.

---

# Development Principles

Never rewrite the application.

Improve incrementally.

Preserve existing functionality.

Avoid regressions.

Reuse existing APIs whenever possible.

Never introduce duplicated logic.

---

# UI Philosophy

Information first.

Workflow before appearance.

Avoid:

- huge cards
- decorative charts
- gradients
- empty whitespace
- flashy animations

Prefer:

- compact layouts
- operational status
- dense information
- fast workflows

---

# Architecture

Backend

Flask

SQLAlchemy

Scheduler

Telegram

Playwright

SQLite (future MySQL support)

Frontend

HTML

CSS

Vanilla JavaScript

No SPA framework.

---

# Coding Standards

Reuse services.

Keep functions focused.

Prefer composition over duplication.

Maintain RBAC.

Maintain structured logging.

Keep tests passing.

---

# Workflow

Before coding:

Review current implementation.

Explain findings.

Identify risks.

Propose plan.

Implement.

Run tests.

Summarize files changed.

Wait for approval.

---

# Current Roadmap

Sprint 1
Operations Center

✅ Complete

Sprint 2
Orders Workspace

✅ Complete

Sprint 3
Customer CRM

Pending

Sprint 4
Platform Center

Pending

Sprint 5
Alerts Center

Pending

Sprint 6
Automation Center

Pending

Sprint 7
Reports & Analytics

Pending

Sprint 8
AI Operations Assistant

Pending

---

# Long-Term Goal

TicketOS should become the operating system for football ticket businesses.

It should replace logging into multiple supplier platforms throughout the day.

The software should provide:

- one dashboard
- one customer database
- one order workspace
- one reporting system
- one automation center