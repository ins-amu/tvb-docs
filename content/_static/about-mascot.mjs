/**
 * Interactive audio playback for the About-section goat mascot (`.tvb-about-mascot`).
 *
 * Uses document-level event delegation and a MutationObserver so playback
 * survives MyST client-side SPA navigation without leaking listeners or
 * re-fetching audio on non-About pages.
 */

export const AUDIO_PATH = './goat.opus';
export const MASCOT_SELECTOR = '.tvb-about-mascot';
export const PLAYING_CLASS = 'tvb-about-mascot--playing';

/** Resolve the audio file URL relative to this module (safe under BASE_URL subpaths). */
export function resolveAudioUrl(moduleUrl = import.meta.url) {
  return new URL(AUDIO_PATH, moduleUrl).href;
}

/**
 * Create a delegated controller for `.tvb-about-mascot` hover, click, and
 * keyboard activation.
 */
export function createMascotController({
  doc = typeof document !== 'undefined' ? document : undefined,
  win = typeof window !== 'undefined' ? window : undefined,
  audioUrl = resolveAudioUrl(),
  createAudio = (url) => {
    const audio = new Audio(url);
    audio.preload = 'auto';
    return audio;
  },
  usePointerEvents = Boolean(win && 'PointerEvent' in win),
} = {}) {
  let audio = null;

  function setPlaying(playing) {
    if (!doc) return;
    for (const el of doc.querySelectorAll(MASCOT_SELECTOR)) {
      el.classList?.toggle?.(PLAYING_CLASS, playing);
    }
  }

  const onAudioPlay = () => setPlaying(true);
  const onAudioStop = () => setPlaying(false);

  function getAudio() {
    if (audio) return audio;
    audio = createAudio(audioUrl);
    if (audio && typeof audio.addEventListener === 'function') {
      audio.addEventListener('play', onAudioPlay);
      audio.addEventListener('ended', onAudioStop);
      audio.addEventListener('pause', onAudioStop);
      audio.addEventListener('error', onAudioStop);
    }
    return audio;
  }

  function play({ restart = false } = {}) {
    const el = getAudio();
    if (!el) return;
    if (!restart && !el.paused && !el.ended) return;
    try {
      el.currentTime = 0;
    } catch {
      // Ignore InvalidStateError before audio metadata is loaded.
    }
    try {
      Promise.resolve(el.play()).catch(() => {
        // Ignore browser autoplay restrictions prior to a user gesture.
      });
    } catch {
      // Ignore synchronous play() failures.
    }
  }

  function enhanceMascots() {
    if (!doc) return;
    const mascots = [...doc.querySelectorAll(MASCOT_SELECTOR)];
    for (const mascot of mascots) {
      if (!mascot.hasAttribute('role')) mascot.setAttribute('role', 'button');
      if (!mascot.hasAttribute('tabindex')) mascot.setAttribute('tabindex', '0');
      if (!mascot.hasAttribute('aria-label')) mascot.setAttribute('aria-label', 'Play goat sound');
    }
    if (mascots.length > 0) {
      getAudio();
    }
  }

  const hoverEvent = usePointerEvents ? 'pointerover' : 'mouseover';

  function findMascot(target) {
    return target && typeof target.closest === 'function' ? target.closest(MASCOT_SELECTOR) : null;
  }

  function onHover(event) {
    if (usePointerEvents && event.pointerType !== 'mouse') return;
    const mascot = findMascot(event.target);
    if (!mascot) return;
    if (event.relatedTarget && typeof mascot.contains === 'function' && mascot.contains(event.relatedTarget)) {
      return;
    }
    play({ restart: false });
  }

  function onClick(event) {
    const mascot = findMascot(event.target);
    if (!mascot) return;
    play({ restart: true });
  }

  function onKeydown(event) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const mascot = findMascot(event.target);
    if (!mascot) return;
    event.preventDefault?.();
    play({ restart: true });
  }

  if (doc) {
    doc.addEventListener(hoverEvent, onHover);
    doc.addEventListener('click', onClick);
    doc.addEventListener('keydown', onKeydown);
  }

  function destroy() {
    if (doc) {
      doc.removeEventListener(hoverEvent, onHover);
      doc.removeEventListener('click', onClick);
      doc.removeEventListener('keydown', onKeydown);
    }
    if (audio && typeof audio.removeEventListener === 'function') {
      audio.removeEventListener('play', onAudioPlay);
      audio.removeEventListener('ended', onAudioStop);
      audio.removeEventListener('pause', onAudioStop);
      audio.removeEventListener('error', onAudioStop);
    }
  }

  return { enhanceMascots, play, destroy };
}

function startAboutMascot() {
  if (typeof window !== 'undefined') {
    if (window.__tvbAboutMascotInstalled) return;
    window.__tvbAboutMascotInstalled = true;
  }
  const controller = createMascotController();
  controller.enhanceMascots();
  if (typeof MutationObserver !== 'undefined' && document.body) {
    const observer = new MutationObserver(() => controller.enhanceMascots());
    observer.observe(document.body, { childList: true, subtree: true });
  }
}

if (typeof document !== 'undefined') {
  if (document.body) startAboutMascot();
  else document.addEventListener('DOMContentLoaded', startAboutMascot, { once: true });
}
