web: daphne -b 0.0.0.0 -p $PORT config.asgi:application
worker: celery -A config worker -l info -Q default,pdf_extraction
beat: celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
release: python manage.py migrate --noinput && python manage.py collectstatic --noinput --clear && python manage.py setup_periodic_tasks
