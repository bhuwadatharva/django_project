# Campaign Budget Monitoring & Alert System

A production-conscious backend service built with **Python 3.14 / Django 6.1 / Django REST Framework** and **PostgreSQL 18** to monitor advertising campaign spending across platforms like Meta Ads and Google Ads, calculate budget utilization with fixed-point decimal precision, and generate deduplicated threshold alerts.

---

## 1. Business Problem & Project Overview

Digital marketing teams manage advertising budgets across platforms such as Meta Ads and Google Ads. Without proactive automated monitoring:
- Campaigns can silently overspend due to algorithmic bidding surges or unexpected traffic spikes.
- Repeated monitoring scripts can spam operations channels with duplicate alerts every time they run.
- Network retries from webhook ingestion can double-count spending records.

This application provides a backend system to:
1. Store campaigns, allocated budgets, and append-only spending records.
2. Ingest spending events with strict idempotency guarantees.
3. Dynamically compute budget utilization:
   $$\text{utilization\_percentage} = \left(\frac{\text{current\_period\_spending}}{\text{total\_budget}}\right) \times 100$$
4. Detect threshold crossings (configurable, defaulting to **90.00%** and **99.00%**), handling single-event multi-threshold jumps (e.g., jumping directly from 85% to 99.5%).
5. Enforce **single-alert deduplication** per threshold and budget period.
6. Provide decoupled notification dispatching via Django's email framework with audit logging and fault isolation.

> **Note on Simulated Data:** This service simulates ad platform interactions. It does not integrate real proprietary Meta or Google Marketing APIs directly in the initial version, allowing predictable local testing and clear domain modeling.

---

## 2. Architecture Diagram

```mermaid
flowchart TD
    subgraph Clients["Clients & Scheduled Jobs"]
        Client[API Clients / Ad Webhooks]
        Cron[Cron / Scheduler]
        Admin[Operations Admin]
    end

    subgraph API["Django REST Framework API"]
        CampAPI["/api/campaigns/"]
        SpendAPI["/api/campaigns/{id}/spending/"]
        AlertAPI["/api/alerts/"]
        TriggerAPI["/api/monitoring/run/"]
    end

    subgraph Services["Domain Services Layer"]
        SpendService["spending_service.ingest_spending()"]
        BudgetService["budget_service.evaluate_campaign_alerts()"]
        Runner["budget_service.run_budget_monitoring()"]
        NotifService["notification_service.send_alert_notification()"]
    end

    subgraph Command["Management Command"]
        MgmtCmd["python manage.py monitor_campaign_budgets"]
    end

    subgraph Storage["PostgreSQL 18 Database"]
        T_Campaign[("campaigns_campaign")]
        T_Spend[("campaigns_spendingrecord<br/>(Unique Idempotency Key)")]
        T_Alert[("campaigns_budgetalert<br/>(Unique: campaign + threshold + period)")]
    end

    subgraph Notification["Notification Layer"]
        EmailBackend[Django Email Backend<br/>(Console / SMTP)]
    end

    Client -->|Create / Read| CampAPI
    Client -->|Ingest Spend| SpendAPI
    Admin -->|Manual Trigger| TriggerAPI
    Cron -->|CLI Runner| MgmtCmd

    SpendAPI --> SpendService
    SpendService -->|Atomic Insert| T_Spend

    MgmtCmd --> Runner
    TriggerAPI --> Runner
    Runner --> BudgetService

    BudgetService -->|Row Lock select_for_update| T_Campaign
    BudgetService -->|Sum Spend| T_Spend
    BudgetService -->|Persist Alert| T_Alert
    BudgetService -->|Decoupled Dispatch| NotifService

    NotifService -->|Send Email| EmailBackend
    NotifService -->|Update status: SENT / FAILED| T_Alert
    AlertAPI -->|Audit Logs| T_Alert
```

---

## 3. Technology Stack

- **Language:** Python 3.14 (compatible with Python 3.12+)
- **Framework:** Django 6.1 (LTS compatible)
- **API Toolkit:** Django REST Framework 3.18
- **Database:** PostgreSQL 18 with `psycopg` (v3) binary driver
- **Configuration:** `django-environ` (12-Factor App pattern)
- **Testing:** `pytest` 9.1 with `pytest-django` 4.14
- **Email:** Django Core Email Framework (Console backend in development)

---

## 4. Installation & Local Setup

### Prerequisites
- Python 3.12+ (Python 3.14 tested)
- PostgreSQL 18 (or local PostgreSQL instance running on port 5432)
- Git

