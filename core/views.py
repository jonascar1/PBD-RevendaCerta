import json
from urllib.parse import urlencode
from django.conf import settings
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .carteira import calcular_carteira, obter_configuracao_carteira
from .decorators import perfil_requerido
from .forms import (
    AlterarSituacaoForm,
    AvaliacaoTrocaForm,
    CancelarReservaForm,
    CancelarVendaForm,
    ClienteForm,
    ComposicaoFormSet,
    ConfiguracaoCarteiraForm,
    ConfirmarPropostaForm,
    ContatoCarteiraForm,
    DecisaoPropostaForm,
    DespesaEditarForm,
    DespesaForm,
    EditarVeiculoForm,
    EntregaVeiculoForm,
    EtapaDocumentacaoForm,
    LoginForm,
    PrecoVendaForm,
    ProcuraForm,
    PropostaFiltroForm,
    PropostaForm,
    ReservaForm,
    TelefoneClienteFormSet,
    VeiculoForm,
    VendedorCadastroForm,
    VendedorEdicaoForm,
)
from .historico import linha_do_tempo_veiculo, resumo_cliente
from .models import (
    AvaliacaoTroca,
    AvisoProcura,
    Cliente,
    ContatoCarteira,
    DecisaoProposta,
    EntregaVeiculo,
    EtapaDocumentacao,
    FotoAvaliacaoTroca,
    FotoVeiculo,
    HistoricoPrecoVeiculo,
    HistoricoSituacaoVeiculo,
    LancamentoFinanceiro,
    Oportunidade,
    PerfilVendedor,
    Procura,
    Proposta,
    ReservaVeiculo,
    Usuario,
    Veiculo,
    Venda,
)


# ==============================================================================
# Funções Auxiliares
# ==============================================================================

def adicionar_erros_de_validacao(form, erro, renomear=None):
    """Converte um ValidationError do model em erros vinculados aos campos do form."""
    renomear = renomear or {}
    if hasattr(erro, "message_dict"):
        for campo, mensagens in erro.message_dict.items():
            campo = renomear.get(campo, campo)
            alvo = campo if campo in form.fields else None
            for mensagem in mensagens:
                form.add_error(alvo, mensagem)
    else:
        for mensagem in erro.messages:
            form.add_error(None, mensagem)


def erros_do_form_como_mensagens(request, form):
    """Envia os erros de validação de um formulário para o sistema de mensagens."""
    for erros in form.errors.values():
        for erro in erros:
            messages.error(request, erro)


def expirar_reservas_vencidas():
    """Encerra sob demanda todas as reservas cujo prazo já expirou."""
    for reserva in ReservaVeiculo.objects.filter(
        cancelada=False, expira_em__lte=timezone.now()
    ):
        reserva.expirar()


def _propostas_visiveis(usuario):
    """Restringe a visualização de propostas ao próprio vendedor, liberando todas aos demais."""
    propostas = Proposta.objects.select_related("cliente", "veiculo", "vendedor")
    if usuario.is_vendedor():
        propostas = propostas.filter(vendedor=usuario)
    return propostas


def _contato_origem_do_vendedor(request):
    """Contato da carteira (do próprio vendedor) que originou a proposta, se informado."""
    valor = request.POST.get("contato") or request.GET.get("contato") or ""
    if not valor.isdigit():
        return None
    return ContatoCarteira.objects.filter(
        pk=int(valor), vendedor=request.user
    ).first()


def _dados_veiculos_para_js(veiculos):
    """Serializa preço e status de reserva dos veículos para consumo no formulário de proposta."""
    reservas = {
        r.veiculo_id: r
        for r in ReservaVeiculo.objects.filter(
            veiculo__in=veiculos,
            cancelada=False,
            expira_em__gt=timezone.now(),
        )
    }
    dados = {}
    for veiculo in veiculos:
        reserva = reservas.get(veiculo.pk)
        dados[str(veiculo.pk)] = {
            "preco": str(veiculo.preco_venda),
            "reservado": reserva is not None,
            "reserva_expira": (
                timezone.localtime(reserva.expira_em).strftime("%d/%m/%Y %H:%M")
                if reserva
                else ""
            ),
        }
    return dados


def _veiculos_disponiveis_para_procura():
    """Veículos que estão à venda agora, usados no cruzamento com as procuras."""
    return Veiculo.objects.filter(
        situacao=Veiculo.Situacao.DISPONIVEL,
        status=Veiculo.Status.DISPONIVEL,
    )


# ==============================================================================
# Autenticação, Painel Geral e Vitrine Pública
# ==============================================================================

