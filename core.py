# core.py
from pydoc import text

import stanza
from deep_translator import GoogleTranslator
import requests
from config import LanguageMapper
import re
import difflib


try:
    from phonemizer import phonemize
    from phonemizer.separator import Separator
    HAS_PHONEMIZER = True
except ImportError:
    HAS_PHONEMIZER = False


try:
    from pypinyin import pinyin
    HAS_PINYIN = True
except ImportError:
    HAS_PINYIN = False
try:
    import pykakasi
    HAS_KAKASI = True
    kks = pykakasi.kakasi()
except ImportError:
    HAS_KAKASI = False
try:
    from hangul_romanize import Transliter
    from hangul_romanize.rule import academic
    HAS_HANGUL = True
    hangul_transliter = Transliter(academic)
except ImportError:
    HAS_HANGUL = False
try:
    import transliterate
    HAS_TRANSLITERATE = True
except ImportError:
    HAS_TRANSLITERATE = False


# Simple Arabic Transliteration Mapper
ARABIC_TO_LATIN = {
    'ا': 'a', 'ب': 'b', 'ت': 't', 'ث': 'th', 'ج': 'j', 'ح': 'h', 'خ': 'kh',
    'د': 'd', 'ذ': 'dh', 'ر': 'r', 'ز': 'z', 'س': 's', 'ش': 'sh', 'ص': 's',
    'ض': 'd', 'ط': 't', 'ظ': 'z', 'ع': "'", 'غ': 'gh', 'ف': 'f', 'ق': 'q',
    'ك': 'k', 'ل': 'l', 'م': 'm', 'ن': 'n', 'ه': 'h', 'و': 'w', 'ي': 'y',
    'ة': 'h', 'ى': 'a', 'آ': 'aa', 'إ': 'i', 'أ': 'a', 'ؤ': 'u', 'ئ': 'i',
    ' ': ' '
}


def simple_arabic_romanize(text):
    return "".join([ARABIC_TO_LATIN.get(char, char) for char in text])


