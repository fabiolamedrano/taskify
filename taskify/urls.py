from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from django.conf import settings
from django.conf.urls.static import static

from users.views import SignupView

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        'login/',
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name='login',
    ),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('signup/', SignupView.as_view(), name='signup'),
    path('projects/', include('projects.urls')),
    path('teams/', include('teams.urls')),
    path('notifications/', include('notifications.urls')),
    path('tags/', include('tasks.tag_urls')),
    path('users/', include('users.urls')),
    path('api/', include('api.urls')),
    path('tasks/', include('tasks.urls')),
    path('', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)