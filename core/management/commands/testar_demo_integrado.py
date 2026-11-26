from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client, override_settings
from django.urls import reverse
from core.demo_lifecycle import lifecycle_lock, provision, drop, schemas, expiry
from core.demo_http_probe import schema_scope
from core.demo_local_runtime import COOKIE, SALT
from core.models import Usuario, Veiculo
from django.core import signing

class Command(BaseCommand):
    help = 'Testa o middleware real com dois ambientes descartáveis locais.'
    def handle(self, *args, **opts):
        if settings.ROOT_URLCONF != 'config.demo_local_urls':
            raise CommandError('Use --settings=config.demo_local_settings')
        def require(ok, msg):
            if not ok: raise CommandError(msg)
        def snapshot():
            with schema_scope('public'):
                return (list(Usuario.objects.order_by('pk').values_list('pk','username')), list(Veiculo.objects.order_by('pk').values_list('pk','marca','modelo')))
        before = snapshot()
        created = []
        try:
            with override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False):
                clients = [Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)]
                for client in clients:
                    require(client.get('/demo/entrar/').status_code==200,'Entrada indisponível')
                    csrf=client.cookies[settings.CSRF_COOKIE_NAME].value
                    r=client.post('/demo/entrar/',{'acao':'criar','csrfmiddlewaretoken':csrf})
                    require(r.status_code==302,'Criação recusada')
                    name = signing.loads(client.cookies[COOKIE].value, salt=SALT)
                    created.append(name)
                    for role in ('gerente','vendedor','administrativo'):
                        require(client.get('/demo/perfil/').status_code==200,'Seleção indisponível')
                        csrf=client.cookies[settings.CSRF_COOKIE_NAME].value
                        require(client.post('/demo/perfil/',{'perfil':role,'csrfmiddlewaretoken':csrf}).status_code==302,'Alternância falhou')
                        require(client.get(reverse('painel_'+role)).status_code==200,'Painel inacessível: '+role)
                    require(client.post('/demo/perfil/',{'perfil':'gerente'}).status_code==403,'POST sem CSRF aceito')
                a,b = created
                require(a != b, 'Ambientes iguais')
                with schema_scope(a):
                    v=Veiculo.objects.first(); pk=v.pk; Veiculo.objects.filter(pk=pk).update(marca='TESTE ISOLAMENTO')
                with schema_scope(b): require(not Veiculo.objects.filter(marca='TESTE ISOLAMENTO').exists(),'Dados vazaram para B')
                require(clients[0].get('/media/perfis/inexistente.jpg').status_code==403,'Perfil original acessível')
                require(clients[0].get('/media/demos/'+b+'/perfis/inexistente.jpg').status_code==403,'Mídia cruzada acessível')
                client = clients[0]
                deadline = expiry(a)
                client.get('/demo/entrar/')
                csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
                require(client.post('/demo/entrar/', {'acao':'criar','csrfmiddlewaretoken':csrf}).status_code == 302, 'Continuação falhou')
                require(signing.loads(client.cookies[COOKIE].value,salt=SALT)==a, 'Continuação criou outro ambiente')
                require(client.post('/demo/entrar/', {'acao':'reiniciar','csrfmiddlewaretoken':csrf}).status_code == 302, 'Reinício falhou')
                fresh = signing.loads(client.cookies[COOKIE].value,salt=SALT)
                created.append(fresh)
                require(fresh != a and a not in schemas(), 'Schema anterior não removido')
                require(expiry(fresh)==deadline, 'Prazo alterado')
                with schema_scope(fresh): require(not Veiculo.objects.filter(marca='TESTE ISOLAMENTO').exists(), 'Dados não restaurados')
                clients[0].cookies[COOKIE]='invalido'
                require(clients[0].get(reverse('painel')).status_code==403,'Cookie inválido aceito')
            require(snapshot()==before,'Dados originais alterados')
            self.stdout.write(self.style.SUCCESS('OK: dois ambientes, três perfis, CSRF, cookie inválido e dados originais preservados, continuação e reinício sem renovar prazo.'))
        finally:
            with lifecycle_lock():
                for name in created:
                    if name in schemas(): drop(name)
