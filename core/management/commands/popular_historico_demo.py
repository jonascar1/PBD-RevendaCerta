from datetime import date, datetime, time, timedelta
from decimal import Decimal as D
from django.core.management.base import BaseCommand, CommandError
from django.core.files.storage import storages
from django.db import connection, transaction
from django.utils import timezone
from core.demo_schema import PATTERN, schema_scope
from core.demo_lifecycle import lifecycle_lock
from core.demo_lifecycle import active
from core.models import (Usuario, Veiculo, FotoVeiculo, Cliente, Proposta, ComposicaoPagamento,
    ReservaVeiculo, Venda, LancamentoFinanceiro, EntregaVeiculo, MetaMensal, MetaIndividual,
    ConfiguracaoCarteira, HistoricoProposta, HistoricoSituacaoVeiculo, Procura)

class Command(BaseCommand):
    help = 'Complementa histórico fictício sem reduzir estoque; simulação por padrão.'
    def add_arguments(self, parser):
        parser.add_argument('schema')
        parser.add_argument('--confirmar', action='store_true')

    def handle(self, *args, **opts):
        schema = opts['schema']
        if not PATTERN.fullmatch(schema):
            raise CommandError('Schema demonstrativo obrigatório.')
        fields = ('marca','modelo','tipo','ano_fabricacao','ano_modelo','cor','combustivel','cambio','quilometragem','preco_venda')
        with lifecycle_lock():
            with schema_scope('public'):
                refs = Veiculo.objects.filter(situacao__in=['VENDIDO','ENTREGUE'], preco_venda__gt=0, fotos__isnull=False).distinct().order_by('pk').prefetch_related('fotos')
                catalog = [(v.pk, {f:getattr(v,f) for f in fields}, [p.imagem.name for p in v.fotos.all() if p.imagem.name.startswith('veiculos/')]) for v in refs]
            backend = storages['media_original']
            if hasattr(backend,'bucket'):
                keys = {o.key for o in backend.bucket.objects.filter(Prefix='veiculos/') if o.size > 0}
                catalog = [(pk,attrs,[k for k in photos if k in keys]) for pk,attrs,photos in catalog]
            else:
                catalog = [(pk,attrs,[k for k in photos if backend.exists(k)]) for pk,attrs,photos in catalog]
            with schema_scope(schema), transaction.atomic():
                if not active(): raise CommandError('Demonstração expirada.')
                with connection.cursor() as cursor:
                    cursor.execute('SELECT id FROM demo_lifecycle WHERE id=1 FOR UPDATE')
                if Veiculo.objects.filter(placa__startswith='DHX').exists() or Cliente.objects.filter(email__endswith='@historico.demo.invalid').exists():
                    raise CommandError('Histórico já aplicado; nenhuma alteração.')
                g = Usuario.objects.get(username='gerente',perfil='GERENTE')
                s = Usuario.objects.get(username='vendedor',perfil='VENDEDOR')
                a = Usuario.objects.get(username='administrativo',perfil='ADMINISTRATIVO')
                hoje = timezone.localdate()
                estoque = Veiculo.objects.filter(situacao='DISPONIVEL',status='DISPONIVEL',fotos__isnull=False).distinct()
                before = estoque.count()
                used = set(FotoVeiculo.objects.values_list('imagem',flat=True))
                selected=[]
                # Prioriza modelos antigos para a carteira, sem reutilizar fotos de estoque.
                for pk,attrs,photos in sorted(catalog,key=lambda x:(x[1]['ano_modelo'],x[0])):
                    photos=list(dict.fromkeys(photos))
                    if not photos or used.intersection(photos): continue
                    selected.append((pk,attrs,photos)); used.update(photos)
                if len(selected)<38: raise CommandError(f'Apenas {len(selected)} veículos históricos com fotos; necessário 38.')
                old=[x for x in selected if x[1]['ano_modelo'] <= hoje.year-4]
                ancient=old[:8]
                rest=[x for x in selected if x not in ancient][:38-len(ancient)]
                clients=[]
                for i in range(52):
                    c=Cliente(tipo='PF',nome=f'Cliente histórico fictício {i+1:02d}',cpf=f'000001{i+20000:05d}',data_nascimento=date(1985,1,1),email=f'cliente{i+1}@historico.demo.invalid',cidade='Flores',estado='PE')
                    c.full_clean(); c.save(); clients.append(c)
                def stamp(d): return timezone.make_aware(datetime.combine(d,time(12)))
                def proposal(v,c,d):
                    p=Proposta(veiculo=v,cliente=c,vendedor=s,data=d,valor_oferecido=v.preco_venda)
                    p.full_clean(); p.save(usuario=s)
                    item=ComposicaoPagamento(proposta=p,tipo='ENTRADA',valor=p.valor_oferecido); item.full_clean(); item.save()
                    HistoricoProposta.objects.filter(proposta=p).update(alterado_em=stamp(d))
                    return p
                for i,(pk,attrs,photos) in enumerate(ancient+rest):
                    if pk>9999: raise CommandError('Identificador fora do intervalo.')
                    d=hoje-timedelta(days=1460+i*5) if i<len(ancient) else hoje-timedelta(days=((i-len(ancient))*11)%330)
                    d=max(d,date(attrs['ano_modelo'],1,1)) if attrs['ano_modelo']<=hoje.year else hoje
                    v=Veiculo(**attrs,placa=f'DHX{pk:04d}',chassi=f'9RXDEMH{pk:010d}',renavam=f'97{pk:09d}',origem='COMPRADO',custo_aquisicao=(attrs['preco_venda']*D('.78')).quantize(D('.01')),situacao='DISPONIVEL',status='DISPONIVEL',criado_por=g,tipo_alcada='PERCENTUAL',valor_alcada=3)
                    v.full_clean(); v.save()
                    acquired=d-timedelta(days=15)
                    Veiculo.objects.filter(pk=v.pk).update(criado_em=stamp(acquired))
                    FotoVeiculo.objects.bulk_create([FotoVeiculo(veiculo=v,imagem=k,ordem=j,principal=j==0) for j,k in enumerate(photos[:5])])
                    for tipo,valor,desc,cat in [('CUSTO_AQUISICAO',v.custo_aquisicao,'Aquisição fictícia',None),('DESPESA',D(150+i*17),'Preparação fictícia','MANUTENCAO')]:
                        l=LancamentoFinanceiro.objects.create(veiculo=v,tipo=tipo,valor=valor,descricao=desc,categoria_despesa=cat,registrado_por=a,data_lancamento=acquired)
                        LancamentoFinanceiro.objects.filter(pk=l.pk).update(criado_em=stamp(acquired))
                    c=clients[i]; p=proposal(v,c,d)
                    r=ReservaVeiculo.objects.create(veiculo=v,cliente=c,cliente_nome=c.nome,cliente_contato=c.email,vendedor=s,proposta_origem=p,expira_em=timezone.now()+timedelta(hours=24))
                    Veiculo.objects.filter(pk=v.pk).update(situacao='RESERVADO',status='RESERVADO')
                    sale=Venda.fechar(v.pk,p.pk,c.pk,s)
                    Venda.objects.filter(pk=sale.pk).update(data=d,criada_em=stamp(d))
                    sale.pagamentos.update(data_pagamento=d)
                    ReservaVeiculo.objects.filter(pk=r.pk).update(criada_em=stamp(d),expira_em=stamp(d)+timedelta(hours=24),cancelada_em=stamp(d))
                    sale.lancamentos_financeiros.update(data_lancamento=d,criado_em=stamp(d))
                    sale.etapas_documentacao.update(data=d,criada_em=stamp(d),atualizada_em=stamp(d))
                    if i<30:
                        delivery=min(hoje,d+timedelta(days=3))
                        for etapa in sale.etapas_documentacao.all(): etapa.atualizar(a,'CONCLUIDA',delivery)
                        entrega=sale.registrar_entrega(a,data_entrega=delivery,checklist={k:True for k,_ in EntregaVeiculo.ITENS_CHECKLIST})
                        EntregaVeiculo.objects.filter(pk=entrega.pk).update(criada_em=stamp(delivery))
                        sale.etapas_documentacao.update(atualizada_em=stamp(delivery))
                    HistoricoSituacaoVeiculo.objects.filter(veiculo=v).exclude(situacao_nova='ENTREGUE').update(alterado_em=stamp(d))
                    HistoricoSituacaoVeiculo.objects.filter(veiculo=v,situacao_nova='ENTREGUE').update(alterado_em=stamp(min(hoje,d+timedelta(days=3))))
                # Propostas abertas sem reservar ou retirar veículos da vitrine.
                livres=list(estoque.filter(propostas__isnull=True).order_by('pk')[:48])
                for i,v in enumerate(livres): proposal(v,clients[38+i%14],hoje-timedelta(days=i%15))
                for i in range(6):
                    p=Procura(cliente=clients[38+i],vendedor=s,marca_modelo=f'Modelo desejado fictício {i+1}',valido_ate=hoje+timedelta(days=30))
                    p.full_clean(); p.save()
                ConfiguracaoCarteira.objects.update_or_create(pk=1,defaults={'anos_sem_comprar':3,'atualizado_por':g})
                for i in range(12):
                    month=(hoje.replace(day=1)-timedelta(days=i*30)).replace(day=1)
                    meta,_=MetaMensal.objects.get_or_create(mes=month,defaults={'loja':5,'padrao_vendedor':5})
                    MetaIndividual.objects.get_or_create(mensal=meta,vendedor=s,defaults={'quantidade':5})
                if estoque.count()!=before: raise CommandError('Estoque disponível mudou; operação revertida.')
                for model in (Veiculo,Cliente,Venda,Proposta,EntregaVeiculo,LancamentoFinanceiro,Procura): self.stdout.write(f'{model.__name__}: {model.objects.count()}')
                self.stdout.write(f'Disponíveis com fotos: {before}; vendas antigas novas: {len(ancient)}')
                if not opts['confirmar']:
                    transaction.set_rollback(True); self.stdout.write('SIMULAÇÃO: registros revertidos; sequências podem avançar.')
                else: self.stdout.write(self.style.SUCCESS('Histórico demonstrativo criado.'))
