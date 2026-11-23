"""Django shell: python manage.py shell < aplicar_aprovacoes.py
Prévia por padrão; aplicação somente com REVENDACERTA_APLICAR=SIM.
"""
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from django.db import transaction
from core.models import Veiculo

ARQUIVO = Path('aprovacao_catalogo_244.csv')
SIM = {'SIM', 'S', '1'}
NAO = {'', 'NAO', 'NÃO', 'N', '0'}
APLICAR = os.environ.get('REVENDACERTA_APLICAR', '').upper() == 'SIM'
CAMPOS_IDENTIDADE = {'marca': 'marca', 'modelo': 'modelo', 'combustivel': 'combustivel_atual',
                    'ano_fabricacao': 'ano_fabricacao_atual', 'ano_modelo': 'ano_modelo_atual'}


def preparar(registros, veiculos):
    erros, propostas, vistos = [], [], set()
    for linha in registros:
        ident = linha.get('id', '?')
        try:
            pk = int(ident)
            if pk in vistos:
                raise ValueError('ID duplicado')
            vistos.add(pk)
            obj = veiculos.get(pk)
            if obj is None:
                raise ValueError('Veículo ausente no banco')
            for campo, coluna in CAMPOS_IDENTIDADE.items():
                if str(getattr(obj, campo)) != linha[coluna].strip():
                    raise ValueError(f'{campo} diverge do CSV')
            mudancas = {}
            aprovacao = linha['aprovar_combustivel'].strip().upper()
            if aprovacao not in SIM | NAO:
                raise ValueError('aprovar_combustivel inválido')
            if aprovacao in SIM:
                novo = linha['combustivel_sugerido'].strip()
                if not novo or len(novo) > 30:
                    raise ValueError('combustível proposto inválido')
                if novo != obj.combustivel:
                    mudancas['combustivel'] = novo
            aprovacao_anos = linha['aprovar_anos'].strip().upper()
            if aprovacao_anos not in SIM | NAO:
                raise ValueError('aprovar_anos inválido')
            if aprovacao_anos in SIM:
                fab_s, mod_s = (linha['ano_fabricacao_proposto'].strip(), linha['ano_modelo_proposto'].strip())
                if not fab_s.isdigit() or not mod_s.isdigit():
                    raise ValueError('anos propostos ausentes')
                fab, mod = int(fab_s), int(mod_s)
                if not (1950 <= fab <= 2027 and fab <= mod <= fab + 1):
                    raise ValueError('anos propostos fora do intervalo')
                for campo, novo in [('ano_fabricacao', fab), ('ano_modelo', mod)]:
                    if getattr(obj, campo) != novo:
                        mudancas[campo] = novo
            if mudancas:
                propostas.append((obj, mudancas))
        except (ValueError, KeyError) as exc:
            erros.append(f'ID {ident}: {exc}')
    if len(vistos) != len(veiculos):
        erros.append(f'CSV contém {len(vistos)} IDs únicos, banco contém {len(veiculos)} veículos')
    if set(veiculos) != vistos:
        erros.append('Conjunto de IDs do CSV difere dos IDs do banco')
    return erros, propostas


if not ARQUIVO.is_file():
    raise SystemExit(f'CSV não encontrado: {ARQUIVO.resolve()}')
with ARQUIVO.open(newline='', encoding='utf-8-sig') as f:
    registros = list(csv.DictReader(f, delimiter=';'))
if not registros:
    raise SystemExit('CSV vazio')

# Na aplicação, o bloqueio e a comparação são feitos dentro da mesma transação.
with transaction.atomic():
    consulta = Veiculo.objects.all().order_by('pk')
    if APLICAR:
        consulta = consulta.select_for_update()
    veiculos = {obj.pk: obj for obj in consulta}
    erros, propostas = preparar(registros, veiculos)
    print(f'Registros CSV: {len(registros)} | Banco: {len(veiculos)} | Alterações: {len(propostas)} | Erros: {len(erros)}')
    for erro in erros:
        print('ERRO:', erro)
    for obj, mudancas in propostas:
        print(f'{obj.pk} - {obj.marca} {obj.modelo}: ' + ', '.join(
            f'{campo}: {getattr(obj, campo)!r} -> {novo!r}' for campo, novo in mudancas.items()))
    if erros:
        raise SystemExit('Validação falhou; nenhuma alteração foi realizada.')
    if not APLICAR:
        print('PRÉVIA: banco não alterado. Para aplicar, use REVENDACERTA_APLICAR=SIM.')
    elif not propostas:
        print('Nenhuma mudança pendente. Banco não alterado.')
    else:
        agora = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
        backup = Path(f'backup_catalogo_antes_{agora}.json')
        payload = {
            'gerado_em_utc': datetime.now(timezone.utc).isoformat(),
            'origem_csv': str(ARQUIVO),
            'total_veiculos': len(veiculos),
            'alteracoes': [
                {'id': obj.pk, 'marca': obj.marca, 'modelo': obj.modelo,
                 'antes': {campo: getattr(obj, campo) for campo in mudancas},
                 'depois': mudancas} for obj, mudancas in propostas
            ],
        }
        # Backup deve ser gravado antes da primeira alteração.
        with backup.open('x', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f'Backup gravado: {backup.resolve()}')
        for obj, mudancas in propostas:
            Veiculo.objects.filter(pk=obj.pk).update(**mudancas)
        print(f'CONCLUÍDO: {len(propostas)} veículos atualizados. Guarde o backup.')
