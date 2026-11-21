"""
T01 - Perfis, vendedores e o painel de cada um
T02 - O veículo: ficha, fotos, custo de aquisição e origem

Cobre os critérios de aceite:
- Login com usuário/senha (senha cifrada via AbstractUser do Django)
- Três perfis: gerente, vendedor, administrativo
- Vendedor tem alçada de desconto e percentual de comissão
- Só gerente edita alçada/comissão (regra fica no lado de permissões/views, aqui
  deixamos o campo protegido por um método de validação)
- Vendedor desativado não entra, mas vendas dele continuam no sistema
  (usamos soft delete: campo `ativo`, nunca deletamos o registro)
- Unicidade do veículo (placa/chassi) no estoque ativo
- Reserva exclusiva com prazo, com expiração automática
- Histórico de situação e de preço do veículo
- Margem derivada dos lançamentos financeiros (nunca um campo digitado)
- Auditoria simples de edição/exclusão de lançamentos financeiros
"""

# --- stdlib ---
import re
from datetime import date
from decimal import Decimal

# --- django ---
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.aggregates import Sum
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from django.core.exceptions import PermissionDenied, ValidationError

# ============================================================
# Constantes / regex
# ============================================================

PLACA_REGEX = re.compile(r"^[A-Z]{3}-?\d{4}$|^[A-Z]{3}\d[A-Z]\d{2}$")  # antiga e Mercosul
CHASSI_REGEX = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")  # 17 chars, sem I/O/Q (padrão VIN)


# ============================================================
# Usuários e perfis
# ============================================================

class Usuario(AbstractUser):
    """
    Usuário base do sistema. A senha já vem cifrada automaticamente pelo
    Django (AbstractUser usa PBKDF2 por padrão) — não reinventar isso.
    """

    class Perfil(models.TextChoices):
        GERENTE = "GERENTE", "Gerente"
        VENDEDOR = "VENDEDOR", "Vendedor"
        ADMINISTRATIVO = "ADMINISTRATIVO", "Administrativo"

    perfil = models.CharField(max_length=20, choices=Perfil.choices)

    # Soft delete: nunca apagar o usuário, só desativar.
    ativo = models.BooleanField(default=True)

    def is_gerente(self):
        return self.perfil == self.Perfil.GERENTE

    def is_vendedor(self):
        return self.perfil == self.Perfil.VENDEDOR

    def is_administrativo(self):
        return self.perfil == self.Perfil.ADMINISTRATIVO

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_perfil_display()})"


class PerfilVendedor(models.Model):
    """
    Dados extras de quem é vendedor: alçada de desconto e comissão.
    """

    class TipoAlcada(models.TextChoices):
        PERCENTUAL = "PERCENTUAL", "Percentual (%)"
        VALOR = "VALOR", "Valor (R$)"

    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.PROTECT,
        related_name="dados_vendedor",
        limit_choices_to={"perfil": Usuario.Perfil.VENDEDOR},
    )

    tipo_alcada = models.CharField(
        max_length=20,
        choices=TipoAlcada.choices,
        default=TipoAlcada.PERCENTUAL,
    )

    valor_alcada = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Limite máximo de desconto permitido ao vendedor.",
    )

    percentual_comissao = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percentual de comissão do vendedor sobre a margem da venda.",
    )

    editado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edicoes_alcada_comissao",
    )
    editado_em = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.editado_por_id and not self.editado_por.is_gerente():
            raise ValidationError(
                "Alçada de desconto e comissão só podem ser editadas por um gerente."
            )

    def __str__(self):
        return (
            f"Vendedor: {self.usuario} — "
            f"alçada {self.valor_alcada} ({self.get_tipo_alcada_display()}) / "
            f"comissão {self.percentual_comissao}%"
        )


# ============================================================
# Veículos
# ============================================================

class Veiculo(models.Model):
    class Origem(models.TextChoices):
        COMPRADO = "COMPRADO", "Comprado de terceiro"
        TROCA = "TROCA", "Recebido em troca"
        CONSIGNADO = "CONSIGNADO", "Consignado"

    class Status(models.TextChoices):
        DISPONIVEL = "DISPONIVEL", "Disponível"
        RESERVADO = "RESERVADO", "Reservado"
        VENDIDO = "VENDIDO", "Vendido"

    class Situacao(models.TextChoices):
        PREPARACAO = "PREPARACAO", "Em preparação"
        DISPONIVEL = "DISPONIVEL", "Disponível"
        RESERVADO = "RESERVADO", "Reservado"
        VENDIDO = "VENDIDO", "Vendido"
        ENTREGUE = "ENTREGUE", "Entregue"

    placa = models.CharField(max_length=8)
    chassi = models.CharField(max_length=17)
    renavam = models.CharField(max_length=11)
    marca = models.CharField(max_length=60)
    modelo = models.CharField(max_length=60)
    ano_fabricacao = models.PositiveSmallIntegerField()
    ano_modelo = models.PositiveSmallIntegerField()
    cor = models.CharField(max_length=30)
    combustivel = models.CharField(max_length=30)
    quilometragem = models.PositiveIntegerField()
    opcionais = models.TextField(blank=True)

    situacao = models.CharField(
        max_length=20,
        choices=Situacao.choices,
        default=Situacao.PREPARACAO,
    )

    origem = models.CharField(max_length=20, choices=Origem.choices)

    custo_aquisicao = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    preco_venda = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    valor_repasse = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    venda_fechada = models.BooleanField(default=False)
    cliente_comprador = models.ForeignKey(
        "Cliente",
        on_delete=models.PROTECT,
        related_name="veiculos_comprados",
        null=True,
        blank=True,
    )

    avaliacao_origem = models.OneToOneField(
        "AvaliacaoTroca",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="veiculo_estoque",
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DISPONIVEL)

    criado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="veiculos_cadastrados"
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["placa"],
                condition=models.Q(status__in=["DISPONIVEL", "RESERVADO"]),
                name="placa_unica_estoque_ativo",
            ),
            models.UniqueConstraint(
                fields=["chassi"],
                condition=models.Q(status__in=["DISPONIVEL", "RESERVADO"]),
                name="chassi_unico_estoque_ativo",
            ),
        ]

    def clean(self):
        erros = {}

        placa_normalizada = self.placa.upper().replace(" ", "")
        if not PLACA_REGEX.match(placa_normalizada):
            erros["placa"] = "Placa inválida. Use o formato antigo (ABC1234) ou Mercosul (ABC1D23)."
        self.placa = placa_normalizada

        chassi_normalizado = self.chassi.upper().replace(" ", "")
        if not CHASSI_REGEX.match(chassi_normalizado):
            erros["chassi"] = "Chassi inválido. Deve ter 17 caracteres, sem I, O ou Q."
        self.chassi = chassi_normalizado

        if self.origem in (self.Origem.COMPRADO, self.Origem.TROCA):
            if not self.custo_aquisicao or self.custo_aquisicao <= 0:
                erros["custo_aquisicao"] = "Custo de aquisição é obrigatório para essa origem."
        elif self.origem == self.Origem.CONSIGNADO:
            self.custo_aquisicao = Decimal("0")
            if self.valor_repasse is None:
                erros["valor_repasse"] = "Valor de repasse é obrigatório para consignado."

        if self.pk:
            original = Veiculo.objects.filter(pk=self.pk).first()
            if original and original.venda_fechada and original.custo_aquisicao != self.custo_aquisicao:
                erros["custo_aquisicao"] = "Não é possível alterar o custo após o fechamento da venda."

        if erros:
            raise ValidationError(erros)

    def __str__(self):
        return f"{self.marca} {self.modelo} — {self.placa}"

    @property
    def reserva_ativa(self):
        """Reserva vigente (não cancelada e não vencida), ou None."""
        return self.reservas.filter(
            cancelada=False, expira_em__gt=timezone.now()
        ).first()


class HistoricoSituacaoVeiculo(models.Model):
    veiculo = models.ForeignKey(
        Veiculo, on_delete=models.PROTECT, related_name="historico_situacoes"
    )

    situacao_anterior = models.CharField(max_length=20, blank=True, null=True)
    situacao_nova = models.CharField(max_length=20)

    alterado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="alteracoes_situacao_veiculo"
    )
    alterado_em = models.DateTimeField(auto_now_add=True)

    motivo = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.veiculo} — {self.situacao_anterior} → {self.situacao_nova}"


