const form = document.querySelector("#search-form");
const statusEl = document.querySelector("#status");
const resultsEl = document.querySelector("#results");
const savedEl = document.querySelector("#saved");
const refreshSavedButton = document.querySelector("#refresh-saved");
const template = document.querySelector("#sound-card-template");

let lastResults = [];
let audioContext;
const waveformCache = new Map();
const feedbackSelections = new Map();

const LICENSE_LABELS = {
  "creative commons 0": "CC0",
  attribution: "저작자 표시",
  "attribution noncommercial": "비상업",
};

const FEEDBACK_LABELS = {
  good: "좋음",
  bad: "별로",
  heavy_good: "묵직함 좋음",
  too_sharp: "너무 날카로움",
  magic_feel: "마법 느낌 있음",
};

function setStatus(message) {
  statusEl.textContent = message;
}

function formNumber(id, fallback) {
  const value = Number.parseFloat(document.querySelector(id).value);
  return Number.isFinite(value) ? value : fallback;
}

function buildSearchPayload() {
  return {
    prompt: document.querySelector("#prompt").value.trim(),
    license: document.querySelector("#license").value,
    min_duration: formNumber("#min-duration", 0.1),
    max_duration: formNumber("#max-duration", 3.0),
    page_size: Math.trunc(formNumber("#page-size", 20)),
  };
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      message = `${response.status} ${response.statusText}`;
    }
    throw new Error(message);
  }

  return response.json();
}

function translateError(message) {
  if (message.includes("FREESOUND_API_KEY")) {
    return ".env에 Freesound API 키를 설정해야 검색할 수 있습니다.";
  }
  if (message.includes("Failed to fetch")) {
    return "서버에 연결할 수 없습니다.";
  }
  return message;
}

function licenseLabel(license) {
  const key = (license || "").toLowerCase();
  return LICENSE_LABELS[key] || license || "라이선스 미상";
}

function previewAudioUrl(sound) {
  return `/api/preview-audio/${sound.id}?preview_url=${encodeURIComponent(sound.preview_url)}`;
}

function renderTags(container, tags) {
  container.replaceChildren();
  for (const tag of tags.slice(0, 8)) {
    const pill = document.createElement("span");
    pill.textContent = tag;
    container.append(pill);
  }
}

function renderScoreReasons(container, reasons) {
  container.replaceChildren();
  for (const reason of (reasons || []).slice(0, 6)) {
    const pill = document.createElement("span");
    pill.textContent = reason;
    container.append(pill);
  }
}

function renderSoundCard(sound) {
  const node = template.content.firstElementChild.cloneNode(true);
  node.querySelector("h3").textContent = sound.name;
  node.querySelector(".meta").textContent =
    `${sound.duration.toFixed(2)}초 · ${licenseLabel(sound.license)} · ${sound.username || "제작자 미상"}`;
  const adjustment =
    sound.personal_score_adjustment > 0
      ? ` +${sound.personal_score_adjustment}`
      : sound.personal_score_adjustment < 0
        ? ` ${sound.personal_score_adjustment}`
        : "";
  node.querySelector(".score").textContent = `점수 ${sound.score}${adjustment}`;
  renderScoreReasons(node.querySelector(".score-reasons"), sound.score_reasons || []);

  const audio = node.querySelector("audio");
  if (sound.preview_url) {
    audio.src = sound.preview_url;
  } else {
    audio.remove();
  }

  node.querySelector(".description").textContent = sound.description || "";
  renderTags(node.querySelector(".tags"), sound.tags || []);

  const link = node.querySelector("a");
  if (sound.url) {
    link.href = sound.url;
  } else {
    link.remove();
  }

  node.querySelector("[data-action='save']").addEventListener("click", async () => {
    try {
      await saveSound(sound);
      setStatus(`저장됨: ${sound.name}`);
      await loadSavedSounds();
    } catch (error) {
      setStatus(`저장 실패: ${translateError(error.message)}`);
    }
  });

  const waveformButton = node.querySelector("[data-action='waveform']");
  const waveformPanel = node.querySelector(".waveform-panel");
  const canvas = node.querySelector(".waveform-canvas");
  const metrics = node.querySelector(".analysis-metrics");

  if (!sound.preview_url) {
    waveformButton.disabled = true;
    waveformButton.textContent = "파형 없음";
  } else {
    waveformButton.addEventListener("click", async () => {
      try {
        waveformButton.disabled = true;
        waveformButton.textContent = "분석 중...";
        const analysis = await analyzeSound(sound, audio);
        waveformPanel.hidden = false;
        renderMetrics(metrics, analysis);
        appendAnalysisReasons(node.querySelector(".score-reasons"), analysis);
        drawWaveform(canvas, analysis, 0);
        bindWaveformSeek(canvas, audio, sound, analysis);
        await saveAnalysis(analysis);
        waveformButton.textContent = "파형 갱신";
        setStatus(`파형 분석 완료: ${sound.name}`);
      } catch (error) {
        setStatus(`파형 분석 실패: ${translateError(error.message)}`);
        waveformButton.textContent = "파형 보기";
      } finally {
        waveformButton.disabled = false;
      }
    });
  }

  for (const button of node.querySelectorAll("[data-feedback]")) {
    button.addEventListener("click", async () => {
      const feedbackType = button.dataset.feedback;
      try {
        await sendFeedback(sound, feedbackType);
        markFeedbackSelected(sound.id, feedbackType, node);
        setStatus(`평가 저장됨: ${FEEDBACK_LABELS[feedbackType]} · ${sound.name}`);
      } catch (error) {
        setStatus(`평가 저장 실패: ${translateError(error.message)}`);
      }
    });
  }

  return node;
}

