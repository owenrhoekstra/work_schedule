from axes.models import AccessAttempt, AccessLog
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Clear all django-axes lockouts and login history."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Only clear lockouts for this username.")
        parser.add_argument("--ip", help="Only clear lockouts for this IP address.")

    def handle(self, *args, **options):
        qs = AccessAttempt.objects.all()
        if options["username"]:
            qs = qs.filter(username=options["username"])
        if options["ip"]:
            qs = qs.filter(ip_address=options["ip"])

        count = qs.count()
        qs.delete()
        AccessLog.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(f"Cleared {count} lockout(s)."))
