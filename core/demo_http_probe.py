"""Local HTTP isolation probe. Not installed in the production middleware stack."""
import re
from contextlib import contextmanager
from django.core import signing
from django.db import connection
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.utils.cache import add_never_cache_headers

COOKIE = 'rc_demo_probe'
SALT = 'rc.local.demo.http.probe'
PATTERN = re.compile(r'demo_[0-9a-f]{32}\Z')

@contextmanager
def schema_scope(name):
    if name != 'public' and not PATTERN.fullmatch(name):
        raise ValueError('Schema inválido')
    original = dict(connection.settings_dict.get('OPTIONS', {}))
    connection.close()
    try:
        connection.settings_dict['OPTIONS'] = {**original, 'options': '-c search_path=' + name}
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_schema(), current_schemas(false)')
            if cursor.fetchone() != (name, [name]):
                raise ValueError('Schema inexistente ou search_path inválido')
        yield
    finally:
        connection.close()
        connection.settings_dict['OPTIONS'] = original

class DemoProbeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = request.COOKIES.get(COOKIE)
        if not token:
            return HttpResponseForbidden('Sonda exige contexto de demonstração.')
        try:
            name = signing.loads(token, salt=SALT, max_age=86400)
            if not isinstance(name, str) or not PATTERN.fullmatch(name):
                raise ValueError('Contexto inválido')
            with schema_scope(name):
                with connection.cursor() as cursor:
                    cursor.execute('SELECT expira_em FROM demo_lifecycle WHERE id=1')
                    row = cursor.fetchone()
                if not row or row[0] <= timezone.now():
                    return HttpResponseForbidden('Demonstração expirada.')
                response = self.get_response(request)
                add_never_cache_headers(response)
                return response
        except (signing.BadSignature, ValueError):
            return HttpResponseForbidden('Contexto inválido.')
