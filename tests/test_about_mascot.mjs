import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import {
  MASCOT_SELECTOR,
  PLAYING_CLASS,
  createMascotController,
  resolveAudioUrl,
} from '../content/_static/about-mascot.mjs';
import { stageAboutMascot } from '../tools/stage_about_mascot.mjs';

function makeFakeElement({ isMascot = false, children = [] } = {}) {
  const attrs = new Map();
  const classes = new Set(isMascot ? ['tvb-about-mascot'] : []);
  const el = {
    children,
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      toggle: (c, force) => {
        if (force === undefined) {
          if (classes.has(c)) classes.delete(c);
          else classes.add(c);
        } else if (force) {
          classes.add(c);
        } else {
          classes.delete(c);
        }
      },
      contains: (c) => classes.has(c),
    },
    hasAttribute: (k) => attrs.has(k),
    setAttribute: (k, v) => attrs.set(k, String(v)),
    getAttribute: (k) => attrs.get(k) ?? null,
    closest: (selector) => (selector === MASCOT_SELECTOR && isMascot ? el : null),
    contains: (other) => other === el || children.includes(other),
  };
  for (const child of children) {
    child.closest = (selector) => (selector === MASCOT_SELECTOR && isMascot ? el : null);
  }
  return el;
}

function makeFakeDocument(mascots = []) {
  const listeners = new Map();
  return {
    querySelectorAll: (selector) => (selector === MASCOT_SELECTOR ? mascots : []),
    addEventListener: (type, fn) => {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(fn);
    },
    removeEventListener: (type, fn) => {
      listeners.get(type)?.delete(fn);
    },
    dispatch: (type, event = {}) => {
      for (const fn of [...(listeners.get(type) ?? [])]) {
        fn(event);
      }
    },
    listenerCount: (type) => listeners.get(type)?.size ?? 0,
  };
}

function makeFakeAudio({ rejectPlay = false, throwOnCurrentTime = false } = {}) {
  const listeners = new Map();
  let _currentTime = 0;
  const audio = {
    paused: true,
    ended: false,
    playCalls: 0,
    rejectNextPlay: rejectPlay,
    get currentTime() {
      return _currentTime;
    },
    set currentTime(val) {
      if (throwOnCurrentTime) {
        const err = new Error('InvalidStateError');
        err.name = 'InvalidStateError';
        throw err;
      }
      _currentTime = val;
    },
    addEventListener: (type, fn) => {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(fn);
    },
    removeEventListener: (type, fn) => {
      listeners.get(type)?.delete(fn);
    },
    emit: (type) => {
      for (const fn of [...(listeners.get(type) ?? [])]) fn();
    },
    play: () => {
      audio.playCalls += 1;
      if (audio.rejectNextPlay) {
        audio.rejectNextPlay = false;
        return Promise.reject(new Error('NotAllowedError'));
      }
      audio.paused = false;
      audio.ended = false;
      audio.emit('play');
      return Promise.resolve();
    },
    finish: () => {
      audio.paused = true;
      audio.ended = true;
      audio.emit('ended');
    },
  };
  return audio;
}

test('resolveAudioUrl resolves relative to module URL including BASE_URL subpaths', () => {
  assert.equal(
    resolveAudioUrl('http://localhost:8000/about-mascot.mjs'),
    'http://localhost:8000/goat.opus',
  );
  assert.equal(
    resolveAudioUrl('https://ins-amu.github.io/tvb-docs/about-mascot.mjs'),
    'https://ins-amu.github.io/tvb-docs/goat.opus',
  );
});

test('hover plays on mouse pointerover, avoids interrupting active playback, and replays after ended', () => {
  const mascot = makeFakeElement({ isMascot: true });
  const doc = makeFakeDocument([mascot]);
  const audio = makeFakeAudio();
  let created = 0;
  const controller = createMascotController({
    doc,
    win: { PointerEvent: function () {} },
    audioUrl: 'http://localhost:8000/goat.opus',
    createAudio: () => {
      created += 1;
      return audio;
    },
  });

  // No audio created yet until mascot exists & enhanced or interacted with
  assert.equal(created, 0);
  controller.enhanceMascots();
  assert.equal(created, 1);
  assert.equal(mascot.getAttribute('role'), 'button');
  assert.equal(mascot.getAttribute('tabindex'), '0');
  assert.equal(mascot.getAttribute('aria-label'), 'Play goat sound');

  // Mouse hover plays
  doc.dispatch('pointerover', { pointerType: 'mouse', target: mascot, relatedTarget: null });
  assert.equal(audio.playCalls, 1);
  assert.equal(mascot.classList.contains(PLAYING_CLASS), true);

  // Re-hovering while still playing does not restart
  doc.dispatch('pointerover', { pointerType: 'mouse', target: mascot, relatedTarget: null });
  assert.equal(audio.playCalls, 1);

  // Finish playback; playing class clears and hovering again plays
  audio.finish();
  assert.equal(mascot.classList.contains(PLAYING_CLASS), false);
  doc.dispatch('pointerover', { pointerType: 'mouse', target: mascot, relatedTarget: null });
  assert.equal(audio.playCalls, 2);

  controller.destroy();
  assert.equal(doc.listenerCount('pointerover'), 0);
});