class FotoVeiculo(models.Model):
    veiculo = models.ForeignKey(Veiculo, on_delete=models.CASCADE, related_name="fotos")
    imagem = models.ImageField(upload_to="veiculos/%Y/%m/")
    ordem = models.PositiveSmallIntegerField(default=0)
    principal = models.BooleanField(default=False)

    class Meta:
        ordering = ["ordem"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.principal:
            FotoVeiculo.objects.filter(veiculo=self.veiculo).exclude(pk=self.pk).update(
                principal=False
            )


class ReservaVeiculo(models.Model):
    veiculo = models.ForeignKey(
        Veiculo,
        on_delete=models.PROTECT,
        related_name="reservas",
        limit_choices_to={"status": Veiculo.Status.DISPONIVEL},
    )
    cliente = models.ForeignKey(
        "Cliente",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reservas",
    )
    cliente_nome = models.CharField(max_length=120)
    cliente_contato = models.CharField(max_length=60)
    vendedor = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="reservas_feitas"
    )

    criada_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField()

    cancelada = models.BooleanField(default=False)
    proposta_origem = models.OneToOneField(
        "Proposta",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reserva_gerada",
    )

    cancelada_em = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )

    cancelada_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reservas_canceladas",
        editable=False,
    )

    motivo_cancelamento = models.TextField(
        blank=True,
        editable=False,
    )
    def esta_valida(self):
        return not self.cancelada and timezone.now() < self.expira_em
    
    def expirar(self):
        with transaction.atomic():

            veiculo = Veiculo.objects.select_for_update().get(
                pk=self.veiculo_id
            )

            reserva = ReservaVeiculo.objects.select_for_update().get(
                pk=self.pk
            )

            agora = timezone.now()

            if reserva.cancelada or reserva.expira_em > agora:
                return False

            reserva.cancelada = True
            reserva.cancelada_em = agora
            reserva.motivo_cancelamento = "Reserva expirada automaticamente"

            reserva.save(
                update_fields=[
                    "cancelada",
                    "cancelada_em",
                    "motivo_cancelamento",
                ]
            )

            if reserva.proposta_origem_id:
                Proposta.objects.filter(
                    pk=reserva.proposta_origem_id,
                ).exclude(
                    situacao=Proposta.Situacao.CANCELADA,
                ).update(
                    situacao=Proposta.Situacao.CANCELADA,
                    atualizada_em=agora,
                )

            if veiculo.situacao == Veiculo.Situacao.RESERVADO:
                veiculo.situacao = Veiculo.Situacao.DISPONIVEL
                veiculo.status = Veiculo.Status.DISPONIVEL

                veiculo.save(
                    update_fields=["situacao", "status"]
                )

                HistoricoSituacaoVeiculo.objects.create(
                    veiculo=veiculo,
                    situacao_anterior=Veiculo.Situacao.RESERVADO,
                    situacao_nova=Veiculo.Situacao.DISPONIVEL,
                    alterado_por=reserva.vendedor,
                    motivo="Reserva expirada automaticamente",
                )

            Proposta.ativar_aguardando(veiculo.pk)

            self.refresh_from_db()

            return True

    def clean(self):
        if self.expira_em and self.expira_em <= timezone.now():
            raise ValidationError({"expira_em": "O prazo da reserva deve ser no futuro."})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.esta_valida():
            Veiculo.objects.filter(pk=self.veiculo_id).update(status=Veiculo.Status.RESERVADO)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["veiculo"],
                condition=models.Q(cancelada=False),
                name="uma_reserva_ativa_por_veiculo",
            )
        ]


# ============================================================
# Financeiro
# ============================================================

class LancamentoFinanceiro(models.Model):
    class Tipo(models.TextChoices):
        CUSTO_AQUISICAO = "CUSTO_AQUISICAO", "Custo de aquisição"
        DESPESA = "DESPESA", "Despesa (preparo, documentação, etc.)"
        VENDA = "VENDA", "Valor de venda"
        COMISSAO = "COMISSAO", "Comissão paga"

    veiculo = models.ForeignKey(
        Veiculo, on_delete=models.PROTECT, related_name="lancamentos"
    )
        # T14: liga a comissão à venda que a gerou (vazio nos demais lançamentos).
    venda = models.ForeignKey(
        "Venda",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lancamentos_financeiros",
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    descricao = models.CharField(max_length=200, blank=True)
    registrado_por = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)
    data_lancamento = models.DateField(default=timezone.now)

    editado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="despesas_editadas",
    )
    editado_em = models.DateTimeField(null=True, blank=True)
    excluido = models.BooleanField(default=False)
    excluido_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="despesas_excluidas",
    )
    excluido_em = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_tipo_display()}: R$ {self.valor} — {self.veiculo}"


def calcular_margem(veiculo: Veiculo) -> Decimal:
    lancamentos = veiculo.lancamentos.filter(excluido=False)

    entradas = sum(
        l.valor for l in lancamentos if l.tipo == LancamentoFinanceiro.Tipo.VENDA
    )
    saidas = sum(
        l.valor
        for l in lancamentos
        if l.tipo in (
            LancamentoFinanceiro.Tipo.CUSTO_AQUISICAO,
            LancamentoFinanceiro.Tipo.DESPESA,
            LancamentoFinanceiro.Tipo.COMISSAO,
        )
    )
    return Decimal(entradas) - Decimal(saidas)


class HistoricoPrecoVeiculo(models.Model):
    veiculo = models.ForeignKey(
        Veiculo, on_delete=models.PROTECT, related_name="historico_precos"
    )

    valor_anterior = models.DecimalField(max_digits=12, decimal_places=2)
    valor_novo = models.DecimalField(max_digits=12, decimal_places=2)

    custo_total_no_momento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    abaixo_do_custo = models.BooleanField(default=False)

    alterado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="alteracoes_preco_veiculo"
    )
    alterado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.veiculo} — R$ {self.valor_anterior} → R$ {self.valor_novo}"



# ============================================================
# Clientes
# ============================================================

class Cliente(models.Model):
    class Tipo(models.TextChoices):
        PESSOA_FISICA = "PF", "Pessoa Física"
        PESSOA_JURIDICA = "PJ", "Pessoa Jurídica"

    tipo = models.CharField(
        max_length=2,
        choices=Tipo.choices,
    )

    nome = models.CharField(max_length=150, blank=True)
    cpf = models.CharField(max_length=11, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)

    cnpj = models.CharField(max_length=14, blank=True)
    razao_social = models.CharField(max_length=180, blank=True)
    nome_fantasia = models.CharField(max_length=150, blank=True)
    responsavel = models.CharField(max_length=150, blank=True)

    cep = models.CharField(max_length=8, blank=True)
    logradouro = models.CharField(max_length=180, blank=True)
    numero = models.CharField(max_length=20, blank=True)
    complemento = models.CharField(max_length=100, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=2, blank=True)

    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    responsavel = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    class Meta:
        ordering = ["nome", "razao_social"]
        constraints = [
            models.UniqueConstraint(
                fields=["cpf"],
                condition=~models.Q(cpf=""),
                name="cliente_cpf_unico",
            ),
            models.UniqueConstraint(
                fields=["cnpj"],
                condition=~models.Q(cnpj=""),
                name="cliente_cnpj_unico",
            ),
        ]

    def clean(self):
        super().clean()
        erros = {}

        self.cpf = re.sub(r"\D", "", self.cpf or "")
        self.cnpj = re.sub(r"\D", "", self.cnpj or "")
        self.cep = re.sub(r"\D", "", self.cep or "")

        if self.tipo == self.Tipo.PESSOA_FISICA:
            if not self.nome.strip():
                erros["nome"] = "Informe o nome do cliente."
            if len(self.cpf) != 11:
                erros["cpf"] = "O CPF deve conter 11 dígitos."
            if not self.data_nascimento:
                erros["data_nascimento"] = "Informe a data de nascimento."
            self.cnpj = ""
            self.razao_social = ""
            self.nome_fantasia = ""
            self.responsavel = ""

        elif self.tipo == self.Tipo.PESSOA_JURIDICA:
            if not self.razao_social.strip():
                erros["razao_social"] = "Informe a razão social."
            if len(self.cnpj) != 14:
                erros["cnpj"] = "O CNPJ deve conter 14 dígitos."
            if not self.responsavel.strip():
                erros["responsavel"] = "Informe o responsável."
            self.cpf = ""
            self.nome = ""
            self.data_nascimento = None

        else:
            erros["tipo"] = "Selecione pessoa física ou jurídica."

        if erros:
            raise ValidationError(erros)

    @property
    def nome_exibicao(self):
        if self.tipo == self.Tipo.PESSOA_FISICA:
            return self.nome
        return self.nome_fantasia or self.razao_social

    def desativar(self):
        self.ativo = False
        self.save(update_fields=["ativo", "atualizado_em"])

    def desativar(self):
        self.ativo = False
        self.save(update_fields=["ativo", "atualizado_em"])

    def reativar(self):
        self.ativo = True
        self.save(update_fields=["ativo", "atualizado_em"])
        
    def __str__(self):
        return self.nome_exibicao

class TelefoneCliente(models.Model):
    class Tipo(models.TextChoices):
        CELULAR = "CELULAR", "Celular"
        FIXO = "FIXO", "Fixo"
        COMERCIAL = "COMERCIAL", "Comercial"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="telefones",
    )
    numero = models.CharField(max_length=20)
    tipo = models.CharField(
        max_length=12,
        choices=Tipo.choices,
        default=Tipo.CELULAR,
    )
    principal = models.BooleanField(default=False)

    class Meta:
        ordering = ["-principal", "numero"]

    def clean(self):
        super().clean()
        self.numero = re.sub(r"\D", "", self.numero or "")

        if len(self.numero) not in (10, 11):
            raise ValidationError({
                "numero": "Informe um telefone com DDD e 10 ou 11 dígitos."
            })

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def __str__(self):
        return self.numero


