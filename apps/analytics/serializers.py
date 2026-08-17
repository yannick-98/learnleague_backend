from rest_framework import serializers


class QuestionAnalyticsSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    text = serializers.CharField()
    difficulty = serializers.CharField()
    topic = serializers.CharField()
    correct_option = serializers.CharField()
    correct_percentage = serializers.FloatField()
    avg_response_time = serializers.FloatField()
    most_chosen_option = serializers.CharField(allow_null=True)
    options_distribution = serializers.DictField(child=serializers.IntegerField())
    total_answers = serializers.IntegerField()


class PlayerReportSerializer(serializers.Serializer):
    position = serializers.IntegerField()
    player_id = serializers.IntegerField()
    alias = serializers.CharField()
    avatar = serializers.CharField()
    score = serializers.IntegerField()
    correct_answers = serializers.IntegerField()
    total_answers = serializers.IntegerField()
    accuracy = serializers.FloatField()
    avg_response_time = serializers.FloatField()
    fastest_answer_time = serializers.FloatField(allow_null=True)
    slowest_answer_time = serializers.FloatField(allow_null=True)
    strongest_topic = serializers.CharField(allow_null=True)
    weakest_topic = serializers.CharField(allow_null=True)


class GameSummarySerializer(serializers.Serializer):
    total_players = serializers.IntegerField()
    active_players = serializers.IntegerField()
    avg_score = serializers.FloatField()
    max_score = serializers.IntegerField()
    min_score = serializers.IntegerField()
    avg_accuracy = serializers.FloatField()
    total_questions = serializers.IntegerField()
    total_answers = serializers.IntegerField()
    avg_response_time = serializers.FloatField()
    completion_rate = serializers.FloatField()


class GameAnalyticsSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    session_code = serializers.CharField()
    activity_title = serializers.CharField()
    status = serializers.CharField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    summary = GameSummarySerializer()
    ranking = serializers.ListField()
    questions_analysis = QuestionAnalyticsSerializer(many=True)
    recommendations = serializers.ListField(child=serializers.CharField())
    player_reports = PlayerReportSerializer(many=True)
