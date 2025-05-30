# src/database/seed_metadata.py
# -*- coding: utf-8 -*-

import sys
import os

# Adiciona o diretório raiz do projeto ao sys.path
project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root_path not in sys.path:
    sys.path.append(project_root_path)

try:
    from config import settings
    from src.database.db_utils import get_db_session # Usaremos a sessão do db_utils
    # Importe os modelos SQLAlchemy relevantes
    from src.database.create_db_tables import AnalyticalTheory, TheoryFrameworkDimension
except ImportError as e:
    settings.logger.error(f"Erro em seed_metadata.py ao importar: {e}")
    sys.exit(1)

# --- Definição dos Metadados a Serem Inseridos ---

THEORIES_DATA = [
    {"theory_name": "Hierarquia de Maslow", "description": "Classifica motivadores humanos e de mercado em níveis de necessidade (Fisiológicas, Segurança, Sociais, Estima, Autorrealização)."},
    # {"theory_name": "Finanças Comportamentais - Vieses", "description": "Identifica e analisa vieses cognitivos e emocionais que afetam a tomada de decisão financeira."},
    # {"theory_name": "Teoria de Redes Complexas", "description": "Mapeia e analisa interconexões, influências e dinâmicas de contágio em sistemas financeiros e corporativos."},
    # {"theory_name": "Teoria dos Jogos", "description": "Modela interações estratégicas entre agentes racionais ou com racionalidade limitada, cujos payoffs dependem das ações dos outros."},
    # {"theory_name": "Modelagem de Cenários Comportamentais", "description": "Simula o impacto de comportamentos de mercado (pânico, euforia, bolhas) em ativos ou no mercado."}
    # Adicione outras teorias principais do FAC-IA aqui conforme necessário
]

MASLOW_DIMENSIONS_DATA = [
    {"dimension_name": "Fisiológicas", "description": "Necessidades básicas de sobrevivência (alimento, água, abrigo, energia) e funcionamento elementar da sociedade."},
    {"dimension_name": "Segurança", "description": "Necessidade de proteção contra perigos físicos, financeiros, emocionais; busca por estabilidade, saúde, ordem e previsibilidade."},
    {"dimension_name": "Sociais", "description": "Necessidade de pertencimento, amor, amizade, interação social, comunicação e lazer compartilhado."},
    {"dimension_name": "Estima", "description": "Necessidade de reconhecimento, status, respeito dos outros, autoapreciação, competência e realização pessoal visível."},
    {"dimension_name": "Autorrealização", "description": "Necessidade de desenvolvimento pleno do potencial individual, criatividade, inovação, contribuição significativa e experiências transcendentes."}
]

# (Opcional para Fase 0, mas bom para preparar o futuro)
# BEHAVIORAL_FINANCE_DIMENSIONS_DATA = [
#     {"dimension_name": "Viés de Ancoragem", "description": "Dependência excessiva de informações iniciais (âncoras) ao tomar decisões."},
#     {"dimension_name": "Excesso de Confiança", "description": "Superestimação das próprias habilidades ou da precisão das informações que possui."},
#     {"dimension_name": "Comportamento de Manada", "description": "Tendência a seguir as ações de um grupo maior, mesmo que contradigam a própria análise."},
#     {"dimension_name": "FOMO (Fear of Missing Out)", "description": "Medo de ficar de fora de oportunidades de ganho, levando a decisões impulsivas."},
#     {"dimension_name": "Aversão à Perda", "description": "Tendência a sentir o impacto de uma perda de forma mais intensa do que o prazer de um ganho equivalente."},
#     {"dimension_name": "Viés de Disponibilidade", "description": "Supervalorização de informações recentes, vívidas ou facilmente recordáveis."},
#     {"dimension_name": "Viés de Confirmação", "description": "Busca e interpretação de informações que confirmem crenças preexistentes, ignorando dados contraditórios."}
# ]

# GAME_THEORY_MODELS_DIMENSIONS_DATA = [
#     {"dimension_name": "Competição de Preços (Bertrand)", "description": "Empresas competem definindo preços simultaneamente."},
#     {"dimension_name": "Competição de Quantidade (Cournot)", "description": "Empresas competem definindo quantidades produzidas simultaneamente."},
#     {"dimension_name": "Liderança Estratégica (Stackelberg)", "description": "Uma empresa líder age primeiro, e as seguidoras reagem."},
#     {"dimension_name": "Jogos Regulatórios (Principal-Agente)", "description": "Análise da interação estratégica entre empresas (agente) e órgãos reguladores (principal)."}
#     # Adicione os outros 7 modelos de Teoria dos Jogos aqui quando for implementá-los
# ]
# Adicione listas similares para Teoria de Redes Complexas e Modelagem de Cenários Comportamentais quando for o momento

