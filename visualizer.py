import io
import re
import base64
import warnings
from typing import Optional

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import pandas as pd
import numpy as np

DARK_BG      = "#0f172a"
DARK_PANEL   = "#1e293b"
DARK_BORDER  = "#334155"
TEXT_PRIMARY = "#e2e8f0"
TEXT_MUTED   = "#94a3b8"
GRID_COLOR   = "#334155"

PALETTE = [
    "#6090f8",  # brand blue
    "#34d399",  # emerald
    "#f59e0b",  # amber
    "#f87171",  # red
    "#a78bfa",  # violet
    "#38bdf8",  # sky
    "#fb923c",  # orange
    "#4ade80",  # green
    "#e879f9",  # fuchsia
    "#facc15",  # yellow
]

def _apply_dark_theme():
    """Set matplotlib rcParams ke dark theme."""
    plt.rcParams.update({
        "figure.facecolor":     DARK_BG,
        "axes.facecolor":       DARK_PANEL,
        "axes.edgecolor":       DARK_BORDER,
        "axes.labelcolor":      TEXT_MUTED,
        "axes.titlecolor":      TEXT_PRIMARY,
        "text.color":           TEXT_PRIMARY,
        "xtick.color":          TEXT_MUTED,
        "ytick.color":          TEXT_MUTED,
        "grid.color":           GRID_COLOR,
        "grid.alpha":           0.4,
        "grid.linestyle":       "--",
        "font.family":          "DejaVu Sans",
        "font.size":            10,
        "axes.spines.top":      False,
        "axes.spines.right":    False,
        "legend.facecolor":     DARK_PANEL,
        "legend.edgecolor":     DARK_BORDER,
        "legend.labelcolor":    TEXT_PRIMARY,
    })


VIZ_KEYWORDS = [
    "grafik", "chart", "plot", "diagram", "visualisasi", "visualize",
    "tren", "trend", "sebaran", "distribusi", "distribution",
    "perbandingan", "bandingkan", "compare",
    "histogram", "pie", "batang", "garis", "scatter",
    "gambarkan", "tampilkan grafik", "buat grafik",
]


def detect_viz_intent(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in VIZ_KEYWORDS)


def get_chart_title(question: str, columns: list[str]) -> str:
    q = question.strip().rstrip("?").strip()
    if q:
        return q[0].upper() + q[1:] if len(q) > 1 else q.upper()
    return " vs ".join(columns[:2])


def _classify_columns(columns: list[str], rows: list) -> tuple[list[int], list[int]]:
    if not rows:
        return [], list(range(len(columns)))

    numeric_idx = []
    cat_idx     = []

    for i in range(len(columns)):
        try:
            val = rows[0][i]
            if val is None:
                cat_idx.append(i)
            else:
                float(val)
                numeric_idx.append(i)
        except (ValueError, TypeError, IndexError):
            cat_idx.append(i)

    return numeric_idx, cat_idx


