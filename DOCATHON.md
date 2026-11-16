# TVB Docathon Prep Kit & Contributor Backlog

This document prepares Marmaduke and the TVB documentation team for the contributor kickoff meeting. It contains a 10-minute walkthrough script with live demo steps, followed by a prioritized, ready-to-claim backlog of concrete authoring assignments.

---

## Part 1: 10-Minute Walkthrough Script

*Use this script to guide contributors through the converged repository architecture, authoring workflow, and pull request validation.*

### Timetable

| Time | Segment | Goal |
|---|---|---|
| **00:00 – 02:30** | **Step 1: Tour of the Unified Repo** | Explain the single-source architecture (`content/` $\to$ MyST + JupyterLite). |
| **02:30 – 06:30** | **Step 2: Live Demo (3-Minute Edit)** | Copy template, add code, run `make check`, preview in browser. |
| **06:30 – 08:30** | **Step 3: PR & CI Workflow** | Explain fast PR checks vs. automated GitHub Pages publishing. |
| **08:30 – 10:00** | **Step 4: Claiming Backlog Items** | Direct contributors to the backlog table below and kickoff hacking. |

---

### Step 1: Tour of the Unified Repo (2.5 mins)

**Speaker Notes:**
> *"Welcome everyone! Today we have completely converged the TVB documentation and interactive lab into a single repository. Previously, documentation and JupyterLite notebooks lived in separate silos and quickly drifted apart. Now, there is exactly one source of truth: `content/`."*

**Key points to highlight:**
1. **Unified Dual Views:**
   - **Static Book at `/`:** Clean, searchable MyST HTML book built with executed figures.
   - **Interactive Lab at `/lite/`:** Fully client-side JupyterLite environment running Python 3.12 via WebAssembly (Xeus-Python) with TVB, NumPy, SciPy, and Numba.
2. **Diátaxis Quadrants:**
   - `content/tutorials/`: Step-by-step learning by doing.
   - `content/howtos/`: Practical goal-oriented recipes.
   - `content/reference/`: Technical datasheets and model cards.
   - `content/explanation/`: Conceptual background, mathematics, and design trade-offs.
3. **Automatic Notebook Generation:**
   - When you write a `.md` page with ` ```{code-cell} ipython3 `, `tools/stage_lite.py` automatically converts it into a runnable `.ipynb` notebook staged for both JupyterLite and direct download.
   - You never have to manually maintain both a `.md` file and a `.ipynb` file!

---

### Step 2: Live Demo — "Adding a Section in 3 Minutes" (4 mins)

**Speaker Notes:**
> *"Let's see how effortless it is to create a new page and verify it locally."*

**Live actions to perform in terminal:**

1. **Pick and copy a template from `content/_templates/`:**
   ```bash
   cp content/_templates/howto-template.md content/howtos/inspect-connectome.md
   ```
2. **Register the new page in `_toc.yml`:**
   Open `_toc.yml` and add `content/howtos/inspect-connectome.md` under the `How-to guides` section:
   ```yaml
   - caption: How-to guides
     chapters:
       - file: content/howtos/index.md
       - file: content/howtos/inspect-connectome.md
   ```
3. **Open `content/howtos/inspect-connectome.md` and customize:**
   - Set title: `# How-to: Inspect connectome weights and tract lengths`
   - Set interactive links: `/lite/lab/index.html?path=howtos/inspect-connectome.ipynb`
   - Add a fast code cell using `tvb.simulator.lab.connectivity`.
4. **Run local verification:**
   ```bash
   make check
   ```
   *Explain that `make check` executes `make refs` (verifying DOIs) and `make docs` (compiling MyST, executing all code cells, and staging JupyterLite notebooks).*
5. **Serve and inspect:**
   ```bash
   make serve
   ```
   Open `http://localhost:8000/howtos/inspect-connectome.html`:
   - Point out the rendered text and freshly computed figures.
   - Click **"Open in JupyterLite Lab"** to demonstrate seamless transition to `http://localhost:8000/lite/lab/index.html?path=howtos/inspect-connectome.ipynb` with zero software installation required!

---

### Step 3: Pull Request & CI Flow (2 mins)