class Proposta(models.Model):
    class StatusAprovacao(models.TextChoices):
        NAO_NECESSARIA = "NAO_NECESSARIA", "Não necessária"
        PENDENTE = "PENDENTE", "Pendente"
        APROVADA = "APROVADA", "Aprovada"
        RECUSADA = "RECUSADA", "Recusada"
        CONTRAPROPOSTA = "CONTRAPROPOSTA", "Contraproposta"
    class Situacao(models.TextChoices):
        AGUARDANDO = "AGUARDANDO", "Aguardando"
        ATIVA = "ATIVA", "Ativa"
        CANCELADA = "CANCELADA", "Cancelada"
        AGUARDANDO_GERENTE = "AGUARDANDO_GERENTE", "Aguardando gerente"
        APROVADA = "APROVADA", "Aprovada"
        RECUSADA = "RECUSADA", "Recusada"
        CONTRAPROPOSTA = "CONTRAPROPOSTA", "Contraproposta"

    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="propostas"
    )
    veiculo = models.ForeignKey(
        Veiculo, on_delete=models.PROTECT, related_name="propostas"
    )
    vendedor = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="propostas",
        limit_choices_to={
            "perfil__in": [Usuario.Perfil.VENDEDOR, Usuario.Perfil.GERENTE]
        },
    )

    data = models.DateField(default=timezone.localdate)
    valor_oferecido = models.DecimalField(max_digits=12, decimal_places=2)

    preco_tabela = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, editable=False
    )

    situacao = models.CharField(
        max_length=20,
        choices=Situacao.choices,
        default=Situacao.ATIVA,
        editable=False,
    )
    reserva_aguardada = models.ForeignKey(
        "ReservaVeiculo",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="propostas_aguardando",
    )
    status_aprovacao = models.CharField(
        max_length=20,
        choices=StatusAprovacao.choices,
        default=StatusAprovacao.NAO_NECESSARIA,
        editable=False,
    )

    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    _valor_original = None
    
    class Meta:
        ordering = ["-criada_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["veiculo"],
                condition=models.Q(situacao="ATIVA"),
                name="uma_proposta_ativa_por_veiculo",
            )
        ]
    

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._valor_original = instance.__dict__.get("valor_oferecido")
        return instance

    @property
    def desconto_embutido(self):
        if self.preco_tabela is None:
            return Decimal("0.00")
        return self.preco_tabela - self.valor_oferecido

    @property
    def desconto_percentual(self):
        if not self.preco_tabela:
            return Decimal("0.00")
        return (self.desconto_embutido / self.preco_tabela * 100).quantize(
            Decimal("0.01")
        )

    @property
    def soma_composicao(self):
        total = self.composicao.aggregate(total=Sum("valor"))["total"]
        return total or Decimal("0.00")

    @property
    def diferenca(self):
        return self.valor_oferecido - self.soma_composicao

    @property
    def composicao_fecha(self):
        return self.diferenca == 0

    @property
    def alcada_vendedor(self):
        """Perfil comercial do vendedor da proposta (ou None, ex.: gerente)."""
        return getattr(self.vendedor, "dados_vendedor", None)
    @property
    def fora_da_alcada(self):
        """
        Verifica se o desconto ultrapassa a alçada do vendedor.
        Gerentes não precisam de aprovação.
        """
        perfil = self.alcada_vendedor

        if perfil is None:
            if self.vendedor.is_vendedor():
                raise ValidationError(
                    "Este vendedor não possui alçada cadastrada. "
                    "Solicite ao gerente que configure seu perfil comercial."
                )
            return False

        if self.desconto_embutido <= 0:
            return False

        if perfil.tipo_alcada == PerfilVendedor.TipoAlcada.PERCENTUAL:
            return self.desconto_percentual > perfil.valor_alcada

        return self.desconto_embutido > perfil.valor_alcada
    
    def _desconto_percentual_de(self, valor):
            """Desconto sobre o preço de tabela se a venda fosse por `valor`."""
            if not self.preco_tabela:
                return Decimal("0.00")
            return ((self.preco_tabela - valor) / self.preco_tabela * 100).quantize(Decimal("0.01"))

    def _alcada_texto(self):
        """Foto da alçada em texto legível, para a trilha de auditoria."""
        perfil = self.alcada_vendedor
        if perfil is None:
            return ""
        if perfil.tipo_alcada == PerfilVendedor.TipoAlcada.PERCENTUAL:
            return f"{perfil.valor_alcada}%"
        return f"R$ {perfil.valor_alcada}"
    
    def clean(self):
        erros = {}

        if self.valor_oferecido is not None and self.valor_oferecido <= 0:
            erros["valor_oferecido"] = "O valor oferecido deve ser maior que zero."

        if self.veiculo_id:
            if not self.veiculo.preco_venda:
                erros["veiculo"] = "Este veículo ainda não tem preço de venda definido."
            elif not self.pk and self.veiculo.situacao not in (
                Veiculo.Situacao.DISPONIVEL,
                Veiculo.Situacao.RESERVADO,
            ):
                erros["veiculo"] = (
                    "Só é possível fazer proposta para veículo disponível ou reservado."
                )

        if self.cliente_id and not self.pk and not self.cliente.ativo:
            erros["cliente"] = "Cliente desativado não pode receber proposta."

        if self.pk and self.situacao == self.Situacao.CANCELADA:
            erros["__all__"] = "Proposta cancelada não pode ser editada."

        if erros:
            raise ValidationError(erros)

    def save(self, *args, usuario=None, **kwargs):
        criando = self.pk is None

        with transaction.atomic():
            veiculo = Veiculo.objects.select_for_update().get(
                pk=self.veiculo_id
            )

            if self.situacao != self.Situacao.CANCELADA and veiculo.preco_venda:
                self.preco_tabela = veiculo.preco_venda

            valor_mudou = (
                criando or self.valor_oferecido != self._valor_original
            )

            precisa_aprovacao = (
                valor_mudou
                and self.situacao != self.Situacao.CANCELADA
                and self.fora_da_alcada
            )

            # Situação inicial: respeita a reserva e a proposta ativa.
            if criando:
                reserva = veiculo.reservas.filter(
                    cancelada=False,
                    expira_em__gt=timezone.now(),
                ).exists()

                proposta_ativa = Proposta.objects.filter(
                    veiculo_id=self.veiculo_id,
                    situacao=self.Situacao.ATIVA,
                ).exists()

                if reserva or proposta_ativa:
                    self.situacao = self.Situacao.AGUARDANDO
                    self.reserva_aguardada = veiculo.reserva_ativa
                else:
                    self.situacao = self.Situacao.ATIVA
                    self.reserva_aguardada = None

            # Aprovação é independente da situação do veículo.
            if valor_mudou:
                if precisa_aprovacao:
                    self.status_aprovacao = self.StatusAprovacao.PENDENTE
                else:
                    self.status_aprovacao = (
                        self.StatusAprovacao.NAO_NECESSARIA
                    )

            super().save(*args, **kwargs)

            if valor_mudou:
                HistoricoProposta.objects.create(
                    proposta=self,
                    valor_anterior=(
                        None if criando else self._valor_original
                    ),
                    valor_novo=self.valor_oferecido,
                    alterado_por=usuario or self.vendedor,
                )

            if precisa_aprovacao:
                self.registrar_pedido(usuario or self.vendedor)

            self._valor_original = self.valor_oferecido
            
    def aceitar_contraproposta(self, usuario):
        """
        Permite que o vendedor responsável aceite a contraproposta
        registrada pelo gerente.
        """
        if not (
            getattr(usuario, "is_authenticated", False)
            and usuario.ativo
            and usuario.is_vendedor()
        ):
            raise PermissionDenied(
                "Somente o vendedor responsável pode aceitar a contraproposta."
            )

        with transaction.atomic():
            # Bloqueia o veículo para evitar conflitos com outras propostas.
            veiculo_id = Proposta.objects.only("veiculo_id").get(
                pk=self.pk
            ).veiculo_id

            veiculo = Veiculo.objects.select_for_update().get(
                pk=veiculo_id
            )

            proposta = Proposta.objects.select_for_update().get(
                pk=self.pk
            )

            if proposta.vendedor_id != usuario.pk:
                raise PermissionDenied(
                    "Você não pode aceitar a contraproposta de outro vendedor."
                )

            if proposta.situacao == self.Situacao.CANCELADA:
                raise ValidationError(
                    "Uma proposta cancelada não pode ser aceita."
                )

            if proposta.status_aprovacao != self.StatusAprovacao.CONTRAPROPOSTA:
                raise ValidationError(
                    "Esta proposta não possui uma contraproposta pendente de aceite."
                )

            # Recupera a contraproposta mais recente do gerente.
            decisao = (
                proposta.decisoes.filter(
                    tipo=DecisaoProposta.Tipo.CONTRAPROPOSTA
                )
                .order_by("-feito_em", "-id")
                .first()
            )

            if not decisao:
                raise ValidationError(
                    "Não foi encontrada uma contraproposta registrada."
                )

            valor_anterior = proposta.valor_oferecido
            novo_valor = decisao.valor_referencia


            # Registra o novo valor e a aprovação.
            proposta.valor_oferecido = novo_valor
            proposta.status_aprovacao = self.StatusAprovacao.APROVADA

            # Atualiza diretamente para não executar novamente
            # a regra de alçada do método save().
            Proposta.objects.filter(pk=proposta.pk).update(
                valor_oferecido=novo_valor,
                status_aprovacao=self.StatusAprovacao.APROVADA,
                situacao=proposta.situacao,
                reserva_aguardada=proposta.reserva_aguardada,
                atualizada_em=timezone.now(),
            )

            # Registra a alteração do valor.
            HistoricoProposta.objects.create(
                proposta=proposta,
                valor_anterior=valor_anterior,
                valor_novo=novo_valor,
                alterado_por=usuario,
            )

            # Registra o aceite na trilha de auditoria.
            aceite = DecisaoProposta.objects.create(
                proposta=proposta,
                tipo=DecisaoProposta.Tipo.ACEITE_CONTRAPROPOSTA,
                valor_referencia=novo_valor,
                desconto_percentual_no_momento=(
                    proposta._desconto_percentual_de(novo_valor)
                ),
                alcada_no_momento=proposta._alcada_texto(),
                parecer="Contraproposta aceita pelo vendedor.",
                feito_por=usuario,
            )

            self.refresh_from_db()

        return aceite
    
    def recusar_contraproposta(self, usuario):
        """
        O vendedor responsável recusa a contraproposta do gerente.
        A proposta fica RECUSADA + CANCELADA e a fila do veículo anda.
        """
        if not (
            getattr(usuario, "is_authenticated", False)
            and usuario.ativo
            and usuario.is_vendedor()
        ):
            raise PermissionDenied(
                "Somente o vendedor responsável pode recusar a contraproposta."
            )

        with transaction.atomic():
            veiculo_id = Proposta.objects.only(
                "veiculo_id"
            ).get(pk=self.pk).veiculo_id

            Veiculo.objects.select_for_update().get(
                pk=veiculo_id
            )

            proposta = Proposta.objects.select_for_update().get(
                pk=self.pk,
                veiculo_id=veiculo_id,
            )

            if proposta.vendedor_id != usuario.pk:
                raise PermissionDenied(
                    "Você não pode recusar a contraproposta de outro vendedor."
                )

            if proposta.situacao == self.Situacao.CANCELADA:
                raise ValidationError("Uma proposta cancelada não pode ser recusada.")

            if proposta.status_aprovacao != self.StatusAprovacao.CONTRAPROPOSTA:
                raise ValidationError(
                    "Esta proposta não possui uma contraproposta pendente."
                )

            decisao_gerente = proposta.decisoes.filter(
                tipo=DecisaoProposta.Tipo.CONTRAPROPOSTA
            ).first()

            if not decisao_gerente:
                raise ValidationError(
                    "Não foi encontrada uma contraproposta registrada."
                )

            recusa = DecisaoProposta.objects.create(
                proposta=proposta,
                tipo=DecisaoProposta.Tipo.RECUSA_CONTRAPROPOSTA,
                valor_referencia=decisao_gerente.valor_referencia,
                desconto_percentual_no_momento=(
                    proposta._desconto_percentual_de(decisao_gerente.valor_referencia)
                ),
                alcada_no_momento=proposta._alcada_texto(),
                parecer="Contraproposta recusada pelo vendedor.",
                feito_por=usuario,
            )

            proposta.status_aprovacao = self.StatusAprovacao.RECUSADA
            proposta.situacao = self.Situacao.CANCELADA
            proposta.save(
                update_fields=["status_aprovacao", "situacao", "atualizada_em"]
            )

            Proposta.ativar_aguardando(proposta.veiculo_id)

            self.refresh_from_db()

        return recusa
    
    @classmethod
    def ativar_aguardando(cls, veiculo_id):
        """Promove a proposta aguardando mais antiga, se o veículo estiver livre."""
        with transaction.atomic():
            veiculo = Veiculo.objects.select_for_update().get(pk=veiculo_id)
            if veiculo.situacao != Veiculo.Situacao.DISPONIVEL:
                return
            if veiculo.reserva_ativa:
                return
            
            if cls.objects.filter(
                veiculo_id=veiculo_id, situacao=cls.Situacao.ATIVA
            ).exists():
                return

            proxima = (
                cls.objects.filter(
                    veiculo_id=veiculo_id, situacao=cls.Situacao.AGUARDANDO
                )
               .order_by("criada_em", "pk")
                .first()
            )
            if proxima:
                proxima.situacao = cls.Situacao.ATIVA
                proxima.reserva_aguardada = None
                proxima.save(
                    update_fields=["situacao", "reserva_aguardada", "atualizada_em"]
                )
    
    def cancelar(self):
        if self.situacao == self.Situacao.CANCELADA:
            return

        with transaction.atomic():
            self.situacao = self.Situacao.CANCELADA
            self.save(update_fields=["situacao", "atualizada_em"])
            Proposta.ativar_aguardando(self.veiculo_id)
            
        
    def registrar_pedido(self, usuario):
            """Grava na trilha o pedido de aprovação (a situação já foi ajustada no save)."""
            return DecisaoProposta.objects.create(
            proposta=self,
            tipo=DecisaoProposta.Tipo.PEDIDO,
            valor_referencia=self.valor_oferecido,
            desconto_percentual_no_momento=self.desconto_percentual,
            alcada_no_momento=self._alcada_texto(),
            feito_por=usuario,
            )

    def decidir(self, usuario, tipo, parecer="", novo_valor=None):
        if not (
            getattr(usuario, "is_authenticated", False)
            and usuario.ativo
            and usuario.is_gerente()
        ):
            raise PermissionDenied(
                "Somente um gerente ativo pode decidir sobre propostas."
            )

        Tipo = DecisaoProposta.Tipo

        if tipo not in (
            Tipo.APROVACAO,
            Tipo.RECUSA,
            Tipo.CONTRAPROPOSTA,
        ):
            raise ValidationError("Tipo de decisão inválido.")

        parecer = (parecer or "").strip()

        with transaction.atomic():
            proposta = Proposta.objects.select_for_update().get(
                pk=self.pk
            )
            if proposta.situacao == self.Situacao.CANCELADA:
                raise ValidationError("Esta proposta foi cancelada.")

            if proposta.vendedor_id == usuario.pk:
                raise PermissionDenied(
                    "Ninguém pode decidir sobre a própria proposta."
                )

            if (
                proposta.status_aprovacao
                != self.StatusAprovacao.PENDENTE
            ):
                raise ValidationError(
                    "Esta proposta não está aguardando decisão do gerente."
                )

            if tipo == Tipo.APROVACAO:
                nova_aprovacao = self.StatusAprovacao.APROVADA
                valor_ref = proposta.valor_oferecido

            elif tipo == Tipo.RECUSA:
                if not parecer:
                    raise ValidationError(
                        "Informe o parecer da recusa."
                    )

                nova_aprovacao = self.StatusAprovacao.RECUSADA
                valor_ref = proposta.valor_oferecido

            else:
                if not parecer:
                    raise ValidationError(
                        "Informe o parecer da contraproposta."
                    )

                if novo_valor is None:
                    raise ValidationError(
                        "Informe o valor da contraproposta."
                    )

                try:
                    novo_valor = Decimal(novo_valor)
                except (InvalidOperation, TypeError, ValueError):
                    raise ValidationError(
                        "Valor da contraproposta inválido."
                    )

                if novo_valor <= proposta.valor_oferecido:
                    raise ValidationError(
                        "A contraproposta deve ser maior que o valor oferecido."
                    )

                nova_aprovacao = self.StatusAprovacao.CONTRAPROPOSTA
                valor_ref = novo_valor.quantize(Decimal("0.01"))

            decisao = DecisaoProposta.objects.create(
                proposta=proposta,
                tipo=tipo,
                valor_referencia=valor_ref,
                desconto_percentual_no_momento=(
                    proposta._desconto_percentual_de(valor_ref)
                ),
                alcada_no_momento=proposta._alcada_texto(),
                parecer=parecer,
                feito_por=usuario,
            )

            proposta.status_aprovacao = nova_aprovacao

            if tipo == Tipo.RECUSA:
                proposta.situacao = self.Situacao.CANCELADA

            proposta.save(
                update_fields=[
                    "status_aprovacao",
                    "situacao",
                    "atualizada_em",
                ]
            )
            
            if tipo == Tipo.RECUSA:
                Proposta.ativar_aguardando(proposta.veiculo_id)
                
            self.status_aprovacao = nova_aprovacao
            self.situacao = proposta.situacao

            return decisao
    
    def __str__(self):
        return f"Proposta #{self.pk} — {self.cliente} — {self.veiculo}"


