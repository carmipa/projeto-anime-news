
import logging
import colorlog
import sys

def setup_logger(name: str = "AnimeBootNews") -> logging.Logger:
    """
    Configura e retorna um logger com suporte a cores (GRC style).
    """
    # Cria o logger base
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)  # Nível padrão. Pode ser alterado para DEBUG via env var se necessário.

    # Evita duplicação de handlers se chamar setup_logger múltiplas vezes
    if logger.handlers:
        return logger

    # Handler de Console (Stream)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    # Formatação com Cores
    # Documentação Cores: black, red, green, yellow, blue, purple, cyan, white
    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        reset=True,
        log_colors={
            'DEBUG':    'white',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

# Instância padrão para importação direta
log = setup_logger()
