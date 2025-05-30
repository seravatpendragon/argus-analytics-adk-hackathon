import pandas as pd
import sqlite3
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import os
from datetime import datetime

# --- Configurações ---
# Ajuste o PROJECT_ROOT para apontar para a raiz do seu projeto
# Este script está em 'scripts/', então subimos um nível.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_NAME = "argus_config.db" # Nome do seu banco de dados
DB_DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
DB_PATH = os.path.join(DB_DATA_DIR, DB_NAME)

# Nome do arquivo PDF de saída
TIMESTAMP_STR = datetime.now().strftime("%Y%m%d_%H%M%S")
PDF_FILENAME = os.path.join(PROJECT_ROOT, 'reports', f'Relatorio_Indicadores_Macro_{TIMESTAMP_STR}.pdf')
# Certifique-se de que a pasta 'reports' existe na raiz do projeto
REPORTS_DIR = os.path.join(PROJECT_ROOT, 'reports')

def fetch_distinct_indicators(conn):
    """Busca todos os nomes de indicadores distintos no banco de dados."""
    try:
        df_indicators = pd.read_sql_query("SELECT DISTINCT indicator_name FROM macroeconomic_data ORDER BY indicator_name;", conn)
        return df_indicators['indicator_name'].tolist()
    except Exception as e:
        print(f"Erro ao buscar lista de indicadores: {e}")
        return []

def fetch_indicator_data(conn, indicator_name):
    """Busca os dados (data, valor) para um indicador específico."""
    try:
        query = "SELECT date, value FROM macroeconomic_data WHERE indicator_name = ? ORDER BY date ASC;"
        df_data = pd.read_sql_query(query, conn, params=(indicator_name,))
        
        if df_data.empty:
            print(f"Nenhum dado encontrado para o indicador: {indicator_name}")
            return None
            
        df_data['date'] = pd.to_datetime(df_data['date'])
        df_data['value'] = pd.to_numeric(df_data['value'], errors='coerce')
        df_data.dropna(subset=['value'], inplace=True) # Remove linhas onde o valor não pôde ser convertido
        
        if df_data.empty:
            print(f"Nenhum dado válido (após conversão de valor) encontrado para o indicador: {indicator_name}")
            return None
            
        return df_data.sort_values(by='date') # Garante ordenação
        
    except Exception as e:
        print(f"Erro ao buscar dados para o indicador '{indicator_name}': {e}")
        return None

def create_report():
    """Cria o relatório PDF com um gráfico para cada indicador."""
    if not os.path.exists(DB_PATH):
        print(f"ERRO: Banco de dados não encontrado em {DB_PATH}")
        return

    # Garante que o diretório de relatórios exista
    if not os.path.exists(REPORTS_DIR):
        try:
            os.makedirs(REPORTS_DIR)
            print(f"Diretório de relatórios criado em: {REPORTS_DIR}")
        except Exception as e:
            print(f"ERRO ao criar diretório de relatórios '{REPORTS_DIR}': {e}")
            return

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        indicator_names = fetch_distinct_indicators(conn)

        if not indicator_names:
            print("Nenhum indicador encontrado no banco de dados para gerar o relatório.")
            return

        print(f"Gerando relatório para {len(indicator_names)} indicadores...")

        with PdfPages(PDF_FILENAME) as pdf:
            for indicator_name in indicator_names:
                print(f"Processando e plotando: {indicator_name}")
                df_indicator = fetch_indicator_data(conn, indicator_name)

                if df_indicator is not None and not df_indicator.empty:
                    fig, ax = plt.subplots(figsize=(11, 7)) # Tamanho da página A4 aproximado em polegadas
                    
                    ax.plot(df_indicator['date'], df_indicator['value'], marker='.', linestyle='-', linewidth=1, markersize=3)
                    
                    # Título e rótulos
                    title = f"{indicator_name}"
                    # Quebra de linha no título se for muito longo
                    if len(indicator_name) > 70: # Ajuste este valor conforme necessário
                        parts = indicator_name.split('(')
                        if len(parts) > 1:
                            title = f"{parts[0].strip()}\n({parts[1].strip()}"
                        else: # Quebra simples se não houver parênteses
                            mid_point = len(indicator_name) // 2
                            # Encontra um espaço perto do meio para quebrar
                            break_point = indicator_name.rfind(' ', 0, mid_point + 5)
                            if break_point == -1: break_point = mid_point
                            title = indicator_name[:break_point] + "\n" + indicator_name[break_point:].strip()

                    ax.set_title(title, fontsize=10)
                    ax.set_xlabel("Data", fontsize=8)
                    ax.set_ylabel("Valor", fontsize=8)
                    
                    # Formatação do eixo X para datas
                    fig.autofmt_xdate(rotation=45) # Rotaciona as datas para melhor visualização
                    ax.tick_params(axis='x', labelsize=7)
                    ax.tick_params(axis='y', labelsize=7)
                    
                    ax.grid(True, linestyle='--', alpha=0.6)
                    plt.tight_layout(pad=1.5) # Adiciona um pouco de padding
                    
                    pdf.savefig(fig, bbox_inches='tight') # Salva a figura atual no PDF
                    plt.close(fig) # Fecha a figura para liberar memória
                else:
                    print(f"  -> Dados insuficientes ou inválidos para plotar {indicator_name}.")

        print(f"\nRelatório PDF gerado com sucesso: {PDF_FILENAME}")

    except sqlite3.Error as e:
        print(f"Erro de SQLite ao gerar relatório: {e}")
    except Exception as e:
        print(f"Erro inesperado ao gerar relatório: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    print("Iniciando geração do relatório de indicadores...")
    create_report()
    print("Geração do relatório concluída.")