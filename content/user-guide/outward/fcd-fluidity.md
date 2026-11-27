---
title: Functional connectivity dynamics and fluidity
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../../references.bib
---
# Functional connectivity dynamics and fluidity

A functional connectivity (FC) matrix computed over a whole recording is an
average. It says which regions co-vary over the session, but not whether they
did so throughout or only during part of it. Hansen et al. showed that this
matters for resting-state fMRI [@hansen2015]. When FC is computed in 60 s windows, it often stays nearly
unchanged for minutes, then turns into an almost unrelated pattern within the
span of one window, and earlier configurations can come back later in the
same session. Whole-brain models tuned only to reproduce the static FC did
not show this switching, even when they matched the static matrix well.

**Functional connectivity dynamics** (FCD) is the representation they
introduced for this behaviour: a matrix that compares the FC of every time
window with the FC of every other window. **Fluidity** reduces that matrix to a
single number, the variance of its values. Both are used as data features when
whole-brain models are fitted to, or inferred from, resting-state recordings
[@deco2017; @lavanga2023; @hashemi2024; @ziaeemehr2025].

## From windows to the FCD matrix

Take regional signals $x_i(t)$, $i = 1, \dots, N$, sampled at $T$ time points.
Choose a window of $w$ samples and a step of $s$ samples. The window that starts
at sample $t$ gives one FC matrix,

$$
\mathrm{FC}_{ij}(t) = \operatorname{corr}\bigl(x_i[t, t+w),\; x_j[t, t+w)\bigr),
$$

and there are $M = \lfloor (T - w)/s \rfloor + 1$ such windows. Because
$\mathrm{FC}(t)$ is symmetric with ones on the diagonal, only its
$N(N-1)/2$ entries above the diagonal carry information. Writing them as a
vector $\mathbf{v}(t)$, the FCD is the $M \times M$ matrix of correlations
between those vectors [@hansen2015]:

$$
\mathrm{FCD}(t_1, t_2) = \operatorname{corr}\bigl(\mathbf{v}(t_1),\, \mathbf{v}(t_2)\bigr).
$$

An entry near 1 means the two windows had the same *pattern* of connectivity.
The Pearson correlation ignores an overall shift or rescaling of the vector, so
two windows with the same pattern at different overall strength still score
high. An entry near 0 means the patterns are unrelated.

