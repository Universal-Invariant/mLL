# Interactive Polyglot Reader

A powerful multilingual text processing and audio generation tool that creates interactive HTML readers with synchronized text and audio in multiple languages.

## Features

- **Multi-language Support**: Process text in 60+ languages with support for Google Translate, Stanza NLP, and Edge-TTS
- **Interactive HTML Output**: Generate beautiful, dark-themed interactive readers with word-level synchronization
- **Audio Generation**: Create high-quality TTS audio using Microsoft Edge's neural voices
- **Smart Caching**: Extensive caching system for processed paragraphs, audio files, and linguistic data
- **Linguistic Analysis**: Part-of-speech tagging, lemmatization, and dictionary definitions
- **Romanization Support**: Built-in romanization for Chinese (Pinyin), Japanese (Hepburn), Korean (Hangul), Arabic, and more
- **Back-translation Alignment**: Intelligent word alignment between source and target languages
- **Agglutinative Language Handling**: Configurable penalties for agglutinative languages like Turkish, Korean, Japanese

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  config.py  │────▶│   core.py    │────▶│  engine.py  │
│             │     │              │     │             │
│ - Languages │     │ - NLP        │     │ - Pipeline  │
│ - Mappings  │     │ - Translation│     │ - TTS       │
│ - Voices    │     │ - Romanization│    │ - HTML Gen  │
└─────────────┘     └──────────────┘     └─────────────┘
```

### Components

- **config.py**: Language mappings, voice configurations, and language resolution logic
- **core.py**: NLP processing, translation, romanization, and dictionary lookups
- **engine.py**: Main processing pipeline, TTS generation, caching, and HTML output

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-directory>
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Download Stanza models (automatic on first run):
```python
import stanza
stanza.download('en')  # Replace with your language code
```

4. Install optional phonemizer backend (for IPA transcription):
```bash
# Linux/Ubuntu
sudo apt-get install espeak-ng

# macOS
brew install espeak-ng

# Windows
# Download from: https://github.com/espeak-ng/espeak-ng/releases
```

## Usage

### Basic Example

```python
from engine import PolyglotEngine

# Initialize the engine
engine = PolyglotEngine(output_dir="output", project_name="my_reader")

# Define your text and languages
paragraphs = [
    "The quick brown fox jumps over the lazy dog.",
    "Pack my box with five dozen liquor jugs."
]

# Process and generate HTML
batch_data = engine.process_batch(
    paragraphs=paragraphs,
    source_lang="English",
    target_languages=["Spanish", "French", "German"]
)

# Generate interactive HTML
engine.generate_html_batch(batch_data, output_filename="index.html")
```

### Advanced Configuration

```python
from config import LanguageMapper

# Get available languages
languages = LanguageMapper.get_available_languages()
print(f"Supported languages: {languages}")

# Get language codes
codes = LanguageMapper.get_codes("Japanese", voice_index=0)
print(f"Google code: {codes['google']}")
print(f"Stanza code: {codes['stanza']}")
print(f"TTS voice: {codes['tts']}")
```

## Supported Languages

The system supports 60+ languages including:

- **European**: English, Spanish, French, German, Italian, Portuguese, Russian, Polish, etc.
- **Asian**: Chinese (Simplified & Traditional), Japanese, Korean, Hindi, Thai, Vietnamese, etc.
- **Middle Eastern**: Arabic, Hebrew, Persian, Turkish
- **African**: Afrikaans, Swahili, Yoruba
- **And many more!**

## Output Structure

```
output/
└── my_reader/
    ├── index.html          # Interactive reader
    ├── para_*.json         # Cached paragraph data
    ├── tts_*.mp3           # Generated audio files
    └── tts_*.json          # Audio timestamp data
```

## HTML Features

- **Word-level Highlighting**: Synchronized highlighting as audio plays
- **Source Text Toggle**: Show/hide original source text
- **Dictionary Lookup**: Click words for definitions
- **POS Color Coding**: Visual part-of-speech indicators
- **Playback Controls**: Play, pause, seek, speed control
- **Responsive Design**: Works on desktop and mobile
- **Dark Theme**: Easy on the eyes for extended reading

## Customization

### Font Sizes
Adjust via CSS variables in the generated HTML:
```css
:root {
    --main-font: 2.0em;      /* Target text size */
    --source-font: 0.9em;    /* Source text size */
    --rom-font: 0.8em;       /* Romanization size */
}
```

### Voice Selection
Select different voices per language:
```python
codes = LanguageMapper.get_codes("English", voice_index=1)  # Second voice
```

### Agglutinative Penalties
Configure word alignment strictness in `config.py`:
```python
AGGLUTINATIVE_PENALTIES = {
    "Turkish": 1,    # Allow many-to-1 mapping
    "English": 100,  # Strict 1-to-1 mapping
}
```

## Dependencies

See `requirements.txt` for full list. Key dependencies:
- **edge-tts**: Text-to-speech generation
- **stanza**: NLP processing (tokenization, POS, lemmatization)
- **deep-translator**: Google Translate integration
- **phonemizer**: IPA transcription (optional)
- **pypinyin**: Chinese Pinyin (optional)
- **pykakasi**: Japanese romanization (optional)
- **hangul-romanize**: Korean romanization (optional)

## Performance Tips

1. **Use Caching**: The system automatically caches results. Re-run processing is instant for cached content.
2. **Batch Processing**: Process multiple paragraphs together for efficiency.
3. **Voice Cache**: Edge voices are cached after first fetch.
4. **Model Downloads**: Stanza models download once and persist locally.

## Troubleshooting

### Missing Phonemizer
```
ImportError: No module named 'phonemizer'
```
Install with: `pip install phonemizer` and ensure espeak-ng is installed on your system.

### Edge-TTS Errors
```
Error fetching Edge-TTS voices
```
Check internet connection. The system needs to fetch voice list from Microsoft servers.

### Stanza Download Issues
```
Exception: Stanza model download failed
```
Try manual download: `stanza.download('lang_code')`

## License

MIT License

## Contributing

Contributions welcome! Please feel free to submit issues and pull requests.

## Acknowledgments

- Microsoft Edge TTS for neural voice synthesis
- Stanford Stanza for NLP processing
- Google Translate for translation services
- Free Dictionary API for word definitions
