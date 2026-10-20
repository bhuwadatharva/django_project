# Campaign Budget Monitoring & Alert System

A backend service built with **Python, Django REST Framework, and PostgreSQL** to monitor advertising campaign spending, calculate budget utilization with decimal precision, and generate deduplicated threshold alerts.

> **Scope:** This version simulates ad-platform spending ingestion. It does not directly synchronize with the Meta Marketing API or Google Ads API.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Monitoring Algorithm](#monitoring-algorithm)
- [Scheduled Monitoring](#scheduled-monitoring)
- [Running Tests](#running-tests)
- [Limitations and Roadmap](#limitations-and-roadmap)

## Overview

Advertising teams need to know when campaign spending approaches its allocated budget. Without automated monitoring, campaigns may overspend, repeated jobs may send duplicate alerts, and retried ingestion requests may record the same spending more than once.

This service provides an API and scheduled monitoring process to track campaign budgets and alert operations teams when spending crosses configured thresholds.

### Key Features

- Create, retrieve, and update campaigns.
- Record spending events with idempotency protection.
- Calculate current-period spending and budget utilization.
- Detect configurable threshold crossings (defaults: **90%** and **99%**).
- Detect multiple thresholds crossed by a single spending event.
- Deduplicate alerts by campaign, threshold, and budget period.
- Send alert notifications through Django's email framework.
- Keep alert records and delivery statuses for auditing.
- Trigger monitoring through an API endpoint or management command.

## Architecture

```mermaid
flowchart TD
    subgraph Clients["Clients and Scheduled Jobs"]
        Client["API clients / simulated ad webhooks"]
        Scheduler["Cron / Task Scheduler"]
        Admin["Operations admin"]
    end

    subgraph API["Django REST Framework API"]
        CampaignAPI["/api/campaigns/"]
        SpendingAPI["/api/campaigns/{id}/spending/"]
        AlertsAPI["/api/alerts/"]
        MonitoringAPI["/api/monitoring/run/"]
    end

    subgraph Services["Domain Services"]
        SpendingService["spending_service.ingest_spending()"]
        BudgetService["budget_service.evaluate_campaign_alerts()"]
        MonitoringRunner["budget_service.run_budget_monitoring()"]
        NotificationService["notification_service.send_alert_notification()"]
    end

    subgraph Command["Management Command"]
        ManagementCommand["manage.py monitor_campaign_budgets"]
    end

    subgraph Database["PostgreSQL"]
        CampaignTable[("Campaigns")]
        SpendingTable[("Spending records")]
        AlertTable[("Budget alerts")]
    end

    subgraph Email["Notification Layer"]
        EmailBackend["Django email backend (console or SMTP)"]
    end

    Client --> CampaignAPI
    Client --> SpendingAPI
    Admin --> MonitoringAPI
    Scheduler --> ManagementCommand

    SpendingAPI --> SpendingService
    SpendingService --> SpendingTable

    ManagementCommand --> MonitoringRunner
    MonitoringAPI --> MonitoringRunner
    MonitoringRunner --> BudgetService

    BudgetService --> CampaignTable
    BudgetService --> SpendingTable
    BudgetService --> AlertTable
    BudgetService --> NotificationService

    NotificationService --> EmailBackend
    NotificationService --> AlertTable
    AlertsAPI --> AlertTable
```

### Monitoring flow

1. A client creates a campaign and records spending events.
2. The monitoring runner selects active campaigns and totals spending for each campaign's current budget period.
3. The service calculates utilization and checks configured thresholds in ascending order.
4. An alert is created only if an alert for that campaign, threshold, and period does not already exist.
5. The notification service attempts delivery and records the resulting alert status.

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ (Python 3.14 tested in the supplied test output) |
| Web framework | Django 6.1 |
| API | Django REST Framework 3.18 |
| Database | PostgreSQL 18 |
| PostgreSQL driver | `psycopg` v3 |
| Configuration | `django-environ` |
| Testing | `pytest`, `pytest-django` |
| Notifications | Django email framework |

Use versions compatible with your project's `requirements.txt` and installed environment.

## Prerequisites

- Python 3.12 or newer
- PostgreSQL running locally or on a reachable database server
- Git
- The project source code, including `manage.py` and `requirements.txt`

## Local Setup

### 1. Open the project directory

Run these commands from the directory containing `manage.py`:

```bash
cd path/to/your/project
```

### 2. Create and activate a virtual environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux or macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

If the project includes `.env.example`, copy it to `.env` and update the values. Otherwise, create a `.env` file in the location expected by the Django settings.

Example development configuration:

```dotenv
DEBUG=True
SECRET_KEY=replace-with-a-local-development-secret
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://postgres:password@localhost:5432/campaign_monitoring_db
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=alerts@admonitoring.local
ALERT_THRESHOLDS=90.0,99.0
ALERT_RECIPIENT_EMAIL=ops@admonitoring.local
```

**Important:** These are example values. Use your own database credentials and secret key. Do not commit `.env` or production secrets to version control. Keep `DEBUG=False` in production.

### 5. Create the database

For a local PostgreSQL instance, you can create the database with `psql`:

```bash
psql -U postgres -h localhost -c "CREATE DATABASE campaign_monitoring_db;"
```

If the database already exists, skip this command.

### 6. Apply migrations

```bash
python manage.py migrate
```

### 7. Create an admin account (optional)

```bash
python manage.py createsuperuser
```

### 8. Start the development server

```bash
python manage.py runserver 127.0.0.1:8000
```

The API should now be available at `http://127.0.0.1:8000/`, assuming the configured URL routes use the endpoints documented below.

## Environment Variables

| Variable | Purpose | Example |
|---|---|---|
| `DEBUG` | Enables Django debug mode | `True` for local development |
| `SECRET_KEY` | Django secret key | Set a private value |
| `ALLOWED_HOSTS` | Allowed host names | `localhost,127.0.0.1` |
| `DATABASE_URL` | PostgreSQL connection URL | `postgres://user:password@localhost:5432/campaign_monitoring_db` |
| `EMAIL_BACKEND` | Email backend class | `django.core.mail.backends.console.EmailBackend` |
| `DEFAULT_FROM_EMAIL` | Sender address for alerts | `alerts@admonitoring.local` |
| `ALERT_THRESHOLDS` | Comma-separated utilization thresholds | `90.0,99.0` |
| `ALERT_RECIPIENT_EMAIL` | Alert recipient | `ops@admonitoring.local` |

Confirm variable names against the project's settings before deploying; the table reflects the configuration described for this project.

## API Reference

The examples below assume the API routes are mounted at the paths shown. Replace example IDs with IDs returned by your API.

### 1. Create a campaign

**Request**

```http
POST /api/campaigns/
Content-Type: application/json
```

```json
{
  "name": "Q4 Holiday Retargeting",
  "platform": "META_ADS",
  "external_campaign_id": "act_882910_c1",
  "total_budget": "5000.00",
  "is_active": true
}
```

**Example response — `201 Created`**

```json
{
  "id": 1,
  "name": "Q4 Holiday Retargeting",
  "platform": "META_ADS",
  "external_campaign_id": "act_882910_c1",
  "total_budget": "5000.00",
  "current_period_start": "2026-10-19",
  "is_active": true,
  "current_period_spending": "0.00",
  "utilization_percentage": "0.00",
  "created_at": "2026-10-19T13:40:00Z",
  "updated_at": "2026-10-19T13:40:00Z"
}
```

### 2. Retrieve a campaign and its current metrics

**Request:** `GET /api/campaigns/1/`

**Example response — `200 OK`**

```json
{
  "id": 1,
  "name": "Q4 Holiday Retargeting",
  "platform": "META_ADS",
  "external_campaign_id": "act_882910_c1",
  "total_budget": "5000.00",
  "current_period_start": "2026-10-19",
  "is_active": true,
  "current_period_spending": "4525.00",
  "utilization_percentage": "90.50",
  "created_at": "2026-10-19T13:40:00Z",
  "updated_at": "2026-10-19T13:40:00Z"
}
```

### 3. Record a spending event

The endpoint uses an idempotency key to protect against duplicate submissions.

**Request**

```http
POST /api/campaigns/1/spending/
Content-Type: application/json
```

```json
{
  "amount": "4525.00",
  "source_reference": "meta_invoice_991823",
  "idempotency_key": "c4b92b6a-6a75-4fc1-91a5-8123fa46b3f9"
}
```

**Expected behavior**

- First submission: `201 Created`.
- Identical retry: `200 OK` and the existing record is returned.
- Reuse of the same key with conflicting data: `409 Conflict` (as described by the project's tests).

**Example response**

```json
{
  "id": 1,
  "campaign": 1,
  "amount": "4525.00",
  "source_reference": "meta_invoice_991823",
  "idempotency_key": "c4b92b6a-6a75-4fc1-91a5-8123fa46b3f9",
  "recorded_at": "2026-10-19T13:42:15Z"
}
```

### 4. List alerts for a campaign

**Request:** `GET /api/campaigns/1/alerts/`

**Example response — `200 OK`**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "campaign": 1,
      "threshold_percentage": "90.00",
      "spending_at_alert": "4525.00",
      "budget_at_alert": "5000.00",
      "period_start": "2026-10-19",
      "status": "SENT",
      "created_at": "2026-10-19T13:45:00Z"
    }
  ]
}
```

### 5. Trigger a monitoring run

**Request:** `POST /api/monitoring/run/`

The endpoint is described as requiring HTTP Basic authentication.

```http
Authorization: Basic <admin_credentials>
```

**Example response — `200 OK`**

```json
{
  "status": "completed",
  "total_campaigns_evaluated": 12,
  "total_alerts_created": 2,
  "created_alert_ids": [15, 16],
  "failed_campaign_ids": []
}
```

### 6. Global alert list

The project also describes `GET /api/alerts/` for listing alert audit records and filtering them. Check the API view or router configuration for the exact supported query parameters.

## Monitoring Algorithm

### Budget utilization

The service calculates utilization from current-period spending and the campaign's total budget:

```text
utilization_percentage = (current_period_spending / total_budget) * 100
```

Decimal arithmetic is used for monetary values to avoid common floating-point precision errors.

### Threshold detection

1. Only campaigns with `is_active=True` are evaluated.
2. Spending is scoped to records where `recorded_at >= campaign.current_period_start`.
3. Configured thresholds are checked in ascending order. The defaults are `90.00` and `99.00`.
4. If utilization moves directly from 80% to 99.5%, both the 90% and 99% alerts should be generated.
5. A database uniqueness constraint on campaign, threshold, and period prevents duplicate alerts for the same budget cycle.
6. The alert is stored before notification delivery. Successful delivery changes the status to `SENT`; a delivery failure changes it to `FAILED` while retaining the alert record.

### Idempotency and concurrency

- Spending records use a unique idempotency key so a retried request does not create another record.
- Alert uniqueness is enforced at the database level using the combination of campaign, threshold percentage, and period start.
- The described monitoring service uses `select_for_update` to lock campaign rows while evaluating alerts.

## Scheduled Monitoring

Run the monitoring management command manually:

```bash
python manage.py monitor_campaign_budgets
```

### Optional command arguments

Monitor selected campaigns:

```bash
python manage.py monitor_campaign_budgets --campaign-ids="1,2,5"
```

Override the configured thresholds for a run:

```bash
python manage.py monitor_campaign_budgets --thresholds="80.0,90.0,95.0,99.0"
```

### Schedule on Linux with cron

Example: run every five minutes. Replace the paths with the absolute paths for your environment.

```cron
*/5 * * * * /path/to/.venv/bin/python /path/to/manage.py monitor_campaign_budgets >> /path/to/budget_monitor.log 2>&1
```

### Schedule on Windows

Use Windows Task Scheduler to run the virtual environment's Python executable with the following arguments:

```text
manage.py monitor_campaign_budgets
```

Set the task's **Start in** directory to the project directory containing `manage.py`.

## Running Tests

Run the project's test suite from the project root:

```bash
pytest
```

The supplied test output reports **31 passed, 1 warning**. The tests cover API behavior, command execution, notification handling, budget calculations, threshold boundaries, deduplication, and database constraints.

Example test output summary:

```text
======================== 31 passed, 1 warning in 2.43s ========================
```

## Limitations and Roadmap

1. **Simulated ad platforms:** Direct synchronization adapters for Meta Marketing API and Google Ads API are not included in this version.
2. **Synchronous monitoring:** The management command runs synchronously. For larger workloads, consider a task queue such as Celery with Redis after measuring performance and transaction behavior.
3. **Email-only notifications:** The current notification layer uses Django's email framework. Slack or PagerDuty integrations could be added as separate notification providers.
4. **Deployment configuration:** Production deployment requires secure secrets, production email settings, database configuration, logging, and appropriate host/debug settings.

## Contributing

1. Create a branch for your change.
2. Keep business logic in the service layer where practical.
3. Add or update tests for changed behavior.
4. Run `pytest` before opening a pull request.

## License

No license information was provided in the original README. Add a `LICENSE` file and update this section if you intend to distribute the project.
