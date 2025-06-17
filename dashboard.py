import streamlit as st
import pandas as pd
from src.data_analysis.data_handler import AnalysisDataHandler

st.set_page_config(layout="wide", page_title="Argus Analytics")

st.title("👁️ Argus Analytics")
st.markdown("### Transformando Informação em Inteligência Estratégica")

# --- Barra Lateral de Filtros ---
st.sidebar.header("Filtros de Análise")
topic = st.sidebar.text_input("Tópico ou Empresa", "Petrobras")
days_back = st.sidebar.slider("Analisar Últimos (dias)", 1, 90, 30)

# --- Carregamento e Processamento de Dados ---
try:
    data_handler = AnalysisDataHandler(topic=topic, days_back=days_back)
    st.sidebar.success(f"{len(data_handler.raw_analyses)} notícias encontradas e analisadas.")
except Exception as e:
    st.sidebar.error(f"Erro ao carregar dados: {e}")
    st.stop()


# --- Abas para cada tipo de Análise ---
if not data_handler.raw_analyses:
    st.warning(f"Nenhuma notícia analisada encontrada para '{topic}' nos últimos {days_back} dias.")
else:
    tab_sentimento, tab_entidades, tab_maslow, tab_stakeholders, tab_detalhes = st.tabs([
        "📈 Sentimento", "👥 Entidades", "🔺 Maslow", "🤝 Stakeholders", "📄 Detalhes"
    ])

    with tab_sentimento:
        st.header("Evolução do Sentimento do Mercado")
        
        sentiment_df = data_handler.get_sentiment_over_time()
        if not sentiment_df.empty:
            st.line_chart(sentiment_df)
            st.markdown("O gráfico mostra a flutuação do score de sentimento (-1.0 a 1.0) para o tópico ao longo do tempo.")
        else:
            st.warning("Não há dados de sentimento para exibir.")

    with tab_entidades:
        st.header("Principais Entidades Mencionadas")
        # Lógica para agregar e exibir dados de entidades virá aqui

    with tab_maslow:
        st.header("Impacto Estratégico (Maslow)")
        # Lógica para o gráfico de radar do Maslow virá aqui

    with tab_stakeholders:
        st.header("Análise de Stakeholders")
        # Lógica para o gráfico de barras dos stakeholders virá aqui

    with tab_detalhes:
        st.header("Análise Detalhada por Notícia")
        for i, analysis in enumerate(data_handler.raw_analyses):
            resumo = analysis.get('analise_resumo', {}).get('summary', 'Resumo não disponível.')
            with st.expander(f"Notícia {i+1}: {resumo[:100]}..."):
                st.json(analysis)