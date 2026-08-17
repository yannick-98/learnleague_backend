from django.db import models


class Activity(models.Model):
    MODES = [('live_quiz', 'Live Quiz')]
    STATUSES = [('draft', 'Draft'), ('ready', 'Ready'), ('played', 'Played')]

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    teacher = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='activities',
    )
    classroom = models.ForeignKey(
        'classes.ClassRoom',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities',
    )
    material = models.ForeignKey(
        'materials.TeachingMaterial',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activities',
    )
    mode = models.CharField(max_length=20, choices=MODES, default='live_quiz')
    status = models.CharField(max_length=20, choices=STATUSES, default='draft')
    time_per_question = models.IntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Activity'
        verbose_name_plural = 'Activities'

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    @property
    def question_count(self):
        return self.questions.count()

    def mark_ready(self):
        if self.questions.exists():
            self.status = 'ready'
            self.save(update_fields=['status', 'updated_at'])


class Question(models.Model):
    DIFFICULTIES = [('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')]
    OPTION_CHOICES = [('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')]

    activity = models.ForeignKey(
        Activity,
        on_delete=models.CASCADE,
        related_name='questions',
    )
    text = models.TextField()
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    correct_option = models.CharField(max_length=1, choices=OPTION_CHOICES)
    explanation = models.TextField(blank=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTIES, default='medium')
    topic = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=300, blank=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = 'Question'
        verbose_name_plural = 'Questions'

    def __str__(self):
        return f"Q{self.order}: {self.text[:80]}"
