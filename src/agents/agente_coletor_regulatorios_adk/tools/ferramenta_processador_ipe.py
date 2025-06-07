import pandas as pd
import zipfile
from io import TextIOWrapper
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import settings
from src.database.db_utils import get_db_session, get_or_create_news_source
from src.database.create_db_tables import NewsArticle

def tool_process_cvm_ipe_local(caminho_zip_local: str, Codigo_CVM_empresa: str) -> dict:
    """
    Processa um arquivo IPE ZIP local, filtra por uma empresa e salva novos documentos no banco.
    """
    settings.logger.info(f"Processando arquivo IPE '{caminho_zip_local}' para a empresa CVM: {Codigo_CVM_empresa}")
    
    db_session: Session | None = None
    try:
        db_session = get_db_session()
        nome_arquivo_csv = Path(caminho_zip_local).stem + '.csv'
        
        all_docs_to_insert = []
        
        source_domain_cvm = "cvm.gov.br"
        source_name_cvm = "Comissão de Valores Mobiliários (CVM)"
        credibility_data_mock = {source_domain_cvm: {"source_name": source_name_cvm, "overall_credibility_score": 1}}
        cvm_source_obj = get_or_create_news_source(db_session, source_domain_cvm, source_name_cvm, credibility_data_mock)
        if not cvm_source_obj:
            raise Exception("Não foi possível criar a fonte padrão 'CVM' no banco de dados.")

        with zipfile.ZipFile(caminho_zip_local, 'r') as z:
            with z.open(nome_arquivo_csv, 'r') as csv_file:
                chunk_iterator = pd.read_csv(
                    TextIOWrapper(csv_file, 'latin-1'), sep=';', encoding='latin-1',
                    chunksize=10000, dtype={'Codigo_CVM': str}
                )
                
                for chunk in chunk_iterator:
                    
                    chunk.columns = [str(col).strip() for col in chunk.columns]
                    df_empresa = chunk[chunk['Codigo_CVM'] == Codigo_CVM_empresa]

                    for row in df_empresa.itertuples():
                        link_documento = getattr(row, 'Link_Download', None)
                        if not link_documento or not isinstance(link_documento, str):
                            continue

                        # LÓGICA DE TÍTULO INTELIGENTE (SUA SUGESTÃO)
                        assunto = getattr(row, 'Assunto', '')
                        if isinstance(assunto, str) and assunto.strip():
                            headline_text = assunto.strip()
                        else:
                            # Fallback para Categoria + Protocolo
                            categoria = getattr(row, 'Categoria', 'Documento')
                            protocolo = getattr(row, 'Protocolo_Entrega', 'Sem Protocolo')
                            headline_text = f"{categoria} - Protocolo {protocolo}"
                            settings.logger.warning(f"Documento CVM sem 'Assunto'. Usando fallback: '{headline_text}'. Link: {link_documento}")

                        doc_dict = {
                            "headline": headline_text,
                            "article_link": link_documento,
                            "publication_date": datetime.strptime(str(row.Data_Entrega), '%Y-%m-%d'),
                            "news_source_id": cvm_source_obj.news_source_id,
                            "summary": f"Documento Regulatório: {getattr(row, 'Categoria', '')}",
                            "article_type": "Regulatório CVM",
                            "processing_status": 'processed', 
                            "source_feed_name": "CVM - Regulatórios",
                            "collection_date": datetime.now(tz=timezone.utc)
                        }
                        all_docs_to_insert.append(doc_dict)
        
        if not all_docs_to_insert:
            return {"status": "success", "message": "Nenhum documento novo para a empresa encontrada."}

        stmt = pg_insert(NewsArticle).values(all_docs_to_insert)
        stmt = stmt.on_conflict_do_nothing(index_elements=['article_link'])
        result = db_session.execute(stmt)
        db_session.commit()
        
        return {"status": "success", "message": f"{result.rowcount} novos documentos regulatórios inseridos."}

    except Exception as e:
        if db_session: db_session.rollback()
        settings.logger.error(f"Erro ao processar arquivo IPE: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        if db_session: db_session.close()