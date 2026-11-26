# Revenda Certa — roteiro de revisão pré-deploy

## Preparação
Use somente o banco local `revendacerta_demo`. Faça backup antes (pg_dump com as credenciais locais, sem publicar o dump). Aplique primeiro as correções pré-deploy. Execute `python manage.py check` e `python manage.py popular_cenarios --confirmar`. Opcionalmente informe `--vendedor USERNAME --outro-vendedor USERNAME`. O comando imprime os usuários e IDs a utilizar. Guarde a saída. Não cria usuários nem altera senhas; exige dois vendedores ativos com perfil comercial e um gerente. Não repete a carga se já houver clientes marcados. Se falhar, a transação é revertida. Não há comando de limpeza: restaure o backup em banco de demonstração separado se quiser reiniciar os cenários.

São oito veículos de modelos ainda não cadastrados (comparação marca/modelo sem distinção de maiúsculas), seis clientes fictícios, três vendas (duas antigas), uma contraproposta, uma procura, uma despesa e uma reserva com proposta em fila. Os carros usam placas RCD8001 a RCD8008, e clientes começam com DEMO RC. Não há fotos novas: o objetivo é testar fluxos e telas; use os carros existentes para testar galerias. Os valores e identificadores são fictícios; não faça ligações reais. As vendas antigas são retrodatadas para simular carteira, não representam uma auditoria histórica real. A reserva dura 24h; teste no mesmo dia.

## Roteiro (na ordem sugerida)

| Perfil | Onde olhar | O que verificar |
|---|---|---|
| Gerente | Veículos → pesquisar placa RCD8008 | Contador singular: 1 veículo encontrado. Abrir detalhes e conferir menu ativo. |
| Gerente | Negociações → cliente DEMO RC Contraproposta | Link do cliente estilizado, histórico abre e navegação permanece coerente. |
| Vendedor 1 | Propostas → DEMO RC Contraproposta | Aceitar R$ 75.000; composição anterior R$ 70.000; aviso de diferença R$ 5.000. Ajustar pagamento para R$ 75.000, confirmar reserva e conferir possibilidade de fechamento. |
| Vendedores 1 e 2 | Carteira de clientes | DEMO RC Carteira Compartilhada aparece inicialmente na fila de ambos. Registrar contato no V1; atualizar V2 e conferir que saiu da fila. Se agendar retorno futuro, não deve reaparecer antes da data. |
| Gerente | Carteira de clientes → DEMO RC Carteira Compartilhada | Abrir histórico pelo nome e voltar à carteira. |
| Administrativo | Despesas → RCD8006 | Despesa de R$ 350; conferir botões editar/excluir, mensagens e histórico. |
| Gerente ou administrativo autorizado | Veículos/despesas → RCD8005 | Alterar de Em preparação para Disponível pela interface. Antes disso não deve haver aviso dessa procura. |
| Vendedor 1 | Início e Procuras | Conferir aviso do RCD8005 para DEMO RC Procura; marcar como lido e verificar atualização. |
| Gerente | Veículos → RCD8007 | Reserva ativa; proposta do segundo vendedor em espera. Testar cancelamento e promoção da fila por último. |
| Gerente | Vendas / Margens / Relatórios | Localizar DEMO RC Venda Atual, conferir valor R$ 80.000, margem e filtros. |
| Administrativo | Documentação / Entregas | Venda atual com etapas pendentes; conferir ações e mensagens. |
| Vendedor 1 | Comissões | Conferir venda atual; comissão depende do percentual já configurado no perfil. |
| Gerente | Início → configurar metas (`/painel/gerente/metas/`) | Alterar meta, salvar, conferir histórico legível, tema claro/escuro e celular. |

Para testar o redirecionamento de reserva inexistente, prefira teste automatizado; não é um fluxo normal de navegação. Execute `python manage.py test core.tests.test_revisao_pendencias --verbosity=2` se o arquivo da correção estiver instalado e `python manage.py test --verbosity=2` para a suíte disponível.

## Limitações
A carga foi construída a partir dos models e URLs do ZIP enviado e das correções pré-deploy. Sintaxe Python verificada, mas não executada contra Django/PostgreSQL neste ambiente. Não cria avaliações de troca nem simula todos os estados de documentação/entrega. Não execute em produção. Não altera configurações globais de carteira ou comissão. Se não houver oito modelos inéditos da lista, o comando aborta sem gravar dados.
