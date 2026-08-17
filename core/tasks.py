import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='core.tasks.cleanup_stale_waiting_sessions')
def cleanup_stale_waiting_sessions(max_age_hours: int = 24) -> int:
    """Delete game sessions stuck in 'waiting' longer than max_age_hours."""
    from apps.games.models import GameSession

    cutoff = timezone.now() - timedelta(hours=max_age_hours)
    qs = GameSession.objects.filter(status='waiting', created_at__lt=cutoff)
    count = qs.count()
    qs.delete()
    logger.info('Deleted %d stale waiting sessions (older than %dh).', count, max_age_hours)
    return count


@shared_task(name='core.tasks.cleanup_expired_jwt_tokens')
def cleanup_expired_jwt_tokens() -> int:
    """Remove expired outstanding JWT tokens from the blacklist app tables."""
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    qs = OutstandingToken.objects.filter(expires_at__lt=timezone.now())
    count = qs.count()
    qs.delete()
    logger.info('Deleted %d expired JWT outstanding tokens.', count)
    return count


@shared_task(name='core.tasks.cleanup_stuck_materials')
def cleanup_stuck_materials(max_processing_hours: int = 2) -> int:
    """Mark PDF materials stuck in 'processing' as failed."""
    from apps.materials.models import TeachingMaterial

    cutoff = timezone.now() - timedelta(hours=max_processing_hours)
    qs = TeachingMaterial.objects.filter(status='processing', updated_at__lt=cutoff)
    count = qs.count()
    qs.update(
        status='failed',
        error_message='Processing timed out. Please reprocess the material.',
    )
    logger.info('Marked %d stuck materials as failed.', count)
    return count
