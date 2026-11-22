
import csv
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.http import require_GET

from .decorators import perfil_requerido
from .relatorios_exportacao import obter_dados_exportacao

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    LongTable,
    TableStyle,
    KeepTogether,
)

def _obter_dados(request):
    hoje = timezone.localdate()

    return obter_dados_exportacao(
        data_inicio=request.GET.get(
            "data_inicio",
            hoje.replace(day=1).isoformat(),
        ),
        data_fim=request.GET.get(
            "data_fim",
            hoje.isoformat(),
        ),
        dias_parados=request.GET.get("dias_parados", "30"),
    )


def _formatar_csv(valor):
    if isinstance(valor, Decimal):
        return str(valor).replace(".", ",")

    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")

    return str(valor) if valor is not None else ""


@perfil_requerido("GERENTE")
@require_GET
def exportar_relatorio_csv(request):
    try:
        dados = _obter_dados(request)
    except (ValueError, TypeError, OverflowError) as erro:
        return HttpResponseBadRequest(str(erro))

    resposta = HttpResponse(
        content_type="text/csv; charset=utf-8"
    )

    resposta["Content-Disposition"] = (
        'attachment; filename="vendacerta_relatorios.csv"'
    )

    # BOM para compatibilidade com Excel.
    resposta.write("\ufeff")

    escritor = csv.writer(
        resposta,
        delimiter=";",
    )

    inicio, fim = dados["periodo"]

    escritor.writerow(["VENDACERTA - RELATÓRIOS"])
    escritor.writerow([
        "Período",
        inicio.strftime("%d/%m/%Y"),
        fim.strftime("%d/%m/%Y"),
    ])
    escritor.writerow([
        "Limite de carros parados (dias)",
        dados["dias_parados"],
    ])
    escritor.writerow([])

    for nome, secao in dados["secoes"].items():
        escritor.writerow([nome.upper()])
        escritor.writerow(secao["cabecalhos"])

        for linha in secao["linhas"]:
            escritor.writerow([
                _formatar_csv(valor)
                for valor in linha
            ])

        escritor.writerow([])

    return resposta

@perfil_requerido("GERENTE")
@require_GET
def exportar_relatorio_excel(request):
    try:
        dados = _obter_dados(request)
    except (ValueError, TypeError, OverflowError) as erro:
        return HttpResponseBadRequest(str(erro))

    workbook = Workbook()
    workbook.remove(workbook.active)

    inicio, fim = dados["periodo"]

    for nome, secao in dados["secoes"].items():
        planilha = workbook.create_sheet(title=nome)

        total_colunas = len(secao["cabecalhos"])

        planilha.merge_cells(
            start_row=1,
            start_column=1,
            end_row=1,
            end_column=total_colunas,
        )

        titulo = planilha.cell(
            row=1,
            column=1,
            value=f"VENDACERTA | {nome.upper()}",
        )
        titulo.font = Font(
            size=16,
            bold=True,
            color="FFFFFF",
        )
        titulo.fill = PatternFill(
            "solid",
            fgColor="172554",
        )
        titulo.alignment = Alignment(vertical="center")
        planilha.row_dimensions[1].height = 32

        planilha.cell(
            row=2,
            column=1,
            value=(
                f"Período: {inicio:%d/%m/%Y} a "
                f"{fim:%d/%m/%Y}"
            ),
        )

        planilha.cell(
            row=3,
            column=1,
            value=(
                "Carros parados: "
                f"{dados['dias_parados']} dias ou mais"
            ),
        )

        linha_cabecalho = 5

        for indice, cabecalho in enumerate(
            secao["cabecalhos"],
            start=1,
        ):
            celula = planilha.cell(
                row=linha_cabecalho,
                column=indice,
                value=cabecalho,
            )
            celula.font = Font(
                bold=True,
                color="FFFFFF",
            )
            celula.fill = PatternFill(
                "solid",
                fgColor="2563EB",
            )

        for indice_linha, valores in enumerate(
            secao["linhas"],
            start=6,
        ):
            for indice_coluna, valor in enumerate(
                valores,
                start=1,
            ):
                celula = planilha.cell(
                    row=indice_linha,
                    column=indice_coluna,
                )

                if isinstance(valor, Decimal):
                    celula.value = float(valor)
                    celula.number_format = '#,##0.00'
                else:
                    celula.value = valor

                if isinstance(valor, date):
                    celula.number_format = "DD/MM/YYYY"

                if indice_linha % 2 == 0:
                    celula.fill = PatternFill(
                        "solid",
                        fgColor="EFF6FF",
                    )

        planilha.freeze_panes = "A6"

        ultima_linha = max(
            5,
            5 + len(secao["linhas"]),
        )

        planilha.auto_filter.ref = (
            f"A5:{get_column_letter(total_colunas)}"
            f"{ultima_linha}"
        )

        for coluna in range(1, total_colunas + 1):
            letra = get_column_letter(coluna)

            valores_coluna = [
                str(secao["cabecalhos"][coluna - 1])
            ]

            valores_coluna.extend(
                str(linha[coluna - 1] or "")
                for linha in secao["linhas"]
            )

            largura = min(
                max(
                    max(map(len, valores_coluna)) + 3,
                    16,
                ),
                45,
            )

            planilha.column_dimensions[letra].width = largura

    arquivo = BytesIO()
    workbook.save(arquivo)
    arquivo.seek(0)

    resposta = HttpResponse(
        arquivo.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

    resposta["Content-Disposition"] = (
        'attachment; filename="vendacerta_relatorios.xlsx"'
    )

    return resposta



def _texto_pdf(valor):
    if valor is None:
        return "—"

    if isinstance(valor, Decimal):
        return f"{valor:,.2f}".replace(",", "X").replace(
            ".", ","
        ).replace("X", ".")

    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")

    return str(valor)


def _rodape_pdf(canvas, documento):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)

    canvas.drawString(
        36,
        22,
        "VENDACERTA | Relatório Gerencial",
    )

    canvas.drawRightString(
        documento.pagesize[0] - 36,
        22,
        f"Página {documento.page}",
    )

    canvas.restoreState()


