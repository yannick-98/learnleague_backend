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
        username='ana_teacher', email='ana_teacher@test.com',
        password='TestPass123', role='teacher',
    )


@pytest.fixture
def auth_client(api_client, teacher):
    api_client.force_authenticate(user=teacher)
    return api_client


@pytest.fixture
def finished_session(db, teacher):
    activity = Activity.objects.create(
        title='Analytics Quiz', teacher=teacher, status='played', time_per_question=30,
    )
    questions = []
    for i in range(3):
        q = Question.objects.create(
            activity=activity, text=f'Q{i+1}?',
            option_a='A', option_b='B', option_c='C', option_d='D',
            correct_option='B', difficulty='medium', topic=f'Topic {i+1}', order=i,
        )
        questions.append(q)

    from django.utils import timezone
    session = GameSession.objects.create(
        activity=activity, teacher=teacher,
        status='finished',
        started_at=timezone.now(),
        finished_at=timezone.now(),
    )

    # Add 3 players with answers
    for i in range(3):
        player = Player.objects.create(
            session=session,
            alias=f'Player{i+1}',
            avatar='🦊',
            score=100 * (3 - i),
            correct_answers=2,
            total_answers=3,
            avg_response_time=5.0 + i,
        )
        for j, q in enumerate(questions):
            Answer.objects.create(
                player=player, question=q,
                selected_option='B' if j < 2 else 'A',
                is_correct=(j < 2),
                response_time=5.0 + j,
                points=120 if j < 2 else 0,
            )

    return session


@pytest.mark.django_db
class TestGameAnalytics:
    def test_get_analytics(self, auth_client, finished_session):
        url = reverse('analytics-session', kwargs={'session_id': finished_session.id})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data['data']
        assert 'summary' in data
        assert 'ranking' in data
        assert 'questions_analysis' in data
        assert 'recommendations' in data
        assert 'player_reports' in data

    def test_analytics_summary_values(self, auth_client, finished_session):
        url = reverse('analytics-session', kwargs={'session_id': finished_session.id})
        response = auth_client.get(url)
        summary = response.data['data']['summary']
        assert summary['total_players'] == 3
        assert summary['total_questions'] == 3

    def test_analytics_ranking_order(self, auth_client, finished_session):
        url = reverse('analytics-session', kwargs={'session_id': finished_session.id})
        response = auth_client.get(url)
        ranking = response.data['data']['ranking']
        scores = [r['score'] for r in ranking]
        assert scores == sorted(scores, reverse=True)

    def test_analytics_questions_analysis(self, auth_client, finished_session):
        url = reverse('analytics-session', kwargs={'session_id': finished_session.id})
        response = auth_client.get(url)
        qa = response.data['data']['questions_analysis']
        assert len(qa) == 3
        for q in qa:
            assert 'correct_percentage' in q
            assert 'options_distribution' in q

    def test_export_csv(self, auth_client, finished_session):
        url = reverse('analytics-session-export', kwargs={'session_id': finished_session.id})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'text/csv' in response['Content-Type']
        assert b'PLAYER RANKING' in response.content

    def test_analytics_not_found(self, auth_client):
        url = reverse('analytics-session', kwargs={'session_id': 99999})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_access_other_teacher_analytics(self, api_client, finished_session):
        other = User.objects.create_user(
            username='intruder', email='intruder@test.com', password='TestPass123',
        )
        api_client.force_authenticate(user=other)
        url = reverse('analytics-session', kwargs={'session_id': finished_session.id})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestDashboard:
    def test_dashboard(self, auth_client, teacher, finished_session):
        url = reverse('analytics-dashboard')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert 'stats' in response.data
        assert 'recent_sessions' in response.data
        assert response.data['stats']['total_sessions'] >= 1

    def test_dashboard_unauthenticated(self, api_client):
        url = reverse('analytics-dashboard')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestExtendedAnalytics:
    def test_classroom_analytics(self, auth_client, teacher):
        from apps.classes.models import ClassRoom
        from apps.activities.models import Activity
        from apps.games.models import GameSession

        classroom = ClassRoom.objects.create(
            name='Math', subject='Mathematics', education_level='secondary', teacher=teacher,
        )
        activity = Activity.objects.create(
            title='Quiz', teacher=teacher, classroom=classroom, status='ready',
        )
        GameSession.objects.create(
            activity=activity, teacher=teacher, classroom=classroom, status='finished',
        )

        url = reverse('analytics-classroom', kwargs={'classroom_id': classroom.id})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data['data']
        assert data['classroom']['id'] == classroom.id
        assert data['summary']['finished_sessions'] >= 1

    def test_activity_analytics(self, auth_client, teacher, finished_session):
        url = reverse('analytics-activity', kwargs={'activity_id': finished_session.activity_id})
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data['data']
        assert data['activity']['id'] == finished_session.activity_id
        assert 'session_history' in data

    def test_dashboard_export_json(self, auth_client, teacher):
        url = reverse('analytics-dashboard-export')
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'application/json' in response['Content-Type']
