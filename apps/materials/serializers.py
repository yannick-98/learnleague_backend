from rest_framework import serializers
from .models import TeachingMaterial
from .utils import validate_pdf_file


class TeachingMaterialSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    classroom_name = serializers.SerializerMethodField()
    activities_count = serializers.SerializerMethodField()

    class Meta:
        model = TeachingMaterial
        fields = [
            "id", "title", "pdf_file", "file_url", "extracted_text",
            "teacher", "classroom", "classroom_name", "status",
            "page_count", "file_size", "error_message",
            "activities_count", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "teacher", "extracted_text", "status",
            "page_count", "file_size", "error_message",
            "created_at", "updated_at",
        ]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.pdf_file and request:
            return request.build_absolute_uri(obj.pdf_file.url)
        return None

    def get_classroom_name(self, obj):
        return obj.classroom.name if obj.classroom else None

    def get_activities_count(self, obj):
        return obj.activities.count()


class TeachingMaterialUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeachingMaterial
        fields = ["title", "pdf_file", "classroom"]

    def validate_pdf_file(self, value):
        is_valid, error = validate_pdf_file(value)
        if not is_valid:
            raise serializers.ValidationError(error)
        return value

    def validate_classroom(self, value):
        if value and value.teacher != self.context["request"].user:
            raise serializers.ValidationError("You do not own this classroom.")
        return value

    def create(self, validated_data):
        validated_data["teacher"] = self.context["request"].user
        validated_data["file_size"] = validated_data["pdf_file"].size
        return super().create(validated_data)


class TeachingMaterialUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeachingMaterial
        fields = ["title", "classroom"]

    def validate_classroom(self, value):
        if value and value.teacher != self.context["request"].user:
            raise serializers.ValidationError("You do not own this classroom.")
        return value
