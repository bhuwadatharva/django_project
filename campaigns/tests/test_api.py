import uuid
from decimal import Decimal
import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from campaigns.models import Campaign, Platform, SpendingRecord, BudgetAlert, AlertStatus


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def active_campaign(db):
    return Campaign.objects.create(
        name="Summer Sale 2026",
        platform=Platform.META_ADS,
        total_budget=Decimal("1000.00"),
        is_active=True,
    )


@pytest.mark.django_db
class TestCampaignAPI:
    def test_create_campaign_success(self, api_client):
        url = reverse("campaign-list")
        payload = {
            "name": "Black Friday Promo",
            "platform": "GOOGLE_ADS",
            "total_budget": "5000.00",
            "is_active": True,
        }
        response = api_client.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Black Friday Promo"
        assert response.data["total_budget"] == "5000.00"
        assert response.data["current_period_spending"] == "0.00"
        assert response.data["utilization_percentage"] == "0.00"

    def test_create_campaign_rejects_zero_or_negative_budget(self, api_client):
        url = reverse("campaign-list")
        payload = {
            "name": "Invalid Budget Campaign",
            "platform": "GOOGLE_ADS",
            "total_budget": "0.00",
        }
        response = api_client.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "total_budget" in response.data

        payload["total_budget"] = "-150.00"
        response = api_client.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_campaign_detail_shows_utilization(self, api_client, active_campaign):
        SpendingRecord.objects.create(
            campaign=active_campaign,
            amount=Decimal("450.00"),
            idempotency_key=uuid.uuid4(),
        )

        url = reverse("campaign-detail", kwargs={"pk": active_campaign.id})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["current_period_spending"] == "450.00"
        assert response.data["utilization_percentage"] == "45.00"


@pytest.mark.django_db
class TestSpendingIngestionAPI:
    def test_record_spending_success(self, api_client, active_campaign):
        url = reverse("campaign-record-spending", kwargs={"pk": active_campaign.id})
        idempotency_key = str(uuid.uuid4())
        payload = {
            "amount": "250.50",
            "source_reference": "inv-meta-001",
            "idempotency_key": idempotency_key,
        }
        response = api_client.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["amount"] == "250.50"
        assert response.data["idempotency_key"] == idempotency_key
        assert SpendingRecord.objects.filter(campaign=active_campaign).count() == 1

    def test_idempotent_retry_returns_existing_record_without_duplicate(self, api_client, active_campaign):
        url = reverse("campaign-record-spending", kwargs={"pk": active_campaign.id})
        idempotency_key = str(uuid.uuid4())
        payload = {
            "amount": "100.00",
            "source_reference": "ref-1",
            "idempotency_key": idempotency_key,
        }

        resp1 = api_client.post(url, data=payload, format="json")
        assert resp1.status_code == status.HTTP_201_CREATED

        resp2 = api_client.post(url, data=payload, format="json")
        assert resp2.status_code == status.HTTP_200_OK
        assert resp2.data["id"] == resp1.data["id"]
        assert SpendingRecord.objects.filter(campaign=active_campaign).count() == 1

    def test_idempotent_key_conflict_returns_409(self, api_client, active_campaign):
        url = reverse("campaign-record-spending", kwargs={"pk": active_campaign.id})
        idempotency_key = str(uuid.uuid4())
        payload1 = {
            "amount": "100.00",
            "idempotency_key": idempotency_key,
        }
        resp1 = api_client.post(url, data=payload1, format="json")
        assert resp1.status_code == status.HTTP_201_CREATED

        payload2 = {
            "amount": "200.00",
            "idempotency_key": idempotency_key,
        }
        resp2 = api_client.post(url, data=payload2, format="json")
        assert resp2.status_code == status.HTTP_409_CONFLICT

    def test_reject_negative_or_zero_spending(self, api_client, active_campaign):
        url = reverse("campaign-record-spending", kwargs={"pk": active_campaign.id})
        response = api_client.post(url, data={"amount": "0.00"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = api_client.post(url, data={"amount": "-50.00"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestCampaignUpdatesAndAlertAPIs:
    def test_patch_campaign_updates_budget_and_active_status(self, api_client, active_campaign):
        url = reverse("campaign-detail", kwargs={"pk": active_campaign.id})
        patch_payload = {
            "total_budget": "1500.00",
            "is_active": False,
        }
        response = api_client.patch(url, data=patch_payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_budget"] == "1500.00"
        assert response.data["is_active"] is False

    def test_list_campaign_alerts_endpoint(self, api_client, active_campaign):
        BudgetAlert.objects.create(
            campaign=active_campaign,
            threshold_percentage=Decimal("90.00"),
            spending_at_alert=Decimal("900.00"),
            budget_at_alert=Decimal("1000.00"),
            period_start=active_campaign.current_period_start,
            status=AlertStatus.TRIGGERED,
        )

        url = reverse("campaign-list-alerts", kwargs={"pk": active_campaign.id})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["threshold_percentage"] == "90.00"

    def test_global_alert_list_endpoint_and_filtering(self, api_client, active_campaign):
        BudgetAlert.objects.create(
            campaign=active_campaign,
            threshold_percentage=Decimal("90.00"),
            spending_at_alert=Decimal("900.00"),
            budget_at_alert=Decimal("1000.00"),
            period_start=active_campaign.current_period_start,
            status=AlertStatus.TRIGGERED,
        )
        BudgetAlert.objects.create(
            campaign=active_campaign,
            threshold_percentage=Decimal("99.00"),
            spending_at_alert=Decimal("990.00"),
            budget_at_alert=Decimal("1000.00"),
            period_start=active_campaign.current_period_start,
            status=AlertStatus.TRIGGERED,
        )

        url = reverse("global-alerts")
        resp = api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data["results"]) == 2

        resp_filtered = api_client.get(f"{url}?threshold=99.00")
        assert resp_filtered.status_code == status.HTTP_200_OK
        assert len(resp_filtered.data["results"]) == 1
        assert resp_filtered.data["results"][0]["threshold_percentage"] == "99.00"

    def test_trigger_monitoring_endpoint_permissions(self, api_client, active_campaign):
        url = reverse("trigger-monitoring")

        anon_resp = api_client.post(url, data={}, format="json")
        assert anon_resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

        admin_user = User.objects.create_superuser(
            username="admin_tester",
            email="admin@test.com",
            password="admin_secure_password",
        )
        api_client.force_authenticate(user=admin_user)
        admin_resp = api_client.post(url, data={}, format="json")
        assert admin_resp.status_code == status.HTTP_200_OK
        assert admin_resp.data["status"] == "completed"
        assert "total_campaigns_evaluated" in admin_resp.data