### 1. Clone & Set Up Virtual Environment
```bash
cd d:/Website/django_project
python -m venv .venv

# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# On Linux/macOS:
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and verify database credentials:
```ini
DEBUG=True
SECRET_KEY=django-insecure-dev-key-change-in-production
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://postgres:password@localhost:5432/campaign_monitoring_db
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=alerts@admonitoring.local
ALERT_THRESHOLDS=90.0,99.0
ALERT_RECIPIENT_EMAIL=ops@admonitoring.local
```

### 4. Create PostgreSQL Database & Run Migrations
```bash
# If using psql:
psql -U postgres -h localhost -c "CREATE DATABASE campaign_monitoring_db;"

# Apply Django migrations:
python manage.py migrate
```

### 5. Create Superuser (Optional for Admin Access)
```bash
python manage.py createsuperuser
```

### 6. Start Development Server
```bash
python manage.py runserver 127.0.0.1:8000
```

---

## 5. REST API Documentation & Sample Payloads

### 5.1 Create Campaign
- **Endpoint:** `POST /api/campaigns/`
- **Request Body:**
  ```json
  {
      "name": "Q4 Holiday Retargeting",
      "platform": "META_ADS",
      "external_campaign_id": "act_882910_c1",
      "total_budget": "5000.00",
      "is_active": true
  }
  ```
- **Response (201 Created):**
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

### 5.2 Retrieve Campaign (With Real-Time Metrics)
- **Endpoint:** `GET /api/campaigns/1/`
- **Response (200 OK):**
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

### 5.3 Ingest Spending Event (Idempotent)
- **Endpoint:** `POST /api/campaigns/1/spending/`
- **Request Body:**
  ```json
  {
      "amount": "4525.00",
      "source_reference": "meta_invoice_991823",
      "idempotency_key": "c4b92b6a-6a75-4fc1-91a5-8123fa46b3f9"
  }
  ```
- **Response (201 Created on first call, 200 OK on identical retry):**
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

### 5.4 List Campaign Alerts
- **Endpoint:** `GET /api/campaigns/1/alerts/`
- **Response (200 OK):**
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

### 5.5 Trigger Admin Monitoring Run
- **Endpoint:** `POST /api/monitoring/run/`
- **Headers:** `Authorization: Basic <admin_credentials>`
- **Response (200 OK):**
  ```json
  {
      "status": "completed",
      "total_campaigns_evaluated": 12,
      "total_alerts_created": 2,
      "created_alert_ids": [15, 16],
      "failed_campaign_ids": []
  }
  ```

---

## 6. How the Monitoring Algorithm & Deduplication Works

1. **Active Campaigns Filter:**
   Only campaigns with `is_active=True` are evaluated. Inactive campaigns are skipped.
2. **Current Period Scoping:**
   Calculates total spend where `recorded_at >= campaign.current_period_start`.
3. **Ascending Threshold Evaluation:**
   Evaluates configured thresholds (`[90.00, 99.00]`).
4. **Multi-Threshold Crossing Support:**
   If a single spending record pushes utilization from `80%` directly to `99.5%`, the algorithm generates the `90.00%` alert **and** the `99.00%` alert in chronological order.
5. **Deduplication:**
   A database `UniqueConstraint(['campaign', 'threshold_percentage', 'period_start'])` guarantees at the database engine level that no duplicate alert can ever be committed for the same campaign, threshold, and budget cycle.
6. **Decoupled Delivery:**
   The `BudgetAlert` is committed with status `TRIGGERED`. Notification dispatch runs in a decoupled block. If the email succeeds, status is updated to `SENT`. If it fails, status is marked `FAILED` with detailed error logs, and the alert remains safely stored in PostgreSQL.

---

## 7. Scheduled Monitoring (CLI Management Command)

Run the monitoring job via command line:
```bash
python manage.py monitor_campaign_budgets
```

### CLI Options
- Monitor specific campaigns:
  ```bash
  python manage.py monitor_campaign_budgets --campaign-ids="1,2,5"
  ```
- Override thresholds on demand:
  ```bash
  python manage.py monitor_campaign_budgets --thresholds="80.0,90.0,95.0,99.0"
  ```

### Scheduling with Cron (Linux) or Task Scheduler (Windows)
- **Linux Crontab (every 5 minutes):**
  ```cron
  */5 * * * * /path/to/.venv/bin/python /path/to/manage.py monitor_campaign_budgets >> /var/log/budget_monitor.log 2>&1
  ```
- **Windows Task Scheduler:**
  Create a scheduled task pointing to `.\.venv\Scripts\python.exe` with arguments `manage.py monitor_campaign_budgets`.

---

## 8. Running Automated Tests

Run the complete test suite with `pytest`:
```bash
pytest
```

Output:
```
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.7.0
rootdir: D:\Website\django_project
configfile: pytest.ini
collected 31 items

