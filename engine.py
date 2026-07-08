# engine.py
import json
import hashlib
import asyncio
import edge_tts
from pathlib import Path
from config import LanguageMapper
from core import NLPProcessor
from html_template import get_html_template
import logging


def get_tts_cache_paths(text, voice, lang_code, output_dir):
    key = f"{text}_{voice}"
    hash_str = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    audio_path = output_dir / f"tts_{lang_code}_{hash_str}.mp3"
    json_path = output_dir / f"tts_{lang_code}_{hash_str}.json"
    return audio_path, json_path


def get_sentence_cache_path(source_text, lang_code, output_dir):
    hash_str = hashlib.md5(f"{source_text}_{lang_code}".encode("utf-8")).hexdigest()[
        :16
    ]
    return output_dir / f"sentence_{lang_code}_{hash_str}.json"


async def _generate_tts_stream(text, voice, audio_path):
    communicate = edge_tts.Communicate(text, voice)
    word_boundaries = []
    with open(audio_path, "wb") as fp:
        async for event in communicate.stream():
            if event["type"] == "audio":
                fp.write(event["data"])
            # Note that WordBoundaries seem to be disabled to be able to spoof edge
            elif event["type"] == "WordBoundary" or event["type"] == "word_boundary":
                # print("Event:", event)
                word_boundaries.append(
                    {
                        "text": event["text"],
                        "start": event["offset"] // 10000,
                        "end": (event["offset"] + event["duration"]) // 10000,
                    }
                )
            elif (
                event["type"] == "SentenceBoundary"
                or event["type"] == "sentence_boundary"
            ):
                pass
            elif event["type"] == "error":
                print("Error:", event)
                break

    return word_boundaries


def generate_and_cache_tts(source_text, translated_text, voice, lang_code, output_dir):
    audio_path, json_path = get_tts_cache_paths(
        translated_text, voice, lang_code, output_dir
    )
    if audio_path.exists() and json_path.exists():
        print(f"   [Cache Hit] Using cached audio for: {translated_text[:30]}...")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Handle backward compatibility in case old cache files just have arrays
            timestamps = (
                data.get("timestamps", data) if isinstance(data, dict) else data
            )
        return audio_path.name, timestamps

    # If the text is empty after stripping markers, skip generating audio
    if not translated_text.strip():
        return "", []

    print(f"   [Cache Miss] Generating TTS for: {translated_text[:30]}...")
    timestamps = asyncio.run(_generate_tts_stream(translated_text, voice, audio_path))

    # Dump full contextual JSON data for the TTS file
    rich_cache_payload = {
        "source_text": source_text,
        "target_text": translated_text,
        "language": lang_code,
        "voice": voice,
        "timestamps": timestamps,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rich_cache_payload, f, indent=2, ensure_ascii=False)

    return audio_path.name, timestamps


