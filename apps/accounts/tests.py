import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from .models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def teacher_data():
    return {
        "email": "test@learnleague.com",
        "username": "testteacher",
        "first_name": "Test",
        "last_name": "Teacher",
        "password": "TestPass123!",
        "password_confirm": "TestPass123!",
        "school": "Test School",
    }


@pytest.fixture
def teacher(db, teacher_data):
    data = teacher_data.copy()
    data.pop("password_confirm")
    password = data.pop("password")
    user = User.objects.create_user(**data, password=password)
    return user


@pytest.mark.django_db
class TestRegister:
    def test_register_success(self, api_client, teacher_data):
        url = reverse("auth-register")
        response = api_client.post(url, teacher_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["success"] is True
        assert "tokens" in response.data
        assert User.objects.filter(email=teacher_data["email"]).exists()

    def test_register_duplicate_email(self, api_client, teacher, teacher_data):
        url = reverse("auth-register")
        response = api_client.post(url, teacher_data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_password_mismatch(self, api_client, teacher_data):
        teacher_data["password_confirm"] = "DifferentPass123!"
        url = reverse("auth-register")
        response = api_client.post(url, teacher_data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_weak_password(self, api_client, teacher_data):
        teacher_data["password"] = "123"
        teacher_data["password_confirm"] = "123"
        url = reverse("auth-register")
        response = api_client.post(url, teacher_data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client, teacher):
        url = reverse("auth-login")
        response = api_client.post(url, {"email": teacher.email, "password": "TestPass123!"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "tokens" in response.data
        assert response.data["tokens"]["access"]

    def test_login_wrong_password(self, api_client, teacher):
        url = reverse("auth-login")
        response = api_client.post(url, {"email": teacher.email, "password": "wrongpassword"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_unknown_email(self, api_client):
        url = reverse("auth-login")
        response = api_client.post(url, {"email": "unknown@test.com", "password": "anything"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestProfile:
    def test_get_profile(self, api_client, teacher):
        api_client.force_authenticate(user=teacher)
        url = reverse("auth-profile")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == teacher.email

    def test_update_profile(self, api_client, teacher):
        api_client.force_authenticate(user=teacher)
        url = reverse("auth-profile")
        response = api_client.patch(url, {"school": "New School"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        teacher.refresh_from_db()
        assert teacher.school == "New School"

    def test_profile_unauthenticated(self, api_client):
        url = reverse("auth-profile")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestLogout:
    def test_logout_success(self, api_client, teacher):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = str(RefreshToken.for_user(teacher))
        api_client.force_authenticate(user=teacher)
        url = reverse("auth-logout")
        response = api_client.post(url, {"refresh": refresh}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True

    def test_logout_unauthenticated(self, api_client):
        url = reverse("auth-logout")
        response = api_client.post(url, {"refresh": "invalid"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestChangePassword:
    def test_change_password_success(self, api_client, teacher):
        api_client.force_authenticate(user=teacher)
        url = reverse("auth-change-password")
        response = api_client.post(url, {
            "old_password": "TestPass123!",
            "new_password": "NewPass456!",
            "confirm_password": "NewPass456!",
        }, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "tokens" in response.data
        teacher.refresh_from_db()
        assert teacher.check_password("NewPass456!")

    def test_change_password_mismatch(self, api_client, teacher):
        api_client.force_authenticate(user=teacher)
        url = reverse("auth-change-password")
        response = api_client.post(url, {
            "old_password": "TestPass123!",
            "new_password": "NewPass456!",
            "confirm_password": "DifferentPass!",
        }, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestTokenRefresh:
    def test_token_refresh_success(self, api_client, teacher):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = str(RefreshToken.for_user(teacher))
        url = reverse("token-refresh")
        response = api_client.post(url, {"refresh": refresh}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data


@pytest.mark.django_db
class TestPasswordReset:
    def test_password_reset_sends_email(self, api_client, teacher, settings):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        url = reverse('auth-password-reset')
        response = api_client.post(url, {'email': teacher.email}, format='json')
        assert response.status_code == status.HTTP_200_OK
        from django.core import mail
        assert len(mail.outbox) == 1

    def test_password_reset_unknown_email(self, api_client, settings):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        url = reverse('auth-password-reset')
        response = api_client.post(url, {'email': 'unknown@test.com'}, format='json')
        assert response.status_code == status.HTTP_200_OK
        from django.core import mail
        assert len(mail.outbox) == 0

    def test_password_reset_confirm(self, api_client, teacher):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(teacher.pk))
        token = default_token_generator.make_token(teacher)
        url = reverse('auth-password-reset-confirm')
        response = api_client.post(url, {
            'uid': uid,
            'token': token,
            'new_password': 'NewSecure456!',
            'confirm_password': 'NewSecure456!',
        }, format='json')
        assert response.status_code == status.HTTP_200_OK
        teacher.refresh_from_db()
        assert teacher.check_password('NewSecure456!')
