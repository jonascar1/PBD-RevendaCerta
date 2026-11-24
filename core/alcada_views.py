from django import forms
from django.db import transaction
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from .decorators import perfil_requerido
from .models import Veiculo, HistoricoAlcada

class LoteForm(forms.Form):
    tipo = forms.ChoiceField(choices=Veiculo.TipoAlcada.choices)
    valor = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    def clean(self):
        dados = super().clean()
        if dados.get('tipo') == 'PERCENTUAL' and dados.get('valor', 0) > 100:
            self.add_error('valor', 'O percentual não pode ultrapassar 100%.')
        return dados

@perfil_requerido('GERENTE')
@require_http_methods(['GET', 'POST'])
def alcadas_lote(request):
    elegiveis = Veiculo.objects.exclude(situacao__in=['VENDIDO','ENTREGUE']).exclude(status='VENDIDO').filter(venda_fechada=False)
    qs = elegiveis.order_by('marca','modelo','pk')
    marca = request.GET.get('marca','')
    categoria = request.GET.get('categoria','')
    zero = request.GET.get('zero','')
    if marca: qs = qs.filter(marca=marca)
    if categoria: qs = qs.filter(tipo=categoria)
    if zero: qs = qs.filter(valor_alcada=0)
    form = LoteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            ids = {int(i) for i in request.POST.getlist('veiculos')}
        except ValueError:
            ids = set()
        if not ids:
            form.add_error(None, 'Selecione pelo menos um veículo.')
        else:
            with transaction.atomic():
                itens = list(elegiveis.select_for_update().filter(pk__in=ids).order_by('pk'))
                tipo, valor = form.cleaned_data['tipo'], form.cleaned_data['valor']
                if len(itens) != len(ids):
                    form.add_error(None, 'A seleção contém veículos indisponíveis para alteração.')
                elif tipo == 'VALOR' and any(v.preco_venda is None or valor > v.preco_venda for v in itens):
                    form.add_error('valor', 'O limite em reais exige preço cadastrado e não pode superar o preço de nenhum veículo selecionado.')
                else:
                    registros = []
                    for v in itens:
                        if (v.tipo_alcada, v.valor_alcada) == (tipo, valor): continue
                        registros.append(HistoricoAlcada(veiculo=v, gerente=request.user, tipo_anterior=v.tipo_alcada, valor_anterior=v.valor_alcada, tipo_novo=tipo, valor_novo=valor))
                        v.tipo_alcada, v.valor_alcada = tipo, valor
                    Veiculo.objects.bulk_update(itens, ['tipo_alcada','valor_alcada'])
                    HistoricoAlcada.objects.bulk_create(registros)
                    messages.success(request, f'{len(registros)} veículo(s) atualizado(s).')
                    return redirect('alcadas_lote')
    return render(request, 'core/alcadas_lote.html', dict(form=form, veiculos=qs, marcas=elegiveis.order_by('marca').values_list('marca',flat=True).distinct(), categorias=Veiculo.Tipo.choices, marca=marca, categoria=categoria, zero=zero, historico=HistoricoAlcada.objects.select_related('veiculo','gerente').order_by('-criado_em')[:50]))
