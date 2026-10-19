import logging
import uuid
from decimal import Decimal
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from campaigns.models import Campaign, SpendingRecord, BudgetAlert
from campaigns.serializers import (
    CampaignSerializer,
    SpendingRecordSerializer,
    BudgetAlertSerializer,
)
from campaigns.services.budget_service import run_budget_monitoring
from campaigns.services.spending_service import (
    ingest_spending,
    IdempotencyConflictError,
)

logger = logging.getLogger('campaigns')


class CampaignViewSet(viewsets.ModelViewSet):
    queryset = Campaign.objects.all().order_by('-created_at')
    serializer_class = CampaignSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        is_active = self.request.query_params.get('is_active')
        platform = self.request.query_params.get('platform')
        search = self.request.query_params.get('search')

        if is_active is not None:
            if is_active.lower() in ('true', '1'):
                queryset = queryset.filter(is_active=True)
            elif is_active.lower() in ('false', '0'):
                queryset = queryset.filter(is_active=False)

        if platform:
            queryset = queryset.filter(platform=platform)

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset

    @action(detail=True, methods=['post'], url_path='spending')
    def record_spending(self, request, pk=None):
        campaign = self.get_object()
        serializer = SpendingRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data['amount']
        idempotency_key = serializer.validated_data.get('idempotency_key', uuid.uuid4())
        source_reference = serializer.validated_data.get('source_reference', '')
        recorded_at = serializer.validated_data.get('recorded_at')

        try:
            record, created = ingest_spending(
                campaign=campaign,
                amount=amount,
                idempotency_key=idempotency_key,
                source_reference=source_reference,
                recorded_at=recorded_at,
            )
        except IdempotencyConflictError as err:
            logger.warning("Idempotency conflict for campaign %s: %s", campaign.id, str(err))
            return Response(
                {'detail': str(err)},
                status=status.HTTP_409_CONFLICT,
            )

        response_data = SpendingRecordSerializer(record).data
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(response_data, status=status_code)

    @action(detail=True, methods=['get'], url_path='alerts')
    def list_alerts(self, request, pk=None):
        campaign = self.get_object()
        alerts = campaign.alerts.all().order_by('-created_at')
        page = self.paginate_queryset(alerts)
        if page is not None:
            serializer = BudgetAlertSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = BudgetAlertSerializer(alerts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GlobalAlertListView(APIView):
    def get(self, request):
        alerts = BudgetAlert.objects.select_related('campaign').all().order_by('-created_at')

        threshold = request.query_params.get('threshold')
        campaign_id = request.query_params.get('campaign_id')
        status_filter = request.query_params.get('status')

        if threshold:
            try:
                alerts = alerts.filter(threshold_percentage=Decimal(threshold))
            except Exception:
                raise ValidationError({'threshold': 'Invalid decimal threshold.'})

        if campaign_id:
            alerts = alerts.filter(campaign_id=campaign_id)

        if status_filter:
            alerts = alerts.filter(status=status_filter)

        paginator = CampaignViewSet().paginator
        page = paginator.paginate_queryset(alerts, request)
        if page is not None:
            serializer = BudgetAlertSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = BudgetAlertSerializer(alerts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TriggerMonitoringView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        campaign_ids = request.data.get('campaign_ids')
        summary = run_budget_monitoring(campaign_ids=campaign_ids)
        return Response(
            {
                'status': 'completed',
                'total_campaigns_evaluated': summary.total_campaigns_evaluated,
                'total_alerts_created': summary.total_alerts_created,
                'created_alert_ids': summary.created_alert_ids,
                'failed_campaign_ids': summary.failed_campaign_ids,
            },
            status=status.HTTP_200_OK,
        )
