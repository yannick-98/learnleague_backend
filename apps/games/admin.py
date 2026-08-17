from django.contrib import admin
from django.utils.html import format_html

from .models import GameSession, Player, Answer


class PlayerInline(admin.TabularInline):
    model = Player
    extra = 0
    fields = ['alias', 'avatar', 'score', 'correct_answers', 'total_answers', 'avg_response_time', 'is_active']
    readonly_fields = ['score', 'correct_answers', 'total_answers', 'avg_response_time']
    ordering = ['-score']
    show_change_link = True


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ['code', 'activity', 'teacher', 'status', 'player_count_display', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['code', 'activity__title', 'teacher__username']
    ordering = ['-created_at']
    raw_id_fields = ['activity', 'teacher', 'classroom']
    readonly_fields = ['code', 'created_at']
    inlines = [PlayerInline]

    @admin.display(description='Players')
    def player_count_display(self, obj):
        return obj.players.count()


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ['alias', 'session', 'score', 'correct_answers', 'total_answers', 'avg_response_time', 'is_active']
    list_filter = ['is_active', 'session__status']
    search_fields = ['alias', 'session__code']
    ordering = ['-score']
    raw_id_fields = ['session']
    readonly_fields = ['player_token', 'joined_at']


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['player', 'question_short', 'selected_option', 'is_correct', 'response_time', 'points']
    list_filter = ['is_correct', 'selected_option']
    search_fields = ['player__alias', 'player__session__code']
    raw_id_fields = ['player', 'question']

    @admin.display(description='Question')
    def question_short(self, obj):
        return obj.question.text[:60]