```{code-cell} ipython3
:tags: [hide-input]

%matplotlib inline
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, sosfiltfilt

TR = 2.0          # sampling interval (s)
T = 600           # 600 samples = 20 min
N = 10            # regions
w = 30            # window: 30 samples = 60 s
k = w             # diagonal offset for fluidity (step = 1 sample)

def modular(groups, rho):
    """Correlation matrix with correlation rho inside each group, 0 between."""
    C = np.eye(N)
    for g in groups:
        C[np.ix_(g, g)] = rho
    np.fill_diagonal(C, 1.0)
    return C

C_A = modular([[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]], 0.8)
C_B = modular([[0, 1, 2, 5, 6], [3, 4, 7, 8, 9]], 0.8)
sos = butter(2, [0.04, 0.07], btype="band", fs=1 / TR, output="sos")

def toy_signals(seed):
    """Two signals with the same expected static FC: one switches, one does not."""
    rng = np.random.default_rng(seed)
    states, s = [], 0
    while len(states) < T:                 # epochs of 1-4 min, alternating
        states += [s] * int(rng.integers(30, 121))
        s = 1 - s
    states = np.array(states[:T])
    z = rng.standard_normal((N, T + 200))  # band-limited, unit-variance sources
    z = sosfiltfilt(sos, z, axis=1)[:, 100:-100]
    z /= z.std(axis=1, keepdims=True)
    L = [np.linalg.cholesky(C_A), np.linalg.cholesky(C_B)]
    x_switch = np.stack([L[states[t]] @ z[:, t] for t in range(T)], axis=1)
    C_mean = (1 - states.mean()) * C_A + states.mean() * C_B
    x_stationary = np.linalg.cholesky(C_mean) @ z
    return x_switch, x_stationary, states

def fc_stream(x, w, step=1):
    """Upper triangle of FC for each window, shape (M, N(N-1)/2)."""
    iu = np.triu_indices(x.shape[0], 1)
    starts = range(0, x.shape[1] - w + 1, step)
    return np.array([np.corrcoef(x[:, t:t + w])[iu] for t in starts])

def fcd(x, w, step=1):
    return np.corrcoef(fc_stream(x, w, step))

def fluidity(F, k):
    """Variance of FCD entries at least k windows off the diagonal."""
    return F[np.triu_indices_from(F, k=k)].var()

x_switch, x_stationary, states = toy_signals(seed=7)
F_switch, F_stationary = fcd(x_switch, w), fcd(x_stationary, w)

# Figure 1
import matplotlib.patheffects as pe

cmap = plt.get_cmap("viridis")
col_A, col_B = cmap(0.25), cmap(0.80)            # pattern A, pattern B
col_trace, col_window = cmap(0.05), cmap(0.55)   # traces, shaded windows
outlined = dict(mfc="none", mec="white", mew=1.8, ms=8, clip_on=False,
                path_effects=[pe.Stroke(linewidth=3.6, foreground="black"), pe.Normal()])
minutes = np.arange(T) * TR / 60
win_min = w * TR / 60

def first_window(state, after):
    """Start of the first window after `after` lying entirely in one state."""
    for t in range(after, T - w):
        if (states[t:t + w] == state).all():
            return t

starts = [first_window(0, 0)]
starts.append(first_window(1, starts[0] + w))
starts.append(first_window(0, starts[1] + w))
fc_shown = [np.corrcoef(x_switch[:, t:t + w]) for t in starts]

# Values span roughly -0.3 to 1, so use a sequential map over the observed range.
lowest = min(F_switch.min(), F_stationary.min(), *(fc.min() for fc in fc_shown))
vmin, vmax = np.floor(lowest * 10) / 10, 1.0

fig = plt.figure(figsize=(9, 9.5), layout="constrained")
top, middle, bottom = fig.subfigures(3, 1, height_ratios=[1.1, 1.0, 1.7])

ax = top.subplots()
shown = [0, 3, 5, 8]
for n, r in enumerate(shown):
    ax.plot(minutes, x_switch[r] - 3.5 * n, lw=0.8, color=col_trace)
ax.set_yticks([-3.5 * n for n in range(len(shown))],
              [f"region {r + 1}" for r in shown], fontsize=8)
bounds = np.r_[0, np.flatnonzero(np.diff(states)) + 1, T]
epochs = [(a, b, states[a]) for a, b in zip(bounds[:-1], bounds[1:])]
for a, b, s in epochs:
    ax.axvspan(minutes[a], minutes[b - 1] + TR / 60, ymin=0.95, ymax=1.0,
               color=[col_A, col_B][s], lw=0)
for n, t in enumerate(starts):
    ax.axvspan(minutes[t], minutes[t] + win_min, ymax=0.94, color=col_window, alpha=0.22, lw=0)
    ax.text(minutes[t] + win_min / 2, 0.925, f"$w_{n + 1}$", ha="center", va="top",
            fontsize=9, transform=ax.get_xaxis_transform())
label_A = [e for e in epochs if e[2] == 0][-2]
label_B = [e for e in epochs if e[2] == 1][-1]
for (a, b, s), name in [(label_A, "pattern A"), (label_B, "pattern B")]:
    ax.text((minutes[a] + minutes[b - 1]) / 2, 1.01, name, ha="center", va="bottom",
            fontsize=8, color="#333333", transform=ax.get_xaxis_transform())
ax.set_xlim(0, minutes[-1])
ax.set_ylim(-3.5 * (len(shown) - 1) - 2.8, 5.4)
ax.set_xlabel("time (min)")
ax.set_title("A   Regional signals, cut into overlapping windows", loc="left", fontsize=10)
for side in ["top", "right", "left"]:
    ax.spines[side].set_visible(False)

middle.suptitle("B   One FC matrix per window", x=0.02, ha="left", fontsize=10)
axes = middle.subplots(1, 3)
for n, (ax, t, fc) in enumerate(zip(axes, starts, fc_shown)):
    im = ax.imshow(fc, cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"FC($w_{n + 1}$): {minutes[t]:.1f}–{minutes[t] + win_min:.1f} min", fontsize=9)
middle.colorbar(im, ax=axes, shrink=0.85, label="correlation")

ax, ax_row = bottom.subplots(1, 2, width_ratios=[1.25, 1])
M = F_switch.shape[0]
half = TR / 60 / 2                 # pixel i is centred on the start of window i
extent = [-half, minutes[M - 1] + half, minutes[M - 1] + half, -half]
im = ax.imshow(F_switch, cmap=cmap, vmin=vmin, vmax=vmax, extent=extent)
for n, t in enumerate(starts):
    ax.plot(minutes[t], minutes[t], "o", **outlined)
    ax.annotate(f"$w_{n + 1}$", (minutes[t], minutes[t]), xytext=(8, -12),
                textcoords="offset points", fontsize=9, color="white",
                path_effects=[pe.withStroke(linewidth=2.5, foreground="black")])
ax.plot(minutes[starts[2]], minutes[starts[0]], "s", **outlined)
ax.annotate("FCD($w_1$, $w_3$)", (minutes[starts[2]], minutes[starts[0]]),
            xytext=(9, -15), textcoords="offset points", fontsize=8, color="white",
            path_effects=[pe.withStroke(linewidth=2.5, foreground="black")])
ax.set_xlabel("start of window $t_2$ (min)")
ax.set_ylabel("start of window $t_1$ (min)")
ax.set_title(r"C   FCD$(t_1, t_2)$ = corr[FC$(t_1)$, FC$(t_2)$]", loc="left", fontsize=10)
bottom.colorbar(im, ax=ax, shrink=0.85, location="left", pad=0.12,
                label="correlation between FC patterns")

row = F_switch[starts[0]]
for a, b, s in epochs:
    if a < M:
        ax_row.axvspan(minutes[a], minutes[min(b, M) - 1], ymin=0.96, ymax=1.0,
                       color=[col_A, col_B][s], lw=0)
ax_row.axvspan(0, win_min, color=col_window, alpha=0.22, lw=0)
ax_row.plot(minutes[:M], row, color=col_trace, lw=1.2)
ax_row.axhline(0, color="#9a9a9a", lw=0.8)
ax_row.plot(minutes[starts[2]], row[starts[2]], "s", **outlined)
ax_row.annotate("pattern A again", (minutes[starts[2]], row[starts[2]]), xytext=(9, -15),
                textcoords="offset points", fontsize=8)
ax_row.text(win_min + 0.2, -0.55, "overlap\nwith $w_1$", fontsize=8, color="#555555")
ax_row.set_xlim(0, minutes[M - 1])
ax_row.set_ylim(-0.7, 1.15)
ax_row.set_xlabel("start of window $t_2$ (min)")
ax_row.set_ylabel(r"FCD($w_1$, $t_2$)")
ax_row.set_title("D   One row of the FCD", loc="left", fontsize=10)
for side in ["top", "right"]:
    ax_row.spines[side].set_visible(False)
plt.show()
```