def login_view(request):
    """Autentica o usuário e valida se o cadastro está ativo."""
    if request.method == "POST":
        form = LoginForm(request.POST)

        if form.is_valid():
            usuario = authenticate(
                request,
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )

            if usuario is None:
                messages.error(request, "Usuário ou senha inválidos.")
            elif not usuario.ativo:
                messages.error(request, "Usuário inativo. Contate o gerente.")
            else:
                login(request, usuario)
                return redirect("painel")
    else:
        form = LoginForm()

    return render(request, "core/login.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def painel_view(request):
    """Redireciona o usuário autenticado para o painel correspondente ao seu perfil."""
    usuario = request.user

    if usuario.is_gerente():
        return redirect("painel_gerente")
    if usuario.is_vendedor():
        return redirect("painel_vendedor")
    if usuario.is_administrativo():
        return redirect("painel_administrativo")

    logout(request)
    messages.error(request, "Perfil de usuário inválido. Contate o gerente.")
    return redirect("login")


def vitrine_view(request):
    """Exibe o catálogo público de veículos disponíveis com filtros de busca."""
    expirar_reservas_vencidas()

    estoque = Veiculo.objects.filter(
        situacao=Veiculo.Situacao.DISPONIVEL,
        status=Veiculo.Status.DISPONIVEL,
    )

    marca = request.GET.get("marca", "").strip()
    preco = request.GET.get("preco", "").strip()
    ano = request.GET.get("ano", "").strip()
    combustivel = request.GET.get("combustivel", "").strip()

    veiculos = (
        estoque.only(
            "id",
            "marca",
            "modelo",
            "ano_fabricacao",
            "ano_modelo",
            "cor",
            "combustivel",
            "cambio",
            "quilometragem",
            "preco_venda",
            "criado_em",
        )
        .prefetch_related("fotos")
        .order_by("-criado_em")
    )

    if marca:
        veiculos = veiculos.filter(marca__icontains=marca)

    if preco:
        try:
            preco_maximo = Decimal(preco.replace(",", "."))
            if preco_maximo >= 0:
                veiculos = veiculos.filter(preco_venda__lte=preco_maximo)
        except (InvalidOperation, ValueError):
            preco = ""

    if ano:
        try:
            ano_filtro = int(ano)
            if 1900 <= ano_filtro <= 2100:
                veiculos = veiculos.filter(
                    Q(ano_fabricacao=ano_filtro) | Q(ano_modelo=ano_filtro)
                )
        except (ValueError, TypeError):
            ano = ""

    if combustivel:
        veiculos = veiculos.filter(combustivel__icontains=combustivel)

    marcas = (
        estoque.order_by()
        .values_list("marca", flat=True)
        .distinct()
        .order_by("marca")
    )
    combustiveis = (
        estoque.order_by()
        .values_list("combustivel", flat=True)
        .distinct()
        .order_by("combustivel")
    )
    anos = sorted(
        set(estoque.values_list("ano_fabricacao", flat=True))
        | set(estoque.values_list("ano_modelo", flat=True)),
        reverse=True,
    )

    return render(
        request,
        "core/vitrine.html",
        {
            "whatsapp_numero": getattr(settings, "WHATSAPP_NUMERO", ""),
            "veiculos": veiculos,
            "marcas": marcas,
            "anos": anos,
            "combustiveis": combustiveis,
            "filtros": {
                "marca": marca,
                "preco": preco,
                "ano": ano,
                "combustivel": combustivel,
            },
        },
    )



# Catálogo público em grade, independente do carrossel da página inicial.
def explorar_view(request):
    expirar_reservas_vencidas()
    estoque = Veiculo.objects.filter(
        situacao=Veiculo.Situacao.DISPONIVEL,
        status=Veiculo.Status.DISPONIVEL,
    )
    campos = {campo.name for campo in Veiculo._meta.fields}
    filtros = {chave: request.GET.get(chave, "").strip() for chave in (
        "busca", "marca", "modelo", "preco", "ano", "combustivel", "tipo", "cambio", "ordem"
    )}
    veiculos = estoque
    if filtros["busca"]:
        veiculos = veiculos.filter(
            Q(marca__icontains=filtros["busca"]) | Q(modelo__icontains=filtros["busca"])
        )
    for chave in ("marca", "modelo", "combustivel", "tipo", "cambio"):
        if chave in campos and filtros[chave]:
            veiculos = veiculos.filter(**{f"{chave}__iexact": filtros[chave]})
    if filtros["preco"]:
        try:
            valor = Decimal(filtros["preco"].replace(",", "."))
            if valor >= 0:
                veiculos = veiculos.filter(preco_venda__lte=valor)
        except (InvalidOperation, ValueError):
            filtros["preco"] = ""
    if filtros["ano"]:
        try:
            ano = int(filtros["ano"])
            if 1900 <= ano <= 2100:
                veiculos = veiculos.filter(Q(ano_fabricacao=ano) | Q(ano_modelo=ano))
        except ValueError:
            filtros["ano"] = ""
    ordenacoes = {
        "ano_novo": ("-ano_modelo", "-pk"),
        "ano_antigo": ("ano_modelo", "pk"),
        "menor_km": ("quilometragem", "pk"),
        "menor_preco": ("preco_venda", "-criado_em", "-pk"),
        "maior_preco": ("-preco_venda", "-criado_em", "-pk"),
        "mais_antigos": ("criado_em", "pk"),
        "recentes": ("-criado_em", "-pk"),
    }
    veiculos = veiculos.prefetch_related("fotos").order_by(
        *ordenacoes.get(filtros["ordem"], ordenacoes["recentes"])
    )
    pagina = Paginator(veiculos, 12).get_page(request.GET.get("pagina"))
    opcoes = {}
    for campo in ("marca", "modelo", "combustivel", "tipo", "cambio"):
        if campo in campos:
            opcoes[campo] = list(
                estoque.exclude(**{f"{campo}__isnull": True})
                .exclude(**{campo: ""}).order_by(campo)
                .values_list(campo, flat=True).distinct()
            )
        else:
            opcoes[campo] = []
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return render(request, "core/explorar.html", {
        "whatsapp_numero": getattr(settings, "WHATSAPP_NUMERO", ""),
        "anos": sorted({a for a in set(estoque.values_list("ano_fabricacao", flat=True)) | set(estoque.values_list("ano_modelo", flat=True)) if a and a >= 1900}, reverse=True),
        "pagina": pagina,
        "filtros": filtros,
        "opcoes": opcoes,
        "total": pagina.paginator.count,
        "parametros": parametros.urlencode(),
    })


def vender_publico_view(request):
    return render(request, "core/vender.html", {"whatsapp_numero": getattr(settings, "WHATSAPP_NUMERO", "")})


def sobre_nos_view(request):
    return render(request, "core/sobre_nos.html", {"whatsapp_numero": getattr(settings, "WHATSAPP_NUMERO", "")})

def vitrine_veiculo_detalhe_view(request, pk):
    """Exibe apenas os campos públicos de um veículo disponível na vitrine."""
    expirar_reservas_vencidas()
    estoque = _veiculos_disponiveis_para_procura().prefetch_related("fotos")
    veiculo = get_object_or_404(estoque, pk=pk)
    outros = estoque.exclude(pk=pk)
    mesma_marca = list(outros.filter(marca__iexact=veiculo.marca).order_by("-criado_em")[:4])
    candidatos = outros.exclude(pk__in=[v.pk for v in mesma_marca])
    recomendados = sorted(candidatos, key=lambda v: (v.tipo != veiculo.tipo, v.combustivel != veiculo.combustivel, abs((v.preco_venda or 0) - (veiculo.preco_venda or 0))))[:12]
    numero = getattr(settings, "WHATSAPP_NUMERO", "")
    mensagem = f"Olá! Vim pelo site Revenda Certa e tenho interesse no {veiculo.marca} {veiculo.modelo}, ano {veiculo.ano_modelo}. Gostaria de mais informações.\n{request.build_absolute_uri()}"
    whatsapp = f"https://wa.me/{numero}?" + urlencode({"text": mensagem})
    return render(request, "core/vitrine_veiculo_detalhe.html", {"whatsapp_numero": numero, "veiculo": veiculo, "fotos": veiculo.fotos.all(), "mesma_marca": mesma_marca, "recomendados": recomendados, "whatsapp_veiculo": whatsapp})


# ==============================================================================
# Vendedor
# ==============================================================================

@perfil_requerido("VENDEDOR")
def painel_vendedor_view(request):
    from .dashboard_metrics import seller_metrics
    expirar_reservas_vencidas()
    dados = get_object_or_404(PerfilVendedor, usuario=request.user)
    return render(request, "core/vendedor_painel_inicio.html", {
        "dados": dados, "dashboard": seller_metrics(request.user),
    })


@perfil_requerido("VENDEDOR")
@require_GET
def veiculos_vendedor_view(request):
    """Catálogo interno somente para consulta, com filtros combináveis."""
    from django.db.models import F

    expirar_reservas_vencidas()
    estoque = Veiculo.objects.all()
    filtros = {campo: request.GET.get(campo, "").strip() for campo in (
        "busca", "marca", "situacao", "tipo", "cambio", "combustivel",
        "ano", "preco_min", "preco_max", "ordem",
    )}
    veiculos = estoque
    if filtros["busca"]:
        for termo in filtros["busca"].split():
            veiculos = veiculos.filter(
                Q(marca__icontains=termo) | Q(modelo__icontains=termo)
                | Q(placa__icontains=termo)
            )

    def opcoes_distintas(campo):
        return [(str(v), str(v)) for v in estoque.exclude(**{campo: ""})
                .exclude(**{f"{campo}__isnull": True}).order_by(campo)
                .values_list(campo, flat=True).distinct()]

    opcoes = {
        "marca": opcoes_distintas("marca"),
        "situacao": Veiculo.Situacao.choices,
        "tipo": Veiculo.Tipo.choices,
        "cambio": Veiculo.Cambio.choices,
        "combustivel": opcoes_distintas("combustivel"),
        "ano": [(str(ano), str(ano)) for ano in estoque.order_by("-ano_modelo")
                .values_list("ano_modelo", flat=True).distinct()],
    }
    for campo in ("marca", "situacao", "tipo", "cambio", "combustivel", "ano"):
        valor = filtros[campo]
        if valor and valor in {str(v) for v, _ in opcoes[campo]}:
            if campo == "ano":
                veiculos = veiculos.filter(ano_modelo=int(valor))
            else:
                veiculos = veiculos.filter(**{f"{campo}__iexact": valor})
        elif valor:
            filtros[campo] = ""

    erros = []
    limites = {}
    for campo, label in (("preco_min", "Preço mínimo"), ("preco_max", "Preço máximo")):
        if filtros[campo]:
            try:
                valor = Decimal(filtros[campo].replace(",", "."))
                if not valor.is_finite() or not Decimal(0) <= valor <= Decimal("9999999999.99"):
                    raise ValueError
                if valor != valor.quantize(Decimal("0.01")):
                    raise ValueError
                limites[campo] = valor
                filtros[campo] = format(valor, "f")
            except (InvalidOperation, ValueError):
                erros.append(f"{label} inválido. Informe um valor positivo ou zero, com até duas casas decimais.")
                filtros[campo] = ""
    if limites.get("preco_min", Decimal(0)) > limites.get("preco_max", Decimal("9999999999.99")):
        erros.append("O preço mínimo não pode ser maior que o preço máximo.")
        veiculos = veiculos.none()
    else:
        if "preco_min" in limites:
            veiculos = veiculos.filter(preco_venda__gte=limites["preco_min"])
        if "preco_max" in limites:
            veiculos = veiculos.filter(preco_venda__lte=limites["preco_max"])

    ordenacoes = {
        "recentes": ("Mais recentes", ("-criado_em", "-pk")),
        "menor_preco": ("Menor preço", (F("preco_venda").asc(nulls_last=True), "pk")),
        "maior_preco": ("Maior preço", (F("preco_venda").desc(nulls_last=True), "pk")),
        "ano_novo": ("Ano mais novo", ("-ano_modelo", "-pk")),
        "ano_antigo": ("Ano mais antigo", ("ano_modelo", "pk")),
        "menor_km": ("Menor quilometragem", ("quilometragem", "pk")),
    }
    if filtros["ordem"] not in ordenacoes:
        filtros["ordem"] = "recentes"
    veiculos = veiculos.prefetch_related("fotos").order_by(*ordenacoes[filtros["ordem"]][1])
    opcoes["ordem"] = [(chave, dados[0]) for chave, dados in ordenacoes.items()]
    campos_select = [
        {"nome": chave, "rotulo": rotulo, "opcoes": opcoes[chave], "valor": filtros[chave]}
        for chave, rotulo in (("marca", "Marca"), ("situacao", "Situação"),
                              ("tipo", "Categoria"), ("cambio", "Câmbio"),
                              ("combustivel", "Combustível"), ("ano", "Ano do modelo"))
    ]
    return render(request, "core/vendedor_veiculos.html", {
        "veiculos": veiculos, "busca": filtros["busca"], "filtros": filtros,
        "campos_select": campos_select, "opcoes_ordem": opcoes["ordem"],
        "erros_filtro": erros,
        "filtros_ativos": any(v for k, v in filtros.items() if k not in ("busca", "ordem"))
                          or filtros["ordem"] != "recentes" or bool(erros),
    })


@perfil_requerido("VENDEDOR")
def detalhes_veiculo_vendedor_view(request, veiculo_id):
    """Ficha técnica do veículo sob a visão operacional do vendedor."""
    expirar_reservas_vencidas()

    veiculo = get_object_or_404(
        Veiculo.objects.prefetch_related("fotos"), pk=veiculo_id
    )
    dados = get_object_or_404(PerfilVendedor, usuario=request.user)

    return render(
        request,
        "core/vendedor_veiculo_detalhes.html",
        {
            "veiculo": veiculo,
            "fotos": veiculo.fotos.order_by("-principal", "ordem", "id"),
            "dados": dados,
            "reserva": veiculo.reserva_ativa,
            "fila": veiculo.propostas.filter(situacao=Proposta.Situacao.AGUARDANDO)
            .select_related("cliente", "vendedor")
            .order_by("criada_em", "pk"),
            "form_reserva": ReservaForm(),
            "form_cancelamento": CancelarReservaForm(),
            "form_preparacao": AlterarSituacaoForm(
                initial={"situacao": Veiculo.Situacao.DISPONIVEL}
            ),
            "form_venda": AlterarSituacaoForm(
                initial={"situacao": Veiculo.Situacao.VENDIDO}
            ),
            "form_entrega": AlterarSituacaoForm(
                initial={"situacao": Veiculo.Situacao.ENTREGUE}
            ),
            "procuras_compativeis": [
                p
                for p in Procura.abertas_compativeis(veiculo)
                if p.vendedor_id == request.user.pk
            ],
        },
    )


@login_required
def clientes_view(request):
    """Lista clientes cadastrados com filtro por nome, razão social, documento ou telefone."""
    busca = request.GET.get("busca", "").strip()
    clientes = Cliente.objects.prefetch_related("telefones")

    if busca:
        clientes = clientes.filter(
            Q(nome__icontains=busca)
            | Q(razao_social__icontains=busca)
            | Q(nome_fantasia__icontains=busca)
            | Q(cpf__icontains=busca)
            | Q(cnpj__icontains=busca)
            | Q(telefones__numero__icontains=busca)
        ).distinct()

    clientes = clientes.order_by("nome", "razao_social")

    return render(
        request,
        "core/vendedor_painel_clientes.html",
        {"clientes": clientes, "busca": busca},
    )


@login_required
def cadastrar_cliente_view(request):
    """Cadastra cliente PF ou PJ juntamente com seus telefones de contato."""
    cliente = Cliente()

    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        formset = TelefoneClienteFormSet(request.POST, instance=cliente)

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    cliente = form.save()
                    formset.instance = cliente
                    formset.save()

                messages.success(request, "Cliente cadastrado com sucesso.")
                return redirect("clientes")

            except IntegrityError:
                form.add_error(
                    None,
                    "Não foi possível cadastrar: o CPF ou CNPJ informado já está registrado.",
                )
    else:
        form = ClienteForm(instance=cliente)
        formset = TelefoneClienteFormSet(instance=cliente)

    return render(
        request,
        "core/vendedor_cliente_form.html",
        {
            "form": form,
            "formset": formset,
            "titulo": "Cadastrar cliente",
        },
    )


@login_required
def detalhes_cliente_view(request, cliente_id):
    """Exibe dados cadastrais, veículos adquiridos, propostas e vendas do cliente."""
    cliente = get_object_or_404(
        Cliente.objects.prefetch_related("telefones"),
        pk=cliente_id,
    )

    veiculos_comprados = (
        Veiculo.objects.filter(cliente_comprador=cliente)
        .prefetch_related("fotos")
        .order_by("-criado_em")
    )
    propostas = (
        _propostas_visiveis(request.user)
        .filter(cliente=cliente)
        .order_by("-criada_em")
    )
    vendas = (
        Venda.objects.filter(cliente=cliente, situacao=Venda.Situacao.FECHADA)
        .select_related("veiculo")
        .prefetch_related("etapas_documentacao")
        .order_by("-data", "-pk")
    )

    return render(
        request,
        "core/vendedor_cliente_detalhes.html",
        {
            "cliente": cliente,
            "veiculos_comprados": veiculos_comprados,
            "propostas": propostas,
            "vendas": vendas,
        },
    )


@login_required
def editar_cliente_view(request, cliente_id):
    """Atualiza os dados cadastrais e telefones de um cliente existente."""
    cliente = get_object_or_404(Cliente, pk=cliente_id)

    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        formset = TelefoneClienteFormSet(request.POST, instance=cliente)

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    cliente = form.save()
                    formset.instance = cliente
                    formset.save()

                messages.success(request, "Cliente atualizado com sucesso.")
                return redirect("detalhes_cliente", cliente_id=cliente.pk)

            except IntegrityError:
                form.add_error(
                    None,
                    "Não foi possível atualizar: o CPF ou CNPJ informado já está registrado.",
                )
    else:
        form = ClienteForm(instance=cliente)
        formset = TelefoneClienteFormSet(instance=cliente)

    return render(
        request,
        "core/vendedor_cliente_form.html",
        {
            "form": form,
            "formset": formset,
            "titulo": "Editar cliente",
        },
    )


@login_required
def desativar_cliente_view(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id)

    if request.method == "POST":
        cliente.desativar()
        messages.success(request, "Cliente desativado com sucesso.")
        return redirect("detalhes_cliente", cliente_id=cliente.pk)

    return render(
        request,
        "core/vendedor_cliente_confirmar_desativacao.html",
        {"cliente": cliente},
    )


@login_required
def reativar_cliente_view(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id)

    if request.method == "POST":
        cliente.reativar()
        messages.success(request, "Cliente reativado com sucesso.")
        return redirect("detalhes_cliente", cliente_id=cliente.pk)

    return render(
        request,
        "core/vendedor_cliente_confirmar_reativacao.html",
        {"cliente": cliente},
    )


@login_required
def deletar_cliente_view(request, cliente_id):
    """Exclui fisicamente o cliente apenas se não houver vínculos protegidos (vendas/propostas)."""
    cliente = get_object_or_404(Cliente, pk=cliente_id)

    if request.method == "POST":
        try:
            cliente.delete()
            messages.success(request, "Cliente excluído com sucesso.")
            return redirect("clientes")
        except ProtectedError:
            messages.error(
                request,
                "Não é possível excluir este cliente pois ele possui veículos com vendas registradas. "
                "Para inativá-lo, utilize a opção de desativação.",
            )
            return redirect("detalhes_cliente", cliente_id=cliente.id)

    return render(
        request,
        "core/vendedor_cliente_confirmar_exclusao.html",
        {"cliente": cliente},
    )


@perfil_requerido("VENDEDOR")
def propostas_view(request):
    """Lista as propostas do vendedor com filtros por cliente, veículo e situação."""
    expirar_reservas_vencidas()

    filtros_form = PropostaFiltroForm(request.GET or None)
    propostas = _propostas_visiveis(request.user)

    if filtros_form.is_valid():
        cliente = filtros_form.cleaned_data.get("cliente")
        veiculo = filtros_form.cleaned_data.get("veiculo")
        situacao = filtros_form.cleaned_data.get("situacao")
        vendedor = filtros_form.cleaned_data.get("vendedor")

        if cliente:
            propostas = propostas.filter(cliente=cliente)
        if veiculo:
            propostas = propostas.filter(veiculo=veiculo)
        if situacao:
            propostas = propostas.filter(situacao=situacao)
        if vendedor:
            propostas = propostas.filter(vendedor=vendedor)

    propostas = propostas.order_by("-criada_em")

    return render(
        request,
        "core/vendedor_painel_propostas.html",
        {"propostas": propostas, "filtros_form": filtros_form},
    )


def _proposta_form_view(request, proposta, titulo):
    """Fluxo compartilhado de criação e edição de proposta com composição de pagamento."""
    editando = proposta.pk is not None

    if request.method == "POST":
        form = PropostaForm(request.POST, instance=proposta)
        formset = ComposicaoFormSet(request.POST, instance=proposta)

        # O formset precisa conhecer o valor oferecido antes de validar o fechamento da soma.
        form_valido = form.is_valid()
        formset.valor_oferecido = form.cleaned_data.get("valor_oferecido")

        if form_valido and formset.is_valid():
            with transaction.atomic():
                proposta = form.save(commit=False)
                if not editando:
                    proposta.vendedor = request.user
                    contato_origem = _contato_origem_do_vendedor(request)
                    if (
                        contato_origem
                        and contato_origem.cliente_id == proposta.cliente_id
                    ):
                        proposta.contato_origem = contato_origem
                proposta.save(usuario=request.user)

                formset.instance = proposta
                formset.save()

            if proposta.situacao == Proposta.Situacao.AGUARDANDO:
                if proposta.reserva_aguardada:
                    prazo = timezone.localtime(proposta.reserva_aguardada.expira_em)
                    messages.warning(
                        request,
                        "Proposta registrada como AGUARDANDO: o veículo está reservado "
                        f"até {prazo:%d/%m/%Y %H:%M}. Ela só será ativada se a reserva vencer.",
                    )
                else:
                    messages.warning(
                        request,
                        "Proposta registrada como AGUARDANDO: já existe outra proposta ativa "
                        "para este veículo. Ela será ativada quando chegar sua vez na fila.",
                    )
            else:
                messages.success(
                    request,
                    "Proposta atualizada com sucesso."
                    if editando
                    else "Proposta registrada com sucesso.",
                )
            return redirect("detalhes_proposta", proposta_id=proposta.pk)
    else:
        initial = {}
        if not editando:
            for campo in ("cliente", "veiculo"):
                valor = request.GET.get(campo, "")
                if valor.isdigit():
                    initial[campo] = int(valor)

        form = PropostaForm(instance=proposta, initial=initial)
        formset = ComposicaoFormSet(instance=proposta)

    contato_origem = None if editando else _contato_origem_do_vendedor(request)
    contato_origem_id = contato_origem.pk if contato_origem else None

    return render(
        request,
        "core/vendedor_painel_proposta_formulario.html",
        {
            "form": form,
            "formset": formset,
            "titulo": titulo,
            "contato_origem_id": contato_origem_id,
            "proposta": proposta if editando else None,
            "veiculos_info": _dados_veiculos_para_js(form.fields["veiculo"].queryset),
            "avaliacoes_troca_info": {
                str(avaliacao.pk): {
                    "valor": str(avaliacao.valor_avaliado),
                    "descricao": (
                        f"{avaliacao.marca} {avaliacao.modelo} "
                        f"{avaliacao.ano_modelo} - {avaliacao.placa}"
                    ),
                }
                for avaliacao in AvaliacaoTroca.objects.all()
            },
        },
    )


@perfil_requerido("VENDEDOR")
def nova_proposta_view(request):
    expirar_reservas_vencidas()
    return _proposta_form_view(request, Proposta(), "Nova proposta")


@perfil_requerido("VENDEDOR")
def editar_proposta_view(request, proposta_id):
    expirar_reservas_vencidas()
    proposta = get_object_or_404(_propostas_visiveis(request.user), pk=proposta_id)

    if proposta.situacao == Proposta.Situacao.CANCELADA:
        messages.error(request, "Proposta cancelada não pode ser editada.")
        return redirect("detalhes_proposta", proposta_id=proposta.pk)

    if proposta.status_aprovacao in ("PENDENTE", "CONTRAPROPOSTA"):
        messages.error(
            request, "Esta proposta está em análise e não pode ser editada agora."
        )
        return redirect("detalhes_proposta", proposta_id=proposta.pk)

    if proposta.veiculo.situacao in (
        Veiculo.Situacao.VENDIDO,
        Veiculo.Situacao.ENTREGUE,
    ):
        messages.error(
            request,
            "O veículo desta proposta já foi vendido; a proposta não pode mais ser editada.",
        )
        return redirect("detalhes_proposta", proposta_id=proposta.pk)

    return _proposta_form_view(request, proposta, "Editar proposta")


@perfil_requerido("VENDEDOR")
def detalhes_proposta_view(request, proposta_id):
    """Exibe detalhes, composição, histórico de valores e ações disponíveis para a proposta."""
    expirar_reservas_vencidas()
    proposta = get_object_or_404(_propostas_visiveis(request.user), pk=proposta_id)

    autorizada = proposta.status_aprovacao in (
        Proposta.StatusAprovacao.NAO_NECESSARIA,
        Proposta.StatusAprovacao.APROVADA,
    )

    return render(
        request,
        "core/vendedor_painel_proposta_detalhe.html",
        {
            "proposta": proposta,
            "composicao": proposta.composicao.all(),
            "decisoes": proposta.decisoes.select_related("feito_por"),
            "historico": proposta.historico.select_related("alterado_por"),
            "reserva": (
                proposta.reserva_aguardada
                if proposta.situacao == Proposta.Situacao.AGUARDANDO
                else None
            ),
            "form_confirmacao": ConfirmarPropostaForm(),
            "venda": proposta.vendas.filter(situacao=Venda.Situacao.FECHADA).first(),
            "reserva_gerada": ReservaVeiculo.objects.filter(
                proposta_origem=proposta
            ).first(),
            "pode_fechar_venda": (
                proposta.situacao == Proposta.Situacao.ATIVA
                and autorizada
                and proposta.veiculo.situacao == Veiculo.Situacao.RESERVADO
                and ReservaVeiculo.objects.filter(
                    proposta_origem=proposta,
                    cancelada=False,
                ).exists()
                and not proposta.vendas.filter(situacao=Venda.Situacao.FECHADA).exists()
            ),
            "pode_confirmar": (
                proposta.situacao == Proposta.Situacao.ATIVA
                and autorizada
                and proposta.veiculo.situacao == Veiculo.Situacao.DISPONIVEL
                and not ReservaVeiculo.objects.filter(
                    proposta_origem=proposta
                ).exists()
            ),
        },
    )


@perfil_requerido("VENDEDOR")
def confirmar_proposta_view(request, proposta_id):
    """Confirma uma proposta ativa e autorizada, bloqueando o veículo por 24 horas."""
    if request.method != "POST":
        return redirect("detalhes_proposta", proposta_id=proposta_id)

    form = ConfirmarPropostaForm(request.POST)
    if not form.is_valid():
        erros_do_form_como_mensagens(request, form)
        return redirect("detalhes_proposta", proposta_id=proposta_id)

    try:
        with transaction.atomic():
            # Ordem de bloqueio: veículo primeiro, depois proposta.
            proposta_base = get_object_or_404(
                Proposta.objects.only("veiculo_id"),
                pk=proposta_id,
                vendedor=request.user,
            )
            veiculo = Veiculo.objects.select_for_update().get(
                pk=proposta_base.veiculo_id
            )
            proposta = Proposta.objects.select_for_update().get(
                pk=proposta_id,
                vendedor=request.user,
            )

            if proposta.situacao != Proposta.Situacao.ATIVA:
                raise ValidationError(
                    "Somente uma proposta ativa pode ser confirmada. "
                    "Propostas em espera devem aguardar sua vez."
                )
            if proposta.status_aprovacao not in (
                Proposta.StatusAprovacao.NAO_NECESSARIA,
                Proposta.StatusAprovacao.APROVADA,
            ):
                raise ValidationError(
                    "A proposta ainda não possui autorização para confirmação."
                )
            if veiculo.situacao != Veiculo.Situacao.DISPONIVEL:
                raise ValidationError("O veículo não está disponível para reserva.")
            if veiculo.reservas.filter(cancelada=False).exists():
                raise ValidationError(
                    "Este veículo já possui uma reserva não encerrada."
                )
            if ReservaVeiculo.objects.filter(proposta_origem=proposta).exists():
                raise ValidationError("Esta proposta já gerou uma reserva.")

            prazo = timezone.now() + timedelta(hours=24)
            reserva = ReservaVeiculo.objects.create(
                veiculo=veiculo,
                cliente=proposta.cliente,
                cliente_nome=proposta.cliente.nome_exibicao,
                cliente_contato="Contato registrado no cadastro do cliente",
                vendedor=request.user,
                proposta_origem=proposta,
                expira_em=prazo,
            )

            veiculo.situacao = Veiculo.Situacao.RESERVADO
            veiculo.status = Veiculo.Status.RESERVADO
            veiculo.save(update_fields=["situacao", "status"])

            HistoricoSituacaoVeiculo.objects.create(
                veiculo=veiculo,
                situacao_anterior=Veiculo.Situacao.DISPONIVEL,
                situacao_nova=Veiculo.Situacao.RESERVADO,
                alterado_por=request.user,
                motivo=f"Reserva gerada pela proposta #{proposta.pk}",
            )

    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    except IntegrityError:
        messages.error(
            request,
            "Não foi possível reservar: já existe uma reserva conflitante.",
        )
    else:
        messages.success(
            request,
            f"Proposta confirmada. Reserva #{reserva.pk} criada "
            f"até {timezone.localtime(reserva.expira_em):%d/%m/%Y %H:%M}.",
        )

    return redirect("detalhes_proposta", proposta_id=proposta_id)


@perfil_requerido("VENDEDOR")
def aceitar_contraproposta_view(request, proposta_id):
    if request.method != "POST":
        return redirect("propostas")

    proposta = get_object_or_404(_propostas_visiveis(request.user), pk=proposta_id)

    try:
        proposta.aceitar_contraproposta(request.user)
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    except PermissionDenied as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, "Contraproposta aceita com sucesso!")

    return redirect("detalhes_proposta", proposta_id=proposta.pk)


