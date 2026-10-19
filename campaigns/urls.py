from django.urls import path, include
from rest_framework.routers import DefaultRouter

from campaigns.views import CampaignViewSet, GlobalAlertListView, TriggerMonitoringView

router = DefaultRouter()
router.register(r'campaigns', CampaignViewSet, basename='campaign')

urlpatterns = [
    path('alerts/', GlobalAlertListView.as_view(), name='global-alerts'),
    path('monitoring/run/', TriggerMonitoringView.as_view(), name='trigger-monitoring'),
    path('', include(router.urls)),
]
