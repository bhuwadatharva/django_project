import logging
from django.conf import settings
from django.core.mail import send_mail

from campaigns.models import BudgetAlert, AlertStatus

logger = logging.getLogger('campaigns')


class NotificationDeliveryError(Exception):
    pass


def send_alert_notification(alert, recipient_email=None, fail_silently=False):
    recipient = recipient_email or getattr(settings, 'ALERT_RECIPIENT_EMAIL', 'ops@admonitoring.local')
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'alerts@admonitoring.local')

    subject = f"[BUDGET ALERT] Campaign '{alert.campaign.name}' reached {alert.threshold_percentage}% utilization"

    body = (
        f"Campaign: {alert.campaign.name}\n"
        f"Platform: {alert.campaign.get_platform_display()}\n"
        f"Period Start: {alert.period_start}\n\n"
        f"Threshold Reached: {alert.threshold_percentage}%\n"
        f"Current Spending: {alert.spending_at_alert}\n"
        f"Total Budget: {alert.budget_at_alert}\n"
        f"Alert Triggered At: {alert.created_at}\n"
    )

    try:
        sent = send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=False,
        )

        if sent:
            alert.status = AlertStatus.SENT
            alert.save(update_fields=['status'])
            return True
        else:
            alert.status = AlertStatus.FAILED
            alert.save(update_fields=['status'])
            return False

    except Exception:
        alert.status = AlertStatus.FAILED
        alert.save(update_fields=['status'])
        if not fail_silently:
            pass
        return False


def dispatch_pending_alerts(alerts=None):
    if alerts is None:
        target_alerts = list(BudgetAlert.objects.filter(status=AlertStatus.TRIGGERED).order_by('id'))
    else:
        target_alerts = alerts

    success_count = 0
    failure_count = 0

    for alert in target_alerts:
        if send_alert_notification(alert):
            success_count += 1
        else:
            failure_count += 1

    return success_count, failure_count
