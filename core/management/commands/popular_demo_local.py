import os
from datetime import date, timedelta
from decimal import Decimal as D
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from core.demo_http_probe import PATTERN, schema_scope
from core.demo_local_runtime import active
from core.models import (Usuario, Veiculo, FotoVeiculo, Cliente, Proposta, ComposicaoPagamento, ReservaVeiculo, Venda, LancamentoFinanceiro, ConfiguracaoCarteira, MetaMensal, MetaIndividual)

class Command(BaseCommand):
    help = 'Popula uma demonstração local com estoque e cenários comerciais fictícios.'
    def add_arguments(self, parser):
        parser.add_argument('schema')
        parser.add_argument('--confirmar', action='store_true')
    def handle(self, *args, **opts):
        name = opts['schema']
        if not settings.DEBUG or os.getenv('DATABASE_URL') or connection.vendor != 'postgresql' or connection.settings_dict['HOST'] not in ('localhost','127.0.0.1','::1','') or not PATTERN.fullmatch(name):
            raise CommandError('Somente demonstração PostgreSQL local.')
        # Read only catalog attributes and existing photo references, never personal data.
        fields = ('marca','modelo','tipo','ano_fabricacao','ano_modelo','cor','combustivel','cambio','quilometragem','preco_venda')
        with schema_scope('public'):
            refs = list(Veiculo.objects.filter(situacao='DISPONIVEL',status='DISPONIVEL',fotos__isnull=False,preco_venda__gt=0).distinct().order_by('pk').prefetch_related('fotos')[:12])
            catalog = [(dict((f,getattr(v,f)) for f in fields), [(p.imagem.name,p.ordem,p.principal) for p in v.fotos.all() if p.imagem.name.startswith('veiculos/')][:3]) for v in refs]
        if len(catalog)<8: raise CommandError('Catálogo com fotos insuficiente.')
        with schema_scope(name), transaction.atomic():
            if not active(): raise CommandError('Demonstração expirada.')
            with connection.cursor() as cursor:
                cursor.execute('SELECT id FROM demo_lifecycle WHERE id=1 FOR UPDATE')
            if Veiculo.objects.exists() or Cliente.objects.exists() or Proposta.objects.exists() or Venda.objects.exists():
                raise CommandError('Demonstração já contém dados comerciais. Nenhum registro alterado.')
            g=Usuario.objects.get(username='gerente',perfil='GERENTE')
            s=Usuario.objects.get(username='vendedor',perfil='VENDEDOR')
            a=Usuario.objects.get(username='administrativo',perfil='ADMINISTRATIVO')
            hoje=timezone.localdate()
            carros=[]
            for i in range(len(catalog)+4):
                attrs, fotos=catalog[i%len(catalog)]
                v=Veiculo(**attrs,placa=f'DMX{i+1000:04d}',chassi=f'9RXDEMA{i+1000000000:010d}',renavam=f'990000{i:05d}',origem='COMPRADO',custo_aquisicao=(attrs['preco_venda']*D('.8')).quantize(D('.01')),situacao='DISPONIVEL',status='DISPONIVEL',criado_por=g,tipo_alcada='PERCENTUAL',valor_alcada=3)
                v.full_clean(); v.save(); carros.append(v)
                LancamentoFinanceiro.objects.create(veiculo=v,tipo='CUSTO_AQUISICAO',valor=v.custo_aquisicao,registrado_por=g)
                if i<len(catalog):
                    for j,(key,ordem,principal) in enumerate(fotos):
                        FotoVeiculo.objects.create(veiculo=v,imagem=key,ordem=j,principal=j==0)
            clientes=[]
            for i in range(8):
                c=Cliente(tipo='PF',nome=f'Cliente fictício {i+1:02d}',cpf=f'000000{i+10000:05d}',data_nascimento=date(1990,1,1),email=f'cliente{i+1}@demo.invalid',cidade='Flores',estado='PE')
                c.full_clean(); c.save(); clientes.append(c)
            for i,v in enumerate(carros[-4:]):
                c=clientes[i]; p=Proposta(veiculo=v,cliente=c,vendedor=s,valor_oferecido=v.preco_venda)
                p.full_clean(); p.save(usuario=s)
                item=ComposicaoPagamento(proposta=p,tipo='ENTRADA',valor=p.valor_oferecido); item.full_clean(); item.save()
                ReservaVeiculo.objects.create(veiculo=v,cliente=c,cliente_nome=c.nome,cliente_contato=c.email,vendedor=s,proposta_origem=p,expira_em=timezone.now()+timedelta(hours=24))
                Veiculo.objects.filter(pk=v.pk).update(situacao='RESERVADO',status='RESERVADO')
                if i<2:
                    venda=Venda.fechar(v.pk,p.pk,c.pk,s)
                    if i==0:
                        for etapa in venda.etapas_documentacao.all(): etapa.atualizar(a,'CONCLUIDA',hoje)
                        from core.models import EntregaVeiculo
                        venda.registrar_entrega(a,data_entrega=hoje,checklist={k:True for k,_ in EntregaVeiculo.ITENS_CHECKLIST})
            ConfiguracaoCarteira.objects.update_or_create(pk=1,defaults={'anos_sem_comprar':3,'atualizado_por':g})
            meta,_=MetaMensal.objects.get_or_create(mes=hoje.replace(day=1),defaults={'loja':5,'padrao_vendedor':5})
            MetaIndividual.objects.get_or_create(mensal=meta,vendedor=s,defaults={'quantidade':5})
            for model in (Veiculo,FotoVeiculo,Cliente,Proposta,ReservaVeiculo,Venda): self.stdout.write(f'{model.__name__}: {model.objects.count()}')
            if not opts['confirmar']:
                transaction.set_rollback(True); self.stdout.write('SIMULAÇÃO: dados revertidos.')
            else: self.stdout.write(self.style.SUCCESS('Demonstração populada.'))