**Figure 1.** From time series to FCD, using synthetic signals. **A** Ten
band-limited signals (0.04–0.07 Hz, one sample every 2 s, 20 min; four are
shown) whose correlations follow one of two modular patterns, A or B, switching
every 1–4 min (coloured bar). Each 60 s window yields one FC matrix; three
windows are shaded. **B** The FC of $w_1$ and $w_3$, both in pattern A, look
alike; $w_2$, in pattern B, does not. **C** The FCD compares every window with
every other one (here, 571 windows with a step of one sample). The square
marks the entry for $w_1$ and $w_3$: high, because pattern A recurred.
**D** The row of the FCD that belongs to $w_1$, with the pattern at each
window's start shown above. It is high wherever pattern A returns and near
zero during pattern B. It drops slightly before each change in the bar,
because a window already reaches into the next epoch before it starts there.

The signals in Figure 1 are not a brain model. They are built so that the
truth is known: by construction the connectivity jumps between two fixed
patterns, and the two patterns are nearly uncorrelated with each other. Three
features of the FCD follow, and they are the features to look for in real
FCD matrices:

- **The band along the diagonal.** Windows that overlap share samples, so
  their FC are similar whatever the dynamics. For a step of one sample this
  band is about $w$ entries wide on each side of the diagonal. It reflects
  the analysis, not the brain.
- **Blocks on the diagonal.** A square of high values means that FC stayed in
  one configuration for as long as the square is wide. Hansen et al. called
  these epochs of stable FC [@hansen2015].
- **Off-diagonal blocks.** High values far from the diagonal mean that a
  configuration came back after the network had left it, as pattern A does in
  the figure. Low values pair configurations that have nothing in common.

In the toy data, entries between pattern A and pattern B windows sit near zero,
and some are negative. That is a property of the two patterns chosen here. In
the empirical data of Hansen et al., FCD entries were positive, which the
authors read as couplings changing in strength much more often than in sign
[@hansen2015].

## Fluidity

Fluidity is the variance of the FCD entries, taken over the upper triangle
with the overlap band left out:

$$
\text{fluidity} = \operatorname{Var}\bigl\{\mathrm{FCD}(t_1, t_2) :
t_2 - t_1 \ge k \bigr\},
$$