function appendAnalysisReasons(container, analysis) {
  const reasons = [];
  if (analysis.leading_silence_seconds >= 0.35) {
    reasons.push(`앞 무음 ${analysis.leading_silence_seconds.toFixed(2)}초`);
  }
  if (analysis.heaviness_score >= 65) {
    reasons.push(`묵직함 ${analysis.heaviness_score}`);
  }
  if (analysis.sharpness_score >= 65) {
    reasons.push(`날카로움 ${analysis.sharpness_score}`);
  }
  if (analysis.emptiness_score >= 45) {
    reasons.push(`빈 구간 주의 ${analysis.emptiness_score}`);
  }

  for (const reason of reasons) {
    const pill = document.createElement("span");
    pill.className = "analysis-reason";
    pill.textContent = reason;
    container.append(pill);
  }
}

function markFeedbackSelected(soundId, feedbackType, node) {
  feedbackSelections.set(soundId, feedbackType);
  for (const button of node.querySelectorAll("[data-feedback]")) {
    const selected = button.dataset.feedback === feedbackType;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
}

function renderResults(results) {
  resultsEl.replaceChildren();
  if (results.length === 0) {
    resultsEl.append(emptyState("검색 결과가 없습니다."));
    return;
  }
  for (const sound of results) {
    resultsEl.append(renderSoundCard(sound));
  }
}

function renderSaved(sounds) {
  savedEl.replaceChildren();
  if (sounds.length === 0) {
    savedEl.append(emptyState("저장한 후보가 없습니다."));
    return;
  }

  for (const sound of sounds) {
    const item = document.createElement("article");
    item.className = "saved-item";

    const title = document.createElement("strong");
    title.textContent = sound.name;

    const meta = document.createElement("span");
    meta.textContent = `${sound.duration.toFixed(2)}초 · 점수 ${sound.score} · ${licenseLabel(sound.license)}`;

    item.append(title, meta);
    savedEl.append(item);
  }
}

function emptyState(text) {
  const node = document.createElement("p");
  node.className = "empty";
  node.textContent = text;
  return node;
}

async function searchSounds(event) {
  event.preventDefault();
  const payload = buildSearchPayload();
  if (!payload.prompt) {
    setStatus("검색 프롬프트를 입력하세요.");
    return;
  }

  setStatus("Freesound에서 후보를 찾는 중입니다...");
  resultsEl.replaceChildren();

  try {
    const data = await apiFetch("/api/search", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    lastResults = data.results;
    renderResults(lastResults);
    setStatus(`검색식: ${data.query} · 후보 ${lastResults.length}개`);
  } catch (error) {
    setStatus(`검색 실패: ${translateError(error.message)}`);
    renderResults([]);
  }
}

async function saveSound(sound) {
  return apiFetch("/api/saved-sounds", {
    method: "POST",
    body: JSON.stringify(sound),
  });
}

async function saveAnalysis(analysis) {
  return apiFetch("/api/sound-analyses", {
    method: "POST",
    body: JSON.stringify(analysis),
  });
}

async function sendFeedback(sound, feedbackType) {
  return apiFetch("/api/feedback", {
    method: "POST",
    body: JSON.stringify({
      id: sound.id,
      prompt: document.querySelector("#prompt").value.trim(),
      feedback_type: feedbackType,
      name: sound.name,
      tags: sound.tags || [],
    }),
  });
}

function getAudioContext() {
  audioContext ||= new AudioContext();
  return audioContext;
}

async function analyzeSound(sound, audioElement) {
  if (waveformCache.has(sound.id)) {
    return waveformCache.get(sound.id);
  }

  const audioUrl = previewAudioUrl(sound);
  audioElement.src = audioUrl;
  const response = await fetch(audioUrl);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  const arrayBuffer = await response.arrayBuffer();
  const buffer = await getAudioContext().decodeAudioData(arrayBuffer.slice(0));
  const samples = extractMonoSamples(buffer);
  const waveform = makeWaveform(samples, 180);
  const basic = computeBasicMetrics(samples, buffer.sampleRate, buffer.duration);
  const bands = await computeBandRatios(buffer);
  const analysis = {
    id: sound.id,
    preview_url: sound.preview_url,
    waveform,
    duration: roundMetric(buffer.duration),
    ...basic,
    ...bands,
  };

  analysis.heaviness_score = clampScore(Math.round(bands.low_ratio * 100 + basic.rms * 80));
  analysis.sharpness_score = clampScore(
    Math.round(bands.high_ratio * 100 + basic.spectral_centroid_hz / 120)
  );
  analysis.emptiness_score = clampScore(
    Math.round((basic.leading_silence_seconds / Math.max(buffer.duration, 0.1)) * 160)
  );

  waveformCache.set(sound.id, analysis);
  return analysis;
}

function extractMonoSamples(buffer) {
  const length = buffer.length;
  const channels = buffer.numberOfChannels;
  const output = new Float32Array(length);

  for (let channel = 0; channel < channels; channel += 1) {
    const data = buffer.getChannelData(channel);
    for (let index = 0; index < length; index += 1) {
      output[index] += data[index] / channels;
    }
  }

  return output;
}

function makeWaveform(samples, bucketCount) {
  const waveform = [];
  const bucketSize = Math.max(1, Math.floor(samples.length / bucketCount));
  let peak = 0;

  for (let offset = 0; offset < samples.length; offset += bucketSize) {
    let sum = 0;
    let count = 0;
    for (let index = offset; index < Math.min(offset + bucketSize, samples.length); index += 1) {
      sum += Math.abs(samples[index]);
      count += 1;
    }
    const value = count ? sum / count : 0;
    peak = Math.max(peak, value);
    waveform.push(value);
  }

  return waveform.map((value) => (peak > 0 ? value / peak : 0));
}

function computeBasicMetrics(samples, sampleRate, duration) {
  let sumSquares = 0;
  let peak = 0;
  let crossings = 0;
  let previous = samples[0] || 0;

  for (const sample of samples) {
    const abs = Math.abs(sample);
    peak = Math.max(peak, abs);
    sumSquares += sample * sample;
    if ((previous < 0 && sample >= 0) || (previous >= 0 && sample < 0)) {
      crossings += 1;
    }
    previous = sample;
  }

  const rms = Math.sqrt(sumSquares / Math.max(samples.length, 1));
  const threshold = Math.max(0.015, peak * 0.035);
  let leadingIndex = samples.findIndex((sample) => Math.abs(sample) >= threshold);
  if (leadingIndex < 0) {
    leadingIndex = samples.length;
  }

  const zcr = crossings / Math.max(samples.length - 1, 1);
  return {
    rms: roundMetric(rms),
    peak: roundMetric(peak),
    leading_silence_seconds: roundMetric(leadingIndex / sampleRate),
    spectral_centroid_hz: Math.round(Math.min(sampleRate / 2, zcr * sampleRate * 0.5)),
  };
}

async function computeBandRatios(buffer) {
  const [low, mid, high] = await Promise.all([
    filteredRms(buffer, "lowpass", 250, 0.707),
    filteredRms(buffer, "bandpass", 1200, 0.8),
    filteredRms(buffer, "highpass", 4000, 0.707),
  ]);
  const total = low + mid + high || 1;
  return {
    low_ratio: roundMetric(low / total),
    mid_ratio: roundMetric(mid / total),
    high_ratio: roundMetric(high / total),
  };
}

async function filteredRms(buffer, type, frequency, q) {
  const context = new OfflineAudioContext(1, buffer.length, buffer.sampleRate);
  const source = context.createBufferSource();
  const filter = context.createBiquadFilter();
  const mono = context.createBuffer(1, buffer.length, buffer.sampleRate);
  mono.copyToChannel(extractMonoSamples(buffer), 0);

  source.buffer = mono;
  filter.type = type;
  filter.frequency.value = frequency;
  filter.Q.value = q;
  source.connect(filter);
  filter.connect(context.destination);
  source.start();

  const rendered = await context.startRendering();
  const samples = rendered.getChannelData(0);
  let sumSquares = 0;
  for (const sample of samples) {
    sumSquares += sample * sample;
  }
  return Math.sqrt(sumSquares / Math.max(samples.length, 1));
}

function renderMetrics(container, analysis) {
  container.replaceChildren(
    metric("앞 무음", `${analysis.leading_silence_seconds.toFixed(2)}초`),
    metric("RMS", analysis.rms.toFixed(3)),
    metric("저역", `${Math.round(analysis.low_ratio * 100)}%`),
    metric("고역", `${Math.round(analysis.high_ratio * 100)}%`),
    metric("묵직함", analysis.heaviness_score),
    metric("날카로움", analysis.sharpness_score)
  );
}

function metric(label, value) {
  const item = document.createElement("span");
  item.textContent = `${label} ${value}`;
  return item;
}

function drawWaveform(canvas, analysis, progressRatio = 0) {
  const waveform = analysis.waveform;
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width * dpr));
  const height = Math.max(80, Math.round(rect.height * dpr));
  const ctx = canvas.getContext("2d");
  canvas.width = width;
  canvas.height = height;
  ctx.clearRect(0, 0, width, height);

  ctx.fillStyle = "#f8fafc";
  ctx.fillRect(0, 0, width, height);

  const duration = Math.max(analysis.duration || 0, analysis.leading_silence_seconds || 0.1);
  const silenceRatio = duration > 0 ? analysis.leading_silence_seconds / duration : 0;
  if (silenceRatio > 0.015) {
    ctx.fillStyle = "rgba(100, 116, 139, 0.18)";
    ctx.fillRect(0, 0, Math.min(width, silenceRatio * width), height);
    ctx.fillStyle = "#64748b";
    ctx.font = `${Math.max(10, 11 * dpr)}px sans-serif`;
    ctx.fillText("앞 무음", 8 * dpr, 16 * dpr);
  }

  ctx.strokeStyle = "#d7dde5";
  ctx.beginPath();
  ctx.moveTo(0, height / 2);
  ctx.lineTo(width, height / 2);
  ctx.stroke();

  const barWidth = width / waveform.length;
  ctx.fillStyle = "#0f766e";
  waveform.forEach((value, index) => {
    const barHeight = Math.max(2, value * height * 0.82);
    const x = index * barWidth;
    const y = (height - barHeight) / 2;
    ctx.fillRect(x, y, Math.max(1, barWidth * 0.68), barHeight);
  });

  ctx.fillStyle = "rgba(199, 90, 22, 0.9)";
  const progressX = Math.max(0, Math.min(width, progressRatio * width));
  ctx.fillRect(progressX, 0, Math.max(2, 2 * dpr), height);

  ctx.fillStyle = "#c75a16";
  ctx.beginPath();
  ctx.arc(progressX, height / 2, Math.max(4, 4 * dpr), 0, Math.PI * 2);
  ctx.fill();
}

function bindWaveformSeek(canvas, audio, sound, analysis) {
  if (canvas.dataset.bound === "true") {
    return;
  }
  canvas.dataset.bound = "true";
  canvas.addEventListener("click", (event) => {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const duration = Number.isFinite(audio.duration) ? audio.duration : sound.duration;
    audio.currentTime = ratio * duration;
    drawWaveform(canvas, analysis, ratio);
    audio.play().catch(() => {});
  });
  audio.addEventListener("timeupdate", () => {
    const duration = Number.isFinite(audio.duration) ? audio.duration : sound.duration;
    drawWaveform(canvas, analysis, audio.currentTime / Math.max(duration, 0.1));
  });
}

function clampScore(value) {
  return Math.max(0, Math.min(100, value));
}

function roundMetric(value) {
  return Math.round(value * 1000) / 1000;
}

async function loadSavedSounds() {
  try {
    const sounds = await apiFetch("/api/saved-sounds");
    renderSaved(sounds);
  } catch (error) {
    setStatus(`저장 목록을 불러오지 못했습니다: ${translateError(error.message)}`);
  }
}

form.addEventListener("submit", searchSounds);
refreshSavedButton.addEventListener("click", loadSavedSounds);
loadSavedSounds();
