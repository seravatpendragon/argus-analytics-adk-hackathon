# Argus Analytics: Deciphering the Market with Multi-Agent AI

**Hackathon:** Agent Development Kit Hackathon with Google Cloud

## Project Overview

Argus Analytics is a multi-agent Artificial Intelligence system, built with the Agent Development Kit (ADK) and Google Cloud, designed to overcome the limitations of superficial financial analysis and information overload. Our goal is to provide deeper, more actionable insights into financial assets (with an initial focus on PETR4), by applying a Maslow's Hierarchy of Needs-inspired framework to understand the drivers of market sentiment and a CRAAP-based methodology to assess the credibility of news sources.

## 🎯 The Problem We Solve

Investors and analysts often struggle to:
1.  Move beyond superficial sentiment analysis (positive/negative/neutral) to understand the true **underlying motivations and concerns** driving market perception of an asset.
2.  Cope with the **massive volume of news and information**, distinguishing credible sources from noise and misinformation.
3.  Systematically integrate **qualitative and behavioral factors** into investment analysis.

Argus Analytics aims to answer: *How can we leverage multi-agent AI to decipher the 'why' behind market sentiment (via Maslow), prioritize credible information (via CRAAP), and generate more robust and contextualized financial intelligence for assets like PETR4?*

## ✨ Proposed Solution

Our solution is an autonomous system composed of multiple AI agents orchestrated by the ADK. Each agent specializes in a stage of the analysis pipeline:

1.  **Diverse Data Collection:** Agents collect market data (YFinance), macroeconomic data (BCB, IBGE), and, crucially, news metadata (via RSS/Google Alerts).
2.  **News Processing and Enrichment:** Agents clean the data, extract the full text from articles, and assess the credibility of news sources using a CRAAP-inspired methodology.
3.  **Strategic LLM Analysis (Gemini):** A core agent utilizes Gemini (via Vertex AI) to perform a deep analysis of news content, including:
    * Nuanced sentiment analysis.
    * **Mapping to Maslow's Hierarchy of Needs** (adapted to the corporate/financial context of PETR4).
    * Identification of key stakeholders.
    * (Optional/Future in MVP) Detection of cognitive biases.
4.  **Insight Synthesis:** Agents consolidate the analyses to generate a "Maslow Profile" for the asset, identify trends, and potential inflection points.

## 🚀 Key Features and Innovations

* **Multi-Agent Architecture with ADK:** Modular design with specialized agents orchestrated by the Agent Development Kit.
* **Maslow-based Market Sentiment Analysis:** Innovative application of Maslow's Hierarchy of Needs to understand the deep motivations behind sentiment expressed in news about PETR4.
* **Source Credibility Assessment (CRAAP-inspired):** Methodology to assign credibility scores to news sources, refining the quality of analytical inputs.
* **Advanced Sentiment Analysis via LLM:** Use of Gemini for detailed and contextualized sentiment extraction.
* **Google Cloud Integration:** Leveraging Vertex AI (Gemini), Cloud Run for hosting agents, and BigQuery/PostgreSQL for data storage and analysis.
* **Detailed Initial Focus:** In-depth analysis for PETR4, with an architecture designed for scalability.

## 🛠️ Architecture and Technologies Used

Our system comprises [Number] main ADK agents:
1.  `MetadataCollectorAgent_ADK`: Collects news metadata.
2.  `FullTextExtractorAgent_ADK`: Fetches the full content of articles.
3.  `StrategicLLMAnalysisAgent_ADK`: Performs sentiment, Maslow, stakeholder (and bias, if implemented) analysis using Gemini.
4.  `MaslowSynthesizerAgent_ADK`: Aggregates Maslow analyses to generate the asset's profile.
5.  `OrchestratorAgent_ADK`: Manages the workflow between agents.

**Architecture Diagram:**
`[Link to your Architecture Diagram here - E.g., a .png file in the repository or a link to a diagramming tool]`

**Key Technologies:**
* **Agent Development Kit (ADK)**: For building and orchestrating agents.
* **Python**: Main programming language.
* **Google Cloud Platform:**
    * **Vertex AI (Gemini Pro/Advanced):** For text analysis intelligence.
    * **Cloud Run:** For hosting ADK agents scalably.
    * **BigQuery:** For storing and analyzing processed data and insights (recommended for the hackathon).
    * **PostgreSQL:** For operational data storage.
* SQLAlchemy: For database interaction.
* Other Python libraries: `newspaper3k`, `requests`, `BeautifulSoup`, `pandas`, etc.

## ⚙️ Current Project Status (Example - Update according to your progress)

As of May 30, 2025, the project has completed Phase 0 (environment and DB setup) and is well into Phase 1:
* Collection of market data (YFinance), macroeconomic data (BCB, IBGE), and news metadata (RSS) for PETR4 is functional, with data being persisted to PostgreSQL.
* News link cleaning scripts are operational.
* **Next steps for the Hackathon:**
    1.  Implement the `FullTextExtractorAgent_ADK`.
    2.  Develop and refine the `StrategicLLMAnalysisAgent_ADK` with prompts for sentiment, Maslow, and stakeholders (main focus).
    3.  Implement the `MaslowSynthesizerAgent_ADK`.
    4.  Orchestrate all agents with ADK and deploy them to Cloud Run.
    5.  Move/analyze final data in BigQuery.

## 🔧 Setup and Installation (Example - Adapt to your reality)

1.  Clone this repository:
    ```bash
    git clone [https://docs.github.com/en/repositories/creating-and-managing-repositories/about-repositories](https://docs.github.com/en/repositories/creating-and-managing-repositories/about-repositories)
    cd [repository-name]
    ```
2.  Create and activate a Python virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate    # Windows
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Set up environment variables:
    * Copy the `.env.example` file to `.env`.
    * Fill in your database credentials, Google Cloud API keys (for Vertex AI), and other necessary configurations in the `.env` file.
5.  Set up the PostgreSQL database:
    * Create the database specified in your `.env`/`settings.py`.
    * Run the table creation script (if you don't have a migration system like Alembic yet):
        ```bash
        python src/database/create_db_tables.py
        ```
6.  ## 🚀 How to Run (Example - Adapt to your reality)

To start the analysis pipeline for PETR4 (after setup):
1.  Run the main orchestrator agent:
    ```bash
    python src/main_orchestrator_adk.py --ticker PETR4
    ```
2.  (Optional) To run agents individually for testing/debugging:
    ```bash
    # Example for the full-text extractor agent
    python src/agents/full_text_extractor_agent_adk.py --max-articles 10
    ```
3.  Analysis results and insights will be stored in PostgreSQL and/or BigQuery.
    ## 🎥 Demo Video

`[Link to your Demo Video on YouTube/Vimeo here - Required]`

## 🌐 Hosted Project

`[Link to your Hosted Project here - E.g., Cloud Run URL or an interface, if any - Required]`

## 📜 License

This project is licensed under the MIT License - see the `LICENSE` file for details.

---

Remember to update this README as your project evolves during the hackathon! Add more technical details, refine the sections, and replace the placeholders. Good luck!