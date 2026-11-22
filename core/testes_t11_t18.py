"""Testes adicionais T11–T18. Executar: python manage.py test core --verbosity 2.

Preserva core/tests.py (T10). Banco isolado gerenciado pelo Django.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .carteira import calcular_carteira, data_limite_carteira
from .models import (
    AvaliacaoTroca, AvisoProcura, Cliente, ConfiguracaoCarteira,
    ContatoCarteira, LancamentoFinanceiro, Procura, Proposta, Venda, Veiculo,
)
from .tests import DadosT10


class BaseT11T18(DadosT10):
    def setUp(self):
        self.preparar()

    def outra_unidade(self, indice):
        return Veiculo.objects.create(
            placa=f'XYZ{indice}A{indice}3',
            chassi=f'9BWZZZ377VT{indice:06d}',
            renavam=f'{indice:011d}', marca='Volkswagen', modelo='Gol',
            ano_fabricacao=2020, ano_modelo=2021, cor='Prata',
            combustivel='Flex', quilometragem=30000,
            origem=Veiculo.Origem.COMPRADO,
            custo_aquisicao=Decimal('30000.00'),
            preco_venda=Decimal('40000.00'),
            situacao=Veiculo.Situacao.DISPONIVEL,
            status=Veiculo.Status.DISPONIVEL, criado_por=self.gerente,
            tipo=Veiculo.Tipo.HATCH, cambio=Veiculo.Cambio.MANUAL,
        )

    def venda_registrada(self, veiculo=None, vendedor=None, cliente=None, dias=1300):
        veiculo = veiculo or self.veiculo
        vendedor = vendedor or self.vendedor
        cliente = cliente or self.cliente
        proposta = Proposta.objects.create(
            cliente=cliente, veiculo=veiculo, vendedor=vendedor,
            valor_oferecido=Decimal('40000.00'),
        )
        return Venda.objects.create(
            proposta=proposta, veiculo=veiculo, cliente=cliente,
            vendedor=vendedor, fechada_por=vendedor,
            data=timezone.localdate() - timedelta(days=dias),
            preco_tabela=Decimal('40000.00'), valor_venda=Decimal('40000.00'),
        )

    def procura(self, **campos):
        dados = {
            'cliente': self.cliente, 'vendedor': self.vendedor,
            'valido_ate': timezone.localdate() + timedelta(days=30),
        }
        dados.update(campos)
        return Procura.objects.create(**dados)


class TestesT11Trocas(BaseT11T18, TestCase):
    def avaliacao(self, **campos):
        dados = dict(
            placa='TST1A23', chassi='9BWZZZ377VT004299',
            marca='Fiat', modelo='Uno', ano_fabricacao=2019,
            ano_modelo=2020, cor='Branco', combustivel='Flex',
            quilometragem=70000, estado_geral=AvaliacaoTroca.EstadoGeral.BOM,
            valor_avaliado=Decimal('22000.00'), avaliado_por=self.gerente,
        )
        dados.update(campos)
        return AvaliacaoTroca(**dados)

    def test_avaliacao_gerente_valida(self):
        self.avaliacao().full_clean()

    def test_avaliacao_por_vendedor_rejeitada(self):
        with self.assertRaises(ValidationError):
            self.avaliacao(avaliado_por=self.vendedor).full_clean()

    def test_debitos_exigem_descricao(self):
        with self.assertRaises(ValidationError):
            self.avaliacao(possui_debitos=True).full_clean()

    def test_valor_avaliado_deve_ser_positivo(self):
        with self.assertRaises(ValidationError):
            self.avaliacao(valor_avaliado=Decimal('0')).full_clean()


class TestesT12Fechamento(BaseT11T18, TestCase):
    def test_venda_registra_dados_essenciais(self):
        venda = self.venda_registrada()
        self.assertEqual(venda.cliente_id, self.cliente.pk)
        self.assertEqual(venda.vendedor_id, self.vendedor.pk)
        self.assertEqual(venda.valor_venda, Decimal('40000.00'))
        self.assertEqual(venda.situacao, Venda.Situacao.FECHADA)

    def test_vendedor_nao_pode_cancelar_venda(self):
        venda = self.venda_registrada()
        with self.assertRaises(PermissionDenied):
            venda.cancelar(self.vendedor, 'Tentativa não autorizada')


class TestesT14Margem(BaseT11T18, TestCase):
    def lancamento(self, tipo, valor, **campos):
        return LancamentoFinanceiro.objects.create(
            veiculo=self.veiculo, tipo=tipo, valor=Decimal(valor),
            registrado_por=self.gerente, **campos,
        )

    def test_margem_recalcula_com_despesa_posterior(self):
        venda = self.venda_registrada()
        antes = venda.calcular_margem()['margem']
        self.lancamento(LancamentoFinanceiro.Tipo.DESPESA, '250.00')
        depois = venda.calcular_margem()['margem']
        self.assertEqual(antes - depois, Decimal('250.00'))

    def test_despesa_excluida_nao_reduz_margem(self):
        venda = self.venda_registrada()
        antes = venda.calcular_margem()['margem']
        self.lancamento(LancamentoFinanceiro.Tipo.DESPESA, '250.00', excluido=True)
        self.assertEqual(venda.calcular_margem()['margem'], antes)

    def test_margem_negativa_e_sinalizada(self):
        venda = self.venda_registrada()
        self.lancamento(LancamentoFinanceiro.Tipo.DESPESA, '50000.00')
        self.assertTrue(venda.calcular_margem()['negativa'])


class TestesT16Carteira(BaseT11T18, TestCase):
    def test_configuracao_padrao_tres_anos(self):
        self.assertEqual(calcular_carteira()['anos_configurados'], 3)

    def test_prazo_em_ano_bissexto(self):
        from datetime import date
        self.assertEqual(data_limite_carteira(date(2028, 2, 29), 1), date(2027, 2, 28))

    def test_cliente_antigo_entra_na_carteira(self):
        self.venda_registrada(dias=1500)
        self.assertEqual(calcular_carteira(vendedor=self.vendedor)['total_clientes'], 1)

    def test_cliente_inativo_nao_entra(self):
        self.venda_registrada(dias=1500)
        self.cliente.desativar()
        self.assertEqual(calcular_carteira()['total_clientes'], 0)

    def test_nova_compra_reinicia_prazo_para_todos(self):
        self.venda_registrada(dias=1500)
        self.venda_registrada(veiculo=self.outra_unidade(1), vendedor=self.outro_vendedor, dias=20)
        self.assertEqual(calcular_carteira(vendedor=self.vendedor)['total_clientes'], 0)
        self.assertEqual(calcular_carteira(vendedor=self.outro_vendedor)['total_clientes'], 0)

    def test_multiplos_vendedores_compartilham_cliente_elegivel(self):
        self.venda_registrada(dias=1600)
        self.venda_registrada(veiculo=self.outra_unidade(2), vendedor=self.outro_vendedor, dias=1400)
        self.assertEqual(calcular_carteira(vendedor=self.vendedor)['total_clientes'], 1)
        self.assertEqual(calcular_carteira(vendedor=self.outro_vendedor)['total_clientes'], 1)
        self.assertEqual(calcular_carteira()['total_clientes'], 1)

    def test_venda_cancelada_nao_conta(self):
        venda = self.venda_registrada(dias=1500)
        Venda.objects.filter(pk=venda.pk).update(situacao=Venda.Situacao.CANCELADA)
        self.assertEqual(calcular_carteira()['total_clientes'], 0)

    def test_prazo_gerente_pode_configurar(self):
        config = ConfiguracaoCarteira.objects.get(pk=1) if ConfiguracaoCarteira.objects.exists() else ConfiguracaoCarteira()
        config.anos_sem_comprar = 5
        config.atualizado_por = self.gerente
        config.save()
        self.venda_registrada(dias=1500)
        self.assertEqual(calcular_carteira()['total_clientes'], 0)


class TestesT17Contatos(BaseT11T18, TestCase):
    def test_contato_com_retorno_anterior_e_invalido(self):
        contato = ContatoCarteira(
            cliente=self.cliente, vendedor=self.vendedor,
            data_retorno=timezone.localdate() - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            contato.full_clean()

    def test_contato_do_mes_sai_da_fila_diaria(self):
        self.venda_registrada(dias=1500)
        ContatoCarteira.objects.create(
            cliente=self.cliente, vendedor=self.vendedor,
            canal=ContatoCarteira.Canal.WHATSAPP, observacao='Ligação concluída',
        )
        carteira = calcular_carteira(vendedor=self.vendedor)
        self.assertEqual(carteira['total_clientes'], 1)
        self.assertEqual(carteira['total_hoje'], 0)
        self.assertEqual(carteira['contatados_mes'], 1)

    def test_retorno_hoje_volta_a_fila(self):
        self.venda_registrada(dias=1500)
        ContatoCarteira.objects.create(
            cliente=self.cliente, vendedor=self.vendedor,
            data_retorno=timezone.localdate(),
        )
        self.assertEqual(calcular_carteira(vendedor=self.vendedor)['total_hoje'], 1)

    def test_contato_de_um_vendedor_nao_marca_o_outro(self):
        self.venda_registrada(dias=1600)
        self.venda_registrada(veiculo=self.outra_unidade(3), vendedor=self.outro_vendedor, dias=1400)
        ContatoCarteira.objects.create(cliente=self.cliente, vendedor=self.vendedor)
        self.assertEqual(calcular_carteira(vendedor=self.vendedor)['total_hoje'], 0)
        self.assertEqual(calcular_carteira(vendedor=self.outro_vendedor)['total_hoje'], 1)


class TestesT18Procuras(BaseT11T18, TestCase):
    def test_preco_maximo_inferior_ao_minimo_e_invalido(self):
        procura = self.procura(preco_minimo=Decimal('90000'), preco_maximo=Decimal('50000'))
        with self.assertRaises(ValidationError):
            procura.full_clean()

    def test_procura_compativel_com_veiculo(self):
        procura = self.procura(marca_modelo='volkswagen gol', preco_maximo=Decimal('50000'))
        self.assertTrue(procura.combina_com(self.veiculo))
        self.veiculo.preco_venda = Decimal('60000')
        self.assertFalse(procura.combina_com(self.veiculo))

    def test_procura_vencida_e_encerrada_automaticamente(self):
        procura = self.procura()
        Procura.objects.filter(pk=procura.pk).update(valido_ate=timezone.localdate() - timedelta(days=1))
        self.assertEqual(Procura.encerrar_vencidas(), 1)
        procura.refresh_from_db()
        self.assertEqual(procura.situacao, Procura.Situacao.VENCIDA)

    def test_vendedor_de_outra_procura_nao_pode_encerrar(self):
        procura = self.procura()
        with self.assertRaises(PermissionDenied):
            procura.encerrar(self.outro_vendedor)

    def test_cruzamento_nao_duplica_avisos(self):
        procura = self.procura(marca_modelo='Gol')
        self.assertEqual(Procura.cruzar_com_veiculo(self.veiculo), 1)
        self.assertEqual(Procura.cruzar_com_veiculo(self.veiculo), 0)
        self.assertEqual(AvisoProcura.objects.filter(procura=procura, veiculo=self.veiculo).count(), 1)

    def test_gerente_pode_encerrar_procura(self):
        procura = self.procura()
        procura.encerrar(self.gerente)
        self.assertEqual(procura.situacao, Procura.Situacao.ENCERRADA)

class TestesT13Documentacao(BaseT11T18, TestCase):
    def test_vendedor_nao_pode_registrar_entrega(self):
        venda = self.venda_registrada()
        with self.assertRaises(PermissionDenied):
            venda.registrar_entrega(self.vendedor)

    def test_entrega_recusada_se_veiculo_nao_esta_vendido(self):
        venda = self.venda_registrada()
        with self.assertRaises(ValidationError):
            venda.registrar_entrega(self.gerente)


class TestesT15Historico(BaseT11T18, TestCase):
    def test_vendedor_nao_acessa_historico_gerencial(self):
        self.client.force_login(self.vendedor)
        resposta = self.client.get(reverse('historico_veiculo', args=[self.veiculo.pk]))
        self.assertEqual(resposta.status_code, 403)

    def test_gerente_acessa_historico_de_veiculo(self):
        self.client.force_login(self.gerente)
        resposta = self.client.get(reverse('historico_veiculo', args=[self.veiculo.pk]))
        self.assertEqual(resposta.status_code, 200)

    def test_vendedor_nao_acessa_historico_de_cliente_gerencial(self):
        self.client.force_login(self.vendedor)
        resposta = self.client.get(reverse('historico_cliente', args=[self.cliente.pk]))
        self.assertEqual(resposta.status_code, 403)


class TestesPermissoesT16T18(BaseT11T18, TestCase):
    def test_vendedor_nao_configura_carteira(self):
        self.client.force_login(self.vendedor)
        resposta = self.client.get(reverse('configurar_carteira'))
        self.assertEqual(resposta.status_code, 403)

    def test_gerente_nao_registra_contato_como_vendedor(self):
        self.client.force_login(self.gerente)
        resposta = self.client.get(reverse('registrar_contato_carteira', args=[self.cliente.pk]))
        self.assertEqual(resposta.status_code, 403)

    def test_contato_cliente_fora_da_carteira_bloqueado(self):
        self.client.force_login(self.vendedor)
        resposta = self.client.post(reverse('registrar_contato_carteira', args=[self.cliente.pk]), {})
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(ContatoCarteira.objects.count(), 0)
