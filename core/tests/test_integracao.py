from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from ..models import Usuario, Veiculo, HistoricoAlcada, MetaMensal, MetaIndividual, HistoricoMeta, ReservaVeiculo, PerfilVendedor
from ..dashboard_metrics import manager_metrics, seller_metrics


class IntegracaoComercial(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gerente = Usuario.objects.create_user(username='gerente', perfil='GERENTE')
        cls.vendedor = Usuario.objects.create_user(username='vendedor', perfil='VENDEDOR')
        cls.outro = Usuario.objects.create_user(username='outro', perfil='VENDEDOR')
        cls.admin = Usuario.objects.create_user(username='administrativo', perfil='ADMINISTRATIVO')
        cls.carro = Veiculo.objects.create(placa='ABC1D23', chassi='123456789ABCDEFGH', renavam='12345678901', marca='Fiat', modelo='Uno', ano_fabricacao=2020, ano_modelo=2020, cor='Branco', combustivel='Flex', quilometragem=100, origem='COMPRADO', custo_aquisicao=Decimal('30000'), preco_venda=Decimal('40000'), situacao='DISPONIVEL', criado_por=cls.gerente)

    def lote(self, ids, tipo='PERCENTUAL', valor='5'):
        return self.client.post(reverse('alcadas_lote'), {'veiculos': ids, 'tipo': tipo, 'valor': valor})

    def test_permissoes(self):
        for usuario in (self.vendedor, self.admin):
            self.client.force_login(usuario)
            for rota in ('alcadas_lote', 'configurar_metas'):
                with self.subTest(usuario=usuario.username, rota=rota):
                    self.assertEqual(self.client.get(reverse(rota)).status_code, 403)
                    self.assertEqual(self.client.post(reverse(rota), {}).status_code, 403)

    def test_lote_auditoria_e_repeticao(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.lote([self.carro.pk]).status_code, 302)
        self.carro.refresh_from_db()
        self.assertEqual(self.carro.valor_alcada, Decimal('5'))
        h = HistoricoAlcada.objects.get(veiculo=self.carro)
        self.assertEqual(h.gerente, self.gerente)
        self.assertEqual(h.valor_anterior, 0)
        self.assertEqual(h.valor_novo, 5)
        self.lote([self.carro.pk])
        self.assertEqual(HistoricoAlcada.objects.count(), 1)

    def test_lote_selecao_invalida_nao_altera(self):
        self.client.force_login(self.gerente)
        self.lote([self.carro.pk, self.carro.pk + 99999])
        self.carro.refresh_from_db()
        self.assertEqual(self.carro.valor_alcada, 0)
        self.assertFalse(HistoricoAlcada.objects.exists())

    def test_lote_valor_acima_preco(self):
        self.client.force_login(self.gerente)
        self.lote([self.carro.pk], 'VALOR', '40001')
        self.carro.refresh_from_db()
        self.assertEqual(self.carro.valor_alcada, 0)
        self.assertFalse(HistoricoAlcada.objects.exists())

    def test_lote_veiculo_vendido(self):
        Veiculo.objects.filter(pk=self.carro.pk).update(situacao='VENDIDO', status='VENDIDO')
        self.client.force_login(self.gerente)
        self.lote([self.carro.pk])
        self.carro.refresh_from_db()
        self.assertEqual(self.carro.valor_alcada, 0)
        self.assertFalse(HistoricoAlcada.objects.exists())

    def test_metas_e_dashboards(self):
        self.client.force_login(self.gerente)
        mes = date(2026, 11, 1)
        url = reverse('configurar_metas') + '?mes=2026-11'
        self.assertEqual(self.client.post(url, {'loja': 25, 'padrao': 5, f'v_{self.vendedor.pk}': 8}).status_code, 302)
        meta = MetaMensal.objects.get(mes=mes)
        self.assertEqual(meta.loja, 25)
        self.assertEqual(MetaIndividual.objects.get(mensal=meta, vendedor=self.vendedor).quantidade, 8)
        self.assertEqual(HistoricoMeta.objects.get(mensal=meta).gerente, self.gerente)
        self.assertEqual(manager_metrics(mes)['goal'], 25)
        self.assertEqual(seller_metrics(self.vendedor, mes)['goal'], 8)
        self.assertEqual(seller_metrics(self.outro, mes)['goal'], 5)
        self.assertIsNone(manager_metrics(date(2026, 12, 1))['goal'])
        self.assertEqual(manager_metrics(mes)['kpis']['sales'], 0)
        self.assertEqual(len(seller_metrics(self.vendedor, mes)['months']), 12)

    def test_comissao_somente_gerente(self):
        perfil = PerfilVendedor(usuario=self.vendedor, percentual_comissao=5, editado_por=self.outro)
        with self.assertRaises(ValidationError):
            perfil.clean()
        perfil.editado_por = self.gerente
        perfil.clean()

    def test_reserva_vencida(self):
        reserva = ReservaVeiculo(veiculo=self.carro, vendedor=self.vendedor, expira_em=timezone.now()-timedelta(minutes=1))
        self.assertFalse(reserva.esta_valida())
        with self.assertRaises(ValidationError):
            reserva.clean()
