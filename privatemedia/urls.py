"""Routes for the private media gate.

The route name is a load-bearing contract: S-02 and S-04 reverse it rather than
building media URLs by hand.
"""

from django.urls import path

from privatemedia import views

app_name = 'privatemedia'

urlpatterns = [
    path('media/<uuid:pk>/', views.serve_private_image, name='image'),
]
