from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ActivityViewSet, QuestionViewSet

# Use nested routers if drf-nested-routers is installed; fall back to manual patterns.
try:
    from rest_framework_nested import routers as nested_routers
    _has_nested = True
except ImportError:
    _has_nested = False

router = DefaultRouter()
router.register(r'', ActivityViewSet, basename='activity')

urlpatterns = [
    path('', include(router.urls)),
]

if _has_nested:
    questions_router = nested_routers.NestedDefaultRouter(router, r'', lookup='activity')
    questions_router.register(r'questions', QuestionViewSet, basename='activity-questions')
    urlpatterns += [path('', include(questions_router.urls))]
else:
    # Manual nested routes
    question_list = QuestionViewSet.as_view({'get': 'list', 'post': 'create'})
    question_detail = QuestionViewSet.as_view({
        'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'
    })
    bulk_create = QuestionViewSet.as_view({'post': 'bulk_create'})
    reorder = QuestionViewSet.as_view({'post': 'reorder'})

    urlpatterns += [
        path('<int:activity_pk>/questions/', question_list, name='activity-questions-list'),
        path('<int:activity_pk>/questions/<int:pk>/', question_detail, name='activity-questions-detail'),
        path('<int:activity_pk>/questions/bulk_create/', bulk_create, name='activity-questions-bulk-create'),
        path('<int:activity_pk>/questions/reorder/', reorder, name='activity-questions-reorder'),
    ]
