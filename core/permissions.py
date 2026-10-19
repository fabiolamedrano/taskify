from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class NotClientMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_client:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class OwnerOrAdminMixin:
    owner_field = None

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        user = self.request.user
        if not (user.is_admin or getattr(obj, self.owner_field) == user.pk):
            raise PermissionDenied
        return obj

class AdminRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_admin:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)