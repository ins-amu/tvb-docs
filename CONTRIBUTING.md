# Contributing to TVB Documentation & JupyterLite Lab

Welcome to the unified TVB documentation and interactive lab repository. This guide explains our architecture, developer workflow, and authoring conventions.

---

## Architecture: Unified Single-Repository

This repository houses both the **MyST documentation** (served at `/`) and **JupyterLite** (served at `/lite/`) as two synchronized views over a single source of truth in `content/`.

```
content/
├── tutorials/       \
├── howtos/           |--> MyST Build  ---> _build/html/ (HTML Documentation at /)
├── reference/        |--> stage_lite  ---> _build/lite_contents/
├── explanation/      |                       │
└── demos/           /                        ▼
                                     JupyterLite Build ---> _build/html/lite/ (In-browser Lab at /lite/)
```

- **Single source of truth:** Markdown pages (`.md`) containing ` ```{code-cell} ipython3 ` are compiled into static HTML with executed outputs during `myst build`, and **automatically converted** into interactive `.ipynb` notebooks for JupyterLite (`/lite/lab/index.html`) and downloadable notebooks (`/notebooks/`) by `tools/stage_lite.py`.
- **Zero synchronization drift:** Authors write and maintain one document. Readers can read the text online, run the code live in their browser without installation, or download the notebook to run locally.

---

## Quickstart

You will need Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

All build tasks live in [`make.py`](make.py), a stdlib-only Python script, so
`make` is optional. On macOS/Linux use `make <task>` or `python3 make.py <task>`;
on Windows use `py -3 make.py <task>`.

### 1. Start Developing (Automatic Setup + Live Reload)
Running bare `make` (or `python3 make.py`) runs the default `dev` task:
```bash
make
```
This automatically:
1. Creates `.venv` if missing and verifies it matches `requirements/uv.lock` via `uv` (syncing if needed).
2. Incrementally stages downloadable `.ipynb` notebooks into `_build/notebooks/`.
3. Starts a live-reloading MyST dev server + unified local router at [http://localhost:8000](http://localhost:8000) (automatically picking the next free port if 8000 is occupied, or reporting the URL if this repo's server is already running).

Visit:
- **MyST Documentation (live reload):** [http://localhost:8000](http://localhost:8000)
- **Interactive JupyterLite Lab (if built):** [http://localhost:8000/lite/lab/index.html](http://localhost:8000/lite/lab/index.html)
- **Downloadable Notebooks:** [http://localhost:8000/notebooks/](http://localhost:8000/notebooks/)

Useful flags for local editing:
- `python3 make.py dev --no-execute` — skip notebook/cell execution for fast prose, CSS, or TOC edits.
- `python3 make.py status` — show build freshness, active dev server, and what `make` will run next.
- `python3 make.py serve --static` — preview the static `_build/html` build on port 8000 instead of live `myst start`.

### 2. Verify and Build Static Docs
Run the reference validation and static MyST build with code execution:
```bash
python3 make.py check
```
*(This runs `make.py refs` followed by `make.py docs`—the exact checks CI executes on pull requests. Locally, unchanged steps are skipped using `_build/.state.json`; pass `-f`/`--force` to rebuild everything.)*

### 3. Build JupyterLite (Optional)
To build the WebAssembly kernel and JupyterLite distribution locally into `_build/lite` (and sync it to `_build/html/lite`):
```bash
python3 make.py lite-setup   # only needed once, or auto-run by `make lite` if micromamba is installed
python3 make.py lite
```
`make lite` caches the emscripten WASM prefix in `_build/xeus-prefix/` keyed by `environment.yml`, builds into `_build/lite/` (so `make docs` never deletes it), and automatically chooses between a no-op, `tvbl`-only re-patch, content-only Lite update, or full rebuild.

Use `make clean` to clear generated HTML/site outputs while keeping expensive caches (`_build/execute`, `_build/cache`, `_build/xeus-prefix`, `_build/lite`), or `make clean-all` to wipe everything.

---

## Diátaxis Framework

Every page belongs to exactly one quadrant. Decide before you write, and keep the register consistent throughout the page:

| Quadrant | Directory | Orientation | Core Question |
|---|---|---|---|
| **Tutorials** | `content/tutorials/` | Learning-oriented (hands-on) | *Does the reader achieve a guaranteed result by following steps?* |
| **How-to guides** | `content/howtos/` | Task-oriented (recipes) | *Does the reader solve one specific real-world problem?* |
| **Reference** | `content/reference/` | Information-oriented (datasheets) | *Am I describing the system accurately and concisely?* |
| **Explanation** | `content/explanation/` | Understanding-oriented (theory) | *Am I discussing why things are the way they are?* |

Do not mix modes on one page. If a tutorial needs deep theory or mathematical derivations, link to an Explanation page instead of inflating the tutorial.

---

## Glossary

Add shared technical vocabulary to `content/glossary.md` in alphabetical order.
Keep each definition on a single source line of 25 words or fewer. Use native
`{term}` links for related definitions and a separate paragraph to link to an
Explanation page. Keep the rationale, assumptions, and examples in Explanation.

The MyST build links matching terms in rendered prose, including notebook
Markdown cells. The spelling variants and terms that require a deliberate link
are in `plugins/glossary-links.mjs`. To link an ambiguous term in its technical
sense, use `` {term}`monitors <Monitor>` ``. Check the rendered paragraph when
adding an alias since it can introduce links throughout the docs.

CI checks the built pages for broken glossary references and fails if any
are found. Known terms and aliases left unlinked in eligible prose produce
warnings with the source page and term names. Code, headings, and existing
links are outside this check. When reviewing a new concept, decide whether
it needs a definition, an alias, or an explicit link.

`python3 make.py docs` runs the same check and adds the glossary search field. After a
manual MyST HTML build, run `node tools/build_glossary.mjs` to do both.

## How to Contribute Content

There are two primary ways to contribute:

### Way 1: Authoring a New Page from a Template

Page templates with pre-configured frontmatter, Diátaxis structure, and interactive callouts are available in `content/_templates/`:

- `content/_templates/tutorial-template.md`
- `content/_templates/howto-template.md`
- `content/_templates/reference-model-card-template.md`
- `content/_templates/explanation-template.md`

#### Steps:
1. **Copy the template:**
   ```bash
   cp content/_templates/tutorial-template.md content/tutorials/my-new-tutorial.md
   ```
2. **Edit your page:**
   - Update frontmatter, title, and orientation sentence.
   - Use ` ```{code-cell} ipython3 ` blocks for executable code.
   - Ensure simulations are fast and deterministic (execution time < 10 seconds per page) so the build completes quickly.
