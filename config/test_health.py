import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestHealthCheck:
    def test_health_check_returns_status(self, api_client):
        response = api_client.get(reverse('health_check'))
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE)
        data = response.json()
        assert 'status' in data
        assert 'db' in data
