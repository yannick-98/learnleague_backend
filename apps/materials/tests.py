import io
import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch

from apps.accounts.models import User
from apps.materials.models import TeachingMaterial


FAKE_PDF_BYTES = (
    b'%PDF-1.4\n'
    b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n'
    b'2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n'
    b'3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n'
    b'xref\n0 4\n0000000000 65535 f\n'
    b'trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n9\n%%EOF'
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def teacher(db):
    return User.objects.create_user(
        username='mat_teacher', email='mat_teacher@test.com',
        password='TestPass123', role='teacher',
    )


@pytest.fixture
def auth_client(api_client, teacher):
    api_client.force_authenticate(user=teacher)
    return api_client


@pytest.fixture
def material(db, teacher):
    return TeachingMaterial.objects.create(
        title='Test Material',
        teacher=teacher,
        status='completed',
        extracted_text='This is the extracted text from the PDF.',
        page_count=5,
        file_size=1024,
    )


@pytest.mark.django_db
class TestMaterialUpload:
    @patch('django.db.transaction.on_commit', lambda callback: callback())
    @patch('apps.materials.views._S3_CONFIGURED', True)
    @patch('apps.materials.views.extract_pdf_text')
    def test_upload_pdf(self, mock_task, auth_client):
        url = reverse('material-list')
        pdf_file = SimpleUploadedFile(
            'test.pdf', FAKE_PDF_BYTES, content_type='application/pdf'
        )
        data = {'title': 'My PDF', 'pdf_file': pdf_file}
        response = auth_client.post(url, data, format='multipart')
        assert response.status_code == status.HTTP_201_CREATED
        mock_task.delay.assert_called_once()

    @patch('apps.materials.views.extract_pdf_text')
    def test_upload_too_large(self, mock_task, auth_client):
        url = reverse('material-list')
        large_content = b'%PDF-' + b'x' * (21 * 1024 * 1024)
        pdf_file = SimpleUploadedFile('big.pdf', large_content, content_type='application/pdf')
        response = auth_client.post(url, {'title': 'Big PDF', 'pdf_file': pdf_file}, format='multipart')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_materials(self, auth_client, material):
        url = reverse('material-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_retrieve_material(self, auth_client, material):
        url = reverse('material-detail', kwargs={'pk': material.pk})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['data']['id'] == material.id

    def test_preview_extracted_text(self, auth_client, material):
        url = reverse('material-preview', kwargs={'pk': material.pk})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'preview' in response.data['data']

    def test_download_pdf_file(self, auth_client, material):
        pdf_file = SimpleUploadedFile('test.pdf', FAKE_PDF_BYTES, content_type='application/pdf')
        material.pdf_file = pdf_file
        material.save()
        url = reverse('material-file', kwargs={'pk': material.pk})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
        body = b''.join(response.streaming_content)
        assert body.startswith(b'%PDF')

    def test_download_pdf_file_not_found(self, auth_client, material):
        url = reverse('material-file', kwargs={'pk': material.pk})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch('apps.materials.views.extract_pdf_text')
    def test_reprocess_material(self, mock_task, auth_client, material):
        material.pdf_file.name = 'materials/pdfs/test.pdf'
        material.save()
        # Directly set the field to simulate a file being present
        TeachingMaterial.objects.filter(pk=material.pk).update(pdf_file='materials/pdfs/test.pdf')
        url = reverse('material-reprocess', kwargs={'pk': material.pk})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_200_OK

    def test_delete_material(self, auth_client, material):
        url = reverse('material-detail', kwargs={'pk': material.pk})
        response = auth_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert not TeachingMaterial.objects.filter(pk=material.pk).exists()

    def test_cannot_access_other_teacher_material(self, api_client, teacher, material):
        other = User.objects.create_user(
            username='othmat', email='othmat@test.com', password='TestPass123'
        )
        api_client.force_authenticate(user=other)
        url = reverse('material-detail', kwargs={'pk': material.pk})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_material_title(self, auth_client, material):
        url = reverse('material-detail', kwargs={'pk': material.pk})
        response = auth_client.patch(url, {'title': 'Updated Title'}, format='json')
        assert response.status_code == status.HTTP_200_OK
        material.refresh_from_db()
        assert material.title == 'Updated Title'
