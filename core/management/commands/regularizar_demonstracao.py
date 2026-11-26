import random
from decimal import Decimal, ROUND_DOWN
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from core.models import (Usuario, Veiculo, PerfilVendedor, LancamentoFinanceiro,
                         HistoricoAlcada, Venda, Proposta, Cliente)


class Command(BaseCommand):
    help = 'Regulariza custos, alçadas e comissões do banco de demonstração.'

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        if connection.vendor != 'postgresql' or connection.settings_dict['NAME'] != 'revendacerta_demo':
            raise CommandError('Banco não autorizado.')
        if any(m.objects.exists() for m in (Venda, Proposta, Cliente, HistoricoAlcada)):
            raise CommandError('Banco comercial não está no estado inicial esperado.')
        veiculos = list(Veiculo.objects.select_for_update().order_by('pk'))
        if len(veiculos) != 244 or any(v.valor_alcada != 0 or v.origem != 'COMPRADO' for v in veiculos):
            raise CommandError('Catálogo diferente do estado esperado.')
        gerente = Usuario.objects.get(username='jonas', perfil='GERENTE', is_active=True)
        comissoes = {'monik': 10, 'joao': 10, 'berg': 8, 'valter': 8, 'ana': 10, 'rayane': 8, 'alberto': 8}
        perfis = list(PerfilVendedor.objects.select_for_update().select_related('usuario').all())
        if {p.usuario.username for p in perfis} != set(comissoes) or any(p.percentual_comissao != 0 for p in perfis):
            raise CommandError('Perfis diferentes do estado esperado.')
        custos = LancamentoFinanceiro.objects.filter(tipo='CUSTO_AQUISICAO', excluido=False)
        ids = set(custos.values_list('veiculo_id', flat=True))
        faltantes = [v for v in veiculos if v.pk not in ids]
        if custos.count() != 238 or len(ids) != 238 or {v.pk for v in faltantes} != {1,2,3,4,5,6}:
            raise CommandError('Custos diferentes do estado esperado.')
        rng = random.Random(20261125)
        confirmar = options['confirmar']
        zeros = 0
        for v in veiculos:
            custo, preco = v.custo_aquisicao, v.preco_venda
            if custo is None or custo <= 0 or preco is None or preco <= 0:
                raise CommandError(f'Preço ou custo inválido: {v}')
            if v.pk not in ids:
                self.stdout.write(f'Aquisição: {v} — R$ {custo}')
                l = LancamentoFinanceiro(veiculo=v, tipo='CUSTO_AQUISICAO', valor=custo,
                    descricao='Aquisição do veículo', registrado_por=gerente,
                    data_lancamento=timezone.localtime(v.criado_em).date())
                l.full_clean()
                if confirmar:
                    l.save()
            limite = min(max(Decimal(0), preco-custo)*Decimal('0.35'), preco*Decimal(rng.randint(150,500))/10000)
            sorteio = rng.random()
            tipo = 'PERCENTUAL' if sorteio < .75 else 'VALOR'
            if sorteio < .05:
                valor = Decimal(0)
            elif tipo == 'PERCENTUAL':
                valor = (limite/preco*100).quantize(Decimal('.01'), rounding=ROUND_DOWN)
            else:
                valor = (limite/100).to_integral_value(rounding=ROUND_DOWN)*100
            zeros += valor == 0
            h = HistoricoAlcada(veiculo=v, gerente=gerente, tipo_anterior=v.tipo_alcada,
                valor_anterior=v.valor_alcada, tipo_novo=tipo, valor_novo=valor)
            h.full_clean()
            v.tipo_alcada, v.valor_alcada = tipo, valor
            for campo in ('tipo_alcada', 'valor_alcada'):
                v._meta.get_field(campo).clean(getattr(v,campo), v)
            if confirmar:
                h.save()
                Veiculo.objects.filter(pk=v.pk).update(tipo_alcada=tipo, valor_alcada=valor)
        for p in perfis:
            p.percentual_comissao = Decimal(comissoes[p.usuario.username])
            p.editado_por = gerente
            p.full_clean()
            self.stdout.write(f'Comissão: {p.usuario.username} — {p.percentual_comissao}%')
            if confirmar:
                p.save(update_fields=['percentual_comissao','editado_por','editado_em'])
        self.stdout.write(f'Custos a regularizar: {len(faltantes)}; alçadas: {len(veiculos)}; sem desconto: {zeros}; comissões: {len(perfis)}')
        if confirmar:
            if custos.count() != 244 or HistoricoAlcada.objects.count() != 244:
                raise CommandError('Falha na conferência final.')
            self.stdout.write(self.style.SUCCESS('Regularização concluída.'))
        else:
            self.stdout.write('SIMULAÇÃO: nenhuma alteração realizada.')
