from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ClassRoomViewSet

router = DefaultRouter()
router.register(r'', ClassRoomViewSet, basename='classroom')

urlpatterns = [
    path('', include(router.urls)),
]
