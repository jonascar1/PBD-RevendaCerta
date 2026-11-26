from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from core.carteira import data_limite_carteira
from core.models import (Usuario, PerfilVendedor, Veiculo, Cliente, Proposta,
    ComposicaoPagamento, DecisaoProposta, ReservaVeiculo, Venda, Procura,
    LancamentoFinanceiro, HistoricoSituacaoVeiculo, ConfiguracaoCarteira)

CATALOGO = [('Mazda','CX-30','SUV'), ('Mazda','MX-5','OUTRO'),
 ('Lexus','UX 250h','SUV'), ('Lexus','ES 300h','SEDA'),
 ('Acura','Integra','SEDA'), ('Genesis','G70','SEDA'),
 ('Genesis','GV70','SUV'), ('Infiniti','Q50','SEDA'),
 ('Infiniti','QX50','SUV'), ('Dacia','Jogger','UTILITARIO'),
 ('Skoda','Octavia','SEDA'), ('Skoda','Karoq','SUV'),
 ('Seat','Leon','HATCH'), ('Cupra','Formentor','SUV'),
 ('Opel','Mokka','SUV'), ('Opel','Insignia','SEDA')]

class Command(BaseCommand):
    help = 'Cria cenários fictícios de revisão, exclusivamente no banco revendacerta_demo.'

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true')
        parser.add_argument('--vendedor')
        parser.add_argument('--outro-vendedor')

    @transaction.atomic
    def handle(self, *args, **opts):
        if connection.vendor != 'postgresql' or connection.settings_dict['NAME'] != 'revendacerta_demo':
            raise CommandError('Use exclusivamente o PostgreSQL revendacerta_demo.')
        with connection.cursor() as c:
            c.execute('SELECT current_database()')
            if c.fetchone()[0] != 'revendacerta_demo':
                raise CommandError('Banco incorreto.')
            c.execute('SELECT pg_advisory_xact_lock(7262501)')
        if not opts['confirmar']:
            raise CommandError('Faça backup e execute novamente com --confirmar.')
        if Cliente.objects.filter(email__endswith='@rc-cenarios.invalid').exists():
            raise CommandError('Cenários já existentes. Não serão duplicados. Use o roteiro original.')
        usuarios = Usuario.objects.filter(ativo=True, is_active=True)
        gerente = usuarios.filter(perfil='GERENTE').first()
        vendedores = usuarios.filter(perfil='VENDEDOR', dados_vendedor__isnull=False).order_by('pk')
        v1 = vendedores.filter(username=opts['vendedor']).first() if opts['vendedor'] else vendedores.first()
        v2 = (vendedores.exclude(pk=v1.pk).filter(username=opts['outro_vendedor']).first() if opts['outro_vendedor'] else vendedores.exclude(pk=v1.pk).first()) if v1 else None
        if not all((gerente,v1,v2)):
            raise CommandError('São necessários um gerente e dois vendedores ativos com perfil comercial.')
        candidatos = [(m,n,t) for m,n,t in CATALOGO if not Veiculo.objects.filter(marca__iexact=m,modelo__iexact=n).exists()]
        if len(candidatos)<8:
            raise CommandError('Menos de oito modelos inéditos disponíveis; nenhuma alteração realizada.')
        hoje = timezone.localdate()
        cfg = ConfiguracaoCarteira.objects.filter(pk=1).first()
        antiga = data_limite_carteira(hoje, cfg.anos_sem_comprar if cfg else 3)-timedelta(days=30)
        def cliente(i,nome):
            obj = Cliente(tipo='PF', nome='DEMO RC '+nome, cpf=f'0000008{i:04d}', data_nascimento=date(1985,1,1), email=f'cenario{i}@rc-cenarios.invalid')
            obj.full_clean(); obj.save(); return obj
        def carro(i, preparacao=False):
            marca,modelo,tipo=candidatos[i-1]
            placa=f'RCD{8000+i:04d}'; chassi=f'9RCDEMA{8000000000+i:010d}'
            if Veiculo.objects.filter(placa=placa).exists() or Veiculo.objects.filter(chassi=chassi).exists():
                raise CommandError('Identificador DEMO já utilizado.')
            obj=Veiculo(placa=placa,chassi=chassi,renavam=f'8800000{i:04d}',marca=marca,modelo=modelo,tipo=tipo,ano_fabricacao=min(2020,antiga.year) if i in (1,2) else 2020,ano_modelo=min(2021,antiga.year) if i in (1,2) else 2021,cor='Prata',combustivel='Gasolina',cambio='AUTOMATICO',quilometragem=45000,origem='COMPRADO',custo_aquisicao=Decimal('60000'),preco_venda=Decimal('80000'),situacao='PREPARACAO' if preparacao else 'DISPONIVEL',criado_por=gerente)
            obj.full_clean(); obj.save()
            LancamentoFinanceiro.objects.create(veiculo=obj,tipo='CUSTO_AQUISICAO',valor=60000,registrado_por=gerente,descricao='DEMO RC aquisição')
            return obj
        def proposta(c,car,v,valor=80000):
            p=Proposta(cliente=c,veiculo=car,vendedor=v,valor_oferecido=Decimal(valor)); p.save(usuario=v); p.full_clean()
            item=ComposicaoPagamento(proposta=p,tipo='ENTRADA',valor=Decimal(valor)); item.full_clean(); item.save(); return p
        def reservar(p):
            car=p.veiculo
            ReservaVeiculo.objects.create(veiculo=car,cliente=p.cliente,cliente_nome=p.cliente.nome,cliente_contato='DEMO — não ligar',vendedor=p.vendedor,proposta_origem=p,expira_em=timezone.now()+timedelta(hours=24))
            car.situacao='RESERVADO'; car.status='RESERVADO'; car.save(update_fields=['situacao','status'])
            HistoricoSituacaoVeiculo.objects.create(veiculo=car,situacao_anterior='DISPONIVEL',situacao_nova='RESERVADO',alterado_por=p.vendedor,motivo='DEMO RC reserva')
        def vender(p,data):
            reservar(p); venda=Venda.fechar(p.veiculo_id,p.pk,p.cliente_id,p.vendedor)
            Venda.objects.filter(pk=venda.pk).update(data=data)
            venda.pagamentos.filter(tipo='ENTRADA').update(data_pagamento=data)
            venda.lancamentos_financeiros.update(data_lancamento=data)
            return venda
        compartilhado=cliente(1,'Carteira Compartilhada')
        vender(proposta(compartilhado,carro(1),v1),antiga-timedelta(days=30))
        vender(proposta(compartilhado,carro(2),v2),antiga)
        atual=cliente(2,'Venda Atual'); venda=vender(proposta(atual,carro(3),v1),hoje)
        p=proposta(cliente(3,'Contraproposta'),carro(4),v1,70000)
        p.decidir(gerente,DecisaoProposta.Tipo.CONTRAPROPOSTA,parecer='DEMO RC negociação',novo_valor=75000)
        car=carro(5,True); interessado=cliente(4,'Procura')
        procura=Procura(cliente=interessado,vendedor=v1,marca_modelo=f'{car.marca} {car.modelo}',valido_ate=hoje+timedelta(days=30)); procura.full_clean(); procura.save()
        desp=carro(6,True)
        LancamentoFinanceiro.objects.create(veiculo=desp,tipo='DESPESA',categoria_despesa='MANUTENCAO',valor=350,descricao='DEMO RC revisão',registrado_por=gerente)
        reservado=proposta(cliente(5,'Reserva'),carro(7),v1); reservar(reservado)
        fila=proposta(cliente(6,'Fila'),reservado.veiculo,v2)
        livre=carro(8)
        for texto in [f'Gerente: {gerente.username}',f'Vendedor 1: {v1.username}',f'Vendedor 2: {v2.username}',f'Carteira: cliente #{compartilhado.pk}',f'Venda atual: #{venda.pk}',f'Contraproposta: #{p.pk}',f'Procura: #{procura.pk}; liberar {car}',f'Despesas: {desp}',f'Reserva: #{reservado.pk}; fila #{fila.pk}',f'Estoque livre: {livre}']:
            self.stdout.write(texto)
        self.stdout.write(self.style.SUCCESS('Cenários criados. Não use contatos fictícios para comunicação real.'))
