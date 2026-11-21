"""
Montagem somente leitura das fichas de histórico de veículos e clientes.

Consolida eventos e registros existentes sem realizar alterações no banco.
"""

from decimal import Decimal

from django.utils import timezone

from .models import (
    ContatoCarteira,
    DecisaoProposta,
    EntregaVeiculo,
    EtapaDocumentacao,
    HistoricoProposta,
    PagamentoVenda,
    Procura,
    Proposta,
    ReservaVeiculo,
    Veiculo,
    Venda,
)


CATEGORIAS = {
    "origem": "Origem",
    "situacao": "Situação",
    "preco": "Preço",
    "despesa": "Despesa",
    "proposta": "Proposta",
    "reserva": "Reserva",
    "venda": "Venda",
    "documentacao": "Documentação",
    "entrega": "Entrega",
}


# ==============================================================================
# Funções Auxiliares
# ==============================================================================

def _brl(valor):
    """Formata um valor numérico no padrão monetário brasileiro (ex.: 'R$ 1.234,56')."""
    texto = f"{Decimal(valor or 0):,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _nome(usuario, padrao="Sistema"):
    """Retorna o nome completo, username ou rótulo padrão caso o usuário seja nulo."""
    if usuario is None:
        return padrao
    return usuario.get_full_name() or usuario.username


def _data_hora(valor):
    """Converte um datetime para string formatada no fuso horário local."""
    return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M")


def _rotulo_situacao(valor):
    """Traduz o código interno de situação do veículo para seu rótulo legível."""
    return dict(Veiculo.Situacao.choices).get(valor, valor or "—")


def _evento(
    data,
    categoria,
    titulo,
    detalhe="",
    autor="Sistema",
    cliente_id=None,
    venda_id=None,
):
    """Estrutura um item padronizado da linha do tempo."""
    return {
        "data": data,
        "categoria": categoria,
        "categoria_rotulo": CATEGORIAS[categoria],
        "titulo": titulo,
        "detalhe": detalhe,
        "autor": autor,
        "cliente_id": cliente_id,
        "venda_id": venda_id,
    }


# ==============================================================================
# Histórico do Veículo
# ==============================================================================

