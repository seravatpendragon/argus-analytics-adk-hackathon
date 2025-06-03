# src/agents/agente_coletor_regulatorios_adk/tools/ferramenta_processador_ipe.py
import pandas as pd
import zipfile
import io
from datetime import datetime, timezone, date
import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any

# --- Configuração de Caminhos e Imports ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"PROJECT_ROOT ({PROJECT_ROOT}) foi adicionado/confirmado no sys.path para ferramenta_processador_ipe.")
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"AVISO (ferramenta_processador_ipe): __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")

# --- Imports Principais e Fallback de Logger/ToolContext ---
_ToolContext_imported_successfully = False
try:
    from config import settings
    from google.adk.tools.tool_context import ToolContext
    _ToolContext_imported_successfully = True # Marcar como importado com sucesso
    
    if not hasattr(settings, 'logger'): # Fallback do logger se settings não o tiver
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("ferramenta_processador_ipe_fb_logger")
        settings.logger.info("Logger fallback inicializado (settings não tinha logger).")
    print("Módulo config.settings e ADK ToolContext importados com sucesso.")

except ImportError as e:
    print(f"Erro CRÍTICO em ferramenta_processador_ipe.py ao importar: {e}")
    # Fallback para settings se config.settings falhar
    if 'settings' not in locals() and 'settings' not in globals():
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        _fb_logger = logging.getLogger("ferramenta_processador_ipe_NO_SETTINGS_logger")
        # Cria um objeto 'settings' dummy para que o resto do script não quebre imediatamente
        settings = type('SettingsFallback', (), {'logger': _fb_logger})() 
        settings.logger.error(f"Falha ao importar config.settings: {e}. Usando logger de fallback MUITO básico.")
    
    # Define ToolContext como uma classe dummy APENAS se a importação real falhou
    if not _ToolContext_imported_successfully: # Usa a flag para checar
        print("AVISO: google.adk.tools.tool_context.ToolContext não pôde ser importado. Definindo classe ToolContext dummy.")
        class ToolContext: # CORRIGIDO: Nova linha e indentação
            pass
except Exception as e:
    print(f"Erro INESPERADO durante imports iniciais: {e}")
    # Fallbacks similares para settings e ToolContext se necessário para o script carregar
    if 'settings' not in locals() and 'settings' not in globals():
        import logging
        logging.basicConfig(level=logging.INFO)
        _fb_logger = logging.getLogger("ferramenta_processador_ipe_UNEXPECTED_ERROR_logger")
        settings = type('SettingsFallback', (), {'logger': _fb_logger})()
    if 'ToolContext' not in globals() and 'ToolContext' not in locals():
        class ToolContext: pass


# --- Constantes ---
DATA_CVM_RAW_PATH = PROJECT_ROOT / "data" / "raw" / "cvm"
CVM_DATA_SOURCES_CONFIG_FILE = PROJECT_ROOT / "config" / "cvm_data_sources.json" # Para o teste

