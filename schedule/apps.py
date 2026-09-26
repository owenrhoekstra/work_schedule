from django.apps import AppConfig


class ScheduleConfig(AppConfig):
    name = "schedule"

    def ready(self):
        from . import signals  # noqa: F401
