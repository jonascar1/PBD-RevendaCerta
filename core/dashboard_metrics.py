"""Indicadores do painel gerencial, sem dados simulados."""
from collections import Counter, defaultdict
from calendar import monthrange
from datetime import date
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from .models import Venda, Veiculo, Proposta, Usuario

MONTHS = ('jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez')

def month_start(day, offset=0):
    year, month = divmod(day.year * 12 + day.month - 1 + offset, 12)
    return date(year, month + 1, 1)

def aging_band(days):
    return 'novo' if days <= 30 else 'atencao' if days <= 60 else 'parado' if days <= 90 else 'critico'

def percent_change(current, previous):
    return round((current - previous) * 100 / previous) if previous else None

def manager_metrics(today=None):
    today = today or timezone.localdate()
    start = month_start(today, -11)
    current = month_start(today)
    months = {month_start(today, i): {'label': MONTHS[month_start(today,i).month-1], 'unidades': 0, 'faturamento': Decimal(0)} for i in range(-11,1)}
    models = defaultdict(lambda: [0, Decimal(0)])
    categories = Counter()
    weekdays = [0]*7
    sellers = {u.pk: {'name': u.get_full_name() or u.username, 'unidades': 0, 'faturamento': Decimal(0)} for u in Usuario.objects.filter(perfil=Usuario.Perfil.VENDEDOR, ativo=True)}
    sales = Venda.objects.filter(situacao=Venda.Situacao.FECHADA, data__range=(start,today)).select_related('veiculo','vendedor')
    for sale in sales:
        row = months[month_start(sale.data)]
        row['unidades'] += 1
        row['faturamento'] += sale.valor_venda
        name = f'{sale.veiculo.marca} {sale.veiculo.modelo}'
        models[name][0] += 1
        models[name][1] += sale.valor_venda
        categories[sale.veiculo.get_tipo_display() or 'Não informado'] += 1
        weekdays[(sale.data.weekday()+1)%7] += 1
        if sale.data >= current:
            seller = sellers.setdefault(sale.vendedor_id, {'name': sale.vendedor.get_full_name() or sale.vendedor.username, 'unidades':0,'faturamento':Decimal(0)})
            seller['unidades'] += 1
            seller['faturamento'] += sale.valor_venda
    stock = []
    for v in Veiculo.objects.filter(situacao__in=[Veiculo.Situacao.DISPONIVEL, Veiculo.Situacao.RESERVADO]):
        entered = timezone.localtime(v.criado_em).date() if timezone.is_aware(v.criado_em) else v.criado_em.date()
        days = max(0,(today-entered).days)
        stock.append({'id':v.pk,'name':f'{v.marca} {v.modelo}','days':days,'price':float(v.preco_venda) if v.preco_venda is not None else None,'band':aging_band(days),'available':v.situacao==Veiculo.Situacao.DISPONIVEL})
    aging = Counter(v['band'] for v in stock)
    stalled = sorted((v for v in stock if v['days']>30), key=lambda v:-v['days'])
    now, prev = months[current], months[month_start(today,-1)]
    goal = getattr(settings,'REVENDA_META_MENSAL',None)
    goal = goal if isinstance(goal,int) and not isinstance(goal,bool) and goal>0 else None
    proposals = Proposta.objects.filter(data__range=(current,today)).count()
    def money_rows(rows):
        return [dict(r, faturamento=float(r['faturamento'])) for r in rows]
    return {'months':money_rows(months.values()), 'kpis':{'sales':now['unidades'],'revenue':float(now['faturamento']),'previous_sales':prev['unidades'],'previous_revenue':float(prev['faturamento']),'sales_delta':percent_change(now['unidades'],prev['unidades']),'revenue_delta':percent_change(now['faturamento'],prev['faturamento']),'available':sum(v['available'] for v in stock),'stalled':len(stalled),'stock_total':len(stock),'ticket':float(now['faturamento']/now['unidades']) if now['unidades'] else 0},'goal':goal,'goal_progress':round(now['unidades']*100/goal) if goal else None,'days_left':monthrange(today.year,today.month)[1]-today.day,'top':money_rows({'name':n,'unidades':v[0],'faturamento':v[1]} for n,v in sorted(models.items(),key=lambda x:(-x[1][0],-x[1][1],x[0]))[:5]),'ranking':money_rows(sorted(sellers.values(),key=lambda r:(-r['unidades'],-r['faturamento'],r['name']))),'category':[{'category':k,'unidades':v} for k,v in categories.most_common()],'weekday':[{'label':k,'unidades':v} for k,v in zip(('Dom','Seg','Ter','Qua','Qui','Sex','Sáb'),weekdays)],'aging':[{'band':k,'count':aging[k]} for k in ('novo','atencao','parado','critico')],'scatter':stock,'stalled':stalled,'funnel':[{'stage':'Atendimentos','value':None},{'stage':'Test drives','value':None},{'stage':'Propostas','value':proposals},{'stage':'Vendas','value':now['unidades']}]}


