"""Explainability for detector flags (spec section 16).

For any observation the Isolation Forest scores, this attributes the score to the
underlying evidence features so an operator can see *why* a point looks anomalous
— never an opaque number. When the optional ``shap`` library is installed a
TreeExplainer computes exact per-feature contributions on the trained forest;
otherwise a transparent standardized-magnitude fallback is used and is LABELLED
as such.

Per spec section 35 we never fabricate SHAP values: if SHAP cannot run, the
output records ``method='standardized_magnitude_fallback'`` rather than inventing
attributions. Wording is deliberately hedged ("probable anomaly", "leading
evidence") — the explainer describes evidence, it does not pronounce a verdict.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .config import DEFAULT_CONFIG
from .features import to_model_matrix

try:  # shap is optional; its absence must degrade gracefully, never crash
    import shap
    _HAVE_SHAP = True
except Exception:  # pragma: no cover - environment dependent
    shap = None
    _HAVE_SHAP = False


def shap_available() -> bool:
    return _HAVE_SHAP


# human phrasing per model feature: (noun phrase, unit, kind). Units are ASCII so
# summaries print safely on any console (JSON reports would escape unicode anyway).
_FEATURE_META: Dict[str, tuple] = {
    "temperature": ("air temperature", "C", "raw"),
    "humidity": ("relative humidity", "%", "raw"),
    "pressure": ("station pressure", "hPa", "raw"),
    "temp_dev_baseline": ("temperature vs diurnal normal", " sigma", "dev"),
    "humidity_dev_baseline": ("humidity vs diurnal normal", " sigma", "dev"),
    "pressure_dev_baseline": ("pressure vs diurnal normal", " sigma", "dev"),
    "temp_rate": ("temperature rate of change", "C/h", "rate"),
    "humidity_rate": ("humidity rate of change", "%/h", "rate"),
    "pressure_rate": ("pressure rate of change", "hPa/h", "rate"),
    "temp_roll_std_3h": ("short-term temperature variability", "C", "var"),
    "pressure_roll_std_3h": ("short-term pressure variability", "hPa", "var"),
    "vpd": ("vapour-pressure deficit", "hPa", "phys"),
    "thermo_inconsistency_score": ("thermodynamic inconsistency", "", "phys"),
    "pressure_change_3h": ("3-hour pressure tendency", "hPa", "tend"),
}


def _phrase(feature: str, raw_value: float, std_value: float) -> str:
    """Short, honest human phrase for one feature's current value."""
    name, unit, kind = _FEATURE_META.get(feature, (feature, "", "raw"))
    if not np.isfinite(raw_value):
        return f"{name} unavailable"
    if kind == "dev":
        return f"{name} ({raw_value:+.1f}{unit})"
    if kind in ("rate", "tend"):
        return f"{name} {raw_value:+.1f} {unit}".rstrip()
    if kind == "phys" and unit == "":
        return f"{name} ({raw_value:.2f})"
    hi_lo = "high" if std_value >= 0 else "low"
    return f"{name} {raw_value:.1f}{unit} (unusually {hi_lo})"


