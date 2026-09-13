from django.urls import path

from outfits import views

app_name = 'outfits'

# Mounted under /wardrobe/ next to the `wardrobe` route itself, which keeps
# its own name outside this namespace.
urlpatterns = [
    path('compose/', views.outfit_compose, name='compose'),
    path('<uuid:pk>/', views.outfit_detail, name='detail'),
    path('<uuid:pk>/tags/add/', views.outfit_tags_add, name='tags_add'),
    path('<uuid:pk>/tags/<uuid:tag_pk>/remove/', views.outfit_tag_remove, name='tag_remove'),
]
