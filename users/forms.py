from django import forms
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm

from core.forms import TailwindFormMixin

from .models import User

MAX_AVATAR_MB = 5
FILE_INPUT = (
    'w-full text-sm file:mr-3 file:rounded-full file:border-0 file:bg-brand-100 '
    'file:px-4 file:py-2 file:text-sm file:font-medium file:text-brand-800'
)

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

class UniqueEmailMixin:
    """Guarda el correo en minúsculas y rechaza uno que ya usa otra cuenta."""

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ya existe una cuenta con ese correo.')
        return email


class SignupForm(UniqueEmailMixin, TailwindFormMixin, UserCreationForm):
    """El rol no es un campo: toda cuenta nueva es «miembro»."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')
        labels = {
            'username': 'Usuario',
            'email': 'Correo electrónico',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
        }


class ProfileForm(UniqueEmailMixin, TailwindFormMixin, forms.ModelForm):
    avatar = forms.ImageField(
        required=False, label='Avatar', widget=forms.FileInput(attrs={'accept': 'image/*'}),
    )
    remove_avatar = forms.BooleanField(required=False, label='Quitar mi avatar actual')

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'avatar']
        labels = {'first_name': 'Nombre', 'last_name': 'Apellido', 'email': 'Correo electrónico'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._old_avatar = self.instance.avatar.name if self.instance.avatar else ''
        self.fields['avatar'].widget.attrs['class'] = FILE_INPUT
        if not self._old_avatar:
            del self.fields['remove_avatar']

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and 'avatar' in self.changed_data and avatar.size > MAX_AVATAR_MB * 1024 * 1024:
            raise forms.ValidationError(f'La imagen no puede pesar más de {MAX_AVATAR_MB} MB.')
        return avatar

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get('remove_avatar') and not self.files.get('avatar'):
            user.avatar = None
        if commit:
            user.save()
            new_name = user.avatar.name if user.avatar else ''
            if self._old_avatar and self._old_avatar != new_name:
                User._meta.get_field('avatar').storage.delete(self._old_avatar)
        return user


class StyledPasswordChangeForm(TailwindFormMixin, PasswordChangeForm):
    pass