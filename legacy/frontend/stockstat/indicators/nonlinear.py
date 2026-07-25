from __future__ import annotations

import numpy as np
from scipy.signal import welch as _welch


def wavelet_decompose(
    signal,
    scales=None,
    wavelet: str = "morl",
):
    r"""Continuous Wavelet Transform (CWT).

    Decomposes *signal* into a time-scale representation using the
    specified mother wavelet (Eq. 4.1):

    .. math::
       W(s, \tau) = \frac{1}{\sqrt{s}} \int x(t)\,
                     \psi^*\!\Big(\frac{t-\tau}{s}\Big)\,dt

    Parameters
    ----------
    signal : array-like
        1-D input signal.
    scales : array-like, optional
        Wavelet scales.  Default ``np.arange(1, len(signal)//2 + 1)``.
    wavelet : str
        Mother wavelet name (default ``"morl"`` — Morlet).

    Returns
    -------
    coef : ndarray, shape (len(scales), len(signal))
        Complex wavelet coefficients.
    scales : ndarray
        The scales used.
    """
    x = np.asarray(signal, dtype=float)
    n = len(x)
    if n < 4:
        raise ValueError("signal must have at least 4 points")
    if scales is None:
        scales = np.arange(1, max(2, n // 2 + 1))
    scales = np.asarray(scales, dtype=float)

    try:
        import pywt
        coef, _ = pywt.cwt(x, scales, wavelet, sampling_period=1.0)
        return coef, scales
    except ImportError:
        pass

    # Fallback: Morlet CWT via FFT
    if wavelet != "morl":
        raise ValueError(
            "fallback CWT only supports 'morl'; install PyWavelets for others"
        )
    w0 = 6.0
    X = np.fft.fft(x - x.mean())
    omega = np.fft.fftfreq(n, d=1.0) * 2 * np.pi
    coef = np.zeros((len(scales), n), dtype=complex)
    for i, s in enumerate(scales):
        norm = np.sqrt(s / np.pi)
        daughter = norm * np.exp(-((s * omega - w0) ** 2) / 2) * (omega > 0)
        coef[i] = np.fft.ifft(X * daughter)
    return coef, scales


def spectral_entropy(signal, fs: float = 1.0, nperseg: int | None = None) -> float:
    r"""Spectral entropy of *signal* (Eq. 5.2).

    .. math::
       H_{\text{spec}} = -\sum_f p(f)\,\ln p(f)

    where :math:`p(f)` is the normalised power spectral density.

    Parameters
    ----------
    signal : array-like
        1-D input.
    fs : float
        Sampling frequency (default 1.0).
    nperseg : int, optional
        Welch segment length.  Default ``min(len, 256)``.

    Returns
    -------
    float
        Spectral entropy in nats.
    """
    x = np.asarray(signal, dtype=float)
    n = len(x)
    if n < 4:
        return 0.0
    if nperseg is None:
        nperseg = min(n, 256)
    nperseg = min(nperseg, n)
    _, psd = _welch(x, fs=fs, nperseg=nperseg)
    p = psd / (psd.sum() + 1e-30)
    p = p[p > 0]
    return float(-np.sum(p * np.log(p)))


def grey_relation(x0, xi, rho: float = 0.5) -> float:
    r"""Grey relational degree between two sequences (Eq. 6.1–6.2).

    Both sequences are initial-value normalised, then the grey
    relational coefficient is averaged:

    .. math::
       \xi_i(j) = \frac{\Delta_{\min}+\rho\,\Delta_{\max}}
                     {\Delta_i(j)+\rho\,\Delta_{\max}}, \qquad
       r_i = \frac{1}{n}\sum_j \xi_i(j)

    Returns
    -------
    float
        Grey relational degree in :math:`[0, 1]`.
    """
    a = np.asarray(x0, dtype=float)
    b = np.asarray(xi, dtype=float)
    if a.shape != b.shape:
        raise ValueError("x0 and xi must have the same shape")
    if len(a) == 0:
        return 0.0
    an = a / (a[0] + 1e-30)
    bn = b / (b[0] + 1e-30)
    delta = np.abs(an - bn)
    d_min = delta.min()
    d_max = delta.max()
    if d_max < 1e-15:
        return 1.0
    coef = (d_min + rho * d_max) / (delta + rho * d_max + 1e-30)
    return float(coef.mean())


def gm11_predict(sequence) -> float:
    r"""GM(1,1) one-step-ahead forecast (Eq. 6.4–6.5).

    Given an observed sequence :math:`X^{(0)}`, the accumulated
    generating operation (AGO) produces :math:`X^{(1)}`, whose
    whitening differential equation

    .. math::
       \frac{dX^{(1)}}{dt} + a\,X^{(1)} = b

    is solved by least squares to yield the prediction.

    Returns
    -------
    float
        Predicted next value of *sequence*.
    """
    x = np.asarray(sequence, dtype=float).ravel()
    n = len(x)
    if n < 4:
        return float(x[-1])
    x1 = np.cumsum(x)
    B = np.column_stack([-0.5 * (x1[1:] + x1[:-1]), np.ones(n - 1)])
    Y = x[1:].reshape(-1, 1)
    try:
        ab = np.linalg.lstsq(B, Y, rcond=None)[0].flatten()
        a, b = ab
    except np.linalg.LinAlgError:
        return float(x[-1])
    if abs(a) < 1e-12:
        return float(x[-1])
    x1_next = (x[0] - b / a) * np.exp(-a * n) + b / a
    x1_prev = (x[0] - b / a) * np.exp(-a * (n - 1)) + b / a
    return float(x1_next - x1_prev)


def transfer_entropy(x, y, k: int = 1, n_bins: int = 4) -> float:
    r"""Transfer entropy :math:`T_{x\to y}` (Eq. 7.2).

    .. math::
       T_{X\to Y} = \sum p(y_{t+1}, y_t^{(k)}, x_t^{(k)})\,
       \ln\frac{p(y_{t+1}\mid y_t^{(k)}, x_t^{(k)})}
              {p(y_{t+1}\mid y_t^{(k)})}

    Uses quantile binning for discretisation.

    Parameters
    ----------
    x, y : array-like
        Source and target 1-D sequences (equal length).
    k : int
        Embedding dimension (default 1).
    n_bins : int
        Number of quantile bins (default 4).

    Returns
    -------
    float
        Transfer entropy in bits (``>= 0``).
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(x)
    if len(y) != n or n <= k + 2:
        return 0.0

    y_fut = y[k + 1:]
    y_past = y[k:-1]
    x_past = x[k:-1]
    if len(y_fut) < 5:
        return 0.0

    def _qb(v):
        uniq = np.unique(v)
        if len(uniq) < n_bins:
            return np.zeros(len(v), dtype=int)
        edges = np.quantile(v, np.linspace(0, 1, n_bins + 1))
        edges[-1] += 1e-12
        return np.digitize(v, edges[1:-1])

    yf = _qb(y_fut)
    yp = _qb(y_past)
    xp = _qb(x_past)

    from collections import Counter, defaultdict

    def _H(labels):
        c = Counter(labels)
        tot = sum(c.values())
        return -sum(v / tot * np.log2(v / tot) for v in c.values())

    def _H_cond(a, b):
        groups = defaultdict(list)
        for ai, bi in zip(a, b):
            groups[bi].append(ai)
        tot = len(a)
        return sum(len(v) / tot * _H(v) for v in groups.values())

    combined = yp * (n_bins + 1) + xp
    te = _H_cond(yf, yp) - _H_cond(yf, combined)
    return float(max(0.0, te))


def hurst_dfa(signal) -> float:
    r"""Hurst exponent via Detrended Fluctuation Analysis (DFA).

    Returns a value in :math:`[0, 1]`:

    * ``≈ 0.5`` — random walk (no memory)
    * ``> 0.5`` — persistent (trending)
    * ``< 0.5`` — anti-persistent (mean-reverting)
    """
    x = np.asarray(signal, dtype=float)
    n = len(x)
    if n < 16:
        return 0.5
    y = np.cumsum(x - x.mean())
    ns = np.unique(
        np.logspace(np.log2(4), np.log2(n // 4), 20, base=2, dtype=int)
    )
    ns = ns[ns >= 4]
    if len(ns) < 4:
        return 0.5
    fluc = []
    for w in ns:
        nseg = len(y) // w
        if nseg < 1:
            continue
        f_vals = []
        for s in range(nseg):
            seg = y[s * w:(s + 1) * w]
            t = np.arange(w)
            p = np.polyfit(t, seg, 1)
            f_vals.append(np.sqrt(np.mean((seg - np.polyval(p, t)) ** 2)))
        fluc.append(np.mean(f_vals))
    fluc = np.array(fluc)
    if len(fluc) < 4 or np.any(fluc <= 0):
        return 0.5
    slope, _, _, _, _ = __import__("scipy.stats", fromlist=["linregress"]).linregress(
        np.log2(ns[:len(fluc)]), np.log2(fluc)
    )
    return float(slope)


def sample_entropy(signal, m: int = 2, r: float | None = None) -> float:
    r"""Sample entropy (Eq. 7.3).

    .. math::
       \mathrm{SampEn}(m, r, N) = -\ln\frac{A^m(r)}{B^m(r)}

    Returns ``0.0`` for constant or very short sequences.
    """
    x = np.asarray(signal, dtype=float)
    n = len(x)
    if r is None:
        r = 0.2 * np.std(x)
    if n < m + 2 or r == 0:
        return 0.0

    def _count(tl):
        tmpls = np.array([x[i:i + tl] for i in range(n - tl + 1)])
        c = 0
        for i in range(len(tmpls)):
            for j in range(i + 1, len(tmpls)):
                if np.max(np.abs(tmpls[i] - tmpls[j])) < r:
                    c += 1
        return c

    B = _count(m)
    A = _count(m + 1)
    if B == 0:
        return 0.0
    return float(-np.log(A / B))


def permutation_entropy(signal, m: int = 3, tau: int = 1) -> float:
    r"""Permutation entropy (Eq. 7.4).

    .. math::
       H_{\text{PE}} = -\sum_\pi p(\pi)\,\ln p(\pi)

    where :math:`\pi` ranges over all :math:`m!` ordinal patterns.
    """
    from itertools import permutations
    x = np.asarray(signal, dtype=float)
    n = len(x)
    if n < m * tau:
        return 0.0
    patterns = list(permutations(range(m)))
    counts = {p: 0 for p in patterns}
    for i in range(n - (m - 1) * tau):
        window = [x[i + j * tau] for j in range(m)]
        counts[tuple(np.argsort(window))] += 1
    total = sum(counts.values())
    if total == 0:
        return 0.0
    p = np.array([c / total for c in counts.values() if c > 0])
    return float(-np.sum(p * np.log2(p)))


# ═══════════════════════════════════════════════════════
# PlotSpec factory functions
# ═══════════════════════════════════════════════════════

def wavelet_scalogram_spec(coef, scales, title: str = "CWT Scalogram",
                           cmap: str = "jet"):
    r"""Build a PlotSpec for a CWT scalogram (time-frequency heatmap).

    Parameters
    ----------
    coef : ndarray, shape (len(scales), n)
        Complex wavelet coefficients from :func:`wavelet_decompose`.
    scales : array-like
        The scales used in the CWT.
    title : str
        Plot title.
    cmap : str
        Matplotlib colour map name.

    Returns
    -------
    PlotSpec
        A heatmap PlotSpec ready for ``renderer.render()``.
    """
    from ..plot.base import PlotSpec
    import pandas as pd
    power = np.abs(coef) ** 2
    df = pd.DataFrame(power, index=scales,
                      columns=range(coef.shape[1]))
    spec = PlotSpec(
        title=title,
        x_label="Time (samples)",
        y_label="Scale",
        figsize=(12, 6),
    )
    spec.add_series(name=title, data=df, kind="heatmap", cmap=cmap)
    return spec


def dfa_fit_spec(signal, title: str = "DFA — Hurst Exponent"):
    r"""Build a PlotSpec for a DFA log-log fit plot.

    Renders the fluctuation function :math:`F(n)` vs window size :math:`n`
    on a log-log scale, with the fitted slope (Hurst exponent) annotated.

    Parameters
    ----------
    signal : array-like
        The input signal (will be analysed internally).
    title : str
        Plot title.

    Returns
    -------
    PlotSpec
        A log-log scatter+line PlotSpec.
    """
    from ..plot.base import PlotSpec
    import pandas as pd
    from scipy import stats as sp_stats

    x = np.asarray(signal, dtype=float)
    n = len(x)
    if n < 16:
        h = 0.5
        ns = np.array([4, 8])
        fluc = np.array([0, 0])
    else:
        y = np.cumsum(x - x.mean())
        ns = np.unique(
            np.logspace(np.log2(4), np.log2(n // 4), 20, base=2, dtype=int)
        )
        ns = ns[ns >= 4]
        fluc = []
        for w in ns:
            nseg = len(y) // w
            if nseg < 1:
                continue
            f_vals = []
            for s in range(nseg):
                seg = y[s * w:(s + 1) * w]
                t = np.arange(w)
                p = np.polyfit(t, seg, 1)
                f_vals.append(np.sqrt(np.mean((seg - np.polyval(p, t)) ** 2)))
            fluc.append(np.mean(f_vals))
        fluc = np.array(fluc)
        ns = ns[:len(fluc)]

    slope, intercept, _, _, _ = sp_stats.linregress(np.log2(ns), np.log2(fluc))

    fit_x = np.log2(ns)
    fit_y = slope * fit_x + intercept

    df_data = pd.DataFrame({
        "fluctuation": np.log2(fluc),
        "fit": fit_y,
    }, index=pd.Series(ns, name="scale"))

    spec = PlotSpec(
        title=f"{title} (H = {slope:.4f})",
        x_label="Scale (log₂)",
        y_label="Fluctuation (log₂)",
        log_x=True,
        log_y=True,
        figsize=(10, 6),
    )
    spec.add_series(name="DFA", data=df_data["fluctuation"], kind="scatter",
                    color="steelblue")
    spec.add_series(name=f"fit (H={slope:.4f})", data=df_data["fit"], kind="line",
                    color="red", linewidth=2)
    return spec


def psd_spec(signal, fs: float = 1.0, nperseg: int | None = None,
             title: str = "Power Spectral Density"):
    r"""Build a PlotSpec for a Welch PSD plot (log-log).

    Parameters
    ----------
    signal : array-like
        Input signal.
    fs : float
        Sampling frequency.
    nperseg : int, optional
        Welch segment length.

    Returns
    -------
    PlotSpec
        A log-log line PlotSpec of the PSD.
    """
    from ..plot.base import PlotSpec
    import pandas as pd

    x = np.asarray(signal, dtype=float)
    n = len(x)
    if n < 4:
        return PlotSpec(title=title)
    if nperseg is None:
        nperseg = min(n, 256)
    nperseg = min(nperseg, n)
    freqs, psd = _welch(x, fs=fs, nperseg=nperseg)

    df = pd.DataFrame({"psd": psd}, index=pd.Series(freqs, name="freq"))
    spec = PlotSpec(
        title=title,
        x_label="Frequency (cycles/sample)",
        y_label="PSD",
        log_x=True,
        log_y=True,
        figsize=(10, 5),
    )
    spec.add_series(name="PSD", data=df["psd"], kind="line", color="darkgreen")
    return spec

