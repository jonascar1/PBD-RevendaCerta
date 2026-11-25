<div align="center">

# Revenda Certa

**Sistema web de gestão de revenda de veículos com vitrine pública**

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)

</div>

---

## Sobre o projeto

Este projeto consiste em um sistema web completo para gestão de revenda de veículos, desenvolvido para a disciplina de **Projeto de Banco de Dados** da **UFRPE (UAST)**, sob orientação do professor **Heldon José**, utilizando Python, Django, HTML, CSS e JavaScript.

A proposta acompanha o ciclo de vida de cada veículo desde a aquisição até a entrega, controlando custos, despesas, avaliação de veículos na troca, reservas com prazo, fila de espera, propostas, contrapropostas e alçada de aprovação de descontos, até o cálculo da margem real da operação e das comissões. Além do fechamento da venda, o sistema mantém o cliente em uma carteira de relacionamento voltada à fidelização e ao retorno ao longo do tempo.

A solução reúne a vitrine pública e a área de gestão em uma aplicação conectada ao mesmo banco de dados. Ambos os integrantes colaboraram em todas as etapas do desenvolvimento.

## Autores

Um sistema web desenvolvido por **Jonas Carneiro** e **Dowglas Hademar** na disciplina de Projeto de Banco de Dados da UFRPE (UAST), sob orientação do professor **Heldon José**.

---

## Funcionalidades

- **Vitrine pública:** catálogo com filtros, galeria de fotos e contato direto pelo WhatsApp.
- **Estoque:** cadastro de veículos com origem (comprado, troca ou consignado), fotos e histórico completo.
- **Reservas e fila de espera:** reservas com prazo de expiração e promoção automática da fila.
- **Propostas:** composição de pagamento, alçada de desconto por veículo, aprovação, recusa e contraproposta do gerente.
- **Vendas:** fechamento atômico, contrato imprimível, documentação pós-venda e checklist de entrega.
- **Financeiro:** despesas por veículo, margem real recalculada e comissão dos vendedores.
- **Carteira de clientes e procuras:** relacionamento para recompra e avisos de veículos compatíveis.
- **Relatórios:** exportação em Excel, PDF e CSV.
- **Perfis de acesso:** Gerente, Vendedor e Administrativo, com tema claro e escuro.

---

## Pré-requisitos

| Ferramenta | Versão recomendada |
|---|---|
| [Python](https://www.python.org/downloads/) | 3.10 ou superior |
| [PostgreSQL](https://www.postgresql.org/download/) | 13 ou superior |
| [Git](https://git-scm.com/downloads) | qualquer versão recente |

> O projeto carrega Lucide, Chart.js, jsPDF e Google Fonts por CDN. Mantenha a conexão com a internet ativa ao usá-lo.

---

## Como executar

### 1. Clone o repositório

```bash
git clone <URL-DO-REPOSITORIO>
cd <NOME-DA-PASTA>
```

### 2. Crie e ative o ambiente virtual

**Windows (PowerShell):**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure as variáveis de ambiente

Credenciais e chaves secretas **não ficam no código**. Elas ficam em um arquivo `.env` local, que nunca é versionado.

Copie o modelo:

**Windows:**
```bash
copy .env.example .env
```

**Linux / macOS:**
```bash
cp .env.example .env
```

Gere uma chave secreta nova:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Abra o `.env` e preencha os valores:

```env
DJANGO_SECRET_KEY=cole-aqui-a-chave-gerada
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

DB_NAME=revendacerta
DB_USER=revendacerta_user
DB_PASSWORD=escolha-uma-senha-forte
DB_HOST=localhost
DB_PORT=5432

WHATSAPP_NUMERO=5587999999999
```

> `DJANGO_DEBUG=True` é necessário para rodar localmente, pois é o que faz o servidor de desenvolvimento servir arquivos estáticos e as fotos enviadas. Nunca use `True` em produção.

### 5. Crie o banco de dados no PostgreSQL

Abra o `psql` (ou o pgAdmin) e execute, usando **os mesmos valores** do seu `.env`:

```sql
CREATE USER revendacerta_user WITH PASSWORD 'escolha-uma-senha-forte';
CREATE DATABASE revendacerta OWNER revendacerta_user;
```

### 6. Aplique as migrações

```bash
python manage.py migrate
```

### 7. Crie o usuário Gerente

O sistema usa um modelo de usuário próprio, com perfil obrigatório. Por isso, não use `createsuperuser`. Abra o shell do Django:

```bash
python manage.py shell
```

E execute:

```python
from core.models import Usuario

Usuario.objects.create_user(
    username="gerente",
    password="defina-uma-senha-forte",
    first_name="Gerente",
    perfil="GERENTE",
)
```

Para criar também um usuário **Administrativo**, repita o comando com `perfil="ADMINISTRATIVO"`.

> Os vendedores são cadastrados pelo próprio gerente no painel, em **Vendedores > Cadastrar vendedor**.

### 8. Inicie o servidor

```bash
python manage.py runserver
```

---

## Acessos

| Página | Endereço |
|---|---|
| Vitrine pública | http://127.0.0.1:8000/ |
| Login da equipe | http://127.0.0.1:8000/accounts/login/ |
| Django Admin | http://127.0.0.1:8000/admin/ |

Após o login, cada perfil é redirecionado ao seu painel: Gerente, Vendedor ou Administrativo.

---

## Expiração de reservas (opcional)

As reservas vencidas são encerradas automaticamente ao navegar pelo sistema. Para processá-las também por comando, por exemplo em um agendador de tarefas, execute:

```bash
python manage.py expirar_reservas
```

---

## Segurança

- O arquivo `.env` está no `.gitignore` e **nunca deve ser enviado ao repositório**. Compartilhe apenas o `.env.example`, que contém valores fictícios.
- Cada pessoa que rodar o projeto deve gerar a própria `DJANGO_SECRET_KEY`.
- Em produção, use `DJANGO_DEBUG=False`, informe o domínio real em `DJANGO_ALLOWED_HOSTS` e configure um servidor para arquivos estáticos e de mídia.

---

## Estrutura resumida

```
├── config/              # Configurações do projeto Django
├── core/
│   ├── models.py        # Regras de domínio
│   ├── views.py         # Views dos painéis
│   ├── forms.py         # Formulários e validações
│   ├── migrations/      # Migrações do banco
│   ├── templates/core/  # Páginas HTML
│   ├── static/core/     # CSS, JS e imagens
│   └── management/      # Comandos personalizados
├── .env.example         # Modelo de variáveis de ambiente
├── requirements.txt
└── manage.py
```

---

## Instituição

**Universidade Federal Rural de Pernambuco**
Unidade Acadêmica de Serra Talhada (UAST)
Disciplina: Projeto de Banco de Dados · Orientação: Prof. Heldon José