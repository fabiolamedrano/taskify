from django import forms
from django.contrib.auth.forms import get_user_model

from core.forms import TailwindFormMixin

from .models import Team, TeamMember

User = get_user_model()

class TeamForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'description', 'leader']
        labels = {
            'name': 'Nombre',
            'description': 'Descripción',
            'leader': 'Líder',
        }
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['leader'].queryset = User.objects.filter(teams=self.instance)
            self.fields['leader'].empty_label = 'Sin líder'

class TeamMemberForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = TeamMember
        fields = ['user', 'role_in_team']
        labels = {
            'user': 'Usuario',
            'role_in_team': 'Rol en el equipo',
        }
        widgets = {'role_in_team': forms.TextInput(attrs={'placeholder': 'Ej.Diseñadora'})}

    def __init__(self, *args, team, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.filter(is_active=True).exclude(teams=team)
        self.fields['user'].label_from_instance = (
            lambda user: f'{user.get_full_name() or user.username} ({user.get_role_display()})'
        )