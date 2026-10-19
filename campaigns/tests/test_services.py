import datetime as dt
import uuid
from decimal import Decimal
import pytest
from django.utils import timezone

from campaigns.models import Campaign, Platform, SpendingRecord, BudgetAlert, AlertStatus
from campaigns.services.budget_service import (
    calculate_campaign_spending,
    calculate_utilization_percentage,
    evaluate_campaign_alerts,
    run_budget_monitoring,
    InvalidBudgetError,
    BudgetCalculationError,
)


@pytest.fixture
def base_campaign(db):
    return Campaign.objects.create(
        name="Q4 Growth Campaign",
        platform=Platform.META_ADS,
        total_budget=Decimal("1000.00"),
        current_period_start=timezone.localdate(),
        is_active=True,
    )


@pytest.mark.django_db
class TestBudgetCalculation:
    def test_calculate_utilization_percentage_accuracy(self):
        res = calculate_utilization_percentage(Decimal("450.00"), Decimal("1000.00"))
        assert res == Decimal("45.00")

        res_zero = calculate_utilization_percentage(Decimal("0.00"), Decimal("1000.00"))
        assert res_zero == Decimal("0.00")

    def test_calculate_utilization_rejects_zero_or_negative_budget(self):
        with pytest.raises(InvalidBudgetError):
            calculate_utilization_percentage(Decimal("100.00"), Decimal("0.00"))

        with pytest.raises(InvalidBudgetError):
            calculate_utilization_percentage(Decimal("100.00"), Decimal("-500.00"))

    def test_calculate_utilization_rejects_negative_spending(self):
        with pytest.raises(BudgetCalculationError):
            calculate_utilization_percentage(Decimal("-50.00"), Decimal("1000.00"))


@pytest.mark.django_db
class TestAlertEvaluationLogic:
    def test_spending_below_threshold_generates_no_alerts(self, base_campaign):
        SpendingRecord.objects.create(
            campaign=base_campaign,
            amount=Decimal("899.90"),
            idempotency_key=uuid.uuid4(),
        )

        alerts = evaluate_campaign_alerts(base_campaign)
        assert len(alerts) == 0
        assert BudgetAlert.objects.filter(campaign=base_campaign).count() == 0

    def test_exact_90_percent_threshold_boundary(self, base_campaign):
        SpendingRecord.objects.create(
            campaign=base_campaign,
            amount=Decimal("900.00"),
            idempotency_key=uuid.uuid4(),
        )

        alerts = evaluate_campaign_alerts(base_campaign)
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.threshold_percentage == Decimal("90.00")
        assert alert.spending_at_alert == Decimal("900.00")
        assert alert.budget_at_alert == Decimal("1000.00")
        assert alert.status == AlertStatus.TRIGGERED

    def test_exact_99_percent_threshold_boundary_after_90(self, base_campaign):
        SpendingRecord.objects.create(
            campaign=base_campaign,
            amount=Decimal("900.00"),
            idempotency_key=uuid.uuid4(),
        )
        alerts_90 = evaluate_campaign_alerts(base_campaign)
        assert len(alerts_90) == 1

        SpendingRecord.objects.create(
            campaign=base_campaign,
            amount=Decimal("90.00"),
            idempotency_key=uuid.uuid4(),
        )
        alerts_99 = evaluate_campaign_alerts(base_campaign)
        assert len(alerts_99) == 1
        assert alerts_99[0].threshold_percentage == Decimal("99.00")
        assert BudgetAlert.objects.filter(campaign=base_campaign).count() == 2

    def test_single_spending_event_crossing_both_thresholds(self, base_campaign):
        SpendingRecord.objects.create(
            campaign=base_campaign,
            amount=Decimal("995.00"),
            idempotency_key=uuid.uuid4(),
        )

        alerts = evaluate_campaign_alerts(base_campaign)
        assert len(alerts) == 2
        assert alerts[0].threshold_percentage == Decimal("90.00")
        assert alerts[1].threshold_percentage == Decimal("99.00")
        assert BudgetAlert.objects.filter(campaign=base_campaign).count() == 2

    def test_repeated_evaluations_do_not_duplicate_alerts(self, base_campaign):
        SpendingRecord.objects.create(
            campaign=base_campaign,
            amount=Decimal("950.00"),
            idempotency_key=uuid.uuid4(),
        )

        alerts_run1 = evaluate_campaign_alerts(base_campaign)
        assert len(alerts_run1) == 1

        alerts_run2 = evaluate_campaign_alerts(base_campaign)
        assert len(alerts_run2) == 0

        summary = run_budget_monitoring(campaign_ids=[base_campaign.id])
        assert summary.total_alerts_created == 0
        assert BudgetAlert.objects.filter(campaign=base_campaign).count() == 1

    def test_inactive_campaigns_do_not_generate_alerts(self, base_campaign):
        base_campaign.is_active = False
        base_campaign.save()

        SpendingRecord.objects.create(
            campaign=base_campaign,
            amount=Decimal("995.00"),
            idempotency_key=uuid.uuid4(),
        )

        alerts = evaluate_campaign_alerts(base_campaign)
        assert len(alerts) == 0
        assert BudgetAlert.objects.filter(campaign=base_campaign).count() == 0

    def test_new_period_allows_new_alerts(self, base_campaign):
        SpendingRecord.objects.create(
            campaign=base_campaign,
            amount=Decimal("920.00"),
            idempotency_key=uuid.uuid4(),
        )
        alerts_period1 = evaluate_campaign_alerts(base_campaign)
        assert len(alerts_period1) == 1

        tomorrow = base_campaign.current_period_start + dt.timedelta(days=30)
        base_campaign.current_period_start = tomorrow
        base_campaign.save()

        assert calculate_campaign_spending(base_campaign) == Decimal("0.00")

        SpendingRecord.objects.create(
            campaign=base_campaign,
            amount=Decimal("950.00"),
            idempotency_key=uuid.uuid4(),
            recorded_at=timezone.make_aware(dt.datetime.combine(tomorrow, dt.time(10, 0))),
        )

        alerts_period2 = evaluate_campaign_alerts(base_campaign)
        assert len(alerts_period2) == 1
        assert alerts_period2[0].period_start == tomorrow
        assert BudgetAlert.objects.filter(campaign=base_campaign).count() == 2
