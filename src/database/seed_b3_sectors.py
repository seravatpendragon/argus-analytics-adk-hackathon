import pandas as pd
import os
import sys
from pathlib import Path

# Adiciona a raiz do projeto ao path
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from src.database.db_utils import get_db_session, get_or_create_sector, get_or_create_subsector, get_or_create_segment
from config import settings

def seed_b3_sectors_from_csv():
    """
    Lê o CSV com os setores da B3 e popula as tabelas correspondentes no banco de dados,
    com detecção automática de separador.
    """
    # IMPORTANTE: Verifique se este caminho está correto para o seu projeto
    caminho_csv = PROJECT_ROOT / "data" / "config_input" / "b3_sectors.csv" 

    if not caminho_csv.exists():
        print(f"ERRO: Arquivo CSV não encontrado em '{caminho_csv}'.")
        return

    print("Iniciando o processo de semeadura dos setores, subsetores e segmentos da B3...")
    
    with get_db_session() as session:
        try:
            # CORREÇÃO: Usando engine='python' e sep=None para que o pandas 
            # detecte o separador automaticamente.
            # Também presumimos que a primeira linha do seu CSV é o cabeçalho.
            df = pd.read_csv(
                caminho_csv, 
                engine='python',
                sep=None,
                skipinitialspace=True
            )
            
            print(f"Colunas detectadas no CSV: {df.columns.to_list()}")
            
            # Garante que os nomes das colunas esperadas existam
            colunas_esperadas = ['Setor_B3', 'Subsetor_B3', 'Segmento_B3']
            if not all(col in df.columns for col in colunas_esperadas):
                print(f"ERRO: O CSV não contém as colunas esperadas: {colunas_esperadas}")
                return

            df.drop_duplicates(inplace=True)
            print(f"Encontradas {len(df)} combinações únicas para processar.")

            for _, row in df.iterrows():
                setor_nome = row['Setor_B3']
                subsetor_nome = row['Subsetor_B3']
                segmento_nome = row['Segmento_B3']

                if pd.isna(setor_nome) or pd.isna(subsetor_nome) or pd.isna(segmento_nome):
                    continue
                
                setor_obj = get_or_create_sector(session, setor_nome)
                subsetor_obj = get_or_create_subsector(session, subsetor_nome, setor_obj.economic_sector_id)
                get_or_create_segment(session, segmento_nome, subsetor_obj.subsector_id)

            session.commit()
            print("\n✅ Processo de semeadura concluído com sucesso!")

        except Exception as e:
            print(f"\n❌ ERRO durante o processo de semeadura: {e}")
            session.rollback()

if __name__ == "__main__":
    seed_b3_sectors_from_csv()