def linha_do_tempo_veiculo(veiculo):
    """
    Constrói a lista cronológica completa de eventos do veículo,
    desde o cadastro até a entrega ao comprador.
    """
    eventos = []

    detalhe = f"Origem: {veiculo.get_origem_display()}."
    if veiculo.origem == Veiculo.Origem.CONSIGNADO:
        detalhe += f" Valor de repasse: {_brl(veiculo.valor_repasse)}."
    else:
        detalhe += f" Custo de aquisição: {_brl(veiculo.custo_aquisicao)}."
    if veiculo.avaliacao_origem_id:
        detalhe += f" Recebido na troca (avaliação #{veiculo.avaliacao_origem_id})."

    eventos.append(
        _evento(
            veiculo.criado_em,
            "origem",
            "Veículo cadastrado",
            detalhe,
            _nome(veiculo.criado_por),
        )
    )

    for h in veiculo.historico_situacoes.select_related("alterado_por"):
        eventos.append(
            _evento(
                h.alterado_em,
                "situacao",
                f"Situação: {_rotulo_situacao(h.situacao_anterior)} → "
                f"{_rotulo_situacao(h.situacao_nova)}",
                h.motivo or "",
                _nome(h.alterado_por),
            )
        )

    for h in veiculo.historico_precos.select_related("alterado_por"):
        detalhe = f"{_brl(h.valor_anterior)} → {_brl(h.valor_novo)}"
        if h.abaixo_do_custo:
            detalhe += " (abaixo do custo total acumulado)"
        eventos.append(
            _evento(
                h.alterado_em,
                "preco",
                "Preço de venda alterado",
                detalhe,
                _nome(h.alterado_por),
            )
        )

    lancamentos = veiculo.lancamentos.select_related(
        "registrado_por", "editado_por", "excluido_por"
    )
    for l in lancamentos:
        nome = "Comissão" if l.tipo == l.Tipo.COMISSAO else "Despesa"
        texto = f"{_brl(l.valor)}" + (f" — {l.descricao}" if l.descricao else "")

        eventos.append(
            _evento(
                l.criado_em,
                "despesa",
                f"{nome} lançada",
                texto,
                _nome(l.registrado_por),
            )
        )
        if l.editado_em:
            eventos.append(
                _evento(
                    l.editado_em,
                    "despesa",
                    f"{nome} editada",
                    texto,
                    _nome(l.editado_por),
                )
            )
        if l.excluido and l.excluido_em:
            eventos.append(
                _evento(
                    l.excluido_em,
                    "despesa",
                    f"{nome} excluída",
                    texto,
                    _nome(l.excluido_por),
                )
            )

    for p in veiculo.propostas.select_related("cliente", "vendedor"):
        eventos.append(
            _evento(
                p.criada_em,
                "proposta",
                f"Proposta #{p.pk} recebida",
                f"{p.cliente.nome_exibicao} ofereceu {_brl(p.valor_oferecido)} "
                f"(tabela {_brl(p.preco_tabela)}).",
                _nome(p.vendedor),
                cliente_id=p.cliente_id,
            )
        )

    for h in HistoricoProposta.objects.filter(
        proposta__veiculo=veiculo, valor_anterior__isnull=False
    ).select_related("alterado_por"):
        eventos.append(
            _evento(
                h.alterado_em,
                "proposta",
                f"Proposta #{h.proposta_id}: valor alterado",
                f"{_brl(h.valor_anterior)} → {_brl(h.valor_novo)}",
                _nome(h.alterado_por),
            )
        )

    for d in DecisaoProposta.objects.filter(
        proposta__veiculo=veiculo
    ).select_related("feito_por"):
        detalhe = _brl(d.valor_referencia)
        if d.parecer:
            detalhe += f" — {d.parecer}"
        eventos.append(
            _evento(
                d.feito_em,
                "proposta",
                f"Proposta #{d.proposta_id}: {d.get_tipo_display()}",
                detalhe,
                _nome(d.feito_por),
            )
        )

    agora = timezone.now()
    for r in veiculo.reservas.select_related("vendedor", "cancelada_por"):
        detalhe = f"Cliente: {r.cliente_nome}. Prazo até {_data_hora(r.expira_em)}."
        if r.proposta_origem_id:
            detalhe += f" Gerada pela proposta #{r.proposta_origem_id}."

        eventos.append(
            _evento(
                r.criada_em,
                "reserva",
                f"Reserva #{r.pk} criada",
                detalhe,
                _nome(r.vendedor),
                cliente_id=r.cliente_id,
            )
        )

        if r.cancelada and r.cancelada_em:
            expirou = r.motivo_cancelamento == "Reserva expirada automaticamente"
            eventos.append(
                _evento(
                    r.cancelada_em,
                    "reserva",
                    f"Reserva #{r.pk} " + ("expirada" if expirou else "encerrada"),
                    r.motivo_cancelamento or "",
                    _nome(r.cancelada_por, "Sistema (expiração automática)"),
                )
            )
        elif not r.cancelada and r.expira_em <= agora:
            eventos.append(
                _evento(
                    r.expira_em,
                    "reserva",
                    f"Reserva #{r.pk} venceu",
                    "O prazo acabou e a reserva ainda não foi encerrada.",
                    "Sistema",
                )
            )

    for v in veiculo.vendas.select_related(
        "cliente", "vendedor", "fechada_por", "cancelada_por"
    ):
        eventos.append(
            _evento(
                v.criada_em,
                "venda",
                f"Venda #{v.pk} fechada",
                f"{v.cliente.nome_exibicao} — {_brl(v.valor_venda)}. "
                f"Vendedor: {_nome(v.vendedor)}.",
                _nome(v.fechada_por),
                cliente_id=v.cliente_id,
                venda_id=v.pk,
            )
        )
        if v.situacao == Venda.Situacao.CANCELADA and v.cancelada_em:
            eventos.append(
                _evento(
                    v.cancelada_em,
                    "venda",
                    f"Venda #{v.pk} cancelada",
                    v.motivo_cancelamento,
                    _nome(v.cancelada_por),
                    cliente_id=v.cliente_id,
                    venda_id=v.pk,
                )
            )

    for e in EtapaDocumentacao.objects.filter(
        venda__veiculo=veiculo
    ).select_related("atualizada_por"):
        detalhe = f"Data da etapa: {e.data:%d/%m/%Y}."
        if e.observacao:
            detalhe += f" {e.observacao}"
        eventos.append(
            _evento(
                e.atualizada_em,
                "documentacao",
                f"{e.get_tipo_display()}: {e.get_situacao_display()}",
                detalhe,
                _nome(e.atualizada_por),
                venda_id=e.venda_id,
            )
        )

    for en in EntregaVeiculo.objects.filter(
        venda__veiculo=veiculo
    ).select_related("responsavel"):
        eventos.append(
            _evento(
                en.criada_em,
                "entrega",
                "Veículo entregue",
                f"Entrega em {en.data_entrega:%d/%m/%Y}, com checklist assinado.",
                _nome(en.responsavel),
                venda_id=en.venda_id,
            )
        )

    eventos.sort(key=lambda evento: evento["data"])
    return eventos


