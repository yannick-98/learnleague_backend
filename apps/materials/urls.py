from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import TeachingMaterialViewSet

router = DefaultRouter()
router.register(r'', TeachingMaterialViewSet, basename='material')

urlpatterns = [
    path('', include(router.urls)),
]
