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

    # Limites do mês corrente.
    inicio_mes = date(hoje.year, hoje.month, 1)
    if hoje.month == 12:
        proximo_mes = date(hoje.year + 1, 1, 1)
    else:
        proximo_mes = date(hoje.year, hoje.month + 1, 1)

    contatos = ContatoCarteira.objects.filter(
        cliente_id__in=elegiveis
    ).select_related("vendedor")

    if vendedor is not None:
        contatos = contatos.filter(vendedor=vendedor)

    # Uma única passada pelos contatos (do mais novo para o mais antigo):
    # - ultimo_contato: o contato mais recente de cada cliente;
    # - ids_contatados: quem foi contatado neste mês (o gerente conta
    #   o cliente uma vez, mesmo que dois vendedores tenham ligado);
    # - contatos_por_vendedor: quais vendedores ligaram neste mês.
    ultimo_contato = {}
    ids_contatados = set()
    contatos_por_vendedor = {}

    for contato in contatos.order_by("-realizado_em", "-pk"):
        ultimo_contato.setdefault(contato.cliente_id, contato)

        data_contato = timezone.localtime(contato.realizado_em).date()
        if inicio_mes <= data_contato < proximo_mes:
            ids_contatados.add(contato.cliente_id)
            contatos_por_vendedor.setdefault(
                contato.cliente_id, set()
            ).add(contato.vendedor_id)

    linhas = []
    for cliente_id, dados in elegiveis.items():
        venda = dados["ultima_venda"]
        dias = (hoje - venda.data).days

        ultimo = ultimo_contato.get(cliente_id)
        retorno = ultimo.data_retorno if ultimo else None
        retorno_chegou = retorno is not None and retorno <= hoje
        contatado_mes = cliente_id in ids_contatados

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
            "contatado_mes": contatado_mes,
            "contatos_vendedores_ids": contatos_por_vendedor.get(
                cliente_id, set()
            ),
            # T17
            "ultimo_contato": ultimo,
            "retorno": retorno,
            "retorno_chegou": retorno_chegou,
            "para_ligar_hoje": (not contatado_mes) or retorno_chegou,
        })

    # Fila geral: compra mais antiga primeiro (usada pelo gerente).
    linhas.sort(
        key=lambda item: (
            item["data_compra"],
            item["cliente"].pk,
        )
    )

    # T17: retornos que chegaram vão para o topo da fila do dia.
    linhas_hoje = sorted(
        (item for item in linhas if item["para_ligar_hoje"]),
        key=lambda item: (
            not item["retorno_chegou"],
            item["data_compra"],
            item["cliente"].pk,
        ),
    )
    linhas_contatadas = [
        item for item in linhas if not item["para_ligar_hoje"]
    ]

    return {
        "linhas": linhas,
        "linhas_hoje": linhas_hoje,
        "linhas_contatadas": linhas_contatadas,
        "total_clientes": len(linhas),
        "total_hoje": len(linhas_hoje),
        "retornos_hoje": sum(
            1 for item in linhas_hoje if item["retorno_chegou"]
        ),
        "contatados_mes": len(ids_contatados),
        "anos_configurados": configuracao.anos_sem_comprar,
        "data_limite": limite,
    }