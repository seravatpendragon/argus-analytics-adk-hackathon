# Em: dashboard.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import pytz
import numpy as np
from src.data_analysis.data_handler import AnalysisDataHandler
from datetime import datetime, timedelta

# --- Configuração da Página ---
st.set_page_config(layout="wide", page_title="Argus Analytics - Sentimento de Mercado")

# --- Funções de Cache e Lógica ---

@st.cache_resource(ttl=600)
def load_data_handler():
    """Carrega e cacheia o handler para evitar reprocessamento a cada interação."""
    handler = AnalysisDataHandler()
    return handler

def calculate_weighted_avg(df: pd.DataFrame):
    """Calcula apenas a média ponderada para um dataframe."""
    if df.empty:
        return 0
    
    # Usando os nomes padronizados das colunas do handler
    sentiment_col = 'sentiment_score'
    weight_col = 'relevance_weight'
    
    if sentiment_col not in df.columns or weight_col not in df.columns:
        st.error(f"Coluna de '{sentiment_col}' ou '{weight_col}' não encontrada no DataFrame.")
        return 0

    weighted_sum = (df[sentiment_col] * df[weight_col]).sum()
    total_weight = df[weight_col].sum()
    
    # Se todos os pesos forem 0, a média ponderada é igual à simples
    if total_weight == 0:
        return df[sentiment_col].mean()
        
    return weighted_sum / total_weight

def display_sentiment_timeseries_chart(df: pd.DataFrame):
    """
    Cria e exibe o gráfico de série temporal usando a abordagem de resample correta.
    """
    st.subheader("Evolução do Sentimento no Tempo")

    # Garante que a coluna de data é do tipo correto
    df_chart = df.copy()
    df_chart['published_at'] = pd.to_datetime(df_chart['published_at'])

    # --- LÓGICA DE AGREGAÇÃO CORRIGIDA ---
    # 1. Define uma função que opera em um grupo (um mini-df diário)
    def calculate_daily_metrics(group):
        if group.empty:
            # Retorna uma Series com NaNs se o dia não tiver notícias
            return pd.Series({'simple_avg': np.nan, 'weighted_avg': np.nan})
        
        simple_avg = group['sentiment_score'].mean()
        
        # Usa a função que já criamos para o cálculo ponderado
        weighted_avg = calculate_weighted_avg(group)
        
        return pd.Series({'simple_avg': simple_avg, 'weighted_avg': weighted_avg})

    # 2. Aplica a função a cada grupo diário gerado pelo resample
    # O resample aqui opera no DataFrame inteiro, passando cada grupo para o .apply()
    daily_sentiment = df_chart.resample('D', on='published_at').apply(calculate_daily_metrics)
    daily_sentiment.dropna(inplace=True) # Remove os dias que não tiveram notícias

    if daily_sentiment.empty:
        st.warning("Não há dados suficientes no período para gerar um gráfico de evolução.")
        return

    # 3. Cria a figura com Plotly (lógica de plotagem inalterada)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily_sentiment.index, 
        y=daily_sentiment['simple_avg'],
        mode='lines+markers', name='Sentimento Simples', 
        line=dict(color='lightblue', dash='dash')
    ))
    fig.add_trace(go.Scatter(
        x=daily_sentiment.index, 
        y=daily_sentiment['weighted_avg'],
        mode='lines+markers', name='Sentimento Ponderado (Argus)', 
        line=dict(color='royalblue')
    ))

    fig.update_layout(
        title_text='Sentimento Diário: Simples vs. Ponderado',
        xaxis_title="Data",
        yaxis_title="Score de Sentimento",
        yaxis_range=[-1, 1],
        legend_title="Tipo de Média",
        height=400
    )
    st.plotly_chart(fig, use_container_width=True)

