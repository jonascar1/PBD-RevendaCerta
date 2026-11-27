"""Dedicated demo service, never the main application."""
from .settings import *
from django.core.exceptions import ImproperlyConfigured
if not PRODUCTION or os.getenv('ENABLE_REMOTE_DEMOS') != '1':
    raise ImproperlyConfigured('Demonstrações remotas desativadas.')
if '-pooler' in DATABASES['default']['HOST'] or not DATABASES['default']['HOST'].endswith('.neon.tech'):
    raise ImproperlyConfigured('Use conexão direta Neon.')
DEMO_REMOTE_ENABLED = True
SESSION_COOKIE_NAME = 'rc_demo_session'
CSRF_COOKIE_NAME = 'rc_demo_csrf'
STORAGES = {**STORAGES, 'media_original': STORAGES['default'], 'default': {'BACKEND':'core.demo_storage.DemoStorage'}}
# Este módulo é exclusivo para comandos administrativos, não para servir HTTP.
ROOT_URLCONF = 'config.demo_admin_urls'