campaigns/tests/test_api.py::TestCampaignAPI::test_create_campaign_success PASSED
campaigns/tests/test_api.py::TestCampaignAPI::test_create_campaign_rejects_zero_or_negative_budget PASSED
campaigns/tests/test_api.py::TestCampaignAPI::test_get_campaign_detail_shows_utilization PASSED
campaigns/tests/test_api.py::TestSpendingIngestionAPI::test_record_spending_success PASSED
campaigns/tests/test_api.py::TestSpendingIngestionAPI::test_idempotent_retry_returns_existing_record_without_duplicate PASSED
campaigns/tests/test_api.py::TestSpendingIngestionAPI::test_idempotent_key_conflict_returns_409 PASSED
campaigns/tests/test_api.py::TestSpendingIngestionAPI::test_reject_negative_or_zero_spending PASSED
campaigns/tests/test_api.py::TestCampaignUpdatesAndAlertAPIs::test_patch_campaign_updates_budget_and_active_status PASSED
campaigns/tests/test_api.py::TestCampaignUpdatesAndAlertAPIs::test_list_campaign_alerts_endpoint PASSED
campaigns/tests/test_api.py::TestCampaignUpdatesAndAlertAPIs::test_global_alert_list_endpoint_and_filtering PASSED
campaigns/tests/test_api.py::TestCampaignUpdatesAndAlertAPIs::test_trigger_monitoring_endpoint_permissions PASSED
campaigns/tests/test_commands.py::TestMonitorCampaignBudgetsCommand::test_command_executes_and_generates_alerts PASSED
campaigns/tests/test_commands.py::TestMonitorCampaignBudgetsCommand::test_command_with_specific_campaign_ids PASSED
campaigns/tests/test_commands.py::TestMonitorCampaignBudgetsCommand::test_command_with_invalid_arguments_raises_error PASSED
campaigns/tests/test_notifications.py::TestNotificationService::test_send_alert_notification_success PASSED
campaigns/tests/test_notifications.py::TestNotificationService::test_email_failure_marks_alert_as_failed_without_losing_alert PASSED
campaigns/tests/test_notifications.py::TestNotificationService::test_dispatch_pending_alerts PASSED
campaigns/tests/test_services.py::TestBudgetCalculation::test_calculate_utilization_percentage_accuracy PASSED
campaigns/tests/test_services.py::TestBudgetCalculation::test_calculate_utilization_rejects_zero_or_negative_budget PASSED
campaigns/tests/test_services.py::TestBudgetCalculation::test_calculate_utilization_rejects_negative_spending PASSED
campaigns/tests/test_services.py::TestAlertEvaluationLogic::test_spending_below_threshold_generates_no_alerts PASSED
campaigns/tests/test_services.py::TestAlertEvaluationLogic::test_exact_90_percent_threshold_boundary PASSED
campaigns/tests/test_services.py::TestAlertEvaluationLogic::test_exact_99_percent_threshold_boundary_after_90 PASSED
campaigns/tests/test_services.py::TestAlertEvaluationLogic::test_single_spending_event_crossing_both_thresholds PASSED
campaigns/tests/test_services.py::TestAlertEvaluationLogic::test_repeated_evaluations_do_not_duplicate_alerts PASSED
campaigns/tests/test_services.py::TestAlertEvaluationLogic::test_inactive_campaigns_do_not_generate_alerts PASSED
campaigns/tests/test_services.py::TestAlertEvaluationLogic::test_new_period_allows_new_alerts PASSED
campaigns/tests/test_models.py::TestModelDatabaseConstraints::test_database_rejects_negative_or_zero_campaign_budget PASSED
campaigns/tests/test_models.py::TestModelDatabaseConstraints::test_database_rejects_negative_or_zero_spending_amount PASSED
campaigns/tests/test_models.py::TestModelDatabaseConstraints::test_database_rejects_duplicate_idempotency_key PASSED
campaigns/tests/test_models.py::TestModelDatabaseConstraints::test_database_rejects_duplicate_alert_for_same_period_and_threshold PASSED

======================== 31 passed, 1 warning in 2.43s ========================
```

---

## 9. Current Limitations & Roadmap

1. **Simulated Ad Networks:** Direct synchronization adapters for Meta Graph API / Google Ads REST API are omitted in favor of clean internal ingestion models.
2. **Synchronous Monitoring Runner:** The management command is synchronous. For installations exceeding 10,000 campaigns, introducing Celery workers with a Redis broker will parallelize campaign evaluation.
3. **Notification Channels:** Currently supports email via Django's email framework. Slack webhooks and PagerDuty integrations can be added as additional notification providers.
