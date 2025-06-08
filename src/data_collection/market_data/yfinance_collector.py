import pandas as pd
from datetime import datetime
from config import settings

class YFinanceDataParser:
    """
    Classe com métodos estáticos para FORMATAR dados brutos do yfinance
    para o padrão do nosso banco de dados.
    """
    @staticmethod
    def parse_timeseries_data(df: pd.DataFrame, value_column_name: str) -> list[dict]:
        """ Formata um DataFrame de série temporal (History, Dividends, Splits). """
        if df is None or df.empty or value_column_name not in df.columns:
            return []
        
        data_points = []
        # Renomeia a coluna alvo para 'value' para um acesso padronizado
        df_renamed = df.rename(columns={value_column_name: 'value'})
        for date_index, row in df_renamed.iterrows():
            try:
                # Garante que o índice seja um timestamp e o valor seja um float
                data_points.append({
                    "effective_date": pd.to_datetime(date_index).date(),
                    "value_numeric": float(row['value'])
                })
            except (ValueError, TypeError):
                continue
        return data_points

    @staticmethod
    def parse_info_data(info_dict: dict, key_from_info: str) -> list[dict]:
        """ Formata um indicador específico do dicionário .info. """
        data_points = []
        # Checa se a chave existe e se o valor não é nulo
        if key_from_info in info_dict and info_dict[key_from_info] is not None:
            try:
                value = float(info_dict[key_from_info])
                data_points.append({
                    "effective_date": datetime.now().date(),
                    "value_numeric": value
                })
            except (ValueError, TypeError):
                settings.logger.warning(f"Não foi possível converter o valor para a chave de info '{key_from_info}'.")
        return data_points