where $t_1$ and $t_2$ count windows and $k$ is the number of windows within
one window length, $k = \lceil w/s \rceil$. Lavanga et al. call it the
switching index or FCD variance and set the offset to the window length
[@lavanga2023]. VBI, the EBRAINS inference toolkit, uses the same offset by
default [@ziaeemehr2025]. The overlap band is removed because its values are
high for any signal: including it adds a contribution that depends on $w$ and
$s$, not on the dynamics.

The variance is informative because it separates cases that the mean of the
FCD does not:

- If FC never changes, every FCD entry is high and close to the same value.
  The variance is small.
- If FC fluctuates around one fixed pattern, as estimation noise alone makes
  it do, the entries cluster around one typical value, set by how strong that
  pattern is relative to the noise. The variance stays comparatively small.
- If FC moves among configurations that recur, the FCD contains both high
  entries (pairs in the same configuration) and low ones (pairs in different
  configurations). The distribution widens and the variance grows.

High fluidity therefore means switching *between recurring patterns*, which is
the structure Hansen et al. found in resting-state data. A related measure,
the dFC speed of Battaglia et al., is
$V(t) = 1 - \operatorname{corr}[\mathrm{FC}(t), \mathrm{FC}(t + \tau)]$ with
$\tau$ the window length [@battaglia2020]. It is one minus the FCD entries
that lie one window length away from the diagonal, so it describes how fast
FC changes from one moment to the next, but not whether earlier patterns come
back.

```{code-cell} ipython3
:tags: [hide-input]

iu = np.triu_indices(N, 1)
r_static = np.corrcoef(np.corrcoef(x_switch)[iu], np.corrcoef(x_stationary)[iu])[0, 1]
off_band = np.triu_indices_from(F_switch, k=k)

seeds = range(10)
flu = np.array([[fluidity(fcd(x, w), k) for x in toy_signals(seed)[:2]] for seed in seeds])

fig, axes = plt.subplots(1, 4, figsize=(11, 3.2), layout="constrained",
                         gridspec_kw={"width_ratios": [1, 1, 1.05, 0.75]})
col_stationary, col_switch = cmap(0.05), cmap(0.60)
for ax, F, name in [(axes[0], F_stationary, "stationary"), (axes[1], F_switch, "switching")]:
    im = ax.imshow(F, cmap=cmap, vmin=vmin, vmax=vmax, extent=extent)
    ax.set_title(f"FCD, {name}", fontsize=10)
    ax.set_xlabel("$t_2$ (min)")
axes[0].set_ylabel("$t_1$ (min)")
axes[1].set_yticklabels([])
fig.colorbar(im, ax=axes[:2], shrink=0.8, label="FCD")

bins = np.linspace(vmin, vmax, 29)
axes[2].hist(F_switch[off_band], bins=bins, color=col_switch, alpha=0.85,
             label=f"switching, var = {fluidity(F_switch, k):.3f}")
axes[2].hist(F_stationary[off_band], bins=bins, histtype="step", color=col_stationary, lw=1.5,
             label=f"stationary, var = {fluidity(F_stationary, k):.3f}")
axes[2].set_xlabel(r"FCD values, $t_2 - t_1 \geq k$")
axes[2].set_yticks([])
axes[2].legend(fontsize=8, frameon=False, loc="upper left")
axes[2].set_title("Distribution of FCD values", fontsize=10)

jitter = np.linspace(-0.12, 0.12, len(flu))
axes[3].plot(0 + jitter, flu[:, 1], "o", color=col_stationary, ms=6, mec="white", mew=0.8)
axes[3].plot(1 + jitter, flu[:, 0], "o", color=col_switch, ms=6, mec="white", mew=0.8)
axes[3].set_xticks([0, 1], ["stationary", "switching"], fontsize=9)
axes[3].set_xlim(-0.5, 1.5)
axes[3].set_ylim(0, None)
axes[3].set_ylabel("fluidity")
axes[3].set_title("10 noise realisations", fontsize=10)
for side in ["top", "right"]:
    axes[3].spines[side].set_visible(False)
fig.suptitle(f"Same static FC (correlation between the two static FC matrices: {r_static:.2f})",
             fontsize=10)
plt.show()
```

**Figure 2.** Fluidity tells apart two signals that static FC cannot. The
stationary signal is the switching signal of Figure 1 with the same sources
mixed by one fixed correlation matrix, the time-weighted average of patterns
A and B, so the two share the same expected static FC. Every window of the
stationary signal samples that same average pattern, so its FCD values
(window pairs at least $k$ apart) form one broad peak; its patches come from
sampling noise. The switching FCD splits into pairs from the same pattern
(high) and from different patterns (near zero), which widens the
distribution. The right panel repeats the comparison for ten noise
realisations.

