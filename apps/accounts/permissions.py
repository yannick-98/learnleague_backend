from rest_framework.permissions import BasePermission


class IsTeacher(BasePermission):
    """Allow access only to users with teacher role."""
    message = 'Only teachers can perform this action.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == 'teacher'
        )


class IsAdminUser(BasePermission):
    """Allow access only to admin users."""
    message = 'Only administrators can perform this action.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.role == 'admin' or request.user.is_staff)
        )


class IsOwnerOrAdmin(BasePermission):
    """Allow access to object owner or admin."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == 'admin' or request.user.is_staff:
            return True
        owner_field = getattr(obj, 'teacher', None) or getattr(obj, 'owner', None)
        return owner_field == request.user
