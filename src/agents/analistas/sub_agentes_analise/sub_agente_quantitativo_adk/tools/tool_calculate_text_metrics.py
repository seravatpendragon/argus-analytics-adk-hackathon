# -*- coding: utf-8 -*-

import nltk
from nltk.stem import RSLPStemmer
from nltk.corpus import stopwords
import string
import math
import json
from pathlib import Path
from collections import Counter
from typing import Dict, Any

from config import settings

# --- Bloco de Setup de PLN e Carregamento de Keywords (CORRIGIDO) ---

def setup_nltk_resources():
    """
    Garante que os recursos NLTK necessários, incluindo a correção para 'punkt_tab',
    estejam presentes.
    """
    # Lista de pacotes que vamos garantir que existam
    packages = ['punkt', 'stopwords', 'rslp', 'punkt_tab']

    for package in packages:
        try:
            # Tentativa de download silencioso. Se já existir, não faz nada.
            # Se não existir, baixa.
            nltk.download(package, quiet=True)
            settings.logger.info(f"Recurso NLTK '{package}' verificado/baixado com sucesso.")
        except Exception as e:
            # Loga um erro se o download falhar por algum motivo (ex: sem internet)
            settings.logger.error(f"Falha ao baixar o recurso NLTK '{package}': {e}")


# A chamada no final do arquivo deve permanecer ou ser adicionada:
setup_nltk_resources()


def load_and_process_keywords() -> set:
    """
    Carrega as keywords do arquivo JSON, junta todas as categorias em uma
    única lista e retorna um set com as palavras stemizadas.
    """
    try:
        # O caminho para o nosso JSON de configuração
        config_path = settings.BASE_DIR / "config" / "financial_keywords.json"
        
        with open(config_path, 'r', encoding='utf-8') as f:
            keywords_by_category = json.load(f)
        
        all_keywords = [kw for sublist in keywords_by_category.values() for kw in sublist]
        
        stemmer = RSLPStemmer()
        processed_keywords = {stemmer.stem(kw) for kw in all_keywords}
        
        settings.logger.info(f"Carregadas e processadas {len(processed_keywords)} keywords financeiras únicas.")
        return processed_keywords
    except Exception as e:
        settings.logger.error(f"Falha ao carregar ou processar o arquivo de keywords: {e}", exc_info=True)
        return set()

# Carrega e processa as keywords uma vez quando o módulo é importado
PROCESSED_KEYWORDS = load_and_process_keywords()
STEMMER = RSLPStemmer()

# --- Fim do Bloco de Setup ---


def analyze_text_metrics(text: str) -> Dict[str, Any]:
    """
    Calcula métricas quantitativas de um texto, usando keywords carregadas de um JSON.
    """
    if not isinstance(text, str) or not text:
        return {"status": "error", "message": "Texto de entrada inválido ou vazio."}

    try:
        text_lower = text.lower()
        all_words = nltk.word_tokenize(text_lower, language='portuguese')
        
        # 1. Cálculo de Entropia
        stop_words = set(stopwords.words('portuguese'))
        meaningful_words = [word for word in all_words if word.isalpha() and word not in stop_words]

        absolute_entropy, relative_entropy, meaningful_word_count, unique_word_count = 0.0, 0.0, 0, 0
        if meaningful_words:
            freq = nltk.FreqDist(meaningful_words)
            meaningful_word_count = len(meaningful_words)
            unique_word_count = len(freq)
            
            entropy_val = -sum((p/meaningful_word_count) * math.log2(p/meaningful_word_count) for p in freq.values())
            absolute_entropy = entropy_val

            max_entropy = math.log2(unique_word_count) if unique_word_count > 1 else 0
            relative_entropy = entropy_val / max_entropy if max_entropy > 0 else 0

        # 2. Contagem de Palavras-Chave (usando a lista carregada do JSON)
        keyword_count = sum(1 for word in all_words if STEMMER.stem(word) in PROCESSED_KEYWORDS)

        return {
            "status": "success",
            "shannon_absolute_entropy": round(absolute_entropy, 4),
            "shannon_relative_entropy": round(relative_entropy, 4),
            "meaningful_word_count": meaningful_word_count,
            "unique_word_count": unique_word_count,
            "financial_keyword_count": float(keyword_count),
            "total_word_count": len(all_words)
        }
        
    except Exception as e:
        settings.logger.error(f"Erro ao calcular métricas do texto: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}