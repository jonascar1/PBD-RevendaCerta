from django.urls import path

from . import views

urlpatterns = [
    # Autenticação e Painel Geral
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("painel/", views.painel_view, name="painel"),

    # Vitrine Pública
    path("", views.vitrine_view, name="vitrine"),
    path("vitrine/veiculo/<int:pk>/", views.vitrine_veiculo_detalhe_view, name="vitrine_veiculo_detalhe"),

    # =========================================================================
    # Painel do Vendedor
    # =========================================================================
    path("painel/vendedor/inicio/", views.painel_vendedor_view, name="painel_vendedor"),
    
    # Veículos (Vendedor)
    path("painel/vendedor/veiculos/<int:veiculo_id>/", views.detalhes_veiculo_vendedor_view, name="detalhes_veiculo_vendedor"),
    path("painel/vendedor/propostas/<int:proposta_id>/fechar-venda/", views.fechar_venda_view, name="fechar_venda"),
    # Clientes
    path("painel/vendedor/clientes/", views.clientes_view, name="clientes"),
    path("painel/vendedor/clientes/cadastrar/", views.cadastrar_cliente_view, name="cadastrar_cliente"),
    path("painel/vendedor/clientes/<int:cliente_id>/", views.detalhes_cliente_view, name="detalhes_cliente"),
    path("painel/vendedor/clientes/<int:cliente_id>/editar/", views.editar_cliente_view, name="editar_cliente"),
    path("painel/vendedor/clientes/<int:cliente_id>/desativar/", views.desativar_cliente_view, name="desativar_cliente"),
    path("painel/vendedor/clientes/<int:cliente_id>/reativar/", views.reativar_cliente_view, name="reativar_cliente"),
    
    # Propostas
    path("painel/vendedor/propostas/", views.propostas_view, name="propostas"),
    path("painel/vendedor/propostas/nova/", views.nova_proposta_view, name="nova_proposta"),
    path("painel/vendedor/propostas/<int:proposta_id>/", views.detalhes_proposta_view, name="detalhes_proposta"),
    path("painel/vendedor/propostas/<int:proposta_id>/editar/", views.editar_proposta_view, name="editar_proposta"),
    path("painel/vendedor/propostas/<int:proposta_id>/confirmar/", views.confirmar_proposta_view, name="confirmar_proposta"),
    path("painel/vendedor/propostas/<int:proposta_id>/aceitar-contraproposta/", views.aceitar_contraproposta_view, name="aceitar_contraproposta"),
    path("painel/vendedor/propostas/<int:proposta_id>/recusar-contraproposta/", views.recusar_contraproposta_view, name="recusar_contraproposta"),

    # =========================================================================
    # Painel Administrativo
    # =========================================================================
    path("painel/administrativo/inicio/", views.painel_administrativo_view, name="painel_administrativo"),
    
    # Despesas
    path("painel/administrativo/despesas/", views.despesas_view, name="despesas"),
    path("painel/administrativo/despesas/<int:veiculo_id>/", views.despesas_veiculo_view, name="despesas_veiculo"),
    path("painel/administrativo/despesas/<int:veiculo_id>/cadastrar/", views.adicionar_despesa_view, name="adicionar_despesa"),
    path("painel/administrativo/despesas/<int:despesa_id>/editar/", views.editar_despesa_view, name="editar_despesa"),
    path("painel/administrativo/despesas/<int:despesa_id>/excluir/", views.excluir_despesa_view, name="excluir_despesa"),
    path("painel/administrativo/despesas/veiculo/<int:veiculo_id>/excluidas/", views.despesas_excluidas_veiculo_view, name="despesas_excluidas_veiculo"),

    # =========================================================================
    # Painel do Gerente
    # =========================================================================
    path("painel/gerente/inicio/", views.painel_gerente_view, name="painel_gerente"),
    path("painel/gerente/vendas/<int:venda_id>/", views.detalhes_venda_view, name="detalhes_venda"),   # T12 - Vendas e contrato
    path("painel/gerente/vendas/<int:venda_id>/contrato/", views.contrato_venda_view, name="contrato_venda"),
    path("painel/gerente/vendas/<int:venda_id>/cancelar/", views.cancelar_venda_view, name="cancelar_venda"),
    # Vendedores
    path("painel/gerente/vendedores/", views.vendedores_view, name="vendedores"),
    path("painel/gerente/vendedores/cadastrar/", views.cadastrar_vendedor_view, name="cadastrar_vendedor"),
    path("painel/gerente/vendedores/<int:vendedor_id>/editar/", views.editar_vendedor_view, name="editar_vendedor"),
    
    # Veículos (Gerente)
    path("painel/gerente/veiculos/", views.veiculos_view, name="veiculos"),
    path("painel/gerente/veiculos/cadastrar/", views.cadastrar_veiculo_view, name="cadastrar_veiculo"),
    path("painel/gerente/veiculos/<int:veiculo_id>/", views.detalhes_veiculo_view, name="detalhes_veiculo"),
    path("painel/gerente/veiculos/<int:veiculo_id>/preco/", views.alterar_preco_veiculo_view, name="alterar_preco_veiculo"),
    path("painel/gerente/veiculos/<int:veiculo_id>/editar/", views.editar_veiculo_view, name="editar_veiculo"),
    
    # Negociações e Propostas (Gerente)
    path("painel/gerente/negociacoes/", views.negociacoes_view, name="negociacoes_gerente"),
    path("painel/gerente/negociacoes/<int:proposta_id>/decidir/", views.decidir_proposta_view, name="decidir_proposta"),
    path("painel/gerente/propostas/<int:proposta_id>/recusar/", views.recusar_proposta_fila_view, name="recusar_proposta_fila"),
    
    # Avaliação de Troca (T11)
    path("painel/gerente/avaliacoes-troca/", views.avaliacoes_troca_view, name="avaliacoes_troca"),
    path("painel/gerente/avaliacoes-troca/nova/", views.nova_avaliacao_troca_view, name="nova_avaliacao_troca"),
    path("painel/gerente/avaliacoes-troca/<int:avaliacao_id>/editar/", views.editar_avaliacao_troca_view, name="editar_avaliacao_troca"),

    # =========================================================================
    # Operações Compartilhadas em Veículos e Reservas
    # =========================================================================
    path("veiculos/<int:veiculo_id>/situacao/", views.alterar_situacao_veiculo_view, name="alterar_situacao_veiculo"),
    path("veiculos/<int:veiculo_id>/reservar/", views.reservar_veiculo_view, name="reservar_veiculo"),
    path("veiculos/reservas/<int:reserva_id>/cancelar/", views.cancelar_reserva_view, name="cancelar_reserva"),
    path("painel/gerente/vendas/<int:venda_id>/entrega/", views.registrar_entrega_view, name="registrar_entrega"),
        # T13 - Documentação e entrega (Administrativo / Gerente)
    path("painel/administrativo/documentacao/", views.documentacao_pendente_view, name="documentacao_pendente"),
    path("painel/administrativo/documentacao/etapas/<int:etapa_id>/atualizar/", views.atualizar_etapa_documentacao_view, name="atualizar_etapa_documentacao"),
    # T14 - Margem e comissão
    path("painel/gerente/margens/", views.margens_view, name="margens"),
    path("painel/vendedor/comissoes/", views.minhas_comissoes_view, name="minhas_comissoes"),
        # T15 - Histórico (Gerente, somente leitura)
    path("painel/gerente/veiculos/<int:veiculo_id>/historico/", views.historico_veiculo_view, name="historico_veiculo"),
    path("painel/gerente/clientes/<int:cliente_id>/historico/", views.historico_cliente_view, name="historico_cliente"),
    
    # T16 - Carteira de clientes

    # Vendedor
    path(
        "painel/vendedor/carteira/",
        views.carteira_vendedor_view,
        name="carteira_vendedor",
    ),
    path(
        "painel/vendedor/carteira/<int:cliente_id>/contatar/",
        views.registrar_contato_carteira_view,
        name="registrar_contato_carteira",
    ),

    # Gerente
    path(
        "painel/gerente/carteira/",
        views.carteira_gerente_view,
        name="carteira_gerente",
    ),
    path(
        "painel/gerente/carteira/configurar/",
        views.configurar_carteira_view,
        name="configurar_carteira",
    ),

]