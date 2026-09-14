from django.urls import path

from outfits import views

app_name = 'outfits'

# Mounted under /wardrobe/ next to the `wardrobe` route itself, which keeps
# its own name outside this namespace.
urlpatterns = [
    path('compose/', views.outfit_compose, name='compose'),
    path('<uuid:pk>/', views.outfit_detail, name='detail'),
    path('<uuid:pk>/edit/', views.outfit_edit, name='edit'),
    path('<uuid:pk>/delete/', views.outfit_delete, name='delete'),
    path('<uuid:pk>/tags/add/', views.outfit_tags_add, name='tags_add'),
    path('<uuid:pk>/tags/<uuid:tag_pk>/remove/', views.outfit_tag_remove, name='tag_remove'),
    path('<uuid:pk>/photo/upload/', views.outfit_photo_upload, name='photo_upload'),
    path('<uuid:pk>/photo/remove/', views.outfit_photo_remove, name='photo_remove'),
    path(
        '<uuid:pk>/missing/<uuid:missing_pk>/replace/',
        views.outfit_missing_replace,
        name='missing_replace',
    ),
    path(
        '<uuid:pk>/missing/<uuid:missing_pk>/dismiss/',
        views.outfit_missing_dismiss,
        name='missing_dismiss',
    ),
]
