from decimal import Decimal
from django.test import SimpleTestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from .models import Veiculo, Proposta
from .alcada_views import LoteForm

class TestAlcadaVeiculo(SimpleTestCase):
    def proposta(self, tipo, limite, valor):
        return Proposta(veiculo=Veiculo(tipo_alcada=tipo, valor_alcada=Decimal(limite)), preco_tabela=Decimal('80000'), valor_oferecido=Decimal(valor))

    def test_percentual_limite_exato(self):
        self.assertFalse(self.proposta('PERCENTUAL','5','76000').fora_da_alcada)
        self.assertTrue(self.proposta('PERCENTUAL','5','75999.99').fora_da_alcada)

    def test_limite_em_reais(self):
        self.assertFalse(self.proposta('VALOR','4000','76000').fora_da_alcada)
        self.assertTrue(self.proposta('VALOR','4000','75999.99').fora_da_alcada)

    def test_alcada_zero(self):
        self.assertFalse(self.proposta('PERCENTUAL','0','80000').fora_da_alcada)
        self.assertTrue(self.proposta('PERCENTUAL','0','79999.99').fora_da_alcada)

    def test_texto_historico(self):
        self.assertEqual(self.proposta('PERCENTUAL','5','76000')._alcada_texto(), '5%')
        self.assertEqual(self.proposta('VALOR','4000','76000')._alcada_texto(), 'R$ 4000')

    def test_lote_validacao(self):
        for tipo, valor in [('PERCENTUAL','101'),('VALOR','-1'),('INVALIDO','5')]:
            self.assertFalse(LoteForm({'tipo':tipo,'valor':valor}).is_valid())
        self.assertTrue(LoteForm({'tipo':'PERCENTUAL','valor':'100'}).is_valid())
