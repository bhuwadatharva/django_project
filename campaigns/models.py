import uuid
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Platform(models.TextChoices):
    META_ADS = 'META_ADS', 'Meta Ads'
    GOOGLE_ADS = 'GOOGLE_ADS', 'Google Ads'


class AlertStatus(models.TextChoices):
    TRIGGERED = 'TRIGGERED', 'Triggered'
    SENT = 'SENT', 'Notification Sent'
    FAILED = 'FAILED', 'Notification Failed'


class Campaign(models.Model):
    """
    Represents an advertising campaign on Meta Ads or Google Ads with an allocated budget.
    """
    name = models.CharField(max_length=255, db_index=True)
    platform = models.CharField(max_length=30, choices=Platform.choices)
    external_campaign_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Optional external identifier from Meta Ads or Google Ads API"
    )
    total_budget = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Allocated budget for the current period in currency units (must be > 0)"
    )
    current_period_start = models.DateField(
        default=timezone.now,
        help_text="Start date of the current budget period"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether the campaign is currently active for monitoring and spending"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'current_period_start']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_budget__gt=Decimal('0.00')),
                name='check_campaign_positive_budget',
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_platform_display()}) - Budget: {self.total_budget}"


class SpendingRecord(models.Model):
    """
    Represents an individual spending event ingested for a campaign.
    """
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='spending_records'
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Amount spent in this event (must be > 0)"
    )
    source_reference = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Optional identifier or reference from the ad platform or billing event"
    )
    idempotency_key = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        help_text="Unique client-provided key to guarantee idempotent spending ingestion"
    )
    recorded_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Timestamp when the spending occurred"
    )

    class Meta:
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['campaign', 'recorded_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal('0.00')),
                name='check_spending_positive_amount',
            )
        ]

    def __str__(self) -> str:
        return f"Campaign {self.campaign_id}: {self.amount} on {self.recorded_at.isoformat()}"


class BudgetAlert(models.Model):
    """
    Immutable audit record of a threshold alert triggered when campaign spending
    reaches or exceeds configured utilization thresholds (e.g., 90% and 99%).
    """
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='alerts'
    )
    threshold_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Configured threshold percentage (e.g., 90.00, 99.00)"
    )
    spending_at_alert = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Total cumulative spending at the moment the alert was triggered"
    )
    budget_at_alert = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Total budget at the moment the alert was triggered"
    )
    period_start = models.DateField(
        help_text="Campaign period start date this alert belongs to"
    )
    status = models.CharField(
        max_length=20,
        choices=AlertStatus.choices,
        default=AlertStatus.TRIGGERED,
        help_text="Notification delivery status"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the alert was generated"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['campaign', 'threshold_percentage']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            # Primary alert deduplication constraint: only ONE alert per campaign, threshold, and budget period
            models.UniqueConstraint(
                fields=['campaign', 'threshold_percentage', 'period_start'],
                name='unique_campaign_threshold_period',
            ),
            models.CheckConstraint(
                condition=models.Q(threshold_percentage__gt=Decimal('0.00')),
                name='check_positive_threshold',
            ),
            models.CheckConstraint(
                condition=models.Q(spending_at_alert__gte=Decimal('0.00')),
                name='check_non_negative_spending_at_alert',
            ),
            models.CheckConstraint(
                condition=models.Q(budget_at_alert__gt=Decimal('0.00')),
                name='check_positive_budget_at_alert',
            ),
        ]

    def __str__(self) -> str:
        return f"Campaign {self.campaign_id} Alert: {self.threshold_percentage}% ({self.period_start})"
