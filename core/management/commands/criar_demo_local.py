"""Provisionamento local, sem acesso HTTP; registro dentro do schema isolado."""
from core.demo_guard import require_demo_database
from django.contrib.contenttypes.models import ContentType
import secrets
import uuid
from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connection, transaction
from django.utils import timezone
from datetime import timedelta
from core.models import Usuario, PerfilVendedor


class Command(BaseCommand):
    help = 'Cria uma demonstração local isolada com três contas e validade de 24 horas.'

    def handle(self, *args, **kwargs):
        require_demo_database()
        original = dict(connection.settings_dict.get('OPTIONS', {}))
        schema = 'demo_' + uuid.uuid4().hex
        quoted = connection.ops.quote_name(schema)
        created = False
        def select(name):
            ContentType.objects.clear_cache()
            connection.close()
            connection.settings_dict['OPTIONS'] = {**original, 'options': '-c search_path=' + name}
            with connection.cursor() as cursor:
                cursor.execute('SELECT current_schema(), current_schemas(false)')
                if cursor.fetchone() != (name, [name]):
                    raise CommandError('search_path inesperado.')
        try:
            select('public')
            with connection.cursor() as cursor:
                cursor.execute('CREATE SCHEMA ' + quoted)
            created = True
            select(schema)
            if connection.introspection.table_names():
                raise CommandError('Schema não vazio.')
            call_command('migrate', interactive=False, verbosity=0, skip_checks=True)
            if Usuario.objects.exists():
                raise CommandError('Schema contém usuários inesperados.')
            expires = timezone.now() + timedelta(hours=24)
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('CREATE TABLE demo_lifecycle (id integer PRIMARY KEY CHECK (id = 1), criado_em timestamptz NOT NULL, expira_em timestamptz NOT NULL)')
                    cursor.execute('INSERT INTO demo_lifecycle VALUES (1, %s, %s)', [timezone.now(), expires])
                for name, role in [('gerente', Usuario.Perfil.GERENTE), ('vendedor', Usuario.Perfil.VENDEDOR), ('administrativo', Usuario.Perfil.ADMINISTRATIVO)]:
                    user = Usuario.objects.create_user(username=name, password=secrets.token_urlsafe(32), perfil=role)
                    if role == Usuario.Perfil.VENDEDOR:
                        PerfilVendedor.objects.get_or_create(usuario=user, defaults={'percentual_comissao': 10})
            self.stdout.write(self.style.SUCCESS(f'Demonstração criada: {schema}'))
            self.stdout.write(f'Expiração: {expires.isoformat()} | Contas: {Usuario.objects.count()}')
        except BaseException:
            if created:
                select('public')
                with connection.cursor() as cursor:
                    cursor.execute('DROP SCHEMA ' + quoted + ' CASCADE')
            raise
        finally:
            ContentType.objects.clear_cache()
            connection.close()
            connection.settings_dict['OPTIONS'] = original
