import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.classes.models import ClassRoom


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def teacher(db):
    return User.objects.create_user(
        username='teacher_cls', email='teacher_cls@test.com',
        password='TestPass123', role='teacher',
        first_name='Alice', last_name='Test',
    )


@pytest.fixture
def other_teacher(db):
    return User.objects.create_user(
        username='other_teacher', email='other@test.com',
        password='TestPass123', role='teacher',
    )


@pytest.fixture
def auth_client(api_client, teacher):
    api_client.force_authenticate(user=teacher)
    return api_client


@pytest.fixture
def classroom(db, teacher):
    return ClassRoom.objects.create(
        name='Math 101', subject='Mathematics',
        education_level='secondary', teacher=teacher,
    )


@pytest.mark.django_db
class TestClassRoomCRUD:
    def test_list_own_classrooms(self, auth_client, classroom):
        url = reverse('classroom-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_cannot_see_other_teachers_classrooms(self, api_client, other_teacher, classroom):
        api_client.force_authenticate(user=other_teacher)
        url = reverse('classroom-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        ids = [c['id'] for c in response.data.get('data', [])]
        assert classroom.id not in ids

    def test_create_classroom(self, auth_client):
        url = reverse('classroom-list')
        data = {
            'name': 'History 201',
            'subject': 'History',
            'education_level': 'bachillerato',
            'color': '#ff6600',
        }
        response = auth_client.post(url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert ClassRoom.objects.filter(name='History 201').exists()

    def test_create_classroom_invalid_color(self, auth_client):
        url = reverse('classroom-list')
        data = {'name': 'Bad Color', 'subject': 'Art', 'education_level': 'secondary', 'color': 'notacolor'}
        response = auth_client.post(url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve_classroom(self, auth_client, classroom):
        url = reverse('classroom-detail', kwargs={'pk': classroom.pk})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['data']['id'] == classroom.id

    def test_update_classroom(self, auth_client, classroom):
        url = reverse('classroom-detail', kwargs={'pk': classroom.pk})
        response = auth_client.patch(url, {'name': 'Updated Math'})
        assert response.status_code == status.HTTP_200_OK
        classroom.refresh_from_db()
        assert classroom.name == 'Updated Math'

    def test_delete_classroom(self, auth_client, classroom):
        url = reverse('classroom-detail', kwargs={'pk': classroom.pk})
        response = auth_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert not ClassRoom.objects.filter(pk=classroom.pk).exists()

    def test_cannot_access_other_teacher_classroom(self, api_client, other_teacher, classroom):
        api_client.force_authenticate(user=other_teacher)
        url = reverse('classroom-detail', kwargs={'pk': classroom.pk})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_classroom_stats(self, auth_client, classroom):
        url = reverse('classroom-stats', kwargs={'pk': classroom.pk})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data['data']
        assert 'materials_count' in data
        assert 'activities_count' in data

    def test_unauthenticated_access(self, api_client):
        url = reverse('classroom-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
