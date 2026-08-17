from rest_framework import status, viewsets
from rest_framework.decorators import action
from apps.accounts.permissions import IsTeacher
from rest_framework.response import Response

from .models import ClassRoom
from .serializers import ClassRoomSerializer, ClassRoomCreateSerializer


class ClassRoomViewSet(viewsets.ModelViewSet):
    """
    CRUD viewset for classrooms. Teachers only see their own classrooms.
    """
    permission_classes = [IsTeacher]

    def get_queryset(self):
        return ClassRoom.objects.filter(teacher=self.request.user).select_related('teacher')

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ClassRoomCreateSerializer
        return ClassRoomSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        classroom = serializer.save()
        output = ClassRoomSerializer(classroom, context={'request': request})
        return Response(
            {'success': True, 'data': output.data},
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ClassRoomSerializer(instance, context={'request': request})
        return Response({'success': True, 'data': serializer.data})

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ClassRoomSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = ClassRoomSerializer(queryset, many=True, context={'request': request})
        return Response({'success': True, 'data': serializer.data})

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = ClassRoomCreateSerializer(
            instance, data=request.data, partial=partial, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        classroom = serializer.save()
        output = ClassRoomSerializer(classroom, context={'request': request})
        return Response({'success': True, 'data': output.data})

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({'success': True, 'data': {'detail': 'Classroom deleted successfully.'}})

    @action(detail=True, methods=['get'], url_path='stats')
    def stats(self, request, pk=None):
        """GET /api/classes/{id}/stats/ — Materials, activities, sessions counts."""
        classroom = self.get_object()
        return Response({
            'success': True,
            'data': {
                'classroom_id': classroom.id,
                'name': classroom.name,
                **classroom.get_stats(),
            },
        })

    @action(detail=True, methods=['get'], url_path='sessions')
    def sessions(self, request, pk=None):
        """GET /api/classes/{id}/sessions/ — All game sessions for this classroom."""
        from apps.games.models import GameSession
        from apps.games.serializers import GameSessionSerializer

        classroom = self.get_object()
        sessions = GameSession.objects.filter(classroom=classroom).select_related('activity', 'teacher')
        serializer = GameSessionSerializer(sessions, many=True, context={'request': request})
        return Response({'success': True, 'data': serializer.data})
