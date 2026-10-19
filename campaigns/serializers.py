import datetime as dt
import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from campaigns.models import Campaign, SpendingRecord, BudgetAlert


class CampaignSerializer(serializers.ModelSerializer):
    current_period_spending = serializers.SerializerMethodField()
    utilization_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            'id',
            'name',
            'platform',
            'external_campaign_id',
            'total_budget',
            'current_period_start',
            'is_active',
            'current_period_spending',
            'utilization_percentage',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'current_period_spending', 'utilization_percentage']

    def validate_total_budget(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Total budget must be strictly greater than 0.00.")
        return value

    def get_current_period_spending(self, obj):
        midnight = dt.datetime.combine(obj.current_period_start, dt.time.min)
        start_dt = midnight if timezone.is_aware(midnight) else timezone.make_aware(midnight)
        total = obj.spending_records.filter(
            recorded_at__gte=start_dt
        ).aggregate(total=Sum('amount'))['total']
        spending = total if total is not None else Decimal('0.00')
        return str(spending.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def get_utilization_percentage(self, obj):
        if obj.total_budget <= Decimal('0.00'):
            return "0.00"

        midnight = dt.datetime.combine(obj.current_period_start, dt.time.min)
        start_dt = midnight if timezone.is_aware(midnight) else timezone.make_aware(midnight)
        total = obj.spending_records.filter(
            recorded_at__gte=start_dt
        ).aggregate(total=Sum('amount'))['total']
        spending = total if total is not None else Decimal('0.00')
        utilization = (spending / obj.total_budget) * Decimal('100.0')
        return str(utilization.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class SpendingRecordSerializer(serializers.ModelSerializer):
    idempotency_key = serializers.UUIDField(default=uuid.uuid4)

    class Meta:
        model = SpendingRecord
        fields = [
            'id',
            'campaign',
            'amount',
            'source_reference',
            'idempotency_key',
            'recorded_at',
        ]
        read_only_fields = ['id', 'campaign']

    def validate_amount(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Spending amount must be strictly greater than 0.00.")
        return value


class BudgetAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetAlert
        fields = [
            'id',
            'campaign',
            'threshold_percentage',
            'spending_at_alert',
            'budget_at_alert',
            'period_start',
            'status',
            'created_at',
        ]
        read_only_fields = fields
