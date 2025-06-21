# Em src/data_analysis/data_handler.py
import pandas as pd
import json
import numpy as np
from datetime import datetime

import pytz
from src.database.db_utils import get_db_session, get_all_analyzed_articles
from config import settings
import re

class AnalysisDataHandler:
    def __init__(self):
        settings.logger.info("Inicializando e processando dados para o dashboard...")
        self.df = self._load_and_process_data()
        if not self.df.empty:
            settings.logger.info(f"DataFrame carregado e processado com {len(self.df)} registros.")

    def _load_and_process_data(self) -> pd.DataFrame:
        with get_db_session() as session:
            articles = get_all_analyzed_articles(session)
        if not articles: return pd.DataFrame()
        
        df = pd.DataFrame(articles)

        # 1. Parsing do JSON de análise (robusto contra erros)
        def parse_json_col(data):
            if isinstance(data, str): return json.loads(data)
            return data if isinstance(data, dict) else {}
        
        llm_analysis_df = pd.json_normalize(df['llm_analysis'].apply(parse_json_col), sep='_')
        df = df.join(llm_analysis_df)

        # 2. Preparação das colunas com os nomes corretos pós-normalização
        numeric_cols_map = {
            'sentiment_score': 'analise_sentimento_sentiment_score',
            'shannon_entropy': 'analise_quantitativa_shannon_relative_entropy',
            'financial_relevance': 'analise_entidades_relevancia_mercado_financeiro',
            'craap_score': 'source_base_credibility' # <<< USANDO A COLUNA DIRETA
        }

        for standard_name, json_name in numeric_cols_map.items():
            if json_name not in df.columns: df[json_name] = 0.0
            df[standard_name] = pd.to_numeric(df[json_name], errors='coerce').fillna(0.0)
        
        # 3. CÁLCULO CORRETO E FINAL DO PESO DE RELEVÂNCIA
        df['relevance_weight'] = (
            df['craap_score'] *
            df['shannon_entropy'] *
            df['financial_relevance'] 
        )

        # 4. Processamento de Entidades e Datas
        df['published_at'] = pd.to_datetime(df['published_at'], errors='coerce')
        df = df.dropna(subset=['published_at'])
        
        entity_col = 'analise_entidades_entidades_identificadas'
        if entity_col not in df.columns: df[entity_col] = [[] for _ in range(len(df))]
        else: df[entity_col] = df[entity_col].apply(lambda d: d if isinstance(d, list) else [])
        
        df['is_macro'] = df[entity_col].apply(lambda ents: any(e.get('tipo') == 'MACROECONOMICO' for e in ents))
        df['is_company_petrobras'] = df[entity_col].apply(lambda ents: any(e.get('tipo') == 'EMPRESA' and 'petrobras' in e.get('nome_sugerido_padrao', '').lower() for e in ents))
        df['is_segment_oil_gas'] = df[entity_col].apply(lambda ents: any(any(keyword in e.get('nome_sugerido_padrao', '').lower() for keyword in ['petróleo', 'gás', 'gas', 'biocombustíveis']) for e in ents))
        
        return df
    
    # ... O resto das funções do handler (get_filtered_data, etc.) continuam as mesmas ...
    def get_filtered_data(self, filter_name: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        if self.df.empty:
            return pd.DataFrame()
        
        if self.df['published_at'].dt.tz is not None:
            if start_date.tzinfo is None:
                start_date = pytz.timezone('America/Sao_Paulo').localize(start_date)
            if end_date.tzinfo is None:
                end_date = pytz.timezone('America/Sao_Paulo').localize(end_date)
            start_date = start_date.astimezone(self.df['published_at'].dt.tz)
            end_date = end_date.astimezone(self.df['published_at'].dt.tz)

        df_filtered_by_date = self.df[(self.df['published_at'] >= start_date) & (self.df['published_at'] <= end_date)]

        if filter_name == "Empresa: Petrobras":
            return df_filtered_by_date[df_filtered_by_date['is_company_petrobras']].copy()
        elif filter_name == "Segmento: Petróleo, Gás & Biocombustíveis":
            return df_filtered_by_date[df_filtered_by_date['is_segment_oil_gas']].copy()
        elif filter_name == "Tema: Macroeconômico":
            return df_filtered_by_date[df_filtered_by_date['is_macro']].copy()
        
        return pd.DataFrame()