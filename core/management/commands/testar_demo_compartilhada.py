from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection, connections, DatabaseError, transaction
from django.test import Client, override_settings
from django.urls import reverse
from core.demo_storage import demo_media_scope
from core.models import Usuario, Veiculo


class Command(BaseCommand):
    help = 'Auditoria local da demonstração compartilhada, sem criar ou apagar schemas.'

    def handle(self, *args, **options):
        if not getattr(settings, 'DEMO_SHARED', False) or not settings.DEBUG or connection.settings_dict['HOST'] not in ('localhost', '127.0.0.1', '::1', ''):
            raise CommandError('Execute somente no PostgreSQL local com config.demo_shared_settings.')
        failures = []
        def check(label, fn):
            try:
                if not fn():
                    raise AssertionError('resultado inesperado')
                self.stdout.write(self.style.SUCCESS('OK: ' + label))
            except Exception as exc:
                failures.append(label)
                self.stdout.write(self.style.ERROR(f'FALHA: {label}: {type(exc).__name__}: {exc}'))
        def snapshot(schema):
            digest = sha256()
            with connection.cursor() as c:
                c.execute('SELECT tablename FROM pg_tables WHERE schemaname=%s ORDER BY tablename', [schema])
                tables = [row[0] for row in c.fetchall()]
                if not tables:
                    raise AssertionError('schema vazio')
                for table in tables:
                    qualified = '.'.join(connection.ops.quote_name(x) for x in (schema, table))
                    c.execute(f'SELECT row_to_json(t)::text FROM {qualified} t ORDER BY row_to_json(t)::text')
                    digest.update(table.encode())
                    for row in c.fetchall():
                        digest.update(row[0].encode()); digest.update(b'\0')
            return digest.hexdigest()
        def context_ok():
            with connection.cursor() as c:
                c.execute("SELECT current_schema(), current_schemas(false), current_setting('transaction_read_only')")
                return c.fetchone() == (settings.DEMO_SCHEMA, [settings.DEMO_SCHEMA], 'on')
        if not context_ok():
            raise CommandError('Contexto inseguro; auditoria interrompida.')
        before = {s: snapshot(s) for s in ('public', settings.DEMO_SCHEMA)}
        def blocked_sql(sql):
            try:
                with transaction.atomic(), connection.cursor() as c:
                    c.execute(sql)
                    transaction.set_rollback(True)
            except DatabaseError as exc:
                return getattr(exc.__cause__, 'sqlstate', None) == '25006' or getattr(exc.__cause__, 'pgcode', None) == '25006'
            return False
        def blocked_storage(action):
            try:
                with demo_media_scope(settings.DEMO_SCHEMA):
                    action()
            except PermissionDenied:
                return True
            return False
        def enter(client, role):
            response = client.get(reverse('demo_perfil'), {'perfil': role})
            if response.status_code != 200:
                raise AssertionError(f'GET seleção: {response.status_code}')
            token = client.cookies[settings.CSRF_COOKIE_NAME].value
            response = client.post(reverse('demo_perfil'), {'perfil': role, 'csrfmiddlewaretoken': token})
            if response.status_code != 302:
                raise AssertionError(f'POST seleção: {response.status_code}')
            return client.session.get('_auth_user_id') == str(Usuario.objects.get(username=role).pk)
        def get_ok(client, route, **kwargs):
            response = client.get(reverse(route, kwargs=kwargs))
            if response.status_code != 200:
                raise AssertionError(f'HTTP {response.status_code}')
            return True
        def post_blocked(client, route, data=None, **kwargs):
            token = client.cookies[settings.CSRF_COOKIE_NAME].value
            response = client.post(reverse(route, kwargs=kwargs), {**(data or {}), 'csrfmiddlewaretoken': token})
            return response.status_code == 403 and response.headers.get('X-RC-Demo-Blocked') == '1' and bool(response.json().get('erro'))
        routes = {
            'gerente': ['painel_gerente','vendedores','cadastrar_vendedor','veiculos','cadastrar_veiculo','negociacoes_gerente','margens','avaliacoes_troca','nova_avaliacao_troca','carteira_gerente','configurar_carteira','procuras_gerente','relatorios_gerente','clientes_gerente','configurar_metas','alcadas_lote','vendas_painel','preferencias'],
            'vendedor': ['painel_vendedor','veiculos_vendedor','clientes','cadastrar_cliente','propostas','nova_proposta','minhas_comissoes','carteira_vendedor','procuras_vendedor','nova_procura','preferencias'],
            'administrativo': ['painel_administrativo','despesas','entregas_administrativo','documentacao_pendente','preferencias'],
        }
        with override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False):
            check('SQL UPDATE bloqueado', lambda: blocked_sql('UPDATE core_veiculo SET marca=marca WHERE FALSE'))
            check('SQL DELETE bloqueado', lambda: blocked_sql('DELETE FROM core_veiculo WHERE FALSE'))
            check('SQL INSERT bloqueado', lambda: blocked_sql('INSERT INTO core_veiculo SELECT * FROM core_veiculo WHERE FALSE'))
            check('Upload bloqueado', lambda: blocked_storage(lambda: default_storage.save('perfis/rc_auditoria.txt', ContentFile(b'teste'))))
            check('Exclusão de mídia bloqueada', lambda: blocked_storage(lambda: default_storage.delete('perfis/rc_auditoria_inexistente.txt')))
            check('Mídia de perfil original bloqueada', lambda: blocked_storage(lambda: default_storage.url('perfis/rc_auditoria.jpg')))
            check('Mídia de outro schema bloqueada', lambda: blocked_storage(lambda: default_storage.url('demos/demo_' + ('0'*32 if settings.DEMO_SCHEMA != 'demo_'+'0'*32 else '1'*32) + '/perfis/teste.jpg')))
            a, b = Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)
            check('Painel exige sessão', lambda: a.get(reverse('painel_gerente')).status_code in (302,403))
            check('Seleção sem CSRF recusada', lambda: a.post(reverse('demo_perfil'), {'perfil':'gerente'}).status_code == 403)
            for role, names in routes.items():
                check('Entrar como '+role, lambda: enter(a, role))
                for name in names:
                    check(role+' / '+name, lambda: get_ok(a,name))
                check(role+' / alteração de foto bloqueada com JSON', lambda: post_blocked(a,'preferencias',{'acao':'remover_foto'}))
                check(role+' / upload bloqueado com JSON', lambda: post_blocked(a,'preferencias',{'acao':'enviar_foto','foto':ContentFile(b'teste',name='teste.jpg')}))
            check('Gerente no navegador A', lambda: enter(a,'gerente'))
            check('Vendedor no navegador B', lambda: enter(b,'vendedor'))
            check('Sessões independentes', lambda: a.session.get('_auth_user_id') != b.session.get('_auth_user_id'))
            check('Vendedor não acessa painel gerente', lambda: b.get(reverse('painel_gerente')).status_code == 403)
            check('Gerente não acessa painel vendedor', lambda: a.get(reverse('painel_vendedor')).status_code == 403)
            check('Cadastro de veículo bloqueado', lambda: post_blocked(a,'cadastrar_veiculo'))
            check('Cadastro de cliente bloqueado', lambda: post_blocked(b,'cadastrar_cliente'))
            check('Nova proposta bloqueada', lambda: post_blocked(b,'nova_proposta'))
            pk = Veiculo.objects.first().pk
            check('Alteração de preço bloqueada', lambda: post_blocked(a,'alterar_preco_veiculo',veiculo_id=pk))
            check('Admin bloqueado', lambda: a.get('/admin/').status_code == 403)
            check('API bloqueada', lambda: a.get('/api/').status_code == 403)
            check('Mídia privada via HTTP bloqueada', lambda: a.get('/media/perfis/rc_auditoria.jpg').status_code == 403)
            def concurrent(client, route):
                try:
                    return get_ok(client, route)
                finally:
                    connections.close_all()
            def both():
                with ThreadPoolExecutor(max_workers=2) as pool:
                    x = pool.submit(concurrent,a,'painel_gerente'); y = pool.submit(concurrent,b,'painel_vendedor')
                    return x.result() and y.result()
            check('Dois navegadores em paralelo', both)
            check('Logout A não encerra B', lambda: a.get(reverse('logout')).status_code == 302 and not a.session.get('_auth_user_id') and get_ok(b,'painel_vendedor'))
        for schema, digest in before.items():
            check('Registros preservados: '+schema, lambda: snapshot(schema) == digest)
        if failures:
            raise CommandError(f'{len(failures)} verificações falharam. Não publique ainda.')
        self.stdout.write(self.style.SUCCESS('AUDITORIA LOCAL APROVADA'))
