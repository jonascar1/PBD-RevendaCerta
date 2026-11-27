"""Seleção validada de schemas para comandos administrativos."""
import re
from django.contrib.contenttypes.models import ContentType
from contextlib import contextmanager
from django.db import connection

PATTERN = re.compile(r'demo_[0-9a-f]{32}\Z')

@contextmanager
def schema_scope(name):
    if name != 'public' and not PATTERN.fullmatch(name):
        raise ValueError('Schema inválido')
    original = dict(connection.settings_dict.get('OPTIONS', {}))
    ContentType.objects.clear_cache()
    connection.close()
    try:
        connection.settings_dict['OPTIONS'] = {**original, 'options': '-c search_path=' + name}
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_schema(), current_schemas(false)')
            if cursor.fetchone() != (name, [name]):
                raise ValueError('Schema inexistente ou search_path inválido')
        yield
    finally:
        ContentType.objects.clear_cache()
        connection.close()
        connection.settings_dict['OPTIONS'] = original