# ==============================================================================
# Histórico do Cliente
# ==============================================================================

def _motivo_nao_fechamento(proposta):
    """
    Identifica o motivo de encerramento de uma proposta não convertida,
    priorizando o evento cronologicamente mais recente (recusa, reserva ou cancelamento).
    """
    candidatos = []

    for d in proposta.decisoes.filter(
        tipo__in=[
            DecisaoProposta.Tipo.RECUSA,
            DecisaoProposta.Tipo.RECUSA_CONTRAPROPOSTA,
            DecisaoProposta.Tipo.RECUSA_FILA,
        ]
    ):
        texto = d.get_tipo_display()
        if d.parecer:
            texto += f": {d.parecer}"
        candidatos.append((d.feito_em, texto))

    for r in ReservaVeiculo.objects.filter(
        proposta_origem=proposta, cancelada=True, cancelada_em__isnull=False
    ):
        candidatos.append(
            (r.cancelada_em, f"Reserva encerrada: {r.motivo_cancelamento}")
        )

    for v in proposta.vendas.filter(
        situacao=Venda.Situacao.CANCELADA, cancelada_em__isnull=False
    ):
        candidatos.append(
            (v.cancelada_em, f"Venda cancelada: {v.motivo_cancelamento}")
        )

    if not candidatos:
        return "Motivo não registrado"

    return max(candidatos, key=lambda c: c[0])[1]


def resumo_cliente(cliente):
    """Consolida o histórico comercial, contatos, trocas e procuras de um cliente."""
    hoje = timezone.localdate()

    compras = list(
        Venda.objects.filter(cliente=cliente, situacao=Venda.Situacao.FECHADA)
        .select_related("veiculo", "vendedor")
        .order_by("-data", "-pk")
    )

    ultima_compra = compras[0].data if compras else None
    dias_desde_ultima_compra = (hoje - ultima_compra).days if ultima_compra else None

    sem_venda = (
        Proposta.objects.filter(cliente=cliente)
        .exclude(vendas__situacao=Venda.Situacao.FECHADA)
        .select_related("veiculo", "vendedor")
    )

    nao_fechadas = [
        {"proposta": p, "motivo": _motivo_nao_fechamento(p)}
        for p in sem_venda.filter(situacao=Proposta.Situacao.CANCELADA).order_by(
            "-criada_em"
        )
    ]

    em_andamento = sem_venda.filter(
        situacao__in=[Proposta.Situacao.ATIVA, Proposta.Situacao.AGUARDANDO]
    ).order_by("-criada_em")

    total_comprado = sum((v.valor_venda for v in compras), Decimal("0.00"))

    contatos = list(
        ContatoCarteira.objects.filter(cliente=cliente)
        .select_related("vendedor")
        .order_by("-realizado_em", "-pk")
    )

    trocas = list(
        PagamentoVenda.objects.filter(
            venda__cliente=cliente,
            venda__situacao=Venda.Situacao.FECHADA,
            tipo=PagamentoVenda.Tipo.TROCA,
        )
        .select_related("venda", "avaliacao_troca")
        .order_by("-venda__data", "-pk")
    )

    procuras = list(
        Procura.objects.filter(cliente=cliente)
        .select_related("vendedor", "venda_atendida")
        .order_by("-criada_em", "-pk")
    )

    return {
        "compras": compras,
        "total_comprado": total_comprado,
        "ultima_compra": ultima_compra,
        "dias_desde_ultima_compra": dias_desde_ultima_compra,
        "nao_fechadas": nao_fechadas,
        "em_andamento": em_andamento,
        "contatos": contatos,
        "trocas": trocas,
        "procuras": procuras,
    }