from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from core.demo_schema import PATTERN, schema_scope
from core.demo_lifecycle import lifecycle_lock
from core.demo_lifecycle import active
from core.models import Cliente, ReservaVeiculo


class Command(BaseCommand):
    help = 'Renomeia clientes fictícios sem alterar seus relacionamentos.'

    def add_arguments(self, parser):
        parser.add_argument('schema')
        parser.add_argument('--confirmar', action='store_true')

    def handle(self, *args, **opts):
        schema = opts['schema']
        if not PATTERN.fullmatch(schema):
            raise CommandError('Informe um schema demonstrativo.')
        nomes = ['Rafael', 'Mariana', 'Lucas', 'Camila', 'André', 'Juliana', 'Bruno', 'Fernanda', 'Gabriel', 'Patrícia', 'Diego', 'Larissa', 'Felipe', 'Renata', 'Pedro', 'Beatriz', 'Daniel', 'Aline', 'Thiago', 'Carolina']
        sobrenomes = ['Almeida Santos', 'Ferreira Lima', 'Rodrigues Silva', 'Martins Oliveira', 'Costa Ribeiro', 'Souza Melo', 'Pereira Gomes']
        with lifecycle_lock(), schema_scope(schema), transaction.atomic():
            if not active():
                raise CommandError('Demonstração expirada.')
            with connection.cursor() as cursor:
                cursor.execute('SELECT id FROM demo_lifecycle WHERE id=1 FOR UPDATE')
            clientes = list(Cliente.objects.filter(tipo='PF', nome__startswith='Cliente ', email__endswith='.invalid').order_by('pk'))
            clientes = [c for c in clientes if c.nome.startswith(('Cliente fictício ', 'Cliente histórico fictício ')) and c.email.split('@')[-1] in ('demo.invalid', 'historico.demo.invalid')]
            usados = set(Cliente.objects.exclude(pk__in=[c.pk for c in clientes]).values_list('nome', flat=True))
            opcoes = iter(f'{n} {sobrenomes[(i+j)%len(sobrenomes)]}' for j in range(len(sobrenomes)) for i,n in enumerate(nomes))
            reservas = 0
            for c in clientes:
                novo = next((n for n in opcoes if n not in usados), None)
                if not novo:
                    raise CommandError('Nomes fictícios insuficientes.')
                usados.add(novo)
                if opts['confirmar']:
                    reservas += ReservaVeiculo.objects.filter(cliente_id=c.pk, cliente_nome=c.nome).update(cliente_nome=novo)
                    Cliente.objects.filter(pk=c.pk).update(nome=novo)
                else:
                    reservas += ReservaVeiculo.objects.filter(cliente_id=c.pk, cliente_nome=c.nome).count()
            self.stdout.write(f'Clientes: {len(clientes)}; reservas vinculadas: {reservas}')
            self.stdout.write('Nomes atualizados.' if opts['confirmar'] else 'SIMULAÇÃO: nenhuma alteração realizada.')