def suggest_chart_type(columns: list[str], rows: list, question: str = "") -> dict:
    """
    Return dict:
    {
        type:      str  — "barh" | "bar" | "pie" | "line" | "scatter" |
                          "bar_multi" | "heatmap" | "histogram"
        num_idx:   list — indeks kolom numerik
        cat_idx:   list — indeks kolom kategorik
        x_col:     int  — indeks kolom X
        y_cols:    list — indeks kolom Y (bisa lebih dari 1)
        reason:    str  — penjelasan mengapa tipe ini dipilih
    }
    """
    n_cols = len(columns)
    n_rows = len(rows)
    q      = question.lower()

    if n_rows == 0 or n_cols < 1:
        return {"type": None, "reason": "Data kosong"}

    num_idx, cat_idx = _classify_columns(columns, rows)

    if any(w in q for w in ["pie", "distribusi", "sebaran", "proporsi"]):
        force_pie = True
    else:
        force_pie = False

    if any(w in q for w in ["tren", "trend", "waktu", "bulan", "tahun", "semester"]):
        force_line = True
    else:
        force_line = False

    if any(w in q for w in ["scatter", "korelasi"]):
        force_scatter = True
    else:
        force_scatter = False

    if any(w in q for w in ["histogram", "frekuensi"]):
        force_hist = True
    else:
        force_hist = False

    if n_cols == 1 and num_idx:
        return {"type": "histogram", "num_idx": num_idx, "cat_idx": cat_idx,
                "x_col": num_idx[0], "y_cols": [], "reason": "1 kolom numerik → histogram"}

    if n_cols == 2 and len(cat_idx) == 1 and len(num_idx) == 1:
        use_pie = (
            force_pie
            or n_rows <= 4
            or any(w in q for w in ["distribusi", "sebaran", "proporsi", "persentase", "komposisi"])
        )
        if use_pie:
            return {"type": "pie", "num_idx": num_idx, "cat_idx": cat_idx,
                    "x_col": cat_idx[0], "y_cols": num_idx,
                    "reason": f"{n_rows} kategori → pie chart"}
        else:
            return {"type": "barh", "num_idx": num_idx, "cat_idx": cat_idx,
                    "x_col": cat_idx[0], "y_cols": num_idx,
                    "reason": f"{n_rows} baris → horizontal bar"}

    if n_cols == 2 and len(num_idx) == 2:
        if force_line:
            return {"type": "line", "num_idx": num_idx, "cat_idx": cat_idx,
                    "x_col": 0, "y_cols": [1], "reason": "2 numerik + tren → line"}
        if force_scatter:
            return {"type": "scatter", "num_idx": num_idx, "cat_idx": cat_idx,
                    "x_col": 0, "y_cols": [1], "reason": "2 numerik → scatter"}
        return {"type": "bar", "num_idx": num_idx, "cat_idx": cat_idx,
                "x_col": 0, "y_cols": [1], "reason": "2 numerik → bar"}

    if n_cols == 3 and len(cat_idx) == 2 and len(num_idx) == 1:
        return {"type": "bar_grouped", "num_idx": num_idx, "cat_idx": cat_idx,
                "x_col": cat_idx[0], "y_cols": num_idx, "group_col": cat_idx[1],
                "reason": "2 kategori + 1 nilai → grouped bar"}

    if n_cols == 3 and len(cat_idx) == 1 and len(num_idx) == 2:
        return {"type": "bar_multi", "num_idx": num_idx, "cat_idx": cat_idx,
                "x_col": cat_idx[0], "y_cols": num_idx,
                "reason": "1 kategori + 2 nilai → multi bar"}

    if len(cat_idx) == 1 and len(num_idx) >= 2:
        return {"type": "bar_multi", "num_idx": num_idx[:5], "cat_idx": cat_idx,
                "x_col": cat_idx[0], "y_cols": num_idx[:5],
                "reason": f"1 kategori + {len(num_idx)} nilai → multi bar"}

    if len(num_idx) >= 3 and not cat_idx:
        return {"type": "line", "num_idx": num_idx, "cat_idx": [],
                "x_col": 0, "y_cols": num_idx[1:],
                "reason": "Banyak numerik → line chart"}

    if cat_idx and num_idx:
        chart = "bar" if n_rows <= 10 else "barh"
        return {"type": chart, "num_idx": num_idx, "cat_idx": cat_idx,
                "x_col": cat_idx[0], "y_cols": [num_idx[0]],
                "reason": f"Default → {chart}"}

    return {"type": "bar", "num_idx": num_idx, "cat_idx": cat_idx,
            "x_col": 0, "y_cols": [1] if n_cols > 1 else [],
            "reason": "Fallback bar chart"}


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _truncate_label(label: str, max_len: int = 18) -> str:
    s = str(label)
    return s[:max_len] + "…" if len(s) > max_len else s


