import pandas as pd
from config import settings
from pathlib import Path

logger = settings.logger

class FGVCollector:
    """
    O "Engenheiro Especialista" em ler arquivos CSV de indicadores da FGV.
    """
    def __init__(self):
        # O caminho para a pasta de dados é relativo à raiz do projeto
        try:
            self.data_path = Path(__file__).resolve().parent.parent.parent / "data" / "config_input"
        except NameError:
            self.data_path = Path.cwd() / "data" / "config_input"

    def get_series_from_csv(self, task: dict) -> pd.DataFrame:
        """
        Lê um arquivo CSV e extrai uma série temporal com base em uma tarefa do manifesto.
        """
        params = task.get("params", {})
        csv_filename = params.get("csv_filename")
        date_col = params.get("date_column_name_in_csv")
        value_col = params.get("value_column_name_in_csv")

        if not all([csv_filename, date_col, value_col]):
            logger.error(f"Task FGV mal configurada. Faltando um dos parâmetros de CSV: {task}")
            return pd.DataFrame()

        file_path = self.data_path / csv_filename
        logger.info(f"FGVCollector: Lendo arquivo '{file_path}'")

        try:
            df = pd.read_csv(file_path)
            
            # Verifica se as colunas necessárias existem
            if date_col not in df.columns or value_col not in df.columns:
                logger.error(f"Colunas '{date_col}' ou '{value_col}' não encontradas no arquivo {csv_filename}.")
                return pd.DataFrame()

            # Seleciona, renomeia e formata os dados
            series_df = df[[date_col, value_col]].copy()
            series_df.rename(columns={date_col: 'date', value_col: 'value'}, inplace=True)
            
            series_df['date'] = pd.to_datetime(series_df['date'], errors='coerce')
            series_df['value'] = pd.to_numeric(series_df['value'], errors='coerce')
            
            series_df.dropna(subset=['date', 'value'], inplace=True)

            logger.info(f"FGVCollector: {len(series_df)} registros encontrados para o indicador '{task['db_indicator_name']}'.")
            return series_df

        except FileNotFoundError:
            logger.error(f"Arquivo CSV não encontrado: {file_path}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Erro ao processar o arquivo CSV da FGV '{csv_filename}': {e}", exc_info=True)
            return pd.DataFrame()