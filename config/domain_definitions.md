# Definições de Domínio para o Projeto Argus Analytics (MVP FAC-IA)

Data da Última Atualização: 26 de Maio de 2025

## 1. Introdução

Este documento formaliza as definições e categorias para diversos campos e conceitos utilizados no banco de dados e nas análises do projeto Argus Analytics, o MVP do Framework de Análise Contínua com Inteligência Artificial (FAC-IA). O objetivo é garantir consistência na coleta, interpretação e utilização dos dados.

## 2. Categorias de Estrutura de Capital (`capital_structure` na tabela `mvp_assets`)

Define a natureza do controle e propriedade da empresa.

* **"Estatal Federal":** Empresa controlada majoritariamente pela União.
* **"Estatal Estadual/Municipal":** Empresa controlada majoritariamente por um estado ou município.
* **"Capital Misto - Controle Estatal":** Empresa de capital aberto com participação estatal significativa e controle decisório pelo ente estatal.
* **"Capital Misto - Controle Privado":** Empresa de capital aberto com participação estatal minoritária ou sem poder de controle decisório pelo ente estatal, onde o controle é primariamente privado.
* **"Privada - Controle Definido Nacional":** Empresa de capital aberto controlada por acionistas privados nacionais (pessoa física, grupo familiar ou empresa nacional).
* **"Privada - Controle Definido Estrangeiro":** Empresa de capital aberto controlada por acionistas privados estrangeiros.
* **"Privada - Capital Pulverizado":** Empresa de capital aberto sem um acionista ou bloco de controle claramente definido (True Corporation).
* **"Outra":** Para estruturas não classificáveis nas anteriores (requer detalhamento em `initial_context_notes`).

## 3. Tipos de Interação Estratégica (`strategic_interaction_type` na tabela `mvp_assets`)

Classifica o tipo predominante de interação estratégica da empresa em seu mercado, inspirado em conceitos da Teoria dos Jogos.

* **"Competição Bertrand (Preço)":** Empresas competem primariamente através da definição de preços para produtos/serviços homogêneos ou pouco diferenciados.
* **"Competição Cournot (Quantidade/Market Share)":** Empresas competem primariamente definindo quantidades de produção ou buscando ativamente aumentar/manter sua participação de mercado.
* **"Liderança Stackelberg (Líder)":** A empresa atua como líder de mercado, tomando decisões estratégicas (preço, quantidade, inovação) que são seguidas pelos concorrentes.
* **"Liderança Stackelberg (Seguidor)":** A empresa reage às decisões estratégicas de um líder de mercado.
* **"Cooperação Tácita / Oligopólio Diferenciado":** Poucos players dominantes, competição menos agressiva em preço, possível coordenação implícita ou foco em diferenciação.
* **"Jogo de Inovação e P&D Contínuo":** A competição se baseia fortemente no lançamento de novos produtos, tecnologias ou P&D intensivo.
* **"Jogo Regulatório Intenso":** As estratégias da empresa são fortemente influenciadas e direcionadas pela interação com agências reguladoras e pelo ambiente legal/político.
* **"Foco em Parcerias/Ecossistema":** A estratégia predominante envolve a criação e manutenção de alianças estratégicas, joint ventures ou ecossistemas de negócios.
* **"Guerra de Atrito / Defesa de Posição":** Interações competitivas intensas e prolongadas, muitas vezes com o objetivo de desgastar concorrentes ou defender market share.
* **"Não Aplicável / Indefinido":** Quando nenhum dos tipos acima descreve adequadamente a interação predominante para o escopo do MVP.

## 4. Níveis da Hierarquia de Maslow

Referem-se à teoria de Abraham Maslow, adaptada para o contexto de análise de empresas e sentimento de mercado.

### 4.1 Níveis Detalhados (para `mvp_assets` - scores da Matriz Fuzzy)

Estes são os níveis cujos scores (ex: `maslow_physiological_score`) são calculados pela sua metodologia de matriz fuzzy e armazenados na tabela `mvp_assets`.

* **Fisiológico (`maslow_physiological_score`):** Relacionado à sobrevivência básica e essencialidade da empresa/setor para a economia ou para as necessidades primárias da população (ex: alimentos, água, energia básica).
* **Segurança (`maslow_security_score`):** Relacionado à estabilidade, previsibilidade, proteção contra perdas, confiabilidade dos produtos/serviços ou da própria empresa/setor (ex: utilities, saúde defensiva, seguros, infraestrutura crítica, empresas com receita recorrente forte).
* **Social/Pertencimento (`maslow_belongingness_score`):** Relacionado à conexão, comunidade, identidade de grupo, aceitação social que a empresa/produto promove ou da qual depende (ex: redes sociais, marcas com forte apelo comunitário, produtos de consumo que facilitam interação).
* **Estima (`maslow_esteem_score`):** Relacionado ao status, reconhecimento, respeito, conquistas, luxo, autoexpressão e poder que a empresa/produto oferece ou representa (ex: marcas de luxo, produtos que conferem status, empresas líderes de mercado com forte reputação).
* **Autorrealização (`maslow_self_actualization_score`):** Relacionado ao crescimento pessoal, desenvolvimento de potencial, inovação disruptiva, propósito maior, criatividade e contribuições transformadoras da empresa/setor (ex: empresas de tecnologia de ponta, educação transformadora, P&D intensivo, empresas com forte impacto social/ambiental positivo percebido como inovador).
* **`maslow_predominant_level`**: O nível da hierarquia acima que apresenta o maior score ou que, segundo sua metodologia fuzzy, melhor caracteriza o perfil Maslow da empresa.
* **`maslow_notes`**: Observações qualitativas específicas sobre a classificação Maslow da empresa.

