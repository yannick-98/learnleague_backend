import csv
import io
import json
from collections import Counter, defaultdict

from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.http import HttpResponse
from apps.accounts.permissions import IsTeacher
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.games.models import GameSession, Player, Answer


def compute_session_analytics(session: GameSession) -> dict:
    """Compute comprehensive analytics for a single game session."""
    activity = session.activity
    questions = list(activity.questions.order_by('order', 'created_at'))
    players = list(session.players.order_by('-score', 'avg_response_time'))
    all_answers = Answer.objects.filter(player__session=session).select_related(
        'player', 'question'
    )

    # ── Summary ────────────────────────────────────────────────────────── #
    total_players = len(players)
    active_players = sum(1 for p in players if p.is_active)
    scores = [p.score for p in players] if players else [0]
    accuracies = [
        (p.correct_answers / p.total_answers * 100) if p.total_answers else 0
        for p in players
    ]
    response_times = [a.response_time for a in all_answers]

    summary = {
        'total_players': total_players,
        'active_players': active_players,
        'avg_score': round(sum(scores) / max(total_players, 1), 1),
        'max_score': max(scores) if scores else 0,
        'min_score': min(scores) if scores else 0,
        'avg_accuracy': round(sum(accuracies) / max(total_players, 1), 1),
        'total_questions': len(questions),
        'total_answers': len(list(all_answers)),
        'avg_response_time': round(sum(response_times) / max(len(response_times), 1), 2),
        'completion_rate': round(
            len(list(all_answers)) / max(len(questions) * max(total_players, 1), 1) * 100, 1
        ),
    }

    # ── Ranking ────────────────────────────────────────────────────────── #
    ranking = [
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

    # ── Per-question analysis ───────────────────────────────────────────── #
    answers_by_question = defaultdict(list)
    for answer in all_answers:
        answers_by_question[answer.question_id].append(answer)

    questions_analysis = []
    for question in questions:
        q_answers = answers_by_question.get(question.id, [])
        total = len(q_answers)
        correct = sum(1 for a in q_answers if a.is_correct)
        times = [a.response_time for a in q_answers]
        option_dist = Counter(a.selected_option for a in q_answers)
        most_chosen = option_dist.most_common(1)[0][0] if option_dist else None

        questions_analysis.append({
            'question_id': question.id,
            'text': question.text,
            'difficulty': question.difficulty,
            'topic': question.topic,
            'correct_option': question.correct_option,
            'correct_percentage': round(correct / max(total, 1) * 100, 1),
            'avg_response_time': round(sum(times) / max(len(times), 1), 2),
            'most_chosen_option': most_chosen,
            'options_distribution': {
                'A': option_dist.get('A', 0),
                'B': option_dist.get('B', 0),
                'C': option_dist.get('C', 0),
                'D': option_dist.get('D', 0),
            },
            'total_answers': total,
        })

    # ── Per-player detailed reports ─────────────────────────────────────── #
    answers_by_player = defaultdict(list)
    for answer in all_answers:
        answers_by_player[answer.player_id].append(answer)

    player_reports = []
    for idx, player in enumerate(players):
        p_answers = answers_by_player.get(player.id, [])
        times = [a.response_time for a in p_answers]

        # Topic performance
        correct_by_topic = defaultdict(int)
        total_by_topic = defaultdict(int)
        for ans in p_answers:
            topic = ans.question.topic or 'General'
            total_by_topic[topic] += 1
            if ans.is_correct:
                correct_by_topic[topic] += 1

        topic_accuracy = {
            t: correct_by_topic[t] / total_by_topic[t]
            for t in total_by_topic
            if total_by_topic[t] > 0
        }
        strongest_topic = max(topic_accuracy, key=topic_accuracy.get) if topic_accuracy else None
        weakest_topic = min(topic_accuracy, key=topic_accuracy.get) if topic_accuracy else None

        player_reports.append({
            'position': idx + 1,
            'player_id': player.id,
            'alias': player.alias,
            'avatar': player.avatar,
            'score': player.score,
            'correct_answers': player.correct_answers,
            'total_answers': player.total_answers,
            'accuracy': round(
                (player.correct_answers / player.total_answers * 100) if player.total_answers else 0, 1
            ),
            'avg_response_time': round(player.avg_response_time, 2),
            'fastest_answer_time': round(min(times), 2) if times else None,
            'slowest_answer_time': round(max(times), 2) if times else None,
            'strongest_topic': strongest_topic,
            'weakest_topic': weakest_topic,
        })

    # ── Recommendations ─────────────────────────────────────────────────── #
    recommendations = _generate_recommendations(questions_analysis, summary)

    return {
        'session_id': session.id,
        'session_code': session.code,
        'activity_title': activity.title,
        'status': session.status,
        'started_at': session.started_at,
        'finished_at': session.finished_at,
        'summary': summary,
        'ranking': ranking,
        'questions_analysis': questions_analysis,
        'recommendations': recommendations,
        'player_reports': player_reports,
    }


def _generate_recommendations(questions_analysis: list, summary: dict) -> list[str]:
    """Generate up to 5 actionable recommendations from analytics data."""
    recs = []

    if not questions_analysis:
        return ['No questions were answered in this session.']

    avg_accuracy = summary.get('avg_accuracy', 0)
    avg_rt = summary.get('avg_response_time', 0)

    # Accuracy-based
    if avg_accuracy < 40:
        recs.append(
            'The class struggled overall (average accuracy below 40%). Consider revisiting '
            'the foundational concepts before the next session.'
        )
    elif avg_accuracy >= 80:
        recs.append(
            'Excellent class performance (average accuracy above 80%). '
            'Consider introducing more advanced questions in the next session.'
        )

    # Difficult questions
    hard_questions = [q for q in questions_analysis if q['correct_percentage'] < 30]
    if hard_questions:
        topics = ', '.join(
            f'"{q["topic"] or q["text"][:40]}"' for q in hard_questions[:3]
        )
        recs.append(
            f'{len(hard_questions)} question(s) had a correct rate below 30%: {topics}. '
            'Dedicate class time to review these topics.'
        )

    # Easy questions (potential ceiling)
    easy_questions = [q for q in questions_analysis if q['correct_percentage'] > 90]
    if easy_questions and len(easy_questions) > len(questions_analysis) * 0.6:
        recs.append(
            'More than 60% of questions were answered correctly by almost everyone. '
            'Increase difficulty to better challenge the class.'
        )

    # Response time
    if avg_rt > 20:
        recs.append(
            f'Average response time was {avg_rt:.1f}s, which is high. '
            'Consider reviewing time-management strategies and simplifying question wording.'
        )

    # Participation
    completion = summary.get('completion_rate', 100)
    if completion < 80:
        recs.append(
            f'Only {completion:.0f}% of expected answers were submitted. '
            'Ensure all students have a stable connection and understand the process.'
        )

    if not recs:
        recs.append('Good session! Keep up the engaging learning style.')

    return recs[:5]


def compute_classroom_analytics(classroom) -> dict:
    """Aggregate analytics for all finished sessions in a classroom."""
    from apps.activities.models import Activity
    from apps.materials.models import TeachingMaterial

    sessions = GameSession.objects.filter(
        classroom=classroom,
        teacher=classroom.teacher,
    ).select_related('activity')
    finished_sessions = sessions.filter(status='finished')

    total_answers = Answer.objects.filter(
        player__session__classroom=classroom,
        player__session__teacher=classroom.teacher,
    )
    correct_count = total_answers.filter(is_correct=True).count()
    answer_count = total_answers.count()

    session_summaries = []
    for session in finished_sessions.order_by('-finished_at')[:10]:
        players = session.players.count()
        session_answers = Answer.objects.filter(player__session=session)
        session_correct = session_answers.filter(is_correct=True).count()
        session_total = session_answers.count()
        session_summaries.append({
            'id': session.id,
            'code': session.code,
            'activity_title': session.activity.title,
            'player_count': players,
            'finished_at': session.finished_at,
            'accuracy': round(session_correct / max(session_total, 1) * 100, 1),
        })

    return {
        'classroom': {
            'id': classroom.id,
            'name': classroom.name,
            'subject': classroom.subject,
            'education_level': classroom.education_level,
        },
        'summary': {
            'total_activities': Activity.objects.filter(classroom=classroom).count(),
            'total_materials': TeachingMaterial.objects.filter(classroom=classroom).count(),
            'total_sessions': sessions.count(),
            'finished_sessions': finished_sessions.count(),
            'total_players': Player.objects.filter(session__classroom=classroom).count(),
            'overall_accuracy': round(correct_count / max(answer_count, 1) * 100, 1),
        },
        'recent_sessions': session_summaries,
    }


def compute_activity_analytics(activity) -> dict:
    """Aggregate analytics across all sessions for an activity."""
    sessions = activity.sessions.filter(teacher=activity.teacher).select_related('classroom')
    finished_sessions = sessions.filter(status='finished')

    session_history = []
    total_players = 0
    accuracies = []

    for session in finished_sessions.order_by('-finished_at'):
        players = session.players.count()
        total_players += players
        session_answers = Answer.objects.filter(player__session=session)
        session_correct = session_answers.filter(is_correct=True).count()
        session_total = session_answers.count()
        accuracy = round(session_correct / max(session_total, 1) * 100, 1)
        accuracies.append(accuracy)
        session_history.append({
            'id': session.id,
            'code': session.code,
            'classroom_name': session.classroom.name if session.classroom else None,
            'status': session.status,
            'player_count': players,
            'accuracy': accuracy,
            'finished_at': session.finished_at,
            'created_at': session.created_at,
        })

    return {
        'activity': {
            'id': activity.id,
            'title': activity.title,
            'status': activity.status,
            'question_count': activity.question_count,
        },
        'summary': {
            'total_sessions': sessions.count(),
            'finished_sessions': finished_sessions.count(),
            'total_players': total_players,
            'avg_players_per_session': round(
                total_players / max(finished_sessions.count(), 1), 1
            ),
            'avg_accuracy': round(sum(accuracies) / max(len(accuracies), 1), 1),
        },
        'session_history': session_history,
    }


def build_dashboard_payload(teacher) -> dict:
    """Build dashboard data dict for a teacher."""
    sessions = GameSession.objects.filter(teacher=teacher)
    finished_sessions = sessions.filter(status='finished')

    total_answers = Answer.objects.filter(player__session__teacher=teacher).count()
    correct_answers = Answer.objects.filter(
        player__session__teacher=teacher, is_correct=True
    ).count()

    from apps.activities.models import Activity
    activity_stats = (
        Activity.objects.filter(teacher=teacher)
        .annotate(
            session_count=Count('sessions'),
            question_count=Count('questions'),
        )
        .values('id', 'title', 'status', 'session_count', 'question_count')
        .order_by('-session_count')[:5]
    )

    recent_sessions = sessions.select_related('activity', 'classroom').order_by('-created_at')[:5]
    recent_data = [
        {
            'id': s.id,
            'code': s.code,
            'activity_title': s.activity.title,
            'classroom_name': s.classroom.name if s.classroom else None,
            'status': s.status,
            'player_count': s.player_count,
            'created_at': s.created_at,
        }
        for s in recent_sessions
    ]

    return {
        'stats': {
            'total_classrooms': teacher.classrooms.count(),
            'total_materials': teacher.materials.count(),
            'total_activities': teacher.activities.count(),
            'total_sessions': sessions.count(),
            'total_finished_sessions': finished_sessions.count(),
            'total_players': Player.objects.filter(session__teacher=teacher).count(),
            'total_answers': total_answers,
            'overall_accuracy': round(correct_answers / max(total_answers, 1) * 100, 1),
        },
        'recent_activities': list(activity_stats),
        'recent_sessions': recent_data,
    }


class GameAnalyticsView(APIView):
    """GET /api/analytics/session/{session_id}/ — Full session analytics."""
    permission_classes = [IsTeacher]

    def get(self, request, session_id):
        try:
            session = GameSession.objects.select_related(
                'activity', 'teacher'
            ).prefetch_related(
                'players',
                'players__answers',
                'players__answers__question',
                'activity__questions',
            ).get(id=session_id, teacher=request.user)
        except GameSession.DoesNotExist:
            return Response(
                {'success': False, 'errors': {'detail': 'Session not found.'}},
                status=404,
            )

        data = compute_session_analytics(session)
        return Response({'success': True, 'data': data})


class GameAnalyticsExportView(APIView):
    """GET /api/analytics/session/{session_id}/export/ — Export analytics as CSV."""
    permission_classes = [IsTeacher]

    def get(self, request, session_id):
        try:
            session = GameSession.objects.select_related('activity').get(
                id=session_id, teacher=request.user
            )
        except GameSession.DoesNotExist:
            return Response(
                {'success': False, 'errors': {'detail': 'Session not found.'}},
                status=404,
            )

        data = compute_session_analytics(session)
        output = io.StringIO()
        writer = csv.writer(output)

        # Summary section
        writer.writerow(['=== SESSION SUMMARY ==='])
        writer.writerow(['Metric', 'Value'])
        for key, value in data['summary'].items():
            writer.writerow([key.replace('_', ' ').title(), value])

        writer.writerow([])
        writer.writerow(['=== PLAYER RANKING ==='])
        writer.writerow(['Position', 'Alias', 'Score', 'Correct', 'Total', 'Accuracy (%)', 'Avg Response Time (s)'])
        for p in data['ranking']:
            writer.writerow([
                p['position'], p['alias'], p['score'],
                p['correct_answers'], p['total_answers'],
                p['accuracy'], p['avg_response_time'],
            ])

        writer.writerow([])
        writer.writerow(['=== QUESTION ANALYSIS ==='])
        writer.writerow([
            'Question ID', 'Text', 'Difficulty', 'Topic',
            'Correct %', 'Avg Response Time (s)', 'Most Chosen', 'A', 'B', 'C', 'D',
        ])
        for q in data['questions_analysis']:
            dist = q['options_distribution']
            writer.writerow([
                q['question_id'], q['text'][:100], q['difficulty'], q['topic'],
                q['correct_percentage'], q['avg_response_time'], q['most_chosen_option'],
                dist.get('A', 0), dist.get('B', 0), dist.get('C', 0), dist.get('D', 0),
            ])

        writer.writerow([])
        writer.writerow(['=== RECOMMENDATIONS ==='])
        for rec in data['recommendations']:
            writer.writerow([rec])

        response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (
            f'attachment; filename="analytics_{session.code}.csv"'
        )
        return response


class TeacherDashboardView(APIView):
    """GET /api/analytics/dashboard/ — Overview statistics for the authenticated teacher."""
    permission_classes = [IsTeacher]

    def get(self, request):
        payload = build_dashboard_payload(request.user)
        return Response({'success': True, **payload})


class DashboardExportView(APIView):
    """GET /api/analytics/dashboard/export/ — Export dashboard data as JSON."""
    permission_classes = [IsTeacher]

    def get(self, request):
        payload = build_dashboard_payload(request.user)
        response = HttpResponse(
            json.dumps(payload, indent=2, default=str),
            content_type='application/json',
        )
        response['Content-Disposition'] = 'attachment; filename="dashboard.json"'
        return response


class ClassroomAnalyticsView(APIView):
    """GET /api/analytics/classroom/{classroom_id}/ — Analytics for a classroom."""
    permission_classes = [IsTeacher]

    def get(self, request, classroom_id):
        from apps.classes.models import ClassRoom
        try:
            classroom = ClassRoom.objects.get(id=classroom_id, teacher=request.user)
        except ClassRoom.DoesNotExist:
            return Response(
                {'success': False, 'errors': {'detail': 'Classroom not found.'}},
                status=404,
            )
        data = compute_classroom_analytics(classroom)
        return Response({'success': True, 'data': data})


class ActivityAnalyticsView(APIView):
    """GET /api/analytics/activity/{activity_id}/ — Analytics for an activity."""
    permission_classes = [IsTeacher]

    def get(self, request, activity_id):
        from apps.activities.models import Activity
        try:
            activity = Activity.objects.get(id=activity_id, teacher=request.user)
        except Activity.DoesNotExist:
            return Response(
                {'success': False, 'errors': {'detail': 'Activity not found.'}},
                status=404,
            )
        data = compute_activity_analytics(activity)
        return Response({'success': True, 'data': data})
