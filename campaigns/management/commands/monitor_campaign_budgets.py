import sys
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError

from campaigns.services.budget_service import run_budget_monitoring


class Command(BaseCommand):
    help = "Monitor active advertising campaigns and generate threshold alerts."

    def add_arguments(self, parser):
        parser.add_argument(
            '--campaign-ids',
            type=str,
            help="Comma-separated list of campaign IDs",
        )
        parser.add_argument(
            '--thresholds',
            type=str,
            help="Comma-separated list of threshold percentages",
        )

    def handle(self, *args, **options):
        campaign_ids_arg = options.get('campaign_ids')
        thresholds_arg = options.get('thresholds')

        campaign_ids = None
        if campaign_ids_arg:
            try:
                campaign_ids = [int(i.strip()) for i in campaign_ids_arg.split(',') if i.strip()]
            except ValueError:
                raise CommandError(f"Invalid integer value in --campaign-ids: {campaign_ids_arg}")

        thresholds = None
        if thresholds_arg:
            try:
                thresholds = [Decimal(t.strip()) for t in thresholds_arg.split(',') if t.strip()]
            except Exception:
                raise CommandError(f"Invalid decimal value in --thresholds: {thresholds_arg}")

        self.stdout.write("Executing campaign budget monitoring runner...")

        summary = run_budget_monitoring(
            campaign_ids=campaign_ids,
            thresholds=thresholds,
        )

        self.stdout.write(
            f"Completed monitoring: {summary.total_campaigns_evaluated} campaign(s) evaluated, "
            f"{summary.total_alerts_created} alert(s) generated."
        )

        if summary.has_failures:
            self.stderr.write(
                f"Warning: Failed processing {len(summary.failed_campaign_ids)} campaign(s)"
            )
            sys.exit(1)
