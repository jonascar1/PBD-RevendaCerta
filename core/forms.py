import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.validators import MaxLengthValidator
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from .models import (
    AvaliacaoTroca,
    Cliente,
    ComposicaoPagamento,
    ConfiguracaoCarteira,
    ContatoCarteira,
    DecisaoProposta,
    EtapaDocumentacao,
    FotoAvaliacaoTroca,
    LancamentoFinanceiro,
    PerfilVendedor,
    Procura,
    Proposta,
    TelefoneCliente,
    Usuario,
    Veiculo,
)


COMBUSTIVEIS = [
    ("", "Selecione"),
    ("Gasolina", "Gasolina"),
    ("Etanol", "Etanol"),
    ("Flex", "Flex"),
    ("Diesel", "Diesel"),
    ("Elétrico", "Elétrico"),
    ("Híbrido", "Híbrido"),
]


# ==============================================================================
# Funções Auxiliares de Validação e Formatação
# ==============================================================================

def _brl(valor):
    """Formata um Decimal no padrão monetário brasileiro (ex.: 'R$ 1.234,56')."""
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def validar_cpf(valor):
    """Valida dígitos verificadores de um CPF (com ou sem máscara)."""
    cpf = re.sub(r"\D", "", valor or "")

    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False

    numeros = [int(d) for d in cpf]

    soma = sum(numeros[i] * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    primeiro = 0 if resto == 10 else resto

    if numeros[9] != primeiro:
        return False

    soma = sum(numeros[i] * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    segundo = 0 if resto == 10 else resto

    return numeros[10] == segundo


def validar_cnpj(valor):
    """Valida dígitos verificadores de um CNPJ (com ou sem máscara)."""
    cnpj = re.sub(r"\D", "", valor or "")

    if len(cnpj) != 14 or len(set(cnpj)) == 1:
        return False

    numeros = [int(d) for d in cnpj]

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(n * p for n, p in zip(numeros[:12], pesos1))
    resto = soma % 11
    primeiro = 0 if resto < 2 else 11 - resto

    if numeros[12] != primeiro:
        return False

    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(n * p for n, p in zip(numeros[:13], pesos2))
    resto = soma % 11
    segundo = 0 if resto < 2 else 11 - resto

    return numeros[13] == segundo


# ==============================================================================
# Base e Campos Reutilizáveis
# ==============================================================================

class BaseForm:
    """
    Mixin base para todos os formulários do sistema.

    Remove restrições nativas de validação HTML5 (mantendo a validação no servidor),
    padroniza o `id` dos inputs pelo nome do campo e aplica a classe `input-erro`
    nos widgets com falhas de validação.
    """

    use_required_attribute = False

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_id", "%s")
        super().__init__(*args, **kwargs)

        for campo in self.fields.values():
            for atributo in ("required", "maxlength", "minlength", "min", "max"):
                campo.widget.attrs.pop(atributo, None)

    def add_error(self, field, error):
        super().add_error(field, error)
        for nome in self._errors:
            if nome in self.fields:
                widget = self.fields[nome].widget
                classes = widget.attrs.get("class", "").split()
                if "input-erro" not in classes:
                    widget.attrs["class"] = " ".join(classes + ["input-erro"])


class CampoMonetarioBR(forms.DecimalField):
    """Campo decimal que aceita entrada formatada em Real (ex.: 'R$ 18.500,00')."""

    widget = forms.TextInput

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget",
            forms.TextInput(attrs={"inputmode": "decimal"}),
        )
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None

        if isinstance(value, str):
            valor = value.strip().replace("R$", "").replace(" ", "")

            if "," in valor:
                valor = valor.replace(".", "").replace(",", ".")
            elif valor.count(".") > 1:
                valor = valor.replace(".", "")

            value = valor

        try:
            return super().to_python(value)
        except (InvalidOperation, ValueError):
            raise forms.ValidationError(
                "Informe um valor monetário válido.",
                code="invalid",
            )


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    """Campo de upload múltiplo de imagens."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        limpar = super().clean
        if isinstance(data, (list, tuple)):
            return [limpar(arquivo, initial) for arquivo in data if arquivo]
        return [limpar(data, initial)] if data else []


# ==============================================================================
# Autenticação
# ==============================================================================

class LoginForm(BaseForm, forms.Form):
    """Formulário de autenticação de usuários."""

    username = forms.CharField(
        label="Usuário",
        error_messages={"required": "Informe o usuário."},
        widget=forms.TextInput(
            attrs={"placeholder": "Digite seu usuário", "autocomplete": "username"}
        ),
    )
    password = forms.CharField(
        label="Senha",
        strip=False,  # Preserva espaços intencionais na senha.
        error_messages={"required": "Informe a senha."},
        widget=forms.PasswordInput(
            attrs={"placeholder": "Digite sua senha", "autocomplete": "current-password"}
        ),
    )


# ==============================================================================
# Vendedores
# ==============================================================================

class _VendedorComercialMixin(forms.Form):
    """Campos comerciais compartilhados entre cadastro e edição de vendedor."""

    tipo_alcada = forms.ChoiceField(
        label="Tipo de alçada",
        choices=PerfilVendedor.TipoAlcada.choices,
        initial=PerfilVendedor.TipoAlcada.PERCENTUAL,
        error_messages={
            "required": "Selecione o tipo de alçada.",
            "invalid_choice": "Tipo de alçada inválido.",
        },
        widget=forms.RadioSelect,
    )
    valor_alcada = forms.DecimalField(
        label="Limite de desconto",
        max_digits=12,
        decimal_places=2,
        min_value=0,
        initial=0,
        error_messages={
            "required": "Informe o limite de desconto.",
            "invalid": "Informe um valor válido.",
            "min_value": "O limite não pode ser negativo.",
        },
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    percentual_comissao = forms.DecimalField(
        label="Percentual de comissão",
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        initial=0,
        error_messages={
            "required": "Informe o percentual de comissão.",
            "invalid": "Informe um valor válido.",
            "min_value": "A comissão não pode ser negativa.",
            "max_value": "A comissão não pode passar de 100%%.",  # %% escapa o % na formatação do Django.
        },
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_alcada")
        valor = cleaned.get("valor_alcada")
        if (
            tipo == PerfilVendedor.TipoAlcada.PERCENTUAL
            and valor is not None
            and valor > 100
        ):
            self.add_error(
                "valor_alcada", "O limite em percentual não pode passar de 100%."
            )
        return cleaned


class VendedorCadastroForm(BaseForm, _VendedorComercialMixin):
    """Cadastro de usuário vendedor e respectivo perfil comercial."""

    nome = forms.CharField(
        label="Nome completo",
        max_length=150,
        error_messages={"required": "Informe o nome completo."},
        widget=forms.TextInput(attrs={"placeholder": "Digite o nome completo"}),
    )
    username = forms.CharField(
        label="Usuário",
        max_length=150,
        error_messages={"required": "Informe o usuário."},
        widget=forms.TextInput(attrs={"placeholder": "Digite o usuário para login"}),
    )
    email = forms.EmailField(
        label="E-mail",
        required=False,
        error_messages={"invalid": "Informe um e-mail válido."},
        widget=forms.EmailInput(attrs={"placeholder": "Digite o e-mail"}),
    )
    senha = forms.CharField(
        label="Senha",
        strip=False,  # Preserva espaços intencionais na senha.
        error_messages={"required": "Informe a senha."},
        widget=forms.PasswordInput(attrs={"placeholder": "Digite a senha"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        Usuario.username_validator(username)
        if Usuario.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Já existe um usuário com este nome.")
        return username


class VendedorEdicaoForm(BaseForm, _VendedorComercialMixin):
    """Edição de dados cadastrais, status e parâmetros comerciais do vendedor."""

    nome = forms.CharField(
        label="Nome",
        max_length=150,
        error_messages={"required": "Informe o nome."},
        widget=forms.TextInput(attrs={"placeholder": "Digite o nome"}),
    )
    email = forms.EmailField(
        label="E-mail",
        required=False,
        error_messages={"invalid": "Informe um e-mail válido."},
        widget=forms.EmailInput(attrs={"placeholder": "Digite o e-mail"}),
    )
    ativo = forms.TypedChoiceField(
        label="Status",
        choices=[("true", "Ativo"), ("false", "Inativo")],
        coerce=lambda valor: valor == "true",
        error_messages={"required": "Informe o status."},
    )


# ==============================================================================
# Veículos e Preço
# ==============================================================================

class VeiculoForm(BaseForm, forms.ModelForm):
    """Cadastro de veículo no estoque com suporte a múltiplas fotos."""

    combustivel = forms.ChoiceField(
        label="Combustível",
        choices=COMBUSTIVEIS,
        error_messages={
            "required": "Selecione o combustível.",
            "invalid_choice": "Combustível inválido.",
        },
    )
    fotos = MultipleImageField(
        label="Fotos do veículo",
        required=False,
        error_messages={"invalid_image": "Envie apenas imagens JPG, PNG ou WEBP."},
    )

    class Meta:
        model = Veiculo
        fields = [
            "placa",
            "chassi",
            "renavam",
            "marca",
            "modelo",
            "ano_fabricacao",
            "ano_modelo",
            "cor",
            "tipo",
            "cambio",
            "combustivel",
            "quilometragem",
            "opcionais",
            "origem",
            "custo_aquisicao",
            "preco_venda",
            "valor_repasse",
        ]
        labels = {
            "placa": "Placa",
            "chassi": "Chassi",
            "renavam": "Renavam",
            "marca": "Marca",
            "modelo": "Modelo",
            "ano_fabricacao": "Ano de fabricação",
            "ano_modelo": "Ano do modelo",
            "cor": "Cor",
            "tipo": "Tipo",
            "cambio": "Câmbio",
            "quilometragem": "Quilometragem",
            "opcionais": "Opcionais",
            "origem": "Origem do veículo",
            "custo_aquisicao": "Custo de aquisição",
            "preco_venda": "Preço de venda",
            "valor_repasse": "Valor de repasse",
        }
        widgets = {
            "placa": forms.TextInput(attrs={"placeholder": "ABC1D23 ou ABC1234"}),
            "chassi": forms.TextInput(attrs={"placeholder": "17 caracteres"}),
            "renavam": forms.TextInput(
                attrs={"inputmode": "numeric", "placeholder": "Digite o renavam"}
            ),
            "ano_fabricacao": forms.NumberInput(
                attrs={"oninput": "this.value = this.value.slice(0, 4)"}
            ),
            "ano_modelo": forms.NumberInput(
                attrs={"oninput": "this.value = this.value.slice(0, 4)"}
            ),
            "marca": forms.TextInput(attrs={"placeholder": "Ex.: Toyota"}),
            "modelo": forms.TextInput(attrs={"placeholder": "Ex.: Corolla"}),
            "cor": forms.TextInput(attrs={"placeholder": "Ex.: Branco"}),
            "opcionais": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Ex.: ar-condicionado, câmera de ré, bancos de couro...",
                }
            ),
            "custo_aquisicao": forms.NumberInput(
                attrs={"step": "0.01", "placeholder": "0,00"}
            ),
            "preco_venda": forms.NumberInput(
                attrs={"step": "0.01", "placeholder": "0,00"}
            ),
            "valor_repasse": forms.NumberInput(
                attrs={"step": "0.01", "placeholder": "0,00"}
            ),
        }
        error_messages = {
            "placa": {"required": "Informe a placa."},
            "chassi": {"required": "Informe o chassi."},
            "renavam": {"required": "Informe o renavam."},
            "marca": {"required": "Informe a marca."},
            "modelo": {"required": "Informe o modelo."},
            "ano_fabricacao": {
                "required": "Informe o ano de fabricação.",
                "invalid": "Ano inválido.",
            },
            "ano_modelo": {
                "required": "Informe o ano do modelo.",
                "invalid": "Ano inválido.",
            },
            "cor": {"required": "Informe a cor."},
            "quilometragem": {
                "required": "Informe a quilometragem.",
                "invalid": "Quilometragem inválida.",
            },
            "origem": {"required": "Selecione a origem do veículo."},
            "tipo": {"invalid_choice": "Tipo inválido."},
            "cambio": {"invalid_choice": "Câmbio inválido."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["origem"].initial = Veiculo.Origem.COMPRADO

    def clean_renavam(self):
        renavam = re.sub(r"\s", "", self.cleaned_data["renavam"])
        if not renavam.isdigit():
            raise forms.ValidationError("O renavam deve conter apenas números.")
        return renavam

    def clean_ano_fabricacao(self):
        ano = self.cleaned_data["ano_fabricacao"]
        limite = date.today().year + 1
        if not 1900 <= ano <= limite:
            raise forms.ValidationError(f"Informe um ano entre 1900 e {limite}.")
        return ano

    def clean(self):
        # Validações de placa, chassi, custo/repasse por origem e unicidade no estoque
        # são complementadas em Veiculo.clean().
        cleaned = super().clean()
        fabricacao = cleaned.get("ano_fabricacao")
        modelo = cleaned.get("ano_modelo")
        if fabricacao and modelo and not fabricacao <= modelo <= fabricacao + 1:
            self.add_error(
                "ano_modelo",
                "O ano do modelo deve ser igual ao de fabricação ou o ano seguinte.",
            )
        return cleaned


class EditarVeiculoForm(VeiculoForm):
    """Edição de veículo existente bloqueando mudança de origem e de custo pós-venda."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["origem"].initial = self.instance.origem

    def clean_origem(self):
        origem = self.cleaned_data["origem"]
        if self.instance.pk and origem != self.instance.origem:
            raise forms.ValidationError(
                "A origem de um veículo já cadastrado não pode ser alterada."
            )
        return origem

    def clean_custo_aquisicao(self):
        custo = self.cleaned_data["custo_aquisicao"]
        if (
            self.instance.pk
            and self.instance.venda_fechada
            and custo != self.instance.custo_aquisicao
        ):
            raise forms.ValidationError(
                "O custo de aquisição não pode ser alterado após o fechamento da venda."
            )
        return custo


class PrecoVendaForm(BaseForm, forms.Form):
    """Atualização do preço de venda do veículo."""

    preco_venda = forms.DecimalField(
        label="Novo preço de venda",
        max_digits=12,
        decimal_places=2,
        min_value=0,
        error_messages={
            "required": "Informe o preço de venda.",
            "invalid": "Informe um valor válido.",
            "min_value": "O preço não pode ser negativo.",
        },
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )

    def clean_preco_venda(self):
        preco = self.cleaned_data["preco_venda"]
        if preco <= 0:
            raise forms.ValidationError("O preço deve ser maior que zero.")
        return preco


# ==============================================================================
# Clientes
# ==============================================================================

class ClienteForm(BaseForm, forms.ModelForm):
    """Cadastro e edição de clientes PF e PJ com sanitização de campos por tipo."""

    class Meta:
        model = Cliente
        exclude = ["ativo", "criado_em", "atualizado_em"]
        widgets = {
            "data_nascimento": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "email": forms.EmailInput(
                attrs={"placeholder": "cliente@email.com"}
            ),
        }
        error_messages = {
            "email": {"invalid": "Informe um e-mail válido."},
        }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_id", "id_%s")
        super().__init__(*args, **kwargs)

        # Permite envio com máscara (pontos, traços e barras) antes da limpeza.
        for nome in ("cpf", "cnpj", "cep"):
            campo = self.fields[nome]
            campo.max_length = None
            campo.validators = [
                v for v in campo.validators if not isinstance(v, MaxLengthValidator)
            ]

    def _somente_numeros(self, nome):
        return re.sub(r"\D", "", self.cleaned_data.get(nome) or "")

    def clean_cpf(self):
        cpf = self._somente_numeros("cpf")
        tipo = self.cleaned_data.get("tipo")

        if tipo == Cliente.Tipo.PESSOA_FISICA:
            if not validar_cpf(cpf):
                raise forms.ValidationError("Informe um CPF válido.")

            if Cliente.objects.filter(cpf=cpf).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError(
                    "Já existe um cliente cadastrado com este CPF."
                )

        return cpf

    def clean_cnpj(self):
        cnpj = self._somente_numeros("cnpj")
        tipo = self.cleaned_data.get("tipo")

        if tipo == Cliente.Tipo.PESSOA_JURIDICA:
            if not validar_cnpj(cnpj):
                raise forms.ValidationError("Informe um CNPJ válido.")

            if Cliente.objects.filter(cnpj=cnpj).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError(
                    "Já existe um cliente cadastrado com este CNPJ."
                )

        return cnpj

    def clean_cep(self):
        cep = self._somente_numeros("cep")
        if cep and len(cep) != 8:
            raise forms.ValidationError("O CEP deve conter 8 dígitos.")
        return cep

    def clean_data_nascimento(self):
        nascimento = self.cleaned_data.get("data_nascimento")
        tipo = self.cleaned_data.get("tipo")

        if (
            tipo == Cliente.Tipo.PESSOA_FISICA
            and nascimento
            and nascimento > timezone.localdate()
        ):
            raise forms.ValidationError(
                "A data de nascimento não pode ser futura."
            )

        return nascimento

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo")

        # Zera atributos exclusivos do tipo oposto para manter integridade cadastral.
        if tipo == Cliente.Tipo.PESSOA_FISICA:
            cleaned["cnpj"] = ""
            cleaned["razao_social"] = ""
            cleaned["nome_fantasia"] = ""
            cleaned["responsavel"] = ""
        elif tipo == Cliente.Tipo.PESSOA_JURIDICA:
            cleaned["cpf"] = ""
            cleaned["nome"] = ""
            cleaned["data_nascimento"] = None

        return cleaned


class BaseTelefoneFormSet(BaseInlineFormSet):
    """Garante unicidade do telefone principal ou promove o primeiro ativo automaticamente."""

    def clean(self):
        super().clean()

        if any(self.errors):
            return

        ativos = [
            f
            for f in self.forms
            if getattr(f, "cleaned_data", None)
            and not f.cleaned_data.get("DELETE")
            and f.cleaned_data.get("numero")
        ]

        principais = [f for f in ativos if f.cleaned_data.get("principal")]

        if len(principais) > 1:
            raise forms.ValidationError(
                "Marque apenas um telefone como principal."
            )

        if ativos and not principais:
            ativos[0].cleaned_data["principal"] = True
            ativos[0].instance.principal = True


class TelefoneClienteForm(BaseForm, forms.ModelForm):
    class Meta:
        model = TelefoneCliente
        fields = ["numero", "tipo", "principal"]

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_id", "%s")
        super().__init__(*args, **kwargs)

    def clean_numero(self):
        numero = re.sub(r"\D", "", self.cleaned_data.get("numero") or "")
        if len(numero) not in (10, 11):
            raise forms.ValidationError(
                "Informe um telefone com DDD e 10 ou 11 dígitos."
            )
        return numero


TelefoneClienteFormSet = inlineformset_factory(
    Cliente,
    TelefoneCliente,
    form=TelefoneClienteForm,
    formset=BaseTelefoneFormSet,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


# ==============================================================================
# Propostas e Composição de Pagamento
# ==============================================================================

class PropostaForm(BaseForm, forms.ModelForm):
    """
    Registro e edição de proposta comercial.

    Na edição, cliente e veículo são bloqueados para preservar a integridade
    da fila de espera do veículo.
    """

    valor_oferecido = CampoMonetarioBR(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    class Meta:
        model = Proposta
        fields = ["cliente", "veiculo", "valor_oferecido", "data"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "valor_oferecido": forms.TextInput(
                attrs={
                    "inputmode": "decimal",
                    "placeholder": "Ex.: 18.500,00",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        editando = bool(self.instance.pk)

        cliente = self.fields["cliente"]
        veiculo = self.fields["veiculo"]

        cliente.queryset = Cliente.objects.filter(ativo=True).order_by(
            "nome", "razao_social"
        )
        veiculo.queryset = Veiculo.objects.filter(
            situacao__in=[Veiculo.Situacao.DISPONIVEL, Veiculo.Situacao.RESERVADO],
            preco_venda__gt=0,
        ).order_by("marca", "modelo")

        cliente.empty_label = "Selecione o cliente..."
        veiculo.empty_label = "Selecione o veículo..."

        cliente.label_from_instance = lambda c: (
            f"{c.nome_exibicao} — {c.cpf or c.cnpj}"
        )
        veiculo.label_from_instance = lambda v: (
            f"{v.marca} {v.modelo} {v.ano_modelo} — {v.placa}"
            f"{' (reservado)' if v.situacao == Veiculo.Situacao.RESERVADO else ''}"
        )

        cliente.error_messages["required"] = "Selecione o cliente."
        cliente.error_messages["invalid_choice"] = "Selecione um cliente válido."
        veiculo.error_messages["required"] = "Selecione o veículo."
        veiculo.error_messages["invalid_choice"] = (
            "Esse veículo não está disponível para proposta."
        )
        self.fields["valor_oferecido"].error_messages["required"] = (
            "Informe o valor oferecido."
        )
        self.fields["valor_oferecido"].error_messages["invalid"] = (
            "Informe um valor válido."
        )
        self.fields["data"].error_messages["required"] = "Informe a data da proposta."

        if editando:
            cliente.queryset = Cliente.objects.filter(pk=self.instance.cliente_id)
            veiculo.queryset = Veiculo.objects.filter(pk=self.instance.veiculo_id)
            cliente.disabled = True
            veiculo.disabled = True


class PropostaFiltroForm(BaseForm, forms.Form):
    """Filtros de pesquisa para a listagem de propostas."""

    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.all().order_by("id"),
        required=False,
        empty_label="Todos os clientes",
    )
    veiculo = forms.ModelChoiceField(
        queryset=Veiculo.objects.all().order_by("marca", "modelo"),
        required=False,
        empty_label="Todos os veículos",
    )
    situacao = forms.ChoiceField(
        choices=[("", "Todas as situações")] + list(Proposta.Situacao.choices),
        required=False,
    )
    vendedor = forms.ModelChoiceField(
        queryset=Usuario.objects.filter(
            perfil__in=[
                Usuario.Perfil.VENDEDOR,
                Usuario.Perfil.GERENTE,
            ]
        ).order_by("username"),
        required=False,
        empty_label="Todos os vendedores",
    )


class ComposicaoPagamentoForm(BaseForm, forms.ModelForm):
    """Parcela individual da composição de pagamento de uma proposta."""

    valor = CampoMonetarioBR(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    financ_valor_parcela = CampoMonetarioBR(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
    )

    class Meta:
        model = ComposicaoPagamento
        fields = [
            "tipo",
            "valor",
            "troca_descricao",
            "avaliacao_troca",
            "financ_banco",
            "financ_parcelas",
            "financ_valor_parcela",
        ]
        widgets = {
            "valor": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
            "financ_valor_parcela": forms.NumberInput(
                attrs={"step": "0.01", "inputmode": "decimal"}
            ),
            "financ_parcelas": forms.NumberInput(attrs={"step": "1"}),
            "troca_descricao": forms.TextInput(
                attrs={"placeholder": "Ex.: Fiat Uno 2012, placa ABC1D23"}
            ),
            "financ_banco": forms.TextInput(attrs={"placeholder": "Banco"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].choices = [("", "Selecione...")] + list(
            ComposicaoPagamento.Tipo.choices
        )
        self.fields["tipo"].error_messages["required"] = "Selecione o tipo."
        self.fields["tipo"].error_messages["invalid_choice"] = "Tipo inválido."
        self.fields["valor"].error_messages["required"] = "Informe o valor."
        self.fields["valor"].error_messages["invalid"] = "Informe um valor válido."

        avaliacoes = self.fields["avaliacao_troca"]
        avaliacoes.queryset = AvaliacaoTroca.objects.all().order_by("-criado_em")
        avaliacoes.empty_label = "Selecione a avaliação..."
        avaliacoes.label_from_instance = lambda avaliacao: (
            f"{avaliacao.marca} {avaliacao.modelo} "
            f"{avaliacao.ano_modelo} - {avaliacao.placa} "
            f"(R$ {avaliacao.valor_avaliado:,.2f})"
        )

    def clean(self):
        cleaned_data = super().clean()

        tipo = cleaned_data.get("tipo")
        avaliacao = cleaned_data.get("avaliacao_troca")
        valor = cleaned_data.get("valor")

        if tipo == ComposicaoPagamento.Tipo.TROCA:
            if not avaliacao:
                self.add_error(
                    "avaliacao_troca",
                    "Selecione uma avaliação de troca realizada pelo gerente.",
                )
            elif Veiculo.objects.filter(avaliacao_origem=avaliacao).exists():
                self.add_error(
                    "avaliacao_troca",
                    "Esta avaliação já foi utilizada em uma venda e o veículo já entrou no estoque.",
                )
            elif valor is not None and valor != avaliacao.valor_avaliado:
                self.add_error(
                    "valor",
                    "O valor da troca deve ser igual ao valor avaliado pelo gerente.",
                )

        return cleaned_data


class BaseComposicaoFormSet(BaseInlineFormSet):
    """
    Valida a soma das parcelas contra `valor_oferecido` e impede duplicidade de troca.

    A view deve atribuir `formset.valor_oferecido` antes de invocar `is_valid()`.
    """

    valor_oferecido = None
    soma_composicao = Decimal("0.00")

    def clean(self):
        super().clean()

        if any(self.errors):
            return

        total = Decimal("0.00")
        linhas = 0
        avaliacoes_utilizadas = set()

        for form in self.forms:
            dados = getattr(form, "cleaned_data", None)
            if not dados or dados.get("DELETE"):
                continue

            avaliacao = dados.get("avaliacao_troca")
            if avaliacao:
                if avaliacao.pk in avaliacoes_utilizadas:
                    form.add_error(
                        "avaliacao_troca",
                        "Esta avaliação já foi selecionada em outra linha da proposta.",
                    )
                else:
                    avaliacoes_utilizadas.add(avaliacao.pk)

            valor = dados.get("valor")
            if valor is None:
                continue
            total += valor
            linhas += 1

        self.soma_composicao = total

        if linhas == 0:
            raise forms.ValidationError(
                "Informe ao menos uma forma de pagamento."
            )

        if self.valor_oferecido is not None and total != self.valor_oferecido:
            diferenca = self.valor_oferecido - total
            situacao = "faltam" if diferenca > 0 else "sobram"
            raise forms.ValidationError(
                f"A composição não fecha com o valor oferecido: "
                f"{situacao} {_brl(abs(diferenca))}."
            )


ComposicaoFormSet = inlineformset_factory(
    Proposta,
    ComposicaoPagamento,
    form=ComposicaoPagamentoForm,
    formset=BaseComposicaoFormSet,
    extra=1,
    can_delete=True,
)


class DecisaoPropostaForm(BaseForm, forms.Form):
    """Coleta a decisão do gerente sobre propostas fora da alçada do vendedor."""

    acao = forms.ChoiceField(
        choices=[
            (DecisaoProposta.Tipo.APROVACAO, "Aprovar"),
            (DecisaoProposta.Tipo.RECUSA, "Recusar"),
            (DecisaoProposta.Tipo.CONTRAPROPOSTA, "Contraproposta"),
        ],
        error_messages={
            "required": "Escolha uma decisão.",
            "invalid_choice": "Decisão inválida.",
        },
    )
    parecer = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 4, "placeholder": "Explique o motivo da sua decisão..."}
        ),
    )
    novo_valor = CampoMonetarioBR(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
    )


class ConfirmarPropostaForm(BaseForm, forms.Form):
    """Formulário vazio para proteção CSRF na confirmação de proposta."""


# ==============================================================================
# Avaliações de Troca
# ==============================================================================

class AvaliacaoTrocaForm(BaseForm, forms.ModelForm):
    """Laudo técnico e financeiro de veículo ofertado como parte de pagamento."""

    fotos = MultipleImageField(required=False)

    class Meta:
        model = AvaliacaoTroca
        fields = [
            "placa",
            "chassi",
            "renavam",
            "marca",
            "modelo",
            "ano_fabricacao",
            "ano_modelo",
            "cor",
            "combustivel",
            "quilometragem",
            "opcionais",
            "estado_geral",
            "possui_debitos",
            "descricao_debitos",
            "possui_pendencias_documentacao",
            "descricao_pendencias",
            "valor_avaliado",
            "observacoes",
        ]
        widgets = {
            "descricao_debitos": forms.Textarea(attrs={"rows": 3}),
            "descricao_pendencias": forms.Textarea(attrs={"rows": 3}),
            "observacoes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["renavam"].required = True

    def clean_renavam(self):
        renavam = self.cleaned_data.get("renavam", "").strip()
        if len(renavam) != 11 or not renavam.isascii() or not renavam.isdigit():
            raise forms.ValidationError(
                "O Renavam deve conter exatamente 11 dígitos numéricos."
            )
        return renavam

    def clean_fotos(self):
        fotos = self.cleaned_data.get("fotos") or []
        formatos_permitidos = {"JPEG", "PNG", "WEBP"}
        tamanho_maximo = 5 * 1024 * 1024  # 5 MB

        for foto in fotos:
            if foto.size > tamanho_maximo:
                raise forms.ValidationError(
                    f'A foto "{foto.name}" ultrapassa o limite de 5 MB.'
                )

            if foto.image.format not in formatos_permitidos:
                raise forms.ValidationError(
                    f'A foto "{foto.name}" possui um formato não permitido. '
                    "Envie apenas JPG, PNG ou WEBP."
                )

        return fotos


class FotoAvaliacaoTrocaForm(BaseForm, forms.ModelForm):
    class Meta:
        model = FotoAvaliacaoTroca
        fields = ["imagem", "descricao"]


# ==============================================================================
# Operações de Reserva, Venda, Entrega e Documentação
# ==============================================================================

class ReservaForm(BaseForm, forms.Form):
    """Reserva manual de veículo para cliente cadastrado ou avulso."""

    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.filter(ativo=True),
        required=False,
        label="Cliente cadastrado",
        empty_label="Selecione um cliente...",
    )
    cliente_nome = forms.CharField(
        label="Nome do cliente não cadastrado",
        max_length=120,
        required=False,
    )
    cliente_contato = forms.CharField(
        label="Contato do cliente não cadastrado",
        max_length=60,
        required=False,
    )

    def clean(self):
        cleaned_data = super().clean()

        cliente = cleaned_data.get("cliente")
        nome = (cleaned_data.get("cliente_nome") or "").strip()
        contato = (cleaned_data.get("cliente_contato") or "").strip()

        if cliente:
            cleaned_data["cliente_nome"] = cliente.nome_exibicao
            telefone = cliente.telefones.first()
            cleaned_data["cliente_contato"] = (
                telefone.numero if telefone else cliente.email
            ) or "Contato não informado"
        else:
            if not nome:
                self.add_error(
                    "cliente_nome",
                    "Informe o nome do cliente não cadastrado.",
                )
            if not contato:
                self.add_error(
                    "cliente_contato",
                    "Informe o contato do cliente não cadastrado.",
                )

        return cleaned_data


class CancelarReservaForm(BaseForm, forms.Form):
    """Cancelamento de reserva ativa com justificativa obrigatória."""

    motivo = forms.CharField(
        label="Motivo do cancelamento",
        min_length=5,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Explique por que a reserva será cancelada...",
            }
        ),
        error_messages={
            "required": "Informe o motivo do cancelamento.",
        },
    )

    def clean_motivo(self):
        motivo = self.cleaned_data["motivo"].strip()
        if len(motivo) < 5:
            raise forms.ValidationError(
                "O motivo precisa ter pelo menos 5 caracteres."
            )
        return motivo


class AlterarSituacaoForm(BaseForm, forms.Form):
    """Transição de situação do veículo e vinculação de proposta no fechamento de venda."""

    situacao = forms.ChoiceField(
        choices=Veiculo.Situacao.choices,
        error_messages={"invalid_choice": "Situação inválida."},
    )
    motivo = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.all(),
        required=False,
        label="Cliente Comprador",
        empty_label="Selecione um cliente...",
        error_messages={"invalid_choice": "Selecione um cliente válido."},
    )
    proposta = forms.ModelChoiceField(
        queryset=Proposta.objects.none(),
        required=False,
        label="Proposta da venda",
        empty_label="Selecione a proposta...",
    )

    def __init__(self, *args, veiculo=None, **kwargs):
        super().__init__(*args, **kwargs)

        if veiculo is not None:
            self.fields["proposta"].queryset = (
                Proposta.objects.filter(
                    veiculo=veiculo,
                    situacao=Proposta.Situacao.ATIVA,
                    status_aprovacao__in=[
                        Proposta.StatusAprovacao.NAO_NECESSARIA,
                        Proposta.StatusAprovacao.APROVADA,
                    ],
                )
                .select_related("cliente")
                .order_by("-criada_em")
            )

    def clean(self):
        cleaned_data = super().clean()

        situacao = cleaned_data.get("situacao")
        cliente = cleaned_data.get("cliente")
        proposta = cleaned_data.get("proposta")

        if situacao == Veiculo.Situacao.VENDIDO and not cliente:
            self.add_error(
                "cliente",
                "Para registrar a venda, é necessário selecionar o cliente comprador.",
            )

        if situacao == Veiculo.Situacao.VENDIDO and not proposta:
            self.add_error(
                "proposta",
                "Para registrar a venda, é necessário selecionar uma proposta.",
            )

        if situacao == Veiculo.Situacao.VENDIDO and proposta:
            if cliente and proposta.cliente_id != cliente.pk:
                self.add_error(
                    "proposta",
                    "A proposta selecionada não pertence ao cliente comprador.",
                )

            if not proposta.composicao_fecha:
                self.add_error(
                    "proposta",
                    "A composição do pagamento deve fechar exatamente o valor da proposta.",
                )

        return cleaned_data


class CancelarVendaForm(BaseForm, forms.Form):
    """Cancelamento de venda fechada com motivo obrigatório."""

    motivo = forms.CharField(
        label="Motivo do cancelamento",
        min_length=5,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Explique por que a venda será cancelada...",
            }
        ),
        error_messages={
            "required": "Informe o motivo do cancelamento.",
            "min_length": "O motivo precisa ter pelo menos 5 caracteres.",
        },
    )

    def clean_motivo(self):
        return self.cleaned_data["motivo"].strip()


