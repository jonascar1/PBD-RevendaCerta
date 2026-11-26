from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction
from core import models as m


class Command(BaseCommand):
    help = 'Limpa exclusivamente o conjunto de testes conhecido de revendacerta_demo.'

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true')

    @transaction.atomic
    def handle(self, *args, **opts):
        if connection.vendor != 'postgresql' or connection.settings_dict['NAME'] != 'revendacerta_demo':
            raise CommandError('Banco não autorizado.')
        with connection.cursor() as cur:
            cur.execute('SELECT current_database()')
            if cur.fetchone()[0] != 'revendacerta_demo':
                raise CommandError('Banco não autorizado.')
            cur.execute('SELECT pg_advisory_xact_lock(7262501)')
        # Fail closed: do not delete a different dataset or new commercial records.
        expected = {m.Usuario:17, m.PerfilVendedor:7, m.Veiculo:252,
            m.FotoVeiculo:4563, m.Cliente:6, m.TelefoneCliente:0,
            m.Proposta:6, m.ComposicaoPagamento:7, m.HistoricoProposta:7,
            m.DecisaoProposta:3, m.ReservaVeiculo:5, m.Venda:3,
            m.PagamentoVenda:3, m.EtapaDocumentacao:9, m.EntregaVeiculo:1,
            m.AvaliacaoTroca:0, m.FotoAvaliacaoTroca:0, m.ContatoCarteira:1,
            m.Oportunidade:0, m.Procura:1, m.AvisoProcura:1,
            m.MetaMensal:1, m.MetaIndividual:7, m.HistoricoMeta:2,
            m.HistoricoAlcada:0, m.HistoricoPrecoVeiculo:0,
            m.HistoricoSituacaoVeiculo:10, m.LancamentoFinanceiro:250,
            m.ConfiguracaoCarteira:1}
        with connection.cursor() as cur:
            tables = ', '.join(connection.ops.quote_name(x._meta.db_table) for x in expected)
            cur.execute('LOCK TABLE ' + tables + ' IN SHARE ROW EXCLUSIVE MODE')
        for model, count in expected.items():
            if model.objects.count() != count:
                raise CommandError(f'{model.__name__}: quantidade mudou; revise antes de limpar.')
        cars = m.Veiculo.objects.filter(placa__in=[f'RCD{i}' for i in range(8001,8009)])
        ids = list(cars.values_list('pk', flat=True))
        clients = m.Cliente.objects.filter(email__endswith='@rc-cenarios.invalid', nome__startswith='DEMO RC ')
        cids = list(clients.values_list('pk', flat=True))
        if len(ids)!=8 or len(cids)!=6 or m.FotoVeiculo.objects.filter(veiculo_id__in=ids).exists():
            raise CommandError('Identificadores ou fotos divergentes.')
        for model in (m.Proposta,m.Venda,m.ReservaVeiculo):
            if model.objects.exclude(veiculo_id__in=ids, cliente_id__in=cids).exists():
                raise CommandError(f'{model.__name__}: registro fora dos cenários.')
        for model in (m.Procura,m.ContatoCarteira):
            if model.objects.exclude(cliente_id__in=cids).exists():
                raise CommandError(f'{model.__name__}: cliente fora dos cenários.')
        original = m.Veiculo.objects.exclude(pk__in=ids)
        if original.filter(cliente_comprador_id__in=cids).exists():
            raise CommandError('Cliente de teste vinculado a veículo original; revisar.')
        if original.exclude(situacao='DISPONIVEL', origem='COMPRADO').exists():
            raise CommandError('Estoque original mudou.')
        despesas = m.LancamentoFinanceiro.objects.filter(pk__in=[239,240,241], tipo='DESPESA').exclude(veiculo_id__in=ids)
        if set(despesas.values_list('pk','descricao')) != {(239,'Limpeza'),(240,'ag'),(241,'tava sujo')}:
            raise CommandError('Despesas de teste divergentes.')
        if m.LancamentoFinanceiro.objects.exclude(veiculo_id__in=ids).exclude(pk__in=[239,240,241]).exclude(tipo='CUSTO_AQUISICAO', venda__isnull=True).exists():
            raise CommandError('Lançamento original inesperado.')
        if m.HistoricoSituacaoVeiculo.objects.exclude(veiculo_id__in=ids).exists():
            raise CommandError('Histórico de veículo original encontrado; revisar.')
        plan = [(m.AvisoProcura,m.AvisoProcura.objects.all()),(m.Procura,m.Procura.objects.all()),
            (m.EntregaVeiculo,m.EntregaVeiculo.objects.all()),(m.EtapaDocumentacao,m.EtapaDocumentacao.objects.all()),
            (m.PagamentoVenda,m.PagamentoVenda.objects.all()),
            (m.LancamentoFinanceiro,m.LancamentoFinanceiro.objects.filter(veiculo_id__in=ids)),
            (m.LancamentoFinanceiro,despesas),(m.Venda,m.Venda.objects.all()),
            (m.HistoricoProposta,m.HistoricoProposta.objects.all()),(m.DecisaoProposta,m.DecisaoProposta.objects.all()),
            (m.ComposicaoPagamento,m.ComposicaoPagamento.objects.all()),
            (m.ReservaVeiculo,m.ReservaVeiculo.objects.all()),(m.Proposta,m.Proposta.objects.all()),
            (m.ContatoCarteira,m.ContatoCarteira.objects.all()),
            (m.HistoricoSituacaoVeiculo,m.HistoricoSituacaoVeiculo.objects.filter(veiculo_id__in=ids)),
            (m.HistoricoMeta,m.HistoricoMeta.objects.all()),(m.MetaIndividual,m.MetaIndividual.objects.all()),
            (m.MetaMensal,m.MetaMensal.objects.all()),(m.Veiculo,cars),(m.Cliente,clients)]
        for model, qs in plan:
            self.stdout.write(f'{model.__name__}: excluir {qs.count()}')
        if not opts['confirmar']:
            self.stdout.write('SIMULAÇÃO: nenhuma alteração. Use --confirmar após conferir.')
            return
        # Break the reservation/proposal FK cycle only within the verified demo set.
        m.Proposta.objects.filter(veiculo_id__in=ids).update(reserva_aguardada=None)
        for model, qs in plan:
            qs.delete()
        if (m.Veiculo.objects.count(),m.FotoVeiculo.objects.count(),m.Usuario.objects.count(),m.LancamentoFinanceiro.objects.count()) != (244,4563,17,238):
            raise CommandError('Contagem final divergente; revertendo.')
        # PostgreSQL ALTER SEQUENCE RESTART is transactional, unlike setval.
        with connection.cursor() as cur:
            for model in dict.fromkeys(model for model, qs in plan):
                if model.objects.exists():
                    continue
                cur.execute('SELECT pg_get_serial_sequence(%s,%s)', [model._meta.db_table,model._meta.pk.column])
                seq = cur.fetchone()[0]
                if seq:
                    cur.execute('SELECT quote_ident(n.nspname), quote_ident(c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=%s::regclass',[seq])
                    schema,name=cur.fetchone()
                    cur.execute(f'ALTER SEQUENCE {schema}.{name} RESTART WITH 1')
        self.stdout.write(self.style.SUCCESS('Limpeza concluída. Catálogo, fotos, usuários e 238 custos preservados.'))
