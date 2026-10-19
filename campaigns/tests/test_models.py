import uuid
from decimal import Decimal
import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from campaigns.models import Campaign, Platform, SpendingRecord, BudgetAlert, AlertStatus


@pytest.mark.django_db(transaction=True)
class TestModelDatabaseConstraints:
    def test_database_rejects_negative_or_zero_campaign_budget(self):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Campaign.objects.create(
                    name="Invalid Budget",
                    platform=Platform.META_ADS,
                    total_budget=Decimal("0.00"),
                )

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Campaign.objects.create(
                    name="Negative Budget",
                    platform=Platform.META_ADS,
                    total_budget=Decimal("-500.00"),
                )

    def test_database_rejects_negative_or_zero_spending_amount(self):
        campaign = Campaign.objects.create(
            name="Valid Campaign",
            platform=Platform.GOOGLE_ADS,
            total_budget=Decimal("1000.00"),
        )

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SpendingRecord.objects.create(
                    campaign=campaign,
                    amount=Decimal("0.00"),
                    idempotency_key=uuid.uuid4(),
                )

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SpendingRecord.objects.create(
                    campaign=campaign,
                    amount=Decimal("-10.00"),
                    idempotency_key=uuid.uuid4(),
                )

    def test_database_rejects_duplicate_idempotency_key(self):
        campaign = Campaign.objects.create(
            name="Valid Campaign",
            platform=Platform.GOOGLE_ADS,
            total_budget=Decimal("1000.00"),
        )
        shared_key = uuid.uuid4()

        SpendingRecord.objects.create(
            campaign=campaign,
            amount=Decimal("100.00"),
            idempotency_key=shared_key,
        )

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SpendingRecord.objects.create(
                    campaign=campaign,
                    amount=Decimal("100.00"),
                    idempotency_key=shared_key,
                )

    def test_database_rejects_duplicate_alert_for_same_period_and_threshold(self):
        campaign = Campaign.objects.create(
            name="Valid Campaign",
            platform=Platform.GOOGLE_ADS,
            total_budget=Decimal("1000.00"),
        )
        today = timezone.localdate()

        BudgetAlert.objects.create(
            campaign=campaign,
            threshold_percentage=Decimal("90.00"),
            spending_at_alert=Decimal("910.00"),
            budget_at_alert=Decimal("1000.00"),
            period_start=today,
            status=AlertStatus.TRIGGERED,
        )

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                BudgetAlert.objects.create(
                    campaign=campaign,
                    threshold_percentage=Decimal("90.00"),
                    spending_at_alert=Decimal("950.00"),
                    budget_at_alert=Decimal("1000.00"),
                    period_start=today,
                    status=AlertStatus.TRIGGERED,
                )
