import pandas as pd
from sqlalchemy.orm import Session
from src.database.db_utils import get_db_session, get_analyses_for_topic

class AnalysisDataHandler:
    """
    Uma classe para buscar, carregar e pré-processar os dados de análise
    do banco de dados para o dashboard.
    """
    def __init__(self, topic: str, days_back: int = 30):
        self.topic = topic
        self.days_back = days_back
        self.raw_analyses = self._load_data()
        self.df = self._create_dataframe()

    def _load_data(self) -> list[dict]:
        """Busca os dados brutos de análise do banco de dados."""
        with get_db_session() as session:
            return get_analyses_for_topic(session, self.topic, self.days_back)

    def _create_dataframe(self) -> pd.DataFrame:
        """Transforma a lista de JSONs em um DataFrame do Pandas para fácil manipulação."""
        if not self.raw_analyses:
            return pd.DataFrame()

        # Extrai e achata os dados que queremos para o DataFrame
        flat_data = []
        for analysis in self.raw_analyses:
            # Adicione a extração de outros campos aqui conforme necessário
            sentiment_data = analysis.get("analise_sentimento", {})

            # Busca a data de publicação original da notícia associada
            # (Esta lógica precisaria ser adicionada a get_analyses_for_topic)
            # Por agora, usaremos um placeholder.

            flat_data.append({
                "sentiment_score": sentiment_data.get("sentiment_score"),
                # "published_at": analysis.get("publication_date") 
            })

        df = pd.DataFrame(flat_data)
        # Converte a coluna de data para o tipo datetime, se existir
        # if "published_at" in df.columns:
        #     df['published_at'] = pd.to_datetime(df['published_at'])
        return df

    def get_sentiment_over_time(self) -> pd.DataFrame:
        """Prepara os dados para o gráfico de linha de sentimento."""
        if self.df.empty or "sentiment_score" not in self.df.columns:
            return pd.DataFrame()

        # Por enquanto, retorna a série de scores. Aprimoraremos com datas.
        return self.df[['sentiment_score']]