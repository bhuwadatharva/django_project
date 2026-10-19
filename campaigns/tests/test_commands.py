from decimal import Decimal
import io
import uuid
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from campaigns.models import Campaign, Platform, SpendingRecord, BudgetAlert


@pytest.fixture
def test_campaigns(db):
    c1 = Campaign.objects.create(
        name="Campaign Alpha",
        platform=Platform.GOOGLE_ADS,
        total_budget=Decimal("1000.00"),
        is_active=True,
    )
    c2 = Campaign.objects.create(
        name="Campaign Beta (Inactive)",
        platform=Platform.META_ADS,
        total_budget=Decimal("500.00"),
        is_active=False,
    )
    return c1, c2


@pytest.mark.django_db
class TestMonitorCampaignBudgetsCommand:
    def test_command_executes_and_generates_alerts(self, test_campaigns):
        c1, c2 = test_campaigns

        SpendingRecord.objects.create(
            campaign=c1,
            amount=Decimal("910.00"),
            idempotency_key=uuid.uuid4(),
        )

        SpendingRecord.objects.create(
            campaign=c2,
            amount=Decimal("490.00"),
            idempotency_key=uuid.uuid4(),
        )

        out = io.StringIO()
        call_command('monitor_campaign_budgets', stdout=out)

        output = out.getvalue()
        assert "Completed monitoring: 1 campaign(s) evaluated, 1 alert(s) generated." in output
        assert BudgetAlert.objects.filter(campaign=c1).count() == 1
        assert BudgetAlert.objects.filter(campaign=c2).count() == 0

    def test_command_with_specific_campaign_ids(self, test_campaigns):
        c1, _ = test_campaigns
        out = io.StringIO()
        call_command('monitor_campaign_budgets', campaign_ids=str(c1.id), stdout=out)
        assert "1 campaign(s) evaluated" in out.getvalue()

    def test_command_with_invalid_arguments_raises_error(self):
        with pytest.raises(CommandError):
            call_command('monitor_campaign_budgets', campaign_ids="invalid,abc")

        with pytest.raises(CommandError):
            call_command('monitor_campaign_budgets', thresholds="abc,xyz")
