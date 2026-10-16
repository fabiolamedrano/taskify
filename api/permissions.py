from functools import reduce

from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_admin(user):
    return user.is_superuser or user.role == user.Role.ADMIN


class NotClientOrReadOnly(BasePermission):
    message = 'Los clientes solo tienen acceso de lectura.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user.role != request.user.Role.CLIENT


class IsAdminOrReadOnly(BasePermission):
    message = 'Solo un administrador puede modificar este recurso.'

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or is_admin(request.user)


class OwnerOrAdminForWrite(BasePermission):

    message = 'Solo el responsable de este elemento o un administrador puede hacer esto.'

    def has_object_permission(self, request, view, obj):
        owner_field = getattr(view, 'owner_field', None)
        methods = getattr(view, 'owner_methods', ('PUT', 'PATCH', 'DELETE'))
        if owner_field is None or request.method not in methods:
            return True
        if is_admin(request.user):
            return True
        owner_id = reduce(getattr, owner_field.split('.'), obj)
        return owner_id == request.user.pk