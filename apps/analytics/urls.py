from django.urls import path

from .views import (
    GameAnalyticsView,
    GameAnalyticsExportView,
    TeacherDashboardView,
    DashboardExportView,
    ClassroomAnalyticsView,
    ActivityAnalyticsView,
)

urlpatterns = [
    path('dashboard/', TeacherDashboardView.as_view(), name='analytics-dashboard'),
    path('dashboard/export/', DashboardExportView.as_view(), name='analytics-dashboard-export'),
    path('classroom/<int:classroom_id>/', ClassroomAnalyticsView.as_view(), name='analytics-classroom'),
    path('activity/<int:activity_id>/', ActivityAnalyticsView.as_view(), name='analytics-activity'),
    path('session/<int:session_id>/', GameAnalyticsView.as_view(), name='analytics-session'),
    path('session/<int:session_id>/export/', GameAnalyticsExportView.as_view(), name='analytics-session-export'),
]
