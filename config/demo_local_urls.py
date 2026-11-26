from django.urls import path, include
from core.demo_local_runtime import switch_role
urlpatterns = [path('demo/perfil/', switch_role, name='demo_perfil'), path('', include('core.urls'))]
