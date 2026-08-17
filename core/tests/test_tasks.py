import pytest
from datetime import timedelta
from django.utils import timezone

from apps.accounts.models import User
from apps.activities.models import Activity
from apps.games.models import GameSession
from apps.materials.models import TeachingMaterial
from core.tasks import (
    cleanup_stale_waiting_sessions,
    cleanup_expired_jwt_tokens,
    cleanup_stuck_materials,
)


@pytest.fixture
def teacher(db):
    return User.objects.create_user(
        username='maint_teacher', email='maint@test.com',
        password='TestPass123', role='teacher',
    )


@pytest.mark.django_db
class TestMaintenanceTasks:
    def test_cleanup_stale_waiting_sessions(self, teacher):
        activity = Activity.objects.create(title='Q', teacher=teacher, status='ready')
        old = GameSession.objects.create(activity=activity, teacher=teacher, status='waiting')
        GameSession.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(hours=48)
        )
        recent = GameSession.objects.create(activity=activity, teacher=teacher, status='waiting')

        deleted = cleanup_stale_waiting_sessions()
        assert deleted == 1
        assert not GameSession.objects.filter(pk=old.pk).exists()
        assert GameSession.objects.filter(pk=recent.pk).exists()

    def test_cleanup_stuck_materials(self, teacher):
        mat = TeachingMaterial.objects.create(
            title='Stuck', teacher=teacher, status='processing',
        )
        TeachingMaterial.objects.filter(pk=mat.pk).update(
            updated_at=timezone.now() - timedelta(hours=5)
        )
        count = cleanup_stuck_materials()
        assert count == 1
        mat.refresh_from_db()
        assert mat.status == 'failed'

    def test_cleanup_expired_jwt_tokens(self, teacher):
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

        refresh = RefreshToken.for_user(teacher)
        str(refresh)

        token = OutstandingToken.objects.get(user=teacher)
        OutstandingToken.objects.filter(pk=token.pk).update(
            expires_at=timezone.now() - timedelta(days=1)
        )
        deleted = cleanup_expired_jwt_tokens()
        assert deleted >= 1