@perfil_requerido("VENDEDOR")
def recusar_contraproposta_view(request, proposta_id):
    if request.method != "POST":
        return redirect("propostas")

    proposta = get_object_or_404(_propostas_visiveis(request.user), pk=proposta_id)

    try:
        proposta.recusar_contraproposta(request.user)
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    except PermissionDenied as erro:
        messages.error(request, str(erro))
    else:
        messages.success(
            request,
            "Contraproposta recusada. Se quiser, registre uma nova proposta.",
        )

    return redirect("detalhes_proposta", proposta_id=proposta.pk)


@perfil_requerido("VENDEDOR")
def fechar_venda_view(request, proposta_id):
    """Efetiva o fechamento da venda a partir de uma proposta reservada."""
    if request.method != "POST":
        return redirect("detalhes_proposta", proposta_id=proposta_id)

    proposta = get_object_or_404(_propostas_visiveis(request.user), pk=proposta_id)

    try:
        venda = Venda.fechar(
            veiculo_id=proposta.veiculo_id,
            proposta_id=proposta.pk,
            cliente_id=proposta.cliente_id,
            usuario=request.user,
        )
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    except PermissionDenied as erro:
        messages.error(request, str(erro))
    except IntegrityError:
        messages.error(
            request,
            "Não foi possível fechar a venda: já existe uma venda fechada "
            "ou um veículo com a mesma placa/chassi no estoque.",
        )
    else:
        messages.success(
            request,
            f"Venda #{venda.pk} fechada com sucesso. O contrato já está disponível.",
        )

    return redirect("detalhes_proposta", proposta_id=proposta.pk)


