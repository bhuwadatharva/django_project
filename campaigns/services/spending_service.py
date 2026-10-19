import uuid
from decimal import Decimal
from typing import Optional, Tuple
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError, Conflict

from campaigns.models import Campaign, SpendingRecord


class SpendingIngestionError(Exception):
    """Base exception for spending ingestion failures."""
    pass


class IdempotencyConflictError(SpendingIngestionError):
    """Raised when an idempotency key is reused with different parameters."""
    pass


def ingest_spending(
    campaign: Campaign,
    amount: Decimal,
    idempotency_key: uuid.UUID,
    source_reference: str = '',
    recorded_at: Optional[timezone.datetime] = None,
) -> Tuple[SpendingRecord, bool]:
    """
    Ingest a spending event for a campaign with strict idempotency and validation.

    Returns:
        Tuple[SpendingRecord, bool]: (spending_record, created)
        - If created is True, the record was newly inserted.
        - If created is False, the request was an idempotent retry of an identical past event.

    Raises:
        ValidationError: If amount is non-positive or campaign is invalid.
        IdempotencyConflictError: If the idempotency key was previously used with different parameters.
    """
    if amount <= Decimal('0.00'):
        raise ValidationError({'amount': 'Spending amount must be strictly greater than 0.00.'})

    # Check for existing record with this idempotency key
    existing_record = SpendingRecord.objects.filter(idempotency_key=idempotency_key).first()
    if existing_record:
        # Verify the payload matches the original request
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
        # Handle concurrent insertion race condition where two identical requests arrive simultaneously
        record = SpendingRecord.objects.filter(idempotency_key=idempotency_key).first()
        if record and record.campaign_id == campaign.id and record.amount == amount:
            return record, False
        raise
