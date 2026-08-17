"""
Register Celery Beat periodic tasks (idempotent).

Run after migrations on deploy:
    python manage.py setup_periodic_tasks
"""
from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask


TASKS = [
    {
        'name': 'cleanup-stale-waiting-sessions',
        'task': 'core.tasks.cleanup_stale_waiting_sessions',
        'hour': '3',
        'minute': '0',
    },
    {
        'name': 'cleanup-expired-jwt-tokens',
        'task': 'core.tasks.cleanup_expired_jwt_tokens',
        'hour': '4',
        'minute': '0',
    },
    {
        'name': 'cleanup-stuck-materials',
        'task': 'core.tasks.cleanup_stuck_materials',
        'hour': '5',
        'minute': '0',
    },
]


class Command(BaseCommand):
    help = 'Create or update django-celery-beat periodic maintenance tasks.'

    def handle(self, *args, **options):
        for spec in TASKS:
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=spec['minute'],
                hour=spec['hour'],
                day_of_week='*',
                day_of_month='*',
                month_of_year='*',
                timezone='UTC',
            )
            task, created = PeriodicTask.objects.update_or_create(
                name=spec['name'],
                defaults={
                    'crontab': schedule,
                    'task': spec['task'],
                    'enabled': True,
                },
            )
            verb = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'{verb} periodic task: {task.name}'))
