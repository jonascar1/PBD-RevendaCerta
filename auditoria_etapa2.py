"""Revenda Certa — auditoria etapa 2, somente leitura.
Execute: python manage.py shell < auditoria_etapa2.py
Gera pendencias_catalogo_etapa2.csv com dados ATUAIS do banco.
"""
import csv
from pathlib import Path
from core.models import Veiculo

# Limites de triagem: indicam necessidade de conferir versão e mercado,
# NÃO são substitutos automaticamente aprovados.
MINIMOS = {
    ('BYD','Dolphin Mini'):2024, ('BYD','Dolphin'):2023,
    ('BYD','Seal'):2022, ('GWM','Ora 03'):2020,
    ('Hyundai','Ioniq 5'):2021, ('Tesla','Model Y'):2020,
    ('Volkswagen','ID.4'):2020, ('BMW','iX'):2021,
    ('Porsche','Taycan'):2019, ('Renault','Kardian'):2023,
}
MAXIMOS_BR = {
    ('Chevrolet','Celta'):2015, ('Chevrolet','Classic'):2016,
    ('Chevrolet','Corsa'):2012, ('Chevrolet','Astra'):2011,
    ('Chevrolet','Vectra'):2011, ('Fiat','Palio'):2018,
    ('Fiat','Punto'):2017, ('Ford','Ka'):2021,
    ('Ford','Fusion'):2020,
}
CAMPOS = ['id','marca','modelo','ano_fabricacao','ano_modelo',
          'combustivel','tipo','cambio','alertas','prioridade',
          'versao_real_escolhida','combustivel_proposto','ano_fabricacao_proposto',
          'ano_modelo_proposto','tipo_proposto','cambio_proposto','observacoes']
registros = list(Veiculo.objects.order_by('marca','modelo','id').values(
    'id','marca','modelo','ano_fabricacao','ano_modelo','combustivel','tipo','cambio'))
contagem = {'ALTA':0,'MEDIA':0,'BAIXA':0}
saida = Path('pendencias_catalogo_etapa2.csv')
with saida.open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=CAMPOS, delimiter=';')
    w.writeheader()
    for v in registros:
        chave = (v['marca'].strip(),v['modelo'].strip())
        alertas=[]
        if chave in MINIMOS and v['ano_fabricacao'] < MINIMOS[chave]:
            alertas.append(f"Ano anterior ao início aproximado da linha ({MINIMOS[chave]}); conferir mercado")
        if chave in MAXIMOS_BR and v['ano_fabricacao'] > MAXIMOS_BR[chave]:
            alertas.append(f"Ano posterior ao fim da linha brasileira ({MAXIMOS_BR[chave]}); conferir mercado")
        if v['ano_modelo'] < v['ano_fabricacao'] or v['ano_modelo'] > v['ano_fabricacao']+1:
            alertas.append('Relação fabricação/ano-modelo incomum')
        if not v['tipo']:
            alertas.append('Tipo vazio')
        if not v['cambio']:
            alertas.append('Câmbio vazio')
        if v['combustivel'] == 'Flex':
            alertas.append('Flex: verificar versão e mercado')
        prioridade = 'ALTA' if any('Ano ' in a or 'vazio' in a for a in alertas) else ('MEDIA' if alertas else 'BAIXA')
        contagem[prioridade] += 1
        w.writerow({**v, 'alertas':' | '.join(alertas), 'prioridade':prioridade})
print(f'Registros consultados: {len(registros)} | prioridades: {contagem}')
print(f'Arquivo criado: {saida.resolve()}')
print('SOMENTE LEITURA: nenhum dado foi alterado.')