def _bar_value_labels(ax, bars, fmt=".1f", offset_pct=0.01, horizontal=False):
    max_val = max((b.get_width() if horizontal else b.get_height()) for b in bars)
    offset  = max_val * offset_pct

    for bar in bars:
        if horizontal:
            val = bar.get_width()
            ax.text(val + offset, bar.get_y() + bar.get_height() / 2,
                    f"{val:{fmt}}", va="center", ha="left",
                    color=TEXT_PRIMARY, fontsize=8.5, fontweight="medium")
        else:
            val = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, val + offset,
                    f"{val:{fmt}}", ha="center", va="bottom",
                    color=TEXT_PRIMARY, fontsize=8.5, fontweight="medium")


def _build_df(columns: list[str], rows: list) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns)


# ── Bar Horizontal ────────────────────────────────────────────
def _chart_barh(df: pd.DataFrame, x_col: str, y_col: str, title: str):
    _apply_dark_theme()
    n = len(df)
    h = max(3.5, n * 0.52)
    fig, ax = plt.subplots(figsize=(8, h))
    fig.patch.set_facecolor(DARK_BG)

    colors = [PALETTE[i % len(PALETTE)] for i in range(n)]
    bars   = ax.barh(df[x_col].astype(str).apply(lambda s: _truncate_label(s, 20)),
                     pd.to_numeric(df[y_col], errors="coerce"),
                     color=colors, alpha=0.88, edgecolor="none", height=0.6)

    _bar_value_labels(ax, bars, horizontal=True)
    ax.set_xlabel(y_col.replace("_", " ").title(), color=TEXT_MUTED)
    ax.set_title(title, color=TEXT_PRIMARY, fontsize=12, pad=14, fontweight="semibold")
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.3)
    ax.set_axisbelow(True)
    plt.tight_layout(pad=1.5)
    return _fig_to_b64(fig)


# ── Bar Vertikal ─────────────────────────────────────────────
def _chart_bar(df: pd.DataFrame, x_col: str, y_col: str, title: str):
    _apply_dark_theme()
    n = len(df)
    w = max(6, n * 0.9)
    fig, ax = plt.subplots(figsize=(min(w, 12), 5))
    fig.patch.set_facecolor(DARK_BG)

    x_labels = df[x_col].astype(str).apply(lambda s: _truncate_label(s, 12))
    colors   = [PALETTE[i % len(PALETTE)] for i in range(n)]
    bars     = ax.bar(x_labels, pd.to_numeric(df[y_col], errors="coerce"),
                      color=colors, alpha=0.88, edgecolor="none", width=0.65)

    _bar_value_labels(ax, bars)
    ax.set_xlabel(x_col.replace("_", " ").title(), color=TEXT_MUTED)
    ax.set_ylabel(y_col.replace("_", " ").title(), color=TEXT_MUTED)
    ax.set_title(title, color=TEXT_PRIMARY, fontsize=12, pad=14, fontweight="semibold")
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    if n > 5:
        plt.xticks(rotation=30, ha="right")
    plt.tight_layout(pad=1.5)
    return _fig_to_b64(fig)


# ── Pie Chart ─────────────────────────────────────────────────
def _chart_pie(df: pd.DataFrame, label_col: str, value_col: str, title: str):
    _apply_dark_theme()
    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor(DARK_BG)

    labels = df[label_col].astype(str).apply(lambda s: _truncate_label(s, 16))
    values = pd.to_numeric(df[value_col], errors="coerce").fillna(0)
    n      = len(df)
    colors = [PALETTE[i % len(PALETTE)] for i in range(n)]

    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct="%1.1f%%",
        startangle=90,
        wedgeprops={"edgecolor": DARK_BG, "linewidth": 2},
        textprops={"color": TEXT_PRIMARY, "fontsize": 9},
        pctdistance=0.82,
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_fontweight("bold")
        at.set_color(DARK_BG)

    ax.set_title(title, color=TEXT_PRIMARY, fontsize=12, pad=18, fontweight="semibold")
    plt.tight_layout(pad=1.5)
    return _fig_to_b64(fig)


