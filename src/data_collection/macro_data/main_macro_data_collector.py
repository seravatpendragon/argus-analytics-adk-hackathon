# src/data_collection/macro_data/main_macro_data_collector.py
# -*- coding: utf-8 -*-

import sys
import os

# Adiciona o diretório raiz do projeto ao sys.path para encontrar config e outros módulos src
project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root_path not in sys.path:
    sys.path.insert(0, project_root_path) # Adiciona a raiz ao path

# Agora o import de 'config.settings' deve funcionar
try:
    from config import settings
    from src.data_collection.macro_data import bcb_collector
    from src.data_collection.macro_data import eia_collector
    from src.data_collection.macro_data import fred_collector
    from src.data_collection.macro_data import ibge_collector
    from src.data_collection.macro_data import fgv_collector

except ImportError as e:
    print(f"Erro CRÍTICO em main_macro_data_collector.py ao importar módulos: {e}")
    sys.exit(1)
except ModuleNotFoundError as e: # Especificamente para módulos não encontrados
    print(f"Erro CRÍTICO: Módulo não encontrado em main_macro_data_collector.py: {e}")
    print("Verifique se o script coletor referenciado (ex: bcb_collector.py) existe na pasta correta.")
    sys.exit(1)


def run_all_macro_collectors():
    """
    Orquestra a execução de todos os coletores de dados macroeconômicos.
    """
    settings.logger.info("=====================================================================")
    settings.logger.info("INICIANDO O COLETOR PRINCIPAL DE DADOS MACROECONÔMICOS...")
    settings.logger.info("=====================================================================")
    
    # --- Coleta de Dados do BCB (Banco Central do Brasil) ---
    try:
        settings.logger.info("---------------------------------------------------------------------")
        settings.logger.info("Iniciando coleta de dados do BCB (SGS)...")
        bcb_collector.collect_bcb_data() # Assume que bcb_collector.py tem uma função collect_bcb_data()
        settings.logger.info("Coleta de dados do BCB (SGS) concluída.")
        settings.logger.info("---------------------------------------------------------------------")
    except AttributeError: # Se bcb_collector foi importado mas não tem collect_bcb_data
        settings.logger.error("Erro: Função 'collect_bcb_data' não encontrada em bcb_collector.py.")
    except Exception as e:
        settings.logger.error(f"Erro crítico durante a coleta de dados do BCB: {e}", exc_info=True)

    # --- Coleta de Dados do FRED (Federal Reserve Economic Data) ---
    # Descomente e ajuste quando fred_collector.py estiver pronto
    if hasattr(settings, 'FRED_API_KEY') and settings.FRED_API_KEY:
        try:
            settings.logger.info("---------------------------------------------------------------------")
            settings.logger.info("Iniciando coleta de dados do FRED...")
            fred_collector.collect_fred_data() 
            settings.logger.info("Coleta de dados do FRED (ainda não totalmente implementada).")
            settings.logger.info("---------------------------------------------------------------------")
        except AttributeError:
             settings.logger.error("Erro: Função 'collect_fred_data' não encontrada em fred_collector.py.")
        except Exception as e:
            settings.logger.error(f"Erro crítico durante a coleta de dados do FRED: {e}", exc_info=True)
    else:
        settings.logger.info("Chave API FRED não configurada em settings.py. Pulando coleta do FRED.")


    # --- Coleta de Dados do IBGE (SIDRA) ---
    # Descomente e ajuste quando ibge_collector.py estiver pronto
    try:
        settings.logger.info("---------------------------------------------------------------------")
        settings.logger.info("Iniciando coleta de dados do IBGE (SIDRA)...")
        ibge_collector.collect_ibge_data()
        settings.logger.info("Coleta de dados do IBGE (SIDRA) (ainda não totalmente implementada).")
        settings.logger.info("---------------------------------------------------------------------")
    except AttributeError:
         settings.logger.error("Erro: Função 'collect_ibge_data' não encontrada em ibge_collector.py.")
    except Exception as e:
        settings.logger.error(f"Erro crítico durante a coleta de dados do IBGE: {e}", exc_info=True)

    # --- Coleta de Dados da EIA (U.S. Energy Information Administration) ---
    # Descomente e ajuste quando eia_collector.py estiver pronto
    if hasattr(settings, 'EIA_API_KEY') and settings.EIA_API_KEY:
        try:
            settings.logger.info("---------------------------------------------------------------------")
            settings.logger.info("Iniciando coleta de dados da EIA...")
            eia_collector.collect_eia_data()
            settings.logger.info("Coleta de dados da EIA (ainda não totalmente implementada).")
            settings.logger.info("---------------------------------------------------------------------")
        except AttributeError:
             settings.logger.error("Erro: Função 'collect_eia_data' não encontrada em eia_collector.py.")
        except Exception as e:
            settings.logger.error(f"Erro crítico durante a coleta de dados da EIA: {e}", exc_info=True)
    else:
        settings.logger.info("Chave API EIA não configurada em settings.py. Pulando coleta da EIA.")

    # --- Coleta de Dados da FGV CSV ---
    try:
        settings.logger.info("---------------------------------------------------------------------")
        settings.logger.info("Iniciando coleta de dados da FGV...")
        fgv_collector.collect_fgv_data()
        settings.logger.info("Coleta de dados da FGV (ainda não totalmente implementada).")
        settings.logger.info("---------------------------------------------------------------------")
    except AttributeError:
            settings.logger.error("Erro: Função 'collect_fgv_data' não encontrada em fgv_collector.py.")
    except Exception as e:
        settings.logger.error(f"Erro crítico durante a coleta de dados da FGV: {e}", exc_info=True)



    settings.logger.info("=====================================================================")
    settings.logger.info("COLETOR PRINCIPAL DE DADOS MACROECONÔMICOS FINALIZADO.")
    settings.logger.info("=====================================================================")

if __name__ == "__main__":
    # Este bloco permite que você rode o coletor macro diretamente
    # python src/data_collection/macro_data/main_macro_data_collector.py
    run_all_macro_collectors()