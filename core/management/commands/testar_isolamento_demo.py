"""Prova local de isolamento; não habilita acesso HTTP."""
import os
import uuid
from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connection
from core.models import Usuario


class Command(BaseCommand):
    help = 'Cria dois schemas temporários, testa isolamento e remove ambos.'

    def handle(self, *args, **options):
        if not settings.DEBUG or os.getenv('DATABASE_URL') or connection.vendor != 'postgresql':
            raise CommandError('Execute somente no PostgreSQL local, sem DATABASE_URL.')
        if connection.settings_dict['HOST'] not in ('localhost', '127.0.0.1', '::1', ''):
            raise CommandError('Host não local.')
        original = dict(connection.settings_dict.get('OPTIONS', {}))
        schemas = ['demo_probe_' + uuid.uuid4().hex for _ in range(2)]
        created = []

        def select(schema):
            connection.close()
            connection.settings_dict['OPTIONS'] = {**original, 'options': '-c search_path=' + schema}
            with connection.cursor() as cursor:
                cursor.execute('SELECT current_schema(), current_schemas(false)')
                current, paths = cursor.fetchone()
                if current != schema or paths != [schema]:
                    raise CommandError('search_path inesperado; teste abortado.')

        def require(condition, message):
            if not condition:
                raise CommandError(message)

        select('public')
        before = list(Usuario.objects.order_by('pk').values_list('pk', 'username', 'perfil'))
        try:
            for schema in schemas:
                select('public')
                with connection.cursor() as cursor:
                    cursor.execute('CREATE SCHEMA ' + connection.ops.quote_name(schema))
                created.append(schema)
                select(schema)
                require(not connection.introspection.table_names(), 'Schema não está vazio.')
                call_command('migrate', interactive=False, verbosity=0, skip_checks=True)
                require(not Usuario.objects.exists(), 'Usuários externos visíveis.')
                Usuario.objects.create_user(username='teste_demo', password=uuid.uuid4().hex, perfil=Usuario.Perfil.GERENTE)
                self.stdout.write('Schema migrado: ' + schema)
            select(schemas[0])
            Usuario.objects.filter(username='teste_demo').update(first_name='Somente A')
            select(schemas[1])
            require(Usuario.objects.get(username='teste_demo').first_name == '', 'Alteração vazou para B.')
            Usuario.objects.filter(username='teste_demo').delete()
            select(schemas[0])
            require(Usuario.objects.get(username='teste_demo').first_name == 'Somente A', 'Exclusão vazou para A.')
            select('public')
            require(before == list(Usuario.objects.order_by('pk').values_list('pk', 'username', 'perfil')), 'Usuários originais mudaram durante o teste.')
            self.stdout.write(self.style.SUCCESS('OK: criação, alteração e exclusão isoladas; usuários originais preservados.'))
        finally:
            try:
                select('public')
                for schema in created:
                    with connection.cursor() as cursor:
                        cursor.execute('DROP SCHEMA ' + connection.ops.quote_name(schema) + ' CASCADE')
                    self.stdout.write('Schema temporário removido: ' + schema)
            finally:
                connection.close()
                connection.settings_dict['OPTIONS'] = original
