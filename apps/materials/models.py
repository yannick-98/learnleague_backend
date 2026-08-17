from django.db import models


class TeachingMaterial(models.Model):
    STATUSES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    title = models.CharField(max_length=300)
    pdf_file = models.FileField(upload_to='materials/pdfs/', blank=True, max_length=500)
    extracted_text = models.TextField(blank=True)
    teacher = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='materials',
    )
    classroom = models.ForeignKey(
        'classes.ClassRoom',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='materials',
    )
    status = models.CharField(max_length=20, choices=STATUSES, default='pending')
    page_count = models.IntegerField(default=0)
    file_size = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Teaching Material'
        verbose_name_plural = 'Teaching Materials'

    def __str__(self):
        return f"{self.title} ({self.status})"

    @property
    def file_url(self):
        if self.pdf_file:
            return self.pdf_file.url
        return None

    @property
    def file_size_mb(self):
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return 0

    @property
    def text_preview(self):
        if self.extracted_text:
            return self.extracted_text[:500] + ('...' if len(self.extracted_text) > 500 else '')
        return ''