test('touch pointerover is ignored while click restarts playback even mid-play', () => {
  const child = makeFakeElement({ isMascot: false });
  const mascot = makeFakeElement({ isMascot: true, children: [child] });
  const doc = makeFakeDocument([mascot]);
  const audio = makeFakeAudio();
  const controller = createMascotController({
    doc,
    win: { PointerEvent: function () {} },
    createAudio: () => audio,
  });

  doc.dispatch('pointerover', { pointerType: 'touch', target: mascot, relatedTarget: null });
  assert.equal(audio.playCalls, 0);

  // Internal child transition is ignored
  doc.dispatch('pointerover', { pointerType: 'mouse', target: child, relatedTarget: mascot });
  assert.equal(audio.playCalls, 0);

  // Click starts playback
  doc.dispatch('click', { target: mascot });
  assert.equal(audio.playCalls, 1);
  audio.currentTime = 2.5;

  // Second click restarts from 0 even while playing
  doc.dispatch('click', { target: child });
  assert.equal(audio.playCalls, 2);
  assert.equal(audio.currentTime, 0);

  controller.destroy();
});

test('keyboard Enter and Space activate playback and call preventDefault', () => {
  const mascot = makeFakeElement({ isMascot: true });
  const doc = makeFakeDocument([mascot]);
  const audio = makeFakeAudio();
  const controller = createMascotController({
    doc,
    win: {},
    createAudio: () => audio,
  });

  let prevented = 0;
  doc.dispatch('keydown', { key: 'Enter', target: mascot, preventDefault: () => { prevented += 1; } });
  assert.equal(audio.playCalls, 1);
  assert.equal(prevented, 1);

  doc.dispatch('keydown', { key: ' ', target: mascot, preventDefault: () => { prevented += 1; } });
  assert.equal(audio.playCalls, 2);
  assert.equal(prevented, 2);

  doc.dispatch('keydown', { key: 'Tab', target: mascot, preventDefault: () => { prevented += 1; } });
  assert.equal(audio.playCalls, 2);
  assert.equal(prevented, 2);

  controller.destroy();
});

test('autoplay rejection and InvalidStateError on currentTime are handled gracefully', async () => {
  const mascot = makeFakeElement({ isMascot: true });
  const doc = makeFakeDocument([mascot]);
  const audio = makeFakeAudio({ rejectPlay: true, throwOnCurrentTime: true });
  const controller = createMascotController({
    doc,
    win: { PointerEvent: function () {} },
    createAudio: () => audio,
  });

  // Hover rejected by autoplay policy — should not throw or leave playing class stuck
  doc.dispatch('pointerover', { pointerType: 'mouse', target: mascot, relatedTarget: null });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(audio.playCalls, 1);
  assert.equal(mascot.classList.contains(PLAYING_CLASS), false);

  // Subsequent click succeeds
  doc.dispatch('click', { target: mascot });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(audio.playCalls, 2);
  assert.equal(mascot.classList.contains(PLAYING_CLASS), true);

  controller.destroy();
});

test('stageAboutMascot copies assets and injects relative module script idempotently', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'tvb-mascot-stage-'));
  try {
    const htmlDir = join(tmp, '_build', 'html');
    mkdirSync(join(htmlDir, 'about-this-site'), { recursive: true });
    mkdirSync(join(htmlDir, 'lite', 'lab'), { recursive: true });
    mkdirSync(join(htmlDir, 'notebooks'), { recursive: true });
    mkdirSync(join(htmlDir, '_static'), { recursive: true });

    writeFileSync(join(htmlDir, 'index.html'), '<html><body><h1>Home</h1></body></html>');
    writeFileSync(
      join(htmlDir, 'about-this-site', 'index.html'),
      '<html><body><div class="tvb-about-mascot"></div></body></html>',
    );
    writeFileSync(join(htmlDir, 'phase-plane-standalone.html'), '<html><body>standalone</body></html>');
    writeFileSync(join(htmlDir, 'lite', 'lab', 'index.html'), '<html><body>lite</body></html>');
    writeFileSync(join(htmlDir, 'notebooks', 'nb.html'), '<html><body>nb</body></html>');
    writeFileSync(join(htmlDir, '_static', 'ignored.html'), '<html><body>ignored</body></html>');

    const first = stageAboutMascot({ htmlDir });
    assert.equal(first.injected, 2);
    assert.equal(existsSync(join(htmlDir, 'about-mascot.mjs')), true);
    assert.equal(existsSync(join(htmlDir, 'goat.opus')), true);

    const rootHtml = readFileSync(join(htmlDir, 'index.html'), 'utf8');
    assert.match(
      rootHtml,
      /<script id="tvb-about-mascot-script" type="module" src="about-mascot\.mjs"><\/script><\/body>/,
    );

    const nestedHtml = readFileSync(join(htmlDir, 'about-this-site', 'index.html'), 'utf8');
    assert.match(
      nestedHtml,
      /<script id="tvb-about-mascot-script" type="module" src="\.\.\/about-mascot\.mjs"><\/script><\/body>/,
    );

    // Excluded directories/files remain untouched
    assert.equal(
      readFileSync(join(htmlDir, 'phase-plane-standalone.html'), 'utf8').includes('tvb-about-mascot-script'),
      false,
    );
    assert.equal(
      readFileSync(join(htmlDir, 'lite', 'lab', 'index.html'), 'utf8').includes('tvb-about-mascot-script'),
      false,
    );
    assert.equal(
      readFileSync(join(htmlDir, 'notebooks', 'nb.html'), 'utf8').includes('tvb-about-mascot-script'),
      false,
    );
    assert.equal(
      readFileSync(join(htmlDir, '_static', 'ignored.html'), 'utf8').includes('tvb-about-mascot-script'),
      false,
    );

    // Idempotent on second run
    const second = stageAboutMascot({ htmlDir });
    assert.equal(second.injected, 0);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});
