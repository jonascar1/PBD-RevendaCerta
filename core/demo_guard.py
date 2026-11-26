from django.conf import settings
from django.core.management import CommandError
from django.db import connection


def require_demo_database():
    host = connection.settings_dict['HOST']
    if connection.vendor != 'postgresql':
        raise CommandError('PostgreSQL obrigatório.')
    if settings.DEBUG and host in ('localhost', '127.0.0.1', '::1', ''):
        return
    if (getattr(settings, 'DEMO_REMOTE_ENABLED', False)
            and not settings.DEBUG and host.endswith('.neon.tech')
            and '-pooler' not in host and not connection.settings_dict.get('CONN_MAX_AGE')):
        return
    raise CommandError('Banco não autorizado para demonstrações.')