class ComposicaoPagamento(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada em dinheiro"
        TROCA = "TROCA", "Veículo na troca"
        FINANCIAMENTO = "FINANCIAMENTO", "Saldo financiado"

    proposta = models.ForeignKey(
        Proposta, on_delete=models.CASCADE, related_name="composicao"
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    valor = models.DecimalField(max_digits=12, decimal_places=2)

    troca_descricao = models.CharField(max_length=150, blank=True)
    avaliacao_troca = models.ForeignKey(
        "AvaliacaoTroca",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="composicoes_pagamento",
    )

    financ_banco = models.CharField(max_length=100, blank=True)
    financ_parcelas = models.PositiveSmallIntegerField(null=True, blank=True)
    financ_valor_parcela = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["avaliacao_troca"],
                name="unique_avaliacao_troca_composicao",
            ),
        ]

    def clean(self):
        erros = {}

        if self.valor is not None and self.valor <= 0:
            erros["valor"] = "O valor deve ser maior que zero."

        if self.tipo == self.Tipo.TROCA:
            if self.avaliacao_troca_id:
                avaliacao = self.avaliacao_troca

                self.troca_descricao = (
                    f"{avaliacao.marca} {avaliacao.modelo} "
                    f"{avaliacao.ano_modelo} - {avaliacao.placa}"
                )

                if self.valor != avaliacao.valor_avaliado:
                    erros["valor"] = (
                        "O valor da troca deve ser igual ao valor avaliado pelo gerente."
                    )

            elif not self.troca_descricao.strip():
                erros["troca_descricao"] = "Descreva o veículo recebido na troca."
            self.financ_banco = ""
            self.financ_parcelas = None
            self.financ_valor_parcela = None

        elif self.tipo == self.Tipo.FINANCIAMENTO:
            if not self.financ_banco.strip():
                erros["financ_banco"] = "Informe o banco do financiamento."
            if not self.financ_parcelas or self.financ_parcelas < 1:
                erros["financ_parcelas"] = "Informe o número de parcelas."
            if not self.financ_valor_parcela or self.financ_valor_parcela <= 0:
                erros["financ_valor_parcela"] = "Informe o valor da parcela."
            self.troca_descricao = ""

        else:
            self.troca_descricao = ""
            self.financ_banco = ""
            self.financ_parcelas = None
            self.financ_valor_parcela = None

        if erros:
            raise ValidationError(erros)

    def __str__(self):
        return f"{self.get_tipo_display()}: R$ {self.valor}"


