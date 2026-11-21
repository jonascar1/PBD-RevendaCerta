"""
T16 - Cálculo automático da carteira de clientes.
"""

from calendar import monthrange
from datetime import date

from django.utils import timezone

from .models import (
    Cliente,
    ConfiguracaoCarteira,
    ContatoCarteira,
    Venda,
)


def data_limite_carteira(hoje, anos):
    """Subtrai anos civis, incluindo o caso de 29/02."""
    ano = hoje.year - anos
    dia = min(hoje.day, monthrange(ano, hoje.month)[1])
    return date(ano, hoje.month, dia)


def obter_configuracao_carteira():
    configuracao, _ = ConfiguracaoCarteira.objects.get_or_create(
        pk=1,
        defaults={"anos_sem_comprar": 3},
    )
    return configuracao


def calcular_carteira(vendedor=None, hoje=None):
    """
    Calcula a carteira a partir das vendas FECHADAS.

    - A última compra do cliente é global.
    - O cliente pode pertencer a vários vendedores.
    - Cada vendedor aparece uma única vez por cliente.
    - Uma nova compra reinicia o prazo para todos.
    - Clientes inativos não entram.
    """
    hoje = hoje or timezone.localdate()
    configuracao = obter_configuracao_carteira()
    limite = data_limite_carteira(
        hoje, configuracao.anos_sem_comprar
    )

    vendas = (
        Venda.objects.filter(
            situacao=Venda.Situacao.FECHADA,
            cliente__ativo=True,
            data__lte=hoje,
        )
        .select_related("cliente", "veiculo", "vendedor")
        .order_by("cliente_id", "-data", "-pk")
    )

    # Uma entrada por cliente, com sua última venda válida
    # e todos os vendedores que já venderam para ele.
    clientes = {}

    for venda in vendas:
        dados = clientes.setdefault(
            venda.cliente_id,
            {
                "cliente": venda.cliente,
                "ultima_venda": venda,
                "vendedores": set(),
                "vendedores_nomes": {},
            },
        )
        if venda.vendedor.is_vendedor():
            dados["vendedores"].add(venda.vendedor_id)
            dados["vendedores_nomes"][venda.vendedor_id] = (
                venda.vendedor.get_full_name()
                or venda.vendedor.username
            )

    elegiveis = {
        cliente_id: dados
        for cliente_id, dados in clientes.items()
        if dados["ultima_venda"].data <= limite
        and (vendedor is None or vendedor.pk in dados["vendedores"])
    }

    telefones = {}
    for cliente in (
        Cliente.objects.filter(pk__in=elegiveis)
        .prefetch_related("telefones")
    ):
        telefones[cliente.pk] = next(
            (telefone.numero for telefone in cliente.telefones.all()),
            "",
        )

    # Contatos realizados durante o mês corrente.
    inicio_mes = date(hoje.year, hoje.month, 1)
    if hoje.month == 12:
        proximo_mes = date(hoje.year + 1, 1, 1)
    else:
        proximo_mes = date(hoje.year, hoje.month + 1, 1)

    contatos = ContatoCarteira.objects.filter(
        realizado_em__date__gte=inicio_mes,
        realizado_em__date__lt=proximo_mes,
        cliente_id__in=elegiveis,
    )

    if vendedor is not None:
        contatos = contatos.filter(vendedor=vendedor)

    # Para o gerente, conta o cliente uma vez,
    # mesmo que dois vendedores tenham ligado.
    ids_contatados = set(
        contatos.values_list("cliente_id", flat=True)
    )

    contatos_por_vendedor = set(
        contatos.values_list("cliente_id", "vendedor_id")
    )

    linhas = []
    for cliente_id, dados in elegiveis.items():
        venda = dados["ultima_venda"]
        dias = (hoje - venda.data).days

        linhas.append({
            "cliente": dados["cliente"],
            "telefone": telefones.get(cliente_id, ""),
            "veiculo": venda.veiculo,
            "data_compra": venda.data,
            "dias_decorridos": dias,
            "anos_decorridos": dias // 365,
            "ultima_venda": venda,
            "vendedores_ids": dados["vendedores"],
            "vendedores_nomes": list(
                dados["vendedores_nomes"].values()
            ),
            "contatado_mes": cliente_id in ids_contatados,
            "contatos_vendedores_ids": {
                vendedor_id
                for contato_cliente_id, vendedor_id in contatos_por_vendedor
                if contato_cliente_id == cliente_id
            },
        })

    linhas.sort(
        key=lambda item: (
            item["data_compra"],
            item["cliente"].pk,
        )
    )

    return {
        "linhas": linhas,
        "total_clientes": len(linhas),
        "contatados_mes": len(ids_contatados),
        "anos_configurados": configuracao.anos_sem_comprar,
        "data_limite": limite,
    }