# ── Line Chart ───────────────────────────────────────────────
def _chart_line(df: pd.DataFrame, x_col: str, y_cols: list[str], title: str):
    _apply_dark_theme()
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor(DARK_BG)

    x_vals = range(len(df))
    for i, y_col in enumerate(y_cols):
        y = pd.to_numeric(df[y_col], errors="coerce")
        color = PALETTE[i % len(PALETTE)]
        ax.plot(list(x_vals), y, marker="o", linewidth=2.2, markersize=7,
                color=color, label=y_col.replace("_", " ").title(), alpha=0.9)
        ax.fill_between(list(x_vals), y, alpha=0.08, color=color)

    ax.set_xticks(list(x_vals))
    ax.set_xticklabels(
        [_truncate_label(str(df[x_col].iloc[i]), 12) for i in x_vals],
        rotation=20 if len(df) > 5 else 0, ha="right"
    )
    ax.set_title(title, color=TEXT_PRIMARY, fontsize=12, pad=14, fontweight="semibold")
    ax.grid(alpha=0.3)
    if len(y_cols) > 1:
        ax.legend(loc="upper right")
    plt.tight_layout(pad=1.5)
    return _fig_to_b64(fig)


# ── Scatter Chart ─────────────────────────────────────────────
def _chart_scatter(df: pd.DataFrame, x_col: str, y_col: str, title: str,
                   label_col: Optional[str] = None):
    _apply_dark_theme()
    fig, ax = plt.subplots(figsize=(7, 5))
    fig.patch.set_facecolor(DARK_BG)

    x = pd.to_numeric(df[x_col], errors="coerce")
    y = pd.to_numeric(df[y_col], errors="coerce")

    scatter = ax.scatter(x, y, c=PALETTE[0], s=80, alpha=0.8, edgecolors=DARK_BG, linewidth=0.8)

    if label_col and label_col in df.columns:
        for _, row in df.iterrows():
            ax.annotate(_truncate_label(str(row[label_col]), 12),
                        (float(row[x_col]), float(row[y_col])),
                        textcoords="offset points", xytext=(5, 5),
                        fontsize=7, color=TEXT_MUTED, alpha=0.8)

    # Trendline
    try:
        z = np.polyfit(x.dropna(), y.dropna(), 1)
        p = np.poly1d(z)
        x_line = np.linspace(x.min(), x.max(), 50)
        ax.plot(x_line, p(x_line), "--", color=PALETTE[1], alpha=0.6, linewidth=1.5,
                label="Trendline")
        ax.legend()
    except Exception:
        pass

    ax.set_xlabel(x_col.replace("_", " ").title(), color=TEXT_MUTED)
    ax.set_ylabel(y_col.replace("_", " ").title(), color=TEXT_MUTED)
    ax.set_title(title, color=TEXT_PRIMARY, fontsize=12, pad=14, fontweight="semibold")
    ax.grid(alpha=0.3)
    plt.tight_layout(pad=1.5)
    return _fig_to_b64(fig)


# ── Multi Bar ─────────────────────────────────────────────────
def _chart_bar_multi(df: pd.DataFrame, x_col: str, y_cols: list[str], title: str):
    _apply_dark_theme()
    n    = len(df)
    n_y  = len(y_cols)
    w    = max(7, n * 0.8 + 1)
    fig, ax = plt.subplots(figsize=(min(w, 13), 5))
    fig.patch.set_facecolor(DARK_BG)

    bar_w  = 0.75 / n_y
    x_base = np.arange(n)

    for i, y_col in enumerate(y_cols):
        offset = (i - n_y / 2 + 0.5) * bar_w
        y      = pd.to_numeric(df[y_col], errors="coerce")
        bars   = ax.bar(x_base + offset, y, width=bar_w * 0.92,
                        color=PALETTE[i % len(PALETTE)], alpha=0.88, edgecolor="none",
                        label=y_col.replace("_", " ").title())

    ax.set_xticks(list(x_base))
    ax.set_xticklabels(
        df[x_col].astype(str).apply(lambda s: _truncate_label(s, 12)),
        rotation=20 if n > 5 else 0, ha="right"
    )
    ax.set_title(title, color=TEXT_PRIMARY, fontsize=12, pad=14, fontweight="semibold")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    plt.tight_layout(pad=1.5)
    return _fig_to_b64(fig)


