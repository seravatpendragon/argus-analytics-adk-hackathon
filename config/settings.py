"""
Configurações globais do ArgusAnalytics-Core.
Carrega variáveis de ambiente, define caminhos e parâmetros de logging.
"""

# config/settings.py

from datetime import datetime
import os
import sys # Necessário para sys.exit
from dotenv import load_dotenv
import logging
from pathlib import Path # Usar pathlib para manipulação de caminhos mais robusta

# --- Carrega as variáveis do arquivo .env para o ambiente ---
# O arquivo .env deve estar na raiz do projeto.
# Calcula o caminho para o .env subindo dois níveis do diretório atual (config/).
dotenv_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=str(dotenv_path)) # load_dotenv espera uma string

# --- Chaves de API ---
# Obtém as chaves de API das variáveis de ambiente.
# É CRÍTICO usar variáveis de ambiente para chaves de API em produção e evitar hardcoding.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EIA_API_KEY = os.getenv("EIA_API_KEY")
FRED_API_KEY = os.getenv("FRED_API_KEY")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
NEWSAPI_API_KEY = os.getenv("NEWSAPI_API_KEY")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")

# Chaves do Reddit (se for usar)
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "ArgusFACIA/0.1 by SeuUsuarioReddit") # Fallback para User-Agent

# --- Configurações do Banco de Dados (PostgreSQL) ---
# Carrega credenciais do banco de dados das variáveis de ambiente.
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost") # Default para localhost se não definido
DB_PORT = os.getenv("DB_PORT", "5432")      # Default para 5432 se não definido
DB_NAME = os.getenv("DB_NAME")

# Constrói a URL de conexão com o banco de dados PostgreSQL.
if DB_USER and DB_PASSWORD and DB_HOST and DB_PORT and DB_NAME:
    DATABASE_URL_POSTGRES = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?client_encoding=utf8"
else:
    DATABASE_URL_POSTGRES = None # Se as credenciais não estiverem completas, a URL é None

# Define qual URL de banco de dados está ativa para o projeto.
ACTIVE_DATABASE_URL = DATABASE_URL_POSTGRES

# (Opcional) Configurações adicionais para o engine do SQLAlchemy
SQLALCHEMY_ENGINE_OPTIONS = {
    "echo": os.getenv("SQLALCHEMY_ECHO", "False").lower() == "true",  # Loga todas as queries SQL geradas (bom para dev)
    # "pool_size": int(os.getenv("SQLALCHEMY_POOL_SIZE", 5)), # Exemplo de configuração de pool
    # "max_overflow": int(os.getenv("SQLALCHEMY_MAX_OVERFLOW", 10)), # Exemplo de configuração de pool
}

# --- Definições de Caminhos do Projeto ---
# Define o diretório base do projeto (a pasta 'argus-analytics-adk-hackathon').
BASE_DIR = Path(__file__).resolve().parent.parent

# Define os caminhos para subdiretórios importantes.
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
LOGS_DIR = BASE_DIR / "logs" # Pasta para arquivos de log
REPORTS_DIR = BASE_DIR / "reports"
NOTEBOOKS_DIR = BASE_DIR / "notebooks"
SRC_DIR = BASE_DIR / "src"

# Garante que o diretório de logs exista.
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# --- Configurações de Logging ---
LOG_FILE = LOGS_DIR / "argus_analytics.log"
LOGGING_LEVEL_STR = os.getenv("LOGGING_LEVEL", "INFO").upper()
LOGGING_LEVEL = getattr(logging, LOGGING_LEVEL_STR, logging.INFO)

# Configuração básica de logging.
# Todas as mensagens com nível igual ou superior a LOGGING_LEVEL serão processadas.
logging.basicConfig(
    level=LOGGING_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), mode='w', encoding='utf-8'), # <--- ADICIONE AQUI
        logging.StreamHandler(sys.stdout) # O StreamHandler geralmente lida bem, mas podemos adicionar por segurança se necessário.
    ]
)

# Obtém um logger para este módulo.
logger = logging.getLogger(__name__)

# --- Constantes da Aplicação ---
DEFAULT_REQUEST_TIMEOUT = int(os.getenv("DEFAULT_REQUEST_TIMEOUT", 30)) # Segundos
MAX_NEWS_ARTICLES_PER_FETCH = int(os.getenv("MAX_NEWS_ARTICLES_PER_FETCH", 100))
MAX_RETRIES_API = int(os.getenv("MAX_RETRIES_API", 3))

