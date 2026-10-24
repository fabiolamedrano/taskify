from django.urls import path

from .views import (
    AccountPasswordChangeView, ProfileView, UserCreateView, UserListView, UserUpdateView,
)

app_name = 'users'

urlpatterns = [
    path('', UserListView.as_view(), name='list'),
    path('new/', UserCreateView.as_view(), name='create'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/password/', AccountPasswordChangeView.as_view(), name='password_change'),
    path('<int:pk>/edit/', UserUpdateView.as_view(), name='update'),
]