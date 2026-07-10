# Gillian Bevan Fuel Station Management System
## Django Architecture (Updated per Client Clarifications)

### Clarifications incorporated
1. **2 shifts/day** (Day + Night) — station runs 24 hours
2. **Cash reconciliation is required**: manager enters actual cash submitted; system compares it against calculated cash due and flags the variance
3. **No manager login/passwords** — manager just selects their name from a dropdown per shift
4. **Web-accessible from anywhere** (site is outside Harare) — manager captures data on-site via tablet browser; Admin/Owner can check stock & sales remotely

---

## 1. Project Structure (single-app, matching your actual layout)

Since everything lives in one `main` app, the structure is flatter — logical
grouping now happens *inside* files/folders rather than across separate apps:

```
fueltracker/
├── manage.py
├── fueltracker/                    # Django project config
│   ├── settings.py
│   ├── urls.py                      # includes main.urls
│   └── wsgi.py
├── main/                            # single app — everything lives here
│   ├── migrations/
│   ├── templates/
│   │   └── main/
│   │       ├── layout.html          # shared base template (nav, auth check)
│   │       ├── index.html
│   │       ├── manager/             # manager-facing entry screens
│   │       │   ├── shift_start.html
│   │       │   ├── meter_entry.html
│   │       │   ├── fuel_receipt.html
│   │       │   ├── tank_return.html
│   │       │   └── shift_close.html
│   │       └── admin/                # admin-facing dashboard/reports
│   │           ├── dashboard.html
│   │           ├── price_edit.html
│   │           └── reports.html
│   ├── __init__.py
│   ├── admin.py                      # Django admin registrations (handy for Admin role)
│   ├── apps.py
│   ├── models.py                     # all models — see models.py below
│   ├── forms.py                      # ModelForms for shift entry, price update, etc.
│   ├── urls.py                       # all routes, namespaced by prefix (manager/, admin/)
│   ├── views.py                      # organize with clear section comments (see below)
│   ├── exports.py                    # openpyxl Excel export logic
│   ├── permissions.py                # shared-PIN gate decorator + admin-required decorator
│   └── tests.py
├── static/
│   ├── media/
│   ├── static_files/
│   └── static_root/
└── venv/
```

**Since it's one app, keep `views.py` organized with clear section headers** so it doesn't turn into an unreadable file as it grows:

```python
# views.py

# ── Manager views (shared-PIN gate, no login) ──────────────
def shift_start(request): ...
def meter_entry(request, shift_id): ...
def fuel_receipt(request, shift_id): ...
def tank_return(request, shift_id): ...
def shift_close(request, shift_id): ...

# ── Admin views (login_required) ───────────────────────────
@login_required
def dashboard(request): ...

@login_required
def price_edit(request): ...

@login_required
def reports(request): ...
```

If `views.py` grows past a few hundred lines, it's easy to later split it into
`views/manager.py` and `views/admin.py` (turn `views.py` into a `views/`
package with an `__init__.py`) — no model changes needed, so this is a
safe refactor to defer until it's actually needed.

**`urls.py` — namespace by prefix so manager vs admin routes are obvious:**

```python
# main/urls.py
from django.urls import path
from . import views

app_name = "main"

urlpatterns = [
    path("", views.index, name="index"),

    # Manager-facing (shared PIN gate applied via decorator/middleware)
    path("shift/start/", views.shift_start, name="shift_start"),
    path("shift/<int:shift_id>/meter/", views.meter_entry, name="meter_entry"),
    path("shift/<int:shift_id>/receipt/", views.fuel_receipt, name="fuel_receipt"),
    path("shift/<int:shift_id>/return/", views.tank_return, name="tank_return"),
    path("shift/<int:shift_id>/close/", views.shift_close, name="shift_close"),

    # Admin-facing (login_required)
    path("admin-dashboard/", views.dashboard, name="dashboard"),
    path("admin-dashboard/price/", views.price_edit, name="price_edit"),
    path("admin-dashboard/reports/", views.reports, name="reports"),
]
```

**Note:** A single-app structure is a perfectly good fit for this project's
size — no need to split into multiple Django apps unless the system grows
substantially (e.g., you later add multi-station support company-wide). The
`models.py` file below doesn't change based on this decision.

---

## 2. Access Model (No manager login)

Since managers don't have passwords, security is handled differently:

- The **manager-entry pages** sit behind a single **shared site PIN/passcode** (not tied to an individual), just to keep the URL from being wide open to the public internet. Enter once per session/tablet.
- The manager then **selects their name from a dropdown** (`Manager` model) — this identifies *who* entered the shift data, without requiring a personal login.
- The **Admin dashboard** (price changes, company-wide reports) sits behind normal Django `auth.User` login — this is the one place that needs proper authentication, since price changes and financial oversight are sensitive.

This gives you a practical balance: fast, frictionless entry for managers on a shared tablet, but real access control around the money-sensitive Admin functions.

---

## 3. Request Flow

```
Manager (tablet, on-site) ──▶ shared PIN gate ──▶ select name + shift type (Day/Night)
        │
        ▼
  Enter closing meter readings, fuel received, returns, cash submitted
        │
        ▼
  Django view calculates: litres sold, cash due (locked-in price), variance
        │
        ▼
  Saved to PostgreSQL (single source of truth)
        │
        ▼
Admin (anywhere, web) ──▶ Django login ──▶ Dashboard: stock, sales, variances, price editor, Excel export
```

---

## 4. Deployment (matches your EC2 + Postgres plan)

- **Gunicorn** (WSGI server) + **Nginx** (reverse proxy, serves static files, handles SSL via Let's Encrypt)
- **PostgreSQL** running on the same EC2 instance
- **Django settings**: `ALLOWED_HOSTS` set to your domain, `DEBUG=False`, static files collected via `collectstatic`, environment variables (DB credentials, `SECRET_KEY`) loaded via `.env` / `django-environ`
- Since it's accessed remotely, make sure to enforce **HTTPS only** (tablets and remote admin access both benefit from this) — Let's Encrypt certs are free and renew automatically via `certbot`

---

## 5. Key Design Decisions Reflected in Models (see `models.py`)

- `Shift` now has a `shift_type` field (`day` / `night`) plus `shift_date`, so you get 2 shifts/day naturally, each independently reconciled.
- `Shift` has a `cash_submitted` field (entered by manager) alongside the system's calculated `cash_due_total` (derived from `MeterReading` rows) — a `variance` property flags over/short amounts.
- `Manager` is a simple lookup table (name + active flag) — no password field, no `auth.User` link. Selected via dropdown.
- `FuelPrice` keeps full history — `MeterReading.price_snapshot` locks in whatever price was active at entry time, so Admin price changes never rewrite historical cash-due figures.