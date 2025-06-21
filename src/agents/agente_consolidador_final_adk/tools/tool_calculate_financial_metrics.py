# src/agents/agente_consolidador_analise_adk/tools/tool_calculate_financial_metrics.py
# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent 
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from config import settings 
from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

# --- Ferramenta de Cálculo do CAPM (já existente) ---
class CalculateCAPMInput(BaseModel):
    risk_free_rate: float = Field(..., description="A taxa de retorno livre de risco (em porcentagem decimal, ex: 0.05 para 5%).")
    beta: float = Field(..., description="O Beta do ativo.")
    market_return_estimate: float = Field(..., description="A estimativa de retorno do mercado (em porcentagem decimal, ex: 0.10 para 10%).")

def calculate_capm(risk_free_rate: float, beta: float, market_return_estimate: float) -> Dict[str, float]:
    """
    Calcula o Custo de Capital Próprio usando o Modelo de Precificação de Ativos de Capital (CAPM).
    Formula: Retorno Livre de Risco + Beta * (Retorno de Mercado - Retorno Livre de Risco).
    Retorna o CAPM calculado como um valor decimal.
    """
    try:
        capm_value = risk_free_rate + beta * (market_return_estimate - risk_free_rate)
        settings.logger.info(f"CAPM calculado: {capm_value:.4f} (RF={risk_free_rate}, Beta={beta}, RM={market_return_estimate})")
        return {"capm_calculated_return": round(capm_value, 4)} 
    except Exception as e:
        settings.logger.error(f"Erro ao calcular CAPM: {e}. Retornando CAPM como 0.0.", exc_info=True)
        return {"capm_calculated_return": 0.0}

calculate_capm_tool = FunctionTool(func=calculate_capm)

# --- NOVA FERRAMENTA: Cálculo do Modelo de Gordon ---
class CalculateGordonGrowthInput(BaseModel):
    d0: float = Field(..., description="Dividendo esperado por ação no próximo ano (D1).")
    expected_return_capm: float = Field(..., description="O retorno esperado da ação (CAPM) como taxa de desconto (em porcentagem decimal, ex: 0.132 para 13.2%).")
    growth_rate: float = Field(..., description="Taxa de crescimento constante dos dividendos (g) (em porcentagem decimal, ex: 0.03 para 3%).")

def calculate_gordon_growth_fair_price(d0: float, expected_return_capm: float, growth_rate: float) -> Dict[str, float]:
    """
    Calcula o preço justo da ação hoje (P0) usando o Modelo de Gordon (Dividend Discount Model).
    Fórmula: P0 = D1 / (E(Ra) - g).
    Retorna o preço justo calculado.
    """
    try:
        if expected_return_capm <= growth_rate:
            settings.logger.warning(f"Erro no Modelo de Gordon: Retorno esperado ({expected_return_capm}) <= Taxa de crescimento ({growth_rate}). Retornando preço justo 0.0.")
            return {"fair_price_gordon_model": 0.0} # Evita divisão por zero ou resultados negativos/infinitos
        d1 = d0 * (1 + growth_rate)  # Calcula o dividendo no próximo ano (D1) usando o crescimento    
        fair_price = d1 / (expected_return_capm - growth_rate)
        
        settings.logger.info(f"Preço Justo (Gordon Model) calculado: R$ {fair_price:.2f} (D1={d1}, E(Ra)={expected_return_capm}, g={growth_rate})")
        
        return {"fair_price_gordon_model": round(fair_price, 2)} # Arredonda para 2 casas decimais
    except Exception as e:
        settings.logger.error(f"Erro ao calcular preço justo com Modelo de Gordon: {e}. Retornando preço justo 0.0.", exc_info=True)
        return {"fair_price_gordon_model": 0.0}

# Instancia a ferramenta de cálculo do CAPM
calculate_capm_tool = FunctionTool(
    func=calculate_capm
)

# Instancia a ferramenta de cálculo do Modelo de Gordon
calculate_gordon_growth_fair_price_tool = FunctionTool(
    func=calculate_gordon_growth_fair_price
)