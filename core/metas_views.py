from datetime import date
from django import forms
from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .decorators import perfil_requerido
from .models import Usuario, MetaMensal, MetaIndividual, HistoricoMeta

class MetaForm(forms.Form):
    loja = forms.IntegerField(min_value=1, max_value=100000, label="Meta geral da loja")
    padrao = forms.IntegerField(min_value=1, max_value=100000, label="Meta padrão por vendedor")

@perfil_requerido("GERENTE")
@require_http_methods(["GET", "POST"])
def configurar_metas(request):
    atual = timezone.localdate().replace(day=1)
    try:
        mes = date.fromisoformat(request.GET.get("mes", atual.strftime("%Y-%m")) + "-01")
    except ValueError:
        mes = atual
    vendedores = list(Usuario.objects.filter(perfil="VENDEDOR", ativo=True).order_by("first_name", "username"))
    meta = MetaMensal.objects.filter(mes=mes).first()
    individuais = dict(MetaIndividual.objects.filter(mensal=meta).values_list("vendedor_id", "quantidade")) if meta else {}
    form = MetaForm(request.POST if request.method == "POST" else None, initial={"loja": meta.loja, "padrao": meta.padrao_vendedor} if meta else {})
    for v in vendedores:
        form.fields[f"v_{v.pk}"] = forms.IntegerField(required=False, min_value=1, max_value=100000, label=v.get_full_name() or v.username, initial=individuais.get(v.pk))
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            m, created = MetaMensal.objects.select_for_update().get_or_create(mes=mes, defaults={"loja":form.cleaned_data["loja"], "padrao_vendedor":form.cleaned_data["padrao"]})
            def snapshot():
                return {"loja":m.loja,"padrao":m.padrao_vendedor,"individuais":{str(k):v for k,v in MetaIndividual.objects.filter(mensal=m).values_list("vendedor_id","quantidade")}}
            anterior = {} if created else snapshot()
            m.loja = form.cleaned_data["loja"]
            m.padrao_vendedor = form.cleaned_data["padrao"]
            m.save(update_fields=["loja","padrao_vendedor"])
            for v in vendedores:
                quantidade = form.cleaned_data[f"v_{v.pk}"]
                if quantidade is None:
                    MetaIndividual.objects.filter(mensal=m,vendedor=v).delete()
                else:
                    MetaIndividual.objects.update_or_create(mensal=m,vendedor=v,defaults={"quantidade":quantidade})
            HistoricoMeta.objects.create(mensal=m,gerente=request.user,anterior=anterior,novo=snapshot())
        messages.success(request,"Metas salvas com sucesso.")
        return redirect("painel_gerente")
    historico = list(HistoricoMeta.objects.filter(mensal=meta).select_related("gerente").order_by("-criado_em")) if meta else []
    nomes = {str(v.pk): v.get_full_name() or v.username for v in Usuario.objects.filter(perfil="VENDEDOR")}
    for h in historico:
        antes = h.anterior.get("individuais", {})
        depois = h.novo.get("individuais", {})
        h.mudancas_individuais = [
            {"nome": nomes.get(k, f"Vendedor #{k}"), "antes": antes.get(k, "Padrão"), "depois": depois.get(k, "Padrão")}
            for k in sorted(antes.keys() | depois.keys()) if antes.get(k) != depois.get(k)
        ]
    return render(request, "core/configurar_metas.html", {"form": form, "mes": mes.strftime("%Y-%m"), "historico": historico})