@perfil_requerido("VENDEDOR")
def minhas_comissoes_view(request):
    """Exibe as comissões do vendedor nas vendas fechadas (sem expor a margem da loja)."""
    vendas = (
        Venda.objects.filter(
            vendedor=request.user,
            situacao=Venda.Situacao.FECHADA,
        )
        .select_related("veiculo", "cliente")
        .annotate(
            comissao=Sum(
                "lancamentos_financeiros__valor",
                filter=Q(
                    lancamentos_financeiros__tipo=LancamentoFinanceiro.Tipo.COMISSAO,
                    lancamentos_financeiros__excluido=False,
                ),
            )
        )
        .order_by("-data", "-pk")
    )

    total_comissao = sum(
        ((venda.comissao or Decimal("0.00")) for venda in vendas),
        Decimal("0.00"),
    )

    return render(
        request,
        "core/vendedor_painel_comissoes.html",
        {
            "vendas": vendas,
            "total_comissao": total_comissao,
            "perfil": getattr(request.user, "dados_vendedor", None),
        },
    )


@perfil_requerido("VENDEDOR")
@require_GET
def carteira_vendedor_view(request):
    carteira = calcular_carteira(vendedor=request.user)
    return render(request, "core/vendedor_carteira.html", {"carteira": carteira})


@perfil_requerido("VENDEDOR")
def registrar_contato_carteira_view(request, cliente_id):
    """Registra abordagem de recompra apenas se o cliente constar na carteira ativa do vendedor."""
    cliente = get_object_or_404(
        Cliente.objects.prefetch_related("telefones"),
        pk=cliente_id,
        ativo=True,
    )

    carteira = calcular_carteira(vendedor=request.user)
    linha = next(
        (item for item in carteira["linhas"] if item["cliente"].pk == cliente.pk),
        None,
    )

    if linha is None:
        raise PermissionDenied("Este cliente não pertence à sua carteira atual.")

    if request.method == "POST":
        form = ContatoCarteiraForm(request.POST)

        if form.is_valid():
            contato = form.save(commit=False)
            contato.cliente = cliente
            contato.vendedor = request.user

            try:
                contato.full_clean()
                with transaction.atomic():
                    contato.save()
                    if contato.resultado == ContatoCarteira.Resultado.QUER_VER_OPCOES:
                        Oportunidade.objects.create(
                            contato=contato,
                            cliente=cliente,
                            vendedor=request.user,
                        )
            except ValidationError as erro:
                adicionar_erros_de_validacao(form, erro)
            else:
                if contato.resultado == ContatoCarteira.Resultado.QUER_VER_OPCOES:
                    messages.success(
                        request,
                        "Contato registrado e oportunidade criada. "
                        "Registre a proposta para o cliente.",
                    )
                    return redirect(
                        f"{reverse('nova_proposta')}"
                        f"?cliente={cliente.pk}&contato={contato.pk}"
                    )
                messages.success(request, "Contato registrado com sucesso.")
                return redirect("carteira_vendedor")
    else:
        form = ContatoCarteiraForm()

    return render(
        request,
        "core/vendedor_carteira_contato.html",
        {"form": form, "cliente": cliente, "linha": linha},
    )


@perfil_requerido("VENDEDOR")
@require_GET
def procuras_vendedor_view(request):
    Procura.encerrar_vencidas()

    procuras = (
        Procura.objects.filter(vendedor=request.user)
        .select_related("cliente")
        .order_by("-criada_em", "-pk")
    )

    abertas = [p for p in procuras if p.esta_aberta]

    # Veículos do estoque que casam com cada procura aberta, hoje.
    disponiveis = list(_veiculos_disponiveis_para_procura())
    for procura in abertas:
        procura.compativeis = [
            v for v in disponiveis if procura.combina_com(v)
        ]

    return render(
        request,
        "core/vendedor_painel_procuras.html",
        {
            "abertas": abertas,
            "encerradas": [p for p in procuras if not p.esta_aberta],
        },
    )


@perfil_requerido("VENDEDOR")
def nova_procura_view(request):
    if request.method == "POST":
        form = ProcuraForm(request.POST)

        if form.is_valid():
            procura = form.save(commit=False)
            procura.vendedor = request.user

            try:
                procura.full_clean()
                procura.save()
            except ValidationError as erro:
                adicionar_erros_de_validacao(form, erro)
            else:
                messages.success(
                    request,
                    "Procura registrada. Você será avisado quando um "
                    "veículo compatível ficar disponível.",
                )
                return redirect("procuras_vendedor")
    else:
        initial = {}
        cliente_id = request.GET.get("cliente", "")
        if cliente_id.isdigit():
            initial["cliente"] = int(cliente_id)

        form = ProcuraForm(initial=initial)

    return render(request, "core/vendedor_procura_form.html", {"form": form})


@perfil_requerido("VENDEDOR")
@require_POST
def marcar_aviso_procura_lido_view(request, aviso_id):
    aviso = get_object_or_404(AvisoProcura, pk=aviso_id)

    try:
        aviso.marcar_como_lido(request.user)
    except PermissionDenied as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, "Aviso marcado como lido.")

    return redirect("painel_vendedor")


# ==============================================================================
# Administrativo
# ==============================================================================

@perfil_requerido("ADMINISTRATIVO")
def painel_administrativo_view(request):
    from .administrativo_metrics import contexto_administrativo
    return render(request, "core/administrativo_painel_inicio.html", contexto_administrativo())


@perfil_requerido("ADMINISTRATIVO")
def despesas_view(request):
    """Listagem de despesas e acesso ao cadastro por veículo."""
    busca = request.GET.get("busca", "").strip()
    despesas_ativas = LancamentoFinanceiro.objects.filter(
        tipo=LancamentoFinanceiro.Tipo.DESPESA, excluido=False
    )
    despesas = despesas_ativas.select_related("veiculo", "registrado_por")
    if busca:
        despesas = despesas.filter(
            Q(descricao__icontains=busca) | Q(veiculo__marca__icontains=busca)
            | Q(veiculo__modelo__icontains=busca) | Q(veiculo__placa__icontains=busca)
        )
    despesas = despesas.order_by("-data_lancamento", "-criado_em")
    veiculos = Veiculo.objects.order_by("marca", "modelo", "pk")
    selecionado = veiculos.filter(pk=request.GET.get("veiculo")).first() if request.GET.get("veiculo", "").isdigit() else veiculos.first()
    lista = despesas.filter(veiculo=selecionado) if selecionado else despesas.none()
    gastos = despesas_ativas.filter(veiculo=selecionado).aggregate(total=Sum("valor"))["total"] or 0
    return render(request, "core/administrativo_painel_despesas.html", {
        "selecionado": selecionado, "lista": lista, "gastos": gastos,
        "custo_total": (selecionado.custo_aquisicao or 0) + gastos if selecionado else 0,
        "form": DespesaForm(),
        "despesas": despesas,
        "busca": busca,
        "veiculos": Veiculo.objects.order_by("marca", "modelo"),
        "total_despesas": despesas_ativas.count(),
        "valor_total": despesas_ativas.aggregate(total=Sum("valor"))["total"] or 0,
        "veiculos_com_despesas": Veiculo.objects.filter(
            lancamentos__tipo=LancamentoFinanceiro.Tipo.DESPESA,
            lancamentos__excluido=False,
        ).distinct().count(),
    })


@perfil_requerido("ADMINISTRATIVO")
def despesas_veiculo_view(request, veiculo_id):
    veiculo = get_object_or_404(Veiculo, pk=veiculo_id)

    despesas = veiculo.lancamentos.filter(
        tipo=LancamentoFinanceiro.Tipo.DESPESA,
        excluido=False,
    ).order_by("-data_lancamento", "-criado_em")

    total_despesas = sum(despesa.valor for despesa in despesas)
    custo_aquisicao = veiculo.custo_aquisicao or 0
    custo_total = custo_aquisicao + total_despesas

    return render(
        request,
        "core/administrativo_despesas_veiculo.html",
        {
            "veiculo": veiculo,
            "despesas": despesas,
            "total_despesas": total_despesas,
            "custo_aquisicao": custo_aquisicao,
            "custo_total": custo_total,
        },
    )


@perfil_requerido("ADMINISTRATIVO")
def adicionar_despesa_view(request, veiculo_id):
    veiculo = get_object_or_404(Veiculo, pk=veiculo_id)

    if request.method == "POST":
        form = DespesaForm(request.POST)
        if form.is_valid():
            despesa = form.save(commit=False)
            despesa.veiculo = veiculo
            despesa.tipo = LancamentoFinanceiro.Tipo.DESPESA
            despesa.registrado_por = request.user
            despesa.save()
            if request.POST.get("origem") == "painel":
                from django.urls import reverse
                return redirect(reverse("despesas") + f"?veiculo={veiculo.pk}")
            return redirect("despesas_veiculo", veiculo_id=veiculo.id)
    else:
        form = DespesaForm()

    return render(
        request,
        "core/administrativo_adicionar_despesa.html",
        {"form": form, "veiculo": veiculo},
    )


@perfil_requerido("ADMINISTRATIVO")
def editar_despesa_view(request, despesa_id):
    despesa = get_object_or_404(
        LancamentoFinanceiro,
        pk=despesa_id,
        tipo=LancamentoFinanceiro.Tipo.DESPESA,
    )

    if request.method == "POST":
        form = DespesaEditarForm(request.POST, instance=despesa)
        if form.is_valid():
            despesa = form.save(commit=False)
            despesa.editado_por = request.user
            despesa.editado_em = timezone.now()
            despesa.save()
            return redirect("despesas_veiculo", veiculo_id=despesa.veiculo.id)
    else:
        form = DespesaEditarForm(instance=despesa)

    return render(
        request,
        "core/administrativo_editar_despesa.html",
        {"form": form, "despesa": despesa, "veiculo": despesa.veiculo},
    )


@perfil_requerido("ADMINISTRATIVO")
def excluir_despesa_view(request, despesa_id):
    """Realiza exclusão lógica (soft delete) mantendo rastreabilidade do usuário."""
    despesa = get_object_or_404(
        LancamentoFinanceiro,
        pk=despesa_id,
        tipo=LancamentoFinanceiro.Tipo.DESPESA,
        excluido=False,
    )

    if request.method == "POST":
        despesa.excluido = True
        despesa.excluido_por = request.user
        despesa.excluido_em = timezone.now()
        despesa.save(update_fields=["excluido", "excluido_por", "excluido_em"])
        return redirect("despesas_veiculo", veiculo_id=despesa.veiculo.id)

    return render(
        request,
        "core/administrativo_excluir_despesa.html",
        {"despesa": despesa, "veiculo": despesa.veiculo},
    )


@perfil_requerido("ADMINISTRATIVO")
def despesas_excluidas_veiculo_view(request, veiculo_id):
    veiculo = get_object_or_404(Veiculo, pk=veiculo_id)

    despesas = veiculo.lancamentos.filter(
        tipo=LancamentoFinanceiro.Tipo.DESPESA,
        excluido=True,
    ).order_by("-excluido_em")

    return render(
        request,
        "core/administrativo_despesas_excluidas_veiculo.html",
        {"veiculo": veiculo, "despesas": despesas},
    )


# ==============================================================================
# Gerente
# ==============================================================================

@perfil_requerido("GERENTE")
def painel_gerente_view(request):
    from .dashboard_metrics import manager_metrics
    return render(request, "core/gerente_painel_inicio.html", {"dashboard": manager_metrics()})


@perfil_requerido("GERENTE")
def vendedores_view(request):
    busca = request.GET.get("busca", "").strip()
    status = request.GET.get("status", "")

    vendedores = PerfilVendedor.objects.select_related("usuario").all()

    if busca:
        vendedores = vendedores.filter(
            Q(usuario__first_name__icontains=busca)
            | Q(usuario__last_name__icontains=busca)
            | Q(usuario__username__icontains=busca)
            | Q(usuario__email__icontains=busca)
        )

    if status == "ativo":
        vendedores = vendedores.filter(usuario__ativo=True)
    elif status == "inativo":
        vendedores = vendedores.filter(usuario__ativo=False)
    else:
        status = ""

    return render(
        request,
        "core/gerente_painel_vendedores.html",
        {
            "vendedores": vendedores,
            "busca": busca,
            "status_selecionado": status,
        },
    )


