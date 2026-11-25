from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.carteira import calcular_carteira
from core.models import (
    Cliente, ConfiguracaoCarteira, ContatoCarteira, Proposta,
    Usuario, Veiculo, Venda,
)


class CarteiraClientesTest(TestCase):
    hoje = date(2026, 11, 24)
    antiga = date(2022, 11, 24)

    @classmethod
    def setUpTestData(cls):
        cls.gerente = Usuario.objects.create_user(username='gerente_teste', perfil='GERENTE')
        cls.vendedor = Usuario.objects.create_user(username='vendedor_teste', perfil='VENDEDOR')
        cls.outro = Usuario.objects.create_user(username='outro_teste', perfil='VENDEDOR')
        cls.comprador = Cliente.objects.create(tipo='PF', nome='Cliente teste carteira', cpf='52998224725', data_nascimento=date(1990, 1, 1))
        ConfiguracaoCarteira.objects.update_or_create(pk=1, defaults={'anos_sem_comprar': 3})

    def venda(self, data=None, vendedor=None, situacao=Venda.Situacao.FECHADA):
        vendedor = vendedor or self.vendedor
        n = Veiculo.objects.count() + 1
        carro = Veiculo.objects.create(
            placa=f'ABC{n:04d}', chassi=f'123456789AB{n:06d}', renavam=f'{n:011d}',
            marca='Fiat', modelo='Uno', ano_fabricacao=2020, ano_modelo=2020,
            cor='Branco', combustivel='Flex', quilometragem=100, origem='COMPRADO',
            custo_aquisicao=Decimal('30000'), preco_venda=Decimal('40000'),
            situacao='DISPONIVEL', criado_por=self.gerente,
            tipo_alcada='PERCENTUAL', valor_alcada=Decimal('5'),
        )
        proposta = Proposta.objects.create(cliente=self.comprador, veiculo=carro, vendedor=vendedor, valor_oferecido=Decimal('40000'))
        # Cria o histórico diretamente: o alvo é a carteira, não o fechamento comercial.
        return Venda.objects.create(proposta=proposta, veiculo=carro, cliente=self.comprador,
            vendedor=vendedor, data=data or self.antiga, preco_tabela=Decimal('40000'),
            valor_venda=Decimal('40000'), situacao=situacao, fechada_por=vendedor)

    def contato(self, data=date(2026, 11, 10), retorno=None, resultado=ContatoCarteira.Resultado.AINDA_COM_CARRO):
        contato = ContatoCarteira(cliente=self.comprador, vendedor=self.vendedor,
            realizado_em=timezone.make_aware(datetime.combine(data, time(12))),
            data_retorno=retorno, resultado=resultado)
        contato.full_clean()
        contato.save()
        return contato

    def conferir(self, elegiveis, fila, vendedor=None):
        dados = calcular_carteira(vendedor=vendedor or self.vendedor, hoje=self.hoje)
        self.assertEqual(dados['total_clientes'], elegiveis)
        self.assertEqual(dados['total_hoje'], fila)
        self.assertEqual([x['cliente'].pk for x in dados['linhas_hoje']], [self.comprador.pk] if fila else [])
        return dados

    def test_01_compra_antiga(self):
        self.venda(); self.conferir(1, 1)

    def test_02_limite_exato(self):
        self.venda(date(2023, 11, 24)); self.conferir(1, 1)

    def test_03_compra_recente(self):
        self.venda(date(2024, 11, 24)); self.conferir(0, 0)

    def test_04_recompra_com_outro_vendedor(self):
        self.venda(); self.venda(date(2025, 11, 24), self.outro)
        self.conferir(0, 0); self.conferir(0, 0, self.outro)

    def test_05_dois_vendedores(self):
        self.venda(); self.venda(date(2023, 1, 1), self.outro)
        self.conferir(1, 1); self.conferir(1, 1, self.outro)
        self.assertEqual(calcular_carteira(hoje=self.hoje)['total_clientes'], 1)

    def test_06_venda_cancelada(self):
        self.venda(situacao=Venda.Situacao.CANCELADA); self.conferir(0, 0)

    def test_07_cliente_inativo(self):
        self.venda(); self.comprador.desativar(); self.conferir(0, 0)

    def test_08_contatado_no_mes(self):
        self.venda(); self.contato(); self.conferir(1, 0)

    def test_09_retorno_hoje(self):
        self.venda(); self.contato(retorno=self.hoje)
        self.assertEqual(self.conferir(1, 1)['retornos_hoje'], 1)

    def test_10_retorno_atrasado(self):
        self.venda(); self.contato(retorno=date(2026, 11, 20)); self.conferir(1, 1)

    def test_11_retorno_futuro(self):
        self.venda(); self.contato(retorno=date(2026, 12, 1), resultado=ContatoCarteira.Resultado.NAO_QUER_AGORA)
        self.conferir(1, 0)

    def test_12_retorno_futuro_apos_mudanca_mes(self):
        self.venda(); self.contato(data=date(2026, 10, 25), retorno=date(2026, 12, 1))
        self.conferir(1, 0)

    def test_13_trocou_em_outra_loja(self):
        self.venda(); self.contato(resultado=ContatoCarteira.Resultado.TROCOU_OUTRA_LOJA)
        self.assertEqual(self.conferir(0, 0)['trocaram_outra_loja'], 1)

    def test_14_vendedor_sem_historico(self):
        self.venda(vendedor=self.outro); self.conferir(0, 0)

    def test_15_tela_vendedor_exibe_cliente_elegivel(self):
        self.venda()
        self.client.force_login(self.vendedor)
        with patch('core.carteira.timezone.localdate', return_value=self.hoje):
            resposta = self.client.get(reverse('carteira_vendedor'))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context['carteira']['total_hoje'], 1)
        self.assertContains(resposta, self.comprador.nome)
