"""Valida aprovações do CSV, sem modificar o banco. Executar via manage.py shell < validar_aprovacoes.py"""
import csv
from pathlib import Path
from core.models import Veiculo

arquivo = Path('aprovacao_catalogo_244.csv')
with arquivo.open(newline='', encoding='utf-8-sig') as f:
    registros = list(csv.DictReader(f, delimiter=';'))

sim = {'SIM', 'S', '1'}
nao = {'', 'NAO', 'NÃO', 'N', '0'}
erros = []
propostas = []
ids = set()
for linha in registros:
    try:
        pk = int(linha['id'])
        if pk in ids:
            raise ValueError('ID duplicado')
        ids.add(pk)
        atual = Veiculo.objects.filter(pk=pk).first()
        if atual is None:
            raise ValueError('Veículo não encontrado')
        for campo, coluna in [('marca','marca'),('modelo','modelo'),('combustivel','combustivel_atual'),('ano_fabricacao','ano_fabricacao_atual'),('ano_modelo','ano_modelo_atual')]:
            if str(getattr(atual, campo)) != linha[coluna]:
                raise ValueError(f'{campo} mudou no banco desde a exportação')
        mudancas = {}
        for coluna, campo, sugerido in [('aprovar_combustivel','combustivel','combustivel_sugerido')]:
            valor = linha[coluna].strip().upper()
            if valor not in sim | nao:
                raise ValueError(f'{coluna} deve ser SIM ou NÃO')
            if valor in sim:
                novo = linha[sugerido].strip()
                if not novo or len(novo) > 30:
                    raise ValueError('combustível sugerido vazio ou longo demais')
                if novo != atual.combustivel:
                    mudancas[campo] = novo
        valor = linha['aprovar_anos'].strip().upper()
        if valor not in sim | nao:
            raise ValueError('aprovar_anos deve ser SIM ou NÃO')
        if valor in sim:
            anos = [linha['ano_fabricacao_proposto'].strip(), linha['ano_modelo_proposto'].strip()]
            if not all(a.isdigit() for a in anos):
                raise ValueError('ambos os anos propostos são obrigatórios')
            fab, mod = map(int, anos)
            if not (1950 <= fab <= 2027 and fab <= mod <= fab + 1):
                raise ValueError('anos fora da faixa esperada')
            for campo, novo in [('ano_fabricacao', fab),('ano_modelo', mod)]:
                if getattr(atual, campo) != novo:
                    mudancas[campo] = novo
        if mudancas:
            propostas.append((pk, atual.marca, atual.modelo, mudancas))
    except (KeyError, ValueError) as exc:
        erros.append(f'ID {linha.get("id", "?")}: {exc}')
print(f'Linhas: {len(registros)} | alterações aprovadas: {len(propostas)} | erros: {len(erros)}')
for pk, marca, modelo, mudancas in propostas:
    print(f'{pk} - {marca} {modelo}: {mudancas}')
for erro in erros:
    print('ERRO:', erro)
print('SOMENTE PRÉVIA. Nenhum dado foi modificado.')
