import logging
import sys
from config.settings import LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT

def setup_logging(name: str) -> logging.Logger:
    """
    Configura e retorna um logger com base nas configurações em settings.py.

    Args:
        name (str): O nome do logger, geralmente __name__ do módulo que o chama.

    Returns:
        logging.Logger: O objeto de logger configurado.
    """
    # Define o formato da mensagem de log
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # Configura o handler para enviar logs para a saída padrão (console)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Obtém o logger e evita adicionar handlers duplicados
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)

    if not logger.handlers:
        logger.addHandler(handler)

    # Impede que os logs se propaguem para o logger raiz, evitando duplicação
    logger.propagate = False

    return logger