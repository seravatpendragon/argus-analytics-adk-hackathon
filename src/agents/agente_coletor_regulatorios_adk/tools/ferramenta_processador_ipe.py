# src/agents/agente_coletor_regulatorios_adk/tools/ferramenta_processador_ipe.py

import logging
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import zipfile
import io
import os
import numpy as np # Importar numpy para np.nan

# --- Configuração de Caminhos para Imports do Projeto ---
from pathlib import Path
import sys
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    # Sobe 4 níveis (tools/ -> agente_coletor_regulatorios_adk/ -> agents/ -> src/ -> PROJECT_ROOT)
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except Exception as e:
    logging.error(f"Erro ao configurar PROJECT_ROOT em ferramenta_processador_ipe.py: {e}")
    PROJECT_ROOT = Path(os.getcwd())

# Importa o logger de settings e db_utils
try:
    from config import settings
    from src.database.db_utils import get_db_session, NewsArticle # Importa NewsArticle para usar no filtro de data
    from sqlalchemy import func # Para usar func.max
    _USING_MOCK_DB_FOR_DATE_CHECK = False
except ImportError as e:
    logging.error(f"Não foi possível importar settings ou db_utils para ferramenta_processador_ipe: {e}. O teste de data será mockado.")
    _USING_MOCK_DB_FOR_DATE_CHECK = True
    # Mocks para o teste de data se o DB real não estiver disponível
    class MockNewsArticle:
        publication_date = None # Mock para o atributo
    class MockDBSession:
        def query(self, *args): return self
        def filter(self, *args): return self
        def scalar(self): return None # Sempre retorna None para simular nenhuma data anterior
        def close(self): pass
    def get_db_session(): return MockDBSession()
    
logger = logging.getLogger(__name__)

# Constantes para tipos de documento CVM relevantes
TIPOS_DOC_CVM_RELEVANTES = [
    "Fato Relevante",
    "Comunicado ao Mercado",
    "Aviso aos Acionistas",
    "Relatório Proventos", # Geralmente contém informações importantes e textuais
    "Comunicação sobre demandas societárias",
    "Comunicação sobre Transação entre Partes Relacionadas",
    "Informação Prestada às Bolsas Estrangeiras",
    "Assembleia",
    "Aviso aos Debenturistas",
    "Calendário de Eventos Corporativos",
    "Carta Anual de Governança Corporativa",
    "Dados Econômico-Financeiros",
    "Documentos de Oferta de Distribuição Pública",
    "Escrituras e aditamentos de debêntures",
    "Estatuto Social",
    "Informação Prestada às Bolsas Estrangeiras",
    "Reunião da Administração",
    "Valores Mobiliários negociados e detidos (art. 11 da Instr. CVM nº 358)"
]

def get_latest_processed_date_for_cvm_file(session: Any, file_identifier: str, cd_cvm_empresa: str) -> Optional[datetime]:
    """
    Busca a data de publicação mais recente de um artigo CVM já processado e salvo no DB
    para um dado arquivo ZIP e código CVM da empresa.
    """
    if _USING_MOCK_DB_FOR_DATE_CHECK:
        return None 
    return None


