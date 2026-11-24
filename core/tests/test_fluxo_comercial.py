from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from ..models import (Usuario, Veiculo, Cliente, Proposta, DecisaoProposta,
                      ReservaVeiculo, Venda, ComposicaoPagamento, PerfilVendedor,
                      LancamentoFinanceiro, EtapaDocumentacao)

D = Decimal


class FluxoComercial(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gerente = Usuario.objects.create_user(username='gerente', perfil='GERENTE')
        cls.vendedor = Usuario.objects.create_user(username='vendedor', perfil='VENDEDOR')
        cls.outro = Usuario.objects.create_user(username='outro', perfil='VENDEDOR')
        cls.cliente = Cliente.objects.create(tipo='PF', nome='Cliente teste', cpf='52998224725', data_nascimento=date(1990, 1, 1))
        cls.carro = Veiculo.objects.create(placa='ABC1D23', chassi='123456789ABCDEFGH', renavam='12345678901', marca='Fiat', modelo='Uno', ano_fabricacao=2020, ano_modelo=2020, cor='Branco', combustivel='Flex', quilometragem=100, origem='COMPRADO', custo_aquisicao=D('30000'), preco_venda=D('40000'), situacao='DISPONIVEL', criado_por=cls.gerente, tipo_alcada='PERCENTUAL', valor_alcada=D('5'))
        PerfilVendedor.objects.update_or_create(usuario=cls.vendedor, defaults={'percentual_comissao': D('5'), 'editado_por': cls.gerente})

    def proposta(self, valor='38000', vendedor=None):
        return Proposta.objects.create(cliente=self.cliente, veiculo=self.carro, vendedor=vendedor or self.vendedor, valor_oferecido=D(valor))

    def confirmar(self, p):
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.post(reverse('confirmar_proposta', args=[p.pk])).status_code, 302)

    def fechar(self, p, usuario=None):
        return Venda.fechar(self.carro.pk, p.pk, self.cliente.pk, usuario or self.vendedor)

    def test_dentro_alcada(self):
        p = self.proposta()
        self.assertEqual(p.status_aprovacao, 'NAO_NECESSARIA')
        self.assertEqual(p.preco_tabela, D('40000'))
        self.assertFalse(p.decisoes.exists())
        self.assertEqual(p.historico.count(), 1)

    def test_fora_alcada_pedido_e_aprovacao(self):
        p = self.proposta('37999.99')
        self.assertEqual(p.status_aprovacao, 'PENDENTE')
        pedido = p.decisoes.get(tipo='PEDIDO')
        self.assertEqual(pedido.feito_por, self.vendedor)
        self.assertEqual(D(pedido.alcada_no_momento.rstrip('%')), D('5'))
        p.decidir(self.gerente, 'APROVACAO')
        p.refresh_from_db()
        self.assertEqual(p.status_aprovacao, 'APROVADA')
        self.assertEqual(p.decisoes.get(tipo='APROVACAO').feito_por, self.gerente)
        with self.assertRaises(ValidationError):
            p.decidir(self.gerente, 'APROVACAO')

    def test_vendedor_nao_decide(self):
        p = self.proposta('37000')
        with self.assertRaises(PermissionDenied):
            p.decidir(self.vendedor, 'APROVACAO')
        p.refresh_from_db()
        self.assertEqual(p.status_aprovacao, 'PENDENTE')
        self.assertEqual(p.decisoes.count(), 1)

    def test_recusa_promove_fila(self):
        p = self.proposta('37000')
        segunda = self.proposta(vendedor=self.outro)
        terceira = self.proposta()
        self.assertEqual(segunda.situacao, 'AGUARDANDO')
        p.decidir(self.gerente, 'RECUSA', parecer='Desconto excessivo')
        p.refresh_from_db(); segunda.refresh_from_db(); terceira.refresh_from_db()
        self.assertEqual(p.situacao, 'CANCELADA')
        self.assertEqual(p.status_aprovacao, 'RECUSADA')
        self.assertEqual(segunda.situacao, 'ATIVA')
        self.assertEqual(terceira.situacao, 'AGUARDANDO')

    def test_contraproposta_aceite(self):
        p = self.proposta('37000')
        p.decidir(self.gerente, 'CONTRAPROPOSTA', parecer='Novo valor', novo_valor=D('37500'))
        with self.assertRaises(PermissionDenied):
            p.aceitar_contraproposta(self.outro)
        p.aceitar_contraproposta(self.vendedor)
        self.assertEqual(p.valor_oferecido, D('37500'))
        self.assertEqual(p.status_aprovacao, 'APROVADA')
        self.assertEqual(p.historico.count(), 2)
        self.assertTrue(p.decisoes.filter(tipo='ACEITE_CONTRAPROPOSTA').exists())

    def test_contraproposta_invalida(self):
        p = self.proposta('37000')
        with self.assertRaises(ValidationError):
            p.decidir(self.gerente, 'CONTRAPROPOSTA', parecer='Novo valor', novo_valor=D('36000'))
        self.assertEqual(p.decisoes.count(), 1)

    def test_contraproposta_recusa(self):
        p = self.proposta('37000')
        p.decidir(self.gerente, 'CONTRAPROPOSTA', parecer='Novo valor', novo_valor=D('38000'))
        p.recusar_contraproposta(self.vendedor)
        self.assertEqual(p.situacao, 'CANCELADA')
        self.assertTrue(p.decisoes.filter(tipo='RECUSA_CONTRAPROPOSTA').exists())

    def test_pendente_nao_reserva(self):
        p = self.proposta('37000')
        self.confirmar(p)
        self.assertFalse(ReservaVeiculo.objects.filter(veiculo=self.carro).exists())

    def test_reserva_exclusiva_e_expiracao(self):
        p = self.proposta()
        self.confirmar(p)
        r = ReservaVeiculo.objects.get(proposta_origem=p)
        self.confirmar(p)
        self.assertEqual(ReservaVeiculo.objects.filter(veiculo=self.carro).count(), 1)
        segunda = self.proposta(vendedor=self.outro)
        self.assertEqual(segunda.situacao, 'AGUARDANDO')
        ReservaVeiculo.objects.filter(pk=r.pk).update(expira_em=timezone.now()-timedelta(seconds=1))
        self.assertTrue(r.expirar())
        p.refresh_from_db(); segunda.refresh_from_db(); self.carro.refresh_from_db()
        self.assertTrue(r.cancelada)
        self.assertEqual(p.situacao, 'CANCELADA')
        self.assertEqual(segunda.situacao, 'ATIVA')
        self.assertEqual(self.carro.situacao, 'DISPONIVEL')

    def test_venda_composicao_incompleta(self):
        p = self.proposta()
        self.confirmar(p)
        ComposicaoPagamento.objects.create(proposta=p, tipo='ENTRADA', valor=D('1000'))
        with self.assertRaises(ValidationError):
            self.fechar(p)
        self.assertFalse(Venda.objects.exists())
        self.assertTrue(ReservaVeiculo.objects.get(proposta_origem=p).esta_valida())

    def test_venda_pagamentos_comissao_e_margem(self):
        p = self.proposta('37000')
        p.decidir(self.gerente, 'APROVACAO')
        self.confirmar(p)
        ComposicaoPagamento.objects.create(proposta=p, tipo='ENTRADA', valor=D('37000'))
        with self.assertRaises(PermissionDenied):
            self.fechar(p, self.outro)
        venda = self.fechar(p)
        self.carro.refresh_from_db()
        self.assertEqual(venda.soma_pagamentos, D('37000'))
        self.assertEqual(self.carro.situacao, 'VENDIDO')
        self.assertTrue(self.carro.venda_fechada)
        self.assertTrue(ReservaVeiculo.objects.get(proposta_origem=p).cancelada)
        self.assertEqual(LancamentoFinanceiro.objects.get(venda=venda, tipo='COMISSAO').valor, D('350'))
        self.assertEqual(venda.calcular_margem()['margem'], D('6650'))
        self.assertEqual(EtapaDocumentacao.objects.filter(venda=venda).count(), len(EtapaDocumentacao.Tipo.choices))
        with self.assertRaises(ValidationError):
            self.fechar(p)
        self.assertEqual(Venda.objects.count(), 1)
