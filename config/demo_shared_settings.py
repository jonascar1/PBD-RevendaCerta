"""Dedicated read-only demonstration service; never use for the main site."""
from .settings import *
import re
from django.core.exceptions import ImproperlyConfigured
DEMO_SHARED = True
DEMO_SCHEMA = os.getenv('DEMO_SCHEMA', '')
if not re.fullmatch(r'demo_[0-9a-f]{32}', DEMO_SCHEMA):
    raise ImproperlyConfigured('DEMO_SCHEMA inválido.')
DATABASES['default']['OPTIONS'] = {**DATABASES['default'].get('OPTIONS', {}), 'options': f'-c search_path={DEMO_SCHEMA} -c default_transaction_read_only=on'}
DATABASES['default']['CONN_MAX_AGE'] = 0
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
SESSION_COOKIE_NAME = 'rc_shared_session'
CSRF_COOKIE_NAME = 'rc_shared_csrf'
STORAGES = {**STORAGES, 'media_original': STORAGES['default'], 'default': {'BACKEND': 'core.demo_shared.ReadOnlyStorage'}}
ROOT_URLCONF = 'config.demo_shared_urls'
MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware') + 1, 'core.demo_shared.ReadOnlyMiddleware')
