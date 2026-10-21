from django.urls import path

from .tag_views import TagCreateView, TagDeleteView, TagListView, TagUpdateView

app_name = 'tags'

urlpatterns = [
    path('', TagListView.as_view(), name='list'),
    path('new/', TagCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', TagUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', TagDeleteView.as_view(), name='delete'),
]