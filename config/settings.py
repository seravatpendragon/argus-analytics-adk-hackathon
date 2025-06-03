"""
Configurações globais do ArgusAnalytics-Core.
Carrega variáveis de ambiente, define caminhos e parâmetros de logging.
"""

# config/settings.py

import os
from dotenv import load_dotenv
import logging

# Carrega as variáveis do arquivo .env para o ambiente
# Certifique-se de que o arquivo .env está na raiz do projeto ou no mesmo nível que o script que importa este settings
# Para garantir que funcione bem quando settings.py está em um subdiretório (config/),
# você pode especificar o caminho para o .env se necessário:
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path=dotenv_path)
# load_dotenv() # Tenta carregar .env do diretório atual ou da raiz do projeto

# --- Chaves de API ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EIA_API_KEY = os.getenv("EIA_API_KEY")
FRED_API_KEY = os.getenv("FRED_API_KEY")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
FINNHUB_API_KEY= os.getenv("FINNHUB_API_KEY")
NEWSAPI_API_KEY= os.getenv("NEWSAPI_API_KEY")
GNEWS_API_KEY= os.getenv("GNEWS_API_KEY")
# ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY") # Exemplo, adicione conforme necessário
# Adicione suas chaves do Reddit aqui também, se for usar
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "ArgusFACIA/0.1 by SeuUsuarioReddit")


# --- Configurações do Banco de Dados (PostgreSQL) ---
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost") # Default para localhost se não definido
DB_PORT = os.getenv("DB_PORT", "5432")      # Default para 5432 se não definido
DB_NAME = os.getenv("DB_NAME")

if DB_USER and DB_PASSWORD and DB_HOST and DB_PORT and DB_NAME:
    DATABASE_URL_POSTGRES = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?client_encoding=utf8"
else:
    DATABASE_URL_POSTGRES = None # Ou uma URL de fallback para um SQLite local para dev, se preferir

# Define qual URL de banco de dados está ativa
# Para este projeto, estamos focando no PostgreSQL
ACTIVE_DATABASE_URL = DATABASE_URL_POSTGRES

# (Opcional) Configurações adicionais para o engine do SQLAlchemy
# Podem ser úteis para debugging ou otimização de pool de conexões no futuro
SQLALCHEMY_ENGINE_OPTIONS = {
    "echo": os.getenv("SQLALCHEMY_ECHO", "False").lower() == "true",  # Loga todas as queries SQL geradas (bom para dev)
    # "pool_size": int(os.getenv("SQLALCHEMY_POOL_SIZE", 5)),
    # "max_overflow": int(os.getenv("SQLALCHEMY_MAX_OVERFLOW", 10)),
}

# --- Definições de Caminhos do Projeto ---
# Define o diretório base do projeto (argus_analytics/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # __file__ é config/settings.py, sobe dois níveis

DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DATA_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DATA_DIR = os.path.join(DATA_DIR, "processed")
LOGS_DIR = os.path.join(BASE_DIR, "logs") # Pasta para arquivos de log
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
NOTEBOOKS_DIR = os.path.join(BASE_DIR, "notebooks")
SRC_DIR = os.path.join(BASE_DIR, "src")

# Garante que o diretório de logs exista
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# --- Configurações de Logging ---
LOG_FILE = os.path.join(LOGS_DIR, "argus_analytics.log")
LOGGING_LEVEL_STR = os.getenv("LOGGING_LEVEL", "INFO").upper()
LOGGING_LEVEL = getattr(logging, LOGGING_LEVEL_STR, logging.INFO)

# Configuração básica de logging (pode ser expandida em um módulo de logging dedicado)
logging.basicConfig(
    level=LOGGING_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler() # Também loga para o console
    ]
)
logger = logging.getLogger(__name__)

# --- Constantes da Aplicação ---
DEFAULT_REQUEST_TIMEOUT = int(os.getenv("DEFAULT_REQUEST_TIMEOUT", 30)) # Segundos
MAX_NEWS_ARTICLES_PER_FETCH = int(os.getenv("MAX_NEWS_ARTICLES_PER_FETCH", 100))
MAX_RETRIES_API = int(os.getenv("MAX_RETRIES_API", 3))

# --- Configurações Específicas de Módulos ---
# Exemplo: se você tiver um arquivo JSON com léxicos ou definições
MASLOW_LEXICON_FILE = os.path.join(BASE_DIR, "config", "maslow_lexicon_v1.json")
GAME_THEORY_MODELS_CONFIG_FILE = os.path.join(BASE_DIR, "config", "game_theory_models_config_v1.json")

# --- Feature Flags (para desenvolvimento modular e fases do MVP) ---
# Permite ligar/desligar funcionalidades facilmente
ENABLE_BEHAVIORAL_BIAS_ANALYSIS = os.getenv("ENABLE_BEHAVIORAL_BIAS_ANALYSIS", "False").lower() == "true"
ENABLE_NETWORK_COMPLEX_ANALYSIS = os.getenv("ENABLE_NETWORK_COMPLEX_ANALYSIS", "False").lower() == "true"
ENABLE_GAME_THEORY_ANALYSIS = os.getenv("ENABLE_GAME_THEORY_ANALYSIS", "False").lower() == "true"
ENABLE_BEHAVIORAL_SIMULATIONS = os.getenv("ENABLE_BEHAVIORAL_SIMULATIONS", "False").lower() == "true"

# --- Verificações e Logs Iniciais (para debugging do setup) ---

for var in ["GEMINI_API_KEY", "EIA_API_KEY", "FRED_API_KEY", "ALPHA_VANTAGE_API_KEY", "DB_USER", "DB_PASSWORD", "DB_NAME"]:
    if not globals().get(var):
        logger.warning(f"Variável de ambiente {var} não encontrada.")

if ACTIVE_DATABASE_URL:
    logger.info(f"Usando banco de dados: {ACTIVE_DATABASE_URL.split('@')[-1]}") # Loga sem a senha
else:
    logger.error("URL do banco de dados (ACTIVE_DATABASE_URL) não está configurada. Verifique as variáveis de ambiente DB_USER, DB_PASSWORD, etc.")

logger.info(f"Diretório base do projeto: {BASE_DIR}")
logger.info(f"Logging configurado para nível: {LOGGING_LEVEL_STR}, arquivo: {LOG_FILE}")


ATIVOS_MVP_CSV_PATH = os.path.join(DATA_DIR, "config_input", "ativos_mvp.csv") 

API_DELAYS = {
    "YFINANCE": float(os.getenv("YFINANCE_API_DELAY_SECONDS", "1.0")),
    "BCB": float(os.getenv("BCB_API_DELAY_SECONDS", "1.0")),
    "IBGE": float(os.getenv("IBGE_API_DELAY_SECONDS", "1.0")),
    "FRED": float(os.getenv("FRED_API_DELAY_SECONDS", "1.0")),
    "EIA": float(os.getenv("EIA_API_DELAY_SECONDS", "1.0")),
    "NEWSAPI": float(os.getenv("NEWSAPI_API_DELAY_SECONDS", "1.0")),
    "RSS": float(os.getenv("NEWSAPI_API_DELAY_SECONDS", "0.5"))
}

# filepath: c:\ArgusAnalytics\argus-analytics-adk-hackathon\src\config.py
import logging

class Settings:
    logger = logging.getLogger("default_logger")

settings = Settings()



