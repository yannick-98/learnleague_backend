from django.db import models


EDUCATION_LEVELS = [
    ("primary", "Primaria"),
    ("secondary", "Secundaria (ESO)"),
    ("bachillerato", "Bachillerato"),
    ("fp", "Formación Profesional"),
    ("university", "Universidad"),
    ("professional", "Formación profesional"),
    ("other", "Otros"),
]

CLASS_COLORS = [
    "#6366f1", "#8b5cf6", "#ec4899", "#ef4444",
    "#f97316", "#eab308", "#22c55e", "#14b8a6",
    "#3b82f6", "#06b6d4",
]


class ClassRoom(models.Model):
    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=200)
    education_level = models.CharField(max_length=50, choices=EDUCATION_LEVELS)
    description = models.TextField(blank=True)
    teacher = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="classrooms",
    )
    color = models.CharField(max_length=7, default="#6366f1")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Classroom"
        verbose_name_plural = "Classrooms"

    def __str__(self):
        return f"{self.name} — {self.teacher.full_name}"

    @property
    def materials_count(self):
        return self.materials.count()

    @property
    def activities_count(self):
        return self.activities.count()

    @property
    def sessions_count(self):
        return self.gamesession_set.count()

    def get_stats(self):
        return {
            "materials_count": self.materials_count,
            "activities_count": self.activities_count,
            "sessions_count": self.sessions_count,
        }
