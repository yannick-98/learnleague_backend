import re

from rest_framework import serializers
from .models import ClassRoom

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

class ClassRoomSerializer(serializers.ModelSerializer):
    materials_count = serializers.ReadOnlyField()
    activities_count = serializers.ReadOnlyField()
    sessions_count = serializers.ReadOnlyField()
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = ClassRoom
        fields = [
            "id", "name", "subject", "education_level", "description",
            "teacher", "teacher_name", "color",
            "materials_count", "activities_count", "sessions_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "teacher", "created_at", "updated_at"]

    def get_teacher_name(self, obj):
        return obj.teacher.full_name


class ClassRoomCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassRoom
        fields = ["name", "subject", "education_level", "description", "color"]

    def validate_color(self, value):
        if not HEX_COLOR_RE.match(value):
            raise serializers.ValidationError(
                "Color must be a valid hex value (e.g. #6366f1)."
            )
        return value

    def create(self, validated_data):
        validated_data["teacher"] = self.context["request"].user
        return super().create(validated_data)
