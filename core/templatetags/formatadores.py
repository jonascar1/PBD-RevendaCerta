import re

from django import template

register = template.Library()


def _digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


@register.filter
def cpf(valor):
    d = _digitos(valor)
    if len(d) != 11:
        return valor or ""
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


@register.filter
def cnpj(valor):
    d = _digitos(valor)
    if len(d) != 14:
        return valor or ""
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


@register.filter
def cep(valor):
    d = _digitos(valor)
    if len(d) != 8:
        return valor or ""
    return f"{d[:5]}-{d[5:]}"


@register.filter
def telefone(valor):
    d = _digitos(valor)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return valor or ""