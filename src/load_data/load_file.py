import os
from .read_docx import read_docx
from .read_pdf import read_pdf
from .read_txt import read_txt

from src.utils.logger import setup_logger
logger = setup_logger("my_new_module")

def load_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        return read_pdf(path)
    elif ext == ".docx":
        return read_docx(path)
    elif ext == ".txt":
        return read_txt(path)
    else:
        return ""