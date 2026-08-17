from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTeacher
from core.throttling import GameJoinRateThrottle

from .models import GameSession, Player, Answer
from .serializers import (
    GameSessionSerializer,
    GameSessionCreateSerializer,
    PlayerSerializer,
    RankingSerializer,
    PlayerJoinSerializer,
)


class GameSessionViewSet(viewsets.ModelViewSet):
    """
    CRUD for game sessions. Teachers only see their own sessions.

    Live game control (start, questions, finish) should use WebSocket.
    REST actions start/next_question/finish remain as fallback only.
    """
    permission_classes = [IsTeacher]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']
    def get_queryset(self):
        return GameSession.objects.filter(
            teacher=self.request.user
        ).select_related('activity', 'teacher', 'classroom')

    def get_serializer_class(self):
        return GameSessionSerializer

    def create(self, request, *args, **kwargs):
        serializer = GameSessionCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        session = serializer.save()
        output = GameSessionSerializer(session, context={'request': request})
        return Response({'success': True, 'data': output.data}, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = GameSessionSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = GameSessionSerializer(queryset, many=True, context={'request': request})
        return Response({'success': True, 'data': serializer.data})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = GameSessionSerializer(instance, context={'request': request})
        return Response({'success': True, 'data': serializer.data})

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({'success': True, 'data': {'detail': 'Session deleted.'}})

    @action(
        detail=False,
        methods=['get'],
        url_path='by_code/(?P<code>[A-Z0-9]{6})',
        permission_classes=[AllowAny],
        throttle_classes=[GameJoinRateThrottle],
    )
    def by_code(self, request, code=None):
        """GET /api/games/sessions/by_code/{code}/ — Public lookup by session code."""
        try:
            session = GameSession.objects.select_related(
                'activity', 'classroom'
            ).get(code=code)
        except GameSession.DoesNotExist:
            return Response(
                {'success': False, 'errors': {'detail': 'Session not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            'success': True,
            'data': {
                'id': session.id,
                'code': session.code,
                'status': session.status,
                'activity_title': session.activity.title,
                'classroom_name': session.classroom.name if session.classroom else None,
                'player_count': session.player_count,
            },
        })

    @action(detail=True, methods=['post'], url_path='start')
    def start(self, request, pk=None):
        """POST /api/games/sessions/{id}/start/ — Teacher starts the game."""
        session = self.get_object()
        if session.status != 'waiting':
            return Response(
                {'success': False, 'errors': {'detail': f'Cannot start a session in {session.status} state.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        session.status = 'active'
        session.started_at = timezone.now()
        session.save(update_fields=['status', 'started_at'])
        return Response({
            'success': True,
            'data': {
                'detail': 'Game started.',
                'session': GameSessionSerializer(session, context={'request': request}).data,
            },
        })

    @action(detail=True, methods=['post'], url_path='next_question')
    def next_question(self, request, pk=None):
        """POST /api/games/sessions/{id}/next_question/ — Advance to next question."""
        session = self.get_object()
        if session.status != 'active':
            return Response(
                {'success': False, 'errors': {'detail': 'Session is not active.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        questions = list(session.activity.questions.order_by('order', 'created_at'))
        current_idx = session.current_question_index

        if current_idx >= len(questions):
            return Response(
                {'success': False, 'errors': {'detail': 'No more questions.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        question = questions[current_idx]
        session.current_question_index = current_idx + 1
        session.question_started_at = timezone.now()
        session.save(update_fields=['current_question_index', 'question_started_at'])

        return Response({
            'success': True,
            'data': {
                'question_index': current_idx,
                'total_questions': len(questions),
                'question': {
                    'id': question.id,
                    'text': question.text,
                    'option_a': question.option_a,
                    'option_b': question.option_b,
                    'option_c': question.option_c,
                    'option_d': question.option_d,
                    'correct_option': question.correct_option,
                    'explanation': question.explanation,
                    'difficulty': question.difficulty,
                    'time_limit': session.activity.time_per_question,
                },
            },
        })

    @action(detail=True, methods=['post'], url_path='finish')
    def finish(self, request, pk=None):
        """POST /api/games/sessions/{id}/finish/ — Teacher ends the game."""
        session = self.get_object()
        if session.status == 'finished':
            return Response(
                {'success': False, 'errors': {'detail': 'Session already finished.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        session.status = 'finished'
        session.finished_at = timezone.now()
        session.save(update_fields=['status', 'finished_at'])

        # Mark activity as played
        session.activity.status = 'played'
        session.activity.save(update_fields=['status'])

        ranking = _build_ranking(session)
        return Response({
            'success': True,
            'data': {
                'detail': 'Game finished.',
                'ranking': ranking,
            },
        })

    @action(detail=True, methods=['get'], url_path='ranking')
    def ranking(self, request, pk=None):
        """GET /api/games/sessions/{id}/ranking/ — Final ranking."""
        session = self.get_object()
        ranking = _build_ranking(session)
        return Response({'success': True, 'data': {'ranking': ranking}})

    @action(detail=True, methods=['get'], url_path='players')
    def players(self, request, pk=None):
        """GET /api/games/sessions/{id}/players/ — List active players."""
        session = self.get_object()
        players_qs = session.players.filter(is_active=True).order_by('joined_at')
        serializer = PlayerSerializer(players_qs, many=True)
        return Response({'success': True, 'data': serializer.data})


class PlayerJoinView(APIView):
    """POST /api/games/join/{code}/ — Student joins session with alias + avatar."""
    permission_classes = [AllowAny]
    throttle_classes = [GameJoinRateThrottle]
    def post(self, request, code):
        try:
            session = GameSession.objects.get(code=code.upper())
        except GameSession.DoesNotExist:
            return Response(
                {'success': False, 'errors': {'detail': 'Session not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if session.status == 'finished':
            return Response(
                {'success': False, 'errors': {'detail': 'This session has already ended.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PlayerJoinSerializer(data=request.data, context={'session': session})
        serializer.is_valid(raise_exception=True)

        player = Player.objects.create(
            session=session,
            alias=serializer.validated_data['alias'],
            avatar=serializer.validated_data.get('avatar', '🦊'),
            is_active=False,
        )

        return Response({
            'success': True,
            'data': {
                'player_id': player.id,
                'player_token': str(player.player_token),
                'alias': player.alias,
                'avatar': player.avatar,
                'session_code': session.code,
                'websocket_url': f'/ws/game/{session.code}/',
            },
        }, status=status.HTTP_201_CREATED)


def _build_ranking(session: GameSession) -> list[dict]:
    """Build a full ranked list of players for a session."""
    players = list(
        session.players.order_by('-score', 'avg_response_time')
    )
    return [
        {
            'position': idx + 1,
            'id': p.id,
            'alias': p.alias,
            'avatar': p.avatar,
            'score': p.score,
            'correct_answers': p.correct_answers,
            'total_answers': p.total_answers,
            'avg_response_time': round(p.avg_response_time, 2),
            'accuracy': round(
                (p.correct_answers / p.total_answers * 100) if p.total_answers else 0, 1
            ),
        }
        for idx, p in enumerate(players)
    ]
