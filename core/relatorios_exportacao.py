from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DateTimeField, F, OuterRef, Prefetch, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.formats import number_format

from .models import (
    ContatoCarteira,
    HistoricoSituacaoVeiculo,
    LancamentoFinanceiro,
    Oportunidade,
    Veiculo,
    Venda,
)


def obter_dados_exportacao(data_inicio, data_fim, dias_parados=30):
    """Consulta os dados do relatório por período e estoque parado sem modificar o banco."""

    inicio = date.fromisoformat(data_inicio)
    fim = date.fromisoformat(data_fim)

    if inicio > fim:
        raise ValueError("A data inicial não pode superar a final.")

    dias_parados = int(dias_parados)
    if not 1 <= dias_parados <= 3650:
        raise ValueError("O limite deve estar entre 1 e 3650 dias.")

    vendas = list(
        Venda.objects.filter(
            situacao=Venda.Situacao.FECHADA,
            data__range=(inicio, fim),
        )
        .select_related("veiculo", "vendedor", "cliente")
        .order_by("-data", "-pk")
    )

    faturamento = sum(
        (v.valor_venda for v in vendas),
        Decimal("0.00"),
    )

    quantidade = len(vendas)
    ticket_medio = (
        faturamento / quantidade
        if quantidade
        else Decimal("0.00")
    )

    desempenho = {}
    margens = []

    for venda in vendas:
        nome_vendedor = (
            venda.vendedor.get_full_name()
            or venda.vendedor.username
        )

        dados = desempenho.setdefault(
            venda.vendedor_id,
            {
                "vendedor": nome_vendedor,
                "quantidade": 0,
                "faturamento": Decimal("0.00"),
                "desconto_total": Decimal("0.00"),
                "comissao": Decimal("0.00"),
            },
        )

        margem = venda.calcular_margem()

        dados["quantidade"] += 1
        dados["faturamento"] += venda.valor_venda
        dados["desconto_total"] += venda.desconto
        dados["comissao"] += margem["comissao"]

        margens.append([
            str(venda.veiculo),
            venda.valor_venda,
            margem["custo_aquisicao"],
            margem["despesas"],
            margem["comissao"],
            margem["margem"],
            margem["margem_percentual"],
        ])

    linhas_desempenho = []

    for dados in sorted(
        desempenho.values(),
        key=lambda item: item["faturamento"],
        reverse=True,
    ):
        linhas_desempenho.append([
            dados["vendedor"],
            dados["quantidade"],
            dados["faturamento"],
            dados["desconto_total"] / dados["quantidade"],
            dados["comissao"],
        ])

    despesas = (
        LancamentoFinanceiro.objects.filter(
            tipo=LancamentoFinanceiro.Tipo.DESPESA,
            excluido=False,
            data_lancamento__range=(inicio, fim),
        )
        .values("categoria_despesa")
        .annotate(
            quantidade=Count("id"),
            total=Sum("valor"),
        )
        .order_by("-total", "categoria_despesa")
    )

    despesas_sem_categoria = (
        LancamentoFinanceiro.objects.filter(
            tipo=LancamentoFinanceiro.Tipo.DESPESA,
            excluido=False,
            data_lancamento__range=(inicio, fim),
            categoria_despesa__isnull=True,
        ).count()
    )

    categorias = dict(LancamentoFinanceiro.CategoriaDespesa.choices)

    linhas_despesas = [
        [
            categorias.get(
                item["categoria_despesa"],
                "Sem categoria (registro antigo)",
            ),
            item["quantidade"],
            item["total"],
        ]
        for item in despesas
    ]

    total_contatos = ContatoCarteira.objects.filter(
        realizado_em__date__range=(inicio, fim)
    ).count()

    oportunidades = Oportunidade.objects.filter(
        criada_em__date__range=(inicio, fim)
    )
    total_oportunidades = oportunidades.count()
    oportunidades_vendidas = (
        oportunidades.filter(
            contato__propostas_geradas__vendas__situacao=Venda.Situacao.FECHADA
        )
        .distinct()
        .count()
    )

    # O relatório de parados é uma fotografia do estoque na data final do
    # período (limitada a hoje): conta dias a partir de quando o carro
    # ficou disponível.
    data_referencia = min(fim, timezone.localdate())
    limite = data_referencia - timedelta(days=dias_parados)

    ultima_disponibilidade = (
        HistoricoSituacaoVeiculo.objects.filter(
            veiculo=OuterRef("pk"),
            situacao_nova=Veiculo.Situacao.DISPONIVEL,
        )
        .order_by("-alterado_em")
        .values("alterado_em")[:1]
    )

    estoque = (
        Veiculo.objects.filter(
            situacao__in=[
                Veiculo.Situacao.DISPONIVEL,
                Veiculo.Situacao.RESERVADO,
            ],
            status__in=[
                Veiculo.Status.DISPONIVEL,
                Veiculo.Status.RESERVADO,
            ],
            venda_fechada=False,
        )
        .annotate(
            disponivel_desde=Coalesce(
                Subquery(ultima_disponibilidade),
                F("criado_em"),
                output_field=DateTimeField(),
            )
        )
        .filter(disponivel_desde__date__lte=limite)
        .prefetch_related(
            Prefetch(
                "lancamentos",
                queryset=LancamentoFinanceiro.objects.filter(
                    excluido=False,
                    tipo__in=[
                        LancamentoFinanceiro.Tipo.CUSTO_AQUISICAO,
                        LancamentoFinanceiro.Tipo.DESPESA,
                    ],
                ),
                to_attr="custos_ativos",
            )
        )
        .order_by("disponivel_desde", "pk")
    )

    linhas_estoque = []

    for veiculo in estoque:
        custo_aquisicao_lancamentos = sum(
            (
                lancamento.valor
                for lancamento in veiculo.custos_ativos
                if lancamento.tipo
                == LancamentoFinanceiro.Tipo.CUSTO_AQUISICAO
            ),
            Decimal("0.00"),
        )

        despesas_acumuladas = sum(
            (
                lancamento.valor
                for lancamento in veiculo.custos_ativos
                if lancamento.tipo
                == LancamentoFinanceiro.Tipo.DESPESA
            ),
            Decimal("0.00"),
        )

        if veiculo.origem == Veiculo.Origem.CONSIGNADO:
            custo_base = veiculo.valor_repasse or Decimal("0.00")
        else:
            custo_base = (
                custo_aquisicao_lancamentos
                if custo_aquisicao_lancamentos
                else veiculo.custo_aquisicao or Decimal("0.00")
            )

        custo_acumulado = custo_base + despesas_acumuladas

        desde = timezone.localtime(veiculo.disponivel_desde).date()
        dias_estoque = (data_referencia - desde).days

        linhas_estoque.append([
            str(veiculo),
            veiculo.placa,
            desde,
            dias_estoque,
            custo_acumulado,
            veiculo.preco_venda,
            veiculo.get_situacao_display(),
        ])


    return {
        "periodo": (inicio, fim),
        "dias_parados": dias_parados,
        "secoes": {
            "Resumo": {
                "cabecalhos": ["Indicador", "Valor"],
                "linhas": [
                    ["Quantidade de vendas", quantidade],
                    ["Faturamento", faturamento],
                    ["Ticket médio", ticket_medio],
                ],
            },"Vendas": {
                "cabecalhos": [
                    "Data", "Veículo", "Cliente", "Vendedor", "Valor",
                ],
                "linhas": [
                    [
                        venda.data,
                        str(venda.veiculo),
                        venda.cliente.nome_exibicao,
                        venda.vendedor.get_full_name()
                        or venda.vendedor.username,
                        venda.valor_venda,
                    ]
                    for venda in vendas
                ],
            },
            "Vendedores": {
                "cabecalhos": [
                    "Vendedor", "Vendas", "Faturamento",
                    "Desconto médio", "Comissão",
                ],
                "linhas": linhas_desempenho,
            },
            "Margens": {
                "cabecalhos": [
                    "Veículo", "Valor vendido", "Aquisição",
                    "Despesas", "Comissão", "Margem",
                    "Margem (%)",
                ],
                "linhas": margens,
            },
            "Despesas": {
                "cabecalhos": [
                    "Tipo de despesa", "Quantidade", "Total",
                ],
                "linhas": linhas_despesas,
            },
            "Contatos e oportunidades": {
                "cabecalhos": ["Indicador", "Valor"],
                "linhas": [
                    ["Contatos realizados", total_contatos],
                    ["Oportunidades criadas", total_oportunidades],
                    ["Oportunidades que viraram venda", oportunidades_vendidas],
                ],
            },
            "Carros parados": {
                "cabecalhos": [
                "Veículo",
                "Placa",
                "Disponível desde",
                "Dias em estoque",
                "Custo acumulado",
                "Preço atual",
                "Situação",
            ],
                "linhas": linhas_estoque,
            },
        },
        "despesas_sem_categoria": despesas_sem_categoria,
    }


