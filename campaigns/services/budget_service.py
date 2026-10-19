import datetime as dt
import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from campaigns.models import Campaign, BudgetAlert, AlertStatus

logger = logging.getLogger('campaigns')


class BudgetCalculationError(Exception):
    pass


class InvalidBudgetError(BudgetCalculationError):
    pass


@dataclass
class MonitoringRunSummary:
    total_campaigns_evaluated: int = 0
    total_alerts_created: int = 0
    created_alert_ids: list = field(default_factory=list)
    failed_campaign_ids: list = field(default_factory=list)

    @property
    def has_failures(self):
        return len(self.failed_campaign_ids) > 0


def get_period_start_datetime(period_start):
    midnight = dt.datetime.combine(period_start, dt.time.min)
    if timezone.is_aware(midnight):
        return midnight
    return timezone.make_aware(midnight)


def calculate_campaign_spending(campaign):
    start_dt = get_period_start_datetime(campaign.current_period_start)
    result = campaign.spending_records.filter(
        recorded_at__gte=start_dt
    ).aggregate(total=Sum('amount'))['total']

    spending = result if result is not None else Decimal('0.00')
    return spending.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def calculate_utilization_percentage(total_spending, total_budget):
    if total_budget <= Decimal('0.00'):
        raise InvalidBudgetError(f"Total budget must be strictly positive, got: {total_budget}")

    if total_spending < Decimal('0.00'):
        raise BudgetCalculationError(f"Total spending cannot be negative, got: {total_spending}")

    if total_spending == Decimal('0.00'):
        return Decimal('0.00')

    utilization = (total_spending / total_budget) * Decimal('100.0')
    return utilization.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def evaluate_campaign_alerts(campaign, thresholds=None):
    if not campaign.is_active:
        return []

    if thresholds is None:
        thresholds = getattr(settings, 'ALERT_THRESHOLDS', [Decimal('90.00'), Decimal('99.00')])

    sorted_thresholds = sorted(thresholds)

    with transaction.atomic():
        locked_campaign = Campaign.objects.select_for_update().get(id=campaign.id)

        if not locked_campaign.is_active:
            return []

        current_spending = calculate_campaign_spending(locked_campaign)
        utilization = calculate_utilization_percentage(
            total_spending=current_spending,
            total_budget=locked_campaign.total_budget,
        )

        existing_thresholds = set(
            BudgetAlert.objects.filter(
                campaign=locked_campaign,
                period_start=locked_campaign.current_period_start,
            ).values_list('threshold_percentage', flat=True)
        )

        newly_created_alerts = []

        for threshold in sorted_thresholds:
            if utilization >= threshold and threshold not in existing_thresholds:
                try:
                    alert = BudgetAlert.objects.create(
                        campaign=locked_campaign,
                        threshold_percentage=threshold,
                        spending_at_alert=current_spending,
                        budget_at_alert=locked_campaign.total_budget,
                        period_start=locked_campaign.current_period_start,
                        status=AlertStatus.TRIGGERED,
                    )
                    newly_created_alerts.append(alert)
                    existing_thresholds.add(threshold)
                    logger.warning(
                        "Budget alert triggered for campaign %s at %s%%",
                        locked_campaign.id,
                        threshold,
                    )
                except IntegrityError:
                    pass

        return newly_created_alerts


def run_budget_monitoring(campaign_ids=None, thresholds=None):
    queryset = Campaign.objects.filter(is_active=True).order_by('id')
    if campaign_ids:
        queryset = queryset.filter(id__in=campaign_ids)

    summary = MonitoringRunSummary()

    for campaign in queryset:
        summary.total_campaigns_evaluated += 1
        try:
            alerts = evaluate_campaign_alerts(campaign, thresholds=thresholds)
            if alerts:
                summary.total_alerts_created += len(alerts)
                summary.created_alert_ids.extend([a.id for a in alerts])

                from campaigns.services.notification_service import send_alert_notification
                for alert in alerts:
                    try:
                        send_alert_notification(alert)
                    except Exception:
                        pass
        except Exception:
            summary.failed_campaign_ids.append(campaign.id)

    return summary
