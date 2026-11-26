# How-to guides

**How-to guides are task recipes: goal-oriented and practical.** A how-to guide
assumes you already know the basics and shows you how to solve one specific
problem, such as configuring a simulation, exporting results, or embedding the
trajecturtle phase-plane widget in a page.

How-to guides are for practitioners in a working context: they cut straight to
the steps and skip the teaching. If you are new here, start with the
[Tutorials](../tutorials/index.md); for exact parameter and API facts see
[Reference](../reference/index.md); for the reasoning behind the design see
[Explanation](../explanation/index.md).

## Core Recipes

- **[Adding a custom stimulus](custom-stimulus.md)** — Injecting spatio-temporal inputs into regional neural mass equations.
- **[Check an amortised posterior](../user-guide/inference/posterior-calibration.md)** — Parameter recovery, simulation-based calibration and coverage for simulation-based inference.
- **[Fit an evoked-response model with a likelihood](../user-guide/inference/erp-likelihood.md)** — Optimisation, MCMC, the Laplace approximation and model comparison.
- **[Writing a new model](write-a-model.md)** — Implementing and registering a custom neural mass model in TVB.
- **[Keep a Jansen–Rit network in the alpha regime](jansen-rit-alpha-network.md)** — Bounding the network input and placing the input noise so that each region's input stays in the range Jansen & Rit used for alpha.
- **[Simulate the Hopf whole-brain model](hopf-whole-brain-model.md)** — Stuart–Landau nodes at the bifurcation with diffusive coupling, noise and TR sampling in consistent units.

## Connectivity & Stimuli

Recipes for importing, generating, and perturbing structural networks:

- **[Using Your Own Connectivity](../demos/using_your_own_connectivity.ipynb)** — Loading external structural connectomes (weights, tract lengths, region centers) into TVB.
- **[Generate Surrogate Connectivity](../demos/generate_surrogate_connectivity.ipynb)** — Generating synthetic and null-model network connectomes.
- **[Simulate Region Stimulus](../demos/simulate_region_stimulus.ipynb)** — Applying pulsed or oscillatory stimulation to selected brain regions.
- **[Simulate Region BOLD Stimulus](../demos/simulate_region_bold_stimulus.ipynb)** — Simulating hemodynamic BOLD responses driven by regional stimulation.
- **[Applying Multiple Stimuli](../demos/multiple_stimuli.ipynb)** — Configuring concurrent independent stimuli across distinct nodes.
- **[Simulate BOLD Continuation](../demos/simulate_bold_continuation.ipynb)** — Advancing and continuing BOLD simulations across consecutive time windows.

## Forward Models & Analyzers

Recipes for computing neuroimaging projections and post-processing signals:

- **[Simulate Surface SEEG, EEG, MEG](../demos/simulate_surface_seeg_eeg_meg.ipynb)** — Computing forward projections from cortical surface dynamics to EEG, MEG, and SEEG channels.
- **[Simulate SEEG with Observation Noise](../demos/simulate_seeg_from_epileptors_with_observation_noise.ipynb)** — Forward SEEG modeling from Epileptor nodes with realistic channel noise.
- **[Analyze Region Correlation Coefficients](../demos/analyze_region_corrcoef.ipynb)** — Computing pairwise Pearson correlation and functional connectivity matrices.
- **[Analyze Power Spectra](../demos/analyze_power_spectra.ipynb)** — Spectral analysis (FFT, Welch, spectrograms) of simulated time series.
- **[Display Source Sensor Geometry](../demos/display_source_sensor_geometry.ipynb)** — Visualizing sensors, lead fields, and anatomical source spaces.

## Backends, Hybrid & HPC

Recipes for high-performance computing, GPU acceleration, and hybrid co-simulation:

- **[Using Backends](../demos/using_backends.ipynb)** — Switching between computational backends (NumPy, Numba, SciPy) for simulation execution.
- **[Simulate Hybrid Parameter Sweeps](../demos/simulate_hybrid_parameter_sweeps.ipynb)** — Automated parameter explorations across hybrid model configurations.
- **[Simulate Hybrid Stimuli & Advanced](../demos/simulate_hybrid_stimuli_and_advanced.ipynb)** — Complex stimulation paradigms in multiscale hybrid architectures.
- **[Simulate Hybrid Stochastic & BOLD](../demos/simulate_hybrid_stochastic_and_bold.ipynb)** — Stochastic multiscale integration coupled with hemodynamic monitor pipelines.
- **[GPU Parallel Parameter Sweeps](../demos/gpu_parallel_parameter_sweeps.ipynb)** — Massively parallel sweeps across parameter spaces utilizing GPU acceleration.
- **[Model Generation using DSL](../demos/model_generation_using_dsl.ipynb)** — Defining neural mass models using TVB's domain-specific language (DSL).
- **[RateML Python TVB](../demos/RateML_Python_TVB.ipynb)** — Generating efficient Python code from RateML model specifications.
- **[RateML CUDA on HPC](../demos/RateML_CUDA_on_HPC.ipynb)** — Deploying RateML-generated CUDA kernels on high-performance computing clusters.
- **[Zerlaut Parameter Sweep on HPC](../demos/Zerlaut_parametersweep_HPC.ipynb)** — Large-scale parallel parameter sweeps of Zerlaut mean-field models on supercomputing clusters.

## Framework, REST & Atlases

Recipes for interacting with the TVB web framework, REST APIs, and external brain atlases:

- **[Integrating with SIIBRA](../demos/siibra_tvb_api.ipynb)** — Fetching brain parcellations, regional data, and connectivity matrices from the EBRAINS Siibra API.
- **[Interacting with Allen Institute Data](../demos/interacting_with_Allen.ipynb)** — Integrating mouse connectivity and gene expression data from the Allen Brain Atlas.
- **[Interacting with the Framework](../demos/interacting_with_the_framework.ipynb)** — Operating TVB framework storage, projects, and data types programmatically.
- **[REST API: Fire Simulation](../demos/interacting_with_rest_api_fire_simulation.ipynb)** — Launching and monitoring remote simulations via the TVB REST API client.
- **[REST API: Launch Operations](../demos/interacting_with_rest_api_launch_operations.ipynb)** — Triggering analyzer and importer operations over HTTP REST endpoints.
- **[Launching BIDS Derivatives Importer](../demos/launching_bids_adapter.ipynb)** — Importing neuroimaging datasets formatted according to the BIDS standard.
- **[Generate TimeSeries H5 from Library](../demos/generate_ts_h5_from_library.ipynb)** — Exporting TVB library time series into HDF5 format for the TVB GUI.
- **[Encrypt Data](../demos/encrypt_data.ipynb)** — Cryptographic protection and client-side encryption of neuroimaging files.
- **[Export, Encrypt & Decrypt Data](../demos/export_encrypt_decrypt_data.ipynb)** — Secure data exchange workflows for sensitive clinical neuroimaging data.
