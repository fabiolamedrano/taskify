from django.urls import path

from .views import TeamCreateView, TeamDeleteView, TeamDetailView, TeamListView, TeamMemberAddView, TeamMemberRemoveView, TeamUpdateView

app_name = 'teams'

urlpatterns = [
    path('', TeamListView.as_view(), name='list'),
    path('new/', TeamCreateView.as_view(), name='create'),
    path('<int:pk>/', TeamDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', TeamUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', TeamDeleteView.as_view(), name='delete'),
    path('<int:pk>/members/add/', TeamMemberAddView.as_view(), name='member_add'),
    path('members/<int:pk>/remove/', TeamMemberRemoveView.as_view(), name='member_remove'),
]