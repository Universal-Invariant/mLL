import os
import json
import subprocess
from pathlib import Path

CACHE_FILE = Path(__file__).parent / "edge_voices_cache.json"

# ==========================================
# 1. GOOGLE TRANSLATE LANGUAGES (Hardcoded)
# ==========================================
GOOGLE_LANGS = {
    "Afrikaans": "af", "Albanian": "sq", "Amharic": "am", "Arabic": "ar",
    "Armenian": "hy", "Azerbaijani": "az", "Basque": "eu", "Belarusian": "be",
    "Bengali": "bn", "Bosnian": "bs", "Bulgarian": "bg", "Catalan": "ca",
    "Chinese (Simplified)": "zh-CN", "Chinese (Traditional)": "zh-TW",
    "Croatian": "hr", "Czech": "cs", "Danish": "da", "Dutch": "nl",
    "English": "en", "Estonian": "et", "Finnish": "fi", "French": "fr",
    "Galician": "gl", "Georgian": "ka", "German": "de", "Greek": "el",
    "Gujarati": "gu", "Hebrew": "he", "Hindi": "hi", "Hungarian": "hu",
    "Icelandic": "is", "Indonesian": "id", "Irish": "ga", "Italian": "it",
    "Japanese": "ja", "Kannada": "kn", "Kazakh": "kk", "Korean": "ko",
    "Latin": "la", "Latvian": "lv", "Lithuanian": "lt", "Macedonian": "mk",
    "Malay": "ms", "Malayalam": "ml", "Maltese": "mt", "Marathi": "mr",
    "Mongolian": "mn", "Nepali": "ne", "Norwegian": "no", "Persian": "fa",
    "Polish": "pl", "Portuguese (Brazil)": "pt-BR", "Portuguese (Portugal)": "pt-PT",
    "Punjabi": "pa", "Romanian": "ro", "Russian": "ru", "Serbian": "sr",
    "Slovak": "sk", "Slovenian": "sl", "Spanish": "es", "Swahili": "sw",
    "Swedish": "sv", "Tamil": "ta", "Telugu": "te", "Thai": "th",
    "Turkish": "tr", "Ukrainian": "uk", "Urdu": "ur", "Uzbek": "uz",
    "Vietnamese": "vi", "Welsh": "cy"
}

# ==========================================
# 2. STANZA LANGUAGES (Extracted & Mapped)
# ==========================================
STANZA_LANGS = {
    "af", "ar", "hy", "eu", "bg", "ca", "zh-hans", "zh-hant", "hr", "cs", "da",
    "nl", "en", "et", "fi", "fr", "gl", "de", "el", "he", "hi", "hu", "id",
    "ga", "it", "ja", "kk", "ko", "la", "lv", "no_bokmaal", "no_nynorsk", "fa",
    "pl", "pt", "ro", "ru", "sr", "sk", "sl", "es", "sv", "tr", "uk", "ur", "vi",
    "mk", "mt", "is", "ml", "mr", "ne", "pa", "gu", "kn", "sw", "am", "az",
    "be", "bs", "ka", "mn", "uz", "cy"
}

def google_to_stanza(g_code):
    mapping = {"zh-CN": "zh-hans", "zh-TW": "zh-hant", "pt-BR": "pt", "pt-PT": "pt", "no": "no_bokmaal", "he": "he", "iw": "he" }
    return mapping.get(g_code, g_code)

def google_to_edge_locale(g_code):
    mapping = {
        "af": "af-ZA", "ar": "ar-SA", "bg": "bg-BG", "bn": "bn-BD", "ca": "ca-ES",
        "cs": "cs-CZ", "da": "da-DK", "de": "de-DE", "el": "el-GR", "en": "en-US",
        "es": "es-ES", "et": "et-EE", "fi": "fi-FI", "fr": "fr-FR", "gl": "gl-ES",
        "he": "he-IL", "hi": "hi-IN", "hr": "hr-HR", "hu": "hu-HU", "id": "id-ID",
        "it": "it-IT", "ja": "ja-JP", "ko": "ko-KR", "lt": "lt-LT", "lv": "lv-LV",
        "ms": "ms-MY", "nl": "nl-NL", "no": "nb-NO", "pl": "pl-PL", "pt-BR": "pt-BR",
        "pt-PT": "pt-PT", "ro": "ro-RO", "ru": "ru-RU", "sk": "sk-SK", "sl": "sl-SI",
        "sr": "sr-RS", "sv": "sv-SE", "ta": "ta-IN", "te": "te-IN", "th": "th-TH",
        "tr": "tr-TR", "uk": "uk-UA", "ur": "ur-PK", "vi": "vi-VN", "zh-CN": "zh-CN",
        "zh-TW": "zh-TW", "cy": "cy-GB", "ga": "ga-IE", "mt": "mt-MT", "is": "is-IS",
        "mk": "mk-MK", "ml": "ml-IN", "mr": "mr-IN", "ne": "ne-NP", "fa": "fa-IR",
        "pa": "pa-IN", "gu": "gu-IN", "kn": "kn-IN", "sw": "sw-KE", "am": "am-ET",
        "az": "az-AZ", "eu": "eu-ES", "be": "be-BY", "bs": "bs-BA", "ka": "ka-GE",
        "kk": "kk-KZ", "mn": "mn-MN", "uz": "uz-UZ"
    }
    return mapping.get(g_code, g_code.upper())