### 4.2 Níveis Simplificados (para Análise de Sentimento de Notícias - Módulo 4)

Usados para classificar o tom geral ou a implicação de notícias individuais em relação ao sentimento de mercado.

* **"Medo":** Notícias que evocam incerteza, risco, perdas potenciais, pânico, aversão ao risco, ameaças à segurança ou estabilidade.
* **"Neutro":** Notícias factuais, sem forte carga emocional positiva ou negativa aparente, ou com sentimentos mistos que se anulam.
* **"Ganância":** Notícias que evocam otimismo excessivo, euforia, oportunidades de alto ganho rápido, especulação intensa, potencial para grandes valorizações (às vezes descoladas de fundamentos).

## 5. Tipos de Relação Estratégica (`relationship_type` na tabela `strategic_relationships`)

Define a natureza da interação ou conexão entre dois ativos (empresas).

* **"Concorrente Direto":** Empresas que oferecem produtos/serviços similares e disputam os mesmos clientes no mesmo segmento de mercado.
* **"Concorrente Indireto":** Empresas cujos produtos/serviços, embora diferentes, podem satisfazer a mesma necessidade do consumidor ou competir por uma fatia do orçamento do cliente.
* **"Fornecedor Chave":** Empresa A é um fornecedor crítico para a empresa B.
* **"Cliente Chave":** Empresa A é um cliente crítico para a empresa B.
* **"Parceria Estratégica":** Acordo formal ou informal de cooperação para um objetivo comum.
* **"Complementaridade Setorial":** Empresas em setores diferentes, mas cujos negócios se beneficiam mutuamente ou são interdependentes.
* **"Influência Regulatória Comum":** Empresas que operam sob o mesmo arcabouço regulatório intensivo ou são significativamente impactadas pelas mesmas agências.
* **"Participação Acionária Relevante":** Empresa A possui participação significativa na Empresa B, ou vice-versa, ou um mesmo acionista relevante em ambas.
* **"Outra":** Para relações não especificadas acima (requer descrição).

## 6. Diretrizes para Campos Qualitativos de Texto Livre na `mvp_assets`

Estes campos devem ser preenchidos com informações concisas e factuais, focando nos aspectos mais relevantes para a análise estratégica.

### 6.1 `government_connection_details`
* **Foco:** Natureza da regulação (agência, intensidade), dependência de contratos/licitações, tipo de concessões, participação governamental direta/indireta (além da `capital_structure`), histórico relevante de intervenções.

### 6.2 `competition_exposure_details`
* **Foco:** Identificação dos 2-3 principais concorrentes, percepção da estrutura do mercado (oligopólio, fragmentado), principais bases de competição (preço, inovação), barreiras de entrada significativas, ameaças competitivas notáveis.

### 6.3 `initial_context_notes`
* **Foco:** Qualquer outra informação idiossincrática e relevante sobre o ativo que não se encaixe nos demais campos, mas que possa impactar a análise (ex: reestruturações recentes, alta dependência de commodities específicas, litígios importantes, mudanças chave na liderança, riscos ESG específicos e notórios).

## 7. Critérios CRAAP (para `monitored_sources`)

Usados para avaliar e ponderar a credibilidade e utilidade das fontes de notícias. Scores podem ser de 0.0 a 1.0 (ou 1 a 5, ajuste conforme sua escala).

* **`craap_currency` (Atualidade):** Quão recente é a informação? A fonte é atualizada frequentemente? Para notícias financeiras, a atualidade é crucial.
* **`craap_relevance` (Relevância):** A informação se relaciona diretamente com o tópico de interesse (empresa, setor, mercado)? O público-alvo da fonte é pertinente?
* **`craap_authority` (Autoridade):** Qual a credibilidade do autor, da publicação ou da organização por trás da fonte? Possuem expertise reconhecida na área?
* **`craap_accuracy` (Acurácia):** A informação é factualmente correta, bem pesquisada e suportada por evidências? Há revisão editorial? A fonte tem histórico de correção de erros?
* **`craap_purpose` (Propósito):** Qual o objetivo da informação (informar, persuadir, vender, entreter)? Há viés político, ideológico ou comercial claro que possa distorcer a informação?
* **`craap_score_geral`**: Um score consolidado derivado dos critérios individuais, usado como peso para a fonte.

---