# ── Grouped Bar ───────────────────────────────────────────────
def _chart_bar_grouped(df: pd.DataFrame, x_col: str, group_col: str,
                       y_col: str, title: str):
    """Bar chart dikelompokkan berdasarkan kolom group."""
    _apply_dark_theme()

    groups  = df[group_col].unique()
    x_cats  = df[x_col].unique()
    n_cats  = len(x_cats)
    n_groups = len(groups)
    bar_w   = 0.75 / n_groups

    fig, ax = plt.subplots(figsize=(max(7, n_cats * 1.2), 5))
    fig.patch.set_facecolor(DARK_BG)

    x_base = np.arange(n_cats)

    for i, grp in enumerate(groups):
        sub    = df[df[group_col] == grp].set_index(x_col)
        vals   = [float(sub.loc[cat, y_col]) if cat in sub.index else 0 for cat in x_cats]
        offset = (i - n_groups / 2 + 0.5) * bar_w
        bars   = ax.bar(x_base + offset, vals, width=bar_w * 0.92,
                        color=PALETTE[i % len(PALETTE)], alpha=0.88, edgecolor="none",
                        label=_truncate_label(str(grp), 16))

    ax.set_xticks(list(x_base))
    ax.set_xticklabels(
        [_truncate_label(str(c), 14) for c in x_cats],
        rotation=20 if n_cats > 4 else 0, ha="right"
    )
    ax.set_title(title, color=TEXT_PRIMARY, fontsize=12, pad=14, fontweight="semibold")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    plt.tight_layout(pad=1.5)
    return _fig_to_b64(fig)


