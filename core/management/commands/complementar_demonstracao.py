from datetime import timedelta
from decimal import Decimal as D
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone
from core.models import (Usuario, Veiculo, Cliente, Venda, Proposta, ReservaVeiculo,
    HistoricoSituacaoVeiculo, HistoricoPrecoVeiculo, TelefoneCliente, AvaliacaoTroca,
    ComposicaoPagamento, ContatoCarteira, Oportunidade, Procura, AvisoProcura,
    HistoricoAlcada, FotoVeiculo)

class Command(BaseCommand):
    help = 'Complementa a população comercial de demonstração.'
    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true')

    @transaction.atomic
    def handle(self, *args, **opts):
        if connection.vendor != 'postgresql' or connection.settings_dict['NAME'] != 'revendacerta_demo':
            raise CommandError('Banco não autorizado.')
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(7262501)')
        for model, expected in [(Veiculo,374),(Cliente,180),(Venda,140),(Proposta,320),(ReservaVeiculo,140),(FotoVeiculo,4563),(HistoricoPrecoVeiculo,0),(TelefoneCliente,0),(AvaliacaoTroca,0),(ContatoCarteira,0),(Oportunidade,0),(AvisoProcura,0)]:
            if model.objects.count()!=expected:
                raise CommandError(f'Estado inicial inesperado: {model.__name__}. Não execute duas vezes.')
        now=timezone.now(); hoje=timezone.localdate()
        gerente=Usuario.objects.get(username='jonas',perfil='GERENTE')
        sellers=list(Usuario.objects.filter(perfil='VENDEDOR',ativo=True,is_active=True).order_by('pk'))
        clients=list(Cliente.objects.order_by('pk'))
        livres=list(Veiculo.objects.filter(situacao='DISPONIVEL').exclude(propostas__isnull=False).exclude(reservas__cancelada=False).order_by('pk'))
        if len(livres)<54 or len(sellers)!=7: raise CommandError('Estoque livre ou equipe insuficiente.')
        def create(model, **fields):
            obj=model(**fields); obj.full_clean(); obj.save(); return obj
        def money(x): return x.quantize(D('.01'))
        # Números deliberadamente não discáveis (DDD 00), apenas para demonstração.
        for i,c in enumerate(clients[:100]):
            create(TelefoneCliente,cliente=c,numero=f'0090000{i:04d}',tipo='WHATSAPP',principal=True)
        # Histórico de preços: duas mudanças em 40 unidades, sem alterar propostas existentes.
        for i,v in enumerate(livres[:40]):
            custo=(v.custo_aquisicao or D(0))+(v.lancamentos.filter(tipo='DESPESA',excluido=False).aggregate(s=Sum('valor'))['s'] or D(0))
            for j in range(2):
                anterior=v.preco_venda; novo=money(anterior*(D('1.02') if j==0 else D('.98')))
                h=create(HistoricoPrecoVeiculo,veiculo=v,valor_anterior=anterior,valor_novo=novo,custo_total_no_momento=custo,abaixo_do_custo=novo<custo,alterado_por=gerente)
                HistoricoPrecoVeiculo.objects.filter(pk=h.pk).update(alterado_em=max(v.criado_em,now-timedelta(days=12-8*j)))
                v.preco_venda=novo; v.save(update_fields=['preco_venda'])
        # Consignações novas, sem alterar o custo de veículos já cadastrados.
        for i,ref in enumerate(livres[:15]):
            v=create(Veiculo,placa=f'RDS{i+1000:04d}',chassi=f'9RSDEMA{i+1000000000:010d}',renavam=f'980000{i:05d}',marca=ref.marca,modelo=ref.modelo,tipo=ref.tipo,cambio=ref.cambio,ano_fabricacao=ref.ano_fabricacao,ano_modelo=ref.ano_modelo,cor=ref.cor,combustivel=ref.combustivel,quilometragem=ref.quilometragem+5000,origem='CONSIGNADO',custo_aquisicao=D(0),valor_repasse=money(ref.preco_venda*D('.92')),preco_venda=ref.preco_venda,situacao='DISPONIVEL',criado_por=gerente,tipo_alcada='PERCENTUAL',valor_alcada=D('1'))
            create(HistoricoAlcada,veiculo=v,gerente=gerente,tipo_anterior='PERCENTUAL',valor_anterior=0,tipo_novo='PERCENTUAL',valor_novo=1)
        # Reservas manuais e fila, seguindo a lógica da view e do save da proposta.
        for i,v in enumerate(livres[40:48]):
            c=clients[140+i]; s=sellers[i%7]
            r=create(ReservaVeiculo,veiculo=v,cliente=c,cliente_nome=c.nome,cliente_contato=c.email,vendedor=s,expira_em=now+timedelta(hours=24))
            v.situacao='RESERVADO'; v.status='RESERVADO'; v.save(update_fields=['situacao','status'])
            create(HistoricoSituacaoVeiculo,veiculo=v,situacao_anterior='DISPONIVEL',situacao_nova='RESERVADO',alterado_por=s,motivo='Reserva comercial de demonstração')
            for j in range(2 if i<4 else 1):
                p=Proposta(veiculo=v,cliente=clients[150+i*2+j],vendedor=sellers[(i+j+1)%7],data=hoje,valor_oferecido=v.preco_venda,situacao='AGUARDANDO',reserva_aguardada=r)
                p.full_clean(); p.save(usuario=p.vendedor)
                create(ComposicaoPagamento,proposta=p,tipo='ENTRADA',valor=p.valor_oferecido)
                if p.situacao!='AGUARDANDO': raise CommandError('Fila inconsistente.')
        # Avaliações independentes; não inventar uma venda de troca já fechada.
        for i in range(25):
            ref=livres[i%len(livres)]; ano=min(ref.ano_modelo,2022)
            create(AvaliacaoTroca,placa=f'RDT{i+1000:04d}',chassi=f'9RTDEMA{i+1000000000:010d}',renavam=f'970000{i:05d}',marca=ref.marca,modelo=ref.modelo,ano_fabricacao=min(ref.ano_fabricacao,ano),ano_modelo=ano,cor=ref.cor,combustivel=ref.combustivel,quilometragem=ref.quilometragem+25000,estado_geral='BOM' if i%3 else 'REGULAR',valor_avaliado=money(ref.preco_venda*D('.55')),avaliado_por=gerente,observacoes='Avaliação simulada; revisão de pneus e documentação recomendada.')
        # Contatos apenas de compradores antigos, com o vendedor da venda.
        antigas=list(Venda.objects.filter(data__lte=hoje-timedelta(days=1100),situacao='FECHADA').select_related('cliente','vendedor').order_by('data'))
        if len(antigas)<15: raise CommandError('Compradores antigos insuficientes.')
        for i,venda in enumerate(antigas[:15]):
            resultado=['QUER_VER_OPCOES','NAO_QUER_AGORA','AINDA_COM_CARRO'][i%3]
            contato=create(ContatoCarteira,cliente=venda.cliente,vendedor=venda.vendedor,resultado=resultado,canal='WHATSAPP',realizado_em=now-timedelta(days=2),data_retorno=hoje+timedelta(days=7) if resultado=='NAO_QUER_AGORA' else None,observacao={'QUER_VER_OPCOES':'Solicitou opções de seminovos para recompra.','NAO_QUER_AGORA':'Prefere conversar na próxima semana.','AINDA_COM_CARRO':'Ainda utiliza o veículo e não pretende trocar agora.'}[resultado])
            if resultado=='QUER_VER_OPCOES': create(Oportunidade,contato=contato,cliente=venda.cliente,vendedor=venda.vendedor)
        disponiveis=list(Veiculo.objects.filter(situacao='DISPONIVEL').order_by('pk'))
        for procura in Procura.objects.filter(situacao='ABERTA',valido_ate__gte=hoje).order_by('pk'):
            for v in disponiveis:
                if procura.combina_com(v):
                    AvisoProcura.objects.get_or_create(procura=procura,veiculo=v,defaults={'vendedor':procura.vendedor})
                    break
            if AvisoProcura.objects.count()>=15: break
        for model in (Veiculo,Cliente,Venda,Proposta,ReservaVeiculo,HistoricoPrecoVeiculo,TelefoneCliente,AvaliacaoTroca,ContatoCarteira,Oportunidade,AvisoProcura,FotoVeiculo):
            self.stdout.write(f'{model.__name__}: {model.objects.count()}')
        if not opts['confirmar']:
            transaction.set_rollback(True); self.stdout.write('SIMULAÇÃO: registros revertidos; sequências podem avançar.')
        else: self.stdout.write(self.style.SUCCESS('Complementação concluída.'))
