from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from core.models import (Veiculo, Venda, Proposta, ReservaVeiculo, LancamentoFinanceiro, MetaMensal, FotoVeiculo, Cliente, Usuario, HistoricoProposta, DecisaoProposta)

class Command(BaseCommand):
    help = 'Auditoria somente leitura da demonstracao.'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        if connection.vendor != 'postgresql' or connection.settings_dict['NAME'] != 'revendacerta_demo':
            raise CommandError('Banco nao autorizado.')
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
        issues = []
        def check(condition, message):
            if not condition:
                issues.append(message)
        def total(qs):
            return qs.aggregate(s=Sum('valor'))['s'] or Decimal('0')
        inicio, fim = date(2025,11,25), date(2026,11,25)
        vendas = Venda.objects.filter(situacao='FECHADA')
        periodo = vendas.filter(data__range=(inicio,fim))
        self.stdout.write('\nVENDAS MENSAIS (periodo simulado)')
        for m in MetaMensal.objects.order_by('mes'):
            q = periodo.filter(data__year=m.mes.year,data__month=m.mes.month)
            self.stdout.write(f'{m.mes:%m/%Y}: {q.count()} / meta {m.loja}; receita R$ {q.aggregate(s=Sum("valor_venda"))["s"] or 0}')
        self.stdout.write('\nVENDEDORES')
        for row in periodo.values('vendedor__username').annotate(n=Count('pk'),receita=Sum('valor_venda')).order_by('-n'):
            self.stdout.write(str(row))
        check(periodo.count()==120, f'Vendas no periodo: {periodo.count()} (esperado 120)')
        check(vendas.filter(data__lt=inicio).count()==20,'Quantidade de vendas antigas divergente')
        check(not vendas.filter(data__gt=fim).exists(),'Vendas posteriores ao periodo')
        margem=Decimal(0); comissao=Decimal(0); negativas=0
        for v in vendas.select_related('veiculo','proposta','vendedor','cliente'):
            p=v.proposta; car=v.veiculo
            check(v.soma_pagamentos==v.valor_venda,f'Venda {v.pk}: pagamentos divergentes')
            check(p.valor_oferecido==v.valor_venda,f'Venda {v.pk}: valor da proposta divergente')
            check((p.veiculo_id,p.cliente_id,p.vendedor_id)==(v.veiculo_id,v.cliente_id,v.vendedor_id),f'Venda {v.pk}: vinculos divergentes')
            check(car.situacao in ('VENDIDO','ENTREGUE'),f'Venda {v.pk}: situacao do veiculo {car.situacao}')
            check(p.data<=v.data and car.criado_em.date()<=v.data,f'Venda {v.pk}: cronologia proposta/aquisicao')
            e=getattr(v,'entrega',None)
            check((e is not None)==(car.situacao=='ENTREGUE'),f'Venda {v.pk}: entrega/situacao divergente')
            if e: check(v.data<=e.data_entrega<=fim and e.checklist_completo,f'Venda {v.pk}: entrega inconsistente')
            l=v.lancamentos_financeiros.filter(excluido=False)
            check(total(l.filter(tipo='VENDA'))==v.valor_venda,f'Venda {v.pk}: receita contabil divergente')
            check(total(l.filter(tipo='COMISSAO'))==v.calcular_comissao(),f'Venda {v.pk}: comissao divergente do calculo atual')
            if inicio<=v.data<=fim:
                r=v.calcular_margem(); margem+=r['margem']; comissao+=r['comissao']; negativas+=int(r['negativa'])
        self.stdout.write(f'\nMargem no periodo: R$ {margem}; comissoes: R$ {comissao}; vendas com margem negativa: {negativas}')
        for p in Proposta.objects.select_related('veiculo','reserva_aguardada'):
            check(p.composicao_fecha,f'Proposta {p.pk}: composicao divergente')
            check(p.data>=timezone.localtime(p.veiculo.criado_em).date(),f'Proposta {p.pk}: anterior ao cadastro do veiculo')
            if p.situacao=='AGUARDANDO':
                r=p.reserva_aguardada
                check(r is not None and r.veiculo_id==p.veiculo_id and not r.cancelada,f'Proposta {p.pk}: fila inconsistente')
        for car in Veiculo.objects.all():
            if car.origem=='COMPRADO':
                q=car.lancamentos.filter(tipo='CUSTO_AQUISICAO',excluido=False)
                check(q.count()==1 and total(q)==car.custo_aquisicao,f'Veiculo {car.pk}: custo de aquisicao divergente')
        self.stdout.write('\nSITUACOES')
        for model in (Veiculo,Proposta):
            self.stdout.write(f'{model.__name__}: {list(model.objects.values("situacao").annotate(n=Count("pk")))}')
        self.stdout.write(f'Reservas validas agora: {ReservaVeiculo.objects.filter(cancelada=False,expira_em__gt=timezone.now()).count()}')
        self.stdout.write(f'Reservas vencidas nao canceladas: {ReservaVeiculo.objects.filter(cancelada=False,expira_em__lte=timezone.now()).count()}')
        for model,n in ((Veiculo,389),(Cliente,180),(Usuario,17),(FotoVeiculo,4563)):
            check(model.objects.count()==n,f'{model.__name__}: quantidade diferente de {n}')
        self.stdout.write(f'\nPONTOS PARA REVISAO: {len(issues)}')
        for issue in issues: self.stdout.write(issue)
        self.stdout.write('Auditoria encerrada; nenhuma alteracao realizada.')
