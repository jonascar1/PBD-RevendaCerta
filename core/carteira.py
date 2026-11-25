"""Cálculo automático e priorização da carteira de clientes elegíveis para recompra."""

from calendar import monthrange
from datetime import date

from django.utils import timezone

from .models import Cliente, ConfiguracaoCarteira, ContatoCarteira, Venda


def data_limite_carteira(hoje, anos):
    """Subtrai anos civis de uma data, tratando o caso bissexto (29/02)."""
    ano = hoje.year - anos
    dia = min(hoje.day, monthrange(ano, hoje.month)[1])
    return date(ano, hoje.month, dia)


def obter_configuracao_carteira():
    """Retorna a configuração global da carteira, criando o registro padrão se não existir."""
    configuracao, _ = ConfiguracaoCarteira.objects.get_or_create(
        pk=1,
        defaults={"anos_sem_comprar": 3},
    )
    return configuracao


def calcular_carteira(vendedor=None, hoje=None):
    """
    Calcula a carteira de clientes elegíveis a partir das vendas fechadas.

    Regras de negócio:
    - Considera a última venda fechada global de cada cliente ativo.
    - Um cliente pode integrar a carteira de múltiplos vendedores (sem duplicidade).
    - Qualquer nova compra reinicia o prazo de elegibilidade para todos os vendedores.
    - Clientes contatados no mês saem da fila diária, exceto quando a data de retorno vence.
    """
    hoje = hoje or timezone.localdate()
    configuracao = obter_configuracao_carteira()
    limite = data_limite_carteira(hoje, configuracao.anos_sem_comprar)

    vendas = (
        Venda.objects.filter(
            situacao=Venda.Situacao.FECHADA,
            cliente__ativo=True,
            data__lte=hoje,
        )
        .select_related("cliente", "veiculo", "vendedor")
        .order_by("cliente_id", "-data", "-pk")
    )

    # Agrupa por cliente mantendo sua última venda válida e o conjunto de vendedores.
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
                venda.vendedor.get_full_name() or venda.vendedor.username
            )

    elegiveis = {
        cliente_id: dados
        for cliente_id, dados in clientes.items()
        if dados["ultima_venda"].data <= limite
        and (vendedor is None or vendedor.pk in dados["vendedores"])
    }

    # "Já trocou em outra loja": o cliente sai da carteira, a menos que tenha
    # comprado de novo depois do contato. O caso é contado para o gerente.
    ids_trocou = set()
    for cliente_id, realizado_em in ContatoCarteira.objects.filter(
        cliente_id__in=elegiveis,
        resultado=ContatoCarteira.Resultado.TROCOU_OUTRA_LOJA,
    ).values_list("cliente_id", "realizado_em"):
        data_contato = timezone.localtime(realizado_em).date()
        if data_contato >= elegiveis[cliente_id]["ultima_venda"].data:
            ids_trocou.add(cliente_id)

    elegiveis = {
        cliente_id: dados
        for cliente_id, dados in elegiveis.items()
        if cliente_id not in ids_trocou
    }

    telefones = {
        cliente.pk: next((t.numero for t in cliente.telefones.all()), "")
        for cliente in Cliente.objects.filter(pk__in=elegiveis).prefetch_related(
            "telefones"
        )
    }

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

    # Em passagem única (mais recente -> mais antigo), extrai o último contato,
    # os clientes atendidos no mês corrente e os vendedores que realizaram contato.
    ultimo_contato = {}
    ids_contatados = set()
    contatos_por_vendedor = {}

    for contato in contatos.order_by("-realizado_em", "-pk"):
        ultimo_contato.setdefault(contato.cliente_id, contato)

        data_contato = timezone.localtime(contato.realizado_em).date()
        if inicio_mes <= data_contato < proximo_mes:
            ids_contatados.add(contato.cliente_id)
            contatos_por_vendedor.setdefault(contato.cliente_id, set()).add(
                contato.vendedor_id
            )

    linhas = []
    for cliente_id, dados in elegiveis.items():
        venda = dados["ultima_venda"]
        dias = (hoje - venda.data).days

        ultimo = ultimo_contato.get(cliente_id)
        retorno = ultimo.data_retorno if ultimo else None
        retorno_chegou = retorno is not None and retorno <= hoje
        contatado_mes = cliente_id in ids_contatados

        # Respeita a data de retorno agendada, independentemente do resultado do contato.
        adiado = (
            retorno is not None
            and retorno > hoje
        )
        linhas.append(
            {
                "cliente": dados["cliente"],
                "telefone": telefones.get(cliente_id, ""),
                "veiculo": venda.veiculo,
                "data_compra": venda.data,
                "dias_decorridos": dias,
                "anos_decorridos": dias // 365,
                "ultima_venda": venda,
                "vendedores_ids": dados["vendedores"],
                "vendedores_nomes": list(dados["vendedores_nomes"].values()),
                "contatado_mes": contatado_mes,
                "contatos_vendedores_ids": contatos_por_vendedor.get(
                    cliente_id, set()
                ),
                "ultimo_contato": ultimo,
                "retorno": retorno,
                "retorno_chegou": retorno_chegou,
                "adiado": adiado,
                "para_ligar_hoje": (
                    retorno_chegou or (not contatado_mes and not adiado)
                ),
            }
        )

    # Fila geral ordenada pela compra mais antiga (visão gerencial).
    linhas.sort(key=lambda item: (item["data_compra"], item["cliente"].pk))

    # Fila do dia prioriza retornos agendados vencidos no topo.
    linhas_hoje = sorted(
        (item for item in linhas if item["para_ligar_hoje"]),
        key=lambda item: (
            not item["retorno_chegou"],
            item["data_compra"],
            item["cliente"].pk,
        ),
    )
    linhas_contatadas = [item for item in linhas if not item["para_ligar_hoje"]]

    return {
        "linhas": linhas,
        "linhas_hoje": linhas_hoje,
        "linhas_contatadas": linhas_contatadas,
        "total_clientes": len(linhas),
        "total_hoje": len(linhas_hoje),
        "retornos_hoje": sum(1 for item in linhas_hoje if item["retorno_chegou"]),
        "contatados_mes": len(ids_contatados),
        "trocaram_outra_loja": len(ids_trocou),
        "anos_configurados": configuracao.anos_sem_comprar,
        "data_limite": limite,
    }