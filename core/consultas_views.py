from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .decorators import perfil_requerido
from .models import Cliente, Venda


@perfil_requerido('GERENTE')
@require_GET
def clientes_gerente(request):
    busca = request.GET.get('q', '').strip()
    situacao = request.GET.get('situacao', '')
    clientes = Cliente.objects.annotate(compras=Count('vendas', filter=Q(vendas__situacao=Venda.Situacao.FECHADA)))
    if busca:
        clientes = clientes.filter(Q(nome__icontains=busca) | Q(razao_social__icontains=busca) | Q(nome_fantasia__icontains=busca) | Q(cpf__icontains=busca) | Q(cnpj__icontains=busca))
    if situacao in ('ativo', 'inativo'):
        clientes = clientes.filter(ativo=situacao == 'ativo')
    return render(request, 'core/gerente_clientes.html', {
        'pagina': Paginator(clientes.order_by('nome', 'razao_social', 'pk'), 25).get_page(request.GET.get('page')),
        'busca': busca, 'situacao': situacao,
    })


@perfil_requerido('GERENTE', 'ADMINISTRATIVO')
@require_GET
def vendas_painel(request):
    busca = request.GET.get('q', '').strip()
    situacao = request.GET.get('situacao', '')
    vendas = Venda.objects.select_related('cliente', 'veiculo', 'vendedor', 'entrega').prefetch_related('etapas_documentacao')
    if busca:
        vendas = vendas.filter(Q(cliente__nome__icontains=busca) | Q(cliente__razao_social__icontains=busca) | Q(veiculo__marca__icontains=busca) | Q(veiculo__modelo__icontains=busca) | Q(veiculo__placa__icontains=busca))
    if situacao in dict(Venda.Situacao.choices):
        vendas = vendas.filter(situacao=situacao)
    return render(request, 'core/painel_vendas.html', {
        'base_template': 'core/gerente_base.html' if request.user.is_gerente() else 'core/administrativo_base.html',
        'pagina': Paginator(vendas.order_by('-data', '-pk'), 25).get_page(request.GET.get('page')),
        'busca': busca, 'situacao': situacao,
    })
