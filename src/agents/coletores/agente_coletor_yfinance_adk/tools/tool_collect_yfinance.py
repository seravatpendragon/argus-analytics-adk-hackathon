import json
from pathlib import Path
import yfinance as yf
import pandas as pd
from datetime import datetime
from config import settings
from sqlalchemy.orm import Session
# Garanta que todas as funções de DB necessárias estão importadas
from src.database.db_utils import get_db_session, get_or_create_indicator, batch_upsert_indicator_values, get_company_id_for_ticker
# A classe que formata os dados
from src.data_collection.market_data.yfinance_collector import YFinanceDataParser

def load_json_config(config_path: Path) -> list:
    """Carrega um arquivo de configuração JSON que se espera ser uma lista."""
    if not config_path.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def tool_collect_yfinance_data() -> dict:
    """
    Coleta todos os tipos de dados do Yahoo Finance, cria os metadados dos indicadores
    e persiste os valores no banco de dados.
    """
    settings.logger.info("Ferramenta 'tool_collect_yfinance_data' (versão final) iniciada...")
    db_session: Session | None = None
    try:
        db_session = get_db_session()
        config_path = Path(settings.BASE_DIR) / "config" / "yfinance_indicators_config.json"
        config_list = load_json_config(config_path)
        
        parser = YFinanceDataParser()
        all_values_to_persist = []

        # 1. Agrupa todos os tickers para um download eficiente em lote
        tickers_to_fetch = list(set(
            conf.get("params", {}).get("ticker_symbol")
            for conf in config_list if conf.get("enabled") and conf.get("params", {}).get("ticker_symbol")
        ))
        if not tickers_to_fetch:
            return {"status": "success", "message": "Nenhum ticker habilitado para coleta."}

        settings.logger.info(f"Fazendo download em lote para {len(tickers_to_fetch)} tickers...")
        yf_tickers_obj = yf.Tickers(" ".join(tickers_to_fetch))
        settings.logger.info("Download em lote concluído.")

        # 2. Itera na configuração para processar cada indicador
        for conf in config_list:
            if not conf.get("enabled"):
                continue

            # ETAPA ESSENCIAL QUE ESTAVA FALTANDO:
            # Para cada indicador na config, primeiro garantimos que ele exista na tabela
            # de metadados 'EconomicIndicators' e pegamos seu ID.
            indicator_obj = get_or_create_indicator(
                session=db_session,
                name=conf["db_indicator_name"],
                source_name=conf.get("source_api", "YFINANCE"),
                indicator_type=conf["db_indicator_type"],
                frequency=conf["db_indicator_frequency"],
                unit=conf["db_indicator_unit"]
            )
            if not indicator_obj:
                settings.logger.warning(f"Não foi possível criar metadado para o indicador: {conf['db_indicator_name']}")
                continue

            ticker_symbol = conf.get("params", {}).get("ticker_symbol")
            ticker_data = yf_tickers_obj.tickers.get(ticker_symbol)
            if not ticker_data:
                continue

            data_type = conf.get("yfinance_data_type", "").upper()
            prepared_data = []

            # Delega a formatação para o Parser especialista
            if data_type == "INFO":
                key_from_info = conf.get("params", {}).get("value_column_yfinance")
                prepared_data = parser.parse_info_data(ticker_data.info, key_from_info)
            elif data_type in ["HISTORY", "DIVIDENDS", "SPLITS"]:
                # ... (lógica para chamar o parse_timeseries_data como antes)
                raw_df = pd.DataFrame()
                if data_type == "HISTORY": raw_df = ticker_data.history(period="5y", interval="1d")
                elif data_type == "DIVIDENDS": raw_df = ticker_data.dividends.to_frame()
                elif data_type == "SPLITS": raw_df = ticker_data.splits.to_frame()
                
                value_col = conf.get("params", {}).get("value_column_yfinance", raw_df.columns[0] if not raw_df.empty else None)
                if value_col:
                    prepared_data = parser.parse_timeseries_data(raw_df, value_col)

            # Vincula o ID do indicador e o ID da empresa a cada ponto de dado
            company_id = get_company_id_for_ticker(db_session, ticker_symbol) if ticker_symbol else None
            for data_point in prepared_data:
                data_point["indicator_id"] = indicator_obj.indicator_id
                data_point["company_id"] = company_id
                all_values_to_persist.append(data_point)

        if not all_values_to_persist:
            return {"status": "success", "message": "Nenhum dado novo para inserir."}
            
        num_inserted = batch_upsert_indicator_values(db_session, all_values_to_persist)
        db_session.commit()
        
        return {"status": "success", "message": f"Coleta YFinance concluída. {num_inserted} novos pontos de dados inseridos."}

    except Exception as e:
        if db_session: db_session.rollback()
        settings.logger.error(f"Erro CRÍTICO na ferramenta YFinance: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        if db_session: db_session.close()