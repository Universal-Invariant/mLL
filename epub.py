import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup


def process_epub(epub_path, base_output_dir):
    book = epub.read_epub(epub_path)

    # 1. Setup Images Directory
    images_dir = os.path.join(base_output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # Extract all images from the EPUB container
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        img_filename = os.path.basename(item.get_name())
        img_path = os.path.join(images_dir, img_filename)
        with open(img_path, 'wb') as f:
            f.write(item.get_content())

    extracted_content = []
    paragraph_idx = 0  # Track paragraph flow for the UI

    block_tags = ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'img']

    # 2. Parse Text and Inject Unicode Markers
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')

        # Iterate through block-level elements
        for element in soup.find_all(block_tags):

            if element.name == 'div' and element.find(block_tags):
                continue

            # Detect alignment (checking inline styles and classes)
            alignment = "left"
            if element.has_attr('style') and 'text-align: center' in element['style']:
                alignment = "center"
            elif element.has_attr('class') and any('center' in c.lower() for c in element['class']):
                alignment = "center"

            # Handle standalone images
            if element.name == 'img':
                img_src = os.path.basename(element.get('src', ''))
                if img_src:
                    extracted_content.append({
                        "type": "image",
                        "src": img_src,
                        "alignment": alignment,
                        "paragraph_index": paragraph_idx
                    })
                    paragraph_idx += 1
                continue

            # Handle inline images within text blocks
            for img in element.find_all('img'):
                img_src = os.path.basename(img.get('src', ''))
                if img_src:
                    # Save the inline image as its own clean block
                    extracted_content.append({
                        "type": "image",
                        "src": img_src,
                        "alignment": alignment,
                        "paragraph_index": paragraph_idx
                    })
                    paragraph_idx += 1

                # Delete the image tag from the HTML tree so it doesn't leave junk in the text
                img.decompose()

            # Now safely extract the pure text
            text = element.get_text(separator=' ', strip=True)

            if text:
                extracted_content.append({
                    "type": "text",            # <-- This prevents the KeyError!
                    "text": text,              # <-- Pure text
                    "format": element.name,    # <-- Stores 'h1', 'h2', 'p', 'div' securely
                    "alignment": alignment,    # <-- Stores 'center' or 'left' securely
                    "paragraph_index": paragraph_idx
                })
                paragraph_idx += 1

    return extracted_content
