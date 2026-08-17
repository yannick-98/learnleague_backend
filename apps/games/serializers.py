from rest_framework import serializers

from apps.activities.serializers import ActivitySerializer
from .models import GameSession, Player, Answer


class PlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ['id', 'alias', 'avatar', 'score', 'correct_answers', 'total_answers',
                  'avg_response_time', 'joined_at', 'is_active']
        read_only_fields = ['id', 'score', 'correct_answers', 'total_answers',
                            'avg_response_time', 'joined_at', 'is_active']


class RankingSerializer(serializers.ModelSerializer):
    position = serializers.SerializerMethodField()

    class Meta:
        model = Player
        fields = ['position', 'id', 'alias', 'avatar', 'score',
                  'correct_answers', 'total_answers', 'avg_response_time']

    def get_position(self, obj):
        # Position is injected by the view
        return getattr(obj, '_position', None)


class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ['id', 'player', 'question', 'selected_option',
                  'is_correct', 'response_time', 'points', 'created_at']
        read_only_fields = ['id', 'is_correct', 'points', 'created_at']


class GameSessionSerializer(serializers.ModelSerializer):
    activity_title = serializers.CharField(source='activity.title', read_only=True)
    activity_info = serializers.SerializerMethodField()
    player_count = serializers.IntegerField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    classroom_name = serializers.SerializerMethodField()

    class Meta:
        model = GameSession
        fields = [
            'id', 'code', 'status', 'status_display',
            'activity', 'activity_title', 'activity_info',
            'classroom', 'classroom_name', 'player_count',
            'current_question_index', 'question_started_at',
            'started_at', 'finished_at', 'created_at',
        ]
        read_only_fields = [
            'id', 'code', 'status', 'player_count',
            'current_question_index', 'question_started_at',
            'started_at', 'finished_at', 'created_at',
        ]

    def get_activity_info(self, obj):
        return {
            'id': obj.activity.id,
            'title': obj.activity.title,
            'question_count': obj.activity.questions.count(),
            'time_per_question': obj.activity.time_per_question,
            'mode': obj.activity.mode,
        }

    def get_classroom_name(self, obj):
        return obj.classroom.name if obj.classroom else None


class GameSessionCreateSerializer(serializers.Serializer):
    activity_id = serializers.IntegerField()

    def validate_activity_id(self, value):
        from apps.activities.models import Activity
        request = self.context['request']
        try:
            activity = Activity.objects.get(pk=value, teacher=request.user)
        except Activity.DoesNotExist:
            raise serializers.ValidationError('Activity not found or you do not own it.')
        if activity.status == 'draft' or not activity.questions.exists():
            raise serializers.ValidationError(
                'Activity must be ready (have questions) before creating a session.'
            )
        self._activity = activity
        return value

    def create(self, validated_data):
        return GameSession.objects.create(
            activity=self._activity,
            teacher=self.context['request'].user,
            classroom=self._activity.classroom,
        )


class PlayerJoinSerializer(serializers.Serializer):
    alias = serializers.CharField(max_length=50, min_length=2)
    avatar = serializers.CharField(max_length=10, required=False, default='🦊')

    def validate_alias(self, value):
        return value.strip()

    def validate(self, attrs):
        session = self.context.get('session')
        alias = attrs['alias']
        if session and Player.objects.filter(session=session, alias__iexact=alias).exists():
            raise serializers.ValidationError({'alias': 'This alias is already taken in this session.'})
        return attrs
