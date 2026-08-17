import random
import string
import uuid

from django.db import models


def generate_code():
    """Generate a unique 6-character uppercase alphanumeric game code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


AVATARS = ['🦊', '🐺', '🦁', '🐯', '🐻', '🐸', '🐧', '🦄', '🐲', '🦉']


class GameSession(models.Model):
    STATUSES = [
        ('waiting', 'Waiting'),
        ('active', 'Active'),
        ('finished', 'Finished'),
    ]

    activity = models.ForeignKey(
        'activities.Activity',
        on_delete=models.CASCADE,
        related_name='sessions',
    )
    teacher = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='sessions',
    )
    classroom = models.ForeignKey(
        'classes.ClassRoom',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gamesession_set',
    )
    code = models.CharField(max_length=6, unique=True, default=generate_code)
    status = models.CharField(max_length=20, choices=STATUSES, default='waiting')
    current_question_index = models.IntegerField(default=0)
    question_started_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Game Session'
        verbose_name_plural = 'Game Sessions'

    def __str__(self):
        return f"Session {self.code} — {self.activity.title} ({self.status})"

    @property
    def player_count(self):
        return self.players.filter(is_active=True).count()

    def get_ranking(self):
        return list(
            self.players.order_by('-score', 'avg_response_time')
            .values('id', 'alias', 'avatar', 'score', 'correct_answers', 'total_answers', 'avg_response_time')
        )


class Player(models.Model):
    session = models.ForeignKey(
        GameSession,
        on_delete=models.CASCADE,
        related_name='players',
    )
    alias = models.CharField(max_length=50)
    avatar = models.CharField(max_length=10, default='🦊')
    score = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)
    total_answers = models.IntegerField(default=0)
    avg_response_time = models.FloatField(default=0.0)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    channel_name = models.CharField(max_length=200, blank=True)
    player_token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)

    class Meta:
        ordering = ['-score', 'avg_response_time']
        unique_together = ['session', 'alias']
        verbose_name = 'Player'
        verbose_name_plural = 'Players'

    def __str__(self):
        return f"{self.alias} (session {self.session.code})"

    def update_stats(self, is_correct: bool, response_time: float, points: int):
        """Recalculate rolling average response time and update score/accuracy."""
        self.score += points
        self.total_answers += 1
        if is_correct:
            self.correct_answers += 1
        old_avg = self.avg_response_time
        self.avg_response_time = (
            (old_avg * (self.total_answers - 1) + response_time) / self.total_answers
        )
        self.save(update_fields=['score', 'total_answers', 'correct_answers', 'avg_response_time'])


class Answer(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey('activities.Question', on_delete=models.CASCADE, related_name='answers')
    selected_option = models.CharField(max_length=1)
    is_correct = models.BooleanField(default=False)
    response_time = models.FloatField()
    points = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['player', 'question']
        ordering = ['created_at']
        verbose_name = 'Answer'
        verbose_name_plural = 'Answers'

    def __str__(self):
        status = 'correct' if self.is_correct else 'wrong'
        return f"{self.player.alias} → {self.selected_option} ({status}, {self.points}pts)"