def formatar_valor_relatorio(valor, tipo="texto"):
    """
    Formata valores para exibição no HTML.
    Mantém os dados originais para as exportações.
    """
    if valor is None:
        return "—"

    if tipo == "moeda":
        numero = number_format(
            valor,
            decimal_pos=2,
            force_grouping=True,
        )
        return f"R$ {numero}"

    if tipo == "percentual":
        numero = number_format(
            valor,
            decimal_pos=2,
        )
        return f"{numero}%"

    if tipo == "data":
        return valor.strftime("%d/%m/%Y")

    return str(valor)


TIPOS_COLUNAS_RELATORIOS = {
    "Resumo": ["texto", "texto"],
    "Vendas": [
    "data", "texto", "texto", "texto", "moeda",
],
    "Vendedores": [
        "texto", "texto", "moeda", "moeda", "moeda",
    ],
    "Margens": [
        "texto", "moeda", "moeda", "moeda",
        "moeda", "moeda", "percentual",
    ],
    "Despesas": [
        "texto", "texto", "moeda",
    ],
   "Contatos e oportunidades": ["texto", "texto"],
   "Carros parados": [
    "texto",
    "texto",
    "data",
    "texto",
    "moeda",
    "moeda",
    "texto",
],
}


def preparar_secoes_html(secoes):
    """
    Cria cópias formatadas das seções para o template.
    Os dados numéricos originais não são modificados.
    """
    resultado = {}

    for nome, secao in secoes.items():
        tipos = TIPOS_COLUNAS_RELATORIOS[nome]

        linhas = []

        for linha in secao["linhas"]:
            linhas.append([
                formatar_valor_relatorio(valor, tipo)
                for valor, tipo in zip(linha, tipos)
            ])

        resultado[nome] = {
            "cabecalhos": secao["cabecalhos"],
            "linhas": linhas,
        }

    return resultado


def obter_contexto_relatorios(data_inicio, data_fim, dias_parados=30):
    """
    Retorna os dados da T19 para a página HTML,
    usando a mesma fonte das exportações.
    """
    dados = obter_dados_exportacao(
        data_inicio=data_inicio,
        data_fim=data_fim,
        dias_parados=dias_parados,
    )

    secoes = preparar_secoes_html(dados["secoes"])

    resumo = dict(dados["secoes"]["Resumo"]["linhas"])

    return {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "dias_parados": dados["dias_parados"],
        "quantidade_vendas": resumo["Quantidade de vendas"],
        "faturamento": resumo["Faturamento"],
        "ticket_medio": resumo["Ticket médio"],
        "relatorio_vendas": secoes["Vendas"],
        "relatorio_vendedores": secoes["Vendedores"],
        "relatorio_margens": secoes["Margens"],
        "relatorio_despesas": secoes["Despesas"],
        "relatorio_contatos": secoes["Contatos e oportunidades"],
        "relatorio_estoque": secoes["Carros parados"],
        "quantidade_parados": len(
            secoes["Carros parados"]["linhas"]
        ),
        "despesas_sem_categoria": dados["despesas_sem_categoria"],
    }