const form = document.querySelector("#search-form");
const statusEl = document.querySelector("#status");
const conditionWarningEl = document.querySelector("#condition-warning");
const resultsEl = document.querySelector("#results");
const savedEl = document.querySelector("#saved");
const providerStatusEl = document.querySelector("#provider-status");
const refreshSavedButton = document.querySelector("#refresh-saved");
const savedFilterInput = document.querySelector("#saved-filter");
const savedSortSelect = document.querySelector("#saved-sort");
const savedCc0Input = document.querySelector("#saved-cc0");
const savedGoodInput = document.querySelector("#saved-good");
const favoriteSearchButton = document.querySelector("#favorite-search");
const recentSearchesEl = document.querySelector("#recent-searches");
const favoriteSearchesEl = document.querySelector("#favorite-searches");
const template = document.querySelector("#sound-card-template");

let lastResults = [];
let savedSounds = [];
let audioContext;
const waveformCache = new Map();
const feedbackSelections = new Map();
const cardContexts = new Map();
const RECENT_SEARCHES_KEY = "soundscrapper.recentSearches";
const FAVORITE_SEARCHES_KEY = "soundscrapper.favoriteSearches";
const SAVED_FOLDER_STATE_KEY = "soundscrapper.savedFolderState";

const LICENSE_LABELS = {
  "creative commons 0": "CC0",
  cc0: "CC0",
  attribution: "저작자 표시",
  "attribution noncommercial": "비상업",
  "cc by": "CC BY",
  "cc by-sa": "CC BY-SA",
  "cc by-nd": "CC BY-ND",
  "cc by-nc": "CC BY-NC",
};

const SOURCE_LABELS = {
  freesound: "Freesound",
  jamendo: "Jamendo",
  openverse: "Openverse",
  wikimedia: "Wikimedia",
  wikimedia_audio: "Wikimedia",
  cc_mixter: "ccMixter",
};

const FEEDBACK_LABELS = {
  good: "좋음",
  bad: "별로",
  game_like: "게임적임",
  asset_ready: "에셋활용 가능",
  heavy_good: "묵직함 좋음",
  sharp_good: "날카로움 좋음",
  clean_good: "깨끗함",
  easy_cut: "컷오프 쉬움",
  loop_good: "루프 좋음",
  noise_bad: "잡음 많음",
  leading_silence_bad: "앞 무음 김",
  too_sharp: "너무 날카로움",
  too_loud: "너무 큼",
  too_long: "너무 김",
  low_quality: "품질 낮음",
  wrong_mood: "느낌 안 맞음",
  license_risky: "라이선스 불안",
};

const SEARCH_MODE_LABELS = {
  clean_source: "깨끗한 소스",
  short_sfx: "짧은 원샷 SFX",
  easy_cut: "컷오프 쉬움",
  loop_bgm: "루프/BGM 후보",
  rights_safe: "저작권 안전 우선",
};

const SEARCH_MODE_CONFLICTS = {
  short_sfx: ["loop_bgm"],
  loop_bgm: ["short_sfx"],
};

function setStatus(message) {
  statusEl.textContent = message;
}

function readStoredList(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function writeStoredList(key, values) {
  localStorage.setItem(key, JSON.stringify(values));
}

function rememberSearch(prompt) {
  const normalized = prompt.trim();
  if (!normalized) {
    return;
  }
  const recent = [normalized, ...readStoredList(RECENT_SEARCHES_KEY).filter((item) => item !== normalized)].slice(0, 8);
  writeStoredList(RECENT_SEARCHES_KEY, recent);
  renderSearchMemory();
}

function toggleFavoriteSearch() {
  const prompt = document.querySelector("#prompt").value.trim();
  if (!prompt) {
    setStatus("즐겨찾기에 넣을 검색어를 먼저 입력하세요.");
    return;
  }
  const favorites = readStoredList(FAVORITE_SEARCHES_KEY);
  const exists = favorites.includes(prompt);
  const nextFavorites = exists ? favorites.filter((item) => item !== prompt) : [prompt, ...favorites].slice(0, 12);
  writeStoredList(FAVORITE_SEARCHES_KEY, nextFavorites);
  renderSearchMemory();
  setStatus(exists ? `즐겨찾기 해제: ${prompt}` : `즐겨찾기 저장: ${prompt}`);
}

function renderSearchMemory() {
  renderSearchChips(recentSearchesEl, readStoredList(RECENT_SEARCHES_KEY), "최근 검색어 없음");
  renderSearchChips(favoriteSearchesEl, readStoredList(FAVORITE_SEARCHES_KEY), "즐겨찾기 없음");
}

function renderSearchChips(container, items, emptyText) {
  container.replaceChildren();
  if (items.length === 0) {
    const empty = document.createElement("span");
    empty.className = "memory-empty";
    empty.textContent = emptyText;
    container.append(empty);
    return;
  }
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item;
    button.addEventListener("click", () => {
      document.querySelector("#prompt").value = item;
      setStatus(`검색어 불러옴: ${item}`);
    });
    container.append(button);
  }
}

function formNumber(id, fallback) {
  const value = Number.parseFloat(document.querySelector(id).value);
  return Number.isFinite(value) ? value : fallback;
}

function checkboxValue(id) {
  return document.querySelector(id)?.checked ?? false;
}

function selectedSearchModes() {
  return Array.from(document.querySelectorAll("[data-search-mode]:checked")).map(
    (input) => input.dataset.searchMode
  );
}

function buildSearchPayload() {
  return {
    prompt: document.querySelector("#prompt").value.trim(),
    license: document.querySelector("#license").value,
    source_filter: document.querySelector("#source-filter").value,
    min_duration: formNumber("#min-duration", 0.1),
    max_duration: formNumber("#max-duration", 3.0),
    page_size: Math.trunc(formNumber("#page-size", 20)),
    game_ready: checkboxValue("#game-ready"),
    search_modes: selectedSearchModes(),
  };
}