# ── Histogram ─────────────────────────────────────────────────
def _chart_histogram(df: pd.DataFrame, col: str, title: str):
    _apply_dark_theme()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    fig.patch.set_facecolor(DARK_BG)

    vals = pd.to_numeric(df[col], errors="coerce").dropna()
    n_bins = min(max(5, len(vals) // 3), 20)

    ax.hist(vals, bins=n_bins, color=PALETTE[0], alpha=0.85, edgecolor=DARK_BG, linewidth=0.8)
    ax.axvline(vals.mean(), color=PALETTE[1], linestyle="--", linewidth=1.8,
               label=f"Mean: {vals.mean():.1f}", alpha=0.9)
    ax.axvline(vals.median(), color=PALETTE[2], linestyle=":", linewidth=1.8,
               label=f"Median: {vals.median():.1f}", alpha=0.9)

    ax.set_xlabel(col.replace("_", " ").title(), color=TEXT_MUTED)
    ax.set_ylabel("Frekuensi", color=TEXT_MUTED)
    ax.set_title(title, color=TEXT_PRIMARY, fontsize=12, pad=14, fontweight="semibold")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout(pad=1.5)
    return _fig_to_b64(fig)


# ── Box Plot (untuk distribusi nilai) ────────────────────────
def _chart_box(df: pd.DataFrame, x_col: Optional[str], y_col: str, title: str):
    _apply_dark_theme()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    fig.patch.set_facecolor(DARK_BG)

    if x_col and x_col in df.columns:
        groups = df[x_col].unique()
        data   = [pd.to_numeric(df[df[x_col] == g][y_col], errors="coerce").dropna().tolist()
                  for g in groups]
        bp = ax.boxplot(data, labels=[_truncate_label(str(g), 12) for g in groups],
                        patch_artist=True, medianprops={"color": PALETTE[1], "linewidth": 2})
        for i, patch in enumerate(bp["boxes"]):
            patch.set_facecolor(PALETTE[i % len(PALETTE)])
            patch.set_alpha(0.7)
    else:
        vals = pd.to_numeric(df[y_col], errors="coerce").dropna()
        bp   = ax.boxplot(vals, patch_artist=True,
                          medianprops={"color": PALETTE[1], "linewidth": 2})
        bp["boxes"][0].set_facecolor(PALETTE[0])
        bp["boxes"][0].set_alpha(0.7)

    ax.set_title(title, color=TEXT_PRIMARY, fontsize=12, pad=14, fontweight="semibold")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout(pad=1.5)
    return _fig_to_b64(fig)


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def generate_chart(
    columns: list[str],
    rows:    list,
    question: str = "",
    title:    str = "",
) -> dict:
    """
    Generate chart otomatis dari hasil SQL query.

    Args:
        columns:  Nama kolom dari hasil query
        rows:     List of rows dari hasil query
        question: Pertanyaan asli user (untuk konteks chart type)
        title:    Judul chart (default: dari question)

    Returns:
        {
            success:     bool,
            chart_type:  str,
            chart_b64:   str,   # PNG base64 untuk <img src="data:...">
            reason:      str,   # Mengapa tipe chart ini dipilih
            error:       str,   # Jika gagal
        }
    """
    try:
        if not rows or not columns:
            return {"success": False, "error": "Data kosong untuk divisualisasikan."}

        if len(rows) < 2 and len(columns) < 2:
            return {"success": False, "error": "Data terlalu sedikit untuk grafik."}

        # Buat title
        if not title:
            title = get_chart_title(question, columns)

        # Bangun DataFrame
        df      = _build_df(columns, rows)
        n_rows  = len(df)

        # Deteksi chart type
        chart_info = suggest_chart_type(columns, rows, question)
        chart_type = chart_info.get("type")
        num_idx    = chart_info.get("num_idx", [])
        cat_idx    = chart_info.get("cat_idx", [])
        x_col_i    = chart_info.get("x_col", 0)
        y_col_is   = chart_info.get("y_cols", [])

        if chart_type is None:
            return {"success": False, "error": "Tidak dapat menentukan tipe grafik yang cocok."}

        # Ambil nama kolom
        x_col  = columns[x_col_i] if x_col_i < len(columns) else columns[0]
        y_cols = [columns[i] for i in y_col_is if i < len(columns)]
        y_col  = y_cols[0] if y_cols else (columns[num_idx[0]] if num_idx else columns[-1])

        # ── Dispatch ke generator yang tepat ─────────────────
        b64 = None

        if chart_type == "pie":
            b64 = _chart_pie(df, x_col, y_col, title)

        elif chart_type == "barh":
            b64 = _chart_barh(df, x_col, y_col, title)

        elif chart_type == "bar":
            b64 = _chart_bar(df, x_col, y_col, title)

        elif chart_type == "line":
            b64 = _chart_line(df, x_col, y_cols if y_cols else [y_col], title)

        elif chart_type == "scatter":
            label_col = columns[cat_idx[0]] if cat_idx else None
            x2 = columns[num_idx[0]] if num_idx else x_col
            y2 = columns[num_idx[1]] if len(num_idx) > 1 else y_col
            b64 = _chart_scatter(df, x2, y2, title, label_col=label_col)

        elif chart_type == "bar_multi":
            b64 = _chart_bar_multi(df, x_col, y_cols if len(y_cols) > 1 else [y_col], title)

        elif chart_type == "bar_grouped":
            group_col_i = chart_info.get("group_col", cat_idx[1] if len(cat_idx) > 1 else cat_idx[0])
            group_col   = columns[group_col_i] if group_col_i < len(columns) else columns[1]
            b64 = _chart_bar_grouped(df, x_col, group_col, y_col, title)

        elif chart_type == "histogram":
            b64 = _chart_histogram(df, y_col if y_col else columns[0], title)

        else:
            b64 = _chart_barh(df, x_col, y_col, title)

        if b64:
            return {
                "success":    True,
                "chart_type": chart_type,
                "chart_b64":  b64,
                "reason":     chart_info.get("reason", ""),
                "error":      None,
            }
        else:
            return {"success": False, "error": "Gagal menghasilkan grafik."}

    except Exception as e:
        import traceback
        return {
            "success":    False,
            "chart_type": "unknown",
            "chart_b64":  None,
            "reason":     "",
            "error":      f"Error visualisasi: {str(e)}",
        }