class NLPProcessor:
    def __init__(self): self.nlp_pipelines = {}

    def get_stanza_pipeline(self, stanza_code):
        if stanza_code not in self.nlp_pipelines:
            print(f"[{stanza_code}] Loading/Downloading Stanza model...")
            stanza.download(
                stanza_code, processors='tokenize,pos,lemma', verbose=False)
            self.nlp_pipelines[stanza_code] = stanza.Pipeline(
                lang=stanza_code, processors='tokenize,pos,lemma', verbose=False)
        return self.nlp_pipelines[stanza_code]

    def batch_stanza_extract(self, stanza_code, paragraphs):
        nlp = self.get_stanza_pipeline(stanza_code)
        combined = "\n\n".join(paragraphs)
        doc = nlp(combined)
        all_words = [w for sent in doc.sentences for w in sent.words]

        if not all_words or all_words[0].start_char is None:
            return self.sequential_stanza_extract(stanza_code, paragraphs)

        para_offsets = []
        current_idx = 0
        for p in paragraphs:
            start = combined.find(p, current_idx)
            if start == -1:
                start = current_idx
            para_offsets.append((start, start + len(p)))
            current_idx = start + len(p) + 2

        para_words = [[] for _ in paragraphs]
        for word in all_words:
            if word.start_char is not None:
                for i, (p_start, p_end) in enumerate(para_offsets):
                    if p_start <= word.start_char < p_end:
                        para_words[i].append({
                            "text": word.text, "lemma": word.lemma, "pos": word.pos,
                            "css": LanguageMapper.POS_CSS_MAP.get(word.pos, "pos-other")
                        })
                        break
        return para_words

    def sequential_stanza_extract(self, stanza_code, paragraphs):
        nlp = self.get_stanza_pipeline(stanza_code)
        para_words = []
        for p in paragraphs:
            doc = nlp(p)
            para_words.append([{"text": w.text, "lemma": w.lemma, "pos": w.pos, "css": LanguageMapper.POS_CSS_MAP.get(
                w.pos, "pos-other")} for sent in doc.sentences for w in sent.words])
        return para_words

    def back_translate_words(self, words, target_lang, source_lang):
        if not words:
            return []

        if target_lang in ['pt-BR', 'pt-PT']:
            target_lang = 'pt'
        if source_lang in ['pt-BR', 'pt-PT']:
            source_lang = 'pt'

        try:
            # We join words by a clear separator to do a single API call for speed
            text_bulk = " \n ".join(words)
            translated_bulk = GoogleTranslator(
                source=target_lang, target=source_lang).translate(text_bulk)
            if translated_bulk:
                translated_words = [w.strip()
                                    for w in translated_bulk.split('\n')]
                if len(translated_words) == len(words):
                    return translated_words
            # Fallback to true batching if newline splitting fails
            return GoogleTranslator(source=target_lang, target=source_lang).translate_batch(words)
        except Exception as e:
            print(f"Back-translation error: {e}")
            return [""] * len(words)

    def get_romanization(self, text, codes):
        google_code = codes["google"]
        translit_lang = codes.get("translit_lang")
        # 3. Update Pinyin extraction to keep tone marks
        if google_code in ['zh-CN', 'zh-TW'] and HAS_PINYIN:
            return ' '.join([item[0] for item in pinyin(text)])
        elif google_code == 'ja' and HAS_KAKASI:
            return ' '.join([item['hepburn'] for item in kks.convert(text)])
        elif google_code == 'ko' and HAS_HANGUL:
            return hangul_transliter.translit(text)
        elif google_code == 'ar':
            return simple_arabic_romanize(text)
        elif translit_lang and HAS_TRANSLITERATE:
            try:
                return transliterate.translit(text, translit_lang, reversed=True)
            except Exception:
                pass

                # Global IPA Fallback for everything else (French, German, Hindi, Turkish, etc.)
        if HAS_PHONEMIZER:
            # Map Google codes to espeak language codes
            espeak_map = {
                'fr': 'fr-fr', 'it': 'it', 'es': 'es', 'pt': 'pt', 'pt-BR': 'pt-br',
                'de': 'de', 'ro': 'ro', 'hu': 'hu', 'pl': 'pl', 'tr': 'tr',
                'hi': 'hi', 'ga': 'ga', 'ru': 'ru', 'bg': 'bg', 'el': 'el'
            }

            es_code = espeak_map.get(google_code)
            if es_code:
                try:
                    # Generate IPA without word boundaries/stress marks for cleaner UI
                    ipa = phonemize(
                        text,
                        language=es_code,
                        backend='espeak',
                        separator=Separator(phone='', word=' ', syllable=''),
                        strip=True,
                        preserve_punctuation=True
                    )
                    return f"/{ipa}/"
                except Exception as e:
                    print(f"Phonemizer error for {text}: {e}")
                    return ""

        return ""

    def get_dictionary_definition(self, word, stanza_pos=None):
        if not word:
            return "No definition found."

        # Map Stanza UPOS tags to Dictionary API POS terms
        pos_map = {
            'NOUN': 'noun', 'VERB': 'verb', 'ADJ': 'adjective',
            'ADV': 'adverb', 'PRON': 'pronoun', 'ADP': 'preposition',
            'CCONJ': 'conjunction', 'SCONJ': 'conjunction', 'INTJ': 'interjection'
        }
        target_pos = pos_map.get(stanza_pos) if stanza_pos else None

        parts = word.split()
        definitions = []

        for part in parts:
            clean_part = ''.join(c for c in part if c.isalnum()).lower()
            if not clean_part:
                continue

            try:
                url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{clean_part}"
                response = requests.get(url, timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        meanings = data[0].get('meanings', [])
                        found_def = ""

                        # Attempt to find the definition that matches our Stanza POS tag
                        if target_pos:
                            for meaning in meanings:
                                if meaning.get('partOfSpeech') == target_pos:
                                    defs = meaning.get('definitions', [])
                                    if defs:
                                        found_def = defs[0].get(
                                            'definition', '')
                                        break

                        # Fallback: if no POS match was found, just grab the first available definition
                        if not found_def and meanings:
                            defs = meanings[0].get('definitions', [])
                            if defs:
                                found_def = defs[0].get('definition', '')

                        if found_def:
                            if len(parts) > 1:
                                definitions.append(
                                    f"({clean_part}) {found_def}")
                            else:
                                definitions.append(found_def)
            except Exception as e:
                print(f"Dictionary API error for '{clean_part}': {e}")
                continue

        if definitions:
            return " | ".join(definitions)

        return "No definition found."

    def translate_text(self, text, source_lang, target_lang):
        if target_lang in ['pt-BR', 'pt-PT']:
            target_lang = 'pt'
        if source_lang in ['pt-BR', 'pt-PT']:
            source_lang = 'pt'
        try:
            return GoogleTranslator(source=source_lang, target=target_lang).translate(text)
        except Exception as e:
            print(f"Translation error: {source_lang} --> {e}")
            return text