function soundIdentity(sound) {
  return `${sound.source_provider || "freesound"}:${sound.source_id || sound.id}`;
}

function savedIdentitySet() {
  return new Set(savedSounds.map((sound) => soundIdentity(sound)));
}

function upsertSavedSound(savedSound) {
  const identity = soundIdentity(savedSound);
  const index = savedSounds.findIndex((sound) => soundIdentity(sound) === identity);
  if (index >= 0) {
    savedSounds[index] = savedSound;
  } else {
    savedSounds.unshift(savedSound);
  }
}

function replaceSavedSound(savedSound) {
  const index = savedSounds.findIndex((sound) => sound.saved_id === savedSound.saved_id);
  if (index >= 0) {
    savedSounds[index] = savedSound;
  } else {
    upsertSavedSound(savedSound);
  }
}

function readSavedFolderState() {
  try {
    const value = JSON.parse(localStorage.getItem(SAVED_FOLDER_STATE_KEY) || "{}");
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch {
    return {};
  }
}

function writeSavedFolderState(value) {
  localStorage.setItem(SAVED_FOLDER_STATE_KEY, JSON.stringify(value));
}

function setConditionWarning(message) {
  conditionWarningEl.textContent = message;
  conditionWarningEl.classList.toggle("is-visible", Boolean(message));
}

function setupSearchModeConflicts() {
  for (const input of document.querySelectorAll("[data-search-mode]")) {
    input.addEventListener("change", () => {
      if (!input.checked) {
        return;
      }

      const mode = input.dataset.searchMode;
      const conflicts = SEARCH_MODE_CONFLICTS[mode] || [];
      const removed = [];
      for (const conflictMode of conflicts) {
        const conflictInput = document.querySelector(`[data-search-mode="${conflictMode}"]`);
        if (conflictInput?.checked) {
          conflictInput.checked = false;
          removed.push(SEARCH_MODE_LABELS[conflictMode] || conflictMode);
        }
      }

      if (removed.length > 0) {
        const selectedLabel = SEARCH_MODE_LABELS[mode] || mode;
        setConditionWarning(
          `${selectedLabel} 조건은 ${removed.join(", ")} 조건과 같이 쓸 수 없어 기존 선택을 해제했습니다.`
        );
      } else {
        setConditionWarning("");
      }
    });
  }
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

  if (response.status === 204) {
    return null;
  }

  const text = await response.text();
  return text ? JSON.parse(text) : null;
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
  if (key.includes("publicdomain/zero") || key.includes("creative commons 0")) {
    return "CC0";
  }
  if (key.includes("creativecommons.org/licenses/by-sa")) {
    return "CC BY-SA";
  }
  if (key.includes("creativecommons.org/licenses/by-nd")) {
    return "CC BY-ND";
  }
  if (key.includes("creativecommons.org/licenses/by-nc")) {
    return "CC BY-NC";
  }
  if (key.includes("creativecommons.org/licenses/by")) {
    return "CC BY";
  }
  return LICENSE_LABELS[key] || license || "라이선스 미상";
}

function licenseCreditNote(license) {
  const key = (license || "").toLowerCase();
  if (key.includes("creative commons 0") || key.includes("publicdomain/zero")) {
    return "CC0 · 출처 표기 선택";
  }
  if (key.includes("attribution") && !key.includes("noncommercial")) {
    return "저작자 표시 필요 · 원본 페이지에서 크레딧 확인";
  }
  if (key.includes("noncommercial")) {
    return "비상업 라이선스 · 게임 배포 전 사용 불가 가능성 확인";
  }
  return "라이선스 원본 확인 필요";
}

function sourceLabel(provider) {
  return SOURCE_LABELS[(provider || "").toLowerCase()] || provider || "Unknown";
}

function previewAudioUrl(sound) {
  return `/api/preview-audio/${sound.id}?preview_url=${encodeURIComponent(sound.preview_url)}`;
}

function downloadPreviewUrl(sound, nameOverride = null) {
  const params = new URLSearchParams({
    preview_url: sound.download_url || sound.preview_url || "",
    name: nameOverride || sound.name || "sound",
  });
  return `/api/download-preview/${sound.id}?${params.toString()}`;
}

function originalSoundUrl(sound) {
  return sound.source_url || sound.url || "";
}

function downloadDisplayName(sound, fallbackName = null) {
  return (sound.download_filename || "").trim() || fallbackName || sound.name || "sound";
}

function renderTags(container, tags, limit = 5) {
  container.replaceChildren();
  for (const tag of tags.slice(0, limit)) {
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

function renderFitBadges(container, sound, analysis = null) {
  const badges = conditionBadges(sound, analysis).slice(0, 6);
  container.replaceChildren();
  for (const badge of badges) {
    const item = document.createElement("span");
    item.className = `fit-badge fit-badge-${badge.tone}`;
    item.textContent = badge.label;
    container.append(item);
  }
}

function conditionBadges(sound, analysis = null) {
  const badges = [];
  const reasons = sound.score_reasons || [];
  const text = [sound.name, sound.description || "", ...(sound.tags || [])].join(" ").toLowerCase();
  const hasReason = (pattern) => reasons.some((reason) => reason.includes(pattern));

  if (hasReason("깨끗한 소스") || text.includes("clean") || text.includes("isolated")) {
    badges.push({ label: "깨끗함", tone: "good" });
  }
  if (hasReason("짧은 원샷") || (sound.duration > 0 && sound.duration <= 3)) {
    badges.push({ label: "짧은 SFX", tone: "good" });
  }
  if (hasReason("컷오프") || hasReason("파형 이벤트") || hasReason("파형 분리")) {
    badges.push({ label: "컷오프 쉬움", tone: "good" });
  }
  if (hasReason("BGM/루프") || text.includes("loop") || text.includes("bgm")) {
    badges.push({ label: "루프 후보", tone: "neutral" });
  }
  if (hasReason("저작권 안전") || licenseLabel(sound.license) === "CC0") {
    badges.push({ label: "권리 안전", tone: "good" });
  }
  if (hasReason("환경음/잡음") || text.includes("noise") || text.includes("field-recording")) {
    badges.push({ label: "잡음 주의", tone: "warn" });
  }
  if (analysis) {
    if (isLoudAnalysis(analysis)) {
      badges.push({ label: "음량 큼", tone: "danger" });
    }
    if (analysis.leading_silence_seconds <= 0.2) {
      badges.push({ label: "앞 무음 적음", tone: "good" });
    } else if (analysis.leading_silence_seconds >= 0.6) {
      badges.push({ label: "앞 무음 김", tone: "warn" });
    }
    if (analysis.emptiness_score >= 45) {
      badges.push({ label: "빈 구간 많음", tone: "warn" });
    }
  }

  return dedupeBadges(badges);
}

function isLoudAnalysis(analysis) {
  return Boolean(analysis && (analysis.peak >= 0.98 || analysis.rms >= 0.32));
}

function renderLoudWarning(node, analysis = null) {
  const warning = node.querySelector(".loud-warning");
  if (!warning) {
    return;
  }
  if (!isLoudAnalysis(analysis)) {
    warning.hidden = true;
    return;
  }
  warning.hidden = false;
  warning.textContent = `청취 주의: 음량이 큼 · Peak ${analysis.peak.toFixed(2)} · RMS ${analysis.rms.toFixed(2)}`;
}

function dedupeBadges(badges) {
  const seen = new Set();
  return badges.filter((badge) => {
    if (seen.has(badge.label)) {
      return false;
    }
    seen.add(badge.label);
    return true;
  });
}

function renderSoundCard(sound) {
  const node = template.content.firstElementChild.cloneNode(true);
  node.dataset.soundId = String(sound.id);
  node.dataset.sourceProvider = sound.source_provider || "";
  const sourceBadge = node.querySelector(".source-badge");
  sourceBadge.textContent = sourceLabel(sound.source_provider);
  sourceBadge.classList.add(`source-${sound.source_provider || "unknown"}`);
  node.querySelector("h3").textContent = sound.name;
  node.querySelector(".meta").textContent =
    `${sound.duration.toFixed(2)}초 · ${licenseLabel(sound.license)}`;
  const adjustment =
    sound.personal_score_adjustment > 0
      ? ` +${sound.personal_score_adjustment}`
      : sound.personal_score_adjustment < 0
        ? ` ${sound.personal_score_adjustment}`
        : "";
  node.querySelector(".score").textContent = `점수 ${sound.score}${adjustment}`;
  node.querySelector(".license-note").textContent = licenseCreditNote(sound.license);
  renderAttributionNote(node.querySelector(".attribution-note"), sound);
  renderLoudWarning(node);
  renderFitBadges(node.querySelector(".fit-badges"), sound);
  renderScoreReasons(node.querySelector(".score-reasons"), sound.score_reasons || []);

  const audio = node.querySelector("audio");
  if (sound.preview_url) {
    audio.src = sound.preview_url;
  } else {
    audio.remove();
  }

  const loopState = {
    full: false,
    segment: false,
    start: 0,
    end: null,
  };
  const loopControls = loopControlElements(node);
  if (sound.preview_url) {
    setupLoopControls(audio, sound, loopState, loopControls);
  } else {
    disableLoopControls(loopControls);
  }
  const context = {
    sound,
    node,
    audio,
    loopState,
    loopControls,
    analysis: null,
    waveformRendered: false,
  };
  cardContexts.set(sound.id, context);

  node.querySelector(".description").textContent = sound.description || "";
  renderTags(node.querySelector(".tags"), sound.tags || [], 5);
  renderTags(node.querySelector(".all-tags"), sound.tags || [], 24);

  const link = node.querySelector("[data-action='open']");
  if (originalSoundUrl(sound)) {
    link.href = originalSoundUrl(sound);
  } else {
    link.remove();
  }

  const saveButton = node.querySelector("[data-action='save']");
  syncSaveButton(saveButton, sound);
  saveButton.addEventListener("click", async () => {
    try {
      const saved = await saveSound(sound);
      upsertSavedSound(saved);
      syncSaveButton(saveButton, sound);
      setStatus(`저장됨: ${sound.name}`);
      renderSaved();
    } catch (error) {
      setStatus(`저장 실패: ${translateError(error.message)}`);
    }
  });

  const downloadButton = node.querySelector("[data-action='download']");
  if (!sound.download_allowed || !(sound.download_url || sound.preview_url)) {
    downloadButton.disabled = true;
    downloadButton.textContent = "다운로드 없음";
  } else {
    downloadButton.addEventListener("click", () => {
      triggerDownload(sound);
    });
  }

  const detailsButton = node.querySelector("[data-action='details']");
  const details = node.querySelector(".card-details");
  detailsButton.addEventListener("click", () => {
    details.open = !details.open;
    detailsButton.textContent = details.open ? "접기" : "상세";
  });
  details.addEventListener("toggle", () => {
    detailsButton.textContent = details.open ? "접기" : "상세";
    if (details.open && context.analysis) {
      renderWaveformForCard(context);
    }
  });

  const waveformButton = node.querySelector("[data-action='waveform']");

  if (!sound.preview_url) {
    waveformButton.disabled = true;
    waveformButton.textContent = "파형 없음";
  } else {
    waveformButton.addEventListener("click", async () => {
      await analyzeSoundCard(context);
    });
  }

  for (const button of node.querySelectorAll("[data-feedback]")) {
    button.addEventListener("click", async () => {
      const feedbackType = button.dataset.feedback;
      const nextActive = button.getAttribute("aria-pressed") !== "true";
      try {
        await sendFeedback(sound, feedbackType, nextActive);
        markFeedbackSelected(sound.id, feedbackType, node, nextActive);
        const action = nextActive ? "저장됨" : "해제됨";
        let suffix = "";
        if (feedbackType === "bad" && nextActive) {
          suffix = " · 마음에 안 든 점을 선택해 주세요";
        } else if (feedbackType === "good" && nextActive) {
          suffix = " · 좋았던 점을 더 선택할 수 있습니다";
        }
        setStatus(`평가 ${action}: ${FEEDBACK_LABELS[feedbackType]} · ${sound.name}${suffix}`);
      } catch (error) {
        setStatus(`평가 저장 실패: ${translateError(error.message)}`);
      }
    });
  }

  syncBadReasonVisibility(node);
  hydrateStoredAnalysis(sound, node);

  return node;
}

function syncSaveButton(button, sound) {
  const saved = savedIdentitySet().has(soundIdentity(sound));
  button.classList.toggle("is-saved", saved);
  button.setAttribute("aria-pressed", String(saved));
  button.setAttribute("aria-label", saved ? "저장됨" : "저장");
  const label = button.querySelector("span");
  if (label) {
    label.textContent = saved ? "저장됨" : "저장";
  }
}

function syncRenderedSaveStates() {
  for (const { sound, node } of cardContexts.values()) {
    const button = node.querySelector("[data-action='save']");
    if (button) {
      syncSaveButton(button, sound);
    }
  }
}

function renderAttributionNote(container, sound) {
  container.replaceChildren();
  const text = sound.attribution_text || `${sound.name} by ${sound.username || "Unknown creator"}`;
  container.append(document.createTextNode(text));
  const links = [
    ["원본", sound.source_url || sound.url],
    ["라이선스", sound.license_url],
    ["저작자", sound.creator_url],
  ].filter(([, href]) => href);

  for (const [label, href] of links) {
    const link = document.createElement("a");
    link.href = href;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = label;
    container.append(document.createTextNode(" · "));
    container.append(link);
  }
}

function triggerDownload(sound, nameOverride = null) {
  const link = document.createElement("a");
  link.href = downloadPreviewUrl(sound, nameOverride);
  link.download = "";
  document.body.append(link);
  link.click();
  link.remove();
  setStatus(`다운로드 시작: ${nameOverride || sound.name} · 라이선스 확인은 원본 페이지 기준입니다.`);
}

async function hydrateStoredAnalysis(sound, node) {
  try {
    const analysis = await apiFetch(`/api/sound-analyses/${sound.id}`);
    if (!analysis) {
      return;
    }
    waveformCache.set(sound.id, analysis);
    const context = cardContexts.get(sound.id);
    if (context) {
      context.analysis = analysis;
      context.waveformRendered = false;
    }
    applyAnalysisToCard(sound, node, analysis, { cached: true });
  } catch {
    // 저장된 분석값은 보조 정보라 실패해도 검색 흐름은 유지한다.
  }
}

async function analyzeSoundCard(context, options = {}) {
  const { sound, node, audio } = context;
  const waveformButton = node.querySelector("[data-action='waveform']");

  try {
    waveformButton.disabled = true;
    waveformButton.textContent = options.auto ? "자동 분석 중..." : "분석 중...";
    const analysis = await analyzeSound(sound, audio);
    context.analysis = analysis;
    context.waveformRendered = false;
    applyAnalysisToCard(sound, node, analysis);
    await saveAnalysis(analysis);
    if (!options.auto) {
      openCardDetails(node);
      renderWaveformForCard(context);
    }
    waveformButton.textContent = "파형 갱신";
    setStatus(`${options.auto ? "자동 " : ""}파형 분석 완료: ${sound.name}`);
  } catch (error) {
    setStatus(`파형 분석 실패: ${translateError(error.message)}`);
    waveformButton.textContent = "파형 보기";
  } finally {
    waveformButton.disabled = false;
  }
}

function applyAnalysisToCard(sound, node, analysis, options = {}) {
  renderLoudWarning(node, analysis);
  renderFitBadges(node.querySelector(".fit-badges"), sound, analysis);
  appendAnalysisReasons(node.querySelector(".score-reasons"), analysis);
  const state = node.querySelector(".analysis-state");
  if (state) {
    state.hidden = false;
    state.classList.toggle("is-danger", isLoudAnalysis(analysis));
    state.textContent = isLoudAnalysis(analysis) ? "청취 주의" : options.cached ? "분석 캐시" : "분석됨";
  }
}

function openCardDetails(node) {
  const details = node.querySelector(".card-details");
  const detailsButton = node.querySelector("[data-action='details']");
  if (details) {
    details.open = true;
  }
  if (detailsButton) {
    detailsButton.textContent = "접기";
  }
}

function renderWaveformForCard(context) {
  const { sound, node, audio, loopState, loopControls, analysis } = context;
  const details = node.querySelector(".card-details");
  if (!analysis || !details?.open) {
    return;
  }
  const waveformPanel = node.querySelector(".waveform-panel");
  const canvas = node.querySelector(".waveform-canvas");
  const metrics = node.querySelector(".analysis-metrics");
  waveformPanel.hidden = false;
  renderMetrics(metrics, analysis);
  requestAnimationFrame(() => {
    drawWaveform(canvas, analysis, 0, loopState);
    bindWaveformSeek(canvas, audio, sound, analysis, loopState, loopControls);
    context.waveformRendered = true;
  });
}

function appendAnalysisReasons(container, analysis) {
  const reasons = [];
  if (isLoudAnalysis(analysis)) {
    reasons.push("청취 주의: 음량 큼");
  }
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

  const existing = new Set(Array.from(container.children).map((item) => item.textContent));
  for (const reason of reasons) {
    if (existing.has(reason)) {
      continue;
    }
    const pill = document.createElement("span");
    pill.className = "analysis-reason";
    pill.textContent = reason;
    container.append(pill);
  }
}

function markFeedbackSelected(soundId, feedbackType, node, active) {
  const selectedTypes = feedbackSelections.get(soundId) || new Set();
  const button = node.querySelector(`[data-feedback="${feedbackType}"]`);

  if (button?.dataset.feedbackGroup === "preference" && active) {
    for (const peer of node.querySelectorAll('[data-feedback-group="preference"]')) {
      selectedTypes.delete(peer.dataset.feedback);
      setFeedbackButtonPressed(peer, false);
    }
  }

  if (active) {
    selectedTypes.add(feedbackType);
  } else {
    selectedTypes.delete(feedbackType);
  }

  if (button) {
    setFeedbackButtonPressed(button, active);
  }
  feedbackSelections.set(soundId, selectedTypes);
  syncBadReasonVisibility(node);
}

function setFeedbackButtonPressed(button, selected) {
  button.classList.toggle("is-selected", selected);
  button.setAttribute("aria-pressed", String(selected));
}

function syncBadReasonVisibility(node) {
  const goodButton = node.querySelector('[data-feedback="good"]');
  const badButton = node.querySelector('[data-feedback="bad"]');
  const positiveReasons = node.querySelector(".positive-reasons");
  const badReasons = node.querySelector(".bad-reasons");
  const goodSelected = goodButton?.getAttribute("aria-pressed") === "true";
  const badSelected = badButton?.getAttribute("aria-pressed") === "true";
  if (positiveReasons) {
    positiveReasons.hidden = !goodSelected;
    positiveReasons.classList.toggle("is-highlighted", goodSelected);
  }
  if (!badReasons) {
    return;
  }
  badReasons.hidden = !badSelected;
  badReasons.classList.toggle("is-highlighted", badSelected);
}

function loopControlElements(node) {
  return {
    fullButton: node.querySelector("[data-action='loop']"),
    startButton: node.querySelector("[data-action='loop-start']"),
    endButton: node.querySelector("[data-action='loop-end']"),
    segmentButton: node.querySelector("[data-action='segment-loop']"),
    clearButton: node.querySelector("[data-action='clear-loop']"),
    status: node.querySelector(".loop-status"),
    onChange: null,
  };
}

function disableLoopControls(controls) {
  for (const button of loopButtons(controls)) {
    button.disabled = true;
  }
  controls.status.textContent = "미리듣기 없음";
}

function setupLoopControls(audio, sound, loopState, controls) {
  controls.fullButton.addEventListener("click", () => {
    loopState.full = !loopState.full;
    if (loopState.full) {
      loopState.segment = false;
      audio.loop = true;
      audio.play().catch(() => {});
    } else {
      audio.loop = false;
    }
    updateLoopControls(loopState, controls);
  });

  controls.startButton.addEventListener("click", () => {
    const duration = getDuration(audio, sound);
    const current = clampTime(audio.currentTime || 0, duration);
    const latestStart = Math.max(0, duration - 0.05);
    loopState.start = Math.min(current, latestStart);
    if (loopState.end !== null && loopState.end <= loopState.start + 0.05) {
      loopState.end = null;
      loopState.segment = false;
    }
    updateLoopControls(loopState, controls);
  });

  controls.endButton.addEventListener("click", () => {
    const duration = getDuration(audio, sound);
    const end = clampTime(audio.currentTime || duration, duration);
    loopState.end = Math.max(end, Math.min(duration, loopState.start + 0.15));
    if (loopState.end <= loopState.start) {
      loopState.start = Math.max(0, loopState.end - 0.15);
    }
    updateLoopControls(loopState, controls);
  });

  controls.segmentButton.addEventListener("click", () => {
    loopState.segment = !loopState.segment;
    if (loopState.segment) {
      const duration = getDuration(audio, sound);
      if (loopState.end === null || loopState.end <= loopState.start + 0.05) {
        const fallbackLength = Math.min(1.5, Math.max(0.25, duration - loopState.start));
        loopState.end = Math.min(duration, loopState.start + fallbackLength);
      }
      if (loopState.end <= loopState.start) {
        loopState.start = Math.max(0, duration - 0.25);
        loopState.end = duration;
      }
      loopState.full = false;
      audio.loop = false;
      audio.currentTime = loopState.start;
      audio.play().catch(() => {});
    }
    updateLoopControls(loopState, controls);
  });

  controls.clearButton.addEventListener("click", () => {
    loopState.full = false;
    loopState.segment = false;
    loopState.start = 0;
    loopState.end = null;
    audio.loop = false;
    updateLoopControls(loopState, controls);
  });

  audio.addEventListener("timeupdate", () => {
    if (!loopState.segment || loopState.end === null) {
      return;
    }
    if (audio.currentTime >= loopState.end) {
      audio.currentTime = loopState.start;
      audio.play().catch(() => {});
    }
  });

  updateLoopControls(loopState, controls);
}

function updateLoopControls(loopState, controls) {
  controls.fullButton.classList.toggle("is-selected", loopState.full);
  controls.fullButton.setAttribute("aria-pressed", String(loopState.full));
  controls.segmentButton.classList.toggle("is-selected", loopState.segment);
  controls.segmentButton.setAttribute("aria-pressed", String(loopState.segment));

  if (loopState.segment && loopState.end !== null) {
    controls.status.textContent = `구간 ${formatTime(loopState.start)}-${formatTime(loopState.end)}`;
  } else if (loopState.full) {
    controls.status.textContent = "전체 루프";
  } else if (loopState.end !== null) {
    controls.status.textContent = `A/B ${formatTime(loopState.start)}-${formatTime(loopState.end)}`;
  } else if (loopState.start > 0) {
    controls.status.textContent = `A ${formatTime(loopState.start)}`;
  } else {
    controls.status.textContent = "루프 꺼짐";
  }

  controls.onChange?.();
}

function loopButtons(controls) {
  return [
    controls.fullButton,
    controls.startButton,
    controls.endButton,
    controls.segmentButton,
    controls.clearButton,
  ];
}

function getDuration(audio, sound) {
  if (Number.isFinite(audio.duration) && audio.duration > 0) {
    return audio.duration;
  }
  return Math.max(0.1, sound.duration || 0.1);
}

function clampTime(value, duration) {
  return Math.max(0, Math.min(value, Math.max(0.1, duration)));
}

function formatTime(value) {
  return `${value.toFixed(2)}초`;
}

function renderResults(results) {
  resultsEl.replaceChildren();
  cardContexts.clear();
  if (results.length === 0) {
    resultsEl.append(emptyState("검색 결과가 없습니다."));
    return;
  }
  for (const sound of results) {
    resultsEl.append(renderSoundCard(sound));
  }
}

async function autoAnalyzeTopResults() {
  if (!checkboxValue("#auto-analyze")) {
    return;
  }

  const targets = lastResults.filter((sound) => sound.preview_url).slice(0, 5);
  if (targets.length === 0) {
    return;
  }

  setStatus(`상위 ${targets.length}개 파형 자동 분석을 시작합니다.`);
  for (const sound of targets) {
    const context = cardContexts.get(sound.id);
    if (!context) {
      continue;
    }
    await analyzeSoundCard(context, { auto: true });
  }
  setStatus(`상위 ${targets.length}개 파형 자동 분석 완료`);
}

function filteredSavedSounds() {
  const filterText = (savedFilterInput.value || "").trim().toLowerCase();
  const cc0Only = savedCc0Input.checked;
  const goodOnly = savedGoodInput.checked;

  return savedSounds
    .filter((sound) => {
      const searchable = [
        sound.name,
        sound.username,
        licenseLabel(sound.license),
        sourceLabel(sound.source_provider),
        sound.note || "",
        sound.folder || "",
        sound.download_filename || "",
        ...(sound.labels || []),
        ...(sound.tags || []),
      ]
        .join(" ")
        .toLowerCase();
      if (filterText && !searchable.includes(filterText)) {
        return false;
      }
      if (cc0Only && licenseLabel(sound.license) !== "CC0") {
        return false;
      }
      if (goodOnly && !(sound.feedback_types || []).includes("good")) {
        return false;
      }
      return true;
    })
    .sort(savedSorter(savedSortSelect.value));
}

function savedSorter(sortKey) {
  const byRecent = (left, right) => String(right.saved_at).localeCompare(String(left.saved_at));
  const sorters = {
    recent: byRecent,
    fit: (left, right) =>
      (right.fit_rating || 0) - (left.fit_rating || 0) ||
      right.score - left.score ||
      byRecent(left, right),
    score: (left, right) => right.score - left.score || byRecent(left, right),
    duration_asc: (left, right) => left.duration - right.duration || byRecent(left, right),
    duration_desc: (left, right) => right.duration - left.duration || byRecent(left, right),
  };
  return sorters[sortKey] || byRecent;
}

function renderSaved(sounds = filteredSavedSounds()) {
  savedEl.replaceChildren();
  if (sounds.length === 0) {
    savedEl.append(emptyState("저장한 후보가 없습니다."));
    return;
  }

  const folderState = readSavedFolderState();
  for (const [folderName, folderSounds] of savedFolderGroups(sounds)) {
    const folder = document.createElement("details");
    folder.className = "saved-folder";
    const key = savedFolderKey(folderName);
    folder.open = folderState[key] !== false;
    folder.addEventListener("toggle", () => {
      const nextState = readSavedFolderState();
      nextState[key] = folder.open;
      writeSavedFolderState(nextState);
    });

    const summary = document.createElement("summary");
    const name = document.createElement("strong");
    name.textContent = folderName;
    const count = document.createElement("span");
    count.textContent = `${folderSounds.length}개`;
    summary.append(name, count);
    folder.append(summary);

    const body = document.createElement("div");
    body.className = "saved-folder-body";
    for (const [index, sound] of folderSounds.entries()) {
      body.append(renderSavedItem(sound, defaultSavedDownloadName(folderName, index)));
    }
    folder.append(body);
    savedEl.append(folder);
  }
}

function savedFolderGroups(sounds) {
  const groups = new Map();
  for (const sound of sounds) {
    const folderName = (sound.folder || "").trim() || "미분류";
    if (!groups.has(folderName)) {
      groups.set(folderName, []);
    }
    groups.get(folderName).push(sound);
  }
  return Array.from(groups.entries()).sort(([leftName], [rightName]) => {
    if (leftName === "미분류") {
      return 1;
    }
    if (rightName === "미분류") {
      return -1;
    }
    return leftName.localeCompare(rightName, "ko");
  });
}

function savedFolderKey(folderName) {
  return `folder:${folderName || "미분류"}`;
}

function defaultSavedDownloadName(folderName, index) {
  const baseName = (folderName || "").trim() || "미분류";
  return `${baseName}_${index + 1}`;
}

function renderSavedItem(sound, defaultDownloadName) {
  const item = document.createElement("article");
  item.className = "saved-item";
  item.dataset.savedId = String(sound.saved_id);

  const header = document.createElement("div");
  header.className = "saved-item-head";
  const title = document.createElement("strong");
  title.textContent = sound.name;
  header.append(title, renderSavedRatingControl(sound));

  const meta = document.createElement("span");
  meta.className = "saved-meta";
  meta.textContent =
    `${sourceLabel(sound.source_provider)} · ${sound.duration.toFixed(2)}초 · 점수 ${sound.score} · ${licenseLabel(sound.license)}`;

  item.append(header, meta);

  if (sound.preview_url) {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.preload = "none";
    audio.src = sound.preview_url;
    item.append(audio);
  }

  const feedback = renderSavedFeedback(sound.feedback_types || []);
  if (feedback) {
    item.append(feedback);
  }

  const labels = renderSavedLabels(sound.labels || []);
  if (labels) {
    item.append(labels);
  }

  const actions = document.createElement("div");
  actions.className = "saved-item-actions";
  const downloadButton = document.createElement("button");
  downloadButton.type = "button";
  downloadButton.textContent = "다운로드";
  if (!sound.download_allowed || !(sound.download_url || sound.preview_url)) {
    downloadButton.disabled = true;
    downloadButton.textContent = "다운로드 없음";
  } else {
    downloadButton.addEventListener("click", () =>
      triggerDownload(sound, downloadDisplayName(sound, defaultDownloadName))
    );
  }
  actions.append(downloadButton);

  const openUrl = originalSoundUrl(sound);
  if (openUrl) {
    const openLink = document.createElement("a");
    openLink.href = openUrl;
    openLink.target = "_blank";
    openLink.rel = "noreferrer";
    openLink.textContent = "원본";
    actions.append(openLink);
  }

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "danger-button";
  deleteButton.textContent = "삭제";
  deleteButton.addEventListener("click", async () => {
    try {
      await deleteSavedSound(sound.saved_id);
      savedSounds = savedSounds.filter((itemSound) => itemSound.saved_id !== sound.saved_id);
      renderSaved();
      syncRenderedSaveStates();
      setStatus(`저장 후보 삭제: ${sound.name}`);
    } catch (error) {
      setStatus(`삭제 실패: ${translateError(error.message)}`);
    }
  });
  actions.append(deleteButton);
  item.append(actions);

  const manage = document.createElement("details");
  manage.className = "saved-manage";
  const manageSummary = document.createElement("summary");
  manageSummary.textContent = "관리";
  manage.append(manageSummary, renderSavedEditor(sound, defaultDownloadName));
  item.append(manage);
  return item;
}

function renderSavedLabels(labels) {
  const cleaned = (labels || []).filter(Boolean);
  if (cleaned.length === 0) {
    return null;
  }
  const container = document.createElement("div");
  container.className = "saved-labels";
  for (const label of cleaned.slice(0, 8)) {
    const pill = document.createElement("span");
    pill.textContent = label;
    container.append(pill);
  }
  return container;
}

function renderSavedRatingControl(sound) {
  const rating = document.createElement("select");
  rating.className = sound.fit_rating
    ? "saved-rating-select is-rated"
    : "saved-rating-select";
  rating.setAttribute("aria-label", "적합도");
  const emptyRating = document.createElement("option");
  emptyRating.value = "";
  emptyRating.textContent = "미평가";
  rating.append(emptyRating);
  for (let value = 5; value >= 1; value -= 1) {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = `${value}점`;
    option.selected = sound.fit_rating === value;
    rating.append(option);
  }
  rating.addEventListener("change", () => {
    updateSavedMetadata(sound.saved_id, {
      fit_rating: rating.value ? Number.parseInt(rating.value, 10) : null,
    });
  });
  return rating;
}

function renderSavedEditor(sound, defaultDownloadName) {
  const editor = document.createElement("div");
  editor.className = "saved-editor";

  const folderLabel = document.createElement("label");
  folderLabel.textContent = "폴더";
  const folder = document.createElement("input");
  folder.type = "text";
  folder.value = sound.folder || "";
  folder.placeholder = "예: UI, 전투, 마법";
  folder.addEventListener("change", () => {
    updateSavedMetadata(sound.saved_id, { folder: folder.value.trim() });
  });
  folderLabel.append(folder);

  const labelsLabel = document.createElement("label");
  labelsLabel.textContent = "라벨";
  const labels = document.createElement("input");
  labels.type = "text";
  labels.value = (sound.labels || []).join(", ");
  labels.placeholder = "쉼표로 구분";
  labels.addEventListener("change", () => {
    updateSavedMetadata(sound.saved_id, { labels: parseLabelInput(labels.value) });
  });
  labelsLabel.append(labels);

  const downloadNameLabel = document.createElement("label");
  downloadNameLabel.textContent = "다운로드명";
  const downloadName = document.createElement("input");
  downloadName.type = "text";
  downloadName.value = downloadDisplayName(sound, defaultDownloadName);
  downloadName.placeholder = defaultDownloadName;
  downloadName.addEventListener("change", () => {
    const nextName = downloadName.value.trim();
    updateSavedMetadata(sound.saved_id, {
      download_filename: nextName === defaultDownloadName ? "" : nextName,
    });
  });
  downloadNameLabel.append(downloadName);

  const noteLabel = document.createElement("label");
  noteLabel.className = "saved-note-field";
  noteLabel.textContent = "메모";
  const note = document.createElement("textarea");
  note.value = sound.note || "";
  note.placeholder = "사용할 장면, 컷 위치, 수정 필요점";
  note.rows = 3;
  note.addEventListener("change", () => {
    updateSavedMetadata(sound.saved_id, { note: note.value });
  });
  noteLabel.append(note);

  editor.append(folderLabel, labelsLabel, downloadNameLabel, noteLabel);
  return editor;
}

function parseLabelInput(value) {
  const seen = new Set();
  const labels = [];
  for (const raw of value.split(",")) {
    const label = raw.trim();
    const key = label.toLowerCase();
    if (!label || seen.has(key)) {
      continue;
    }
    labels.push(label);
    seen.add(key);
    if (labels.length === 20) {
      break;
    }
  }
  return labels;
}

function renderSavedFeedback(feedbackTypes) {
  const labels = feedbackTypes.map((type) => FEEDBACK_LABELS[type]).filter(Boolean).slice(0, 4);
  if (labels.length === 0) {
    return null;
  }
  const container = document.createElement("div");
  container.className = "saved-feedback";
  for (const label of labels) {
    const pill = document.createElement("span");
    pill.textContent = label;
    container.append(pill);
  }
  return container;
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

  setStatus("선택한 출처에서 후보를 찾는 중입니다...");
  resultsEl.replaceChildren();

  try {
    const data = await apiFetch("/api/search", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    lastResults = data.results;
    renderResults(lastResults);
    rememberSearch(payload.prompt);
    const warningText =
      data.source_warnings && data.source_warnings.length
        ? ` · ${data.source_warnings.join(" · ")}`
        : "";
    setStatus(`검색식: ${data.query} · 후보 ${lastResults.length}개${warningText}`);
    await autoAnalyzeTopResults();
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

async function updateSavedMetadata(savedId, update) {
  try {
    const saved = await apiFetch(`/api/saved-sounds/${savedId}`, {
      method: "PATCH",
      body: JSON.stringify(update),
    });
    replaceSavedSound(saved);
    renderSaved();
    syncRenderedSaveStates();
    setStatus(`저장 후보 수정: ${saved.name}`);
  } catch (error) {
    setStatus(`저장 후보 수정 실패: ${translateError(error.message)}`);
  }
}

async function deleteSavedSound(savedId) {
  return apiFetch(`/api/saved-sounds/${savedId}`, {
    method: "DELETE",
  });
}

async function saveAnalysis(analysis) {
  return apiFetch("/api/sound-analyses", {
    method: "POST",
    body: JSON.stringify(analysis),
  });
}

async function sendFeedback(sound, feedbackType, active) {
  return apiFetch("/api/feedback", {
    method: "POST",
    body: JSON.stringify({
      id: sound.id,
      prompt: document.querySelector("#prompt").value.trim(),
      feedback_type: feedbackType,
      active,
      name: sound.name,
      tags: sound.tags || [],
      source_provider: sound.source_provider || "freesound",
      source_id: sound.source_id || String(sound.id),
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
    metric("Peak", analysis.peak.toFixed(3)),
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

function drawWaveform(canvas, analysis, progressRatio = 0, loopState = null) {
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

  if (loopState && loopState.end !== null) {
    const startRatio = Math.max(0, Math.min(1, loopState.start / duration));
    const endRatio = Math.max(startRatio, Math.min(1, loopState.end / duration));
    const startX = startRatio * width;
    const endX = endRatio * width;
    ctx.fillStyle = loopState.segment ? "rgba(249, 115, 22, 0.18)" : "rgba(15, 118, 110, 0.11)";
    ctx.fillRect(startX, 0, Math.max(2, endX - startX), height);
    ctx.fillStyle = loopState.segment ? "#c75a16" : "#0f766e";
    ctx.fillRect(startX, 0, Math.max(2, 2 * dpr), height);
    ctx.fillRect(endX, 0, Math.max(2, 2 * dpr), height);
    ctx.font = `${Math.max(10, 11 * dpr)}px sans-serif`;
    ctx.fillText("A", startX + 4 * dpr, height - 8 * dpr);
    ctx.fillText("B", Math.max(4 * dpr, endX - 14 * dpr), height - 8 * dpr);
  }

  const barWidth = width / Math.max(1, waveform.length);
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

function bindWaveformSeek(canvas, audio, sound, analysis, loopState, loopControls) {
  if (canvas.dataset.bound === "true") {
    return;
  }
  canvas.dataset.bound = "true";
  loopControls.onChange = () => {
    const duration = getDuration(audio, sound);
    drawWaveform(canvas, analysis, audio.currentTime / Math.max(duration, 0.1), loopState);
  };
  canvas.addEventListener("click", (event) => {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const duration = getDuration(audio, sound);
    audio.currentTime = ratio * duration;
    drawWaveform(canvas, analysis, ratio, loopState);
    audio.play().catch(() => {});
  });
  audio.addEventListener("timeupdate", () => {
    const duration = getDuration(audio, sound);
    drawWaveform(canvas, analysis, audio.currentTime / Math.max(duration, 0.1), loopState);
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
    savedSounds = await apiFetch("/api/saved-sounds");
    renderSaved();
    syncRenderedSaveStates();
  } catch (error) {
    setStatus(`저장 목록을 불러오지 못했습니다: ${translateError(error.message)}`);
  }
}

async function loadProviderStatus() {
  try {
    const data = await apiFetch("/api/provider-status");
    renderProviderStatus(data.providers || []);
  } catch (error) {
    providerStatusEl.textContent = `API 상태 확인 실패: ${translateError(error.message)}`;
  }
}

function renderProviderStatus(providers) {
  providerStatusEl.replaceChildren();
  for (const provider of providers) {
    const item = document.createElement("span");
    item.className = provider.enabled ? "provider-ok" : "provider-missing";
    item.title = provider.message || "";
    const statusLabel = provider.enabled ? (provider.configured ? "연결" : "익명") : "미설정";
    item.textContent = `${sourceLabel(provider.provider)} ${statusLabel}`;
    providerStatusEl.append(item);
  }
}

form.addEventListener("submit", searchSounds);
refreshSavedButton.addEventListener("click", loadSavedSounds);
savedFilterInput.addEventListener("input", () => renderSaved());
savedSortSelect.addEventListener("change", () => renderSaved());
savedCc0Input.addEventListener("change", () => renderSaved());
savedGoodInput.addEventListener("change", () => renderSaved());
favoriteSearchButton.addEventListener("click", toggleFavoriteSearch);
setupSearchModeConflicts();
renderSearchMemory();
loadProviderStatus();
loadSavedSounds();
