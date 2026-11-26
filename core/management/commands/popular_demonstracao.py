from datetime import date, datetime, time, timedelta
from decimal import Decimal as D
import random
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from core.models import (Usuario, Veiculo, Cliente, Proposta, ComposicaoPagamento, DecisaoProposta, ReservaVeiculo, Venda, Procura, LancamentoFinanceiro, HistoricoSituacaoVeiculo, HistoricoAlcada, MetaMensal, MetaIndividual, HistoricoMeta, FotoVeiculo, EntregaVeiculo)

class Command(BaseCommand):
    help = 'Popula exclusivamente o banco de demonstração com dados fictícios.'
    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true')
    @transaction.atomic
    def handle(self, *args, **opts):
        if connection.vendor != 'postgresql' or connection.settings_dict['NAME'] != 'revendacerta_demo':
            raise CommandError('Banco não autorizado.')
        with connection.cursor() as c:
            c.execute('SELECT pg_advisory_xact_lock(7262501)')
        if any(m.objects.exists() for m in (Cliente, Proposta, Venda, ReservaVeiculo, Procura, MetaMensal)) or Veiculo.objects.count()!=244 or HistoricoAlcada.objects.count()!=244 or LancamentoFinanceiro.objects.count()!=244:
            raise CommandError('Estado inicial inesperado; não execute duas vezes.')
        hoje=date(2026,11,25)
        if timezone.localdate()<hoje: raise CommandError('Data do sistema anterior ao período simulado.')
        rng=random.Random(20261125)
        gerente=Usuario.objects.get(username='jonas',ativo=True,is_active=True)
        vendedores=[Usuario.objects.get(username=n,ativo=True,is_active=True) for n in ('monik','joao','berg','valter','ana','rayane','alberto')]
        admins=list(Usuario.objects.filter(perfil='ADMINISTRATIVO',ativo=True,is_active=True))
        if not admins: raise CommandError('Sem administrativos ativos.')
        def dt(d,h=10): return timezone.make_aware(datetime.combine(d,time(h)))
        def money(v): return D(v).quantize(D('.01'))
        def stamp(obj, **kw): type(obj).objects.filter(pk=obj.pk).update(**kw)
        orig=list(Veiculo.objects.order_by('pk')); rng.shuffle(orig)
        carros=[]
        for i in range(130):
            ref=orig[i%len(orig)]
            ano=min(ref.ano_modelo,2020) if i<20 else min(ref.ano_modelo,2025)
            preco=money(ref.preco_venda*(D('.75') if i<20 else D('1')))
            custo=money(preco*D(rng.randint(77,94))/100)
            v=Veiculo(placa=f'RDX{i+1000:04d}',chassi=f'9RXDEMA{i+1000000000:010d}',renavam=f'990000{i:05d}',marca=ref.marca,modelo=ref.modelo,tipo=ref.tipo,ano_fabricacao=min(ref.ano_fabricacao,ano),ano_modelo=ano,cor=ref.cor,combustivel=ref.combustivel,cambio=ref.cambio,quilometragem=max(10000,ref.quilometragem),origem='COMPRADO',custo_aquisicao=custo,preco_venda=preco,situacao='DISPONIVEL',criado_por=gerente,tipo_alcada='PERCENTUAL',valor_alcada=D('2'))
            v.full_clean(); v.save(); carros.append(v)
            LancamentoFinanceiro.objects.create(veiculo=v,tipo='CUSTO_AQUISICAO',valor=custo,registrado_por=gerente,descricao='Aquisição de estoque')
            HistoricoAlcada.objects.create(veiculo=v,gerente=gerente,tipo_anterior='PERCENTUAL',valor_anterior=0,tipo_novo='PERCENTUAL',valor_novo=2)
        nomes=['Mariana','Rafael','Camila','Bruno','Juliana','Felipe','Patricia','Lucas','Renata','André','Beatriz','Eduardo','Carolina','Mateus','Fernanda','Diego','Larissa','Paulo']
        sobrenomes=['Almeida','Barros','Cardoso','Duarte','Ferreira','Gomes','Lima','Mendes','Nunes','Ribeiro']
        clientes=[]
        for i in range(180):
            c=Cliente(tipo='PF',nome=f'{nomes[i%18]} {sobrenomes[i//18]}',cpf=f'000000{i+10000:05d}',data_nascimento=date(rng.randint(1960,2000),rng.randint(1,12),rng.randint(1,28)),email=f'cliente{i+1}@revenda-demo.invalid',cidade=rng.choice(['Flores','Serra Talhada','Salgueiro','Arcoverde','Afogados da Ingazeira']),estado='PE')
            c.full_clean(); c.save(); stamp(c,criado_em=dt(date(2021,1,1) if i<20 else date(2025,11,25)),atualizado_em=dt(hoje)); clientes.append(c)
        datas=[date(2022,1,1)+timedelta(days=i*25) for i in range(20)]
        meses=[(2025,12,12,12),(2026,1,7,10),(2026,2,8,10),(2026,3,10,10),(2026,4,9,11),(2026,5,11,10),(2026,6,8,11),(2026,7,12,11),(2026,8,10,10),(2026,9,9,12),(2026,10,13,12),(2026,11,11,14)]
        for y,m,n,meta in meses:
            datas.extend(date(y,m,2+j*2) for j in range(n))
            mm=MetaMensal.objects.create(mes=date(y,m,1),loja=meta,padrao_vendedor=2)
            for j,v in enumerate(vendedores): MetaIndividual.objects.create(mensal=mm,vendedor=v,quantidade=meta//7+(j<meta%7))
            h=HistoricoMeta.objects.create(mensal=mm,gerente=gerente,anterior={},novo={'loja':meta,'padrao_vendedor':2}); stamp(h,criado_em=dt(date(y,m,1)))
        vendidos=carros[:20]+[v for v in orig if v.ano_modelo<=2025][:120]
        if len(vendidos)!=140: raise CommandError('Estoque elegível insuficiente.')
        restantes=[v for v in orig+carros if v.pk not in {x.pk for x in vendidos}]
        def preparar(v,d):
            stamp(v,criado_em=dt(d)); v.lancamentos.filter(tipo='CUSTO_AQUISICAO').update(data_lancamento=d,criado_em=dt(d)); HistoricoAlcada.objects.filter(veiculo=v).update(criado_em=dt(d,11))
        def despesa(v,d):
            cat,desc=rng.choice([('MANUTENCAO','Revisão preventiva e filtros'),('LIMPEZA','Higienização interna e externa'),('DOCUMENTACAO','Vistoria e regularização'),('MANUTENCAO','Alinhamento e balanceamento')]); l=LancamentoFinanceiro.objects.create(veiculo=v,tipo='DESPESA',categoria_despesa=cat,descricao=desc,valor=D(rng.randint(8,120)*10),registrado_por=rng.choice(admins),data_lancamento=d); stamp(l,criado_em=dt(d))
        def proposta(v,c,s,d,desconto):
            p=Proposta(veiculo=v,cliente=c,vendedor=s,data=d,valor_oferecido=money(v.preco_venda*(1-desconto))); p.full_clean(); p.save(usuario=s)
            valor=p.valor_oferecido
            if rng.random()<.65:
                entrada=money(valor*D(rng.randint(25,65))/100); saldo=valor-entrada; n=rng.choice([24,36,48,60]); taxa=D('.017'); parcela=money(saldo*taxa/(1-(1+taxa)**(-n)))
                itens=[dict(tipo='ENTRADA',valor=entrada),dict(tipo='FINANCIAMENTO',valor=saldo,financ_banco=rng.choice(['Banco do Brasil','Santander','BV','Itaú']),financ_parcelas=n,financ_valor_parcela=parcela)]
            else: itens=[dict(tipo='ENTRADA',valor=valor)]
            for item in itens:
                x=ComposicaoPagamento(proposta=p,**item); x.full_clean(); x.save()
            stamp(p,criada_em=dt(d),atualizada_em=dt(d)); p.historico.update(alterado_em=dt(d)); p.decisoes.update(feito_em=dt(d)); return p
        equipe=[v for v,n in zip(vendedores,[24,21,19,17,16,13,10]) for _ in range(n)]; rng.shuffle(equipe)
        for i,(v,d) in enumerate(zip(vendidos,datas)):
            preparar(v,d-timedelta(days=45)); despesa(v,d-timedelta(days=7)); despesa(v,d-timedelta(days=3))
            s=vendedores[i%7] if i<20 else equipe[i-20]; c=clientes[i]
            p=proposta(v,c,s,d-timedelta(days=1),D(rng.randint(0,7))/100)
            if p.status_aprovacao=='PENDENTE':
                dec=p.decidir(gerente,DecisaoProposta.Tipo.APROVACAO,parecer='Condição comercial aprovada'); stamp(dec,feito_em=dt(d-timedelta(days=1),14))
            r=ReservaVeiculo.objects.create(veiculo=v,cliente=c,cliente_nome=c.nome,cliente_contato=c.email,vendedor=s,proposta_origem=p,expira_em=timezone.now()+timedelta(hours=24))
            Veiculo.objects.filter(pk=v.pk).update(situacao='RESERVADO',status='RESERVADO')
            h=HistoricoSituacaoVeiculo.objects.create(veiculo=v,situacao_anterior='DISPONIVEL',situacao_nova='RESERVADO',alterado_por=s,motivo='Reserva comercial'); stamp(h,alterado_em=dt(d-timedelta(days=1),15))
            venda=Venda.fechar(v.pk,p.pk,c.pk,s); stamp(venda,data=d,criada_em=dt(d)); venda.refresh_from_db()
            stamp(r,criada_em=dt(d-timedelta(days=1),15),expira_em=dt(d,15),cancelada_em=dt(d)); venda.pagamentos.filter(tipo='ENTRADA').update(data_pagamento=d); venda.lancamentos_financeiros.update(data_lancamento=d,criado_em=dt(d)); v.historico_situacoes.filter(situacao_nova='VENDIDO').update(alterado_em=dt(d)); stamp(p,atualizada_em=dt(d))
            if not v.lancamentos.filter(tipo='VENDA').exists():
                l=LancamentoFinanceiro.objects.create(veiculo=v,venda=venda,tipo='VENDA',valor=venda.valor_venda,registrado_por=s,data_lancamento=d,descricao='Receita da venda'); stamp(l,criado_em=dt(d))
            entrega=d+timedelta(days=rng.randint(2,7)); admin=rng.choice(admins)
            for j,e in enumerate(venda.etapas_documentacao.all()):
                ed=min(hoje,d+timedelta(days=1)); situacao='CONCLUIDA' if entrega<=hoje else ('EM_ANDAMENTO' if j==0 else 'PENDENTE'); e.atualizar(admin,situacao,ed); stamp(e,criada_em=dt(d),atualizada_em=dt(ed))
            if entrega<=hoje:
                en=venda.registrar_entrega(admin,data_entrega=entrega,checklist={k:True for k,_ in EntregaVeiculo.ITENS_CHECKLIST}); stamp(en,criada_em=dt(entrega)); v.historico_situacoes.filter(situacao_nova='ENTREGUE').update(alterado_em=dt(entrega))
            if venda.soma_pagamentos!=venda.valor_venda: raise CommandError('Pagamento divergente.')
        for i,v in enumerate(restantes):
            d=max(date(2025,11,25),hoje-timedelta(days=rng.randint(30,250))); preparar(v,d)
            if i<70: despesa(v,d+timedelta(days=2))
        for i,v in enumerate(restantes[:180]):
            d=hoje-timedelta(days=rng.randint(1,20)); c=clientes[140+i%40]; s=rng.choice(vendedores); p=proposta(v,c,s,d,D(rng.randint(0,9))/100)
            if i<100:
                if p.status_aprovacao=='PENDENTE' and i%2==0:
                    dec=p.decidir(gerente,DecisaoProposta.Tipo.RECUSA,parecer='Valor abaixo da condição comercial'); stamp(dec,feito_em=dt(d,14))
                else: p.cancelar()
            elif p.status_aprovacao=='PENDENTE' and i%3==0:
                dec=p.decidir(gerente,DecisaoProposta.Tipo.CONTRAPROPOSTA,parecer='Ajuste de desconto',novo_valor=money((p.valor_oferecido+v.preco_venda)/2)); stamp(dec,feito_em=dt(d,14))
            stamp(p,atualizada_em=dt(d,15))
        for i in range(60):
            c=clientes[120+i]; s=rng.choice(vendedores); v=rng.choice(restantes); p=Procura(cliente=c,vendedor=s,tipo=v.tipo,marca_modelo=f'{v.marca} {v.modelo}',valido_ate=hoje+timedelta(days=30)); p.full_clean(); p.save(); stamp(p,criada_em=dt(hoje-timedelta(days=10)))
            if i<20: stamp(p,situacao='VENCIDA',valido_ate=hoje-timedelta(days=1),encerrada_em=dt(hoje-timedelta(days=1)))
        for m,n in [(Veiculo,374),(Cliente,180),(Venda,140),(Proposta,320),(ReservaVeiculo,140),(Procura,60),(MetaMensal,12),(MetaIndividual,84),(FotoVeiculo,4563)]:
            total=m.objects.count(); self.stdout.write(f'{m.__name__}: {total}');
            if total!=n: raise CommandError(f'Quantidade inesperada: {m.__name__}')
        if not opts['confirmar']:
            transaction.set_rollback(True); self.stdout.write('SIMULAÇÃO: registros revertidos; sequências PostgreSQL podem avançar.')
        else: self.stdout.write(self.style.SUCCESS('População concluída.'))