def seed_analytical_theories(session):
    """Popula a tabela AnalyticalTheories."""
    settings.logger.info("Populando tabela AnalyticalTheories...")
    existing_theories = {t.theory_name for t in session.query(AnalyticalTheory.theory_name).all()}
    
    for theory_data in THEORIES_DATA:
        if theory_data["theory_name"] not in existing_theories:
            theory = AnalyticalTheory(
                theory_name=theory_data["theory_name"],
                description=theory_data.get("description")
            )
            session.add(theory)
            settings.logger.info(f"Adicionada teoria: {theory_data['theory_name']}")
        else:
            settings.logger.info(f"Teoria '{theory_data['theory_name']}' já existe.")
    session.commit()

def seed_theory_framework_dimensions(session):
    """Popula a tabela TheoryFrameworkDimensions."""
    settings.logger.info("Populando tabela TheoryFrameworkDimensions...")

    # Níveis de Maslow (essenciais para a próxima etapa)
    theory_maslow = session.query(AnalyticalTheory).filter_by(theory_name="Hierarquia de Maslow").first()
    if not theory_maslow:
        settings.logger.error("Teoria 'Hierarquia de Maslow' não encontrada. Execute seed_analytical_theories primeiro.")
        return

    existing_maslow_dims = {
        d.dimension_name for d in session.query(TheoryFrameworkDimension.dimension_name)
        .filter_by(theory_id=theory_maslow.theory_id).all()
    }
    for dim_data in MASLOW_DIMENSIONS_DATA:
        if dim_data["dimension_name"] not in existing_maslow_dims:
            dimension = TheoryFrameworkDimension(
                theory_id=theory_maslow.theory_id,
                dimension_name=dim_data["dimension_name"],
                description=dim_data.get("description")
            )
            session.add(dimension)
            settings.logger.info(f"Adicionada dimensão Maslow: {dim_data['dimension_name']}")
        else:
            settings.logger.info(f"Dimensão Maslow '{dim_data['dimension_name']}' já existe.")
    session.commit()

    # Opcional: Popular dimensões para outras teorias (ex: Vieses Comportamentais)
    # Você pode habilitar isso quando estiver pronto para a Fase 3
    # if settings.ENABLE_BEHAVIORAL_BIAS_ANALYSIS: # Usando a Feature Flag do settings.py
    #     theory_bf = session.query(AnalyticalTheory).filter_by(theory_name="Finanças Comportamentais - Vieses").first()
    #     if theory_bf:
    #         existing_bf_dims = {
    #             d.dimension_name for d in session.query(TheoryFrameworkDimension.dimension_name)
    #             .filter_by(theory_id=theory_bf.theory_id).all()
    #         }
    #         for dim_data in BEHAVIORAL_FINANCE_DIMENSIONS_DATA:
    #             if dim_data["dimension_name"] not in existing_bf_dims:
    #                 dimension = TheoryFrameworkDimension(
    #                     theory_id=theory_bf.theory_id,
    #                     dimension_name=dim_data["dimension_name"],
    #                     description=dim_data.get("description")
    #                 )
    #                 session.add(dimension)
    #                 settings.logger.info(f"Adicionada dimensão de Viés Comportamental: {dim_data['dimension_name']}")
    #             else:
    #                 settings.logger.info(f"Dimensão de Viés Comportamental '{dim_data['dimension_name']}' já existe.")
    #         session.commit()
    #     else:
    #         settings.logger.warning("Teoria 'Finanças Comportamentais - Vieses' não encontrada para popular dimensões.")

    # Adicione blocos similares para Teoria dos Jogos, Redes, etc., usando suas respectivas feature flags
    # if settings.ENABLE_GAME_THEORY_ANALYSIS:
    #     theory_gt = session.query(AnalyticalTheory).filter_by(theory_name="Teoria dos Jogos").first()
    #     if theory_gt:
    #         existing_gt_dims = {
    #             d.dimension_name for d in session.query(TheoryFrameworkDimension.dimension_name)
    #             .filter_by(theory_id=theory_gt.theory_id).all()
    #         }
    #         for dim_data in GAME_THEORY_MODELS_DIMENSIONS_DATA:
    #              if dim_data["dimension_name"] not in existing_gt_dims:
    #                 dimension = TheoryFrameworkDimension(
    #                     theory_id=theory_gt.theory_id,
    #                     dimension_name=dim_data["dimension_name"],
    #                     description=dim_data.get("description")
    #                 )
    #                 session.add(dimension)
    #                 settings.logger.info(f"Adicionada dimensão de Teoria dos Jogos: {dim_data['dimension_name']}")
    #              else:
    #                 settings.logger.info(f"Dimensão de Teoria dos Jogos '{dim_data['dimension_name']}' já existe.")
    #         session.commit()
    #     else:
    #         settings.logger.warning("Teoria 'Teoria dos Jogos' não encontrada para popular dimensões.")


def main():
    """Função principal para popular os metadados."""
    settings.logger.info("Iniciando script para popular metadados (teorias e dimensões)...")
    session = get_db_session()
    try:
        seed_analytical_theories(session)
        seed_theory_framework_dimensions(session)
        settings.logger.info("População de metadados concluída com sucesso.")
    except Exception as e:
        settings.logger.error(f"Erro ao popular metadados: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()