**Speaker Notes:**
> *"How do we guarantee that our documentation never breaks and our references stay accurate?"*

1. **Local Pre-Flight:**
   - Run `make check`. If it exits `0`, your code executes cleanly, all imports resolve, and references are valid.
2. **Automated Crossref Verification (`make refs`):**
   - Every citation in `content/references.bib` is verified against Crossref's API to ensure no hallucinated papers or broken DOIs are committed. Results are cached in `content/.refs-cache.json`.
3. **CI on Pull Requests:**
   - GitHub Actions runs `make check` on every PR. Builds complete rapidly without needing to rebuild heavy WASM binary packages.
4. **Automated CD on `main`:**
   - Once merged to `main`, the CI builds the complete static documentation and JupyterLite WASM bundle and deploys immediately to GitHub Pages.

---

## Part 2: Ready-to-Claim Docathon Backlog

Claim an item by posting in the chat or adding your name to the table. Every item has a concrete starting source and verifiable acceptance criteria.

| ID | Assignment | Quadrant | Source (`content/demos/` or `tvb_library`) | Target Path | Acceptance Criteria |
|:---|:---|:---|:---|:---|:---|
| **TUT-01** | **Regional Jansen–Rit Simulation** | Tutorial | `content/demos/simulate_region_jansen_rit.ipynb` | `content/tutorials/jansen-rit-simulation.md` | Complete step-by-step tutorial configuring Jansen–Rit on 76-region connectome, running 100 ms simulation, plotting alpha rhythm traces and power spectrum. Deterministic execution < 5s. |
| **TUT-02** | **Cortex Surface Simulation** | Tutorial | `content/demos/simulate_surface_seeg_eeg_meg.ipynb`, `exploring_a_surface_mesh.ipynb` | `content/tutorials/surface-simulation.md` | Guide loading cortex triangulation, setting local surface coupling, projecting to scalp EEG/MEG sensors via leadfield, and visualizing source vs sensor activations. |
| **TUT-03** | **BOLD Hemodynamic Monitoring** | Tutorial | `content/demos/exploring_the_bold_monitor.ipynb`, `simulate_region_bold_stimulus.ipynb` | `content/tutorials/bold-monitoring.md` | Tutorial configuring Balloon-Windkessel hemodynamic monitor, downsampling to TR=2.0s, comparing neural state variables against synthetic fMRI BOLD signals. |
| **TUT-04** | **Structural Lesion & Virtual Resection** | Tutorial | `content/demos/exploring_resting_state_in_epilepsy.ipynb` | `content/tutorials/structural-lesion.md` | Tutorial demonstrating virtual surgical resection by zeroing specific connectome edges/nodes; plots pre- vs post-lesion regional synchrony and functional connectivity. |
| **HOW-01** | **Load Custom Connectome Data** | How-to | `content/demos/using_your_own_connectivity.ipynb` | `content/howtos/load-custom-connectivity.md` | Recipe showing how to construct TVB `Connectivity` from raw NumPy matrices / BIDS text files, assign ROI labels, validate symmetry, and set tract propagation speed. |
| **HOW-02** | **Add Regional & Surface Stimuli** | How-to | `content/demos/simulate_region_stimulus.ipynb`, `multiple_stimuli.ipynb` | `content/howtos/add-stimulus.md` | Recipe defining spatial weighting vectors and temporal waveforms (PulseTrain, Sinusoid), attaching stimuli to simulator, and plotting the evoked response. |
| **HOW-03** | **Compute Functional Connectivity & Power Spectra** | How-to | `content/demos/analyze_region_corrcoef.ipynb`, `analyze_power_spectra.ipynb` | `content/howtos/compute-functional-connectivity.md` | Recipe computing static Pearson FC correlation matrices and Welch power spectral densities from simulated time series; plots correlation heatmaps and frequency spectra. |
| **HOW-04** | **Run Parameter Sweeps with Numba / Hybrid Backend** | How-to | `content/demos/simulate_hybrid_parameter_sweeps.ipynb`, `gpu_parallel_parameter_sweeps.ipynb` | `content/howtos/run-parameter-sweeps.md` | Recipe setting up 2D parameter grid sweeps ($G$ vs. speed), executing accelerated simulations with the TVB Hybrid backend, and plotting stability/synchrony heatmaps. |
| **HOW-05** | **Define Custom Models with RateML DSL** | How-to | `content/demos/model_generation_using_dsl.ipynb`, `RateML_Python_TVB.ipynb` | `content/howtos/define-model-rateml.md` | Recipe detailing XML RateML syntax for declaring state variables, parameters, and ODEs; generates and tests the compiled Python/Numba model class. |
| **HOW-06** | **Query Brain Atlases with `siibra`** | How-to | `content/demos/siibra_tvb_api.ipynb` | `content/howtos/query-siibra-atlas.md` | Recipe querying EBRAINS multiscale atlases with `siibra-python`, extracting regional receptor distributions, and assigning heterogeneous parameters to TVB nodes. |
| **REF-01** | **Model Card: GastSollaKennedy** | Reference | `tvb_library/tvb/simulator/models/`, `content/demos/simulate_gast_solla_kennedy_resting_state.ipynb` | `content/reference/model-cards/gast-solla-kennedy.md` | Datasheet specifying exact ODEs, state variables ($r, v$), parameter bounds, coupling `cvar`, typical dynamics, and paper reference [@Gast2024]. |
| **REF-02** | **Model Card: Zerlaut Adaptation Models** | Reference | `tvb_library/tvb/simulator/models/zerlaut.py`, `content/demos/Zerlaut_parametersweep_HPC.ipynb` | `content/reference/model-cards/zerlaut-adaptation.md` | Datasheet specifying first- and second-order adaptation models, semi-analytical transfer function equations, parameter tables, and reference [@Zerlaut2018]. |
| **REF-03** | **Model Card: Epileptor Variants (RestingState & Codim3)** | Reference | `content/demos/exploring_the_epileptor_codim_3_model.ipynb`, `exploring_resting_state_in_epilepsy.ipynb` | `content/reference/model-cards/epileptor-variants.md` | Datasheet detailing `EpileptorRestingState` and `EpileptorCodim3`, permittivity time constants, bifurcation mechanisms, parameter tables, and references. |
| **REF-04** | **Model Cards: CerebellarMF & Hopfield** | Reference | `tvb_library/tvb/simulator/models/` | `content/reference/model-cards/cerebellar-mf.md`, `hopfield.md` | Complete datasheets with state equations, parameter tables, coupling points, and citations for cerebellar mean-field and Hopfield models. |
| **EXP-01** | **Numerical Integrators & Choosing $\Delta t$** | Explanation | `content/demos/integrators_comparison.ipynb`, `integrators_presentation.ipynb` | `content/explanation/numerical-integrators.md` | Conceptual guide comparing Euler, Heun, and RK4; discusses numerical stiffness, discretization drift, noise terms, and conduction delay constraints on $\Delta t$. |
| **EXP-02** | **Resting-State & Epileptor Bifurcations** | Explanation | `content/demos/exploring_resting_state_in_epilepsy.ipynb`, `exploring_epileptor_2d.ipynb` | `content/explanation/epileptor-bifurcations.md` | Conceptual exploration of fast-slow dynamical systems, saddle-node / homoclinic / Hopf bifurcation mechanisms underlying seizure initiation, propagation, and termination. |

---

## Part 3: Contributor Checklist for PRs

Before opening your pull request, verify the following checklist:

1. **Quadrants & Templates:**
   - Did you start from a template in `content/_templates/`?
   - Does your page focus strictly on one Diátaxis quadrant without mixing modes?
2. **Deterministic & Fast Builds:**
   - Do all code cells execute deterministically in $<10$ seconds?
   - Did you keep `simulation_length` short (e.g. $50 - 100\text{ ms}$) so the entire book builds quickly?
3. **Table of Contents:**
   - Is your new file registered in `_toc.yml` under the appropriate caption?
4. **Citations:**
   - Are all references registered in `content/references.bib` with valid DOIs?
   - Did `make refs` pass and update `content/.refs-cache.json`?
5. **Local CI Verification:**
   - Does `make check` pass with zero errors on your branch?
