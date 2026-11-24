// Hydrate [data-ppw-card] containers using the shared Trajecturtle bundle.
const widgetCssUrl = new URL('./widget.css', import.meta.url).href;
const widgetJsUrl = new URL('./widget.js', import.meta.url).href;

let widgetModulePromise = null;

function ensureStylesheet() {
  if (document.querySelector('link[data-ppw-stylesheet]')) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = widgetCssUrl;
  link.dataset.ppwStylesheet = 'true';
  document.head.append(link);
}

function loadWidgetModule() {
  if (!widgetModulePromise) {
    widgetModulePromise = import(widgetJsUrl);
  }
  return widgetModulePromise;
}

function createModelProxy(initialState) {
  const state = structuredClone(initialState);
  const listeners = new Map();
  return {
    get(key) {
      return state[key];
    },
    set(key, value) {
      if (Object.is(state[key], value)) return;
      state[key] = value;
      for (const cb of [...(listeners.get(`change:${key}`) || [])]) {
        cb(this, value);
      }
    },
    on(event, cb) {
      const list = listeners.get(event) || [];
      list.push(cb);
      listeners.set(event, list);
    },
    off(event, cb) {
      const list = listeners.get(event);
      if (!list) return;
      listeners.set(event, list.filter((fn) => fn !== cb));
    },
    save_changes() {},
    send() {},
  };
}

function cardKey(host) {
  if (host.dataset.ppwCard) return host.dataset.ppwCard;
  const cls = [...host.classList].find((c) => c.startsWith('ppw-card-key-'));
  return cls ? cls.slice('ppw-card-key-'.length) : '';
}

async function hydrateHost(host) {
  const key = cardKey(host);
  if (!key || host.dataset.ppwHydrated === 'pending' || host.dataset.ppwHydrated === 'done') {
    return;
  }
  host.dataset.ppwHydrated = 'pending';
  try {
    ensureStylesheet();
    const specUrl = new URL(`./specs/${encodeURIComponent(key)}.json`, import.meta.url).href;
    const [mod, resp] = await Promise.all([loadWidgetModule(), fetch(specUrl)]);
    if (!resp.ok) {
      throw new Error(`Failed to load phase-plane spec for "${key}" (${resp.status})`);
    }
    const specState = await resp.json();
    const model = createModelProxy(specState);
    host.replaceChildren();
    await mod.render({ model, el: host });
    host.dataset.ppwHydrated = 'done';
  } catch (err) {
    host.dataset.ppwHydrated = 'error';
    host.textContent = `Unable to load interactive phase plane (${err.message}).`;
    console.error('[tvb-phaseplane]', err);
  }
}

function scanAndHydrate() {
  for (const host of document.querySelectorAll('.ppw-card-host')) {
    hydrateHost(host);
  }
}

const startHydration = () => {
  scanAndHydrate();
  const observer = new MutationObserver(scanAndHydrate);
  observer.observe(document.body, { childList: true, subtree: true });
};

if (document.readyState === 'complete') {
  setTimeout(startHydration, 200);
} else {
  window.addEventListener('load', () => setTimeout(startHydration, 200), { once: true });
}
