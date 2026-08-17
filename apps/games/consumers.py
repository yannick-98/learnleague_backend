"""
GameConsumer — WebSocket consumer for real-time game sessions.

URL: ws://server/ws/game/{session_code}/?token={jwt}         (teacher)
     ws://server/ws/game/{session_code}/?player_token={uuid}  (student)

Message protocol (JSON objects with a "type" field):

Incoming (teacher):
  teacher_start_game     → broadcast game_started + first question_data
  teacher_end_question   → broadcast question_ended (reveal answer + ranking)
  teacher_next_question  → broadcast question_data with timer
  teacher_finish_game    → broadcast game_finished with ranking
  ping                   → respond with pong

Incoming (student):
  student_answer         → {question_id, selected_option, response_time}
  ping                   → respond with pong

Outgoing broadcasts:
  connected (teacher only), game_state (student on connect),
  game_started, question_data, question_ended,
  player_joined (with total_players), answer_feedback (to answering student),
  answer_progress (group, for teacher), ranking_update, game_finished, error, pong
"""
import json
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

logger = logging.getLogger(__name__)


class GameConsumer(AsyncWebsocketConsumer):

    # ------------------------------------------------------------------ #
    # Connection lifecycle                                                 #
    # ------------------------------------------------------------------ #

    async def connect(self):
        self.session_code = self.scope['url_route']['kwargs']['session_code'].upper()
        self.group_name = f'game_{self.session_code}'
        self.role = None
        self.user = None
        self.player = None

        # Validate session first
        session = await self._get_session(self.session_code)
        if session is None:
            await self.close(code=4004)
            return

        # Parse query parameters
        query_string = self.scope.get('query_string', b'').decode()
        params = parse_qs(query_string)

        jwt_token = (params.get('token') or [None])[0]
        player_token = (params.get('player_token') or [None])[0]

        if jwt_token:
            user = await self._get_user_from_jwt(jwt_token)
            if user is None:
                await self.close(code=4001)
                return
            # Validate teacher owns this session
            if not await self._check_teacher_owns_session(user.id, self.session_code):
                await self.close(code=4003)
                return
            self.user = user
            self.role = 'teacher'

        elif player_token:
            player = await self._get_player_from_token(player_token)
            if player is None:
                await self.close(code=4001)
                return
            # Validate player belongs to this session
            if player['session_code'] != self.session_code:
                await self.close(code=4003)
                return
            self.player = player
            self.role = 'student'

        else:
            await self.close(code=4001)
            return

        self.session_id = session['id']

        # Join channel group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Post-connection tasks
        if self.role == 'teacher':
            await self._send_json({
                'type': 'connected',
                'role': 'teacher',
                'session': session,
            })
        else:
            # Register channel and mark player present in the lobby
            was_inactive = await self._connect_player(self.player['id'], self.channel_name)
            # Send current game state to reconnecting/late-joining student
            await self._send_json({
                'type': 'game_state',
                'status': session['status'],
                'current_question_index': session['current_question_index'],
                'total_questions': session['total_questions'],
                'time_per_question': session['time_per_question'],
            })
            # Announce only when player newly enters the lobby (not on duplicate WS tabs)
            if was_inactive:
                total_players = await self._get_player_count(self.session_id)
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'player_joined',
                        'player': {
                            'id': self.player['id'],
                            'alias': self.player['alias'],
                            'avatar': self.player['avatar'],
                        },
                        'total_players': total_players,
                    },
                )

    async def disconnect(self, close_code):
        try:
            if self.role == 'student' and self.player:
                await self._mark_player_inactive(self.player['id'])
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        except Exception as exc:
            logger.debug('Disconnect cleanup error: %s', exc)

    # ------------------------------------------------------------------ #
    # Receive / dispatch                                                   #
    # ------------------------------------------------------------------ #

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            await self._send_json({'type': 'error', 'message': 'Invalid JSON payload.'})
            return

        msg_type = data.get('type', '')

        if msg_type == 'ping':
            await self._send_json({'type': 'pong'})
            return

        if self.role == 'teacher':
            if msg_type == 'teacher_start_game':
                await self._handle_start_game()
            elif msg_type == 'teacher_end_question':
                await self._handle_end_question()
            elif msg_type == 'teacher_next_question':
                await self._handle_next_question()
            elif msg_type == 'teacher_finish_game':
                await self._handle_finish_game()
            else:
                await self._send_json({'type': 'error', 'message': f'Unknown teacher action: {msg_type}'})

        elif self.role == 'student':
            if msg_type == 'student_answer':
                await self._handle_student_answer(data)
            else:
                await self._send_json({'type': 'error', 'message': f'Unknown student action: {msg_type}'})

    # ------------------------------------------------------------------ #
    # Teacher handlers                                                     #
    # ------------------------------------------------------------------ #

    async def _handle_start_game(self):
        session = await self._db_start_game(self.session_id)
        if not session:
            await self._send_json({'type': 'error', 'message': 'Session could not be started.'})
            return

        await self.channel_layer.group_send(self.group_name, {
            'type': 'game_started',
            'session_code': self.session_code,
            'total_questions': session['total_questions'],
            'time_per_question': session['time_per_question'],
        })

        # Automatically send first question
        await self._handle_next_question()

    async def _handle_end_question(self):
        """Reveal correct answer for the current question and broadcast ranking."""
        result = await self._db_get_current_question_answer(self.session_id)
        if result is None:
            await self._send_json({'type': 'error', 'message': 'No active question to reveal.'})
            return

        top_ranking = await self._db_get_top_ranking(self.session_id, limit=5)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'question_ended',
            'correct_option': result['correct_option'],
            'explanation': result['explanation'],
            'ranking': top_ranking,
        })

    async def _handle_next_question(self):
        result = await self._db_next_question(self.session_id)
        if result is None:
            await self._send_json({'type': 'error', 'message': 'No more questions or session not active.'})
            return

        await self.channel_layer.group_send(self.group_name, {
            'type': 'question_data',
            **result,
        })

    async def _handle_finish_game(self):
        ranking = await self._db_finish_game(self.session_id)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'game_finished',
            'ranking': ranking,
        })

    # ------------------------------------------------------------------ #
    # Student handlers                                                     #
    # ------------------------------------------------------------------ #

    async def _handle_student_answer(self, data):
        if not self.player:
            return

        question_id = data.get('question_id')
        selected_option = str(data.get('selected_option', '')).upper()

        if selected_option not in ('A', 'B', 'C', 'D'):
            await self._send_json({'type': 'error', 'message': 'Invalid option. Must be A, B, C, or D.'})
            return

        # response_time is computed server-side — client value is ignored
        result = await self._db_save_answer(
            player_id=self.player['id'],
            question_id=question_id,
            selected_option=selected_option,
        )

        if result is None:
            # Already answered or question not found — send silent ack
            await self._send_json({'type': 'error', 'message': 'Answer already submitted or invalid question.'})
            return

        # Confirm result to the answering student
        await self._send_json({
            'type': 'answer_feedback',
            'is_correct': result['is_correct'],
            'correct_option': result['correct_option'],
            'points': result['points'],
            'explanation': result['explanation'],
            'total_score': result['total_score'],
        })

        # Notify all (teacher) of answer progress
        total_answered = await self._db_get_answer_count(self.session_id, question_id)
        total_players = await self._get_player_count(self.session_id)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'answer_progress',
            'total_answered': total_answered,
            'total_players': total_players,
        })

        # Broadcast top-5 ranking update to everyone
        top_ranking = await self._db_get_top_ranking(self.session_id, limit=5)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'ranking_update',
            'ranking': top_ranking,
        })

        # Auto-reveal when all active players have answered
        if total_players > 0 and total_answered >= total_players:
            await self._handle_end_question()

    # ------------------------------------------------------------------ #
    # Group message handlers (called by channel_layer.group_send)         #
    # ------------------------------------------------------------------ #

    async def game_started(self, event):
        await self._send_json({
            'type': 'game_started',
            'session_code': event['session_code'],
            'total_questions': event['total_questions'],
            'time_per_question': event['time_per_question'],
        })

    async def question_data(self, event):
        payload = {
            'type': 'question_data',
            'question_index': event['question_index'],
            'total_questions': event['total_questions'],
            'question': event['question'].copy(),
            'time_limit': event.get('time_limit', 30),
        }
        # Strip correct answer for students
        if self.role == 'student':
            payload['question'].pop('correct_option', None)
            payload['question'].pop('explanation', None)
        await self._send_json(payload)

    async def question_ended(self, event):
        await self._send_json({
            'type': 'question_ended',
            'correct_option': event['correct_option'],
            'explanation': event['explanation'],
            'ranking': event['ranking'],
        })

    async def player_joined(self, event):
        await self._send_json({
            'type': 'player_joined',
            'player': event['player'],
            'total_players': event['total_players'],
        })

    async def answer_progress(self, event):
        await self._send_json({
            'type': 'answer_progress',
            'total_answered': event['total_answered'],
            'total_players': event['total_players'],
        })

    async def ranking_update(self, event):
        await self._send_json({
            'type': 'ranking_update',
            'ranking': event['ranking'],
        })

    async def game_finished(self, event):
        await self._send_json({
            'type': 'game_finished',
            'ranking': event['ranking'],
        })

    # ------------------------------------------------------------------ #
    # Database helpers (wrapped with database_sync_to_async)             #
    # ------------------------------------------------------------------ #

    @database_sync_to_async
    def _get_user_from_jwt(self, token_str: str):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from apps.accounts.models import User
            token = AccessToken(token_str)
            return User.objects.get(id=token['user_id'])
        except Exception:
            return None

    @database_sync_to_async
    def _check_teacher_owns_session(self, user_id: int, session_code: str) -> bool:
        from apps.games.models import GameSession
        return GameSession.objects.filter(code=session_code, teacher_id=user_id).exists()

    @database_sync_to_async
    def _get_player_from_token(self, player_token: str):
        from apps.games.models import Player
        from django.core.exceptions import ValidationError
        try:
            p = Player.objects.select_related('session').get(player_token=player_token)
            return {
                'id': p.id,
                'alias': p.alias,
                'avatar': p.avatar,
                'session_code': p.session.code,
            }
        except (Player.DoesNotExist, ValidationError, ValueError):
            return None

    @database_sync_to_async
    def _get_session(self, code: str):
        from apps.games.models import GameSession
        try:
            s = GameSession.objects.select_related('activity').get(code=code)
            return {
                'id': s.id,
                'code': s.code,
                'status': s.status,
                'current_question_index': s.current_question_index,
                'total_questions': s.activity.questions.count(),
                'time_per_question': s.activity.time_per_question,
            }
        except GameSession.DoesNotExist:
            return None

    @database_sync_to_async
    def _get_player_count(self, session_id: int) -> int:
        from apps.games.models import Player
        return Player.objects.filter(session_id=session_id, is_active=True).count()

    @database_sync_to_async
    def _db_start_game(self, session_id: int):
        from apps.games.models import GameSession
        try:
            session = GameSession.objects.select_related('activity').get(id=session_id)
            if session.status != 'waiting':
                return None
            session.status = 'active'
            session.started_at = timezone.now()
            session.save(update_fields=['status', 'started_at'])
            return {
                'total_questions': session.activity.questions.count(),
                'time_per_question': session.activity.time_per_question,
            }
        except GameSession.DoesNotExist:
            return None

    @database_sync_to_async
    def _db_get_current_question_answer(self, session_id: int):
        """Return the correct answer for the most recently sent question."""
        from apps.games.models import GameSession
        try:
            session = GameSession.objects.select_related('activity').get(id=session_id)
            if session.status != 'active':
                return None
            questions = list(session.activity.questions.order_by('order', 'created_at'))
            # current_question_index points to the NEXT question; the current one is at idx-1
            current_idx = session.current_question_index - 1
            if current_idx < 0 or current_idx >= len(questions):
                return None
            question = questions[current_idx]
            return {
                'correct_option': question.correct_option,
                'explanation': question.explanation,
            }
        except GameSession.DoesNotExist:
            return None

    @database_sync_to_async
    def _db_next_question(self, session_id: int):
        from apps.games.models import GameSession
        try:
            session = GameSession.objects.select_related('activity').get(id=session_id)
            if session.status != 'active':
                return None

            questions = list(session.activity.questions.order_by('order', 'created_at'))
            current_idx = session.current_question_index

            if current_idx >= len(questions):
                return None

            question = questions[current_idx]
            session.current_question_index = current_idx + 1
            session.question_started_at = timezone.now()
            session.save(update_fields=['current_question_index', 'question_started_at'])

            return {
                'question_index': current_idx,
                'total_questions': len(questions),
                'time_limit': session.activity.time_per_question,
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
                    'topic': question.topic,
                },
            }
        except GameSession.DoesNotExist:
            return None

    @database_sync_to_async
    def _db_finish_game(self, session_id: int) -> list:
        from apps.games.models import GameSession
        try:
            session = GameSession.objects.get(id=session_id)
            if session.status != 'finished':
                session.status = 'finished'
                session.finished_at = timezone.now()
                session.save(update_fields=['status', 'finished_at'])
                session.activity.status = 'played'
                session.activity.save(update_fields=['status'])
        except GameSession.DoesNotExist:
            return []

        players = list(session.players.order_by('-score', 'avg_response_time'))
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

    @database_sync_to_async
    def _db_save_answer(
        self,
        player_id: int,
        question_id: int,
        selected_option: str,
    ):
        from apps.games.models import Player, Answer

        try:
            player = Player.objects.select_related('session__activity').get(id=player_id)
        except Player.DoesNotExist:
            return None

        session = player.session

        # Session must be actively running
        if session.status != 'active':
            return None

        # Validate that the submitted question is the CURRENT question in the session.
        # current_question_index points to the NEXT question, so current = index - 1.
        questions = list(session.activity.questions.order_by('order', 'created_at'))
        current_idx = session.current_question_index - 1
        if current_idx < 0 or current_idx >= len(questions):
            return None  # No active question right now

        current_question = questions[current_idx]
        if current_question.id != question_id:
            return None  # Client sent a stale or forged question ID

        question = current_question

        # Idempotency: ignore duplicate answers
        if Answer.objects.filter(player=player, question=question).exists():
            return None

        # Server-side response time — the client value is never trusted.
        time_limit = float(session.activity.time_per_question)
        if session.question_started_at:
            elapsed = (timezone.now() - session.question_started_at).total_seconds()
            response_time = min(max(0.0, elapsed), time_limit)
        else:
            response_time = time_limit  # Conservative fallback

        is_correct = selected_option == question.correct_option

        # Points: 100 base + up to 50 speed bonus for correct answers
        points = 0
        if is_correct:
            speed_ratio = max(0.0, 1.0 - (response_time / max(time_limit, 1.0)))
            points = 100 + int(50 * speed_ratio)

        Answer.objects.create(
            player=player,
            question=question,
            selected_option=selected_option,
            is_correct=is_correct,
            response_time=response_time,
            points=points,
        )

        player.update_stats(is_correct, response_time, points)

        return {
            'is_correct': is_correct,
            'correct_option': question.correct_option,
            'explanation': question.explanation,
            'points': points,
            'total_score': player.score,
        }

    @database_sync_to_async
    def _db_get_answer_count(self, session_id: int, question_id: int) -> int:
        from apps.games.models import Answer
        return Answer.objects.filter(
            player__session_id=session_id,
            question_id=question_id,
        ).count()

    @database_sync_to_async
    def _db_get_top_ranking(self, session_id: int, limit: int = 5) -> list:
        from apps.games.models import Player
        players = Player.objects.filter(
            session_id=session_id
        ).order_by('-score', 'avg_response_time')[:limit]
        return [
            {
                'position': idx + 1,
                'alias': p.alias,
                'avatar': p.avatar,
                'score': p.score,
            }
            for idx, p in enumerate(players)
        ]

    @database_sync_to_async
    def _connect_player(self, player_id: int, channel_name: str) -> bool:
        """Mark player active; return True if they were not already in the lobby."""
        from apps.games.models import Player
        player = Player.objects.get(id=player_id)
        was_inactive = not player.is_active
        player.is_active = True
        player.channel_name = channel_name
        player.save(update_fields=['is_active', 'channel_name'])
        return was_inactive

    @database_sync_to_async
    def _mark_player_inactive(self, player_id: int):
        from apps.games.models import Player
        Player.objects.filter(id=player_id).update(is_active=False)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    async def _send_json(self, data: dict):
        try:
            await self.send(text_data=json.dumps(data, default=str))
        except Exception as exc:
            logger.warning('Failed to send WebSocket message: %s', exc)