3. **Automatic JupyterLite notebook generation:**
   - You do **not** need to manually create or sync a `.ipynb` notebook.
   - `tools/stage_lite.py` incrementally detects markdown pages with code cells and automatically generates:
     - Downloadable notebook (during `make.py docs` / `make.py dev`): `_build/notebooks/<quadrant>/<slug>.ipynb` (synced to `_build/html/notebooks/<quadrant>/<slug>.ipynb` on static builds).
     - Interactive notebook (during `make.py lite`): `_build/lite_contents/<quadrant>/<slug>.ipynb` (accessible in JupyterLite at `/lite/lab/index.html?path=<quadrant>/<slug>.ipynb`).
4. **Register in `_toc.yml`:**
   Add your page under the appropriate quadrant chapter in `_toc.yml`:
   ```yaml
   - caption: Tutorials
     chapters:
       - file: content/tutorials/index.md
       - file: content/tutorials/my-new-tutorial.md
   ```
5. **Verify:**
   Run `python3 make.py check` to ensure your code executes without errors and references resolve.

---

### Way 2: Migrating or Curating a Legacy Notebook from `content/demos/`

The `content/demos/` directory contains 60+ legacy demonstration notebooks from previous TVB releases. Contributors can claim and modernize these notebooks:

1. **Transform into a Diátaxis page:**
   - Distil the demo into a focused Tutorial, How-to guide, or Reference Model Card.
   - Follow the structure of `content/_templates/`.
   - Strip out extraneous debugging cells and unneeded widgets.
2. **Curate and modernize in place:**
   - Update deprecated TVB 2.x imports to modern TVB 3.0 / `tvbl` APIs.
   - Ensure imports and dependencies are pinned in `requirements/uv.lock` or `environment.yml`.
   - Once the notebook executes cleanly and deterministically within build time limits, remove `"execute": {"skip": true}` from the notebook metadata so CI verifies it on every PR.

---

## Linking Between Pages

MyST (`mystmd`) resolves links differently depending on whether the target is in `_toc.yml`, exists only on disk, or is staged post-build. Follow these rules so links work both in the built HTML site and on GitHub.

### Summary Table

| Target | Syntax | Example |
|---|---|---|
| Another doc page (`.md` or `.ipynb` in `_toc.yml`) | Relative path from current file | `[First Simulation](../tutorials/first-simulation.md)` |
| Page from `README.md` (repo root) | Relative path including `content/` | `[Tutorials](content/tutorials/index.md)` |
| Page with auto-filled title | Empty brackets or `{doc}` role | `[](../tutorials/first-simulation.md)` or `` {doc}`../tutorials/first-simulation.md` `` |
| Heading / labeled target on a page | Relative path + `#label` (or `{ref}`) | `[Section](../explanation/connectome.md#my-label)` |
| File **not** in `_toc.yml` (e.g. `CONTRIBUTING.md`) | Full GitHub URL (or `{download}` if download is intended) | `[CONTRIBUTING.md](https://github.com/ins-amu/tvb-docs/blob/main/CONTRIBUTING.md)` |
| JupyterLite Lab | Root-relative `/lite/...` path | `[Open in Lab](/lite/lab/index.html?path=tutorials/first-simulation.ipynb)` |
| Downloadable notebook | Root-relative `/notebooks/...` path | `[Download Notebook](/notebooks/tutorials/first-simulation.ipynb)` |
| Glossary term | `{term}` role | `` {term}`monitors <Monitor>` `` |
| External website | Full URL **with `https://`** | `[TVB](https://www.thevirtualbrain.org)` |