@perfil_requerido("GERENTE")
def cadastrar_vendedor_view(request):
    if request.method == "POST":
        form = VendedorCadastroForm(request.POST)

        if form.is_valid():
            cd = form.cleaned_data
            try:
                with transaction.atomic():
                    usuario = Usuario(
                        username=cd["username"],
                        email=cd["email"],
                        perfil=Usuario.Perfil.VENDEDOR,
                        ativo=True,
                    )
                    usuario.set_password(cd["senha"])
                    usuario.first_name = cd["nome"]
                    usuario.full_clean()
                    usuario.save()

                    PerfilVendedor.objects.create(
                        usuario=usuario,
                        percentual_comissao=cd["percentual_comissao"],
                        editado_por=request.user,
                    )

                messages.success(request, "Vendedor cadastrado com sucesso.")
                return redirect("vendedores")

            except ValidationError as erro:
                adicionar_erros_de_validacao(form, erro, renomear={"first_name": "nome"})
            except IntegrityError:
                form.add_error("username", "Esse usuário já está cadastrado.")
    else:
        form = VendedorCadastroForm()

    return render(request, "core/gerente_cadastrar_vendedor.html", {"form": form})


@perfil_requerido("GERENTE")
def editar_vendedor_view(request, vendedor_id):
    dados = get_object_or_404(
        PerfilVendedor.objects.select_related("usuario"),
        pk=vendedor_id,
    )
    usuario = dados.usuario

    if request.method == "POST":
        form = VendedorEdicaoForm(request.POST)

        if form.is_valid():
            cd = form.cleaned_data
            try:
                with transaction.atomic():
                    usuario.first_name = cd["nome"]
                    usuario.email = cd["email"]
                    usuario.ativo = cd["ativo"]
                    usuario.save()

                    dados.percentual_comissao = cd["percentual_comissao"]
                    dados.editado_por = request.user
                    dados.full_clean()
                    dados.save()

                messages.success(request, "Dados do vendedor atualizados com sucesso.")
                return redirect("vendedores")

            except ValidationError as erro:
                usuario.refresh_from_db()
                adicionar_erros_de_validacao(form, erro)
    else:
        form = VendedorEdicaoForm(
            initial={
                "nome": usuario.first_name,
                "email": usuario.email,
                "ativo": "true" if usuario.ativo else "false",
                "percentual_comissao": dados.percentual_comissao,
            }
        )

    return render(
        request,
        "core/gerente_editar_vendedor.html",
        {"dados": dados, "form": form},
    )


@perfil_requerido("GERENTE")
def veiculos_view(request):
    expirar_reservas_vencidas()

    busca = request.GET.get("busca", "").strip()
    situacao = request.GET.get("situacao", "")
    origem = request.GET.get("origem", "")
    ano_fabricacao = request.GET.get("ano_fabricacao", "")

    veiculos = Veiculo.objects.prefetch_related("fotos").all()

    if busca:
        veiculos = veiculos.filter(
            Q(marca__icontains=busca)
            | Q(modelo__icontains=busca)
            | Q(placa__icontains=busca)
        )

    if situacao in dict(Veiculo.Situacao.choices):
        veiculos = veiculos.filter(situacao=situacao)
    else:
        situacao = ""

    if origem in dict(Veiculo.Origem.choices):
        veiculos = veiculos.filter(origem=origem)
    else:
        origem = ""

    if ano_fabricacao:
        try:
            ano = int(ano_fabricacao)
            if 1900 <= ano <= 2100:
                veiculos = veiculos.filter(ano_fabricacao=ano)
            else:
                ano_fabricacao = ""
        except ValueError:
            ano_fabricacao = ""

    veiculos = veiculos.order_by("-criado_em")
    anos = (
        Veiculo.objects.order_by("-ano_fabricacao")
        .values_list("ano_fabricacao", flat=True)
        .distinct()
    )

    return render(
        request,
        "core/gerente_painel_veiculos.html",
        {
            "veiculos": veiculos,
            "busca": busca,
            "situacoes": Veiculo.Situacao.choices,
            "origens": Veiculo.Origem.choices,
            "situacao_selecionada": situacao,
            "origem_selecionada": origem,
            "ano_fabricacao_selecionado": ano_fabricacao,
            "anos": anos,
        },
    )


@perfil_requerido("GERENTE")
def cadastrar_veiculo_view(request):
    if request.method == "POST":
        form = VeiculoForm(request.POST, request.FILES)

        if form.is_valid():
            try:
                with transaction.atomic():
                    veiculo = form.save(commit=False)
                    veiculo.criado_por = request.user
                    veiculo.save()

                    for ordem, imagem in enumerate(form.cleaned_data["fotos"]):
                        FotoVeiculo.objects.create(
                            veiculo=veiculo,
                            imagem=imagem,
                            ordem=ordem,
                            principal=(ordem == 0),
                        )

                messages.success(request, "Veículo cadastrado com sucesso.")
                return redirect("veiculos")

            except IntegrityError:
                form.add_error(
                    None,
                    "Já existe um veículo com essa placa ou chassi no estoque.",
                )
    else:
        form = VeiculoForm()

    return render(request, "core/gerente_cadastrar_veiculo.html", {"form": form})


@perfil_requerido("GERENTE")
def detalhes_veiculo_view(request, veiculo_id):
    """Ficha gerencial completa do veículo com custos, reservas, fila e procuras compatíveis."""
    veiculo = get_object_or_404(
        Veiculo.objects.prefetch_related("fotos"), pk=veiculo_id
    )

    reserva = None
    if veiculo.situacao == Veiculo.Situacao.RESERVADO:
        reserva = ReservaVeiculo.objects.filter(
            veiculo=veiculo,
            cancelada=False,
        ).first()

        if reserva:
            reserva.expirar()
            reserva.refresh_from_db()
            if reserva.cancelada:
                veiculo.refresh_from_db()
                reserva = None

    despesas = veiculo.lancamentos.filter(
        tipo=LancamentoFinanceiro.Tipo.DESPESA, excluido=False
    ).order_by("-data_lancamento", "-criado_em")

    total_despesas = despesas.aggregate(total=Sum("valor"))["total"] or 0
    custo_total = (veiculo.custo_aquisicao or 0) + total_despesas

    historico_reservas = (
        ReservaVeiculo.objects.filter(veiculo=veiculo)
        .select_related(
            "cliente",
            "vendedor",
            "cancelada_por",
            "proposta_origem",
        )
        .order_by("-criada_em", "-pk")
    )

    return render(
        request,
        "core/gerente_detalhes_veiculo.html",
        {
            "veiculo": veiculo,
            "fotos": veiculo.fotos.order_by("-principal", "ordem", "pk"),
            "despesas": despesas,
            "total_despesas": total_despesas,
            "custo_total": custo_total,
            "ultimo_lancamento": despesas.first(),
            "ultimo_historico_preco": veiculo.historico_precos.order_by(
                "-alterado_em"
            ).first(),
            "reserva": reserva,
            "venda": veiculo.vendas.filter(situacao=Venda.Situacao.FECHADA).first(),
            "fila": veiculo.propostas.filter(situacao=Proposta.Situacao.AGUARDANDO)
            .select_related("cliente", "vendedor")
            .order_by("criada_em", "pk"),
            "clientes_list": Cliente.objects.filter(ativo=True).order_by(
                "nome", "razao_social"
            ),
            "form_reserva": ReservaForm(),
            "form_cancelamento": CancelarReservaForm(),
            "form_venda": AlterarSituacaoForm(
                initial={"situacao": Veiculo.Situacao.VENDIDO},
                veiculo=veiculo,
            ),
            "historico_reservas": historico_reservas,
            "propostas_pendentes": veiculo.propostas.filter(
                situacao__in=[
                    Proposta.Situacao.ATIVA,
                    Proposta.Situacao.AGUARDANDO,
                ]
            )
            .select_related("cliente", "vendedor")
            .order_by("criada_em", "pk"),
            "procuras_compativeis": Procura.abertas_compativeis(veiculo),
            "agora": timezone.now(),
        },
    )


@perfil_requerido("GERENTE")
def editar_veiculo_view(request, veiculo_id):
    """Atualiza dados do veículo, gerencia exclusão/reordenação de fotos e define a principal."""
    veiculo = get_object_or_404(Veiculo, pk=veiculo_id)

    if request.method == "POST":
        print("\n========== DEBUG GALERIA ==========")
        print("Foto principal:", request.POST.get("foto_principal"))
        print("Fotos para excluir:", request.POST.get("fotos_excluir"))
        print("Ordem das fotos:", request.POST.get("ordem_fotos"))
        print("===================================\n")

        form = EditarVeiculoForm(request.POST, request.FILES, instance=veiculo)

        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()

                    ids_excluir = [
                        int(foto_id)
                        for foto_id in request.POST.get("fotos_excluir", "").split(",")
                        if foto_id.strip().isdigit()
                    ]
                    FotoVeiculo.objects.filter(
                        veiculo=veiculo,
                        id__in=ids_excluir,
                    ).delete()

                    ids_ordem = list(
                        dict.fromkeys(
                            int(foto_id)
                            for foto_id in request.POST.get("ordem_fotos", "").split(",")
                            if foto_id.strip().isdigit()
                        )
                    )
                    fotos_ordenadas = list(veiculo.fotos.filter(id__in=ids_ordem))
                    fotos_por_id = {foto.id: foto for foto in fotos_ordenadas}

                    for ordem, foto_id in enumerate(ids_ordem):
                        foto = fotos_por_id.get(foto_id)
                        if foto is not None:
                            foto.ordem = ordem
                            foto.save(update_fields=["ordem"])

                    ids_ordenados = set(ids_ordem)
                    proxima_ordem = len(ids_ordenados & set(fotos_por_id))

                    for foto in veiculo.fotos.exclude(id__in=ids_ordenados).order_by(
                        "ordem", "id"
                    ):
                        foto.ordem = proxima_ordem
                        foto.save(update_fields=["ordem"])
                        proxima_ordem += 1

                    fotos_novas = form.cleaned_data.get("fotos") or []
                    ultima_foto = veiculo.fotos.order_by("-ordem", "-id").first()
                    proxima_ordem = veiculo.fotos.count()

                    for indice, imagem in enumerate(fotos_novas):
                        FotoVeiculo.objects.create(
                            veiculo=veiculo,
                            imagem=imagem,
                            ordem=proxima_ordem + indice,
                            principal=(ultima_foto is None and indice == 0),
                        )

                    # A foto principal ocupa sempre a posição zero.
                    principal_id = request.POST.get("foto_principal", "").strip()
                    principal = (
                        veiculo.fotos.filter(pk=int(principal_id)).first()
                        if principal_id.isdigit() else None
                    )
                    if principal is None:
                        principal = veiculo.fotos.order_by("ordem", "pk").first()
                    if principal is not None:
                        veiculo.fotos.exclude(pk=principal.pk).update(principal=False)
                        veiculo.fotos.filter(pk=principal.pk).update(principal=True)
                        restantes = list(
                            veiculo.fotos.exclude(pk=principal.pk).order_by("ordem", "pk")
                        )
                        FotoVeiculo.objects.filter(pk=principal.pk).update(ordem=0)
                        for posicao, foto in enumerate(restantes, start=1):
                            FotoVeiculo.objects.filter(pk=foto.pk).update(ordem=posicao)

                messages.success(request, "Veículo atualizado com sucesso.")
                return redirect("detalhes_veiculo", veiculo_id=veiculo.id)

            except IntegrityError:
                form.add_error(
                    None,
                    "Já existe um veículo com essa placa ou chassi no estoque.",
                )

    else:
        form = EditarVeiculoForm(instance=veiculo)

    return render(
        request,
        "core/gerente_editar_veiculo.html",
        {
            "form": form,
            "veiculo": veiculo,
            "fotos_existentes": veiculo.fotos.order_by("-principal", "ordem", "id"),
        },
    )


