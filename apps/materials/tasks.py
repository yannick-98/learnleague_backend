import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='pdf_extraction')
def extract_pdf_text(self, material_id: int):
    """
    Celery task: Extract text from a PDF TeachingMaterial.
    Updates status to processing → completed or failed.
    """
    from apps.materials.models import TeachingMaterial
    from apps.materials.utils import extract_text_from_pdf

    try:
        material = TeachingMaterial.objects.get(pk=material_id)
    except TeachingMaterial.DoesNotExist:
        logger.error('TeachingMaterial %d not found.', material_id)
        return

    if material.status == 'completed':
        logger.info('Material %d already completed. Skipping.', material_id)
        return

    # Mark as processing
    material.status = 'processing'
    material.error_message = ''
    material.save(update_fields=['status', 'error_message', 'updated_at'])

    try:
        if not material.pdf_file:
            raise ValueError('No PDF file attached to this material.')

        # Use the storage backend API so this works with both local disk and S3
        # (avoids .path which is unavailable on remote storage backends).
        with material.pdf_file.open('rb') as pdf_file:
            text, page_count = extract_text_from_pdf(pdf_file)

        material.extracted_text = text
        material.page_count = page_count
        material.status = 'completed'
        material.error_message = ''
        material.save(update_fields=[
            'extracted_text', 'page_count', 'status', 'error_message', 'updated_at'
        ])

        logger.info(
            'Material %d processed: %d pages, %d characters extracted.',
            material_id, page_count, len(text),
        )

    except Exception as exc:
        logger.exception('Error processing material %d: %s', material_id, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            material.status = 'failed'
            material.error_message = str(exc)[:1000]
            material.save(update_fields=['status', 'error_message', 'updated_at'])
            logger.error('Material %d permanently failed after %d retries.', material_id, self.max_retries)
