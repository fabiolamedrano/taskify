from django import forms
from django.db.models import Q

from core.forms import DateOrderMixin, TailwindFormMixin
from teams.models import Team

from .models import Project


class ProjectForm(TailwindFormMixin, DateOrderMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            'name', 'description', 'objective', 'budget',
            'start_date', 'due_date', 'status', 'team',
        ]
        labels = {
            'name': 'Nombre',
            'description': 'Descripción',
            'objective': 'Objetivo',
            'budget': 'Presupuesto',
            'start_date': 'Fecha de inicio',
            'due_date': 'Fecha límite',
            'status': 'Estado',
            'team': 'Equipo responsable',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'objective': forms.Textarea(attrs={'rows': 3}),
            'budget': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'due_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = Q(pk__in=Team.objects.visible_to(user).values('pk'))
        if self.instance.team_id:
            allowed |= Q(pk=self.instance.team_id)
        self.fields['team'].queryset = Team.objects.filter(allowed)
        self.fields['team'].empty_label = 'Sin equipo'

    def clean_budget(self):
        budget = self.cleaned_data['budget']
        if budget is not None and budget < 0:
            raise forms.ValidationError('El presupuesto no puede ser negativo.')
        return budget