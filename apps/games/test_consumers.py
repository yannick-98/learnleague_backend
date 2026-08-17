import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.models import User
from apps.activities.models import Activity, Question
from apps.games.routing import websocket_urlpatterns
from apps.games.models import GameSession, Player

WS_APP = URLRouter(websocket_urlpatterns)


@pytest.fixture
def teacher(db):
    return User.objects.create_user(
        username='ws_teacher',
        email='ws_teacher@test.com',
        password='TestPass123',
        role='teacher',
    )


@pytest.fixture
def activity(db, teacher):
    act = Activity.objects.create(
        title='WS Quiz', teacher=teacher, status='ready', time_per_question=30,
    )
    for i in range(3):
        Question.objects.create(
            activity=act, text=f'Q{i + 1}?',
            option_a='A', option_b='B', option_c='C', option_d='D',
            correct_option='B', difficulty='medium', order=i,
        )
    return act


@pytest.fixture
def session(db, activity, teacher):
    return GameSession.objects.create(
        activity=activity, teacher=teacher, status='waiting',
    )


@pytest.fixture
def player(db, session):
    return Player.objects.create(
        session=session, alias='Student1', avatar='🦊', is_active=False,
    )


@pytest.fixture
def teacher_access_token(teacher):
    return str(RefreshToken.for_user(teacher).access_token)


@pytest.fixture
def active_session(session):
    session.status = 'active'
    session.current_question_index = 1
    session.question_started_at = timezone.now()
    session.save()
    return session


@pytest.fixture
def first_question(activity):
    return activity.questions.order_by('order').first()


@database_sync_to_async
def _get_session_status(session_id):
    return GameSession.objects.values_list('status', flat=True).get(id=session_id)


@database_sync_to_async
def _get_player_stats(player_id):
    player = Player.objects.get(id=player_id)
    return player.score, player.correct_answers


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_teacher_connect_receives_connected(session, teacher_access_token):
    communicator = WebsocketCommunicator(
        WS_APP,
        f'/ws/game/{session.code}/?token={teacher_access_token}',
    )
    connected, _ = await communicator.connect()
    assert connected

    msg = await communicator.receive_json_from()
    assert msg['type'] == 'connected'
    assert msg['role'] == 'teacher'
    assert msg['session']['code'] == session.code

    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_student_connect_receives_game_state(session, player):
    communicator = WebsocketCommunicator(
        WS_APP,
        f'/ws/game/{session.code}/?player_token={player.player_token}',
    )
    connected, _ = await communicator.connect()
    assert connected

    msg = await communicator.receive_json_from()
    assert msg['type'] == 'game_state'
    assert msg['status'] == 'waiting'

    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_invalid_session_rejects_connection(teacher_access_token):
    communicator = WebsocketCommunicator(
        WS_APP,
        f'/ws/game/ZZZZZZ/?token={teacher_access_token}',
    )
    connected, _ = await communicator.connect()
    assert not connected


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_ping_pong(session, teacher_access_token):
    communicator = WebsocketCommunicator(
        WS_APP,
        f'/ws/game/{session.code}/?token={teacher_access_token}',
    )
    connected, _ = await communicator.connect()
    assert connected
    await communicator.receive_json_from()  # connected

    await communicator.send_json_to({'type': 'ping'})
    msg = await communicator.receive_json_from()
    assert msg['type'] == 'pong'

    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_teacher_start_game_broadcasts(session, teacher_access_token, player):
    teacher_comm = WebsocketCommunicator(
        WS_APP,
        f'/ws/game/{session.code}/?token={teacher_access_token}',
    )
    student_comm = WebsocketCommunicator(
        WS_APP,
        f'/ws/game/{session.code}/?player_token={player.player_token}',
    )

    connected, _ = await teacher_comm.connect()
    assert connected
    connected, _ = await student_comm.connect()
    assert connected

    await teacher_comm.receive_json_from()  # connected
    await student_comm.receive_json_from()  # game_state
    await student_comm.receive_json_from()  # player_joined

    await teacher_comm.send_json_to({'type': 'teacher_start_game'})

    teacher_msgs = []
    student_msgs = []
    for _ in range(3):
        teacher_msgs.append(await teacher_comm.receive_json_from())
    for _ in range(2):
        student_msgs.append(await student_comm.receive_json_from())

    types_teacher = {m['type'] for m in teacher_msgs}
    types_student = {m['type'] for m in student_msgs}
    assert 'game_started' in types_teacher
    assert 'question_data' in types_teacher
    assert 'game_started' in types_student
    assert 'question_data' in types_student

    # Students must not see the correct answer in question_data
    q_msg = next(m for m in student_msgs if m['type'] == 'question_data')
    assert 'correct_option' not in q_msg['question']

    assert await _get_session_status(session.id) == 'active'

    await teacher_comm.disconnect()
    await student_comm.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_student_answer_records_score(active_session, player, first_question):
    session = active_session
    question = first_question

    communicator = WebsocketCommunicator(
        WS_APP,
        f'/ws/game/{session.code}/?player_token={player.player_token}',
    )
    connected, _ = await communicator.connect()
    assert connected
    await communicator.receive_json_from()  # game_state
    await communicator.receive_json_from()  # player_joined

    await communicator.send_json_to({
        'type': 'student_answer',
        'question_id': question.id,
        'selected_option': question.correct_option,
    })

    msg = await communicator.receive_json_from()
    assert msg['type'] == 'answer_feedback'
    assert msg['is_correct'] is True
    assert msg['points'] > 0

    score, correct = await _get_player_stats(player.id)
    assert score > 0
    assert correct == 1

    await communicator.disconnect()
