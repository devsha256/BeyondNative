import logging
import sys

def get_logger(name="beyond_native"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter('[%(asctime)s] %(levelname)-8s | %(module)-15s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        console_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
    return logger

log = get_logger()
