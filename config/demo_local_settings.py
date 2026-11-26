"""Dedicated local demo server. Never use this settings module in production."""
from .settings import *
from django.core.exceptions import ImproperlyConfigured
if not DEBUG or os.getenv('DATABASE_URL') or DATABASES['default']['HOST'] not in ('localhost','127.0.0.1','::1',''):
    raise ImproperlyConfigured('Servidor de demonstração permitido apenas localmente.')
SESSION_COOKIE_NAME = 'rc_demo_session'
CSRF_COOKIE_NAME = 'rc_demo_csrf'
STORAGES = {**STORAGES, 'media_original': STORAGES['default'], 'default': {'BACKEND':'core.demo_storage.DemoStorage'}}
MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(MIDDLEWARE.index('django.contrib.sessions.middleware.SessionMiddleware'), 'core.demo_local_runtime.DemoLocalMiddleware')
ROOT_URLCONF = 'config.demo_local_urls'
