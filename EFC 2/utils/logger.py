import logging
import sys

def setup_logger(name, level=logging.INFO):
    """Configura um logger para o projeto."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Evita adicionar múltiplos handlers se já existirem
    if not logger.handlers:
        # Cria um handler para a saída padrão (console)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        
        # Define o formato da mensagem
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        
        # Adiciona o handler ao logger
        logger.addHandler(ch)
        
    return logger

# Logger principal para o projeto
main_logger = setup_logger('ProjetoRedes')

def log_info(message, component='MAIN'):
    main_logger.info(f"[{component}] {message}")

def log_warning(message, component='MAIN'):
    main_logger.warning(f"[{component}] {message}")

def log_error(message, component='MAIN'):
    main_logger.error(f"[{component}] {message}")

def log_debug(message, component='MAIN'):
    main_logger.debug(f"[{component}] {message}")
