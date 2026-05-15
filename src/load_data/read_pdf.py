import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import os
from src.utils.logger import setup_logger

logger = setup_logger("read_pdf")

def read_pdf(path: str) -> str:
    """
    Читает PDF. Если текстового слоя нет (скан), использует OCR (Tesseract).
    """
    text_content = []
    
    try:
        with pdfplumber.open(path) as pdf:
            logger.info(f"Анализ PDF: {os.path.basename(path)} ({len(pdf.pages)} стр.)")
            
            for i, page in enumerate(pdf.pages):
                # Пробуем обычное извлечение
                page_text = page.extract_text()
                
                if page_text and len(page_text.strip()) > 10:
                    text_content.append(page_text)
                else:
                    # Если текста нет, значит это скан. Включаем OCR для этой страницы.
                    logger.info(f"Страница {i+1} кажется пустой или сканом. Запускаем OCR...")
                    ocr_text = ocr_page(path, i + 1)
                    if ocr_text:
                        text_content.append(ocr_text)

        return "\n".join(text_content).strip()

    except Exception as e:
        logger.error(f"Ошибка при обработке PDF {path}: {e}")
        return ""

def ocr_page(pdf_path: str, page_num: int) -> str:
    """
    Превращает одну страницу PDF в картинку и распознает текст через Tesseract.
    """
    try:
        # Конвертируем только нужную страницу (чтобы не жрать память)
        images = convert_from_path(
            pdf_path, 
            first_page=page_num, 
            last_page=page_num,
            dpi=300 # Высокое качество для лучшего распознавания
        )
        
        if not images:
            return ""
            
        # Распознаем текст (указываем русский и английский языки)
        text = pytesseract.image_to_string(images[0], lang='rus+eng')
        return text
    except Exception as e:
        logger.error(f"Ошибка OCR на странице {page_num}: {e}")
        return ""