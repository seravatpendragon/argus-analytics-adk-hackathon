# src/data_collection/market_data/main_market_data_collector.py

import sys
import os

# Adiciona o diretório raiz do projeto ao sys.path
project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root_path not in sys.path:
    sys.path.append(project_root_path)

try:
    from config import settings
    # Importa a função principal do coletor yfinance
    from src.data_collection.market_data.yfinance_collector import collect_yfinance_data
except ImportError as e:
    print(f"Erro em main_market_data_collector.py ao importar: {e}")
    sys.exit(1)

def main():
    settings.logger.info("Iniciando o Coletor Principal de Dados de Mercado...")
    
    # --- Coleta de Dados do Yahoo Finance ---
    try:
        settings.logger.info("Iniciando coleta de dados do Yahoo Finance...")
        collect_yfinance_data()
        settings.logger.info("Coleta de dados do Yahoo Finance concluída.")
    except Exception as e:
        settings.logger.error(f"Erro durante a coleta de dados do Yahoo Finance: {e}", exc_info=True)

    # --- Aqui você pode adicionar chamadas para outros coletores de dados de mercado no futuro ---
    # Ex: collect_b3_website_data()
    # Ex: collect_alpha_vantage_data()

    settings.logger.info("Coletor Principal de Dados de Mercado finalizado.")

if __name__ == "__main__":
    # Antes de rodar, garanta que a tabela Companies tenha PETR4.SA
    # Exemplo de como adicionar PETR4 (idealmente em um script de seed ou via UI/outro processo)
    # from src.database.db_utils import get_db_session
    # from src.database.create_db_tables import Company, Segment # Supondo que Segment exista com ID 1
    # temp_session = get_db_session()
    # petr4 = temp_session.query(Company).filter_by(ticker="PETR4.SA").first()
    # if not petr4:
    #     # Você precisaria do segment_id correto para a PETR4
    #     # Este é apenas um exemplo, o segment_id=1 é placeholder
    #     # Idealmente, busque o segment_id com base no nome do segmento da PETR4
    #     # ou tenha um script de setup que popule Companies e Segments.
    #     segment_petr4 = temp_session.query(Segment).filter(...).first() # Busque o segmento correto
    #     if segment_petr4:
    #         new_petr4 = Company(name="Petrobras PN", ticker="PETR4.SA", segment_id=segment_petr4.segment_id)
    #         temp_session.add(new_petr4)
    #         temp_session.commit()
    #         settings.logger.info("PETR4.SA adicionada à tabela Companies (exemplo).")
    #     else:
    #         settings.logger.error("Segmento da PETR4 não encontrado para cadastro inicial. Adicione manualmente ou via seed.")
    # temp_session.close()

    main()