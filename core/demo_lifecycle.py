"""Lifecycle serialized by a PostgreSQL advisory lock."""
from .demo_guard import require_demo_database
from django.core.files.storage import storages
import io
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from django.conf import settings
from django.core.management import call_command, CommandError
from django.db import connection
from django.utils import timezone
from .demo_http_probe import PATTERN, schema_scope

@contextmanager
def lifecycle_lock():
    require_demo_database()
    # Dedicated connection: schema_scope closes the ordinary ORM connection.
    lock = connection.copy(alias='demo_lifecycle_lock')
    try:
        with lock.cursor() as cursor:
            cursor.execute('SET statement_timeout = 120000')
            cursor.execute('SELECT pg_advisory_lock(%s)', [723019481])
        yield
    finally:
        lock.close()

def schemas():
    with schema_scope('public'), connection.cursor() as c:
        c.execute('SELECT nspname FROM pg_namespace')
        return [n for n, in c.fetchall() if PATTERN.fullmatch(n)]

def expiry(name):
    with schema_scope(name), connection.cursor() as c:
        c.execute('SELECT expira_em FROM demo_lifecycle WHERE id=1')
        return c.fetchone()[0]

def drop(name):
    if not PATTERN.fullmatch(name): raise ValueError('Schema inválido')
    if not settings.DEBUG:
        backend = storages['media_original']
        prefix = 'demos/' + name + '/'
        for obj in backend.bucket.objects.filter(Prefix=prefix):
            obj.delete()
        if any(backend.bucket.objects.filter(Prefix=prefix).limit(1)):
            raise CommandError('Falha na limpeza de mídia remota.')
    root=Path(settings.MEDIA_ROOT).resolve()/'demos'
    folder=root/name
    if root.is_symlink() or folder.is_symlink(): raise CommandError('Caminho de mídia inseguro.')
    if folder.exists(): shutil.rmtree(folder)
    with schema_scope('public'), connection.cursor() as c:
        c.execute('DROP SCHEMA '+connection.ops.quote_name(name)+' CASCADE')

def cleanup():
    removed=[]
    for name in schemas():
        if expiry(name)<=timezone.now():
            drop(name); removed.append(name)
    return removed

def provision(replace=None):
    cleanup()
    existing=set(schemas())
    if replace and replace not in existing: raise CommandError('Demonstração expirada.')
    if len(existing)>=10 and not replace: raise CommandError('Limite de 10 demonstrações atingido.')
    deadline=expiry(replace) if replace else None
    name=None
    try:
        call_command('criar_demo_local',stdout=io.StringIO())
        new=set(schemas())-existing
        if len(new)!=1: raise CommandError('Criação inesperada.')
        name=new.pop()
        call_command('popular_demo_local',name,confirmar=True,stdout=io.StringIO())
        if deadline:
            with schema_scope(name), connection.cursor() as c:
                c.execute('UPDATE demo_lifecycle SET expira_em=%s WHERE id=1',[deadline])
            drop(replace)
        return name
    except BaseException:
        # Inclui Ctrl+C; o lock impede criação concorrente por outro provisionamento.
        for incomplete in set(schemas()) - existing:
            drop(incomplete)
        raise
