from django.contrib import messages
from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.permissions import AdminRequiredMixin

from .forms import TagForm
from .models import Tag


class TagListView(AdminRequiredMixin, ListView):
    template_name = 'tags/tag_list.html'
    context_object_name = 'tags'

    def get_queryset(self):
        return Tag.objects.annotate(task_count=Count('tasks')).order_by('name')


class TagCreateView(AdminRequiredMixin, CreateView):
    model = Tag
    form_class = TagForm
    template_name = 'tags/tag_form.html'
    success_url = reverse_lazy('tags:list')

    def form_valid(self, form):
        messages.success(self.request, f'Etiqueta «{form.instance.name}» creada.')
        return super().form_valid(form)


class TagUpdateView(AdminRequiredMixin, UpdateView):
    model = Tag
    form_class = TagForm
    template_name = 'tags/tag_form.html'
    success_url = reverse_lazy('tags:list')

    def form_valid(self, form):
        messages.success(self.request, f'Etiqueta «{form.instance.name}» actualizada.')
        return super().form_valid(form)


class TagDeleteView(AdminRequiredMixin, DeleteView):
    model = Tag
    http_method_names = ['post']
    success_url = reverse_lazy('tags:list')

    def form_valid(self, form):
        messages.success(self.request, f'Etiqueta «{self.object.name}» eliminada.')
        return super().form_valid(form)