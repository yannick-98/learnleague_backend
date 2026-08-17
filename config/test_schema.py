import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestOpenAPISchema:
    @override_settings(DEBUG=True, ALLOW_API_DOCS=True)
    def test_schema_available_in_debug(self, api_client):
        url = reverse('schema')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data.get('openapi') or response.data.get('swagger')

    def test_swagger_gated_in_production(self, api_client, settings):
        settings.DEBUG = False
        settings.ALLOW_API_DOCS = False
        response = api_client.get('/api/docs/')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_setup_periodic_tasks_command(self):
        from django.core.management import call_command
        from django_celery_beat.models import PeriodicTask

        call_command('setup_periodic_tasks')
        assert PeriodicTask.objects.filter(name='cleanup-stale-waiting-sessions').exists()