class EntregaVeiculoForm(BaseForm, forms.Form):
    """Checklist de entrega física do veículo vendido ao comprador."""

    data_entrega = forms.DateField(
        label="Data da entrega",
        error_messages={
            "required": "Informe a data da entrega.",
            "invalid": "Data inválida.",
        },
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    documentos_entregues = forms.BooleanField(
        required=False, label="Documentos do veículo entregues"
    )
    chaves_entregues = forms.BooleanField(
        required=False, label="Chaves entregues"
    )
    manual_entregue = forms.BooleanField(
        required=False, label="Manual e acessórios entregues"
    )
    veiculo_conferido = forms.BooleanField(
        required=False, label="Veículo conferido pelo cliente"
    )
    checklist_assinado = forms.BooleanField(
        required=False, label="Checklist assinado pelo cliente"
    )
    observacoes = forms.CharField(
        label="Observações",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_entrega"].initial = timezone.localdate

    def clean_data_entrega(self):
        data = self.cleaned_data["data_entrega"]
        if data > timezone.localdate():
            raise forms.ValidationError("A data da entrega não pode ser futura.")
        return data

    def checklist(self):
        """Retorna o dicionário de itens conferidos no formato esperado por Venda.registrar_entrega()."""
        return {
            campo: self.cleaned_data.get(campo, False)
            for campo in (
                "documentos_entregues",
                "chaves_entregues",
                "manual_entregue",
                "veiculo_conferido",
                "checklist_assinado",
            )
        }


class EtapaDocumentacaoForm(BaseForm, forms.Form):
    """Atualização de etapa documental pós-venda."""

    situacao = forms.ChoiceField(
        choices=EtapaDocumentacao.Situacao.choices,
        error_messages={
            "required": "Informe a situação da etapa.",
            "invalid_choice": "Situação inválida.",
        },
    )
    data = forms.DateField(
        required=False,
        error_messages={"invalid": "Data inválida."},
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    observacao = forms.CharField(required=False, max_length=255)

    def clean_data(self):
        data = self.cleaned_data.get("data")
        if data and data > timezone.localdate():
            raise forms.ValidationError("A data da etapa não pode ser futura.")
        return data


# ==============================================================================
# Despesas Operacionais
# ==============================================================================

class DespesaForm(BaseForm, forms.ModelForm):
    """Lançamento de despesa vinculada a um veículo."""

    class Meta:
        model = LancamentoFinanceiro


        fields = [
            "categoria_despesa",
            "valor",
            "data_lancamento",
            "descricao",
        ]


        labels = {
            "valor": "Valor",
            "data_lancamento": "Data do lançamento",
            "descricao": "Descrição",
            "categoria_despesa": "Categoria da despesa",

        }
        widgets = {
            "valor": forms.NumberInput(attrs={"step": "0.01"}),
            "data_lancamento": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "descricao": forms.Textarea(attrs={"rows": 4,"placeholder": "Ex.: Funilaria, documentação, limpeza...",} ),
            "categoria_despesa": forms.Select(attrs={"class": "form-control"}),}
        
        error_messages = {"valor": {"required":
            "Informe o valor.",
            "invalid": "Informe um valor válido.",},
            "data_lancamento": {
            "required": "Informe a data do lançamento.",
            "invalid": "Data inválida.",
            },
        }

    def clean_valor(self):
        valor = self.cleaned_data["valor"]
        if valor <= 0:
            raise forms.ValidationError("O valor deve ser maior que zero.")
        return valor

    def clean_categoria_despesa(self):
        categoria = self.cleaned_data.get("categoria_despesa")

        if not categoria:
            raise forms.ValidationError(
                "Selecione uma categoria para a despesa."
            )

        return categoria
    
    def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields["data_lancamento"].initial = timezone.localdate


class DespesaEditarForm(DespesaForm):
    """Edição de despesa utilizando input de linha única para descrição."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["descricao"].widget = forms.TextInput()


# ==============================================================================
# Carteira de Clientes e Procuras
# ==============================================================================

class ConfiguracaoCarteiraForm(BaseForm, forms.ModelForm):
    """Configuração do prazo de inatividade para elegibilidade de recompra."""

    class Meta:
        model = ConfiguracaoCarteira
        fields = ["anos_sem_comprar"]
        labels = {
            "anos_sem_comprar": "Anos sem comprar",
        }
        widgets = {
            "anos_sem_comprar": forms.NumberInput(
                attrs={"step": "1", "placeholder": "Ex.: 3"}
            ),
        }

    def clean_anos_sem_comprar(self):
        anos = self.cleaned_data["anos_sem_comprar"]
        if not 1 <= anos <= 50:
            raise forms.ValidationError("Informe um prazo entre 1 e 50 anos.")
        return anos


class ContatoCarteiraForm(BaseForm, forms.ModelForm):
    """Registro de abordagem comercial com cliente da carteira."""

    class Meta:
        model = ContatoCarteira
        fields = ["resultado", "canal", "observacao", "data_retorno"]
        labels = {
            "resultado": "Resultado do contato",
            "canal": "Canal",
            "observacao": "O que foi conversado",
            "data_retorno": "Voltar a falar em",
        }
        widgets = {
            "observacao": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Resumo da conversa..."}
            ),
            "data_retorno": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date"}
            ),
        }
        error_messages = {
            "resultado": {
                "required": "Selecione o resultado do contato.",
                "invalid_choice": "Resultado inválido.",
            },
            "canal": {
                "required": "Selecione o canal do contato.",
                "invalid_choice": "Canal inválido.",
            },
            "data_retorno": {"invalid": "Data inválida."},
        }

    def clean_observacao(self):
        # Mantido obrigatório apenas no form para preservar compatibilidade com registros legados sem observação.
        texto = (self.cleaned_data.get("observacao") or "").strip()
        if not texto:
            raise forms.ValidationError("Resuma o que foi conversado.")
        return texto

    def clean_data_retorno(self):
        retorno = self.cleaned_data.get("data_retorno")
        if retorno and retorno < timezone.localdate():
            raise forms.ValidationError(
                "A data de retorno não pode estar no passado."
            )
        return retorno

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("resultado") == ContatoCarteira.Resultado.NAO_QUER_AGORA
            and not cleaned.get("data_retorno")
        ):
            self.add_error(
                "data_retorno",
                "Informe a data de retorno para quem não quer agora.",
            )
        return cleaned


class ProcuraForm(BaseForm, forms.ModelForm):
    """Cadastro de interesse de compra de cliente para cruzamento automático com estoque."""

    preco_minimo = CampoMonetarioBR(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        label="Preço mínimo",
    )
    preco_maximo = CampoMonetarioBR(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        label="Preço máximo",
    )
    combustivel = forms.ChoiceField(
        label="Combustível",
        choices=COMBUSTIVEIS,
        required=False,
    )

    class Meta:
        model = Procura
        fields = [
            "cliente",
            "tipo",
            "marca_modelo",
            "preco_minimo",
            "preco_maximo",
            "ano_minimo",
            "cambio",
            "combustivel",
            "valido_ate",
        ]
        labels = {
            "cliente": "Cliente",
            "tipo": "Tipo",
            "marca_modelo": "Marca ou modelo",
            "ano_minimo": "Ano mínimo",
            "cambio": "Câmbio",
            "valido_ate": "Procura válida até",
        }
        widgets = {
            "marca_modelo": forms.TextInput(
                attrs={"placeholder": "Ex.: Toyota ou Corolla"}
            ),
            "ano_minimo": forms.NumberInput(
                attrs={"placeholder": "Ex.: 2018"}
            ),
            "valido_ate": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date"}
            ),
        }
        error_messages = {
            "cliente": {
                "required": "Selecione o cliente.",
                "invalid_choice": "Selecione um cliente válido.",
            },
            "tipo": {"invalid_choice": "Tipo inválido."},
            "cambio": {"invalid_choice": "Câmbio inválido."},
            "ano_minimo": {"invalid": "Ano inválido."},
            "valido_ate": {
                "required": "Informe até quando a procura vale.",
                "invalid": "Data inválida.",
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        cliente = self.fields["cliente"]
        cliente.queryset = Cliente.objects.filter(ativo=True).order_by(
            "nome", "razao_social"
        )
        cliente.empty_label = "Selecione o cliente..."
        cliente.label_from_instance = lambda c: (
            f"{c.nome_exibicao} — {c.cpf or c.cnpj}"
        )

        self.fields["valido_ate"].initial = (
            lambda: timezone.localdate() + timedelta(days=30)
        )

    def clean_ano_minimo(self):
        ano = self.cleaned_data.get("ano_minimo")
        if ano is not None and not 1900 <= ano <= 2100:
            raise forms.ValidationError("Informe um ano entre 1900 e 2100.")
        return ano

    def clean_valido_ate(self):
        validade = self.cleaned_data.get("valido_ate")
        if validade and validade < timezone.localdate():
            raise forms.ValidationError(
                "A validade não pode estar no passado."
            )
        return validade