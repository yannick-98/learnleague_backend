import csv
import io
import json

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from apps.accounts.permissions import IsTeacher
from rest_framework.response import Response

from .ai_generator import generate_questions
from .models import Activity, Question
from .serializers import (
    ActivitySerializer,
    ActivityCreateSerializer,
    QuestionSerializer,
    QuestionCreateSerializer,
    AIGenerationRequestSerializer,
)


class ActivityViewSet(viewsets.ModelViewSet):
    """CRUD for activities. Teachers only see their own activities."""
    permission_classes = [IsTeacher]

    def get_queryset(self):
        qs = Activity.objects.filter(teacher=self.request.user).select_related(
            'teacher', 'classroom', 'material'
        ).prefetch_related('questions')
        classroom_id = self.request.query_params.get('classroom')
        if classroom_id:
            qs = qs.filter(classroom_id=classroom_id)
        activity_status = self.request.query_params.get('status')
        if activity_status:
            qs = qs.filter(status=activity_status)
        return qs

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ActivityCreateSerializer
        return ActivitySerializer

    def create(self, request, *args, **kwargs):
        serializer = ActivityCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        activity = serializer.save()
        output = ActivitySerializer(activity, context={'request': request})
        return Response({'success': True, 'data': output.data}, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ActivitySerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = ActivitySerializer(queryset, many=True, context={'request': request})
        return Response({'success': True, 'data': serializer.data})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ActivitySerializer(instance, context={'request': request})
        return Response({'success': True, 'data': serializer.data})

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = ActivityCreateSerializer(
            instance, data=request.data, partial=partial, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        activity = serializer.save()
        output = ActivitySerializer(activity, context={'request': request})
        return Response({'success': True, 'data': output.data})

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({'success': True, 'data': {'detail': 'Activity deleted.'}})

    @action(detail=True, methods=['post'], url_path='generate_questions')
    def generate_questions_view(self, request, pk=None):
        """POST /api/activities/{id}/generate_questions/ — AI question generation."""
        activity = self.get_object()
        serializer = AIGenerationRequestSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        from apps.materials.models import TeachingMaterial
        material = TeachingMaterial.objects.get(pk=serializer.validated_data['material_id'])
        num_questions = serializer.validated_data['num_questions']
        difficulty = serializer.validated_data['difficulty']

        try:
            classroom = activity.classroom
            generated = generate_questions(
                text=material.extracted_text,
                num_questions=num_questions,
                difficulty=difficulty,
                education_level=serializer.validated_data.get('education_level')
                or (classroom.education_level if classroom else None),
                subject=(classroom.subject if classroom else None),
                activity_title=activity.title,
                material_title=material.title,
            )
        except Exception as e:
            return Response(
                {'success': False, 'errors': {'detail': f'Question generation failed: {e}'}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Atomically delete old questions and insert new ones so a generation
        # failure never leaves the activity with zero questions.
        with transaction.atomic():
            activity.questions.all().delete()

            created_questions = []
            for i, q_data in enumerate(generated):
                q_data.pop('order', None)
                question = Question.objects.create(
                    activity=activity,
                    order=i,
                    **{k: v for k, v in q_data.items() if k in (
                        'text', 'option_a', 'option_b', 'option_c', 'option_d',
                        'correct_option', 'explanation', 'difficulty', 'topic', 'source',
                    )}
                )
                created_questions.append(question)

            if created_questions:
                activity.status = 'ready'
                activity.material = material
                activity.save(update_fields=['status', 'material', 'updated_at'])

        output = QuestionSerializer(created_questions, many=True)
        return Response({
            'success': True,
            'data': {
                'questions_created': len(created_questions),
                'activity_status': activity.status,
                'questions': output.data,
            },
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='duplicate')
    def duplicate(self, request, pk=None):
        """POST /api/activities/{id}/duplicate/ — Clone activity and its questions."""
        original = self.get_object()
        new_activity = Activity.objects.create(
            title=f'{original.title} (Copy)',
            description=original.description,
            teacher=request.user,
            classroom=original.classroom,
            material=original.material,
            mode=original.mode,
            status='draft',
            time_per_question=original.time_per_question,
        )
        for q in original.questions.all():
            Question.objects.create(
                activity=new_activity,
                text=q.text,
                option_a=q.option_a,
                option_b=q.option_b,
                option_c=q.option_c,
                option_d=q.option_d,
                correct_option=q.correct_option,
                explanation=q.explanation,
                difficulty=q.difficulty,
                topic=q.topic,
                source=q.source,
                order=q.order,
            )
        output = ActivitySerializer(new_activity, context={'request': request})
        return Response({'success': True, 'data': output.data}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='export')
    def export_json(self, request, pk=None):
        """GET /api/activities/{id}/export/ — Export activity as JSON."""
        activity = self.get_object()
        serializer = ActivitySerializer(activity, context={'request': request})
        response = HttpResponse(
            json.dumps(serializer.data, indent=2, default=str),
            content_type='application/json',
        )
        safe_title = activity.title[:50].replace(' ', '_')
        response['Content-Disposition'] = f'attachment; filename="{safe_title}.json"'
        return response

    @action(detail=True, methods=['get'], url_path='export_csv')
    def export_csv(self, request, pk=None):
        """GET /api/activities/{id}/export_csv/ — Export questions as CSV."""
        activity = self.get_object()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Order', 'Text', 'Option A', 'Option B', 'Option C', 'Option D',
            'Correct Option', 'Explanation', 'Difficulty', 'Topic',
        ])
        for q in activity.questions.all():
            writer.writerow([
                q.order, q.text, q.option_a, q.option_b, q.option_c, q.option_d,
                q.correct_option, q.explanation, q.difficulty, q.topic,
            ])
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        safe_title = activity.title[:50].replace(' ', '_')
        response['Content-Disposition'] = f'attachment; filename="{safe_title}.csv"'
        return response

    @action(detail=True, methods=['post'], url_path='mark_ready')
    def mark_ready(self, request, pk=None):
        """POST /api/activities/{id}/mark_ready/ — Mark activity ready if it has questions."""
        activity = self.get_object()
        if not activity.questions.exists():
            return Response(
                {'success': False, 'errors': {'detail': 'Add at least one question first.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        activity.mark_ready()
        output = ActivitySerializer(activity, context={'request': request})
        return Response({'success': True, 'data': output.data})

    @action(
        detail=True,
        methods=['post'],
        url_path='import_csv',
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_csv(self, request, pk=None):
        """POST /api/activities/{id}/import_csv/ — Import questions from CSV (same format as export)."""
        activity = self.get_object()
        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response(
                {'success': False, 'errors': {'file': 'CSV file is required.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            decoded = csv_file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return Response(
                {'success': False, 'errors': {'file': 'File must be UTF-8 encoded CSV.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reader = csv.DictReader(io.StringIO(decoded))
        required = {'Text', 'Option A', 'Option B', 'Option C', 'Option D', 'Correct Option'}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            return Response(
                {'success': False, 'errors': {'file': f'CSV must include columns: {", ".join(sorted(required))}'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        errors = []
        with transaction.atomic():
            activity.questions.all().delete()
            for i, row in enumerate(reader):
                q_data = {
                    'text': row.get('Text', '').strip(),
                    'option_a': row.get('Option A', '').strip(),
                    'option_b': row.get('Option B', '').strip(),
                    'option_c': row.get('Option C', '').strip(),
                    'option_d': row.get('Option D', '').strip(),
                    'correct_option': row.get('Correct Option', 'A').strip().upper(),
                    'explanation': row.get('Explanation', '').strip(),
                    'difficulty': row.get('Difficulty', 'medium').strip().lower() or 'medium',
                    'topic': row.get('Topic', '').strip(),
                    'order': int(row.get('Order', i) or i),
                }
                serializer = QuestionCreateSerializer(data=q_data)
                if serializer.is_valid():
                    question = serializer.save(activity=activity)
                    created.append(question)
                else:
                    errors.append({'row': i + 2, 'errors': serializer.errors})

            if created:
                activity.mark_ready()

        output = QuestionSerializer(created, many=True)
        return Response({
            'success': True,
            'data': {
                'imported': len(created),
                'errors': errors,
                'activity_status': activity.status,
                'questions': output.data,
            },
        })


class QuestionViewSet(viewsets.ModelViewSet):
    """
    CRUD for questions within an activity.
    Nested under: /api/activities/{activity_pk}/questions/
    """
    permission_classes = [IsTeacher]

    def get_queryset(self):
        return Question.objects.filter(
            activity__teacher=self.request.user,
            activity_id=self.kwargs.get('activity_pk'),
        )

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return QuestionCreateSerializer
        return QuestionSerializer

    def _get_activity(self):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(
            Activity,
            pk=self.kwargs.get('activity_pk'),
            teacher=self.request.user,
        )

    def create(self, request, *args, **kwargs):
        activity = self._get_activity()
        serializer = QuestionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.save(activity=activity)
        output = QuestionSerializer(question)
        return Response({'success': True, 'data': output.data}, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = QuestionSerializer(queryset, many=True)
        return Response({'success': True, 'data': serializer.data})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response({'success': True, 'data': QuestionSerializer(instance).data})

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = QuestionCreateSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        question = serializer.save()
        return Response({'success': True, 'data': QuestionSerializer(question).data})

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({'success': True, 'data': {'detail': 'Question deleted.'}})

    @action(detail=False, methods=['post'], url_path='bulk_create')
    def bulk_create(self, request, activity_pk=None):
        """POST /api/activities/{activity_pk}/questions/bulk_create/"""
        activity = self._get_activity()
        questions_data = request.data.get('questions', [])
        if not isinstance(questions_data, list):
            return Response(
                {'success': False, 'errors': {'questions': 'Must be a list.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        created = []
        errors = []
        for i, q_data in enumerate(questions_data):
            serializer = QuestionCreateSerializer(data=q_data)
            if serializer.is_valid():
                question = serializer.save(activity=activity, order=q_data.get('order', i))
                created.append(QuestionSerializer(question).data)
            else:
                errors.append({'index': i, 'errors': serializer.errors})

        return Response({
            'success': True,
            'data': {
                'created': len(created),
                'errors': errors,
                'questions': created,
            },
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request, activity_pk=None):
        """POST /api/activities/{activity_pk}/questions/reorder/ — Reorder questions."""
        activity = self._get_activity()
        order_data = request.data.get('order', [])
        # order_data: [{'id': 1, 'order': 0}, {'id': 2, 'order': 1}, ...]
        if not isinstance(order_data, list):
            return Response(
                {'success': False, 'errors': {'order': 'Must be a list of {id, order} objects.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        updated = 0
        for item in order_data:
            q_id = item.get('id')
            new_order = item.get('order')
            if q_id is not None and new_order is not None:
                Question.objects.filter(id=q_id, activity=activity).update(order=new_order)
                updated += 1

        return Response({'success': True, 'data': {'updated': updated}})
