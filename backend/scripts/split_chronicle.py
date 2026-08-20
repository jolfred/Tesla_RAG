#!/usr/bin/env python3
"""Split Polnaya_Letopis_Shtaba_Tesla.txt into 100 smaller files by posts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.config import DOCUMENTS_DIR
from backend.utils.logger import setup_logger

logger = setup_logger("splitter")

SRC = DOCUMENTS_DIR / "Polnaya_Letopis_Shtaba_Tesla.txt"
TARGET_COUNT = 100

with open(SRC, "r", encoding="utf-8") as f:
    content = f.read()

header = ""
# Extract header (everything before first post)
first_post_idx = content.find("\n--- [ДАТА:")
if first_post_idx > 0:
    header = content[:first_post_idx].strip()
    body = content[first_post_idx:].strip()
else:
    body = content

# Split by post delimiter
delimiter = "\n--- [ДАТА:"
posts = body.split(delimiter)

# Reconstruct posts with their delimiter
full_posts = []
for i, post in enumerate(posts):
    if i == 0:
        full_posts.append(post.strip())
    else:
        full_posts.append(f"--- [ДАТА:{post.strip()}")

print(f"Total posts: {len(full_posts)}")

posts_per_file = max(1, len(full_posts) // TARGET_COUNT)
file_idx = 0

for start in range(0, len(full_posts), posts_per_file):
    end = min(start + posts_per_file, len(full_posts))
    file_posts = full_posts[start:end]

    file_content = header + "\n\n" if header else ""
    file_content += "\n\n".join(file_posts)

    fname = f"chronicle_part_{file_idx+1:03d}.txt"
    fpath = DOCUMENTS_DIR / fname

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(file_content)

    file_idx += 1

print(f"Split into {file_idx} files")

# Remove original large file
SRC.unlink()
print(f"Removed original {SRC.name}")
