# Módulo 1: Configuração da Base de Dados e Ativos MVP (`src/database/`)

Data da Documentação: 22 de Maio de 2025

## 1. Objetivo do Módulo

Este módulo é o ponto de partida do projeto Argus Analytics (MVP do FAC-IA). Seu principal objetivo é estabelecer a infraestrutura do banco de dados de configuração e carregar as informações essenciais sobre os ativos selecionados para o Produto Mínimo Viável (MVP). Isso inclui dados cadastrais, classificações setoriais e, crucialmente, os resultados da análise de posicionamento na pirâmide de Maslow, obtidos através de uma metodologia proprietária de matriz fuzzy.

Este módulo garante que os dados de configuração dos ativos estejam disponíveis de forma estruturada para os módulos subsequentes de coleta, análise e geração de insights.

## 2. Scripts Principais e Execução

O módulo `src/database/` contém os seguintes scripts chave:

* **`setup.py`**:
    * **Descrição:** Este script é responsável por criar o arquivo de banco de dados SQLite (localizado em `data/fac_config.db`) e a tabela `mvp_assets` com o esquema predefinido. Ele utiliza a cláusula `CREATE TABLE IF NOT EXISTS` para garantir que possa ser executado múltiplas vezes sem erros, apenas criando a tabela se ela ainda não existir.
    * **Como Executar:**
        ```bash
        # Navegue até a raiz do projeto argus_analytics/
        python src/database/setup.py
        ```
    * **Resultado:** O arquivo `data/fac_config.db` é criado (se não existir) e a tabela `mvp_assets` é garantida.

* **`asset_loader.py`**:
    * **Descrição:** Após a criação da estrutura do banco pelo `setup.py`, este script lê os dados detalhados dos ativos MVP de um arquivo CSV (atualmente `data/ativos_mvp - ativos_mvp.csv`) e os insere na tabela `mvp_assets`. Ele mapeia as colunas do CSV para as colunas da tabela do banco de dados e utiliza `INSERT OR IGNORE` para evitar a inserção de registros duplicados (baseado na `ticker` como chave primária).
    * **Como Executar:**
        ```bash
        # Navegue até a raiz do projeto argus_analytics/
        python src/database/asset_loader.py
        ```
    * **Pré-requisitos:**
        1.  O script `src/database/setup.py` deve ter sido executado com sucesso.
        2.  O arquivo CSV de origem (ex: `data/ativos_mvp - ativos_mvp.csv`) deve existir e estar no formato esperado (com os cabeçalhos corretos).
    * **Resultado:** A tabela `mvp_assets` é populada com os dados dos ativos MVP.

## 3. Esquema da Tabela `mvp_assets`

A tabela `mvp_assets` é o principal artefato de dados deste módulo.

* **Instrução SQL de Criação:**
    ```sql
    CREATE TABLE IF NOT EXISTS mvp_assets (
        ticker TEXT PRIMARY KEY NOT NULL,
        company_name TEXT NOT NULL,
        cnpj TEXT UNIQUE,
        b3_sector TEXT,
        b3_subsector TEXT,
        b3_segment TEXT,
        capital_structure TEXT,
        initial_context_notes TEXT,
        maslow_physiological_score REAL,
        maslow_security_score REAL,
        maslow_belongingness_score REAL,
        maslow_esteem_score REAL,
        maslow_self_actualization_score REAL,
        maslow_predominant_level TEXT,
        maslow_notes TEXT
    );
    ```
* **Dicionário de Dados (Principais Campos):**
    * `ticker`: (TEXT, Chave Primária) Código de negociação do ativo.
    * `company_name`: (TEXT) Nome da empresa.
    * `cnpj`: (TEXT, Único) CNPJ da empresa.
    * `b3_sector`, `b3_segment`, `b3_subsector`: (TEXT) Classificações setoriais da B3.
    * `capital_structure`: (TEXT) Estrutura de capital (ex: "Mixed Capital").
    * `maslow_physiological_score` ... `maslow_self_actualization_score`: (REAL) Scores individuais para cada nível da pirâmide de Maslow, calculados via matriz fuzzy.
    * `maslow_predominant_level`: (TEXT) Nível Maslow identificado como predominante.
    * Consulte o código em `src/database/setup.py` ou o arquivo `config/domain_definitions.md` para descrições mais detalhadas de cada campo.

## 4. Decisões Chave Tomadas

* **Banco de Dados:** SQLite foi escolhido para o MVP devido à sua simplicidade, configuração zero e facilidade de integração com Python. O arquivo do banco é `data/fac_config.db`.
* **Empresas MVP:** A seleção inicial para o MVP inclui 8 empresas de diferentes setores da B3 (PETR4, VALE3, SUZB3, MGLU3, LREN3, TOTS3, NTCO3, VIIA3) para permitir uma validação diversificada das análises.
* **Metodologia Maslow:** Em vez de uma atribuição estática, os dados de Maslow são derivados de uma análise proprietária com matriz fuzzy, resultando em scores numéricos por nível e um nível predominante, permitindo uma análise mais rica.
* **Fonte de Dados Iniciais:** Os dados de configuração dos ativos MVP, incluindo os scores Maslow, são carregados a partir do arquivo CSV `data/ativos_mvp - ativos_mvp.csv`.
* **Bibliotecas Python (Módulo 1):** Apenas `sqlite3` (embutida) e `csv` (embutida) são estritamente necessárias para os scripts deste módulo. `os` também é usado para manipulação de caminhos.
* **Idioma e Padrões:** A estrutura do projeto, nomes de arquivos e código estão sendo padronizados para o inglês.

## 5. Status Atual

O Módulo 1 foi concluído com sucesso. O banco de dados `fac_config.db` e a tabela `mvp_assets` foram criados, e a tabela foi populada com dados iniciais para 4 empresas de teste, validando os scripts `setup.py` e `asset_loader.py`. A documentação base também foi estabelecida.