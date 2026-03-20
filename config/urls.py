from django.contrib import admin
from django.urls import include, path

from notifications import views as notifications_views
from common.utils import health_check

urlpatterns = [
    path('admin/', admin.site.urls),

    # public
    path('api/notifications', notifications_views.get_notification_list, name='get_notification_list'),
    path('api/notifications/', include('notifications.urls')),

    path('', health_check),
]