# ==========================================
# 3. EDGE-TTS VOICES (Cached & Parsed)
# ==========================================
def get_edge_voices():
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    print("🔍 Fetching Edge-TTS voices...")
    try:
        result = subprocess.run(['edge-tts', '--list-voices'], capture_output=True, text=True, check=True)
        voices_by_locale = {}
        for line in result.stdout.split('\n'):
            if not line.strip() or line.startswith('Name') or line.startswith('---'): continue
            parts = line.split()
            if len(parts) >= 2:
                locale = f"{parts[0].split('-')[0]}-{parts[0].split('-')[1]}"
                voices_by_locale.setdefault(locale, []).append(parts[0])
        with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(voices_by_locale, f, indent=2)
        return voices_by_locale
    except Exception as e:
        print(f"❌ Error fetching Edge-TTS voices: {e}")
        return {}

# ==========================================
# 4. TRANSLITERATION MAPPING
# ==========================================
TRANSLIT_MAP = {
    "ru": "ru", "uk": "uk", "bg": "bg", "el": "el", "hi": "hi",
    "sr": "sr", "mk": "mk", "ka": "ka", "hy": "hy", "mn": "mn"
}


# ==========================================
# AGGLUTINATIVE PENALTIES (Controllable)
# ==========================================
# 100 = Strict 1-to-1 (Non-agglutinative)
# 1 = Allow Many-to-1 merging (Highly agglutinative)
AGGLUTINATIVE_PENALTIES = {
    # Highly Agglutinative (Allow merging like "in the trees" -> "나무에서")
    "Turkish": 1, "Korean": 1, "Japanese": 1, "Hungarian": 1, "Finnish": 1,
    # Isolating / Fusional (Strict 1-to-1 mapping)
    "English": 100, "French": 100, "Spanish": 100, "Italian": 100, "German": 100,
    "Russian": 100, "Polish": 100, "Romanian": 100, "Bulgarian": 100, "Greek": 100,
    "Chinese (Simplified)": 100, "Chinese (Traditional)": 100, "Arabic": 100,
    "Hindi": 100, "Irish": 100, "Portuguese (Brazil)": 100, "Portuguese (Portugal)": 100
}


# ==========================================
# 5. BUILD THE INTERSECTION MAPPING
# ==========================================
def build_mapping():
    edge_voices = get_edge_voices()
    mapping = {}
    for lang_name, g_code in GOOGLE_LANGS.items():
        s_code = google_to_stanza(g_code)
        e_locale = google_to_edge_locale(g_code)
        if s_code not in STANZA_LANGS: continue

        available_voices = edge_voices.get(e_locale, [])
        if not available_voices:
            base_lang = g_code.split('-')[0]
            for loc, voices in edge_voices.items():
                if loc.startswith(base_lang): available_voices.extend(voices)
        if not available_voices: continue

        mapping[lang_name] = {
            "google": g_code,
            "stanza": s_code,
            "tts": available_voices,
            "translit_lang": TRANSLIT_MAP.get(s_code, None),
            "agglutinative_penalty": AGGLUTINATIVE_PENALTIES.get(lang_name, 100) # Inject penalty
        }
    return mapping


# ==========================================
# 6. EXPLICIT ALIASES (Optional Overrides)
# ==========================================
LANG_ALIASES = {
    "Portuguese": "Portuguese (Brazil)",
    "Chinese": "Chinese (Simplified)",
    "Norwegian": "Norwegian",
    "Spanish": "Spanish"
}

# ==========================================
# 7. LANGUAGE MAPPER CLASS (With Smart Resolution)
# ==========================================
class LanguageMapper:
    MAPPING = build_mapping()
    POS_CSS_MAP = {'NOUN': 'pos-noun', 'VERB': 'pos-verb', 'ADJ': 'pos-adj', 'ADV': 'pos-adv', 'PRON': 'pos-pron'}

    @classmethod
    def _resolve_lang_name(cls, lang_name):
        """
        Resolves a user-provided language name to its exact key in MAPPING.
        Uses a 3-tier fallback: Exact Match -> Explicit Alias -> Smart Prefix Match.
        """
        lang_name_lower = lang_name.lower()

        # Tier 1: Exact Match (Case-insensitive)
        for k in cls.MAPPING.keys():
            if k.lower() == lang_name_lower:
                return k

        # Tier 2: Explicit Alias
        for alias, target in LANG_ALIASES.items():
            if alias.lower() == lang_name_lower and target in cls.MAPPING:
                return target

        # Tier 3: Smart Prefix Matching (e.g., "Portuguese" -> "Portuguese (Brazil)")
        for k in cls.MAPPING.keys():
            if k.lower().startswith(lang_name_lower):
                return k

        return None

    @classmethod
    def get_codes(cls, lang_name, voice_index=0):
        """
        Returns the configuration for a language.
        Automatically resolves shorthand names to their full equivalents.
        """
        actual_name = cls._resolve_lang_name(lang_name)

        if not actual_name:
            raise ValueError(f"Language '{lang_name}' not supported. Available: {list(cls.MAPPING.keys())}")

        codes = cls.MAPPING[actual_name].copy()
        voices = codes["tts"]

        # Select the specific voice based on index, wrapping around if index is too large
        codes["tts"] = voices[voice_index % len(voices)]
        return codes

    @classmethod
    def get_available_languages(cls):
        """Returns a list of all fully supported language names."""
        return list(cls.MAPPING.keys())

# ==========================================
# TEST / DEBUG
# ==========================================
if __name__ == "__main__":
    print(f"\n🌍 Successfully mapped {len(LanguageMapper.MAPPING)} fully supported languages.\n")

    # Demonstrate the smart resolution
    test_names = ["Portuguese", "Chinese", "Norwegian", "Spanish", "French", "en"]
    for name in test_names:
        try:
            codes = LanguageMapper.get_codes(name)
            print(f"✅ '{name}' successfully resolved to '{name}' -> Google: {codes['google']}, Stanza: {codes['stanza']}")
        except ValueError as e:
            print(f"❌ {e}")