### 1. Cross-Linking Documentation Pages (`.md` and `.ipynb`)

Always use **relative file paths** from the file you are editing to the target `.md` or `.ipynb` file:

- From `README.md` (at the repository root), paths into `content/` must include `content/`:
  ```markdown
  [Tutorials](content/tutorials/index.md)
  ```
- From `content/tutorials/first-simulation.md` to `content/explanation/connectome.md`:
  ```markdown
  [Connectome](../explanation/connectome.md)
  ```
- From `content/reference/model-cards/wilson-cowan.md` to `content/tutorials/first-simulation.md`:
  ```markdown
  [First Simulation](../../tutorials/first-simulation.md)
  ```
- Linking to an `.ipynb` listed in `_toc.yml` works the same way:
  ```markdown
  [Jansen–Rit Simulation](../demos/simulate_region_jansen_rit.ipynb)
  ```

**Why relative file paths instead of `/slug` URLs?**
MyST derives URL slugs from **file basenames** and deduplicates collisions with `-1`, `-2`, etc. (for example, `content/demos/index.md` becomes `/index-4`). Relative file paths are resolved automatically to the right `/slug` at build time and also work when browsing source files on GitHub.

**Auto-filled titles:** Leave the link text empty (`[](../tutorials/first-simulation.md)`) or use the `{doc}` role (`` {doc}`../tutorials/first-simulation.md` ``) to have MyST insert the target page's title automatically.

### 2. Linking to Headings, Figures, and Labels

Assign an explicit target label above a heading/block with `(my-label)=` (or `:label: my-label` inside directives such as `::{figure}`), then link to it with `#my-label`:

```markdown
[See the section](#my-label)
[See the section on another page](../explanation/connectome.md#my-label)
```

You can also use `` {ref}`my-label` `` (inserts title) or `` {numref}`fig-example` `` (inserts numbered reference such as *Figure 1*).

### 3. Pitfall: Linking to `.md` Files Not in `_toc.yml`

If you write a relative link to a local file that exists on disk **but is not listed in `_toc.yml`** (such as `CONTRIBUTING.md` or `content/references.bib`), MyST does **not** build it as an HTML page. Instead, MyST treats it as a **static downloadable asset** (`static: true`), copies it to `/_public/<name>-<hash>.<ext>`, and renders a download link — clicking it downloads the raw `.md` file rather than opening a page.

- If the document should be a page on the site, add it to `_toc.yml`.
- If it is a repository-only file (like `CONTRIBUTING.md`), link to its GitHub URL instead of a relative path.

### 4. JupyterLite Lab & Notebook Downloads

`tools/stage_lite.py` stages converted notebooks into `/lite/` and `/notebooks/` *after* the MyST build, using paths relative to `content/` (with `.md` converted to `.ipynb`). Because MyST does not manage these routes, link to them using root-relative paths:

```markdown
[Open in JupyterLite Lab](/lite/lab/index.html?path=tutorials/first-simulation.ipynb)
[Download Notebook](/notebooks/tutorials/first-simulation.ipynb)
```

*(Note: `content/README.ipynb` is a JupyterLite-only landing notebook not in `_toc.yml`, so its links use paths relative to `content/`, e.g. `tutorials/first-simulation.ipynb`.)*

### 5. External URLs

Always include the `https://` scheme. Bare domains like `[TVB](thevirtualbrain.org)` are treated by MyST as unresolved relative file paths.

---

## Citations & References

All academic citations live in `content/references.bib`.

- Cite entries using standard MyST syntax: `[@CitationKey]` or `{cite}`.
- Relative bibliography path in frontmatter:
  - For pages in `content/<quadrant>/`: `bibliography: [../references.bib]`
  - For model cards in `content/reference/model-cards/`: `bibliography: [../../references.bib]`
- **Validate citations:** Run `python3 make.py refs`. This script checks every DOI in `references.bib` against the official Crossref API to detect dead DOIs, author mismatches, or title hallucinations.
- **Cache:** Crossref verification results are cached in `content/.refs-cache.json`. Commit any updates to this cache file alongside your changes in `content/references.bib`.

---

## Pull Request & CI Workflow

1. **Branch:** Create a focused feature branch:
   ```bash
   git checkout -b docs/<feature-or-topic>
   ```
2. **Local check:** Run `python3 make.py check`. This must pass with zero errors:
   - All Crossref references validate.
   - All code cells in all notebooks and executable markdown pages execute successfully.
   - Table of contents links and MyST syntax are valid.
3. **Commit & PR:** Open a Pull Request against `main`.
   - CI will run `python make.py check` (fast PR verification).
   - Once merged into `main`, GitHub Actions will build the complete unified MyST + JupyterLite artifact and deploy to GitHub Pages.