class HistoricoProposta(models.Model):
    proposta = models.ForeignKey(
        Proposta, on_delete=models.PROTECT, related_name="historico"
    )
    valor_anterior = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    valor_novo = models.DecimalField(max_digits=12, decimal_places=2)
    alterado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="alteracoes_proposta"
    )
    alterado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-alterado_em", "-id"]

    def __str__(self):
        anterior = "—" if self.valor_anterior is None else f"R$ {self.valor_anterior}"
        return f"{self.proposta} — {anterior} → R$ {self.valor_novo}"
    
class DecisaoProposta(models.Model):
    """
    Trilha de auditoria da T09: um registro por evento (pedido de aprovação,
    aprovação, recusa, contraproposta). Nunca é editado nem apagado.
    """

    class Tipo(models.TextChoices):
        PEDIDO = "PEDIDO", "Pedido de aprovação"
        APROVACAO = "APROVACAO", "Aprovação"
        RECUSA = "RECUSA", "Recusa"
        CONTRAPROPOSTA = "CONTRAPROPOSTA", "Contraproposta"
        ACEITE_CONTRAPROPOSTA = ("ACEITE_CONTRAPROPOSTA","Aceite da contraproposta",)
        RECUSA_CONTRAPROPOSTA = ("RECUSA_CONTRAPROPOSTA","Recusa da contraproposta",)
        RECUSA_FILA = "RECUSA_FILA", "Recusa de proposta da fila"
        

    proposta = models.ForeignKey(
        Proposta, on_delete=models.PROTECT, related_name="decisoes"
    )
    tipo = models.CharField(
    max_length=30,
    choices=Tipo.choices,
)

    # Pedido: valor que o vendedor ofereceu. Contraproposta: novo valor do gerente.
    valor_referencia = models.DecimalField(max_digits=12, decimal_places=2)

    # Fotos do momento (o preço e a alçada podem mudar depois).
    desconto_percentual_no_momento = models.DecimalField(
        max_digits=7, decimal_places=2, default=0
    )
    alcada_no_momento = models.CharField(max_length=40, blank=True)

    parecer = models.TextField(blank=True)

    feito_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="decisoes_proposta"
    )
    feito_em = models.DateTimeField(auto_now_add=True)
    
    

    class Meta:
        ordering = ["-feito_em", "-id"]

    def save(self, *args, **kwargs):
        # Trilha de auditoria: só se cria, nunca se edita.
        if self.pk:
            raise ValidationError("Registros de decisão não podem ser alterados.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Registros de decisão não podem ser apagados.")

    def __str__(self):
        return f"{self.proposta} — {self.get_tipo_display()} — R$ {self.valor_referencia}"


# ============================================================
# T11 - Avaliação de troca
# ============================================================

