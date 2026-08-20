from pathlib import Path
from backend.utils.logger import setup_logger

logger = setup_logger("load_file")


def load_file(file_path: str) -> str | None:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        from backend.rag.loaders.read_pdf import read_pdf
        return read_pdf(file_path)
    elif ext == ".docx":
        from backend.rag.loaders.read_docx import read_docx
        return read_docx(file_path)
    elif ext == ".txt":
        from backend.rag.loaders.read_txt import read_txt
        return read_txt(file_path)
    elif ext == ".json":
        from backend.rag.loaders.read_json import read_publication_json
        return read_publication_json(file_path)
    else:
        logger.warning(f"Unsupported format: {ext}")
        return None