def tool_process_cvm_ipe_local(caminho_zip_local: str, cd_cvm_empresa: str, tool_context: Any) -> Dict[str, Any]:
    """
    Processa um arquivo ZIP local de dados IPE da CVM, extrai metadados de documentos
    relevantes para uma empresa específica e filtra apenas os novos documentos.

    Args:
        caminho_zip_local (str): Caminho completo para o arquivo ZIP local da CVM.
        cd_cvm_empresa (str): Código CVM da empresa a ser filtrada (ex: "9512" para PETR4).
        tool_context (Any): O contexto da ferramenta do ADK, usado para gerenciar o estado
                            (ex: última data de processamento para evitar duplicatas).

    Returns:
        Dict[str, Any]: Um dicionário com 'status' ('success' ou 'error') e uma lista
                        de metadados de novos documentos ('novos_documentos').
    """
    novos_documentos: List[Dict[str, Any]] = []
    file_identifier = Path(caminho_zip_local).name 
    state_key = f"ipe_last_processed_date_{file_identifier.replace('.', '_')}_{cd_cvm_empresa}"

    last_processed_date_str = tool_context.state.get(state_key)
    last_processed_date: Optional[datetime] = None
    if last_processed_date_str:
        try:
            last_processed_date = datetime.fromisoformat(last_processed_date_str)
            logger.info(f"Processando IPE local: '{caminho_zip_local}' para CD_CVM {cd_cvm_empresa}. Última data: {last_processed_date.isoformat()}")
        except ValueError:
            logger.warning(f"Data inválida no estado da sessão para {state_key}: {last_processed_date_str}. Ignorando data anterior.")
    else:
        logger.info(f"Processando IPE local: '{caminho_zip_local}' para CD_CVM {cd_cvm_empresa}. Última data: Nenhuma")

    try:
        with zipfile.ZipFile(caminho_zip_local, 'r') as z:
            csv_file_name = None
            for name in z.namelist():
                if name.endswith('.csv') and file_identifier.replace('.zip', '') in name:
                    csv_file_name = name
                    break
            
            if not csv_file_name:
                raise FileNotFoundError(f"Arquivo CSV não encontrado dentro do ZIP: {caminho_zip_local}")

            with z.open(csv_file_name) as csv_file:
                df = pd.read_csv(csv_file, sep=';', encoding='latin1', low_memory=False)

        # Filtra pela empresa usando o nome da coluna correto
        df_empresa = df[df['Codigo_CVM'] == int(cd_cvm_empresa)] 

        # Filtra por tipos de documento relevantes usando a coluna 'Categoria'
        df_relevantes = df_empresa[df_empresa['Categoria'].isin(TIPOS_DOC_CVM_RELEVANTES)].copy() 

        # Converte a coluna de data para datetime e filtra documentos novos
        df_relevantes['Data_Entrega'] = pd.to_datetime(df_relevantes['Data_Entrega'], format='%Y-%m-%d', errors='coerce') 
        df_relevantes.dropna(subset=['Data_Entrega'], inplace=True)

        # Ordena por data para garantir que a última data seja a mais recente
        df_relevantes.sort_values(by='Data_Entrega', ascending=False, inplace=True) 

        documentos_filtrados_para_retorno = []
        most_recent_publication_date_in_this_run: Optional[datetime] = None

        for index, row in df_relevantes.iterrows():
            public_date = row['Data_Entrega'].to_pydatetime().replace(tzinfo=timezone.utc)
            
            if last_processed_date and public_date <= last_processed_date:
                continue

            if most_recent_publication_date_in_this_run is None or public_date > most_recent_publication_date_in_this_run:
                most_recent_publication_date_in_this_run = public_date

            # CORREÇÃO AQUI: Tratar np.nan para campos de texto
            title_val = row['Assunto']
            if isinstance(title_val, float) and np.isnan(title_val):
                title_val = None
            
            document_type_val = row['Categoria']
            if isinstance(document_type_val, float) and np.isnan(document_type_val):
                document_type_val = None

            doc_metadata = {
                "title": title_val, # <-- Usar o valor tratado
                "document_url": row['Link_Download'], 
                "publication_date_iso": public_date.isoformat(),
                "document_type": document_type_val, # <-- Usar o valor tratado
                "protocol_id": row['Protocolo_Entrega'], 
                "company_cvm_code": str(row['Codigo_CVM']), 
                "company_name": row['Nome_Companhia'], 
                "source_main_file": file_identifier,
                "source_type": "CVM_IPE" 
            }
            documentos_filtrados_para_retorno.append(doc_metadata)
        
        logger.info(f"DEBUG_IPE: Documentos da empresa {cd_cvm_empresa} que correspondem aos categorias desejados: {len(df_relevantes)}")
        logger.info(f"Processamento de '{caminho_zip_local}' concluído. {len(documentos_filtrados_para_retorno)} novos docs encontrados de {len(df_relevantes)} filtrados.")

        if most_recent_publication_date_in_this_run:
            tool_context.state[state_key] = most_recent_publication_date_in_this_run.isoformat()
            logger.info(f"Estado '{state_key}' ATUALIZADO para: {tool_context.state[state_key]}")

        return {"status": "success", "novos_documentos": documentos_filtrados_para_retorno}

    except FileNotFoundError as e:
        logger.error(f"Arquivo não encontrado: {e}")
        return {"status": "error", "message": f"Arquivo não encontrado: {e}", "novos_documentos": []}
    except Exception as e:
        logger.error(f"Erro ao processar arquivo IPE da CVM '{caminho_zip_local}': {e}", exc_info=True)
        return {"status": "error", "message": str(e), "novos_documentos": []}