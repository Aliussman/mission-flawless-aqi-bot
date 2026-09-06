import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

METHODS = ["us_aqi", "india_aqi", "aqi_rho"]
METHOD_LABELS = {
    "us_aqi": "US EPA",
    "india_aqi": "India CPCB",
    "aqi_rho": "AQI \u03c1 (paper)",
}


def load(comparison_csv, hourly_csv):
    cmp = pd.read_csv(comparison_csv)
    cmp["timestamp"] = pd.to_datetime(cmp["timestamp"], errors="coerce")

    dev = pd.read_csv(hourly_csv)
    dev["timestamp"] = pd.to_datetime(dev["timestamp"], errors="coerce")
    device_cols = [c for c in dev.columns if c.startswith("device_aqi_")]

    merged = pd.merge(cmp, dev[["timestamp"] + device_cols], on="timestamp", how="outer")
    return merged, device_cols


def _stats(a, b):
    """Bias (a-b mean), RMSE, Pearson r between two numeric series."""
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    mask = a.notna() & b.notna()
    a, b = a[mask], b[mask]
    if len(a) == 0:
        return None, None, None
    bias = float((a - b).mean())
    rmse = float(((a - b) ** 2).mean() ** 0.5)
    r = float(a.corr(b))
    return bias, rmse, r


def build_summary(merged, device_cols, out_path):
    """Aggregate stats table: for each method pair and each device-vs-method."""
    rows = []

    # computed-method means
    method_means = {m: float(merged[m].mean()) for m in METHODS}

    # method vs method
    for i, a in enumerate(METHODS):
        for b in METHODS[i + 1:]:
            bias, rmse, r = _stats(merged[a], merged[b])
            rows.append({
                "x": a, "y": b, "kind": "method_vs_method",
                "n": int(merged[a].notna().sum()),
                "mean_x": method_means[a], "mean_y": method_means[b],
                "bias": bias, "rmse": rmse, "corr": r,
            })

    # device vs each computed method
    for d in device_cols:
        dmean = float(merged[d].mean())
        for m in METHODS:
            bias, rmse, r = _stats(merged[d], merged[m])
            rows.append({
                "x": d, "y": m, "kind": "device_vs_method",
                "n": int(merged[m].notna().sum()),
                "mean_x": dmean, "mean_y": method_means[m],
                "bias": bias, "rmse": rmse, "corr": r,
            })

    summary = pd.DataFrame(rows)
    summary.to_csv(out_path, index=False)
    return summary


def plot_timeseries(merged, out_path):
    fig, ax = plt.subplots(figsize=(12, 6))
    for m in METHODS:
        ax.plot(merged["timestamp"], merged[m], label=METHOD_LABELS[m], lw=1.6)
    colors = ["#d62728", "#7f7f7f"]
    for i, d in enumerate([c for c in merged.columns if c.startswith("device_aqi_")]):
        ax.plot(merged["timestamp"], merged[d], "--", label=d.replace("device_aqi_", "device: "),
                lw=1.2, color=colors[i % len(colors)], alpha=0.8)
    ax.set_xlabel("Time"); ax.set_ylabel("AQI")
    ax.set_title("Hourly AQI by method and device")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out_path, dpi=120); plt.close(fig)


def plot_method_pairs(merged, out_dir):
    combos = [
        ("us_aqi", "india_aqi", "US EPA vs India CPCB"),
        ("us_aqi", "aqi_rho", "US EPA vs AQI \u03c1"),
        ("india_aqi", "aqi_rho", "India CPCB vs AQI \u03c1"),
    ]
    for a, b, title in combos:
        fig, ax = plt.subplots(figsize=(5.5, 5.5))
        x = pd.to_numeric(merged[a], errors="coerce")
        y = pd.to_numeric(merged[b], errors="coerce")
        mask = x.notna() & y.notna()
        ax.scatter(x[mask], y[mask], s=18, alpha=0.6)
        vmax = max(x[mask].max(), y[mask].max())
        ax.plot([0, vmax], [0, vmax], "k--", lw=1, label="y = x")
        bias, rmse, r = _stats(x, y)
        ax.set_xlabel(METHOD_LABELS[a]); ax.set_ylabel(METHOD_LABELS[b])
        ax.set_title(f"{title}\n(r={r:.2f}, bias={bias:+.1f}, RMSE={rmse:.1f})")
        ax.legend(); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(out_dir / f"{a}__{b}.png", dpi=110); plt.close(fig)


def plot_device_vs_method(merged, device_cols, out_dir):
    for d in device_cols:
        label = d.replace("device_aqi_", "device: ")
        fig, ax = plt.subplots(figsize=(12, 4.5))
        dval = pd.to_numeric(merged[d], errors="coerce")
        x = merged["timestamp"]
        ax.plot(x, dval, "-o", ms=3, label=label, lw=1.4, color="black")
        for m in METHODS:
            ax.plot(x, merged[m], lw=1.2, label=METHOD_LABELS[m])
        ax.set_xlabel("Time"); ax.set_ylabel("AQI")
        ax.set_title(f"{label} reported AQI vs computed methods")
        ax.legend(); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(out_dir / f"{d}__methods.png", dpi=110); plt.close(fig)


def build_report(comparison_csv, hourly_csv, out_dir):
    out_dir = pd.io.common._expand_user(out_dir)
    from pathlib import Path
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    merged, device_cols = load(comparison_csv, hourly_csv)

    summary = build_summary(merged, device_cols, out_dir / "comparison_summary.csv")
    plot_timeseries(merged, out_dir / "timeseries.png")
    plot_method_pairs(merged, out_dir)
    plot_device_vs_method(merged, device_cols, out_dir)

    print(f"Report written to {out_dir}")
    print("\nMethod-vs-method & device-vs-method summary:")
    print(summary.to_string(index=False))
    return merged, summary