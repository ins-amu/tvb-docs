(() => {
  const words = (text) => text.normalize('NFKD').replace(/\p{M}/gu, '')
    .toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [];

  // Allow insertions, deletions, substitutions and adjacent transpositions.
  function nearlyMatches(query, word) {
    const limit = query.length >= 8 ? 2 : 1;
    if (query.length < 4 || Math.abs(query.length - word.length) > limit) return false;
    const rows = [Array.from({ length: word.length + 1 }, (_, j) => j)];
    for (let i = 1; i <= query.length; i++) {
      const row = [i];
      for (let j = 1; j <= word.length; j++) {
        const cost = Number(query[i - 1] !== word[j - 1]);
        row[j] = Math.min(row[j - 1] + 1, rows[i - 1][j] + 1, rows[i - 1][j - 1] + cost);
        if (i > 1 && j > 1 && query[i - 1] === word[j - 2] && query[i - 2] === word[j - 1]) {
          row[j] = Math.min(row[j], rows[i - 2][j - 2] + 1);
        }
      }
      rows.push(row);
    }
    return rows[query.length][word.length] <= limit;
  }

  function install() {
    if (!/\/glossary\/?$/.test(location.pathname) || document.getElementById('glossary-search')) return;
    const entries = [...document.querySelectorAll('dt[id^="term-"]')]
      .filter((term) => term.nextElementSibling?.matches('dd'))
      .map((term) => {
        const definition = term.nextElementSibling;
        const text = definition.querySelector('p')?.textContent ?? definition.textContent;
        return { term, definition, words: [...new Set(words(`${term.textContent} ${text}`))] };
      });
    if (!entries.length) return;

    const lists = [...new Set(entries.map(({ term }) => term.parentElement))];
    const box = document.createElement('div');
    box.id = 'glossary-search';
    const label = document.createElement('label');
    label.htmlFor = 'glossary-query';
    label.textContent = 'Search glossary';
    const input = document.createElement('input');
    input.id = 'glossary-query';
    input.type = 'search';
    input.placeholder = 'Term or definition';
    input.autocomplete = 'off';
    const status = document.createElement('span');
    status.setAttribute('role', 'status');
    box.append(label, input, status);
    const sections = lists.map((list) => {
      const wrapper = list.parentElement;
      const previous = list.previousElementSibling ?? wrapper.previousElementSibling;
      return { list, heading: previous?.matches('h2') ? previous : null };
    });
    (sections[0].heading ?? lists[0]).before(box);

    function update() {
      const query = words(input.value);
      let count = 0;
      for (const entry of entries) {
        const visible = query.every((part) => entry.words.some((word) =>
          word.includes(part) || nearlyMatches(part, word)));
        entry.term.hidden = entry.definition.hidden = !visible;
        if (visible) count++;
      }
      for (const { list, heading } of sections) {
        list.hidden = !list.querySelector('dt:not([hidden])');
        if (heading) heading.hidden = list.hidden;
      }
      status.textContent = !query.length ? '' : count
        ? `${count} matching ${count === 1 ? 'entry' : 'entries'}`
        : 'No matching entries';
    }

    input.addEventListener('input', update);
    input.addEventListener('search', update);
    // A link to a filtered-out entry should still take the reader to it.
    const revealTarget = (event) => {
      const link = event.target.closest('a[href*="#term-"]');
      if (!link) return;
      const target = new URL(link.href);
      const entry = entries.find(({ term }) => `#${term.id}` === target.hash);
      if (entry?.term.hidden) {
        input.value = '';
        update();
      }
    };
    box.parentElement.addEventListener('click', revealTarget);
  }

  function start() {
    // Let the MyST client hydrate the static page before adding the control.
    const setup = () => {
      install();
      new MutationObserver(install).observe(document.body, { childList: true, subtree: true });
    };
    if (window.requestIdleCallback) window.requestIdleCallback(setup);
    else window.setTimeout(setup, 0);
  }

  if (document.readyState === 'complete') start();
  else window.addEventListener('load', start, { once: true });
})();