def display_detailed_news_table(df: pd.DataFrame):
    """Cria e exibe a tabela detalhada com as notícias filtradas."""
    with st.expander("Ver tabela detalhada das notícias analisadas", expanded=False):
        cols_map = {
            'published_at': 'Data', 'title': 'Título', 'sentiment_score': 'Sentimento',
            'craap_score': 'Credibilidade', 'shannon_entropy': 'Densidade',
            'financial_relevance': 'Relevância Fin.', 'relevance_weight': 'Peso Final'
        }
        display_cols = [col for col in cols_map.keys() if col in df.columns]
        display_df = df[display_cols].rename(columns=cols_map)
        
        st.dataframe(display_df.sort_values(by='Data', ascending=False),
                     column_config={
                         "Data": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY HH:mm"),
                         "Sentimento": st.column_config.NumberColumn(format="%.3f"),
                         "Credibilidade": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=1),
                         "Densidade": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=1),
                         "Relevância Fin.": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=1),
                         "Peso Final": st.column_config.NumberColumn(format="%.3f"),
                     }, use_container_width=True)

# --- UI Principal ---
st.title("🧠 Argus Analytics: Painel de Sentimento de Mercado")
handler = load_data_handler()

# --- Barra Lateral de Filtros ---
with st.sidebar:
    st.header("Filtros de Análise")
    TIMEZONE = pytz.timezone('America/Sao_Paulo')
    filter_options = ["Empresa: Petrobras", "Segmento: Petróleo, Gás & Biocombustíveis", "Tema: Macroeconômico"]
    selected_filter = st.selectbox("Selecione o filtro:", options=filter_options)
    time_range_option = st.selectbox("Recorte Temporal", ["Últimos 7 dias", "Últimos 30 dias", "Últimos 3 meses", "Período Personalizado"])
    
    end_date_naive = datetime.now()
    if time_range_option == "Período Personalizado":
        c1, c2 = st.columns(2)
        start_date_input = c1.date_input("Data Início", value=end_date_naive - timedelta(days=30))
        end_date_input = c2.date_input("Data Fim", value=end_date_naive)
        start_date_naive = datetime.combine(start_date_input, datetime.min.time())
        end_date_naive = datetime.combine(end_date_input, datetime.max.time())
    else:
        days_map = {"Últimos 7 dias": 7, "Últimos 30 dias": 30, "Últimos 3 meses": 90}
        start_date_naive = end_date_naive - timedelta(days=days_map.get(time_range_option, 7))

    start_date_current = TIMEZONE.localize(start_date_naive)
    end_date_current = TIMEZONE.localize(end_date_naive)
    
    period_duration = end_date_current - start_date_current
    start_date_previous = start_date_current - period_duration
    
    apply_filter = st.button("Aplicar Filtros", type="primary")

# --- Exibição dos Resultados ---
if apply_filter:
    current_df = handler.get_filtered_data(selected_filter, start_date_current, end_date_current)
    previous_df = handler.get_filtered_data(selected_filter, start_date_previous, end_date_current)

    st.subheader(f"Resultados para: {selected_filter.replace(':', ': ')}")

    if current_df.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
        current_simple_avg = current_df['sentiment_score'].mean()
        current_weighted_avg = calculate_weighted_avg(current_df)
        previous_weighted_avg = calculate_weighted_avg(previous_df)
        
        delta_vs_previous = 0.0
        if previous_weighted_avg != 0:
            delta_vs_previous = ((current_weighted_avg - previous_weighted_avg) / abs(previous_weighted_avg)) * 100

        col1, col2, col3 = st.columns(3)
        col1.metric("Sentimento Ponderado (Argus Score)", f"{current_weighted_avg:.3f}", f"{delta_vs_previous:.1f}% vs. período anterior")
        col2.metric("Sentimento Simples (Mercado)", f"{current_simple_avg:.3f}")
        col3.metric("Notícias no Período", len(current_df))

        st.markdown("---")
        
        display_sentiment_timeseries_chart(current_df)
        display_detailed_news_table(current_df)

        # Reativando o painel de depuração
        with st.expander("🕵️‍♂️ Painel de Depuração de Pesos"):
            st.write("Estatísticas descritivas dos componentes do peso para o período atual:")
            debug_cols = ['sentiment_score', 'craap_score', 'shannon_entropy', 'financial_relevance', 'relevance_weight']
            st.dataframe(current_df[debug_cols].describe())

else:
    st.info("Selecione os filtros e clique em 'Aplicar Filtros'.")