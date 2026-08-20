def read_pdf(file_path: str) -> str | None:
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            return '\n'.join(page.extract_text() or '' for page in pdf.pages)
    except Exception:
        return None
