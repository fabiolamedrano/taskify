from django import forms

INPUT = (
    'w-full rounded-xl border border-line bg-white px-3 py-2 text-sm '
    'focus:border-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-700/20'
)


class TailwindFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxSelectMultiple):
                continue
            if isinstance(widget, forms.CheckboxInput):
                css = 'h-4 w-4 rounded border-line text-brand-700 focus:ring-brand-700'
            else:
                css = INPUT
            widget.attrs['class'] = f"{widget.attrs.get('class', '')} {css}".strip

class DateOrderMixin:
    def clean(self):
        cleaned = super().clean()
        start, due = cleaned.get('start_date'), cleaned.get('due_date')
        if start and due and due < start:
            self.add_error('due_date', 'La fecha límite no puede ser anterior a la de inicio.')
        return cleaned