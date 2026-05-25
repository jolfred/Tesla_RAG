import logging
import sys
from config import LOG_FILE

def setup_logger(name: str):
    """
    Настраивает универсальный логгер для проекта.
    Пишет одновременно в консоль и в файл app.log.
    """
    logger = logging.getLogger(name)
    
    # Чтобы не дублировать логи при повторных вызовах в одном процессе
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.INFO)
    
    # Формат записи: время [уровень] модуль: сообщение
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )

    # Запись в файл
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)

    # Вывод в терминал
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger