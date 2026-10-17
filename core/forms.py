from django import forms

INPUT = (
    'w-full rounded-lg border border-line bg-white px-3 py-2 text-sm '
    'focus:border-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-700/20'
)


class TailwindFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxSelectMultiple):
                continue
            current = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{current} {INPUT}'.strip()


class DateOrderMixin:
    def clean(self):
        cleaned = super().clean()
        start, due = cleaned.get('start_date'), cleaned.get('due_date')
        if start and due and due < start:
            self.add_error('due_date', 'La fecha límite no puede ser anterior a la de inicio.')
        return cleaned