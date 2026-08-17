from django.contrib import admin

from .models import Activity, Question


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ['order', 'text', 'correct_option', 'difficulty', 'topic']
    ordering = ['order']
    show_change_link = True


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ['title', 'teacher', 'status', 'mode', 'time_per_question', 'question_count', 'created_at']
    list_filter = ['status', 'mode', 'created_at']
    search_fields = ['title', 'teacher__username', 'teacher__email']
    ordering = ['-created_at']
    raw_id_fields = ['teacher', 'classroom', 'material']
    inlines = [QuestionInline]

    @admin.display(description='Questions')
    def question_count(self, obj):
        return obj.questions.count()


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['activity', 'order', 'short_text', 'correct_option', 'difficulty', 'topic']
    list_filter = ['difficulty', 'correct_option']
    search_fields = ['text', 'activity__title', 'topic']
    ordering = ['activity', 'order']
    raw_id_fields = ['activity']

    @admin.display(description='Question')
    def short_text(self, obj):
        return obj.text[:80]
