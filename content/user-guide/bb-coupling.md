---
title: Coupling
bibliography:
  - ../references.bib
---

# Coupling

Coupling functions are the modulators that change connectivity inputs.

The activity (state variables) that has been propagated over the long-range Connectivity passes through these functions before entering the equations (`Model.dfun()`) describing the local dynamics.

The state-variable vector for the $k$-th node or region in the network can be expressed as:

> Derivative = Noise + Local dynamics + Coupling(time delays)

More formally:

$$
\dot{\Psi}_k = -\Lambda(\Psi_k) + Z\left(\Xi_k + \sum_{j=1}^{l} u_{kj}\,\Gamma_{v=2}\left[\left(\Psi_k(t), \Psi_j(t-\tau_{kj})\right)\right]\right)
$$

Here we compute the term Coupling(time delays), or

$$
\sum_{j=1}^{l} u_{kj}\,\Gamma_{v=2}\left[\left(\Psi_k(t), \Psi_j(t-\tau_{kj})\right)\right],
$$

where $u_{kj}$ are the elements of the weights matrix from a Connectivity datatype.

This term is equivalent to the dot product between the weights matrix (on the left) and the delayed state vector.

$$
f_{post} \begin{pmatrix}
\sum
\begin{pmatrix}
u_{11} & u_{12} & \cdots & u_{1l} \\
u_{21} & u_{22} & \cdots & u_{2l} \\
\vdots & \vdots & \ddots & \vdots \\
u_{l1} & u_{l2} & \cdots & u_{ll}
\end{pmatrix}
\cdot
f_{pre} \begin{pmatrix}
\Psi_{1\_delayed} \\
\Psi_{2\_delayed} \\
\vdots \\
\Psi_{l\_delayed} \\
\end{pmatrix}
\end{pmatrix}
=
\begin{pmatrix}
\sum_{j=1}^{l} u_{1j}\,\Gamma_{v=2}[\cdot]   \\[2pt]
\sum_{j=1}^{l} u_{2j}\,\Gamma_{v=2}[\cdot] \\
\vdots \\
\sum_{j=1}^{l} u_{lj}\,\Gamma_{v=2}[\cdot]
\end{pmatrix}
$$


$$

\boxed{
f_{\mathrm{post}}\left(
\begin{pmatrix}
u_{11} & u_{12} & \cdots & u_{1l}\\
u_{21} & u_{22} & \cdots & u_{2l}\\
\vdots & \vdots & \ddots & \vdots\\
u_{k1} & u_{k2} & \cdots & u_{kl}
\end{pmatrix}
\begin{pmatrix}
f_{\mathrm{pre}}(\Psi_{1,\mathrm{delayed}})\\
f_{\mathrm{pre}}(\Psi_{2,\mathrm{delayed}})\\
\vdots\\
f_{\mathrm{pre}}(\Psi_{l,\mathrm{delayed}})
\end{pmatrix}
\right)
=
\begin{pmatrix}
\dot{\Psi}_1\\
\dot{\Psi}_2\\
\vdots\\
\dot{\Psi}_k
\end{pmatrix}
}

$$

This order is important in the case of an asymmetric connectivity matrix, where the convention to distinguish target ($k$) and source ($j$) nodes is the following:

- The row index is the **target** $k$.
- The column index is the **source** $j$.

So `weights[k, j]` is the strength of the projection from region $j$ onto region $k$, and the $k$-th row of the matrix gives the total input received by node $k$.

:::{warning}
This is the **inverse** of the convention used by the Brain Connectivity Toolbox and most graph-theory code. A matrix transposed on import couples the network backwards: it runs, produces plausible spectra, and is wrong. See [weights](weights-section).
:::

An asymmetric matrix therefore cannot be replaced by its transpose without changing the dynamics of the model.