class AvaliacaoTroca(models.Model):

    class EstadoGeral(models.TextChoices):
        EXCELENTE = "EXCELENTE", "Excelente"
        BOM = "BOM", "Bom"
        REGULAR = "REGULAR", "Regular"
        RUIM = "RUIM", "Ruim"

    # Identificação do veículo oferecido na troca
    placa = models.CharField(max_length=8)
    chassi = models.CharField(max_length=17)
    renavam = models.CharField(max_length=11, blank=True, default="")
    marca = models.CharField(max_length=60)
    modelo = models.CharField(max_length=60)

    ano_fabricacao = models.PositiveSmallIntegerField()
    ano_modelo = models.PositiveSmallIntegerField()
    cor = models.CharField(max_length=30)
    combustivel = models.CharField(max_length=30)
    quilometragem = models.PositiveIntegerField()
    opcionais = models.TextField(
        blank=True,
        default="",
        verbose_name="Opcionais"
    )

    # Avaliação realizada pelo gerente
    estado_geral = models.CharField(
        max_length=15,
        choices=EstadoGeral.choices,
    )

    possui_debitos = models.BooleanField(default=False)
    descricao_debitos = models.TextField(blank=True)

    possui_pendencias_documentacao = models.BooleanField(
        default=False
    )
    descricao_pendencias = models.TextField(blank=True)

    valor_avaliado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    observacoes = models.TextField(blank=True)

    # Responsável pela avaliação
    avaliado_por = models.ForeignKey(
        "Usuario",
        on_delete=models.PROTECT,
        related_name="avaliacoes_troca",
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def clean(self):
        erros = {}

        if self.valor_avaliado is not None and self.valor_avaliado <= 0:
            erros["valor_avaliado"] = (
                "O valor avaliado deve ser maior que zero."
            )

        if self.possui_debitos and not self.descricao_debitos.strip():
            erros["descricao_debitos"] = (
                "Descreva os débitos existentes."
            )

        if (
            self.possui_pendencias_documentacao
            and not self.descricao_pendencias.strip()
        ):
            erros["descricao_pendencias"] = (
                "Descreva as pendências de documentação."
            )

        if self.avaliado_por_id and not self.avaliado_por.is_gerente():
            erros["avaliado_por"] = (
                "Somente um gerente pode realizar avaliações."
            )

        if erros:
            raise ValidationError(erros)

    def __str__(self):
        return (
            f"Avaliação: {self.marca} {self.modelo} "
            f"— {self.placa} — R$ {self.valor_avaliado}"
        )


class FotoAvaliacaoTroca(models.Model):
    avaliacao = models.ForeignKey(
        "AvaliacaoTroca",
        on_delete=models.CASCADE,
        related_name="fotos"
    )

    imagem = models.ImageField(
        upload_to="avaliacoes_troca/%Y/%m/"
    )

    descricao = models.CharField(
        max_length=255,
        blank=True
    )

    ordem = models.PositiveIntegerField(default=0)

    criada_em = models.DateTimeField(
        auto_now_add=True
    )
    
    class Meta:
        ordering = ["ordem", "id"]

    def __str__(self):
        return f"Foto da avaliação #{self.avaliacao_id}"


# ============================================================
# T12 - Fechamento, contrato e pagamento
# ============================================================

class Venda(models.Model):
    """
    Registro formal da venda. Nasce no fechamento (Venda.fechar) e guarda
    uma "foto" do negócio: valores, vendedor e cliente no momento da venda.
    Venda cancelada nunca é apagada: fica com motivo e responsável.
    """

    class Situacao(models.TextChoices):
        FECHADA = "FECHADA", "Fechada"
        CANCELADA = "CANCELADA", "Cancelada"

    proposta = models.ForeignKey(
        Proposta, on_delete=models.PROTECT, related_name="vendas"
    )
    veiculo = models.ForeignKey(
        Veiculo, on_delete=models.PROTECT, related_name="vendas"
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="vendas"
    )
    vendedor = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="vendas_realizadas"
    )

    data = models.DateField(default=timezone.localdate)
    preco_tabela = models.DecimalField(max_digits=12, decimal_places=2)
    valor_venda = models.DecimalField(max_digits=12, decimal_places=2)

    situacao = models.CharField(
        max_length=20,
        choices=Situacao.choices,
        default=Situacao.FECHADA,
        editable=False,
    )

    fechada_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="vendas_fechadas"
    )
    criada_em = models.DateTimeField(auto_now_add=True)

    cancelada_em = models.DateTimeField(null=True, blank=True, editable=False)
    cancelada_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="vendas_canceladas",
        editable=False,
    )
    motivo_cancelamento = models.TextField(blank=True, editable=False)

    class Meta:
        ordering = ["-criada_em", "-id"]
        constraints = [
            # Um veículo só pode ter uma venda fechada por vez.
            models.UniqueConstraint(
                fields=["veiculo"],
                condition=models.Q(situacao="FECHADA"),
                name="uma_venda_fechada_por_veiculo",
            ),
            # Uma proposta só pode gerar uma venda fechada por vez.
            models.UniqueConstraint(
                fields=["proposta"],
                condition=models.Q(situacao="FECHADA"),
                name="uma_venda_fechada_por_proposta",
            ),
        ]

    @property
    def esta_fechada(self):
        return self.situacao == self.Situacao.FECHADA

    @property
    def desconto(self):
        return self.preco_tabela - self.valor_venda

    @property
    def entrada(self):
        """Pagamento de entrada desta venda, ou None."""
        return self.pagamentos.filter(
            tipo=PagamentoVenda.Tipo.ENTRADA
        ).first()

    @property
    def financiamento(self):
        """Dados do financiamento desta venda, ou None."""
        return self.pagamentos.filter(
            tipo=PagamentoVenda.Tipo.FINANCIAMENTO
        ).first()

    @property
    def soma_pagamentos(self):
        total = self.pagamentos.aggregate(total=Sum("valor"))["total"]
        return total or Decimal("0.00")
    # ------------------------------------------------------------------
    # Fechamento (T12)
    # ------------------------------------------------------------------
    @classmethod
    def fechar(cls, veiculo_id, proposta_id, cliente_id, usuario, motivo=""):
        """
        Fecha a venda: valida a proposta, grava a Venda e os pagamentos,
        cria o veículo recebido na troca (T11) e leva o veículo a VENDIDO.
        Tudo ou nada: qualquer erro desfaz a operação inteira.
        """
        if not (
            getattr(usuario, "is_authenticated", False)
            and usuario.ativo
            and (
                usuario.is_gerente()
                or usuario.is_administrativo()
                or usuario.is_vendedor()
            )
        ):
            raise PermissionDenied(
                "Somente gerente, administrativo ou o vendedor da proposta "
                "podem fechar uma venda."
            )

        with transaction.atomic():
            # Ordem de bloqueio da T10: veículo primeiro, depois a proposta.
            veiculo = Veiculo.objects.select_for_update().get(pk=veiculo_id)
            proposta = Proposta.objects.select_for_update().get(pk=proposta_id)
            cliente = Cliente.objects.get(pk=cliente_id)
            
            if usuario.is_vendedor() and proposta.vendedor_id != usuario.pk:
                raise PermissionDenied(
                    "Você só pode fechar a venda das suas próprias propostas."
                )
                
            if veiculo.situacao != Veiculo.Situacao.RESERVADO:
                raise ValidationError(
                    "Somente um veículo reservado pode ter a venda fechada."
                )

            if proposta.veiculo_id != veiculo.pk or proposta.cliente_id != cliente.pk:
                raise ValidationError(
                    "A proposta não corresponde ao veículo e ao cliente informados."
                )

            if proposta.situacao != Proposta.Situacao.ATIVA:
                raise ValidationError("Somente uma proposta ativa pode ser fechada.")

            # Critério 1: só fecha com proposta aprovada (ou dentro da alçada).
            if proposta.status_aprovacao not in (
                Proposta.StatusAprovacao.NAO_NECESSARIA,
                Proposta.StatusAprovacao.APROVADA,
            ):
                raise ValidationError(
                    "A venda só pode ser fechada com proposta aprovada "
                    "ou dentro da alçada do vendedor."
                )

            if veiculo.propostas.filter(
                status_aprovacao__in=[
                    Proposta.StatusAprovacao.PENDENTE,
                    Proposta.StatusAprovacao.CONTRAPROPOSTA,
                ]
            ).exclude(situacao=Proposta.Situacao.CANCELADA).exists():
                raise ValidationError(
                    "Há proposta aguardando decisão do gerente ou resposta do "
                    "vendedor. Resolva antes de registrar a venda."
                )

            itens = list(proposta.composicao.select_related("avaliacao_troca"))

            if not itens or not proposta.composicao_fecha:
                raise ValidationError(
                    "A composição do pagamento deve fechar exatamente o valor da proposta."
                )

            # Troca: avaliação válida, valor igual e ainda não recebida no estoque.
            for item in itens:
                if item.tipo != ComposicaoPagamento.Tipo.TROCA:
                    continue

                avaliacao = item.avaliacao_troca
                if avaliacao is None:
                    raise ValidationError(
                        "Existe uma troca sem avaliação vinculada."
                    )
                if item.valor != avaliacao.valor_avaliado:
                    raise ValidationError(
                        "O valor de uma troca está diferente do valor da avaliação. "
                        "Revise a composição antes de fechar a venda."
                    )
                if Veiculo.objects.filter(avaliacao_origem=avaliacao).exists():
                    raise ValidationError(
                        f"A avaliação #{avaliacao.pk} já gerou um veículo no estoque."
                    )

            hoje = timezone.localdate()

            venda = cls.objects.create(
                proposta=proposta,
                veiculo=veiculo,
                cliente=cliente,
                vendedor=proposta.vendedor,
                data=hoje,
                preco_tabela=proposta.preco_tabela or veiculo.preco_venda or 0,
                valor_venda=proposta.valor_oferecido,
                fechada_por=usuario,
            )

            # Critérios 3 e 4: entrada e financiamento ficam gravados na venda.
            for item in itens:
                PagamentoVenda.objects.create(
                    venda=venda,
                    tipo=item.tipo,
                    valor=item.valor,
                    data_pagamento=(
                        hoje if item.tipo == ComposicaoPagamento.Tipo.ENTRADA else None
                    ),
                    troca_descricao=item.troca_descricao,
                    avaliacao_troca=item.avaliacao_troca,
                    financ_banco=item.financ_banco,
                    financ_parcelas=item.financ_parcelas,
                    financ_valor_parcela=item.financ_valor_parcela,
                )

                # T11: o veículo da troca entra no estoque em preparação.
                if item.tipo == ComposicaoPagamento.Tipo.TROCA:
                    a = item.avaliacao_troca
                    recebido = Veiculo(
                        placa=a.placa, chassi=a.chassi, renavam=a.renavam,
                        marca=a.marca, modelo=a.modelo,
                        ano_fabricacao=a.ano_fabricacao, ano_modelo=a.ano_modelo,
                        cor=a.cor, combustivel=a.combustivel,
                        quilometragem=a.quilometragem, opcionais=a.opcionais,
                        origem=Veiculo.Origem.TROCA,
                        custo_aquisicao=a.valor_avaliado,
                        situacao=Veiculo.Situacao.PREPARACAO,
                        status=Veiculo.Status.DISPONIVEL,
                        avaliacao_origem=a,
                        criado_por=usuario,
                    )
                    recebido.full_clean()
                    recebido.save()
                    
            # A reserva cumpriu o papel: encerra sem cancelar a proposta.
            agora = timezone.now()
            for reserva in veiculo.reservas.filter(cancelada=False):
                reserva.cancelada = True
                reserva.cancelada_em = agora
                reserva.cancelada_por = usuario
                reserva.motivo_cancelamento = f"Encerrada pela venda #{venda.pk}"
                reserva.save(
                    update_fields=[
                        "cancelada",
                        "cancelada_em",
                        "cancelada_por",
                        "motivo_cancelamento",
                    ]
                )
            # Critério 5: o veículo passa a vendido.
            veiculo.situacao = Veiculo.Situacao.VENDIDO
            veiculo.status = Veiculo.Status.VENDIDO
            veiculo.venda_fechada = True
            veiculo.cliente_comprador = cliente
            veiculo.save(
                update_fields=["situacao", "status", "venda_fechada", "cliente_comprador"]
            )

            HistoricoSituacaoVeiculo.objects.create(
                veiculo=veiculo,
                situacao_anterior=Veiculo.Situacao.RESERVADO,
                situacao_nova=Veiculo.Situacao.VENDIDO,
                alterado_por=usuario,
                motivo=(motivo or f"Venda #{venda.pk}")[:255],
            )
            # T13: nasce a lista de etapas da documentação, todas pendentes.
            for tipo, _rotulo in EtapaDocumentacao.Tipo.choices:
                EtapaDocumentacao.objects.create(
                    venda=venda, tipo=tipo, atualizada_por=usuario
                )
                
            # T14: a comissão é lançada como despesa do veículo, e por isso
            # entra na conta da margem.
            valor_comissao = venda.calcular_comissao()
            if valor_comissao > 0:
                perfil = venda.vendedor.dados_vendedor
                LancamentoFinanceiro.objects.create(
                    veiculo=veiculo,
                    venda=venda,
                    tipo=LancamentoFinanceiro.Tipo.COMISSAO,
                    valor=valor_comissao,
                    descricao=(
                        f"Comissão da venda #{venda.pk} "
                        f"({perfil.percentual_comissao}%)"
                    )[:200],
                    registrado_por=usuario,
                    data_lancamento=hoje,
                )
                
            return venda

    # ------------------------------------------------------------------
    # Cancelamento (T12)
    # ------------------------------------------------------------------
    def cancelar(self, usuario, motivo):
        """
        Cancela a venda e devolve o veículo ao estoque (disponível).
        Exige motivo. O veículo recebido na troca NÃO é removido do estoque.
        """
        if not (
            getattr(usuario, "is_authenticated", False)
            and usuario.ativo
            and usuario.is_gerente()
        ):
            raise PermissionDenied("Somente um gerente ativo pode cancelar uma venda.")

        motivo = (motivo or "").strip()
        if len(motivo) < 5:
            raise ValidationError("Informe o motivo do cancelamento (mínimo de 5 caracteres).")

        with transaction.atomic():
            veiculo = Veiculo.objects.select_for_update().get(pk=self.veiculo_id)
            venda = Venda.objects.select_for_update().get(pk=self.pk)

            if venda.situacao != self.Situacao.FECHADA:
                raise ValidationError("Esta venda já foi cancelada.")

            if veiculo.situacao != Veiculo.Situacao.VENDIDO:
                raise ValidationError(
                    "Só é possível cancelar a venda de um veículo que ainda não foi entregue."
                )

            agora = timezone.now()
            venda.situacao = self.Situacao.CANCELADA
            venda.cancelada_em = agora
            venda.cancelada_por = usuario
            venda.motivo_cancelamento = motivo
            venda.save(
                update_fields=["situacao", "cancelada_em", "cancelada_por", "motivo_cancelamento"]
            )

            veiculo.situacao = Veiculo.Situacao.DISPONIVEL
            veiculo.status = Veiculo.Status.DISPONIVEL
            veiculo.venda_fechada = False
            veiculo.cliente_comprador = None
            veiculo.save(
                update_fields=["situacao", "status", "venda_fechada", "cliente_comprador"]
            )
            
            # Reserva que ficou aberta (vendas feitas antes desta regra).
            veiculo.reservas.filter(cancelada=False).update(
                cancelada=True,
                cancelada_em=agora,
                cancelada_por=usuario,
                motivo_cancelamento=f"Venda #{venda.pk} cancelada",
            )

            # A proposta que gerou a venda também é cancelada,
            # como no cancelamento de reserva da T10.
            Proposta.objects.filter(pk=venda.proposta_id).update(
                situacao=Proposta.Situacao.CANCELADA,
                atualizada_em=agora,
            )
            # T14: a comissão de uma venda cancelada deixa de entrar nas contas.
            LancamentoFinanceiro.objects.filter(
                venda=venda,
                tipo=LancamentoFinanceiro.Tipo.COMISSAO,
                excluido=False,
            ).update(excluido=True, excluido_por=usuario, excluido_em=agora)
            
            HistoricoSituacaoVeiculo.objects.create(
                veiculo=veiculo,
                situacao_anterior=Veiculo.Situacao.VENDIDO,
                situacao_nova=Veiculo.Situacao.DISPONIVEL,
                alterado_por=usuario,
                motivo=f"Venda #{venda.pk} cancelada: {motivo}"[:255],
            )
            # Promove a próxima proposta da fila, se houver.
            Proposta.ativar_aguardando(veiculo.pk)
            self.refresh_from_db()

        return self
    # ------------------------------------------------------------------
    # Entrega (T13)
    # ------------------------------------------------------------------
    def registrar_entrega(self, usuario, data_entrega=None, checklist=None, observacoes=""):
        """
        Registra a entrega: exige venda fechada, as 3 etapas da documentação
        concluídas e o checklist completo. Leva o veículo a ENTREGUE.
        `checklist` é um dict {campo: bool} com os itens de EntregaVeiculo.ITENS_CHECKLIST.
        """
        if not (
            getattr(usuario, "is_authenticated", False)
            and usuario.ativo
            and (usuario.is_gerente() or usuario.is_administrativo())
        ):
            raise PermissionDenied(
                "Somente gerente ou administrativo ativo pode registrar a entrega."
            )

        checklist = checklist or {}

        with transaction.atomic():
            # Ordem de bloqueio: veículo primeiro, depois a venda.
            veiculo = Veiculo.objects.select_for_update().get(pk=self.veiculo_id)
            venda = Venda.objects.select_for_update().get(pk=self.pk)

            if venda.situacao != self.Situacao.FECHADA:
                raise ValidationError(
                    "Não é possível registrar a entrega: a venda não está fechada."
                )

            if EntregaVeiculo.objects.filter(venda=venda).exists():
                raise ValidationError("A entrega desta venda já foi registrada.")

            if veiculo.situacao != Veiculo.Situacao.VENDIDO:
                raise ValidationError(
                    "Somente um veículo vendido pode ser entregue."
                )

            # Todas as etapas precisam estar concluídas.
            concluidas = set(
                venda.etapas_documentacao.filter(
                    situacao=EtapaDocumentacao.Situacao.CONCLUIDA
                ).values_list("tipo", flat=True)
            )
            faltando = [
                rotulo
                for valor, rotulo in EtapaDocumentacao.Tipo.choices
                if valor not in concluidas
            ]
            if faltando:
                raise ValidationError(
                    "Conclua toda a documentação antes de entregar. Pendente: "
                    + ", ".join(faltando)
                    + "."
                )

            entrega = EntregaVeiculo(
                venda=venda,
                data_entrega=data_entrega or timezone.localdate(),
                responsavel=usuario,
                observacoes=(observacoes or "").strip(),
                **{
                    campo: bool(checklist.get(campo))
                    for campo, _rotulo in EntregaVeiculo.ITENS_CHECKLIST
                },
            )
            entrega.full_clean()  # exige o checklist completo e data válida
            entrega.save()

            veiculo.situacao = Veiculo.Situacao.ENTREGUE
            veiculo.status = Veiculo.Status.VENDIDO
            veiculo.save(update_fields=["situacao", "status"])

            HistoricoSituacaoVeiculo.objects.create(
                veiculo=veiculo,
                situacao_anterior=Veiculo.Situacao.VENDIDO,
                situacao_nova=Veiculo.Situacao.ENTREGUE,
                alterado_por=usuario,
                motivo=f"Entrega da venda #{venda.pk}",
            )

            return entrega

    # ------------------------------------------------------------------
    # Margem e comissão (T14)
    # ------------------------------------------------------------------
    def _soma_lancamentos(self, filtro):
        total = filtro.aggregate(total=Sum("valor"))["total"]
        return total or Decimal("0.00")

    def calcular_comissao(self):
        """
        Comissão = percentual do vendedor sobre a margem da venda ANTES da
        comissão (preço vendido - custo - despesas lançadas até agora).
        Margem zero ou negativa não gera comissão. Quem não tem perfil de
        vendedor (ex.: gerente) não recebe comissão.
        """
        perfil = getattr(self.vendedor, "dados_vendedor", None)
        if perfil is None:
            return Decimal("0.00")

        despesas = self._soma_lancamentos(
            LancamentoFinanceiro.objects.filter(
                veiculo_id=self.veiculo_id,
                tipo=LancamentoFinanceiro.Tipo.DESPESA,
                excluido=False,
            )
        )
        custo = self.veiculo.custo_aquisicao or Decimal("0.00")
        base = self.valor_venda - custo - despesas

        if base <= 0:
            return Decimal("0.00")

        return (base * perfil.percentual_comissao / Decimal("100")).quantize(
            Decimal("0.01")
        )

    def calcular_margem(self):
        """
        Margem REAL, calculada na hora a partir dos lançamentos. Nunca é
        guardada: despesas novas mudam o resultado, por isso o retorno
        traz o momento exato do cálculo (`calculada_em`).
        """
        calculada_em = timezone.now()

        ativos = LancamentoFinanceiro.objects.filter(excluido=False)
        despesas_veiculo = ativos.filter(
            veiculo_id=self.veiculo_id,
            tipo=LancamentoFinanceiro.Tipo.DESPESA,
        )

        despesas = self._soma_lancamentos(despesas_veiculo)
        despesas_apos_venda = self._soma_lancamentos(
            despesas_veiculo.filter(criado_em__gt=self.criada_em)
        )
        comissao = self._soma_lancamentos(
            ativos.filter(venda=self, tipo=LancamentoFinanceiro.Tipo.COMISSAO)
        )

        preco_vendido = self.valor_venda
        custo = self.veiculo.custo_aquisicao or Decimal("0.00")
        margem = preco_vendido - custo - despesas - comissao

        percentual = (
            (margem / preco_vendido * 100).quantize(Decimal("0.01"))
            if preco_vendido
            else Decimal("0.00")
        )

        return {
            "preco_vendido": preco_vendido,
            "custo_aquisicao": custo,
            "despesas": despesas,
            "despesas_apos_venda": despesas_apos_venda,
            "comissao": comissao,
            "margem": margem,
            "margem_percentual": percentual,
            "negativa": margem < 0,
            "calculada_em": calculada_em,
        }
        
    def __str__(self):
        return f"Venda #{self.pk} — {self.cliente} — {self.veiculo}"


