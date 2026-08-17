import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch

from apps.accounts.models import User
from apps.activities.models import Activity, Question
from apps.materials.models import TeachingMaterial


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def teacher(db):
    return User.objects.create_user(
        username='act_teacher', email='act_teacher@test.com',
        password='TestPass123', role='teacher',
    )


@pytest.fixture
def other_teacher(db):
    return User.objects.create_user(
        username='other_act', email='other_act@test.com', password='TestPass123',
    )


@pytest.fixture
def auth_client(api_client, teacher):
    api_client.force_authenticate(user=teacher)
    return api_client


@pytest.fixture
def material(db, teacher):
    return TeachingMaterial.objects.create(
        title='Test Material', teacher=teacher,
        status='completed',
        extracted_text='The mitochondria is the powerhouse of the cell. It produces ATP through cellular respiration. This process requires oxygen and glucose.',
    )


@pytest.fixture
def activity(db, teacher):
    return Activity.objects.create(
        title='Test Quiz', teacher=teacher, status='draft', time_per_question=30,
    )


@pytest.fixture
def question(db, activity):
    return Question.objects.create(
        activity=activity, text='What is 2+2?',
        option_a='3', option_b='4', option_c='5', option_d='6',
        correct_option='B', difficulty='easy', order=0,
    )


@pytest.mark.django_db
class TestActivityCRUD:
    def test_create_activity(self, auth_client):
        url = reverse('activity-list')
        data = {'title': 'New Quiz', 'time_per_question': 45}
        response = auth_client.post(url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert Activity.objects.filter(title='New Quiz').exists()

    def test_list_activities(self, auth_client, activity):
        url = reverse('activity-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_retrieve_activity(self, auth_client, activity):
        url = reverse('activity-detail', kwargs={'pk': activity.pk})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['data']['id'] == activity.id

    def test_update_activity(self, auth_client, activity):
        url = reverse('activity-detail', kwargs={'pk': activity.pk})
        response = auth_client.patch(url, {'title': 'Updated Quiz'})
        assert response.status_code == status.HTTP_200_OK
        activity.refresh_from_db()
        assert activity.title == 'Updated Quiz'

    def test_delete_activity(self, auth_client, activity):
        url = reverse('activity-detail', kwargs={'pk': activity.pk})
        response = auth_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert not Activity.objects.filter(pk=activity.pk).exists()

    def test_cannot_access_other_teacher_activity(self, api_client, other_teacher, activity):
        api_client.force_authenticate(user=other_teacher)
        url = reverse('activity-detail', kwargs={'pk': activity.pk})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestQuestionGeneration:
    def test_generate_questions_mock(self, auth_client, activity, material):
        url = reverse('activity-generate-questions-view', kwargs={'pk': activity.pk})
        data = {'material_id': material.id, 'num_questions': 5, 'difficulty': 'medium'}
        response = auth_client.post(url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['data']['questions_created'] == 5
        assert Question.objects.filter(activity=activity).count() == 5

    def test_generate_questions_invalid_material(self, auth_client, activity):
        url = reverse('activity-generate-questions-view', kwargs={'pk': activity.pk})
        data = {'material_id': 99999, 'num_questions': 5, 'difficulty': 'medium'}
        response = auth_client.post(url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_generate_questions_unprocessed_material(self, auth_client, activity, teacher):
        mat = TeachingMaterial.objects.create(
            title='Pending Mat', teacher=teacher, status='pending',
        )
        url = reverse('activity-generate-questions-view', kwargs={'pk': activity.pk})
        data = {'material_id': mat.id, 'num_questions': 5}
        response = auth_client.post(url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestDuplicateAndExport:
    def test_duplicate_activity(self, auth_client, activity, question):
        url = reverse('activity-duplicate', kwargs={'pk': activity.pk})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_201_CREATED
        assert Activity.objects.filter(title__contains='Copy').exists()
        assert response.data['data']['question_count'] == 1

    def test_export_json(self, auth_client, activity, question):
        url = reverse('activity-export-json', kwargs={'pk': activity.pk})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/json'

    def test_export_csv(self, auth_client, activity, question):
        url = reverse('activity-export-csv', kwargs={'pk': activity.pk})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'text/csv' in response['Content-Type']


@pytest.mark.django_db
class TestMarkReadyAndImport:
    def test_mark_ready_with_questions(self, auth_client, activity, question):
        url = reverse('activity-mark-ready', kwargs={'pk': activity.pk})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        activity.refresh_from_db()
        assert activity.status == 'ready'

    def test_mark_ready_without_questions(self, auth_client, activity):
        url = reverse('activity-mark-ready', kwargs={'pk': activity.pk})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_import_csv(self, auth_client, activity):
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv_content = (
            'Order,Text,Option A,Option B,Option C,Option D,Correct Option,Explanation,Difficulty,Topic\n'
            '0,Question 1?,A1,B1,C1,D1,B,Because,medium,Math\n'
        )
        csv_file = SimpleUploadedFile('questions.csv', csv_content.encode('utf-8'), content_type='text/csv')
        url = reverse('activity-import-csv', kwargs={'pk': activity.pk})
        response = auth_client.post(url, {'file': csv_file}, format='multipart')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['data']['imported'] == 1
        activity.refresh_from_db()
        assert activity.status == 'ready'
        assert activity.questions.count() == 1
