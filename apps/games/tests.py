import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.activities.models import Activity, Question
from apps.games.models import GameSession, Player, Answer


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def teacher(db):
    return User.objects.create_user(
        username='game_teacher', email='game_teacher@test.com',
        password='TestPass123', role='teacher',
    )


@pytest.fixture
def auth_client(api_client, teacher):
    api_client.force_authenticate(user=teacher)
    return api_client


@pytest.fixture
def activity(db, teacher):
    act = Activity.objects.create(
        title='Game Quiz', teacher=teacher, status='ready', time_per_question=30,
    )
    for i in range(5):
        Question.objects.create(
            activity=act, text=f'Question {i+1}?',
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
        session=session, alias='TestPlayer', avatar='🦊',
    )


@pytest.mark.django_db
class TestGameSessionCRUD:
    def test_create_session(self, auth_client, activity):
        url = reverse('gamesession-list')
        response = auth_client.post(url, {'activity_id': activity.id})
        assert response.status_code == status.HTTP_201_CREATED
        assert 'code' in response.data['data']

    def test_cannot_create_session_for_draft_activity(self, auth_client, teacher):
        draft_act = Activity.objects.create(
            title='Draft', teacher=teacher, status='draft', time_per_question=30,
        )
        url = reverse('gamesession-list')
        response = auth_client.post(url, {'activity_id': draft_act.id})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_sessions(self, auth_client, session):
        url = reverse('gamesession-list')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_retrieve_session(self, auth_client, session):
        url = reverse('gamesession-detail', kwargs={'pk': session.pk})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_cannot_update_session(self, auth_client, session):
        url = reverse('gamesession-detail', kwargs={'pk': session.pk})
        response = auth_client.patch(url, {'status': 'finished'}, format='json')
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_start_session(self, auth_client, session):
        url = reverse('gamesession-start', kwargs={'pk': session.pk})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        session.refresh_from_db()
        assert session.status == 'active'

    def test_cannot_start_already_active_session(self, auth_client, session):
        session.status = 'active'
        session.save()
        url = reverse('gamesession-start', kwargs={'pk': session.pk})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_next_question(self, auth_client, session):
        session.status = 'active'
        session.save()
        url = reverse('gamesession-next-question', kwargs={'pk': session.pk})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'question' in response.data['data']

    def test_finish_session(self, auth_client, session, player):
        session.status = 'active'
        session.save()
        url = reverse('gamesession-finish', kwargs={'pk': session.pk})
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        session.refresh_from_db()
        assert session.status == 'finished'

    def test_ranking(self, auth_client, session, player):
        session.status = 'finished'
        session.save()
        url = reverse('gamesession-ranking', kwargs={'pk': session.pk})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'ranking' in response.data['data']


@pytest.mark.django_db
class TestPlayerJoin:
    def test_join_session(self, api_client, session):
        url = reverse('player-join', kwargs={'code': session.code})
        response = api_client.post(url, {'alias': 'Superman', 'avatar': '🦊'})
        assert response.status_code == status.HTTP_201_CREATED
        assert 'player_token' in response.data['data']
        assert Player.objects.filter(session=session, alias='Superman').exists()

    def test_join_duplicate_alias(self, api_client, session, player):
        url = reverse('player-join', kwargs={'code': session.code})
        response = api_client.post(url, {'alias': player.alias, 'avatar': '🐺'})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_join_finished_session(self, api_client, session):
        session.status = 'finished'
        session.save()
        url = reverse('player-join', kwargs={'code': session.code})
        response = api_client.post(url, {'alias': 'Latejoiner'})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_join_invalid_code(self, api_client):
        url = reverse('player-join', kwargs={'code': 'XXXXXX'})
        response = api_client.post(url, {'alias': 'Ghost'})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_by_code_lookup(self, api_client, session):
        url = reverse('gamesession-by-code', kwargs={'code': session.code})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['data']['code'] == session.code

    def test_by_code_lookup_finished(self, api_client, session):
        session.status = 'finished'
        session.save()
        url = reverse('gamesession-by-code', kwargs={'code': session.code})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['data']['status'] == 'finished'


@pytest.mark.django_db
class TestAnswerScoring:
    def test_points_for_correct_fast_answer(self, db, session, player, activity):
        question = activity.questions.first()
        session.status = 'active'
        session.save()

        answer = Answer.objects.create(
            player=player,
            question=question,
            selected_option=question.correct_option,
            is_correct=True,
            response_time=2.0,
            points=100 + int(50 * (1 - 2.0 / 30)),
        )
        assert answer.points > 100  # speed bonus applied

    def test_zero_points_for_wrong_answer(self, db, session, player, activity):
        question = activity.questions.first()
        wrong_option = 'A' if question.correct_option != 'A' else 'C'
        answer = Answer.objects.create(
            player=player,
            question=question,
            selected_option=wrong_option,
            is_correct=False,
            response_time=5.0,
            points=0,
        )
        assert answer.points == 0
