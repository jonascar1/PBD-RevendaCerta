from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from django.urls import reverse
from core.carteira import calcular_carteira


class RevisaoCarteiraTest(SimpleTestCase):
    def calcular(self, vendedor, hoje, retorno=None, contato=True):
        v1 = SimpleNamespace(pk=1, is_vendedor=lambda: True, get_full_name=lambda: 'V1', username='v1')
        v2 = SimpleNamespace(pk=2, is_vendedor=lambda: True, get_full_name=lambda: 'V2', username='v2')
        cliente = SimpleNamespace(pk=10)
        vendas = [SimpleNamespace(cliente_id=10, cliente=cliente, vendedor=v, vendedor_id=v.pk, data=date(2020, 1, 1), veiculo=None) for v in (v1, v2)]
        registro = SimpleNamespace(cliente_id=10, vendedor_id=1, realizado_em=datetime(2026, 11, 20, 15, tzinfo=timezone.utc), data_retorno=retorno)
        with patch('core.carteira.obter_configuracao_carteira', return_value=SimpleNamespace(anos_sem_comprar=3)), patch('core.carteira.Venda') as venda, patch('core.carteira.Cliente') as clientes, patch('core.carteira.ContatoCarteira') as contatos:
            venda.objects.filter.return_value.select_related.return_value.order_by.return_value = vendas
            clientes.objects.filter.return_value.prefetch_related.return_value = []
            contatos.objects.filter.return_value.values_list.return_value = []
            contatos.objects.filter.return_value.select_related.return_value.order_by.return_value = [registro] if contato else []
            return calcular_carteira(vendedor={1:v1, 2:v2}.get(vendedor), hoje=hoje)

    def test_cliente_na_carteira_dos_dois(self):
        for v in (1, 2):
            self.assertEqual(self.calcular(v, date(2026,11,25), contato=False)['total_hoje'], 1)

    def test_contato_global(self):
        for v in (1, 2):
            dados = self.calcular(v, date(2026,11,25))
            self.assertEqual(dados['total_clientes'], 1)
            self.assertEqual(dados['total_hoje'], 0)

    def test_retorno_futuro_apos_virada(self):
        for v in (1, 2):
            self.assertEqual(self.calcular(v, date(2026,12,1), date(2026,12,5))['total_hoje'], 0)

    def test_retorno_responsavel(self):
        for v, esperado in ((1,1),(2,0),(None,1)):
            self.assertEqual(self.calcular(v, date(2026,12,5), date(2026,12,5))['total_hoje'], esperado)

    def test_rota_estoque(self):
        self.assertEqual(reverse('veiculos'), '/painel/gerente/veiculos/')
