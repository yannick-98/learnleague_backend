import logging
import os

from django.db import transaction
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from apps.accounts.permissions import IsTeacher
from rest_framework.response import Response

from .models import TeachingMaterial
from .serializers import (
    TeachingMaterialSerializer,
    TeachingMaterialUploadSerializer,
    TeachingMaterialUpdateSerializer,
)
from .tasks import extract_pdf_text
from .utils import extract_text_from_pdf

logger = logging.getLogger(__name__)

# When S3 is not configured, every dyno has its own ephemeral filesystem, so the
# Celery worker cannot access a file uploaded by the web dyno.  In that case we
# extract text synchronously inside the web request instead of dispatching a task.
_S3_CONFIGURED = bool(os.environ.get('AWS_STORAGE_BUCKET_NAME'))


def _run_extraction(material: TeachingMaterial) -> None:
    """Extract PDF text and persist results on *material* in-process."""
    try:
        material.status = 'processing'
        material.error_message = ''
        material.save(update_fields=['status', 'error_message', 'updated_at'])

        with material.pdf_file.open('rb') as pdf_file:
            text, page_count = extract_text_from_pdf(pdf_file)

        material.extracted_text = text
        material.page_count = page_count
        material.status = 'completed'
        material.error_message = ''
        material.save(update_fields=['extracted_text', 'page_count', 'status', 'error_message', 'updated_at'])
        logger.info('Material %d extracted synchronously: %d pages, %d chars.', material.id, page_count, len(text))
    except Exception as exc:
        logger.exception('Sync PDF extraction failed for material %d: %s', material.id, exc)
        material.status = 'failed'
        material.error_message = str(exc)[:1000]
        material.save(update_fields=['status', 'error_message', 'updated_at'])


class TeachingMaterialViewSet(viewsets.ModelViewSet):
    """
    ViewSet for teaching materials. Supports file upload and PDF text extraction.
    """
    permission_classes = [IsTeacher]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = TeachingMaterial.objects.filter(teacher=self.request.user).select_related(
            'teacher', 'classroom'
        )
        classroom_id = self.request.query_params.get('classroom')
        if classroom_id:
            qs = qs.filter(classroom_id=classroom_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return TeachingMaterialUploadSerializer
        if self.action in ('update', 'partial_update'):
            return TeachingMaterialUpdateSerializer
        return TeachingMaterialSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = TeachingMaterialUpdateSerializer(
            instance, data=request.data, partial=partial, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        material = serializer.save()
        output = TeachingMaterialSerializer(material, context={'request': request})
        return Response({'success': True, 'data': output.data})

    def create(self, request, *args, **kwargs):
        serializer = TeachingMaterialUploadSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        material = serializer.save()

        if _S3_CONFIGURED:
            # With S3 every dyno reads from the same bucket — safe to use Celery.
            _mid = material.id
            transaction.on_commit(lambda: extract_pdf_text.delay(_mid))
        else:
            # No shared storage: extract text right now in the web process so the
            # response already contains the final status (completed / failed).
            _run_extraction(material)

        output = TeachingMaterialSerializer(material, context={'request': request})
        return Response(
            {'success': True, 'data': output.data},
            status=status.HTTP_201_CREATED,
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = TeachingMaterialSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = TeachingMaterialSerializer(queryset, many=True, context={'request': request})
        return Response({'success': True, 'data': serializer.data})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = TeachingMaterialSerializer(instance, context={'request': request})
        return Response({'success': True, 'data': serializer.data})

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.pdf_file:
            try:
                # Use storage backend delete — works with both local disk and S3
                instance.pdf_file.delete(save=False)
            except Exception:
                pass
        instance.delete()
        return Response({'success': True, 'data': {'detail': 'Material deleted.'}})

    @action(detail=True, methods=['post'], url_path='reprocess')
    def reprocess(self, request, pk=None):
        """POST /api/materials/{id}/reprocess/ — Re-trigger text extraction."""
        material = self.get_object()
        if not material.pdf_file:
            return Response(
                {'success': False, 'errors': {'detail': 'No PDF file attached to this material.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if _S3_CONFIGURED:
            material.status = 'pending'
            material.error_message = ''
            material.save(update_fields=['status', 'error_message', 'updated_at'])
            _mid = material.id
            transaction.on_commit(lambda: extract_pdf_text.delay(_mid))
        else:
            _run_extraction(material)

        serializer = TeachingMaterialSerializer(material, context={'request': request})
        return Response({
            'success': True,
            'data': {
                'detail': 'Reprocessing complete.' if not _S3_CONFIGURED else 'Reprocessing started.',
                'material': serializer.data,
            },
        })

    @action(detail=True, methods=['get'], url_path='preview')
    def preview(self, request, pk=None):
        """GET /api/materials/{id}/preview/ — Extracted text preview."""
        material = self.get_object()
        return Response({
            'success': True,
            'data': {
                'id': material.id,
                'title': material.title,
                'status': material.status,
                'page_count': material.page_count,
                'character_count': len(material.extracted_text),
                'preview': material.extracted_text[:2000],
                'has_more': len(material.extracted_text) > 2000,
            },
        })

    @action(detail=True, methods=['get'], url_path='file')
    def file(self, request, pk=None):
        """GET /api/materials/{id}/file/ — Stream the uploaded PDF (teacher owner only)."""
        material = self.get_object()
        if not material.pdf_file:
            return Response(
                {'success': False, 'errors': {'detail': 'No PDF file attached to this material.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        filename = material.pdf_file.name.rsplit('/', 1)[-1] or f'{material.title}.pdf'
        response = FileResponse(
            material.pdf_file.open('rb'),
            content_type='application/pdf',
            as_attachment=False,
            filename=filename,
        )
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
