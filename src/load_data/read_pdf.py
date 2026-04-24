import pdfplumber

def read_pdf(path):
    text = ""
    pdf = pdfplumber.open(path)
    for page in pdf.pages:
        text += page.extract_text()
    return text
