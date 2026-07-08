const languagesList = __DATA_PLACEHOLDER__;
const totalLanguages = languagesList.length;

let currentLangIndex = 0;
let currentLangData = null;
let allTimestamps = [];

// Virtual Timeline State
let globalDuration = 0;
let currentGlobalTime = 0;
let currentSentenceContext = null;

const audio = document.getElementById('audio-player');
const playBtn = document.getElementById('play-btn');
const seekBar = document.getElementById('seek-bar');
const displayArea = document.getElementById('lang-display-area');
const globalSource = document.getElementById('global-source');
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');
const pageIndicator = document.getElementById('page-indicator');

let animationFrameId = null;
let isPlaying = false;
let playbackSpeed = 1.0;

let enabledLanguages = new Set(languagesList.map((l, i) => i));
let showSourceSentence = true;
let showSourceWords = true;

function formatTime(ms) {
	if (!ms || ms < 0) return "0:00";
	const totalSeconds = Math.floor(ms / 1000);
	const minutes = Math.floor(totalSeconds / 60);
	const seconds = totalSeconds % 60;
	return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function updatePageIndicator() {
	const visibleLanguages = languagesList.filter((_, i) => enabledLanguages.has(i));
	const currentIndexInVisible = visibleLanguages.findIndex(l => l.language === currentLangData.language);
	pageIndicator.textContent = `${currentLangData.language} (${currentIndexInVisible + 1} / ${visibleLanguages.length})`;
}

function buildTimestampIndex(langData) {
	allTimestamps = [];
	globalDuration = 0;

	if (!langData || !langData.paragraphs) return;

	langData.paragraphs.forEach((para, paraIdx) => {
		para.sentences.forEach((sentence, sentenceIdx) => {
			let sentenceDuration = 0;

			if (sentence.words && sentence.words.length > 0) {
				const lastWord = sentence.words[sentence.words.length - 1];
				sentenceDuration = lastWord.end + 250;
			}

			sentence.globalStart = globalDuration;
			sentence.globalEnd = globalDuration + sentenceDuration;
			globalDuration += sentenceDuration;

			if (sentence.words) {
				sentence.words.forEach((word, wordIdx) => {
					allTimestamps.push({
						id: `p${paraIdx}-s${sentenceIdx}-w${wordIdx}`,
						localStart: word.start,
						localEnd: word.end,
						globalStart: sentence.globalStart + word.start,
						globalEnd: sentence.globalStart + word.end,
						paraIndex: paraIdx,
						sentenceIndex: sentenceIdx,
						wordIndex: wordIdx,
						audioFile: sentence.audio_file
					});
				});
			}
		});
	});

	seekBar.max = globalDuration || 1;
	document.getElementById('time-total').textContent = formatTime(globalDuration);
}


function renderLanguage(langData) {
	displayArea.innerHTML = '';
	globalSource.innerHTML = '';

	// 1. Regex and Magic Tags completely removed.

	let totalSourceText = [];
	langData.paragraphs.forEach(p => {
		// Only attempt to read sentences if this is a text block
		if (p.type === 'text' && p.sentences) {
			p.sentences.forEach(s => { if (s.source_text) totalSourceText.push(s.source_text); });
		}
	});

	if (totalSourceText.length > 0 && showSourceSentence) {
		globalSource.textContent = totalSourceText.join(' ');
		globalSource.classList.add('visible');
	} else {
		globalSource.classList.remove('visible');
	}

	langData.paragraphs.forEach((para, pIdx) => {

		// --- MEDIA HANDLING (Block Level) ---
		if (para.type === 'image') {
			const imgContainer = document.createElement('div');
			const alignClass = para.alignment ? `align-${para.alignment}` : 'align-left';
			imgContainer.className = `media-container ${alignClass}`;
			if (para.alignment) imgContainer.style.textAlign = para.alignment;

			const imgEl = document.createElement('img');
			imgEl.src = `images/${para.src}`; // Assuming standard relative path
			imgEl.className = 'epub-image';

			imgContainer.appendChild(imgEl);
			displayArea.appendChild(imgContainer);
			return; // Skip text rendering for this block
		}


		// Use the format metadata (h1, h2, p) for the HTML tag, default to div
		const tagName = (para.format && ['h1', 'h2', 'h3', 'h4', 'p'].includes(para.format)) ? para.format : 'div';
		const paraDiv = document.createElement(tagName);
		paraDiv.className = 'book-paragraph';

		// Apply alignment metadata directly
		if (para.alignment) {
			paraDiv.style.textAlign = para.alignment;
			paraDiv.classList.add(`text-${para.alignment}`);
		}

		// Render Sentences and Words
		if (para.sentences) {
			para.sentences.forEach((sentence, sIdx) => {
				const wordCount = sentence.words.length;

				sentence.words.forEach((word, wIdx) => {
					const wordWrap = document.createElement('div');
					wordWrap.className = 'word-wrap';
					wordWrap.dataset.paraIndex = pIdx;
					wordWrap.dataset.sentenceIndex = sIdx;
					wordWrap.dataset.wordIndex = wIdx;

					if (sIdx === 0 && wIdx === 0) {
						wordWrap.classList.add('para-start');
					}

					const backendClass = (word.css || word.pos || '').toLowerCase();

					if (backendClass.includes('punct') || /^[.,!?;:。、！？]+$/.test(word.text.trim())) {
						wordWrap.classList.add('is-punct');
					}
					if (wIdx === wordCount - 1) {
						wordWrap.classList.add('sentence-end');
					}

					// Top Line: Source Structure
					const sourceSpan = document.createElement('span');
					sourceSpan.className = 'word-source';
					if (!showSourceWords) {
						sourceSpan.style.display = 'none';
					} else {
						if (word.source_word) {
							sourceSpan.textContent = word.source_word;
						} else {
							sourceSpan.innerHTML = '&nbsp;';
							sourceSpan.classList.add('empty');
						}
					}
					wordWrap.appendChild(sourceSpan);

					// Middle Line: Target Structure
					const targetSpan = document.createElement('span');
					targetSpan.className = `word-target ${word.css || word.pos || ''}`.trim();
					targetSpan.textContent = word.text;
					wordWrap.appendChild(targetSpan);

					// Bottom Line: Romaji Structure
					const romajiSpan = document.createElement('span');
					romajiSpan.className = 'word-romaji';
					if (word.romaji) {
						romajiSpan.textContent = word.romaji;
					} else {
						romajiSpan.innerHTML = '&nbsp;';
						romajiSpan.classList.add('empty');
					}
					wordWrap.appendChild(romajiSpan);

					wordWrap.addEventListener('click', () => handleWordClick(word, sentence, pIdx, sIdx, wIdx));
					paraDiv.appendChild(wordWrap);
				});
			});
		}

		displayArea.appendChild(paraDiv);
	});

	updatePageIndicator();
}

function loadLanguage(index) {
	if (index < 0 || index >= languagesList.length) return;

	currentLangIndex = index;
	currentLangData = languagesList[index];

	buildTimestampIndex(currentLangData);
	renderLanguage(currentLangData);
	resetPlayback();

	if (currentLangData.paragraphs.length > 0 && currentLangData.paragraphs[0].sentences.length > 0) {
		currentSentenceContext = currentLangData.paragraphs[0].sentences[0];
		if (currentSentenceContext.audio_file) {
			audio.src = currentSentenceContext.audio_file;
			audio.playbackRate = playbackSpeed;
		}
	}
}

function seekAndPlayTarget(sentenceContext, localTimeMs, forcePlay = false) {
	currentSentenceContext = sentenceContext;
	const targetAudio = sentenceContext.audio_file;
	const currentFile = decodeURIComponent(audio.src.split('/').pop());

	if (currentFile !== targetAudio && targetAudio) {
		audio.src = targetAudio;
		audio.playbackRate = playbackSpeed;
		audio.load();

		const onMeta = () => {
			audio.currentTime = localTimeMs / 1000;
			if (isPlaying || forcePlay) {
				isPlaying = true;
				playBtn.textContent = '⏸ Pause';
				audio.play().catch(e => console.log(e));
				startProgressLoop();
			}
			audio.removeEventListener('loadedmetadata', onMeta);
		};
		audio.addEventListener('loadedmetadata', onMeta);
	} else {
		audio.currentTime = localTimeMs / 1000;
		if (isPlaying || forcePlay) {
			isPlaying = true;
			playBtn.textContent = '⏸ Pause';
			audio.play().catch(e => console.log(e));
			startProgressLoop();
		}
	}
}

function handleWordClick(word, sentence, pIdx, sIdx, wIdx) {
	document.querySelectorAll('.word-wrap').forEach(w => w.classList.remove('active'));

	const clickedElement = document.querySelector(`[data-para-index="${pIdx}"][data-sentence-index="${sIdx}"][data-word-index="${wIdx}"]`);
	if (clickedElement) clickedElement.classList.add('active');

	updateDictionary(word);

	if (word.start !== undefined && word.start >= 0) {
		seekAndPlayTarget(sentence, word.start, true);
	}
}

function updateDictionary(word) {
	const dictContainer = document.getElementById('dict-container');
	const dictInstruction = document.getElementById('dict-instruction');

	if (!word) {
		dictContainer.style.display = 'none';
		dictInstruction.style.display = 'block';
		return;
	}

	dictInstruction.style.display = 'none';
	dictContainer.style.display = 'block';

	document.getElementById('dict-title').textContent = word.text;
	document.getElementById('dict-pos').textContent = word.pos || 'N/A';
	document.getElementById('dict-rom').textContent = word.romaji || 'N/A';
	document.getElementById('dict-lemma').textContent = word.lemma || word.text;
	document.getElementById('dict-definition').textContent = word.definition || 'No definition available.';
}

function resetPlayback() {
	isPlaying = false;
	playBtn.textContent = '▶ Play';
	audio.pause();
	audio.currentTime = 0;
	seekBar.value = 0;
	document.getElementById('time-current').textContent = '0:00';
	currentGlobalTime = 0;
	if (animationFrameId) {
		cancelAnimationFrame(animationFrameId);
		animationFrameId = null;
	}
}

function startProgressLoop() {
	if (animationFrameId) cancelAnimationFrame(animationFrameId);

	function loop() {
		if (!isPlaying || !currentSentenceContext) return;

		const localTime = audio.currentTime * 1000;
		currentGlobalTime = currentSentenceContext.globalStart + localTime;

		if (currentGlobalTime > globalDuration) currentGlobalTime = globalDuration;

		document.getElementById('time-current').textContent = formatTime(currentGlobalTime);
		seekBar.value = currentGlobalTime;

		const currentFile = decodeURIComponent(audio.src.split('/').pop());
		const currentWord = allTimestamps.find(ts =>
			ts.audioFile === currentFile && localTime >= ts.localStart && localTime < ts.localEnd
		);

		if (currentWord) {
			document.querySelectorAll('.word-wrap').forEach(w => w.classList.remove('active'));
			const activeEl = document.querySelector(`[data-para-index="${currentWord.paraIndex}"][data-sentence-index="${currentWord.sentenceIndex}"][data-word-index="${currentWord.wordIndex}"]`);
			if (activeEl) {
				activeEl.classList.add('active');
				updateDictionary(currentLangData.paragraphs[currentWord.paraIndex].sentences[currentWord.sentenceIndex].words[currentWord.wordIndex]);
			}
		}

		animationFrameId = requestAnimationFrame(loop);
	}
	animationFrameId = requestAnimationFrame(loop);
}

audio.addEventListener('ended', () => {
	let foundNext = false;
	let pastCurrent = false;

	for (let p of currentLangData.paragraphs) {
		for (let s of p.sentences) {
			if (pastCurrent) {
				seekAndPlayTarget(s, 0, true);
				foundNext = true;
				break;
			}
			if (s === currentSentenceContext) {
				pastCurrent = true;
			}
		}
		if (foundNext) break;
	}

	if (!foundNext) resetPlayback();
});

playBtn.addEventListener('click', () => {
	if (isPlaying) {
		isPlaying = false;
		playBtn.textContent = '▶ Play';
		audio.pause();
		if (animationFrameId) cancelAnimationFrame(animationFrameId);
	} else {
		if (!currentSentenceContext && currentLangData.paragraphs.length > 0) {
			currentSentenceContext = currentLangData.paragraphs[0].sentences[0];
		}
		seekAndPlayTarget(currentSentenceContext, audio.currentTime * 1000, true);
	}
});

seekBar.addEventListener('input', () => {
	const targetGlobalTime = parseInt(seekBar.value);
	document.getElementById('time-current').textContent = formatTime(targetGlobalTime);

	let targetSentenceContext = null;
	let targetLocalTime = 0;

	for (let p of currentLangData.paragraphs) {
		for (let s of p.sentences) {
			if (targetGlobalTime >= s.globalStart && targetGlobalTime <= s.globalEnd) {
				targetSentenceContext = s;
				targetLocalTime = targetGlobalTime - s.globalStart;
				break;
			}
		}
		if (targetSentenceContext) break;
	}

	if (!targetSentenceContext && currentLangData.paragraphs.length > 0) {
		const lastP = currentLangData.paragraphs[currentLangData.paragraphs.length - 1];
		targetSentenceContext = lastP.sentences[lastP.sentences.length - 1];
		targetLocalTime = targetSentenceContext.globalEnd - targetSentenceContext.globalStart;
	}

	if (targetSentenceContext) {
		seekAndPlayTarget(targetSentenceContext, targetLocalTime, isPlaying);
	}
});

document.getElementById('speed-selector').addEventListener('change', (e) => {
	playbackSpeed = parseFloat(e.target.value);
	audio.playbackRate = playbackSpeed;
});

prevBtn.addEventListener('click', () => {
	let newIndex = currentLangIndex - 1;
	while (newIndex >= 0 && !enabledLanguages.has(newIndex)) { newIndex--; }
	if (newIndex >= 0) loadLanguage(newIndex);
});

nextBtn.addEventListener('click', () => {
	let newIndex = currentLangIndex + 1;
	while (newIndex < languagesList.length && !enabledLanguages.has(newIndex)) { newIndex++; }
	if (newIndex < languagesList.length) loadLanguage(newIndex);
});

// Config Panel Logic
const settingsModal = document.getElementById('settings-modal');
const settingsBtn = document.getElementById('settings-btn');
const closeSettings = document.getElementById('close-settings');
const applySettings = document.getElementById('apply-settings');

settingsBtn.addEventListener('click', () => {
	settingsModal.style.display = 'block';
	const checksContainer = document.getElementById('target-checks-container');
	checksContainer.innerHTML = '';
	languagesList.forEach((lang, idx) => {
		const label = document.createElement('label');
		const checkbox = document.createElement('input');
		checkbox.type = 'checkbox';
		checkbox.checked = enabledLanguages.has(idx);
		checkbox.onchange = () => {
			if (checkbox.checked) {
				enabledLanguages.add(idx);
			} else {
				enabledLanguages.delete(idx);
				if (currentLangIndex === idx && enabledLanguages.size > 0) {
					loadLanguage(Array.from(enabledLanguages)[0]);
				}
			}
		};
		label.appendChild(checkbox);
		label.appendChild(document.createTextNode(` ${lang.language}`));
		checksContainer.appendChild(label);
	});
});

closeSettings.addEventListener('click', () => settingsModal.style.display = 'none');
window.addEventListener('click', (e) => { if (e.target === settingsModal) settingsModal.style.display = 'none'; });

const mainFontSlider = document.getElementById('main-font-slider');
const mainFontVal = document.getElementById('main-font-val');
mainFontSlider.addEventListener('input', () => {
	mainFontVal.textContent = mainFontSlider.value + 'em';
	document.documentElement.style.setProperty('--main-font', mainFontSlider.value + 'em');
});

const sourceFontSlider = document.getElementById('source-font-slider');
const sourceFontVal = document.getElementById('source-font-val');
sourceFontSlider.addEventListener('input', () => {
	sourceFontVal.textContent = sourceFontSlider.value + 'em';
	document.documentElement.style.setProperty('--source-font', sourceFontSlider.value + 'em');
});

const romFontSlider = document.getElementById('rom-font-slider');
const romFontVal = document.getElementById('rom-font-val');
romFontSlider.addEventListener('input', () => {
	romFontVal.textContent = romFontSlider.value + 'em';
	document.documentElement.style.setProperty('--rom-font', romFontSlider.value + 'em');
});

const gapSourceSlider = document.getElementById('gap-source-slider');
const gapSourceVal = document.getElementById('gap-source-val');
gapSourceSlider.addEventListener('input', () => {
	gapSourceVal.textContent = gapSourceSlider.value + 'em';
	document.documentElement.style.setProperty('--gap-source', gapSourceSlider.value + 'em');
});

const gapRomajiSlider = document.getElementById('gap-romaji-slider');
const gapRomajiVal = document.getElementById('gap-romaji-val');
gapRomajiSlider.addEventListener('input', () => {
	gapRomajiVal.textContent = gapRomajiSlider.value + 'em';
	document.documentElement.style.setProperty('--gap-romaji', gapRomajiSlider.value + 'em');
});

const lineSpacingSlider = document.getElementById('line-spacing-slider');
const lineSpacingVal = document.getElementById('line-spacing-val');
lineSpacingSlider.addEventListener('input', () => {
	lineSpacingVal.textContent = lineSpacingSlider.value + 'em';
	document.documentElement.style.setProperty('--line-spacing', lineSpacingSlider.value + 'em');
});

const toggleSourceSentence = document.getElementById('toggle-source-sentence');
const toggleSourceWords = document.getElementById('toggle-source-words');
toggleSourceSentence.addEventListener('change', () => { showSourceSentence = toggleSourceSentence.checked; });
toggleSourceWords.addEventListener('change', () => { showSourceWords = toggleSourceWords.checked; });

applySettings.addEventListener('click', () => {
	settingsModal.style.display = 'none';
	renderLanguage(currentLangData);
});

if (languagesList.length > 0) {
	loadLanguage(0);
}