class PagamentoVenda(models.Model):
    """
    Forma de pagamento da venda, copiada da composição da proposta no
    momento do fechamento. Assim, editar a proposta depois não altera
    o que foi efetivamente vendido.
    """

    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada em dinheiro"
        TROCA = "TROCA", "Veículo na troca"
        FINANCIAMENTO = "FINANCIAMENTO", "Saldo financiado"

    venda = models.ForeignKey(
        Venda, on_delete=models.CASCADE, related_name="pagamentos"
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    valor = models.DecimalField(max_digits=12, decimal_places=2)

    # Entrada: data em que o pagamento foi registrado.
    data_pagamento = models.DateField(null=True, blank=True)

    # Troca (T11)
    troca_descricao = models.CharField(max_length=150, blank=True)
    avaliacao_troca = models.ForeignKey(
        AvaliacaoTroca,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pagamentos_venda",
    )

    # Financiamento
    financ_banco = models.CharField(max_length=100, blank=True)
    financ_parcelas = models.PositiveSmallIntegerField(null=True, blank=True)
    financ_valor_parcela = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["id"]

    def clean(self):
        erros = {}

        if self.valor is not None and self.valor <= 0:
            erros["valor"] = "O valor deve ser maior que zero."

        if self.tipo == self.Tipo.FINANCIAMENTO:
            if not self.financ_banco.strip():
                erros["financ_banco"] = "Informe o banco do financiamento."
            if not self.financ_parcelas or self.financ_parcelas < 1:
                erros["financ_parcelas"] = "Informe o número de parcelas."
            if not self.financ_valor_parcela or self.financ_valor_parcela <= 0:
                erros["financ_valor_parcela"] = "Informe o valor da parcela."

        if erros:
            raise ValidationError(erros)

    def __str__(self):
        return f"{self.get_tipo_display()}: R$ {self.valor}"
    

# ============================================================
# T13 - Documentação e entrega
# ============================================================

class EtapaDocumentacao(models.Model):
    """
    Uma etapa do trabalho entre "vendido" e "entregue". É criada junto com a
    venda (Venda.fechar), sempre como PENDENTE, e acompanhada pelo administrativo.
    """

    class Tipo(models.TextChoices):
        TRANSFERENCIA = "TRANSFERENCIA", "Transferência"
        COMUNICACAO_VENDA = "COMUNICACAO_VENDA", "Comunicação de venda"
        NOTA_FISCAL = "NOTA_FISCAL", "Nota fiscal"

    class Situacao(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
        CONCLUIDA = "CONCLUIDA", "Concluída"

    venda = models.ForeignKey(
        Venda, on_delete=models.PROTECT, related_name="etapas_documentacao"
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    situacao = models.CharField(
        max_length=20, choices=Situacao.choices, default=Situacao.PENDENTE
    )

    # Data da situação atual (muda sempre que a situação muda).
    data = models.DateField(default=timezone.localdate)
    observacao = models.CharField(max_length=255, blank=True)

    atualizada_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="etapas_documentacao_atualizadas",
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["venda__data", "venda_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["venda", "tipo"],
                name="uma_etapa_por_tipo_por_venda",
            ),
        ]

    @property
    def concluida(self):
        return self.situacao == self.Situacao.CONCLUIDA

    def atualizar(self, usuario, situacao, data=None, observacao=""):
        """Muda a situação da etapa. Só gerente ou administrativo ativo."""
        if not (
            getattr(usuario, "is_authenticated", False)
            and usuario.ativo
            and (usuario.is_gerente() or usuario.is_administrativo())
        ):
            raise PermissionDenied(
                "Somente gerente ou administrativo ativo pode atualizar a documentação."
            )

        if situacao not in self.Situacao.values:
            raise ValidationError("Situação inválida.")

        data = data or timezone.localdate()
        if data > timezone.localdate():
            raise ValidationError("A data da etapa não pode ser futura.")

        with transaction.atomic():
            venda = Venda.objects.select_for_update().get(pk=self.venda_id)

            if venda.situacao != Venda.Situacao.FECHADA:
                raise ValidationError(
                    "Não é possível alterar a documentação de uma venda cancelada."
                )

            self.situacao = situacao
            self.data = data
            self.observacao = (observacao or "").strip()
            self.atualizada_por = usuario
            self.save()

        return self

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.get_situacao_display()}"


class EntregaVeiculo(models.Model):
    """
    Entrega do veículo ao cliente. Registra data, responsável e o checklist
    assinado. Só existe uma entrega por venda.
    """

    venda = models.OneToOneField(
        Venda, on_delete=models.PROTECT, related_name="entrega"
    )
    data_entrega = models.DateField(default=timezone.localdate)
    responsavel = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="entregas_realizadas"
    )

    # Checklist da entrega (lista fixa).
    documentos_entregues = models.BooleanField(default=False)
    chaves_entregues = models.BooleanField(default=False)
    manual_entregue = models.BooleanField(default=False)
    veiculo_conferido = models.BooleanField(default=False)
    checklist_assinado = models.BooleanField(default=False)

    observacoes = models.TextField(blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    ITENS_CHECKLIST = (
        ("documentos_entregues", "Documentos do veículo entregues"),
        ("chaves_entregues", "Chaves entregues"),
        ("manual_entregue", "Manual e acessórios entregues"),
        ("veiculo_conferido", "Veículo conferido pelo cliente"),
        ("checklist_assinado", "Checklist assinado pelo cliente"),
    )

    class Meta:
        ordering = ["-data_entrega", "-id"]

    @property
    def checklist_completo(self):
        return all(getattr(self, campo) for campo, _ in self.ITENS_CHECKLIST)

    def clean(self):
        if not self.checklist_completo:
            raise ValidationError(
                "Todos os itens do checklist precisam estar marcados e assinados."
            )

        if self.data_entrega and self.data_entrega > timezone.localdate():
            raise ValidationError({"data_entrega": "A data da entrega não pode ser futura."})

    def __str__(self):
        return f"Entrega da venda #{self.venda_id} em {self.data_entrega:%d/%m/%Y}"
    
    
    


# ============================================================
# T16 - Carteira de clientes
# ============================================================

class ConfiguracaoCarteira(models.Model):
    """Configuração única do prazo de retorno à carteira."""

    anos_sem_comprar = models.PositiveSmallIntegerField(
        default=3,
        help_text="Anos desde a última compra válida.",
    )
    atualizado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configuracoes_carteira",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuração da carteira"
        verbose_name_plural = "Configurações da carteira"

    def clean(self):
        super().clean()
        if self.anos_sem_comprar is not None and not 1 <= self.anos_sem_comprar <= 50:
            raise ValidationError({
                "anos_sem_comprar": "Informe um prazo entre 1 e 50 anos."
            })

    def save(self, *args, **kwargs):
        # Existe apenas uma configuração para toda a loja.
        self.pk = 1
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Carteira: {self.anos_sem_comprar} ano(s)"


class ContatoCarteira(models.Model):
    """Histórico de contatos, sem armazenar a fila calculada."""

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="contatos_carteira",
    )
    vendedor = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="contatos_carteira_realizados",
        limit_choices_to={"perfil": Usuario.Perfil.VENDEDOR},
    )
    realizado_em = models.DateTimeField(default=timezone.now)
    observacao = models.TextField(blank=True)
    class Canal(models.TextChoices):
        TELEFONE = "TELEFONE", "Telefone"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        PRESENCIAL = "PRESENCIAL", "Presencial"

    canal = models.CharField(
        max_length=12,
        choices=Canal.choices,
        default=Canal.TELEFONE,
    )
    data_retorno = models.DateField(
        null=True,
        blank=True,
        help_text="Quando voltar a falar com o cliente (opcional).",
    )
    class Meta:
        ordering = ["-realizado_em", "-pk"]
        indexes = [
            models.Index(
                fields=["vendedor", "realizado_em"],
                name="carteira_contato_mes_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.vendedor_id and not self.vendedor.is_vendedor():
            raise ValidationError({
                "vendedor": "O contato deve pertencer a um vendedor."
            })

        if self.data_retorno:
            data_contato = timezone.localtime(self.realizado_em).date()
            if self.data_retorno < data_contato:
                raise ValidationError({
                    "data_retorno": "A data de retorno não pode ser anterior ao contato."
                })
    def __str__(self):
        return f"{self.cliente} - {self.vendedor} - {self.realizado_em:%d/%m/%Y}"
