"""Testes automatizados da T10 do VendaCerta.

Copie este conteúdo para core/tests.py (ou para um módulo em core/tests/).
Os testes de concorrência exigem PostgreSQL e usam TransactionTestCase.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Cliente,
    HistoricoSituacaoVeiculo,
    PerfilVendedor,
    Proposta,
    ReservaVeiculo,
    Usuario,
    Veiculo,
)


class DadosT10:
    """Factories mínimas usando os campos existentes nos arquivos enviados."""

    def preparar(self):
        self.gerente = Usuario.objects.create_user(
            username="gerente_t10", password="SenhaForte123!", perfil=Usuario.Perfil.GERENTE
        )
        self.vendedor = Usuario.objects.create_user(
            username="vendedor_t10", password="SenhaForte123!", perfil=Usuario.Perfil.VENDEDOR
        )
        self.outro_vendedor = Usuario.objects.create_user(
            username="vendedor2_t10", password="SenhaForte123!", perfil=Usuario.Perfil.VENDEDOR
        )
        self.administrativo = Usuario.objects.create_user(
            username="administrativo_t10", password="SenhaForte123!",
            perfil=Usuario.Perfil.ADMINISTRATIVO,
        )
        for usuario in (self.vendedor, self.outro_vendedor):
            PerfilVendedor.objects.create(
                usuario=usuario,
                tipo_alcada=PerfilVendedor.TipoAlcada.PERCENTUAL,
                valor_alcada=Decimal("10.00"),
                percentual_comissao=Decimal("5.00"),
            )
        self.veiculo = Veiculo.objects.create(
            placa="ABC1D23", chassi="9BWZZZ377VT004251", renavam="12345678901",
            marca="Volkswagen", modelo="Gol", ano_fabricacao=2020,
            ano_modelo=2021, cor="Prata", combustivel="Flex",
            quilometragem=30000, origem=Veiculo.Origem.COMPRADO,
            custo_aquisicao=Decimal("30000.00"), preco_venda=Decimal("40000.00"),
            situacao=Veiculo.Situacao.DISPONIVEL,
            status=Veiculo.Status.DISPONIVEL, criado_por=self.gerente,
        )
        self.cliente = Cliente.objects.create(
            tipo=Cliente.Tipo.PESSOA_FISICA, nome="Cliente T10",
            cpf="12345678909", data_nascimento=timezone.localdate() - timedelta(days=10000),
        )

    def proposta(self, *, vendedor=None, valor="40000.00", situacao=None):
        proposta = Proposta.objects.create(
            cliente=self.cliente, veiculo=self.veiculo,
            vendedor=vendedor or self.vendedor,
            valor_oferecido=Decimal(valor),
        )
        if situacao is not None and proposta.situacao != situacao:
            # Monta cenários sem disparar novamente as regras do save().
            Proposta.objects.filter(pk=proposta.pk).update(situacao=situacao)
            proposta.refresh_from_db()
        return proposta

    def reserva(self, *, expira_em=None, proposta=None):
        reserva = ReservaVeiculo.objects.create(
            veiculo=self.veiculo,
            cliente=self.cliente,
            cliente_nome="Cliente T10", cliente_contato="81999999999",
            vendedor=self.vendedor, proposta_origem=proposta,
            expira_em=expira_em or timezone.now() + timedelta(hours=24),
        )
        Veiculo.objects.filter(pk=self.veiculo.pk).update(
            situacao=Veiculo.Situacao.RESERVADO,
            status=Veiculo.Status.RESERVADO,
        )
        self.veiculo.refresh_from_db()
        return reserva


class ReservaModelT10(DadosT10, TestCase):
    def setUp(self):
        self.preparar()

    def test_reserva_nova_tem_prazo_futuro(self):
        reserva = self.reserva()
        self.assertGreater(reserva.expira_em, reserva.criada_em)
        self.assertTrue(reserva.esta_valida())
        self.assertEqual(self.veiculo.reserva_ativa.pk, reserva.pk)

    def test_prazo_passado_reprovado_pela_validacao(self):
        reserva = ReservaVeiculo(
            veiculo=self.veiculo, cliente_nome="Teste", cliente_contato="9999",
            vendedor=self.vendedor, expira_em=timezone.now() - timedelta(minutes=1),
        )
        with self.assertRaises(ValidationError):
            reserva.full_clean()

    def test_expirar_antes_do_prazo_nao_altera_reserva(self):
        reserva = self.reserva()
        self.assertFalse(reserva.expirar())
        reserva.refresh_from_db()
        self.veiculo.refresh_from_db()
        self.assertFalse(reserva.cancelada)
        self.assertEqual(self.veiculo.situacao, Veiculo.Situacao.RESERVADO)

    def test_expiracao_libera_veiculo_e_registra_historico(self):
        reserva = self.reserva()
        ReservaVeiculo.objects.filter(pk=reserva.pk).update(
            expira_em=timezone.now() - timedelta(seconds=1)
        )
        reserva.refresh_from_db()
        self.assertTrue(reserva.expirar())
        reserva.refresh_from_db()
        self.veiculo.refresh_from_db()
        self.assertTrue(reserva.cancelada)
        self.assertIsNotNone(reserva.cancelada_em)
        self.assertIn("expirad", reserva.motivo_cancelamento.lower())
        self.assertEqual(self.veiculo.situacao, Veiculo.Situacao.DISPONIVEL)
        self.assertEqual(self.veiculo.status, Veiculo.Status.DISPONIVEL)
        self.assertTrue(HistoricoSituacaoVeiculo.objects.filter(
            veiculo=self.veiculo, situacao_nova=Veiculo.Situacao.DISPONIVEL
        ).exists())

    def test_expiracao_e_idempotente(self):
        reserva = self.reserva()
        ReservaVeiculo.objects.filter(pk=reserva.pk).update(
            expira_em=timezone.now() - timedelta(minutes=1)
        )
        reserva.refresh_from_db()
        self.assertTrue(reserva.expirar())
        quantidade = HistoricoSituacaoVeiculo.objects.filter(veiculo=self.veiculo).count()
        self.assertFalse(reserva.expirar())
        self.assertEqual(
            HistoricoSituacaoVeiculo.objects.filter(veiculo=self.veiculo).count(), quantidade
        )

    def test_expiracao_cancela_proposta_que_gerou_reserva(self):
        proposta = self.proposta()
        reserva = self.reserva(proposta=proposta)
        ReservaVeiculo.objects.filter(pk=reserva.pk).update(
            expira_em=timezone.now() - timedelta(minutes=1)
        )
        reserva.refresh_from_db()
        self.assertTrue(reserva.expirar())
        proposta.refresh_from_db()
        self.assertEqual(proposta.situacao, Proposta.Situacao.CANCELADA)

    def test_expiracao_promove_primeira_proposta_da_fila(self):
        reserva = self.reserva()
        primeira = self.proposta(situacao=Proposta.Situacao.AGUARDANDO)
        segunda = self.proposta(vendedor=self.outro_vendedor,
                                situacao=Proposta.Situacao.AGUARDANDO)
        ReservaVeiculo.objects.filter(pk=reserva.pk).update(
            expira_em=timezone.now() - timedelta(minutes=1)
        )
        reserva.refresh_from_db()
        reserva.expirar()
        primeira.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual(primeira.situacao, Proposta.Situacao.ATIVA)
        self.assertEqual(segunda.situacao, Proposta.Situacao.AGUARDANDO)

    def test_promocao_nao_ultrapassa_proposta_ativa(self):
        ativa = self.proposta()
        aguardando = self.proposta(situacao=Proposta.Situacao.AGUARDANDO)
        Proposta.ativar_aguardando(self.veiculo.pk)
        ativa.refresh_from_db()
        aguardando.refresh_from_db()
        self.assertEqual(ativa.situacao, Proposta.Situacao.ATIVA)
        self.assertEqual(aguardando.situacao, Proposta.Situacao.AGUARDANDO)

    def test_promocao_nao_acontece_com_veiculo_reservado(self):
        self.reserva()
        aguardando = self.proposta()
        self.assertEqual(aguardando.situacao, Proposta.Situacao.AGUARDANDO)
        Proposta.ativar_aguardando(self.veiculo.pk)
        aguardando.refresh_from_db()
        self.assertEqual(aguardando.situacao, Proposta.Situacao.AGUARDANDO)

    def test_promocao_nao_acontece_com_veiculo_vendido(self):
        aguardando = self.proposta(situacao=Proposta.Situacao.AGUARDANDO)
        Veiculo.objects.filter(pk=self.veiculo.pk).update(
            situacao=Veiculo.Situacao.VENDIDO, status=Veiculo.Status.VENDIDO
        )
        Proposta.ativar_aguardando(self.veiculo.pk)
        aguardando.refresh_from_db()
        self.assertEqual(aguardando.situacao, Proposta.Situacao.AGUARDANDO)

    def test_proposta_criada_durante_reserva_entra_na_fila(self):
        self.reserva()
        proposta = self.proposta()
        self.assertEqual(proposta.situacao, Proposta.Situacao.AGUARDANDO)

    def test_proposta_criada_com_outra_ativa_entra_na_fila(self):
        primeira = self.proposta()
        segunda = self.proposta(vendedor=self.outro_vendedor)
        self.assertEqual(primeira.situacao, Proposta.Situacao.ATIVA)
        self.assertEqual(segunda.situacao, Proposta.Situacao.AGUARDANDO)

    def test_constraint_impede_duas_reservas_nao_canceladas(self):
        self.reserva()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ReservaVeiculo.objects.create(
                    veiculo=self.veiculo, vendedor=self.outro_vendedor,
                    cliente_nome="Outro", cliente_contato="8888",
                    expira_em=timezone.now() + timedelta(hours=24),
                )
        self.assertEqual(
            ReservaVeiculo.objects.filter(veiculo=self.veiculo, cancelada=False).count(), 1
        )

    def test_constraint_impede_duplicidade_mesmo_se_primeira_estiver_vencida(self):
        reserva = self.reserva()
        ReservaVeiculo.objects.filter(pk=reserva.pk).update(
            expira_em=timezone.now() - timedelta(minutes=1)
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ReservaVeiculo.objects.create(
                    veiculo=self.veiculo, vendedor=self.outro_vendedor,
                    cliente_nome="Outro", cliente_contato="8888",
                    expira_em=timezone.now() + timedelta(hours=24),
                )

    def test_apos_cancelamento_pode_criar_nova_reserva(self):
        reserva = self.reserva()
        ReservaVeiculo.objects.filter(pk=reserva.pk).update(cancelada=True)
        nova = ReservaVeiculo.objects.create(
            veiculo=self.veiculo, vendedor=self.outro_vendedor,
            cliente_nome="Outro", cliente_contato="8888",
            expira_em=timezone.now() + timedelta(hours=24),
        )
        self.assertNotEqual(nova.pk, reserva.pk)
        self.assertEqual(
            ReservaVeiculo.objects.filter(veiculo=self.veiculo, cancelada=False).count(), 1
        )


class ReservaViewsT10(DadosT10, TestCase):
    def setUp(self):
        self.preparar()

    def test_reserva_manual_sem_proposta_e_permitida(self):
        self.client.force_login(self.gerente)
        resposta = self.client.post(reverse("reservar_veiculo", args=[self.veiculo.pk]), {
            "cliente_nome": "Cliente avulso", "cliente_contato": "81999999999",
        })
        self.assertEqual(resposta.status_code, 302)
        reserva = ReservaVeiculo.objects.get(veiculo=self.veiculo, cancelada=False)
        self.assertIsNone(reserva.proposta_origem_id)
        self.assertEqual(reserva.vendedor_id, self.gerente.pk)
        self.assertAlmostEqual(
            (reserva.expira_em - reserva.criada_em).total_seconds(), 86400, delta=10
        )
        self.veiculo.refresh_from_db()
        self.assertEqual(self.veiculo.situacao, Veiculo.Situacao.RESERVADO)
        self.assertEqual(self.veiculo.status, Veiculo.Status.RESERVADO)

    def test_reserva_manual_bloqueada_com_proposta_ativa(self):
        self.proposta()
        self.client.force_login(self.gerente)
        self.client.post(reverse("reservar_veiculo", args=[self.veiculo.pk]), {
            "cliente_nome": "Cliente avulso", "cliente_contato": "81999999999",
        })
        self.assertFalse(ReservaVeiculo.objects.filter(veiculo=self.veiculo).exists())

    def test_reserva_manual_bloqueada_com_fila_aguardando(self):
        self.proposta(situacao=Proposta.Situacao.AGUARDANDO)
        self.client.force_login(self.gerente)
        self.client.post(reverse("reservar_veiculo", args=[self.veiculo.pk]), {
            "cliente_nome": "Cliente avulso", "cliente_contato": "81999999999",
        })
        self.assertFalse(ReservaVeiculo.objects.filter(veiculo=self.veiculo).exists())

    def test_vendedor_nao_pode_criar_reserva_manual(self):
        self.client.force_login(self.vendedor)
        resposta = self.client.post(reverse("reservar_veiculo", args=[self.veiculo.pk]), {
            "cliente_nome": "Cliente", "cliente_contato": "81999999999",
        })
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(ReservaVeiculo.objects.exists())

    def test_cancelamento_manual_exige_motivo(self):
        reserva = self.reserva()
        self.client.force_login(self.gerente)
        self.client.post(reverse("cancelar_reserva", args=[reserva.pk]), {"motivo": ""})
        reserva.refresh_from_db()
        self.assertFalse(reserva.cancelada)

    def test_cancelamento_manual_registra_responsavel_motivo_e_libera(self):
        reserva = self.reserva()
        self.client.force_login(self.gerente)
        resposta = self.client.post(reverse("cancelar_reserva", args=[reserva.pk]), {
            "motivo": "Cliente desistiu da compra"
        })
        self.assertEqual(resposta.status_code, 302)
        reserva.refresh_from_db()
        self.veiculo.refresh_from_db()
        self.assertTrue(reserva.cancelada)
        self.assertEqual(reserva.cancelada_por_id, self.gerente.pk)
        self.assertEqual(reserva.motivo_cancelamento, "Cliente desistiu da compra")
        self.assertIsNotNone(reserva.cancelada_em)
        self.assertEqual(self.veiculo.situacao, Veiculo.Situacao.DISPONIVEL)
        self.assertEqual(self.veiculo.status, Veiculo.Status.DISPONIVEL)
        self.assertTrue(HistoricoSituacaoVeiculo.objects.filter(
            veiculo=self.veiculo, motivo="Cliente desistiu da compra"
        ).exists())

    def test_cancelamento_manual_promove_fila(self):
        reserva = self.reserva()
        primeira = self.proposta()
        segunda = self.proposta(vendedor=self.outro_vendedor)
        self.client.force_login(self.gerente)
        self.client.post(reverse("cancelar_reserva", args=[reserva.pk]), {
            "motivo": "Cliente não poderá comparecer"
        })
        primeira.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual(primeira.situacao, Proposta.Situacao.ATIVA)
        self.assertEqual(segunda.situacao, Proposta.Situacao.AGUARDANDO)

    def test_vendedor_nao_pode_cancelar_reserva(self):
        reserva = self.reserva()
        self.client.force_login(self.vendedor)
        resposta = self.client.post(reverse("cancelar_reserva", args=[reserva.pk]), {
            "motivo": "Tentativa sem permissão"
        })
        self.assertEqual(resposta.status_code, 403)
        reserva.refresh_from_db()
        self.assertFalse(reserva.cancelada)

    def test_confirmacao_de_proposta_ativa_cria_reserva(self):
        proposta = self.proposta()
        aguardando = self.proposta(vendedor=self.outro_vendedor)
        self.client.force_login(self.vendedor)
        resposta = self.client.post(reverse("confirmar_proposta", args=[proposta.pk]), {
            "prazo_horas": 24,  # Compatível também com formulário antigo.
        })
        self.assertEqual(resposta.status_code, 302)
        reserva = ReservaVeiculo.objects.get(proposta_origem=proposta)
        self.assertEqual(reserva.veiculo_id, self.veiculo.pk)
        self.assertEqual(reserva.vendedor_id, self.vendedor.pk)
        aguardando.refresh_from_db()
        self.assertEqual(aguardando.situacao, Proposta.Situacao.AGUARDANDO)

    def test_proposta_na_fila_nao_pode_ser_confirmada(self):
        self.proposta()
        aguardando = self.proposta(vendedor=self.outro_vendedor)
        self.client.force_login(self.outro_vendedor)
        self.client.post(reverse("confirmar_proposta", args=[aguardando.pk]), {
            "prazo_horas": 24,
        })
        self.assertFalse(ReservaVeiculo.objects.filter(proposta_origem=aguardando).exists())

    def test_vendedor_nao_confirma_proposta_de_outro(self):
        proposta = self.proposta()
        self.client.force_login(self.outro_vendedor)
        resposta = self.client.post(reverse("confirmar_proposta", args=[proposta.pk]), {
            "prazo_horas": 24,
        })
        self.assertEqual(resposta.status_code, 404)
        self.assertFalse(ReservaVeiculo.objects.exists())

    def test_confirmacao_nao_gera_duas_reservas(self):
        proposta = self.proposta()
        self.client.force_login(self.vendedor)
        url = reverse("confirmar_proposta", args=[proposta.pk])
        self.client.post(url, {"prazo_horas": 24})
        self.client.post(url, {"prazo_horas": 24})
        self.assertEqual(ReservaVeiculo.objects.filter(veiculo=self.veiculo).count(), 1)


class ConcorrenciaPostgreSQLT10(DadosT10, TransactionTestCase):
    """Concorrência real: duas conexões/transações PostgreSQL distintas."""

    def setUp(self):
        self.preparar()

    def test_duas_reservas_simultaneas_apenas_uma_persiste(self):
        if connection.vendor != "postgresql":
            self.skipTest("Este teste exige PostgreSQL")
        barreira = Barrier(2, timeout=15)
        veiculo_id = self.veiculo.pk
        vendedor_ids = (self.vendedor.pk, self.outro_vendedor.pk)

        def tentar_reservar(vendedor_id):
            close_old_connections()
            try:
                with transaction.atomic():
                    barreira.wait()
                    ReservaVeiculo.objects.create(
                        veiculo_id=veiculo_id,
                        vendedor_id=vendedor_id,
                        cliente_nome="Concorrência", cliente_contato="81999999999",
                        expira_em=timezone.now() + timedelta(hours=24),
                    )
                return "criada"
            except IntegrityError:
                return "conflito"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(tentar_reservar, vendedor_ids))

        self.assertCountEqual(resultados, ["criada", "conflito"])
        self.assertEqual(
            ReservaVeiculo.objects.filter(veiculo_id=veiculo_id, cancelada=False).count(), 1
        )

class IntegracoesRecentesT10(DadosT10, TestCase):
    """Cobertura das funcionalidades citadas depois dos arquivos anexados.

    Se uma rota/comando ainda não estiver no projeto, o teste falha explicitamente
    para indicar o requisito pendente, em vez de fingir que passou.
    """

    def setUp(self):
        self.preparar()

    def test_recusa_gerente_registra_motivo_e_promove_fila(self):
        from django.urls import NoReverseMatch
        try:
            url = reverse("recusar_proposta_fila", args=[1])
        except NoReverseMatch:
            self.fail("Rota 'recusar_proposta_fila' não registrada no urls.py atual.")
        primeira = self.proposta()
        segunda = self.proposta(vendedor=self.outro_vendedor)
        url = reverse("recusar_proposta_fila", args=[primeira.pk])
        self.client.force_login(self.gerente)
        resposta = self.client.post(url, {"motivo": "Negociação recusada pelo gerente"})
        self.assertEqual(resposta.status_code, 302)
        primeira.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual(primeira.situacao, Proposta.Situacao.CANCELADA)
        self.assertEqual(segunda.situacao, Proposta.Situacao.ATIVA)
        self.assertTrue(primeira.decisoes.filter(
            parecer="Negociação recusada pelo gerente", feito_por=self.gerente
        ).exists())

    def test_recusa_sem_motivo_nao_cancela(self):
        from django.urls import NoReverseMatch
        try:
            reverse("recusar_proposta_fila", args=[1])
        except NoReverseMatch:
            self.fail("Rota 'recusar_proposta_fila' não registrada no urls.py atual.")
        proposta = self.proposta()
        self.client.force_login(self.gerente)
        self.client.post(reverse("recusar_proposta_fila", args=[proposta.pk]), {
            "motivo": "",
        })
        proposta.refresh_from_db()
        self.assertEqual(proposta.situacao, Proposta.Situacao.ATIVA)

    def test_comando_expirar_reservas_processa_vencimento(self):
        from django.core.management import call_command, get_commands
        from io import StringIO
        self.assertIn(
            "expirar_reservas", get_commands(),
            "O comando expirar_reservas ainda não está registrado em management/commands.",
        )
        reserva = self.reserva()
        ReservaVeiculo.objects.filter(pk=reserva.pk).update(
            expira_em=timezone.now() - timedelta(minutes=1)
        )
        call_command("expirar_reservas", stdout=StringIO(), stderr=StringIO())
        reserva.refresh_from_db()
        self.veiculo.refresh_from_db()
        self.assertTrue(reserva.cancelada)
        self.assertEqual(self.veiculo.situacao, Veiculo.Situacao.DISPONIVEL)
