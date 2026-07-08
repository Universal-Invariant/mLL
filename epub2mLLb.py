import os
import shutil
import zipfile
from pathlib import Path

from epub import process_epub
from engine import PolyglotEngine


def create_mllb(epub_path, source_lang, target_languages, output_name):
    workspace_dir = Path("mllb_workspace")
    book_dir = workspace_dir / output_name

    # 1. Prepare a clean workspace to prevent stale cache files from slipping in
    if book_dir.exists():
        shutil.rmtree(book_dir)
    book_dir.mkdir(parents=True, exist_ok=True)

    print(f"📦 Extracting EPUB: {epub_path}")
    # 2. Extract EPUB (Images are automatically routed to book_dir/images)
    paragraphs = process_epub(epub_path, base_output_dir=book_dir)

    print("🧠 Running NLP and Translation Engine...")

    # 3. Initialize engine pointing strictly to our workspace
    engine = PolyglotEngine(output_dir=str(workspace_dir), project_name=output_name)
    batch_data = engine.process_batch(paragraphs, source_lang, target_languages)

    print("📄 Generating HTML layout...")
    # 4. Generate the final index.html inside the workspace
    engine.generate_html_batch(batch_data, output_filename="index.html")

    # 5. Zip the entire workspace into a self-contained .mLLb file
    mllb_filename = f"{output_name}.mLLb"
    print(f"🗜️ Zipping payload into {mllb_filename}...")

    with zipfile.ZipFile(mllb_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(book_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # Create a relative path to maintain the internal directory structure (e.g., images/cover.jpg)
                arcname = os.path.relpath(file_path, book_dir)
                zipf.write(file_path, arcname)

    print(f"✅ Success! Self-contained book generated: {mllb_filename}")
    return mllb_filename


if __name__ == "__main__":
    create_mllb(
        epub_path="sample.epub",
        source_lang="English",
        target_languages=["French", "Russian", "Japanese"],
        output_name="polyglot_sample"
    )
