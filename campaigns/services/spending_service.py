from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from campaigns.models import SpendingRecord


class SpendingIngestionError(Exception):
    pass


class IdempotencyConflictError(SpendingIngestionError):
    pass


def ingest_spending(
    campaign,
    amount,
    idempotency_key,
    source_reference='',
    recorded_at=None,
):
    if amount <= Decimal('0.00'):
        raise ValidationError({'amount': 'Spending amount must be strictly greater than 0.00.'})

    existing_record = SpendingRecord.objects.filter(idempotency_key=idempotency_key).first()
    if existing_record:
        if existing_record.campaign_id != campaign.id or existing_record.amount != amount:
            raise IdempotencyConflictError(
                f"Idempotency key '{idempotency_key}' has already been used with different parameters."
            )
        return existing_record, False

    if recorded_at is None:
        recorded_at = timezone.now()

    try:
        with transaction.atomic():
            record = SpendingRecord.objects.create(
                campaign=campaign,
                amount=amount,
                source_reference=source_reference,
                idempotency_key=idempotency_key,
                recorded_at=recorded_at,
            )
            return record, True
    except IntegrityError:
        record = SpendingRecord.objects.filter(idempotency_key=idempotency_key).first()
        if record and record.campaign_id == campaign.id and record.amount == amount:
            return record, False
        raise