Figure 2 also shows the main caveat. The stationary signal has no switching by
construction, yet its fluidity is well above zero, because a correlation
estimated from 60 s of a signal oscillating at about 0.05 Hz covers only about
three cycles and varies from window to window. Fluidity, then, is not an
absolute measure of non-stationarity. A value means something only next to a
reference: another group, another model parameter, or a surrogate computed from
the same data that keeps its static FC and removes any switching.
Phase-randomised surrogates do exactly this, and they are the null used by
Hindriks et al. and Battaglia et al. for windowed FC
[@hindriks2016; @battaglia2020]. The spread across realisations makes the same
point from another side: a single 20-minute fluidity value is a noisy estimate.

## Analysis choices that change the result

Every FCD and fluidity value depends on how it was computed. When comparing
model and data, or two groups, every choice below has to be the same on both
sides.

- **Window length.** Leonardi and Van De Ville showed that windows shorter
  than the longest period present in the signals create fluctuations in
  windowed FC even between signals whose relationship is fixed
  [@leonardi2015]. Windows should therefore be at least $1/f_{\min}$ long,
  the period of the lowest frequency the filter keeps: 25 s for the
  0.04–0.07 Hz band of Deco et al., who used 60 s windows [@deco2017].
  Windows that are too long average the switching away.
- **Step and offset.** The step sets how many windows there are and how wide
  the overlap band is. The offset $k$ must cover that band.
- **Session length and pooling.** Hindriks et al. found that in a typical
  10-minute resting-state session, changes in FC estimated with sliding
  windows could almost never be told apart from sampling fluctuations
  [@hindriks2016]. Detection became reliable only after averaging over
  sessions or subjects.
- **Preprocessing and parcellation.** Filtering, the number of regions (which
  sets the length of $\mathbf{v}(t)$), and for simulations the
  forward model that turns activity into a BOLD-like signal all change the
  numbers.

## Fitting models with FCD

A simulated FCD cannot be compared entry by entry with an empirical one. At
rest, nothing ties the switch at minute 6 of a scan to minute 6 of a simulation
driven by noise. Comparisons therefore use statistics of the FCD that do not
depend on timing:

- **The distribution of FCD values.** Deco et al. pooled the upper-triangle
  FCD entries over participants and measured the Kolmogorov–Smirnov distance
  between the simulated and empirical distributions, alongside the
  correlation between static FC matrices [@deco2017].
- **Fluidity and other summary statistics.** In simulation-based inference,
  fluidity and other summaries of the FCD (moments, quantiles, eigenvalues)
  are part of the data features from which parameters such as the global
  coupling are estimated [@hashemi2024; @ziaeemehr2025]. See the
  [inference overview](../inference.md).

These statistics constrain things that static FC does not. Hansen et al.
found that a mean-field model and a linear stochastic model at the coupling
that best fitted static FC produced FCD without long-lasting epochs of stable
FC, unlike the data [@hansen2015]. Switching appeared in a variant of the
mean-field model with stronger local nonlinearity, at global couplings inside
the range where the network has several stable states, and with enough noise.
It disappeared when noise was reduced or when the coupling approached either
end of that range. Lavanga et al. set the global coupling of their models at
the maximum of the FCD variance, and reported lower fluidity in older adults
[@lavanga2023].

Fluidity is not the same quantity as metastability, which is often reported
alongside it. Deco et al. define metastability as the standard deviation over
time of the Kuramoto order parameter, computed from the instantaneous phases
of all regions [@deco2017]. It measures how much global synchrony varies,
whereas fluidity measures how much the *pattern* of pairwise connectivity
varies.

## In TVB

The TVB web application includes an FCD analyzer (*FCD matrix*). It computes
the FCD of a region time series with a sliding window of 120 s and a step of
2 s by default, and stores the result as an
[`Fcd`](../../reference/api/tvb.datatypes.fcd.md) datatype. In scripts, the
FCD of a simulated BOLD signal takes a few lines of NumPy: the hidden cells
above contain a complete implementation. For inference workflows, VBI computes the
FCD and its summary statistics as part of its feature extraction
[@ziaeemehr2025].

## Where to go next

- [Simulate the Hopf whole-brain model](../../howtos/hopf-whole-brain-model.md):
  generate BOLD-like signals at a scanner sampling rate, to which this
  analysis applies directly.
- [Inference](../inference.md): how features such as fluidity are
  used to estimate model parameters.
