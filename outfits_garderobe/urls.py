"""
URL configuration for outfits_garderobe project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from accounts import views as account_views
from outfits import views as outfit_views


def health(request):
    return JsonResponse({'status': 'ok'})


urlpatterns = [
    path('health/', health),
    # `/` carries no content — it reads authentication state and redirects.
    # `wardrobe` was reserved here as a placeholder; S-03 filled it in with the
    # outfit grid. It keeps its name outside the `outfits` namespace because
    # LOGIN_REDIRECT_URL and every "back" link reverse it by that name.
    path('', account_views.home, name='home'),
    path('wardrobe/', outfit_views.wardrobe, name='wardrobe'),
    # Compose and outfit detail pages live under the same prefix.
    path('wardrobe/', include('outfits.urls')),
    path('admin/', admin.site.urls),
    # Mounted at the prefix Django's own LOGIN_URL default already assumes, and
    # above the privatemedia include so route resolution is unambiguous.
    path('accounts/', include('allauth.urls')),
    path('garments/', include('garments.urls')),
    # The private media gate. Never add django.conf.urls.static.static() for
    # MEDIA_ROOT here — that helper serves uploads publicly and would defeat the
    # ownership check this route exists to enforce.
    path('', include('privatemedia.urls')),
]
