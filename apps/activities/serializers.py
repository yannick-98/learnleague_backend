from rest_framework import serializers

from .models import Activity, Question


class QuestionSerializer(serializers.ModelSerializer):
    difficulty_display = serializers.CharField(source='get_difficulty_display', read_only=True)
    correct_option_display = serializers.CharField(source='get_correct_option_display', read_only=True)

    class Meta:
        model = Question
        fields = [
            'id', 'activity', 'text',
            'option_a', 'option_b', 'option_c', 'option_d',
            'correct_option', 'correct_option_display',
            'explanation', 'difficulty', 'difficulty_display',
            'topic', 'source', 'order', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class QuestionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = [
            'id', 'text', 'option_a', 'option_b', 'option_c', 'option_d',
            'correct_option', 'explanation', 'difficulty', 'topic', 'source', 'order',
        ]
        read_only_fields = ['id']

    def validate_correct_option(self, value):
        if value.upper() not in ('A', 'B', 'C', 'D'):
            raise serializers.ValidationError("Must be one of: A, B, C, D.")
        return value.upper()


class ActivitySerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    question_count = serializers.SerializerMethodField()

    def get_question_count(self, obj):
        return obj.questions.count()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    mode_display = serializers.CharField(source='get_mode_display', read_only=True)
    classroom_name = serializers.SerializerMethodField()
    material_title = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = [
            'id', 'title', 'description', 'mode', 'mode_display',
            'status', 'status_display', 'time_per_question',
            'classroom', 'classroom_name', 'material', 'material_title',
            'question_count', 'questions', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_classroom_name(self, obj):
        return obj.classroom.name if obj.classroom else None

    def get_material_title(self, obj):
        return obj.material.title if obj.material else None


class ActivityCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = [
            'id', 'title', 'description', 'mode',
            'time_per_question', 'classroom', 'material', 'status',
        ]
        read_only_fields = ['id']

    def validate_classroom(self, value):
        if value and value.teacher != self.context['request'].user:
            raise serializers.ValidationError('You do not own this classroom.')
        return value

    def validate_material(self, value):
        if value and value.teacher != self.context['request'].user:
            raise serializers.ValidationError('You do not own this material.')
        return value

    def validate_time_per_question(self, value):
        if value < 5 or value > 300:
            raise serializers.ValidationError('Time per question must be between 5 and 300 seconds.')
        return value

    def create(self, validated_data):
        validated_data['teacher'] = self.context['request'].user
        return super().create(validated_data)


class AIGenerationRequestSerializer(serializers.Serializer):
    material_id = serializers.IntegerField(required=True)
    num_questions = serializers.IntegerField(default=10, min_value=1, max_value=50)
    difficulty = serializers.ChoiceField(
        choices=['easy', 'medium', 'hard', 'mixed'],
        default='medium',
    )
    education_level = serializers.ChoiceField(
        choices=['primary', 'secondary', 'bachillerato', 'fp', 'university', 'professional', 'other'],
        required=False,
        allow_null=True,
    )

    def validate_material_id(self, value):
        from apps.materials.models import TeachingMaterial
        request = self.context.get('request')
        try:
            material = TeachingMaterial.objects.get(pk=value, teacher=request.user)
        except TeachingMaterial.DoesNotExist:
            raise serializers.ValidationError('Material not found or you do not own it.')

        if material.status != 'completed':
            raise serializers.ValidationError(
                f'Material text extraction is not complete (status: {material.status}). '
                'Please wait for processing to finish.'
            )
        if not material.extracted_text:
            raise serializers.ValidationError('Material has no extracted text. Please reprocess it.')

        # Reject PDFs that could not be read (encrypted or image-only)
        _PLACEHOLDER_PREFIXES = (
            '[ENCRYPTED PDF',
            '[IMAGE-ONLY PDF',
        )
        if material.extracted_text.startswith(_PLACEHOLDER_PREFIXES):
            raise serializers.ValidationError(
                'This PDF could not be read (it may be encrypted or image-only). '
                'Please upload a text-based, non-encrypted PDF so the AI can generate relevant questions.'
            )

        return value
