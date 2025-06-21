# src/data_processing/conflict_detector.py (Versão Corrigida)

from datetime import datetime
# from config import settings # Provavelmente não precisa mais de settings aqui se não tiver log ou params específicos

class ConflictDetector:
    """
    Analisa um objeto de análise JSON para detectar conflitos de lógica e integridade,
    e então calcula um score de confiança, APENAS COM BASE NOS DADOS DO JSON DE ANÁLISE.
    """
    def __init__(self, analysis_data: dict):
        self.analysis = analysis_data if isinstance(analysis_data, dict) else {}
        self.confidence_score = 100
        self.conflicts = []

    def _check_missing_fields(self):
        """Verifica se campos essenciais estão faltando ou vazios."""
        if not self.analysis.get('analise_resumo', {}).get('summary'):
            self.confidence_score -= 30
            self.conflicts.append("Falha de Integridade: O resumo da análise está ausente.")
        
        if self.analysis.get('analise_sentimento', {}).get('sentiment_score') is None:
            self.confidence_score -= 30
            self.conflicts.append("Falha de Integridade: O score de sentimento está ausente.")
        
        if not self.analysis.get('analise_entidades', {}).get('entidades_identificadas'):
            self.confidence_score -= 20
            self.conflicts.append("Falha de Integridade: Nenhuma entidade foi identificada.")

        # NOVO: Verificar a presença da análise de Stakeholders
        stakeholder_data = self.analysis.get('analise_stakeholders', {})
        if not stakeholder_data or not stakeholder_data.get('stakeholder_analysis'):
            self.confidence_score -= 15 # Penalidade se a seção de Stakeholders estiver ausente ou vazia
            self.conflicts.append("Falha de Integridade: A análise de stakeholders está ausente ou vazia.")

        # NOVO: Verificar a presença da análise de Impacto Maslow
        maslow_data = self.analysis.get('analise_impacto_maslow', {})
        # Verifica se a seção está ausente ou se a chave principal de score está ausente
        if not maslow_data or maslow_data.get('score_maslow') is None:
            self.confidence_score -= 10 # Penalidade se a seção de Maslow estiver ausente ou incompleta
            self.conflicts.append("Falha de Integridade: A análise de impacto Maslow está ausente ou incompleta.")

    def _check_sentiment_intensity_conflict(self):
        sentiment_data = self.analysis.get('analise_sentimento', {})
        score = sentiment_data.get('sentiment_score', 0.0)
        intensity = sentiment_data.get('intensity', 'Nula')
        if abs(score) > 0.6 and intensity in ['Leve', 'Nula']:
            self.confidence_score -= 15
            self.conflicts.append("Conflito Lógico: Sentimento forte com intensidade fraca.")

    def _check_stakeholder_conflict(self):
        sentiment_label = self.analysis.get('analise_sentimento', {}).get('sentiment_label')
        stakeholder_data = self.analysis.get('analise_stakeholders', {}).get('stakeholder_analysis', [])
        for stakeholder in stakeholder_data:
            if stakeholder.get('stakeholder_group') == 'Acionistas/Investidores':
                impact = stakeholder.get('impact_direction')
                if (sentiment_label == 'Positivo' and impact == 'Negativo') or \
                   (sentiment_label == 'Negativo' and impact == 'Positivo'):
                    self.confidence_score -= 20
                    self.conflicts.append("Conflito Lógico: Sentimento geral contradiz o impacto para investidores.")
                break

    def _check_sentiment_maslow_conflict(self):
        sentiment_score = self.analysis.get('analise_sentimento', {}).get('sentiment_score', 0.0)
        primary_maslow = self.analysis.get('analise_impacto_maslow', {}).get('maslow_impact_primary_category')
        if primary_maslow == 'Segurança' and sentiment_score > 0.5:
            self.confidence_score -= 15
            self.conflicts.append("Conflito Lógico: Sentimento altamente positivo com foco em 'Segurança'.")
    
    def _check_agent_alerts(self):
        alerts = self.analysis.get('analise_entidades', {}).get('alertas', [])
        if alerts:
            self.confidence_score -= 25 * len(alerts)
            self.conflicts.append(f"Alerta do Agente: Foram encontrados os seguintes alertas - {', '.join(alerts)}")

    def _check_relevance_conflict(self):
        relevance = self.analysis.get('analise_entidades', {}).get('relevancia_mercado_financeiro', 0.0)
        score = self.analysis.get('analise_sentimento', {}).get('sentiment_score', 0.0)
        if relevance < 0.4 and abs(score) > 0.7:
            self.confidence_score -= 10
            self.conflicts.append("Conflito Lógico: Sentimento forte em notícia de baixa relevância financeira.")

    def run(self) -> dict:
        self._check_missing_fields()
        self._check_sentiment_intensity_conflict()
        self._check_stakeholder_conflict()
        self._check_sentiment_maslow_conflict()
        self._check_agent_alerts()
        self._check_relevance_conflict()
        
        return {
            "confidence_score": max(0, self.confidence_score),
            "conflicts": self.conflicts,
            "audited_by": "ConflictDetector",
            "audit_timestamp": datetime.now().isoformat()
        }