# engine.py
import json
import hashlib
import asyncio
import edge_tts
from pathlib import Path
from config import LanguageMapper
from core import NLPProcessor


def get_tts_cache_paths(text, voice, lang_code, output_dir):
    key = f"{text}_{voice}"
    hash_str = hashlib.md5(key.encode('utf-8')).hexdigest()[:12]
    audio_path = output_dir / f"tts_{lang_code}_{hash_str}.mp3"
    json_path = output_dir / f"tts_{lang_code}_{hash_str}.json"
    return audio_path, json_path


def get_para_cache_path(source_text, lang_code, output_dir):
    hash_str = hashlib.md5(
        f"{source_text}_{lang_code}".encode('utf-8')).hexdigest()[:16]
    return output_dir / f"para_{lang_code}_{hash_str}.json"


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
                word_boundaries.append({"text": event["text"], "start": event["offset"] // 10000, "end": (
                    event["offset"] + event["duration"]) // 10000})
            elif event["type"] == "SentenceBoundary" or event["type"] == "sentence_boundary":
                pass
            elif event["type"] == "error":
                print("Error:", event)
                break

    return word_boundaries


def generate_and_cache_tts(source_text, translated_text, voice, lang_code, output_dir):
    audio_path, json_path = get_tts_cache_paths(
        translated_text, voice, lang_code, output_dir)
    if audio_path.exists() and json_path.exists():
        print(
            f"   [Cache Hit] Using cached audio for: {translated_text[:30]}...")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Handle backward compatibility in case old cache files just have arrays
            timestamps = data.get("timestamps", data) if isinstance(
                data, dict) else data
        return audio_path.name, timestamps

    print(f"   [Cache Miss] Generating TTS for: {translated_text[:30]}...")
    timestamps = asyncio.run(_generate_tts_stream(
        translated_text, voice, audio_path))

    # Dump full contextual JSON data for the TTS file
    rich_cache_payload = {
        "source_text": source_text,
        "target_text": translated_text,
        "language": lang_code,
        "voice": voice,
        "timestamps": timestamps
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(rich_cache_payload, f, indent=2, ensure_ascii=False)

    return audio_path.name, timestamps


class PolyglotEngine:
    def __init__(self, output_dir="output", project_name="multi_lang_reader"):
        self.output_dir = Path(output_dir) / project_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.project_name = project_name
        self.nlp = NLPProcessor()

    def process_batch(self, paragraphs, source_lang, target_languages):
        print(f"\n--- Processing Batch of {len(paragraphs)} Paragraphs ---")
        batch_data = [{"source_text": p, "source_lang": source_lang,
                       "languages": {}} for i, p in enumerate(paragraphs)]

        # 1. Quick check: Is EVERYTHING cached?
        all_cached = True
        for lang in target_languages:
            codes = LanguageMapper.get_codes(lang)
            for p in paragraphs:
                if not get_para_cache_path(p, codes["google"], self.output_dir).exists():
                    all_cached = False
                    break
            if not all_cached:
                break

        if all_cached:
            print(
                "✅ All paragraphs fully cached! Skipping all NLP, Translation, and TTS.")
            for i, p in enumerate(paragraphs):
                for lang in target_languages:
                    codes = LanguageMapper.get_codes(lang)
                    cache_path = get_para_cache_path(
                        p, codes["google"], self.output_dir)
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        batch_data[i]["languages"][lang] = json.load(f)
            return batch_data

        # 2. Process missing data
        src_codes = LanguageMapper.get_codes(source_lang)
        print(" -> Batch processing source text with Stanza...")
        src_para_words = None

        unique_src_words = set(w["text"]
                               for p_words in src_para_words for w in p_words)
        definitions_cache = {sw: self.nlp.get_dictionary_definition(
            sw) for sw in unique_src_words} if src_codes["google"] == "en" else {sw: "N/A" for sw in unique_src_words}

        for k, lang_name in enumerate(target_languages):

            codes = LanguageMapper.get_codes(lang_name)
            # Check if this specific language is fully cached on disk
            is_lang_cached = True
            for p in paragraphs:
                if not get_para_cache_path(p, codes["google"], self.output_dir).exists():
                    is_lang_cached = False
                    break

            if is_lang_cached:
                print(
                    f"   [Cache Hit] Language '{lang_name}' fully cached. Skipping NLP.")
                for i, p in enumerate(paragraphs):
                    cache_path = get_para_cache_path(
                        p, codes["google"], self.output_dir)
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        batch_data[i]["languages"][lang_name] = json.load(f)
                continue

            print(f" ({k})-> Preparing Target Language: {lang_name}")

            # Lazily load Source Stanza only when we know we have a cache miss
            if src_para_words is None:
                print(" -> Batch processing source text with Stanza...")
                src_para_words = self.nlp.batch_stanza_extract(
                    src_codes["stanza"], paragraphs)
                # Dictionary cache only needed if we are doing fresh processing
                unique_src_words = set(
                    w["text"] for p_words in src_para_words for w in p_words)
                definitions_cache = {sw: self.nlp.get_dictionary_definition(
                    sw) for sw in unique_src_words} if src_codes["google"] == "en" else {}

            translated_paragraphs = [self.nlp.translate_text(
                p, src_codes["google"], codes["google"]) for p in paragraphs]
            tgt_para_words = self.nlp.batch_stanza_extract(
                codes["stanza"], translated_paragraphs)

            for i, p in enumerate(paragraphs):
                cache_path = get_para_cache_path(
                    p, codes["google"], self.output_dir)
                if cache_path.exists():
                    print(f"   [Cache Hit] Loading cached paragraph data...")
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        batch_data[i]["languages"][lang_name] = json.load(f)
                    continue

                tgt_words = tgt_para_words[i]
                src_words = src_para_words[i]

                raw_tgt_strings = [w["text"] for w in tgt_words]

                back_translated = self.nlp.back_translate_words(
                    raw_tgt_strings,
                    target_lang=codes["google"],
                    source_lang=src_codes["google"]
                )

                tgt_to_src = {idx: text for idx,
                              text in enumerate(back_translated)}
                tgt_to_core = tgt_to_src  # Dictionary lookup will use the same back-translated word

                audio_filename, timestamps = generate_and_cache_tts(
                    p, translated_paragraphs[i], codes["tts"], codes["google"], self.output_dir)

                aligned_words = []
                ts_idx = 0
                for j, w in enumerate(tgt_words):
                    src_word = tgt_to_src.get(j, "")
                    core_word = tgt_to_core.get(j, "")
                    w_text = w["text"].lower()
                    start_time, end_time = 0, 0
                    if ts_idx < len(timestamps):
                        for k in range(ts_idx, min(ts_idx + 3, len(timestamps))):
                            if timestamps[k]["text"].lower() in w_text or w_text in timestamps[k]["text"].lower():
                                start_time, end_time = timestamps[k]["start"], timestamps[k]["end"]
                                ts_idx = k + 1
                                break
                    if start_time == 0 and end_time == 0 and len(aligned_words) > 0:
                        start_time = aligned_words[-1]["end"]
                        end_time = start_time

                    aligned_words.append({
                        "text": w["text"], "source_word": src_word, "start": start_time, "end": end_time,
                        "lemma": w["lemma"], "pos": w["pos"], "css": w["css"],
                        "romaji": self.nlp.get_romanization(w["text"], codes),
                        "definition": definitions_cache.get(core_word) or (
                            self.nlp.get_dictionary_definition(
                                core_word, stanza_pos=w["pos"]) if src_codes["google"] == "en" and core_word else "No definition found."
                        )
                    })

                # Create a complete textual reservoir for the cache
                cache_payload = {
                    "source_text": p,
                    "target_text": translated_paragraphs[i],
                    "source_lang": source_lang,
                    "target_lang": lang_name,
                    "google_code": codes["google"],
                    "stanza_code": codes["stanza"],
                    "audio_file": audio_filename,
                    "words": aligned_words,
                    "timestamps": timestamps
                }

                batch_data[i]["languages"][lang_name] = cache_payload

                # Save the comprehensive JSON cache
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(cache_payload, f, ensure_ascii=False, indent=2)

        return batch_data

    def generate_html_batch(self, batch_data, output_filename="index.html"):
        output_path = self.output_dir / output_filename
        json_str = json.dumps(batch_data)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(HTML_TEMPLATE.replace('__DATA_PLACEHOLDER__', json_str))
        print(f"\n✅ Success! HTML generated at: {output_path.absolute()}")


# ==========================================
# HTML / JS / CSS FRONTEND
# ==========================================
# [The HTML_TEMPLATE remains exactly the same as the previous version]
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interactive Polyglot Reader</title>
    <style>
        :root { --bg-color: #121212; --text-color: #e0e0e0; --panel-bg: #1e1e1e; --main-font: 2.0em; --source-font: 0.9em; --rom-font: 0.8em; --highlight: #f39c12; --accent: #007acc; --gap-source: 0.1em; --gap-romaji: 0.1em; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg-color); color: var(--text-color); display: flex; flex-direction: column; height: 100vh; margin: 0; overflow: hidden; }
        .top-bar { display: flex; align-items: center; gap: 15px; background: var(--panel-bg); padding: 15px 20px; border-bottom: 1px solid #333; z-index: 10; }
        .top-bar button, .top-bar select { padding: 8px 12px; background: #333; color: white; border: 1px solid #555; border-radius: 5px; cursor: pointer; font-size: 0.9em; }
        .btn-primary { background: var(--accent); border: none; font-weight: bold;}
        .btn-icon { background: transparent; border: none; font-size: 1.5em; color: #aaa; cursor: pointer; }
        input[type="range"] { flex: 1; cursor: pointer; accent-color: var(--highlight); }
        .time-display { font-size: 0.9em; color: #aaa; font-variant-numeric: tabular-nums; min-width: 40px; }
        .content-wrapper { display: flex; flex: 1; overflow: hidden; }
        #main-panel { flex: 1; display: flex; flex-direction: column; padding: 30px; overflow-y: auto; }
        .global-source-text { font-size: 1.2em; color: #888; margin-bottom: 30px; font-style: italic; border-left: 3px solid #444; padding-left: 15px; display: none; }
        .global-source-text.visible { display: block; }
        .chunk-container { margin-bottom: 40px; padding: 20px; background: #1a1a1a; border-radius: 10px; border: 1px solid #333; }
        .chunk-header { font-size: 1.2em; color: var(--accent); margin-bottom: 15px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 10px;}
        .target-text { display: flex; flex-wrap: wrap; line-height: 1.5; }
        .word-wrap { display: inline-flex; flex-direction: column; align-items: center; margin: 0 0.3em; padding: 0.1em 0.2em; cursor: pointer; border-radius: 6px; transition: 0.15s; }
        .word-wrap:hover { background: rgba(255,255,255,0.05); }
        .word-wrap.active { background: var(--highlight); color: #111 !important; transform: scale(1.05); }
        .word-wrap.active .word-source, .word-wrap.active .word-romaji { color: #333; }
        .word-source { font-size: var(--source-font); color: #888; font-style: italic; margin-bottom: var(--gap-source); min-height: 1.2em; line-height: 1.2; display: none; }
        .word-source.visible { display: block; }
        .word-source.empty { color: transparent !important; user-select: none; }
        .word-target { font-size: var(--main-font); font-weight: 500; }
        .word-romaji { font-size: var(--rom-font); color: #aaa; margin-top: var(--gap-romaji); }
        .word-romaji:empty { display: none !important; margin: 0 !important; padding: 0 !important; height: 0 !important; }
        .pos-noun { color: #4ec9b0; } .pos-verb { color: #dcdcaa; } .pos-adj { color: #9cdcfe; } .pos-adv { color: #c586c0; } .pos-pron { color: #ce9178; } .pos-other { color: #d4d4d4; }
        #side-panel { width: 300px; background: var(--panel-bg); padding: 20px; border-left: 1px solid #333; overflow-y: auto; }
        .dict-card { background: #2a2a2a; padding: 20px; border-radius: 10px; }
        .dict-word { font-size: 2em; margin: 0 0 10px 0; color: var(--highlight); }
        .badge { background: #444; padding: 4px 8px; border-radius: 4px; font-size: 0.8em; text-transform: uppercase; margin-right: 5px;}
        .modal { display: none; position: fixed; z-index: 100; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.7); }
        .modal-content { background: #222; margin: 5% auto; padding: 30px; border: 1px solid #444; width: 500px; max-width: 90%; border-radius: 10px; max-height: 80vh; overflow-y: auto; }
        .close-btn { color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; }
        .setting-group { margin-bottom: 20px; }
        .setting-group label { display: block; margin-bottom: 8px; color: #ccc; font-weight: bold; }
        .setting-group input[type="range"] { width: 100%; }
        .checkbox-group { max-height: 250px; overflow-y: auto; background: #1a1a1a; padding: 10px; border-radius: 5px; border: 1px solid #444; }
        .checkbox-group label { display: block; margin: 5px 0; font-weight: normal; cursor: pointer; }
        @media (max-width: 768px) { .content-wrapper { flex-direction: column; } #side-panel { width: 100%; height: 250px; border-left: none; border-top: 1px solid #333; } }
    </style>
</head>
<body>
<div class="top-bar">
    <button id="prev-btn" class="btn-icon" title="Previous Paragraph">⏮</button>
    <span id="page-indicator" style="color: #aaa; font-size: 0.9em; min-width: 60px; text-align: center;">1 / 1</span>
    <button id="next-btn" class="btn-icon" title="Next Paragraph">⏭</button>
    <div style="flex: 1;"></div>
    <button id="play-btn" class="btn-primary">▶ Play</button>
    <span class="time-display" id="time-current">0:00</span>
    <input type="range" id="seek-bar" value="0" min="0" max="100" step="0.1" style="max-width: 200px;">
    <span class="time-display" id="time-total">0:00</span>
    <select id="speed-selector" title="Global Playback Speed">
        <option value="0.5">0.5x</option><option value="0.75">0.75x</option>
        <option value="1" selected>1.0x</option><option value="1.25">1.25x</option>
    </select>
    <button id="settings-btn" class="btn-icon" title="Settings">⚙️</button>
</div>
<div class="content-wrapper">
    <div id="main-panel">
        <div id="global-source" class="global-source-text"></div>
        <div id="lang-display-area"></div>
    </div>
    <div id="side-panel">
        <h2 style="margin-top:0; border-bottom: 1px solid #444; padding-bottom: 10px;">Dictionary</h2>
        <div id="dict-container" class="dict-card" style="display:none;">
            <h1 class="dict-word" id="dict-title">Word</h1>
            <div style="margin-bottom: 15px;">
                <span class="badge" id="dict-pos">POS</span>
                <span class="badge" id="dict-rom" style="background: #007acc;">Romaji</span>
            </div>
            <p style="color: #888; font-size: 0.9em; margin-bottom: 5px;">Dictionary Form (Lemma):</p>
            <strong id="dict-lemma" style="font-size: 1.2em; display: block; margin-bottom: 15px;"></strong>
            <p style="color: #888; font-size: 0.9em; margin-bottom: 5px;">Definition:</p>
            <p id="dict-definition" style="font-size: 1.1em; line-height: 1.5; color: #e0e0e0; margin: 0;"></p>
        </div>
        <p id="dict-instruction" style="color: #666; text-align: center; margin-top: 30px;">Click any word to see details.</p>
    </div>
</div>
<div id="settings-modal" class="modal">
    <div class="modal-content">
        <span class="close-btn" id="close-settings">&times;</span>
        <h2>Reader Settings</h2>
        <div class="setting-group"><label>Target Languages:</label><div class="checkbox-group" id="target-checks-container"></div></div>
        <div class="setting-group"><label>Word Click Speed: <span id="word-speed-val">1.0x</span></label><input type="range" id="word-speed-selector" min="0.25" max="1" step="0.05" value="1"></div>
        <div class="setting-group"><label>Main Target Font Size: <span id="main-font-val">2.0em</span></label><input type="range" id="main-font-slider" min="1.2" max="4.0" step="0.1" value="2.0"></div>
        <div class="setting-group"><label>Source Word Font Size: <span id="source-font-val">0.9em</span></label><input type="range" id="source-font-slider" min="0.5" max="1.5" step="0.1" value="0.9"></div>
        <div class="setting-group"><label>Romaji/Pinyin Font Size: <span id="rom-font-val">0.8em</span></label><input type="range" id="rom-font-slider" min="0.5" max="1.5" step="0.1" value="0.8"></div>
        <div class="setting-group"><label>Gap (Source to Target): <span id="gap-source-val">0.1em</span></label><input type="range" id="gap-source-slider" min="0" max="1.0" step="0.05" value="0.1"></div>
        <div class="setting-group"><label>Gap (Target to Romaji): <span id="gap-romaji-val">0.1em</span></label><input type="range" id="gap-romaji-slider" min="0" max="1.0" step="0.05" value="0.1"></div>
        <div class="setting-group">
            <label><input type="checkbox" id="toggle-source-sentence" checked> Show Full Source Sentence at Top</label>
            <label><input type="checkbox" id="toggle-source-words" checked> Show Source Words Above Target Words</label>
        </div>
        <button id="apply-settings" class="btn-primary" style="width: 100%; padding: 12px; font-size: 1.1em;">Apply & Render</button>
    </div>
</div>
<audio id="audio-player"></audio>
<script>
    const allParagraphs = __DATA_PLACEHOLDER__;
    let currentParaIndex = 0;
    let appData = allParagraphs[currentParaIndex];
    const audio = document.getElementById('audio-player');
    const playBtn = document.getElementById('play-btn');
    const seekBar = document.getElementById('seek-bar');
    const displayArea = document.getElementById('lang-display-area');
    const globalSource = document.getElementById('global-source');
    let currentLang = null;
    let currentTimestamps = [];
    let animationFrameId = null;
    let partialPlayListener = null;

    function init() {
        const targetContainer = document.getElementById('target-checks-container');
        let checksHtml = '<label><input type="checkbox" id="check-all" checked> <strong>ALL</strong></label>';
        Object.keys(appData.languages).forEach(l => { checksHtml += `<label><input type="checkbox" class="target-check" value="${l}" checked> ${l}</label>`; });
        targetContainer.innerHTML = checksHtml;
        document.getElementById('check-all').addEventListener('change', (e) => { document.querySelectorAll('.target-check').forEach(cb => cb.checked = e.target.checked); });
        document.getElementById('settings-btn').addEventListener('click', () => document.getElementById('settings-modal').style.display = 'block');
        document.getElementById('close-settings').addEventListener('click', () => document.getElementById('settings-modal').style.display = 'none');
        document.getElementById('apply-settings').addEventListener('click', () => { document.getElementById('settings-modal').style.display = 'none'; renderContent(); });
        ['main-font', 'source-font', 'rom-font', 'gap-source', 'gap-romaji'].forEach(id => { setupSlider(`${id}-slider`, `${id}-val`, `--${id}`, 'em'); });
        document.getElementById('word-speed-selector').addEventListener('input', (e) => { document.getElementById('word-speed-val').innerText = e.target.value + 'x'; });
        document.getElementById('toggle-source-sentence').addEventListener('change', (e) => { globalSource.classList.toggle('visible', e.target.checked); });
        document.getElementById('toggle-source-words').addEventListener('change', (e) => { document.querySelectorAll('.word-source').forEach(el => el.classList.toggle('visible', e.target.checked)); });
        document.getElementById('prev-btn').addEventListener('click', () => { if (currentParaIndex > 0) { currentParaIndex--; appData = allParagraphs[currentParaIndex]; renderContent(); } });
        document.getElementById('next-btn').addEventListener('click', () => { if (currentParaIndex < allParagraphs.length - 1) { currentParaIndex++; appData = allParagraphs[currentParaIndex]; renderContent(); } });
        setupAudioControls();
        renderContent();
    }
    function setupSlider(sliderId, valId, cssVar, unit) {
        const slider = document.getElementById(sliderId);
        slider.addEventListener('input', (e) => {
            document.getElementById(valId).innerText = e.target.value + unit;
            document.documentElement.style.setProperty(cssVar, e.target.value + unit);
        });
    }
    function renderContent() {
        audio.pause(); audio.currentTime = 0; playBtn.innerText = '▶ Play';
        currentLang = null; currentTimestamps = [];
        document.getElementById('dict-container').style.display = 'none';
        document.getElementById('dict-instruction').style.display = 'block';
        displayArea.innerHTML = '';
        const selectedTargets = Array.from(document.querySelectorAll('.target-check:checked')).map(cb => cb.value);
        globalSource.innerText = appData.source_text;
        globalSource.classList.toggle('visible', document.getElementById('toggle-source-sentence').checked);
        const showSourceWords = document.getElementById('toggle-source-words').checked;
        document.getElementById('page-indicator').innerText = `${currentParaIndex + 1} / ${allParagraphs.length}`;
        document.getElementById('prev-btn').style.opacity = currentParaIndex === 0 ? '0.3' : '1';
        document.getElementById('next-btn').style.opacity = currentParaIndex === allParagraphs.length - 1 ? '0.3' : '1';
        if (selectedTargets.length === 0) {
            displayArea.innerHTML = '<p style="color:#888; text-align:center; margin-top:50px;">Please select at least one target language in Settings.</p>';
            return;
        }
        selectedTargets.forEach(lang => {
            const langData = appData.languages[lang];
            const chunk = document.createElement('div');
            chunk.className = 'chunk-container';
            chunk.innerHTML = `<div class="chunk-header">${lang}</div>`;
            const targetDiv = document.createElement('div');
            targetDiv.className = 'target-text';
            langData.words.forEach((w, wordIdx) => {
                const globalId = `w-${lang}-${wordIdx}`;
                const span = document.createElement('span');
                span.className = `word-wrap ${w.css}`;
                span.id = globalId;
                const isEmpty = !w.source_word;
                const srcClass = isEmpty ? 'empty' : '';
                const srcText = w.source_word || '&nbsp;';
                span.innerHTML = `
                    <div class="word-source ${srcClass} ${showSourceWords ? 'visible' : ''}">${srcText}</div>
                    <div class="word-target">${w.text}</div>
                    <div class="word-romaji">${w.romaji || ''}</div>
                `;
                span.addEventListener('click', () => handleWordClick(lang, wordIdx, span, w));
                targetDiv.appendChild(span);
            });
            chunk.appendChild(targetDiv);
            displayArea.appendChild(chunk);
        });
    }
    function handleWordClick(lang, idx, span, w) {
        document.querySelectorAll('.word-wrap').forEach(el => el.classList.remove('active'));
        span.classList.add('active');
        updateSidebar(span, w);
        if (currentLang !== lang) {
            currentLang = lang;
            audio.src = appData.languages[lang].audio_file;
            audio.load();
            currentTimestamps = appData.languages[lang].words.map((word, i) => ({ id: `w-${lang}-${i}`, start: word.start, end: word.end }));
        }
        playWordPartial(w);
    }
    function playWordPartial(w) {
        audio.pause();
        if (partialPlayListener) audio.removeEventListener('timeupdate', partialPlayListener);
        const wordSpeed = parseFloat(document.getElementById('word-speed-selector').value);
        audio.playbackRate = wordSpeed;
        audio.currentTime = w.start / 1000;
        audio.play();
        playBtn.innerText = '⏸ Pause';
        const endTime = w.end / 1000;
        partialPlayListener = () => {
            if (audio.currentTime >= endTime) {
                audio.pause();
                audio.playbackRate = parseFloat(document.getElementById('speed-selector').value);
                playBtn.innerText = '▶ Play';
                audio.removeEventListener('timeupdate', partialPlayListener);
            }
        };
        audio.addEventListener('timeupdate', partialPlayListener);
    }
    function setupAudioControls() {
        playBtn.addEventListener('click', () => {
            if (audio.paused) {
                if (partialPlayListener) audio.removeEventListener('timeupdate', partialPlayListener);
                audio.playbackRate = parseFloat(document.getElementById('speed-selector').value);
                audio.play(); playBtn.innerText = '⏸ Pause'; syncEngine();
            } else { audio.pause(); playBtn.innerText = '▶ Play'; cancelAnimationFrame(animationFrameId); }
        });
        audio.addEventListener('loadedmetadata', () => {
            seekBar.max = audio.duration;
            document.getElementById('time-total').innerText = formatTime(audio.duration);
        });
        audio.addEventListener('timeupdate', () => {
            if(!audio.paused) {
                seekBar.value = audio.currentTime;
                document.getElementById('time-current').innerText = formatTime(audio.currentTime);
            }
        });
        seekBar.addEventListener('input', () => { audio.currentTime = seekBar.value; });
        document.getElementById('speed-selector').addEventListener('change', (e) => { if(!audio.paused) audio.playbackRate = parseFloat(e.target.value); });
    }
    function syncEngine() {
        const currentTimeMs = audio.currentTime * 1000;
        highlightCurrentWord(currentTimeMs);
        if (!audio.paused) { animationFrameId = requestAnimationFrame(syncEngine); }
    }
    function highlightCurrentWord(currentTimeMs) {
        const activeWord = currentTimestamps.find(ts => currentTimeMs >= ts.start && currentTimeMs <= ts.end && ts.end > 0);
        if (activeWord) {
            const el = document.getElementById(activeWord.id);
            if (el && !el.classList.contains('active')) {
                document.querySelectorAll('.word-wrap').forEach(el => el.classList.remove('active'));
                el.classList.add('active');
            }
        }
    }
    function updateSidebar(span, w) {
        document.getElementById('dict-instruction').style.display = 'none';
        document.getElementById('dict-container').style.display = 'block';
        document.getElementById('dict-title').innerText = w.text;
        document.getElementById('dict-pos').innerText = w.pos;
        document.getElementById('dict-lemma').innerText = w.lemma;
        document.getElementById('dict-definition').innerText = w.definition || "No definition available.";
        const romBadge = document.getElementById('dict-rom');
        if(w.romaji) { romBadge.style.display = 'inline-block'; romBadge.innerText = w.romaji; } else { romBadge.style.display = 'none'; }
    }
    function formatTime(seconds) {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    }
    init();
</script>
</body>
</html>"""

# ==========================================
# EXECUTION
# ==========================================
if __name__ == "__main__":
    engine = PolyglotEngine(output_dir="my_library",
                            project_name="polyglot_master")

    lesson_paragraphs = [
        "The curious cat slowly walked across the old wooden bridge.",
        "It was a bright sunny day, and the birds were singing in the trees.",
        "Suddenly, a bright blue butterfly fluttered past the cat's nose."
    ]

    source_language = 'English'
    target_languages = [
        'French', 'Italian', 'Spanish', 'Portuguese', 'German', 'Romanian',
        'Hungarian', 'Polish', 'Bulgarian', 'Greek', 'Russian',
        'Chinese', 'Japanese', 'Korean', 'Hindi', 'Arabic', 'Irish', 'Turkish'
    ]

    print(
        f"🌍 Mapper found {len(LanguageMapper.get_available_languages())} fully supported languages.")
    print(
        f"🚀 Starting processing for {len(target_languages)} specific languages. Caching is enabled.\n")

    final_data_batch = engine.process_batch(
        lesson_paragraphs, source_language, target_languages)
    engine.generate_html_batch(final_data_batch, output_filename="index.html")
