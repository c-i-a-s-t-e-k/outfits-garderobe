from django.urls import path

from outfits import views

app_name = 'outfits'

# Mounted under /wardrobe/ next to the `wardrobe` route itself, which keeps
# its own name outside this namespace.
urlpatterns = [
    path('compose/', views.outfit_compose, name='compose'),
    path('<uuid:pk>/', views.outfit_detail, name='detail'),
]