class PolyglotEngine:
    def __init__(self, output_dir="output", project_name="multi_lang_reader"):
        self.output_dir = Path(output_dir) / project_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.project_name = project_name
        self.nlp = NLPProcessor()

    def process_batch(self, structural_blocks, source_lang, target_languages):
        print(f"\n--- Processing Batch of {len(structural_blocks)} Sentences ---")

        batch_data = []
        for block in structural_blocks:
            if block["type"] == "text":
                batch_data.append({
                    "type": "text",
                    "source_text": block["text"],
                    "format": block["format"],         # Extracted cleanly
                    "alignment": block["alignment"],   # Extracted cleanly
                    "paragraph_index": block["paragraph_index"],
                    "source_lang": source_lang,
                    "languages": {}
                })
            elif block["type"] == "image":
                # Pass images straight through without NLP processing
                batch_data.append(block)

        sentences = [block["source_text"] for block in batch_data if block["type"] == "text"]

        # 1. Quick check: Is EVERYTHING cached?
        all_cached = True
        for lang in target_languages:
            codes = LanguageMapper.get_codes(lang)
            for p in sentences:
                if not get_sentence_cache_path(
                    p, codes["google"], self.output_dir
                ).exists():
                    all_cached = False
                    break
            if not all_cached:
                break

        if all_cached:
            print(
                "✅ All sentences fully cached! Skipping all NLP, Translation, and TTS."
            )
            for i, p in enumerate(sentences):
                for lang in target_languages:
                    codes = LanguageMapper.get_codes(lang)
                    cache_path = get_sentence_cache_path(
                        p, codes["google"], self.output_dir
                    )
                    with open(cache_path, "r", encoding="utf-8") as f:
                        batch_data[i]["languages"][lang] = json.load(f)
            return batch_data

        # 2. Process missing data
        src_codes = LanguageMapper.get_codes(source_lang)
        print(" -> Batch processing source text with Stanza...")
        src_sentence_words = None
        src_sentence_words = self.nlp.batch_stanza_extract(src_codes["stanza"], sentences)

        unique_src_words = set(w["text"] for p_words in src_sentence_words for w in p_words)
        definitions_cache = (
            {sw: self.nlp.get_dictionary_definition(sw) for sw in unique_src_words}
            if src_codes["google"] == "en"
            else {sw: "N/A" for sw in unique_src_words}
        )

        for k, lang_name in enumerate(target_languages):

            codes = LanguageMapper.get_codes(lang_name)
            # Check if this specific language is fully cached on disk
            is_lang_cached = True
            for p in sentences:
                if not get_sentence_cache_path(
                    p, codes["google"], self.output_dir
                ).exists():
                    is_lang_cached = False
                    break

            if is_lang_cached:
                print(
                    f"   [Cache Hit] Language '{lang_name}' fully cached. Skipping NLP."
                )
                for i, p in enumerate(sentences):
                    cache_path = get_sentence_cache_path(
                        p, codes["google"], self.output_dir
                    )
                    with open(cache_path, "r", encoding="utf-8") as f:
                        batch_data[i]["languages"][lang_name] = json.load(f)
                continue

            print(f" ({k})-> Preparing Target Language: {lang_name}")

            # Lazily load Source Stanza only when we know we have a cache miss
            if src_sentence_words is None:
                print(" -> Batch processing source text with Stanza...")
                src_sentence_words = self.nlp.batch_stanza_extract(
                    src_codes["stanza"], sentences
                )
                # Dictionary cache only needed if we are doing fresh processing
                unique_src_words = set(
                    w["text"] for p_words in src_sentence_words for w in p_words
                )
                definitions_cache = (
                    {
                        sw: self.nlp.get_dictionary_definition(sw)
                        for sw in unique_src_words
                    }
                    if src_codes["google"] == "en"
                    else {}
                )

            translated_sentences = [
                self.nlp.translate_text(p, src_codes["google"], codes["google"])
                for p in sentences
            ]
            tgt_sentence_words = self.nlp.batch_stanza_extract(
                codes["stanza"], translated_sentences
            )

            for i, p in enumerate(sentences):
                cache_path = get_sentence_cache_path(p, codes["google"], self.output_dir)
                if cache_path.exists():
                    print(f"   [Cache Hit] Loading cached sentence data...")
                    with open(cache_path, "r", encoding="utf-8") as f:
                        batch_data[i]["languages"][lang_name] = json.load(f)
                    continue

                tgt_words = tgt_sentence_words[i]
                src_words = src_sentence_words[i]

                raw_tgt_strings = [w["text"] for w in tgt_words]

                back_translated = self.nlp.back_translate_words(
                    raw_tgt_strings,
                    target_lang=codes["google"],
                    source_lang=src_codes["google"],
                )

                tgt_to_src = {idx: text for idx, text in enumerate(back_translated)}
                tgt_to_core = tgt_to_src  # Dictionary lookup will use the same back-translated word

                audio_filename, timestamps = generate_and_cache_tts(
                    p,
                    translated_sentences[i],
                    codes["tts"],
                    codes["google"],
                    self.output_dir,
                )

                aligned_words = []
                ts_idx = 0
                for j, w in enumerate(tgt_words):
                    src_word = tgt_to_src.get(j, "")
                    core_word = tgt_to_core.get(j, "")
                    w_text = w["text"].lower()
                    start_time, end_time = 0, 0
                    if ts_idx < len(timestamps):
                        for k in range(ts_idx, min(ts_idx + 3, len(timestamps))):
                            if (
                                timestamps[k]["text"].lower() in w_text
                                or w_text in timestamps[k]["text"].lower()
                            ):
                                start_time, end_time = (
                                    timestamps[k]["start"],
                                    timestamps[k]["end"],
                                )
                                ts_idx = k + 1
                                break
                    if start_time == 0 and end_time == 0 and len(aligned_words) > 0:
                        start_time = aligned_words[-1]["end"]
                        end_time = start_time

                    aligned_words.append(
                        {
                            "text": w["text"],
                            "source_word": src_word,
                            "start": start_time,
                            "end": end_time,
                            "lemma": w["lemma"],
                            "pos": w["pos"],
                            "css": w["css"],
                            "romaji": self.nlp.get_romanization(w["text"], codes),
                            "definition": definitions_cache.get(core_word)
                            or (
                                self.nlp.get_dictionary_definition(
                                    core_word, stanza_pos=w["pos"]
                                )
                                if src_codes["google"] == "en" and core_word
                                else "No definition found."
                            ),
                        }
                    )

                # Create a complete textual reservoir for the cache
                cache_payload = {
                    "source_text": p,
                    "target_text": translated_sentences[i],
                    "source_lang": source_lang,
                    "target_lang": lang_name,
                    "google_code": codes["google"],
                    "stanza_code": codes["stanza"],
                    "audio_file": audio_filename,
                    "words": aligned_words,
                    "timestamps": timestamps,
                }

                batch_data[i]["languages"][lang_name] = cache_payload

                # Save the comprehensive JSON cache
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(cache_payload, f, ensure_ascii=False, indent=2)

        return batch_data

    def generate_html_batch(self, batch_data, output_filename="index.html"):
        output_path = self.output_dir / output_filename

        # 1. Identify all target languages in the batch
        target_langs = []
        if batch_data and "languages" in batch_data[0]:
            target_langs = list(batch_data[0]["languages"].keys())

        # 2. Pivot structural layout (Language -> Paragraphs -> Sentences -> Words)
        language_centric_data = []
        for lang in target_langs:
            paragraphs_map = {}

            for paragraph_data in batch_data:
                # Detect structural paragraph index mapping; default to a single flow if missing
                p_idx = paragraph_data.get("paragraph_index", paragraph_data.get("para_index", 0))

                if p_idx not in paragraphs_map:
                    paragraphs_map[p_idx] = {
                        "paragraph_index": p_idx,
                        "sentences": []
                    }

                if lang in paragraph_data["languages"]:
                    lang_sentence = paragraph_data["languages"][lang]
                    lang_sentence["source_text"] = paragraph_data.get("source_text", "")
                    paragraphs_map[p_idx]["sentences"].append(lang_sentence)

            # Reassemble ordered list of paragraphs to match source sequence
            sorted_paragraphs = [paragraphs_map[k] for k in sorted(paragraphs_map.keys())]

            language_centric_data.append({
                "language": lang,
                "paragraphs": sorted_paragraphs
            })

        # 3. Inject payload into UI frame
        json_str = json.dumps(language_centric_data, ensure_ascii=False)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", json_str))
        print(f"\n✅ Success! Book-layout HTML compiled at: {output_path.absolute()}")


