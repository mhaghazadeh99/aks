"""
Combined activity inventory for a waste batch: Gamma spectrometry gives
per-nuclide activity; the gas-proportional counter gives only GROSS
totals (total_alpha, total_beta) with no nuclide identification.

METHOD (this is the standard "scaling factor" idea used in radwaste
characterization, e.g. ISO 21238 / IAEA correlation methods — using
easy-to-measure key nuclides to account for hard-to-measure ones):

  1. Every nuclide identified by gamma spectrometry already has its
     TOTAL decay activity (not just "gamma decays") — that's what a
     correctly calibrated gamma-spec analysis reports, using the
     nuclide's gamma emission probability/branching ratio to convert
     photon count rate back to Bq. So a gamma-identified nuclide's
     activity_bq already represents 100% of its decays, including any
     beta or alpha particles it emits as part of that decay.
  2. Some of those decays ALSO show up in the gross alpha/beta count
     (e.g. Cs-137 beta-decays to Ba-137m; Am-241 both alpha- and
     gamma-decays). Left alone, that activity would be counted TWICE:
     once from the gamma line, once inside the gross total.
  3. So: subtract the gamma-identified nuclides' beta (or alpha)
     contribution from the matching gross total BEFORE adding it to
     the inventory. What's left ("pure" beta/alpha) is activity from
     nuclides gamma spec can't see at all (H-3, C-14, Sr-90/Y-90,
     Pu-alpha, etc.).
  4. total = sum(gamma-identified activities) + pure_beta + pure_alpha

CAVEATS (real ones — read before trusting this for a regulatory number):
  - Gross alpha/beta counters are normally calibrated against ONE
    reference nuclide (e.g. Am-241 for alpha, Cs-137 or Sr/Y-90 for
    beta) and report an "as X" equivalent activity. Counting
    efficiency is energy-dependent, so subtracting a true Bq value
    (from gamma spec) from a reference-equivalent Bq value (from the
    counter) is an approximation, not an exact physical subtraction.
    It's the standard practice for this kind of screening, but it is
    NOT interchangeable with a per-nuclide-calibrated measurement.
  - Only nuclides flagged `emits_beta` / `emits_alpha` on the
    Nuclides reference table are netted out. A gamma emitter that
    decays purely by electron capture or isomeric transition (no
    accompanying beta/alpha) must NOT be flagged, or its activity
    would be wrongly subtracted from the gross total.
  - If the net comes out negative (gross count lower than what gamma
    spec alone implies), that's a red flag — mismatched geometry,
    bad calibration, or a counting error — not a real "negative
    activity". This function floors it at 0 and returns a warning
    string instead of silently hiding the problem.
"""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ..models import RadiationType


def total_activity_breakdown(gamma_analysis, alpha_beta_analysis, as_of=None):
    """
    gamma_analysis: an Analysis with detector_type=HPGE (or None)
    alpha_beta_analysis: an Analysis with detector_type=ALPHABETA (or None)
    as_of: date to decay-correct every nuclide activity to (default: today)

    Returns a dict:
      as_of, gamma_total_bq, pure_beta_bq, pure_alpha_bq,
      beta_emitting_gamma_bq, alpha_emitting_gamma_bq, total_bq,
      gamma_lines (list of {"nuclide": Nuclides, "activity_bq": float}),
      warnings (list of str), gamma_analysis, alpha_beta_analysis
    """
    as_of = as_of or timezone.now().date()

    gamma_lines = []
    gamma_total = 0.0
    beta_emitting_gamma_total = 0.0
    alpha_emitting_gamma_total = 0.0
    warnings = []

    if gamma_analysis:
        for na in gamma_analysis.nuclide_activities.filter(radiation_type=RadiationType.GAMMA).select_related("radionuclide"):
            value = na.current_activity_bq(as_of=as_of) or 0.0
            gamma_lines.append({"nuclide": na.radionuclide, "activity_bq": value})
            gamma_total += value
            if getattr(na.radionuclide, "emits_beta", False):
                beta_emitting_gamma_total += value
            if getattr(na.radionuclide, "emits_alpha", False):
                alpha_emitting_gamma_total += value

    pure_beta = None
    if alpha_beta_analysis and alpha_beta_analysis.total_beta is not None:
        gross_beta = float(alpha_beta_analysis.total_beta)
        pure_beta = gross_beta - beta_emitting_gamma_total
        if pure_beta < 0:
            warnings.append(
                _("Gross beta (%(g).3f Bq) is lower than the beta activity already identified "
                  "by gamma spectrometry (%(b).3f Bq) for this batch — check counter calibration "
                  "or geometry. Pure beta was floored at 0 for this total.")
                % {"g": gross_beta, "b": beta_emitting_gamma_total}
            )
            pure_beta = 0.0

    pure_alpha = None
    if alpha_beta_analysis and alpha_beta_analysis.total_alpha is not None:
        gross_alpha = float(alpha_beta_analysis.total_alpha)
        pure_alpha = gross_alpha - alpha_emitting_gamma_total
        if pure_alpha < 0:
            warnings.append(
                _("Gross alpha (%(g).3f Bq) is lower than the alpha activity already identified "
                  "by gamma spectrometry (%(b).3f Bq) for this batch — check counter calibration "
                  "or geometry. Pure alpha was floored at 0 for this total.")
                % {"g": gross_alpha, "b": alpha_emitting_gamma_total}
            )
            pure_alpha = 0.0

    total = gamma_total + (pure_beta or 0.0) + (pure_alpha or 0.0)

    return {
        "as_of": as_of,
        "gamma_total_bq": gamma_total,
        "pure_beta_bq": pure_beta,
        "pure_alpha_bq": pure_alpha,
        "beta_emitting_gamma_bq": beta_emitting_gamma_total,
        "alpha_emitting_gamma_bq": alpha_emitting_gamma_total,
        "total_bq": total if (gamma_lines or pure_beta is not None or pure_alpha is not None) else None,
        "gamma_lines": gamma_lines,
        "warnings": warnings,
        "gamma_analysis": gamma_analysis,
        "alpha_beta_analysis": alpha_beta_analysis,
    }