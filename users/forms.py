from django import forms
from django.contrib.auth.forms import UserCreationForm

from core.forms import TailwindFormMixin

from .models import User

MAX_AVATAR_MB = 5

class UserCreateForm(TailwindFormMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'role']
        labels = {
            'username': 'Usuario',
            'email': 'Correo electrónico',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'role': 'Rol',
        }

class UserUpdateForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'role', 'is_active', 'avatar']
        labels = {
            'username': 'Usuario',
            'email': 'Correo electrónico',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'role': 'Rol',
            'is_active': 'Activo',
            'avatar': 'Avatar',
        }

    def __init__(self, *args, current_user, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk == current_user.pk:
            for name in ('role', 'is_active'):
                self.fields[name].disabled = True
            self.fields['role'].help_text = 'No puedes cambiar tu propio rol ni desactivar tu cuenta.'

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and 'avatar' in self.changed_data and avatar.size > MAX_AVATAR_MB * 1024 * 1024:
            raise forms.ValidationError(f'La imagen no puede pesar mas de {MAX_AVATAR_MB} MB.')
        return avatar