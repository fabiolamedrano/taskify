from django import forms
from django.core.validators import FileExtensionValidator
from django.utils import timezone

from .models import Attachment, Comment, Subtask, TimeLog

MAX_UPLOAD_MB = 5
ALLOWED_EXTENSIONS = [
    'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'txt', 'csv',
    'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip',
]

INPUT = (
    'w-full rounded-lg border border-line bg-white px-3 py-2 text-sm '
    'focus:border-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-700/20'
)


class SubtaskForm(forms.ModelForm):
    class Meta:
        model = Subtask
        fields = ['title']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': INPUT, 'placeholder': 'Nueva subtarea...', 'aria-label': 'Nueva subtarea',
            }),
        }


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': INPUT, 'rows': 3, 'placeholder': 'Escribe un comentario...',
            }),
        }


class TimeLogForm(forms.ModelForm):
    class Meta:
        model = TimeLog
        fields = ['date', 'hours', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': INPUT}, format='%Y-%m-%d'),
            'hours': forms.NumberInput(attrs={'class': INPUT, 'step': '0.25', 'min': '0.25', 'max': '24'}),
            'description': forms.TextInput(attrs={'class': INPUT, 'placeholder': '¿Qué hiciste?'}),
        }

    def clean_hours(self):
        hours = self.cleaned_data['hours']
        if not 0 < hours <= 24:
            raise forms.ValidationError('Las horas deben estar entre 0 y 24.')
        return hours

    def clean_date(self):
        date = self.cleaned_data['date']
        if date > timezone.localdate():
            raise forms.ValidationError('No puedes registrar tiempo en una fecha futura.')
        return date


class AttachmentForm(forms.ModelForm):
    file_name = forms.CharField(
        max_length=255, required=False,
        widget=forms.TextInput(attrs={'class': INPUT, 'placeholder': 'Nombre (opcional)'}),
    )
    file = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_EXTENSIONS)],
        widget=forms.ClearableFileInput(attrs={
            'class': 'w-full text-sm file:mr-3 file:rounded-lg file:border-0 '
                     'file:bg-brand-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-brand-800',
        }),
    )

    class Meta:
        model = Attachment
        fields = ['file_name', 'file', 'url']
        widgets = {
            'url': forms.URLInput(attrs={'class': INPUT, 'placeholder': 'https://...'}),
        }

    def clean(self):
        cleaned = super().clean()
        file = cleaned.get('file')
        url = cleaned.get('url')

        if not file and not url:
            raise forms.ValidationError('Sube un archivo o escribe un enlace.')
        if file and url:
            raise forms.ValidationError('Elige un archivo o un enlace, no ambos.')
        if file and file.size > MAX_UPLOAD_MB * 1024 * 1024:
            self.add_error('file', f'El archivo no puede pesar más de {MAX_UPLOAD_MB} MB.')

        cleaned['file_name'] = (cleaned.get('file_name') or (file.name if file else url))[:255]
        return cleaned

    def save(self, commit=True):
        attachment = super().save(commit=False)
        file = self.cleaned_data.get('file')
        if file:
            attachment.size_kb = max(1, file.size // 1024)
            is_image = getattr(file, 'content_type', '').startswith('image/')
            attachment.type = Attachment.Type.IMAGE if is_image else Attachment.Type.DOCUMENT
        else:
            attachment.type = Attachment.Type.LINK
        if commit:
            attachment.save()
        return attachment