def seller_metrics(user, today=None):
    today = today or timezone.localdate()
    current = month_start(today)
    start = month_start(today, -11)
    team = set(Usuario.objects.filter(perfil=Usuario.Perfil.VENDEDOR, ativo=True).values_list('pk', flat=True))
    team.add(user.pk)
    months = {month_start(today,i): {'label': MONTHS[month_start(today,i).month-1], 'unidades':0, 'faturamento':Decimal(0), 'team':0} for i in range(-11,1)}
    counts = Counter()
    models = defaultdict(lambda: [0, Decimal(0)])
    categories = Counter()
    weekdays = [0]*7
    sales = Venda.objects.filter(situacao=Venda.Situacao.FECHADA, data__range=(start,today), vendedor_id__in=team).select_related('veiculo')
    for sale in sales:
        row = months[month_start(sale.data)]
        row['team'] += 1
        if sale.data >= current:
            counts[sale.vendedor_id] += 1
        if sale.vendedor_id != user.pk:
            continue
        row['unidades'] += 1
        row['faturamento'] += sale.valor_venda
        name = f'{sale.veiculo.marca} {sale.veiculo.modelo}'
        models[name][0] += 1
        models[name][1] += sale.valor_venda
        categories[sale.veiculo.get_tipo_display() or 'Não informado'] += 1
        weekdays[(sale.data.weekday()+1)%7] += 1
    now, prev = months[current], months[month_start(today,-1)]
    proposals = Proposta.objects.filter(vendedor=user)
    opened = proposals.filter(situacao__in=['ATIVA','AGUARDANDO','AGUARDANDO_GERENTE','APROVADA','CONTRAPROPOSTA']).exclude(vendas__situacao=Venda.Situacao.FECHADA).count()
    stalled = []
    for v in Veiculo.objects.filter(situacao=Veiculo.Situacao.DISPONIVEL):
        entered = timezone.localtime(v.criado_em).date() if timezone.is_aware(v.criado_em) else v.criado_em.date()
        days = (today-entered).days
        if days > 30:
            stalled.append({'name':f'{v.marca} {v.modelo}', 'days':days, 'price':float(v.preco_venda) if v.preco_venda is not None else None, 'band':aging_band(days)})
    goal = getattr(settings,'REVENDA_META_MENSAL_VENDEDOR',None)
    goal = goal if type(goal) is int and goal > 0 else None
    return {'months':[{'label':r['label'],'unidades':r['unidades'],'faturamento':float(r['faturamento']),'media':round(r['team']/len(team),1)} for r in months.values()], 'kpis':{'sales':now['unidades'],'revenue':float(now['faturamento']),'previous_sales':prev['unidades'],'previous_revenue':float(prev['faturamento']),'sales_delta':percent_change(now['unidades'],prev['unidades']),'revenue_delta':percent_change(now['faturamento'],prev['faturamento']),'open':opened,'position':1+sum(counts[i]>counts[user.pk] for i in team),'team_size':len(team)}, 'goal':goal,'goal_progress':round(now['unidades']*100/goal) if goal else None,'days_left':monthrange(today.year,today.month)[1]-today.day,'top':[{'name':n,'unidades':v[0],'faturamento':float(v[1])} for n,v in sorted(models.items(),key=lambda x:(-x[1][0],-x[1][1],x[0]))[:5]],'category':[{'category':k,'unidades':v} for k,v in categories.most_common()],'weekday':[{'label':k,'unidades':v} for k,v in zip(('Dom','Seg','Ter','Qua','Qui','Sex','Sáb'),weekdays)],'stalled':sorted(stalled,key=lambda v:-v['days']),'funnel':[{'stage':'Atendimentos','value':None},{'stage':'Test drives','value':None},{'stage':'Propostas','value':proposals.filter(data__range=(current,today)).count()},{'stage':'Vendas','value':now['unidades']}]}