# ==========================================
# HTML / JS / CSS FRONTEND
# ==========================================
# [The HTML_TEMPLATE remains exactly the same as the previous version]
HTML_TEMPLATE = get_html_template()


# ==========================================
# EXECUTION
# ==========================================
if __name__ == "__main__":
    engine = PolyglotEngine(output_dir="my_library", project_name="polyglot_master")

    lesson_paragraphs = [
        "The curious cat slowly walked across the old wooden bridge. What is hilarious is that the cat farted loudly, startling a flock of birds into the sky.",
        "It was a bright sunny day, and the birds were singing in the trees. The cooing of the doves and the chirping of the sparrows created a symphony of nature's music.",
        "Suddenly, a bright blue butterfly fluttered past the cat's nose. The cat leaped into the air, trying to catch the butterfly, but it was too quick and disappeared into the garden.",
    ]

    source_language = "English"
    target_languages = [
        "French",
        "Italian",
        "Spanish",
        "Portuguese",
        "German",
        "Romanian",
        "Hungarian",
        "Polish",
        "Bulgarian",
        "Greek",
        "Russian",
        "Chinese",
        "Japanese",
        "Korean",
        "Hindi",
        "Arabic",
        "Irish",
        "Turkish",
    ]

    target_languages = ["French", "Russian", "Japanese"]

    print(f"🌍 Mapper found {len(LanguageMapper.get_available_languages())} fully supported languages.")
    print(f"🚀 Starting processing for {len(target_languages)} specific languages. Caching is enabled.\n")

    final_data_batch = engine.process_batch(
        lesson_paragraphs, source_language, target_languages
    )
    engine.generate_html_batch(final_data_batch, output_filename="index.html")
