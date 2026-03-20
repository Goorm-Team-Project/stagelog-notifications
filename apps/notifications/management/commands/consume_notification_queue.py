from django.conf import settings
from django.core.management.base import BaseCommand

from notifications.services_consumer import consume_notification_batch


class Command(BaseCommand):
    help = "Consume notification messages from SQS and store into DynamoDB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue-url",
            default=settings.NOTIFICATION_SQS_QUEUE_URL,
            help="SQS queue URL (default: settings.NOTIFICATION_SQS_QUEUE_URL)",
        )
        parser.add_argument(
            "--max-messages",
            type=int,
            default=settings.NOTIFICATION_CONSUMER_MAX_MESSAGES,
        )
        parser.add_argument(
            "--wait-time-seconds",
            type=int,
            default=settings.NOTIFICATION_CONSUMER_WAIT_TIME_SECONDS,
        )

    def handle(self, *args, **options):
        result = consume_notification_batch(
            queue_url=options["queue_url"],
            max_messages=options["max_messages"],
            wait_time_seconds=options["wait_time_seconds"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                "received={received} saved={saved} deleted={deleted} failed={failed}".format(**result)
            )
        )
