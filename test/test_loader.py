import os
from src.load_data.load_file import load_file 

folder = "data/raw/docs"

for file in os.listdir(folder):
    path = os.path.join(folder, file)
    
    text = load_file(path)
    
    print("\n====", file, "====")
    print(text[:500])  # первые 500 символов