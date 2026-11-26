"""Add photographed inventory to an existing isolated demonstration."""
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.core.files.storage import storages
from django.db import connection, transaction
from core.demo_http_probe import PATTERN, schema_scope
from core.demo_lifecycle import lifecycle_lock
from core.demo_local_runtime import active
from core.models import Usuario, Veiculo, FotoVeiculo, LancamentoFinanceiro


class Command(BaseCommand):
    help = 'Amplia estoque fictício com fotos existentes; simulação por padrão.'

    def add_arguments(self, parser):
        parser.add_argument('schema')
        parser.add_argument('--confirmar', action='store_true')

    def handle(self, *args, **opts):
        schema = opts['schema']
        if not PATTERN.fullmatch(schema):
            raise CommandError('Schema demonstrativo obrigatório.')
        fields = ('marca', 'modelo', 'tipo', 'ano_fabricacao', 'ano_modelo', 'cor', 'combustivel', 'cambio', 'quilometragem', 'preco_venda')
        with lifecycle_lock():
            with schema_scope('public'):
                source = Veiculo.objects.filter(situacao='DISPONIVEL', status='DISPONIVEL', preco_venda__gt=0, fotos__isnull=False).distinct().order_by('pk').prefetch_related('fotos')
                catalog = [(v.pk, {f: getattr(v, f) for f in fields}, [p.imagem.name for p in v.fotos.all() if p.imagem.name.startswith('veiculos/')]) for v in source]
            backend = storages['media_original']
            if hasattr(backend, 'bucket'):
                keys = {o.key for o in backend.bucket.objects.filter(Prefix='veiculos/') if o.size > 0}
                catalog = [(pk, attrs, [k for k in photos if k in keys]) for pk, attrs, photos in catalog]
            else:
                catalog = [(pk, attrs, [k for k in photos if backend.exists(k)]) for pk, attrs, photos in catalog]
            with schema_scope(schema), transaction.atomic():
                if not active():
                    raise CommandError('Demonstração expirada.')
                with connection.cursor() as cursor:
                    cursor.execute('SELECT id FROM demo_lifecycle WHERE id=1 FOR UPDATE')
                gerente = Usuario.objects.get(username='gerente', perfil='GERENTE')
                used = set(FotoVeiculo.objects.values_list('imagem', flat=True))
                plates = set(Veiculo.objects.values_list('placa', flat=True))
                added = 0
                for pk, attrs, photos in catalog:
                    photos = list(dict.fromkeys(photos))
                    if not photos or used.intersection(photos):
                        continue
                    if pk > 9999:
                        raise CommandError('Identificador fora do intervalo previsto.')
                    plate = f'DNY{pk:04d}'
                    if plate in plates:
                        continue
                    v = Veiculo(**attrs, placa=plate, chassi=f'9RXDEMZ{pk:010d}', renavam=f'98{pk:09d}', origem='COMPRADO', custo_aquisicao=(attrs['preco_venda']*Decimal('.8')).quantize(Decimal('.01')), situacao='DISPONIVEL', status='DISPONIVEL', criado_por=gerente, tipo_alcada='PERCENTUAL', valor_alcada=3)
                    v.full_clean(validate_unique=False, validate_constraints=False)
                    v.save()
                    FotoVeiculo.objects.bulk_create([FotoVeiculo(veiculo=v, imagem=k, ordem=i, principal=i==0) for i,k in enumerate(photos[:5])])
                    LancamentoFinanceiro.objects.create(veiculo=v, tipo='CUSTO_AQUISICAO', valor=v.custo_aquisicao, registrado_por=gerente)
                    used.update(photos)
                    added += 1
                available = Veiculo.objects.filter(situacao='DISPONIVEL', status='DISPONIVEL', fotos__isnull=False).distinct()
                self.stdout.write(f'Novos veículos: {added}; disponíveis com fotos: {available.count()}; marcas: {available.values("marca").distinct().count()}')
                if not opts['confirmar']:
                    transaction.set_rollback(True)
                    self.stdout.write('SIMULAÇÃO: nenhuma alteração persistida.')
