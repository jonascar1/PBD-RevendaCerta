from datetime import date
from decimal import Decimal
from django.db.models import Count, Q, Sum
from django.utils import timezone
from .models import LancamentoFinanceiro, EtapaDocumentacao, Venda, Veiculo


def contexto_administrativo():
    hoje = timezone.localdate()
    despesas = LancamentoFinanceiro.objects.filter(tipo=LancamentoFinanceiro.Tipo.DESPESA, excluido=False)
    meses = []
    nomes = ('Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez')
    for atraso in range(5, -1, -1):
        ano, mes = divmod(hoje.year * 12 + hoje.month - 1 - atraso, 12)
        inicio = date(ano, mes + 1, 1)
        a, m = divmod(ano * 12 + mes + 1, 12)
        fim = date(a, m + 1, 1)
        valor = despesas.filter(data_lancamento__gte=inicio, data_lancamento__lt=fim).aggregate(v=Sum('valor'))['v'] or Decimal(0)
        meses.append({'label': nomes[mes], 'valor': float(valor)})
    atual, anterior = meses[-1]['valor'], meses[-2]['valor']
    etapas = EtapaDocumentacao.objects.filter(venda__situacao=Venda.Situacao.FECHADA).exclude(situacao=EtapaDocumentacao.Situacao.CONCLUIDA).select_related('venda__veiculo').order_by('data', 'pk')
    entregas = Venda.objects.filter(situacao=Venda.Situacao.FECHADA, veiculo__situacao=Veiculo.Situacao.VENDIDO, entrega__isnull=True)
    prontas = entregas.annotate(concluidas=Count('etapas_documentacao', filter=Q(etapas_documentacao__situacao=EtapaDocumentacao.Situacao.CONCLUIDA))).filter(concluidas=len(EtapaDocumentacao.Tipo.choices)).select_related('cliente','veiculo').order_by('data','pk')
    categorias = dict(LancamentoFinanceiro.CategoriaDespesa.choices)
    tipos = [{'label': categorias.get(r['categoria_despesa'], 'Sem categoria'), 'valor': float(r['v'])} for r in despesas.order_by().values('categoria_despesa').annotate(v=Sum('valor')) if r['v'] > 0]
    return {'atual': atual, 'anterior': anterior, 'delta': round((atual-anterior)/anterior*100) if anterior else None, 'pendentes': etapas.count(), 'etapas': etapas[:6], 'aguardando': entregas.count(), 'prontas': prontas[:6], 'veiculos_com_despesas': despesas.values('veiculo_id').distinct().count(), 'total_despesas': despesas.count(), 'meses': meses, 'tipos': tipos}