# --- Configurações Específicas de Módulos (CVM) ---
# Define o código CVM da Petrobras para filtragem de documentos regulatórios.
CD_CVM_PETROBRAS = os.getenv("CD_CVM_PETROBRAS", "9512") # Código CVM da PETR4

# Define os anos para coleta de dados CVM (pode ser ajustado via .env)
ANO_CORRENTE_STR = os.getenv("CVM_ANO_CORRENTE", str(datetime.now().year))
ANO_ANTERIOR_STR = os.getenv("CVM_ANO_ANTERIOR", str(datetime.now().year - 1))

# Define os tipos de arquivo CVM a serem baixados (pode ser ajustado via .env)
# Exemplo: ITR para Informações Trimestrais, DFP para Demonstrações Financeiras Padronizadas
TIPOS_ARQUIVO_CVM_DOWNLOAD = os.getenv("CVM_TIPOS_ARQUIVO_DOWNLOAD", "IPE_CIA_ABERTA").split(',')

# --- Configurações Específicas de Módulos (API Delays) ---
# Define atrasos entre chamadas de API para respeitar limites de taxa.
API_DELAYS = {
    "YFINANCE": float(os.getenv("YFINANCE_API_DELAY_SECONDS", "1.0")),
    "BCB": float(os.getenv("BCB_API_DELAY_SECONDS", "1.0")),
    "IBGE": float(os.getenv("IBGE_API_DELAY_SECONDS", "1.0")),
    "FRED": float(os.getenv("FRED_API_DELAY_SECONDS", "1.0")),
    "EIA": float(os.getenv("EIA_API_DELAY_SECONDS", "1.0")),
    "NEWSAPI": float(os.getenv("NEWSAPI_API_DELAY_SECONDS", "1.0")),
    "RSS": float(os.getenv("RSS_API_DELAY_SECONDS", "0.5")) # Atraso menor para RSS mockado
}

# --- Feature Flags (para desenvolvimento modular e fases do MVP) ---
# Permite ligar/desligar funcionalidades facilmente via variáveis de ambiente.
ENABLE_BEHAVIORAL_BIAS_ANALYSIS = os.getenv("ENABLE_BEHAVIORAL_BIAS_ANALYSIS", "False").lower() == "true"
ENABLE_NETWORK_COMPLEX_ANALYSIS = os.getenv("ENABLE_NETWORK_COMPLEX_ANALYSIS", "False").lower() == "true"
ENABLE_GAME_THEORY_ANALYSIS = os.getenv("ENABLE_GAME_THEORY_ANALYSIS", "False").lower() == "true"
ENABLE_BEHAVIORAL_SIMULATIONS = os.getenv("ENABLE_BEHAVIORAL_SIMULATIONS", "False").lower() == "true"

# --- Arquivos de Configuração de Léxicos e Modelos ---
# Caminhos para arquivos de configuração JSON para léxicos e modelos específicos.
MASLOW_LEXICON_FILE = BASE_DIR / "config" / "maslow_lexicon_v1.json"
GAME_THEORY_MODELS_CONFIG_FILE = BASE_DIR / "config" / "game_theory_models_config_v1.json"
NEWS_SOURCE_DOMAIN_FILE = BASE_DIR / "config" / "news_source_domain.json" # Adicionado para credibilidade

# --- Verificações e Logs Iniciais (para debugging do setup) ---
# Verifica se as chaves de API essenciais estão carregadas.
# A GEMINI_API_KEY já é verificada e encerra o script se ausente.
for var_name in ["EIA_API_KEY", "FRED_API_KEY", "ALPHA_VANTAGE_API_KEY", "NEWSAPI_API_KEY", "GNEWS_API_KEY",
                 "DB_USER", "DB_PASSWORD", "DB_NAME"]:
    if not os.getenv(var_name): # Verifica diretamente a variável de ambiente
        logger.warning(f"Variável de ambiente '{var_name}' não encontrada. Funcionalidades dependentes podem não operar.")

# Loga a URL do banco de dados (sem a senha para segurança).
if ACTIVE_DATABASE_URL:
    logger.info(f"Usando banco de dados: {ACTIVE_DATABASE_URL.split('@')[-1]}") 
else:
    logger.error("URL do banco de dados (ACTIVE_DATABASE_URL) não está configurada. Verifique as variáveis de ambiente DB_USER, DB_PASSWORD, etc.")

# Loga outros caminhos e níveis de logging.
logger.info(f"Diretório base do projeto: {BASE_DIR}")
logger.info(f"Logging configurado para nível: {LOGGING_LEVEL_STR}, arquivo: {LOG_FILE}")
logger.info(f"GEMINI_API_KEY carregada com sucesso (não exibida por segurança).")