# === CONFIGURAÇÃO DOS TIPOS DE DOCUMENTO IPE ===
COLUNA_TIPO_DOCUMENTO_IPE = "Categoria" # AJUSTE CONFORME SEU CSV (Categoria, Especie, ou Tipo)
TIPOS_DOCUMENTO_IPE_DESEJADOS = [
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
TITULO_AUSENTE_PADRAO = "Documento CVM (Assunto Não Especificado)"
MAX_TITLE_LENGTH = 250

def parse_cvm_date(date_str: str, time_str: str = None) -> datetime | None:
    # ... (função parse_cvm_date como na última versão, sem alterações) ...
    if not date_str or pd.isna(date_str): return None
    dt_obj = None
    cleaned_date_str = str(date_str).strip()
    cleaned_time_str = str(time_str).strip() if time_str and not pd.isna(time_str) and isinstance(time_str, str) and len(time_str.split(':')) == 3 else '00:00:00'
    try:
        dt_obj = datetime.strptime(f"{cleaned_date_str}T{cleaned_time_str}", "%Y-%m-%dT%H:%M:%S")
        return dt_obj.replace(tzinfo=timezone.utc)
    except ValueError: pass
    try:
        dt_obj = datetime.strptime(f"{cleaned_date_str} {cleaned_time_str}", "%d/%m/%Y %H:%M:%S")
        return dt_obj.replace(tzinfo=timezone.utc)
    except ValueError:
        settings.logger.debug(f"DEBUG_DATE_PARSE: Não foi possível parsear data/hora CVM: data='{date_str}', hora='{time_str}'.")
        return None

def tool_process_cvm_ipe_local(
    caminho_zip_local: str,
    cd_cvm_empresa: str,
    tool_context: ToolContext
    ) -> Dict[str, Any]: # Alterado para retornar Dict
    """
    Processa um arquivo ZIP do IPE da CVM (local) para uma empresa específica,
    extraindo metadados de tipos de documentos relevantes (Fatos Relevantes, Comunicados, etc.)
    que são mais recentes que a última data de processamento armazenada no estado da sessão.

    Args:
        caminho_zip_local (str): Caminho para o arquivo ZIP do IPE.
        cd_cvm_empresa (str): Código CVM da empresa (ex: "9512" para PETR4).
        tool_context (ToolContext): Contexto da ferramenta ADK para acessar/salvar estado de 'last_processed_date'.

    Returns:
        dict: Um dicionário contendo:
              'status': 'success' ou 'error'.
              'novos_documentos': Em caso de sucesso, uma lista de dicionários, 
                                  cada um representando um novo documento regulatório.
              'error_message': Em caso de erro, uma mensagem descritiva.
              'docs_processed_count': Número de documentos que passaram no filtro.
              'docs_returned_count': Número de documentos na lista 'novos_documentos'.
    """
    # ... (lógica de data_ultimo_processado_dt e logs iniciais como antes) ...
    zip_file_name_stem = Path(caminho_zip_local).stem
    state_key_last_processed_date = f"ipe_last_processed_date_{zip_file_name_stem}_{cd_cvm_empresa}"
    data_ultimo_processado_str = tool_context.state.get(state_key_last_processed_date)
    data_ultimo_processado_dt = None
    if data_ultimo_processado_str:
        try:
            data_ultimo_processado_dt = datetime.fromisoformat(data_ultimo_processado_str)
            if data_ultimo_processado_dt.tzinfo is None: data_ultimo_processado_dt = data_ultimo_processado_dt.replace(tzinfo=timezone.utc)
        except ValueError: data_ultimo_processado_dt = None; settings.logger.warning(f"Data inválida no estado para '{state_key_last_processed_date}'.")
    
    settings.logger.info(f"Processando IPE local: '{caminho_zip_local}' para CD_CVM {cd_cvm_empresa}. Última data: {data_ultimo_processado_dt or 'Nenhuma'}")

    novos_documentos = []
    data_mais_recente_nesta_rodada = data_ultimo_processado_dt
    docs_processed_count = 0

    try:
        with zipfile.ZipFile(caminho_zip_local, 'r') as zip_ref:
            ano_do_zip = ''.join(filter(str.isdigit, Path(caminho_zip_local).name))
            csv_principal_ipe = f"ipe_cia_aberta_{ano_do_zip}.csv"
            
            if csv_principal_ipe not in zip_ref.namelist():
                msg = f"CSV principal '{csv_principal_ipe}' não encontrado no ZIP '{caminho_zip_local}'."
                settings.logger.error(msg)
                return {"status": "error", "error_message": msg, "docs_processed_count": 0, "docs_returned_count": 0}

            settings.logger.debug(f"DEBUG_IPE: Processando CSV principal: '{csv_principal_ipe}'")
            try:
                with zip_ref.open(csv_principal_ipe) as csv_file_in_zip:
                    # ... (lógica de decode e pd.read_csv como antes) ...
                    csv_content_bytes = csv_file_in_zip.read(); 
                    try: csv_content_str = csv_content_bytes.decode('latin-1')
                    except UnicodeDecodeError: csv_content_str = csv_content_bytes.decode('utf-8', errors='replace')
                    df = pd.read_csv(io.StringIO(csv_content_str), sep=';', dtype={'Codigo_CVM': str, 'Protocolo_Entrega': str, 'Versao': str}, low_memory=False)

                # ... (logs de shape, colunas, amostras como antes) ...
                if 'Codigo_CVM' not in df.columns or COLUNA_TIPO_DOCUMENTO_IPE not in df.columns: #... (erro) ...
                     return {"status": "error", "error_message": "Colunas essenciais faltando no CSV IPE.", "docs_processed_count": 0, "docs_returned_count": 0}


                df[COLUNA_TIPO_DOCUMENTO_IPE] = df[COLUNA_TIPO_DOCUMENTO_IPE].astype(str).str.strip()
                tipos_desejados_lower = [str(t).strip().lower() for t in TIPOS_DOCUMENTO_IPE_DESEJADOS]

                df_empresa_filtrada = df[
                    (df['Codigo_CVM'] == str(cd_cvm_empresa)) &
                    (df[COLUNA_TIPO_DOCUMENTO_IPE].str.lower().isin(tipos_desejados_lower))
                ]
                docs_processed_count = len(df_empresa_filtrada)
                settings.logger.info(f"DEBUG_IPE: Documentos da empresa {cd_cvm_empresa} que correspondem aos tipos desejados: {docs_processed_count}")

                for _, row in df_empresa_filtrada.iterrows():
                    # ... (lógica de parse_cvm_date para data_documento_dt como antes) ...
                    data_entrega_str = row.get('Data_Entrega'); hora_entrega_str = None # Assumindo sem HORA_ENTREG no IPE
                    data_documento_dt = parse_cvm_date(data_entrega_str, hora_entrega_str)
                    if not data_documento_dt: continue
                    if data_ultimo_processado_dt and data_documento_dt <= data_ultimo_processado_dt: continue
                    if data_mais_recente_nesta_rodada is None or data_documento_dt > data_mais_recente_nesta_rodada:
                        data_mais_recente_nesta_rodada = data_documento_dt
                    
                    # ... (lógica de geração de title_para_doc como antes) ...
                    assunto_original = str(row.get('Assunto', '')).strip()
                    categoria_doc_val = str(row.get(COLUNA_TIPO_DOCUMENTO_IPE, '')).strip()
                    data_referencia_str_val = str(row.get('Data_Referencia', '')).strip()
                    title_para_doc = ""
                    if assunto_original and assunto_original.lower() != 'nan' and len(assunto_original) > 3: title_para_doc = assunto_original
                    else:
                        title_para_doc = f"{categoria_doc_val}" 
                        data_referencia_dt_val = parse_cvm_date(data_referencia_str_val)
                        if data_referencia_dt_val and data_documento_dt and data_referencia_dt_val.date() != data_documento_dt.date():
                            title_para_doc += f" (Ref.: {data_referencia_dt_val.strftime('%Y-%m-%d')})"
                        if not assunto_original or assunto_original.lower() == 'nan': title_para_doc += f" - {TITULO_AUSENTE_PADRAO}"
                    title_para_doc = title_para_doc[:MAX_TITLE_LENGTH]

                    doc_info = {
                        "title": title_para_doc,
                        "publication_date_iso": data_documento_dt.isoformat(),
                        "document_url": str(row.get('Link_Download', '')).strip(),
                        "document_type": categoria_doc_val, 
                        "protocol_id": str(row.get('Protocolo_Entrega', '')).strip(),
                        "version": str(row.get('Versao', '1')).strip(),
                        "company_cvm_code": str(row.get('Codigo_CVM')).strip(),
                        "company_name": str(row.get('Nome_Companhia', '')).strip(),
                        "reference_date_iso": (parse_cvm_date(data_referencia_str_val) or data_documento_dt).isoformat(),
                        "submission_type": str(row.get('Tipo_Apresentacao', '')).strip(),
                        "cvm_categoria_original": str(row.get('Categoria', '')).strip(),
                        "cvm_tipo_original": str(row.get('Tipo', '')).strip(),
                        "cvm_especie_original": str(row.get('Especie', '')).strip(),
                        "source_sub_type": csv_principal_ipe,
                        "source_main_file": Path(caminho_zip_local).name,
                        "source": "CVM_IPE"
                    }
                    novos_documentos.append(doc_info)
                    # settings.logger.info(f"Novo doc CVM IPE para {cd_cvm_empresa}: '{doc_info['title'][:50]}...' ({doc_info['publication_date_iso']})")
            # ... (resto do try-except para pd.errors.EmptyDataError e Exception as e_csv) ...
            except pd.errors.EmptyDataError: settings.logger.info(f"CSV '{csv_principal_ipe}' vazio.")
            except Exception as e_csv: settings.logger.error(f"Erro ao processar CSV '{csv_principal_ipe}': {e_csv}", exc_info=True)
        
        if data_mais_recente_nesta_rodada and \
           (data_ultimo_processado_dt is None or data_mais_recente_nesta_rodada > data_ultimo_processado_dt) :
            tool_context.state[state_key_last_processed_date] = data_mais_recente_nesta_rodada.isoformat()
            settings.logger.info(f"Estado '{state_key_last_processed_date}' ATUALIZADO para: {tool_context.state[state_key_last_processed_date]}")

    # ... (resto do try-except para FileNotFoundError, BadZipFile, Exception as e) ...
    except FileNotFoundError: #...
        return {"status": "error", "error_message": f"Arquivo ZIP não encontrado: {caminho_zip_local}", "docs_processed_count": 0, "docs_returned_count": 0}
    except zipfile.BadZipFile: #...
        return {"status": "error", "error_message": f"Arquivo ZIP corrompido: {caminho_zip_local}", "docs_processed_count": 0, "docs_returned_count": 0}
    except Exception as e: #...
        return {"status": "error", "error_message": f"Erro inesperado IPE: {e}", "docs_processed_count": 0, "docs_returned_count": 0}


    settings.logger.info(f"Processamento de '{caminho_zip_local}' concluído. {len(novos_documentos)} novos docs encontrados de {docs_processed_count} filtrados.")
    return {
        "status": "success",
        "novos_documentos": novos_documentos,
        "docs_processed_count": docs_processed_count,
        "docs_returned_count": len(novos_documentos)
    }

# --- Bloco de Teste Standalone ---
if __name__ == '__main__':
    # ... (bloco if __name__ == '__main__': como na sua última versão funcional,
    #      lembrando de usar cd_cvm_petr4_teste = "9512"
    #      e de ajustar COLUNA_TIPO_DOCUMENTO_IPE e TIPOS_DOCUMENTO_IPE_DESEJADOS no topo do script.)
    #      Agora ele espera um dicionário da função.
    # Exemplo de como o bloco de teste ficaria, simplificado:
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("test_processador_ipe_main")

    settings.logger.info("--- Teste Standalone da ferramenta_processador_ipe ---")
    
    test_year = datetime.now().year 
    cd_cvm_petr4_teste = "9512" 
    settings.logger.info(f"Usando CD_CVM '{cd_cvm_petr4_teste}' para este teste e ano {test_year}.")
        
    caminho_zip_teste_str = str(DATA_CVM_RAW_PATH / "IPE" / str(test_year) / f"ipe_cia_aberta_{test_year}.zip")

    class MockToolContext:
        def __init__(self): self.state = {}; self.agent_name = "test_agent_ipe_processor"
    mock_ctx = MockToolContext()

    if Path(caminho_zip_teste_str).exists():
        settings.logger.info(f"Iniciando processamento do arquivo de teste: {caminho_zip_teste_str}")
        
        resultado_processamento = tool_process_cvm_ipe_local(caminho_zip_teste_str, cd_cvm_petr4_teste, mock_ctx)
        
        print(f"\n--- Resultado do Processamento (Status: {resultado_processamento.get('status')}) ---")
        if resultado_processamento.get("status") == "success":
            documentos_encontrados = resultado_processamento.get("novos_documentos", [])
            print(f"--- {len(documentos_encontrados)} NOVOS DOCUMENTOS ENCONTRADOS PARA CD_CVM {cd_cvm_petr4_teste} ---")
            for idx, doc in enumerate(documentos_encontrados[:3]): # Imprime os primeiros 3
                print(f"\n--- Documento {idx+1} ---")
                print(json.dumps(doc, indent=2, ensure_ascii=False))
            
            chave_estado_final = f"ipe_last_processed_date_{Path(caminho_zip_teste_str).stem}_{cd_cvm_petr4_teste}"
            print(f"\nEstado final do ToolContext para '{chave_estado_final}': {mock_ctx.state.get(chave_estado_final)}")
            print(f"Total de documentos filtrados inicialmente para a empresa e tipo: {resultado_processamento.get('docs_processed_count')}")
            print(f"Total de documentos retornados (após filtro de data): {resultado_processamento.get('docs_returned_count')}")
        else:
            print(f"Erro no processamento: {resultado_processamento.get('error_message')}")
    else:
        print(f"Arquivo ZIP de teste IPE não encontrado em '{caminho_zip_teste_str}'. Execute o downloader primeiro.")