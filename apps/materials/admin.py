from django.contrib import admin
from django.utils.html import format_html

from .models import TeachingMaterial


@admin.register(TeachingMaterial)
class TeachingMaterialAdmin(admin.ModelAdmin):
    list_display = ['title', 'teacher', 'classroom', 'status', 'page_count', 'file_size_mb_display', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'teacher__username', 'teacher__email']
    ordering = ['-created_at']
    raw_id_fields = ['teacher', 'classroom']
    readonly_fields = ['extracted_text', 'page_count', 'file_size', 'status', 'error_message', 'created_at', 'updated_at']

    actions = ['reprocess_materials']

    @admin.display(description='Size (MB)')
    def file_size_mb_display(self, obj):
        return f'{obj.file_size_mb} MB'

    @admin.action(description='Reprocess selected materials')
    def reprocess_materials(self, request, queryset):
        from .tasks import extract_pdf_text
        count = 0
        for material in queryset.exclude(status='processing'):
            material.status = 'pending'
            material.save(update_fields=['status'])
            extract_pdf_text.delay(material.id)
            count += 1
        self.message_user(request, f'{count} material(s) queued for reprocessing.')
