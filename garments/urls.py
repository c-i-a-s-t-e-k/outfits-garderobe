from django.urls import path

from garments import views

app_name = 'garments'

urlpatterns = [
    path('', views.garment_list, name='list'),
    path('add/', views.garment_add, name='add'),
]