@perfil_requerido("GERENTE")
def alterar_preco_veiculo_view(request, veiculo_id):
    """Atualiza o preço de tabela, grava histórico e alerta se ficar abaixo do custo total."""
    veiculo = get_object_or_404(Veiculo, pk=veiculo_id)

    if veiculo.venda_fechada:
        return redirect("detalhes_veiculo", veiculo_id=veiculo.id)

    despesas = veiculo.lancamentos.filter(
        tipo=LancamentoFinanceiro.Tipo.DESPESA,
        excluido=False,
    )
    total_despesas = despesas.aggregate(total=Sum("valor"))["total"] or 0
    custo_total = (veiculo.custo_aquisicao or 0) + total_despesas

    if request.method == "POST":
        if veiculo.situacao in [Veiculo.Situacao.VENDIDO, Veiculo.Situacao.ENTREGUE]:
            messages.error(
                request, "O preço não pode ser alterado após a venda do veículo."
            )
            return redirect("detalhes_veiculo", veiculo_id=veiculo.id)

        form = PrecoVendaForm(request.POST)

        if form.is_valid():
            novo_preco = form.cleaned_data["preco_venda"]
            valor_anterior = veiculo.preco_venda or 0
            abaixo_do_custo = novo_preco < custo_total

            veiculo.preco_venda = novo_preco
            veiculo.save(update_fields=["preco_venda"])

            HistoricoPrecoVeiculo.objects.create(
                veiculo=veiculo,
                valor_anterior=valor_anterior,
                valor_novo=novo_preco,
                custo_total_no_momento=custo_total,
                abaixo_do_custo=abaixo_do_custo,
                alterado_por=request.user,
            )

            if abaixo_do_custo:
                messages.warning(
                    request,
                    "Atenção: o preço de venda está abaixo do custo total acumulado.",
                )

            return redirect("detalhes_veiculo", veiculo_id=veiculo.id)
    else:
        form = PrecoVendaForm(initial={"preco_venda": veiculo.preco_venda})

    return render(
        request,
        "core/gerente_alterar_preco.html",
        {"veiculo": veiculo, "custo_total": custo_total, "form": form},
    )


@perfil_requerido("GERENTE")
def aprovacoes_view(request):
    propostas = (
        Proposta.objects.filter(status_aprovacao=Proposta.StatusAprovacao.PENDENTE)
        .exclude(situacao=Proposta.Situacao.CANCELADA)
        .select_related(
            "cliente",
            "veiculo",
            "vendedor",
            "vendedor__dados_vendedor",
        )
        .order_by("criada_em")
    )
    return render(
        request,
        "core/gerente_painel_aprovacoes.html",
        {"propostas": propostas},
    )


@perfil_requerido("GERENTE")
def negociacoes_view(request):
    expirar_reservas_vencidas()

    propostas = Proposta.objects.select_related(
        "cliente", "veiculo", "vendedor"
    ).order_by("-criada_em")

    situacao = request.GET.get("situacao", "")
    if situacao in dict(Proposta.Situacao.choices):
        propostas = propostas.filter(situacao=situacao)
    else:
        situacao = ""

    indicadores = {
        "total": Proposta.objects.count(),
        "aguardando": Proposta.objects.filter(
            status_aprovacao=Proposta.StatusAprovacao.PENDENTE
        ).count(),
        "aprovadas": Proposta.objects.filter(
            status_aprovacao=Proposta.StatusAprovacao.APROVADA
        ).count(),
        "recusadas": Proposta.objects.filter(
            status_aprovacao=Proposta.StatusAprovacao.RECUSADA
        ).count(),
        "contrapropostas": Proposta.objects.filter(
            status_aprovacao=Proposta.StatusAprovacao.CONTRAPROPOSTA
        ).count(),
    }

    return render(
        request,
        "core/gerente_painel_negociacoes.html",
        {
            "propostas": propostas,
            "situacoes": Proposta.Situacao.choices,
            "situacao_selecionada": situacao,
            "indicadores": indicadores,
        },
    )


@perfil_requerido("GERENTE")
def decidir_proposta_view(request, proposta_id):
    """Registra aprovação, recusa ou contraproposta do gerente para descontos acima da alçada."""
    proposta = get_object_or_404(
        Proposta.objects.select_related(
            "cliente",
            "veiculo",
            "vendedor",
            "vendedor__dados_vendedor",
        ),
        pk=proposta_id,
    )

    if request.method == "POST":
        form = DecisaoPropostaForm(request.POST)

        if form.is_valid():
            cd = form.cleaned_data
            try:
                with transaction.atomic():
                    # Ordem de bloqueio: veículo primeiro, depois proposta.
                    veiculo_id = (
                        Proposta.objects.only("veiculo_id")
                        .get(pk=proposta_id)
                        .veiculo_id
                    )
                    Veiculo.objects.select_for_update().get(pk=veiculo_id)
                    proposta = Proposta.objects.select_for_update().get(
                        pk=proposta_id,
                        veiculo_id=veiculo_id,
                    )

                    proposta.decidir(
                        request.user,
                        cd["acao"],
                        parecer=cd["parecer"],
                        novo_valor=cd["novo_valor"],
                    )

                messages.success(request, "Decisão registrada com sucesso.")
                return redirect("negociacoes_gerente")

            except ValidationError as erro:
                adicionar_erros_de_validacao(form, erro)
            except PermissionDenied as erro:
                messages.error(request, str(erro))
                return redirect("negociacoes_gerente")
    else:
        form = DecisaoPropostaForm()

    proposta = get_object_or_404(
        Proposta.objects.select_related(
            "cliente",
            "veiculo",
            "vendedor",
            "vendedor__dados_vendedor",
        ),
        pk=proposta_id,
    )

    return render(
        request,
        "core/gerente_decidir_proposta.html",
        {
            "proposta": proposta,
            "perfil": proposta.alcada_veiculo,
            "decisoes": proposta.decisoes.select_related("feito_por"),
            "historico": proposta.historico.select_related("alterado_por"),
            "form": form,
        },
    )


@perfil_requerido("GERENTE")
def recusar_proposta_fila_view(request, proposta_id):
    """Encerra diretamente uma proposta ativa ou em espera sem reserva vinculada."""
    if request.method != "POST":
        return redirect("negociacoes_gerente")

    motivo = request.POST.get("motivo", "").strip()
    if not motivo:
        messages.error(request, "Informe o motivo da recusa.")
        return redirect("negociacoes_gerente")

    proposta_base = get_object_or_404(
        Proposta.objects.only("veiculo_id"),
        pk=proposta_id,
    )
    veiculo_id = proposta_base.veiculo_id

    try:
        with transaction.atomic():
            # Ordem de bloqueio: veículo primeiro, depois proposta.
            veiculo = Veiculo.objects.select_for_update().get(pk=veiculo_id)
            proposta = Proposta.objects.select_for_update().get(
                pk=proposta_id,
                veiculo=veiculo,
            )

            if proposta.situacao not in (
                Proposta.Situacao.ATIVA,
                Proposta.Situacao.AGUARDANDO,
            ):
                raise ValidationError(
                    "Somente propostas ativas ou aguardando "
                    "podem ser recusadas por este fluxo."
                )

            if ReservaVeiculo.objects.filter(proposta_origem=proposta).exists():
                raise ValidationError(
                    "Esta proposta possui uma reserva vinculada. "
                    "Utilize o cancelamento de reserva."
                )

            era_ativa = proposta.situacao == Proposta.Situacao.ATIVA

            DecisaoProposta.objects.create(
                proposta=proposta,
                tipo=DecisaoProposta.Tipo.RECUSA_FILA,
                valor_referencia=proposta.valor_oferecido,
                desconto_percentual_no_momento=proposta.desconto_percentual,
                alcada_no_momento=proposta._alcada_texto(),
                parecer=motivo,
                feito_por=request.user,
            )

            proposta.situacao = Proposta.Situacao.CANCELADA
            proposta.save(update_fields=["situacao", "atualizada_em"])

            if era_ativa:
                Proposta.ativar_aguardando(veiculo.pk)

    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    else:
        messages.success(request, "Proposta recusada com sucesso.")

    return redirect("detalhes_veiculo", veiculo_id=veiculo_id)


@perfil_requerido("GERENTE")
def avaliacoes_troca_view(request):
    busca = request.GET.get("busca", "").strip()

    avaliacoes = (
        AvaliacaoTroca.objects.select_related("avaliado_por")
        .prefetch_related("fotos")
        .order_by("-criado_em")
    )

    if busca:
        avaliacoes = avaliacoes.filter(
            Q(placa__icontains=busca)
            | Q(marca__icontains=busca)
            | Q(modelo__icontains=busca)
        )

    return render(
        request,
        "core/gerente_painel_avaliacoes_troca.html",
        {"avaliacoes": avaliacoes, "busca": busca},
    )


@perfil_requerido("GERENTE")
def nova_avaliacao_troca_view(request):
    if request.method == "POST":
        form = AvaliacaoTrocaForm(request.POST, request.FILES)

        if form.is_valid():
            try:
                with transaction.atomic():
                    avaliacao = form.save(commit=False)
                    avaliacao.avaliado_por = request.user
                    avaliacao.full_clean()
                    avaliacao.save()

                    for ordem, imagem in enumerate(form.cleaned_data["fotos"]):
                        FotoAvaliacaoTroca.objects.create(
                            avaliacao=avaliacao,
                            imagem=imagem,
                            ordem=ordem,
                        )

                messages.success(
                    request, "Avaliação de troca cadastrada com sucesso."
                )
                return redirect("avaliacoes_troca")

            except ValidationError as erro:
                adicionar_erros_de_validacao(form, erro)
    else:
        form = AvaliacaoTrocaForm()

    return render(
        request,
        "core/gerente_cadastrar_avaliacao_troca.html",
        {
            "form": form,
            "avaliacao": None,
            "titulo": "Nova avaliação de troca",
        },
    )


@perfil_requerido("GERENTE")
def editar_avaliacao_troca_view(request, avaliacao_id):
    """Atualiza o laudo de troca e sincroniza exclusão, reordenação e inclusão de fotos."""
    avaliacao = get_object_or_404(
        AvaliacaoTroca.objects.prefetch_related("fotos"),
        pk=avaliacao_id,
    )

    if request.method == "POST":
        form = AvaliacaoTrocaForm(request.POST, request.FILES, instance=avaliacao)

        if form.is_valid():
            try:
                fotos_removidas_texto = (
                    request.POST.get("fotos_removidas") or "[]"
                ).strip()
                fotos_removidas = json.loads(fotos_removidas_texto)

                ordem_fotos_texto = (
                    request.POST.get("ordem_fotos_existentes") or "[]"
                ).strip()
                ordem_fotos = json.loads(ordem_fotos_texto)

                if not isinstance(ordem_fotos, list):
                    raise ValueError("Ordem das fotos inválida.")
                if any(
                    isinstance(foto_id, bool) or not str(foto_id).isdigit()
                    for foto_id in ordem_fotos
                ):
                    raise ValueError("Identificadores de fotos inválidos.")

                ids_ordenados = [int(foto_id) for foto_id in ordem_fotos]
                if len(ids_ordenados) != len(set(ids_ordenados)):
                    raise ValueError("Existem fotos repetidas na ordenação.")

                if not isinstance(fotos_removidas, list):
                    raise ValueError("Lista de fotos inválida.")
                if any(
                    isinstance(foto_id, bool) or not str(foto_id).isdigit()
                    for foto_id in fotos_removidas
                ):
                    raise ValueError("Identificadores de fotos inválidos.")

                ids_removidos = [int(foto_id) for foto_id in fotos_removidas]

                with transaction.atomic():
                    avaliacao = form.save(commit=False)
                    avaliacao.full_clean()
                    avaliacao.save()

                    FotoAvaliacaoTroca.objects.filter(
                        avaliacao=avaliacao,
                        id__in=ids_removidos,
                    ).delete()

                    if ids_ordenados:
                        fotos_existentes = list(
                            FotoAvaliacaoTroca.objects.filter(avaliacao=avaliacao)
                        )
                        fotos_por_id = {foto.id: foto for foto in fotos_existentes}

                        if set(ids_ordenados) != set(fotos_por_id):
                            raise ValidationError(
                                "A ordem das fotos está desatualizada. "
                                "Atualize a página e tente novamente."
                            )

                        for posicao, foto_id in enumerate(ids_ordenados):
                            fotos_por_id[foto_id].ordem = posicao

                        FotoAvaliacaoTroca.objects.bulk_update(
                            [fotos_por_id[foto_id] for foto_id in ids_ordenados],
                            ["ordem"],
                        )

                    ultima_ordem = (
                        FotoAvaliacaoTroca.objects.filter(avaliacao=avaliacao).aggregate(
                            maior=Max("ordem")
                        )["maior"]
                    )
                    proxima_ordem = ultima_ordem + 1 if ultima_ordem is not None else 0

                    for imagem in form.cleaned_data["fotos"]:
                        FotoAvaliacaoTroca.objects.create(
                            avaliacao=avaliacao,
                            imagem=imagem,
                            ordem=proxima_ordem,
                        )
                        proxima_ordem += 1

                messages.success(
                    request, "Avaliação de troca atualizada com sucesso."
                )
                return redirect("avaliacoes_troca")

            except (ValueError, TypeError, json.JSONDecodeError):
                form.add_error(
                    None, "Não foi possível processar as fotos removidas."
                )
            except ValidationError as erro:
                adicionar_erros_de_validacao(form, erro)
    else:
        form = AvaliacaoTrocaForm(instance=avaliacao)

    return render(
        request,
        "core/gerente_editar_avaliacao_troca.html",
        {
            "form": form,
            "avaliacao": avaliacao,
            "titulo": "Editar avaliação de troca",
        },
    )