@perfil_requerido("GERENTE")
@require_GET
def exportar_relatorio_pdf(request):
    try:
        dados = _obter_dados(request)
    except (ValueError, TypeError, OverflowError) as erro:
        return HttpResponseBadRequest(str(erro))

    arquivo = BytesIO()

    documento = SimpleDocTemplate(
        arquivo,
        pagesize=landscape(A4),
        rightMargin=36,
        leftMargin=36,
        topMargin=42,
        bottomMargin=42,
        title="Relatórios Gerenciais | VENDACERTA",
        author="VENDACERTA",
    )

    estilos = getSampleStyleSheet()

    estilos["Title"].textColor = colors.HexColor("#172554")
    estilos["Heading2"].textColor = colors.HexColor("#1D4ED8")
    estilos["Normal"].leading = 13

    estilo_celula = estilos["BodyText"].clone("CelulaRelatorio")
    estilo_celula.fontSize = 7
    estilo_celula.leading = 9

    estilo_cabecalho = estilo_celula.clone("CabecalhoRelatorio")
    estilo_cabecalho.textColor = colors.white
    estilo_cabecalho.fontName = "Helvetica-Bold"

    elementos = []

    elementos.append(
        Paragraph(
            "VENDACERTA — Relatórios Gerenciais",
            estilos["Title"],
        )
    )

    inicio, fim = dados["periodo"]

    elementos.append(
        Paragraph(
            f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}",
            estilos["Normal"],
        )
    )

    elementos.append(
        Paragraph(
            "Carros parados: "
            f"{dados['dias_parados']} dias ou mais",
            estilos["Normal"],
        )
    )

    elementos.append(Spacer(1, 18))

    for nome, secao in dados["secoes"].items():
        titulo = Paragraph(
            escape(nome),
            estilos["Heading2"],
        )

        cabecalhos = [
            Paragraph(
                escape(str(cabecalho)),
                estilo_cabecalho,
            )
            for cabecalho in secao["cabecalhos"]
        ]

        linhas = [cabecalhos]

        for valores in secao["linhas"]:
            linhas.append([
                Paragraph(
                    escape(_texto_pdf(valor)),
                    estilo_celula,
                )
                for valor in valores
            ])

        if len(linhas) == 1:
            linhas.append([
                Paragraph(
                    "Nenhum registro encontrado.",
                    estilo_celula,
                )
            ] + [""] * (len(cabecalhos) - 1))

        largura_total = documento.width
        largura_coluna = largura_total / len(cabecalhos)

        tabela = LongTable(
            linhas,
            colWidths=[
                largura_coluna
                for _ in cabecalhos
            ],
            repeatRows=1,
            hAlign="LEFT",
        )

        tabela.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#1D4ED8"),
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#EFF6FF"),
                    ],
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, 0),
                    0.5,
                    colors.HexColor("#93C5FD"),
                ),
            ])
        )

        elementos.append(
            KeepTogether([
                titulo,
                Spacer(1, 6),
            ])
        )

        elementos.append(tabela)
        elementos.append(Spacer(1, 20))

    documento.build(
        elementos,
        onFirstPage=_rodape_pdf,
        onLaterPages=_rodape_pdf,
    )

    arquivo.seek(0)

    resposta = HttpResponse(
        arquivo.getvalue(),
        content_type="application/pdf",
    )

    resposta["Content-Disposition"] = (
        'attachment; filename="vendacerta_relatorios.pdf"'
    )

    return resposta
