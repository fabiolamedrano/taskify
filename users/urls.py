from django.urls import path

from .views import UserCreateView, UserListView, UserUpdateView

app_name = 'users'

urlpatterns = [
    path('', UserListView.as_view(), name='list'),
    path('new/', UserCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', UserUpdateView.as_view(), name='update'),
]