@perfil_requerido("GERENTE")
def cancelar_venda_view(request, venda_id):
    venda = get_object_or_404(Venda, pk=venda_id)

    if request.method != "POST":
        return redirect("detalhes_venda", venda_id=venda.pk)

    form = CancelarVendaForm(request.POST)
    if not form.is_valid():
        erros_do_form_como_mensagens(request, form)
        return redirect("detalhes_venda", venda_id=venda.pk)

    try:
        venda.cancelar(request.user, form.cleaned_data["motivo"])
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    except PermissionDenied as erro:
        messages.error(request, str(erro))
    except IntegrityError:
        messages.error(
            request,
            "Não foi possível devolver o veículo ao estoque: já existe outro "
            "veículo ativo com a mesma placa ou chassi.",
        )
    else:
        aviso = ""
        if venda.pagamentos.filter(tipo="TROCA").exists():
            aviso = (
                " Atenção: o veículo recebido na troca continua no estoque "
                "e precisa ser tratado manualmente."
            )

        messages.success(
            request,
            "Venda cancelada. O veículo voltou ao estoque como disponível." + aviso,
        )

    return redirect("detalhes_venda", venda_id=venda.pk)


@perfil_requerido("GERENTE")
def margens_view(request):
    """Exibe o relatório gerencial de margens reais recalculadas dinamicamente."""
    somente_negativas = request.GET.get("negativas") == "1"

    vendas = (
        Venda.objects.filter(situacao=Venda.Situacao.FECHADA)
        .select_related("veiculo", "cliente", "vendedor")
        .order_by("-data", "-pk")
    )

    linhas = [{"venda": venda, "margem": venda.calcular_margem()} for venda in vendas]

    total_vendas = len(linhas)
    total_negativas = sum(1 for linha in linhas if linha["margem"]["negativa"])
    total_margem = sum(
        (linha["margem"]["margem"] for linha in linhas), Decimal("0.00")
    )

    if somente_negativas:
        linhas = [linha for linha in linhas if linha["margem"]["negativa"]]

    return render(
        request,
        "core/gerente_painel_margens.html",
        {
            "linhas": linhas,
            "somente_negativas": somente_negativas,
            "total_vendas": total_vendas,
            "total_negativas": total_negativas,
            "total_margem": total_margem,
            "calculada_em": timezone.now(),
        },
    )


@perfil_requerido("GERENTE")
@require_GET
def historico_veiculo_view(request, veiculo_id):
    """Exibe a linha do tempo auditável do veículo (somente leitura, sem efeitos colaterais)."""
    veiculo = get_object_or_404(Veiculo, pk=veiculo_id)

    return render(
        request,
        "core/gerente_historico_veiculo.html",
        {
            "veiculo": veiculo,
            "eventos": linha_do_tempo_veiculo(veiculo),
        },
    )


@perfil_requerido("GERENTE")
@require_GET
def historico_cliente_view(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id)

    return render(
        request,
        "core/gerente_historico_cliente.html",
        {
            "cliente": cliente,
            "resumo": resumo_cliente(cliente),
            "hoje": timezone.localdate(),
        },
    )


@perfil_requerido("GERENTE")
@require_GET
def carteira_gerente_view(request):
    carteira = calcular_carteira()
    return render(request, "core/gerente_carteira.html", {"carteira": carteira})


@perfil_requerido("GERENTE")
def configurar_carteira_view(request):
    configuracao = obter_configuracao_carteira()

    if request.method == "POST":
        form = ConfiguracaoCarteiraForm(request.POST, instance=configuracao)

        if form.is_valid():
            configuracao = form.save(commit=False)
            configuracao.atualizado_por = request.user
            configuracao.save()

            messages.success(request, "Prazo da carteira atualizado com sucesso.")
            return redirect("carteira_gerente")
    else:
        form = ConfiguracaoCarteiraForm(instance=configuracao)

    return render(
        request,
        "core/gerente_configurar_carteira.html",
        {"form": form, "configuracao": configuracao},
    )


@perfil_requerido("GERENTE")
@require_GET
def procuras_gerente_view(request):
    Procura.encerrar_vencidas()

    situacao = request.GET.get("situacao", "")
    procuras = Procura.objects.select_related("cliente", "vendedor")

    if situacao in dict(Procura.Situacao.choices):
        procuras = procuras.filter(situacao=situacao)
    else:
        situacao = ""

    # Relatório: o que é procurado e não existe no pátio.
    disponiveis = list(_veiculos_disponiveis_para_procura())
    sem_estoque = {}
    for procura in Procura.objects.filter(
        situacao=Procura.Situacao.ABERTA
    ).select_related("cliente"):
        if any(procura.combina_com(v) for v in disponiveis):
            continue
        item = sem_estoque.setdefault(
            procura.resumo(), {"resumo": procura.resumo(), "quantidade": 0}
        )
        item["quantidade"] += 1
    procuras_sem_estoque = sorted(
        sem_estoque.values(), key=lambda i: (-i["quantidade"], i["resumo"])
    )

    return render(
        request,
        "core/gerente_painel_procuras.html",
        {
            "procuras_sem_estoque": procuras_sem_estoque,
            "procuras": procuras.order_by("-criada_em", "-pk"),
            "situacoes": Procura.Situacao.choices,
            "situacao_selecionada": situacao,
            "total_abertas": Procura.objects.filter(
                situacao=Procura.Situacao.ABERTA
            ).count(),
        },
    )


# ==============================================================================
# Operações Compartilhadas
# ==============================================================================

@perfil_requerido("GERENTE")
def reservar_veiculo_view(request, veiculo_id):
    """Cria reserva manual de 24 horas para veículo disponível sem propostas pendentes."""
    if request.method != "POST":
        return redirect("detalhes_veiculo", veiculo_id=veiculo_id)

    form = ReservaForm(request.POST)
    if not form.is_valid():
        erros_do_form_como_mensagens(request, form)
        return redirect("detalhes_veiculo", veiculo_id=veiculo_id)

    cliente_nome = form.cleaned_data["cliente_nome"]
    cliente_contato = form.cleaned_data["cliente_contato"]

    try:
        with transaction.atomic():
            veiculo = Veiculo.objects.select_for_update().get(pk=veiculo_id)

            for antiga in veiculo.reservas.filter(
                cancelada=False, expira_em__lte=timezone.now()
            ):
                antiga.expirar()

            veiculo.refresh_from_db()

            propostas_pendentes = Proposta.objects.filter(
                veiculo=veiculo,
                situacao__in=[
                    Proposta.Situacao.ATIVA,
                    Proposta.Situacao.AGUARDANDO,
                ],
            ).exists()

            if propostas_pendentes:
                messages.error(
                    request,
                    "Não é possível reservar este veículo manualmente "
                    "enquanto existirem propostas pendentes. "
                    "Resolva ou recuse as propostas antes de continuar.",
                )
                return redirect("detalhes_veiculo", veiculo_id=veiculo.pk)

            reserva_existente = veiculo.reservas.filter(cancelada=False).exists()
            if (
                veiculo.situacao != Veiculo.Situacao.DISPONIVEL
                or reserva_existente
            ):
                messages.error(
                    request,
                    "Apenas veículos disponíveis e sem reserva ativa podem ser reservados.",
                )
                return redirect("detalhes_veiculo", veiculo_id=veiculo.id)

            ReservaVeiculo.objects.create(
                veiculo=veiculo,
                cliente=form.cleaned_data.get("cliente"),
                cliente_nome=cliente_nome,
                cliente_contato=cliente_contato,
                vendedor=request.user,
                expira_em=timezone.now() + timedelta(hours=24),
            )

            situacao_anterior = veiculo.situacao
            veiculo.situacao = Veiculo.Situacao.RESERVADO
            veiculo.status = Veiculo.Status.RESERVADO
            veiculo.save(update_fields=["situacao", "status"])

            HistoricoSituacaoVeiculo.objects.create(
                veiculo=veiculo,
                situacao_anterior=situacao_anterior,
                situacao_nova=Veiculo.Situacao.RESERVADO,
                alterado_por=request.user,
                motivo="Reserva do veículo",
            )

    except Veiculo.DoesNotExist:
        return redirect("lista_veiculos")
    except IntegrityError:
        messages.error(request, "Este veículo já possui uma reserva ativa.")
        return redirect("detalhes_veiculo", veiculo_id=veiculo_id)

    messages.success(request, "Veículo reservado com sucesso.")
    return redirect("detalhes_veiculo", veiculo_id=veiculo_id)


@perfil_requerido("GERENTE")
def cancelar_reserva_view(request, reserva_id):
    """Encerra reserva vigente, cancela proposta vinculada e promove a próxima da fila."""
    reserva_base = get_object_or_404(ReservaVeiculo, pk=reserva_id)

    if request.method != "POST":
        return redirect("detalhes_veiculo", veiculo_id=reserva_base.veiculo_id)

    form = CancelarReservaForm(request.POST)
    if not form.is_valid():
        erros_do_form_como_mensagens(request, form)
        return redirect("detalhes_veiculo", veiculo_id=reserva_base.veiculo_id)

    try:
        with transaction.atomic():
            veiculo = Veiculo.objects.select_for_update().get(
                pk=reserva_base.veiculo_id
            )
            reserva = ReservaVeiculo.objects.select_for_update().get(pk=reserva_id)

            if reserva.cancelada:
                raise ValidationError("Esta reserva já foi encerrada.")
            if reserva.expira_em <= timezone.now():
                raise ValidationError(
                    "Esta reserva já venceu. "
                    "Atualize a página para processar a expiração."
                )
            if veiculo.situacao != Veiculo.Situacao.RESERVADO:
                raise ValidationError("O veículo não está em situação de reserva.")

            agora = timezone.now()
            reserva.cancelada = True
            reserva.cancelada_em = agora
            reserva.cancelada_por = request.user
            reserva.motivo_cancelamento = form.cleaned_data["motivo"]
            reserva.save(
                update_fields=[
                    "cancelada",
                    "cancelada_em",
                    "cancelada_por",
                    "motivo_cancelamento",
                ]
            )

            if reserva.proposta_origem_id:
                Proposta.objects.filter(pk=reserva.proposta_origem_id).update(
                    situacao=Proposta.Situacao.CANCELADA,
                    atualizada_em=agora,
                )

            veiculo.situacao = Veiculo.Situacao.DISPONIVEL
            veiculo.status = Veiculo.Status.DISPONIVEL
            veiculo.save(update_fields=["situacao", "status"])

            HistoricoSituacaoVeiculo.objects.create(
                veiculo=veiculo,
                situacao_anterior=Veiculo.Situacao.RESERVADO,
                situacao_nova=Veiculo.Situacao.DISPONIVEL,
                alterado_por=request.user,
                motivo=form.cleaned_data["motivo"],
            )

            Proposta.ativar_aguardando(veiculo.pk)

    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    else:
        messages.success(
            request, "Reserva cancelada e veículo liberado com sucesso."
        )

    return redirect("detalhes_veiculo", veiculo_id=reserva_base.veiculo_id)


