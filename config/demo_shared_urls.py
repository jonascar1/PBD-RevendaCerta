from django.urls import path, include
from core.demo_shared import choose_role
urlpatterns = [path('demo/perfil/', choose_role, name='demo_perfil'), path('', include('core.urls'))]
