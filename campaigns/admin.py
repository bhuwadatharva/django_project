from django.contrib import admin
from .models import Campaign, SpendingRecord, BudgetAlert


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'platform', 'total_budget', 'current_period_start', 'is_active', 'created_at')
    list_filter = ('platform', 'is_active', 'current_period_start')
    search_fields = ('name', 'external_campaign_id')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SpendingRecord)
class SpendingRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'campaign', 'amount', 'source_reference', 'idempotency_key', 'recorded_at')
    list_filter = ('campaign', 'recorded_at')
    search_fields = ('source_reference', 'idempotency_key')
    readonly_fields = ('recorded_at',)


@admin.register(BudgetAlert)
class BudgetAlertAdmin(admin.ModelAdmin):
    list_display = ('id', 'campaign', 'threshold_percentage', 'spending_at_alert', 'budget_at_alert', 'period_start', 'status', 'created_at')
    list_filter = ('threshold_percentage', 'status', 'period_start')
    search_fields = ('campaign__name',)
    readonly_fields = ('created_at',)
