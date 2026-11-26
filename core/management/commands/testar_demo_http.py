import os
from datetime import timedelta
from django.conf import settings
from django.core import signing
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from core.demo_http_probe import COOKIE, SALT, PATTERN, schema_scope
from core.models import Usuario

class Command(BaseCommand):
    help = 'Testa sessões e permissões HTTP localmente, sem abrir cadastro público.'

    def add_arguments(self, parser):
        parser.add_argument('schema')

    def handle(self, *args, **options):
        name = options['schema']
        if (not settings.DEBUG or os.getenv('DATABASE_URL') or connection.vendor != 'postgresql'
                or connection.settings_dict['HOST'] not in ('localhost', '127.0.0.1', '::1', '')
                or not PATTERN.fullmatch(name)):
            raise CommandError('Somente schema demo válido no PostgreSQL local.')
        def require(condition, message):
            if not condition:
                raise CommandError(message)
        with schema_scope('public'):
            before = list(Usuario.objects.order_by('pk').values_list('pk', 'username', 'perfil'))
        stack = list(settings.MIDDLEWARE)
        stack.insert(stack.index('django.contrib.sessions.middleware.SessionMiddleware'), 'core.demo_http_probe.DemoProbeMiddleware')
        with override_settings(MIDDLEWARE=stack, ALLOWED_HOSTS=['testserver']):
            for role in ('gerente', 'vendedor', 'administrativo'):
                client = Client()
                with schema_scope(name):
                    user = Usuario.objects.get(username=role)
                    client.force_login(user)
                client.cookies[COOKIE] = signing.dumps(name, salt=SALT)
                response = client.get(reverse('painel'))
                require(response.status_code == 302 and response.url == reverse('painel_' + role), f'Redirecionamento incorreto: {role}, {response.status_code}')
                response = client.get(reverse('painel_' + role))
                require(response.status_code == 200, f'Painel {role}: HTTP {response.status_code}')
                other = 'vendedor' if role == 'gerente' else 'gerente'
                require(client.get(reverse('painel_' + other)).status_code == 403, f'Permissão cruzada: {role}')
                client.cookies[COOKIE] = 'invalid'
                require(client.get(reverse('painel')).status_code == 403, 'Cookie inválido aceito')
                del client.cookies[COOKIE]
                require(client.get(reverse('painel')).status_code == 403, 'Contexto ausente aceito')
                self.stdout.write(self.style.SUCCESS(f'OK: sessão e permissões de {role}'))
            client.cookies[COOKIE] = signing.dumps(name, salt=SALT)
            with schema_scope(name):
                with connection.cursor() as cursor:
                    cursor.execute('SELECT expira_em FROM demo_lifecycle WHERE id=1')
                    original = cursor.fetchone()[0]
                    cursor.execute('UPDATE demo_lifecycle SET expira_em=%s WHERE id=1', [timezone.now()-timedelta(seconds=1)])
            try:
                require(client.get(reverse('painel')).status_code == 403, 'Demonstração expirada aceita')
            finally:
                with schema_scope(name):
                    with connection.cursor() as cursor:
                        cursor.execute('UPDATE demo_lifecycle SET expira_em=%s WHERE id=1', [original])
            self.stdout.write(self.style.SUCCESS('OK: expiração bloqueada no servidor'))
        with schema_scope('public'):
            require(before == list(Usuario.objects.order_by('pk').values_list('pk', 'username', 'perfil')), 'Usuários originais alterados')
        self.stdout.write(self.style.SUCCESS('OK: usuários originais preservados. Cadastro público continua desativado.'))