@perfil_requerido("GERENTE", "ADMINISTRATIVO")
def alterar_situacao_veiculo_view(request, veiculo_id):
    """Gerencia transições de situação do veículo, fechamento de venda e disparo de avisos."""
    veiculo = get_object_or_404(Veiculo, pk=veiculo_id)

    if request.method != "POST":
        return redirect("detalhes_veiculo", veiculo_id=veiculo.id)

    form = AlterarSituacaoForm(request.POST, veiculo=veiculo)
    if not form.is_valid():
        erros_do_form_como_mensagens(request, form)
        return redirect("detalhes_veiculo", veiculo_id=veiculo.id)

    nova_situacao = form.cleaned_data["situacao"]
    motivo = form.cleaned_data["motivo"]

    if nova_situacao == Veiculo.Situacao.VENDIDO:
        try:
            venda = Venda.fechar(
                veiculo_id=veiculo.pk,
                proposta_id=form.cleaned_data["proposta"].pk,
                cliente_id=form.cleaned_data["cliente"].pk,
                usuario=request.user,
                motivo=motivo,
            )
        except ValidationError as erro:
            messages.error(request, " ".join(erro.messages))
        except PermissionDenied as erro:
            messages.error(request, str(erro))
        except IntegrityError:
            messages.error(
                request,
                "Não foi possível fechar a venda: já existe uma venda fechada ou "
                "um veículo com a mesma placa/chassi no estoque.",
            )
        else:
            messages.success(request, f"Venda #{venda.pk} registrada com sucesso.")

        return redirect("detalhes_veiculo", veiculo_id=veiculo.id)

    transicoes_permitidas = {
        Veiculo.Situacao.PREPARACAO: [Veiculo.Situacao.DISPONIVEL],
    }

    if nova_situacao not in transicoes_permitidas.get(veiculo.situacao, []):
        messages.error(request, "Essa transição de situação não é permitida.")
        return redirect("detalhes_veiculo", veiculo_id=veiculo.id)

    situacao_anterior = veiculo.situacao
    veiculo.situacao = nova_situacao
    veiculo.status = (
        Veiculo.Status.VENDIDO
        if nova_situacao == Veiculo.Situacao.ENTREGUE
        else Veiculo.Status.DISPONIVEL
    )
    veiculo.save(update_fields=["situacao", "status"])

    HistoricoSituacaoVeiculo.objects.create(
        veiculo=veiculo,
        situacao_anterior=situacao_anterior,
        situacao_nova=nova_situacao,
        alterado_por=request.user,
        motivo=motivo or None,
    )

    avisos = 0
    if nova_situacao == Veiculo.Situacao.DISPONIVEL:
        avisos = Procura.cruzar_com_veiculo(veiculo)

    messages.success(request, "Situação do veículo alterada com sucesso.")
    if avisos:
        messages.info(
            request,
            f"{avisos} vendedor(es) foram avisados de procuras compatíveis.",
        )
    return redirect("detalhes_veiculo", veiculo_id=veiculo.id)


@perfil_requerido("GERENTE", "ADMINISTRATIVO")
def detalhes_venda_view(request, venda_id):
    venda = get_object_or_404(
        Venda.objects.select_related(
            "proposta",
            "veiculo",
            "cliente",
            "vendedor",
            "fechada_por",
            "cancelada_por",
        ),
        pk=venda_id,
    )

    return render(
        request,
        "core/gerente_detalhes_venda.html",
        {
            "base_template": "core/administrativo_base.html" if request.user.is_administrativo() else "core/gerente_base.html",
            "venda": venda,
            "pagamentos": venda.pagamentos.all(),
            "form_cancelamento": CancelarVendaForm(),
            "margem": venda.calcular_margem() if request.user.is_gerente() else None,
        },
    )


@perfil_requerido("GERENTE", "ADMINISTRATIVO", "VENDEDOR")
def contrato_venda_view(request, venda_id):
    vendas = Venda.objects.select_related("veiculo", "cliente", "vendedor")
    if request.user.is_vendedor():
        vendas = vendas.filter(vendedor=request.user)

    venda = get_object_or_404(vendas, pk=venda_id)
    return render(
        request,
        "core/gerente_contrato_venda.html",
        {
            "base_template": "core/administrativo_base.html" if request.user.is_administrativo() else "core/gerente_base.html",
            "venda": venda,
            "cliente": venda.cliente,
            "veiculo": venda.veiculo,
            "pagamentos": venda.pagamentos.all(),
            "entrada": venda.entrada,
            "financiamento": venda.financiamento,
        },
    )


@perfil_requerido("GERENTE", "ADMINISTRATIVO")
def registrar_entrega_view(request, venda_id):
    venda = get_object_or_404(
        Venda.objects.select_related("veiculo", "cliente", "vendedor"),
        pk=venda_id,
    )
    entrega_existente = EntregaVeiculo.objects.filter(venda=venda).first()

    if request.method == "POST":
        form = EntregaVeiculoForm(request.POST)

        if form.is_valid():
            try:
                venda.registrar_entrega(
                    usuario=request.user,
                    data_entrega=form.cleaned_data["data_entrega"],
                    checklist=form.checklist(),
                    observacoes=form.cleaned_data["observacoes"],
                )
            except ValidationError as erro:
                for mensagem in erro.messages:
                    form.add_error(None, mensagem)
            except PermissionDenied as erro:
                messages.error(request, str(erro))
                return redirect("detalhes_venda", venda_id=venda.pk)
            except IntegrityError:
                form.add_error(None, "Esta entrega já foi registrada.")
            else:
                messages.success(
                    request, "Entrega registrada. O veículo foi entregue."
                )
                return redirect("entregas_administrativo") if request.user.is_administrativo() else redirect("detalhes_venda", venda_id=venda.pk)
    else:
        form = EntregaVeiculoForm()

    return render(
        request,
        "core/gerente_registrar_entrega.html",
        {
            "base_template": "core/administrativo_base.html" if request.user.is_administrativo() else "core/gerente_base.html",
            "venda": venda,
            "form": form,
            "etapas": venda.etapas_documentacao.all(),
            "entrega": entrega_existente,
            "pode_entregar": (
                venda.esta_fechada
                and venda.veiculo.situacao == Veiculo.Situacao.VENDIDO
                and entrega_existente is None
                and set(venda.etapas_documentacao.filter(situacao=EtapaDocumentacao.Situacao.CONCLUIDA).values_list("tipo", flat=True)) == set(EtapaDocumentacao.Tipo.values)
            ),
        },
    )


@perfil_requerido("GERENTE", "ADMINISTRATIVO")
def entregas_administrativo_view(request):
    aguardando = Venda.objects.filter(
        situacao=Venda.Situacao.FECHADA,
        veiculo__situacao=Veiculo.Situacao.VENDIDO,
        entrega__isnull=True,
    ).annotate(concluidas=Count("etapas_documentacao", filter=Q(
        etapas_documentacao__situacao=EtapaDocumentacao.Situacao.CONCLUIDA
    ))).select_related("cliente", "veiculo").order_by("data", "pk")
    total = len(EtapaDocumentacao.Tipo.choices)
    lista = list(aguardando)
    selecionada = next((v for v in lista if str(v.pk) == request.GET.get("venda")), lista[0] if lista else None)
    return render(request, "core/administrativo_painel_entregas.html", {
        "lista": lista, "selecionada": selecionada,
        "form": EntregaVeiculoForm(),
        "base_template": "core/administrativo_base.html" if request.user.is_administrativo() else "core/gerente_base.html",
        "prontas": aguardando.filter(concluidas=total),
        "bloqueadas": aguardando.exclude(concluidas=total),
        "historico": EntregaVeiculo.objects.select_related("venda__veiculo", "venda__cliente", "responsavel").order_by("-data_entrega", "-pk"),
        "total_etapas": total,
    })


@perfil_requerido("GERENTE", "ADMINISTRATIVO")
def documentacao_pendente_view(request):
    """Lista etapas de documentação pendentes e vendas aptas para entrega."""
    mostrar_todas = request.GET.get("todas") == "1"

    etapas = (
        EtapaDocumentacao.objects.filter(venda__situacao=Venda.Situacao.FECHADA)
        .select_related("venda", "venda__cliente", "venda__veiculo", "venda__vendedor")
        .order_by("venda__data", "venda_id", "id")
    )

    if not mostrar_todas:
        etapas = etapas.exclude(situacao=EtapaDocumentacao.Situacao.CONCLUIDA)

    prontas = (
        Venda.objects.filter(
            situacao=Venda.Situacao.FECHADA,
            veiculo__situacao=Veiculo.Situacao.VENDIDO,
            entrega__isnull=True,
        )
        .annotate(
            concluidas=Count(
                "etapas_documentacao",
                filter=Q(
                    etapas_documentacao__situacao=EtapaDocumentacao.Situacao.CONCLUIDA
                ),
            )
        )
        .filter(concluidas=len(EtapaDocumentacao.Tipo.choices))
        .select_related("cliente", "veiculo")
        .order_by("data", "pk")
    )

    if request.user.is_administrativo():
        todas = list(EtapaDocumentacao.objects.filter(venda__situacao=Venda.Situacao.FECHADA).select_related("venda__veiculo", "venda__cliente").order_by("venda__data", "venda_id", "id"))
        grupos = {}
        fila = []
        for etapa in todas:
            grupo = grupos.setdefault(etapa.venda_id, {"venda": etapa.venda, "etapas": [], "concluidas": 0})
            grupo["etapas"].append(etapa)
            grupo["concluidas"] += int(etapa.concluida)
            if not etapa.concluida:
                etapa.dias = max(0, (timezone.localdate() - etapa.data).days)
                fila.append(etapa)
        fila.sort(key=lambda e: (e.data, e.pk))
        for grupo in grupos.values():
            grupo["progresso"] = round(100 * grupo["concluidas"] / len(EtapaDocumentacao.Tipo.choices))
        return render(request, "core/administrativo_painel_documentacao.html", {"base_template": "core/administrativo_base.html", "grupos": grupos.values(), "fila": fila, "situacoes": EtapaDocumentacao.Situacao.choices})
    return render(
        request,
        "core/gerente_documentacao_legado.html",
        {
            "base_template": "core/administrativo_base.html" if request.user.is_administrativo() else "core/gerente_base.html",
            "etapas": etapas,
            "prontas": prontas,
            "situacoes": EtapaDocumentacao.Situacao.choices,
            "mostrar_todas": mostrar_todas,
        },
    )


@perfil_requerido("GERENTE", "ADMINISTRATIVO")
def atualizar_etapa_documentacao_view(request, etapa_id):
    etapa = get_object_or_404(EtapaDocumentacao, pk=etapa_id)

    if request.method != "POST":
        return redirect("documentacao_pendente")

    form = EtapaDocumentacaoForm(request.POST)
    if not form.is_valid():
        erros_do_form_como_mensagens(request, form)
        return redirect("documentacao_pendente")

    try:
        etapa.atualizar(
            request.user,
            form.cleaned_data["situacao"],
            data=form.cleaned_data["data"],
            observacao=form.cleaned_data["observacao"],
        )
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    except PermissionDenied as erro:
        messages.error(request, str(erro))
    else:
        messages.success(
            request,
            f"{etapa.get_tipo_display()} da venda #{etapa.venda_id} atualizada.",
        )

    return redirect("documentacao_pendente")


@perfil_requerido("VENDEDOR", "GERENTE")
@require_POST
def encerrar_procura_view(request, procura_id):
    procura = get_object_or_404(Procura, pk=procura_id)

    try:
        procura.encerrar(request.user)
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    except PermissionDenied as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, "Procura encerrada.")

    if request.user.is_gerente():
        return redirect("procuras_gerente")
    return redirect("procuras_vendedor")




@perfil_requerido("GERENTE")
@require_GET
def relatorios_gerente_view(request):
    from .relatorios_exportacao import obter_contexto_relatorios

    hoje = timezone.localdate()

    data_inicio = request.GET.get(
        "data_inicio",
        hoje.replace(day=1).isoformat(),
    )

    data_fim = request.GET.get(
        "data_fim",
        hoje.isoformat(),
    )

    dias_parados = request.GET.get("dias_parados", "30")

    contexto = {
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "dias_parados": dias_parados,
        "erros": [],
    }

    try:
        contexto.update(
            obter_contexto_relatorios(
                data_inicio=data_inicio,
                data_fim=data_fim,
                dias_parados=dias_parados,
            )
        )
    except (ValueError, TypeError, OverflowError) as erro:
        contexto["erros"].append(str(erro))

    return render(
        request,
        "core/gerente_relatorios.html",
        contexto,
    )