class Explainer:
    """Attributes an Isolation Forest anomaly score to its evidence features."""

    def __init__(self, detector, config=None):
        self.detector = detector
        self.config = config or DEFAULT_CONFIG
        self.features: List[str] = list(detector.features)
        self._explainer = None
        self._shap_sign = -1.0  # default: shap explains decision_function (higher=normal)
        self.method = "standardized_magnitude_fallback"
        self._init_shap()

    def _init_shap(self) -> None:
        if not _HAVE_SHAP or self.detector.model is None:
            return
        try:
            self._explainer = shap.TreeExplainer(self.detector.model)
            self.method = "shap"
        except Exception:
            self._explainer = None
            self.method = "standardized_magnitude_fallback"

    @staticmethod
    def _orient(sv_sum: np.ndarray, raw: np.ndarray) -> float:
        """Sign so a positive contribution == pushes toward a HIGHER anomaly score.

        Determined empirically from the batch (robust across shap versions);
        defaults to -1 (shap explains decision_function, where higher == more
        normal) when the batch is too small to correlate.
        """
        m = np.isfinite(sv_sum) & np.isfinite(raw)
        if m.sum() >= 5 and np.std(sv_sum[m]) > 0 and np.std(raw[m]) > 0:
            c = float(np.corrcoef(sv_sum[m], raw[m])[0, 1])
            return 1.0 if c >= 0 else -1.0
        return -1.0

    def _contributions(self, Xs: np.ndarray, raw: np.ndarray, max_rows: int):
        """Return (contribs[n,f] oriented toward-anomaly, base_value|None, method)."""
        n = Xs.shape[0]
        if self._explainer is not None and n <= max_rows:
            try:
                sv = np.asarray(self._explainer.shap_values(Xs, check_additivity=False), dtype=float)
                if sv.ndim == 3:  # some shap versions return (n, features, outputs)
                    sv = sv[..., 0]
                exp = float(np.ravel(self._explainer.expected_value)[0])
                sign = self._orient(sv.sum(axis=1), raw)
                self._shap_sign = sign
                return sign * sv, sign * exp, "shap"
            except Exception:
                pass
        # honest fallback: signed standardized magnitude (distance from train mean)
        return Xs.astype(float), None, "standardized_magnitude_fallback"


    def explain(self, feat_df: pd.DataFrame, anomaly_df: Optional[pd.DataFrame] = None,
                top_k: Optional[int] = None, max_rows: int = 5000) -> List[Dict]:
        """Per-row explanation dicts (top-k contributing features + hedged summary)."""
        top_k = int(top_k or self.config.shap_top_features)
        X, complete = to_model_matrix(feat_df, self.config, self.features)
        Xs = self.detector.scaler.transform(X)
        raw = -self.detector.model.decision_function(Xs)
        if anomaly_df is not None and "anomaly_score" in anomaly_df:
            score = anomaly_df["anomaly_score"].reindex(feat_df.index).to_numpy(dtype=float)
        else:
            score = self.detector.score(feat_df)["anomaly_score"].to_numpy(dtype=float)

        Xraw = feat_df.reindex(columns=self.features).to_numpy(dtype=float)
        contribs, base, method = self._contributions(Xs, raw, max_rows)
        order = np.argsort(-np.abs(contribs), axis=1)[:, :top_k]

        out: List[Dict] = []
        for i in range(len(feat_df)):
            if not complete[i]:
                out.append({
                    "method": method, "score": None, "base_value": None, "top_features": [],
                    "summary": "Score not computed: one or more core sensors missing "
                               "(probable data gap, not a confirmed sensor failure).",
                })
                continue
            feats: List[Dict] = []
            for j in order[i]:
                feats.append({
                    "feature": self.features[j],
                    "value": float(Xraw[i, j]) if np.isfinite(Xraw[i, j]) else None,
                    "std_value": round(float(Xs[i, j]), 3),
                    "contribution": round(float(contribs[i, j]), 4),
                    "direction": "increases" if contribs[i, j] > 0 else "decreases",
                    "text": _phrase(self.features[j], Xraw[i, j], Xs[i, j]),
                })
            out.append({
                "method": method,
                "score": None if not np.isfinite(score[i]) else round(float(score[i]), 4),
                "base_value": None if base is None else round(float(base), 4),
                "top_features": feats,
                "summary": self._summary(score[i], feats, method),
            })
        return out

    def explain_row(self, feat_df: pd.DataFrame, **kw) -> Dict:
        """Explain a single observation (first row of ``feat_df``)."""
        rows = self.explain(feat_df.iloc[[0]] if len(feat_df) else feat_df, **kw)
        return rows[0] if rows else {"method": self.method, "top_features": [], "summary": "no data"}

    def _summary(self, score: float, feats: List[Dict], method: str) -> str:
        tag = ("SHAP feature attribution" if method == "shap"
               else "standardized-magnitude fallback, SHAP unavailable")
        lead = "; ".join(f["text"] for f in feats) if feats else "no dominant feature"
        if not np.isfinite(score):
            return f"Score unavailable (incomplete data). Leading evidence: {lead}. ({tag}.)"
        if score >= self.config.severity_critical_score:
            head = f"Probable anomaly (high score {score:.2f})"
        elif score >= self.config.severity_warning_score:
            head = f"Possible anomaly (score {score:.2f})"
        else:
            head = f"No anomaly indicated (score {score:.2f})"
        return f"{head}. Leading evidence: {lead}. ({tag}.)"


def explain_observations(detector, feat_df, anomaly_df=None, config=None, top_k=None):
    """Convenience: build an Explainer and return per-row explanations."""
    return Explainer(detector, config).explain(feat_df, anomaly_df, top_k=top_k)
