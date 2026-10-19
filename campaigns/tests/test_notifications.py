from decimal import Decimal
from unittest.mock import patch
import pytest
from django.core import mail
from django.utils import timezone

from campaigns.models import Campaign, Platform, BudgetAlert, AlertStatus
from campaigns.services.notification_service import (
    send_alert_notification,
    dispatch_pending_alerts,
)


@pytest.fixture
def sample_alert(db):
    campaign = Campaign.objects.create(
        name="Retargeting Ads",
        platform=Platform.META_ADS,
        total_budget=Decimal("2000.00"),
        is_active=True,
    )
    return BudgetAlert.objects.create(
        campaign=campaign,
        threshold_percentage=Decimal("90.00"),
        spending_at_alert=Decimal("1805.00"),
        budget_at_alert=Decimal("2000.00"),
        period_start=timezone.localdate(),
        status=AlertStatus.TRIGGERED,
    )


@pytest.mark.django_db
class TestNotificationService:
    def test_send_alert_notification_success(self, sample_alert):
        success = send_alert_notification(sample_alert, recipient_email="alerts-test@example.com")
        assert success is True

        sample_alert.refresh_from_db()
        assert sample_alert.status == AlertStatus.SENT

        assert len(mail.outbox) == 1
        sent_email = mail.outbox[0]
        assert "90.0" in sent_email.subject
        assert "Retargeting Ads" in sent_email.subject
        assert "1805.00" in sent_email.body
        assert sent_email.to == ["alerts-test@example.com"]

    def test_email_failure_marks_alert_as_failed_without_losing_alert(self, sample_alert):
        alert_id = sample_alert.id

        with patch("campaigns.services.notification_service.send_mail", side_effect=ConnectionError("SMTP server unreachable")):
            success = send_alert_notification(sample_alert)

        assert success is False

        persisted_alert = BudgetAlert.objects.get(id=alert_id)
        assert persisted_alert is not None
        assert persisted_alert.status == AlertStatus.FAILED
        assert persisted_alert.spending_at_alert == Decimal("1805.00")

    def test_dispatch_pending_alerts(self, sample_alert):
        sent, failed = dispatch_pending_alerts([sample_alert])
        assert sent == 1
        assert failed == 0
        sample_alert.refresh_from_db()
        assert sample_alert.status == AlertStatus.SENT
