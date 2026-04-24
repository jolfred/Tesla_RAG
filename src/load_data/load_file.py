import os
from .read_docx import read_docx
from .read_pdf import read_pdf
from .read_txt import read_txt

def load_file(path):
    ext = os.path.splitext(path)[1]

    if ext == ".pdf":
        return read_pdf(path)
    elif ext == ".docx":
        return read_docx(path)
    elif ext == ".txt":
        return read_txt(path)
    else:
        return ""