"""
NOTE (result_unit): the lab types results in the unit chosen on the analysis
(Bq/kg, Bq/L or whole-sample Bq). _concentration() below honours that and never
divides a value that is already per-kg / per-L by the sample size again.

Combined, mass/volume-scaled activity inventory for a waste batch.

THE PROBLEM WITH THE PREVIOUS VERSION: it treated a lab sample's measured
Bq figures as if they already WERE the batch's total activity. They aren't
— a sample is a small fraction of the batch's mass or volume, so the raw
Bq reading needs scaling up before it means anything about the whole batch.
This version does that scaling, and does it correctly even though a Gamma
analysis and an Alpha/Beta analysis on the same batch come from DIFFERENT
physical samples (Sample.analysis_type picks one detector per sample), each
with its own mass/volume.

METHOD, in order:

  1. Every measured Bq figure (a gamma nuclide's activity, or the gross
     alpha/beta total) is first turned into a CONCENTRATION — Bq per kg
     and/or Bq per L of the sample it was actually measured on, using
     whichever of that sample's sample_mass_kg / sample_volume_ml is
     recorded. This is the number that's actually representative of "the
     waste", assuming the sample was representative of the batch.

  2. Netting gamma-identified nuclides out of gross alpha/beta happens AT
     THE CONCENTRATION LEVEL, not on raw Bq — because the gamma sample and
     the alpha/beta sample are generally different physical samples of
     different size. Subtracting raw Bq values from two different-sized
     samples would silently assume they were the same size. Netting only
     happens when both sides share a basis (both have a recorded mass, or
     both have a recorded volume); if they don't share one, netting is
     skipped and flagged rather than guessed.

     Each gamma-identified nuclide contributes to that netting scaled by
     its `beta_emission_probability` / `alpha_emission_probability` (a
     fraction, not a flag) — see reference.Nuclides. A nuclide whose own
     decay is 100% beta contributes all of its activity; one with real
     branching (K-40: 89.28% beta / 10.72% EC) contributes only that
     fraction, not the whole thing.

  3. Every concentration (gamma nuclides, and the netted "pure" gross
     beta/alpha) is then scaled to the BATCH's total mass or volume to get
     a real total activity for the whole batch, in Bq. A stream that can't
     be scaled (its sample recorded no mass/volume, or the batch itself
     has neither) is excluded from the totals — not silently included as
     if the sample-sized number were the batch total — and flagged with a
     warning, since the reported total will then understate the batch.

  4. The whole-batch total is also expressed as a concentration
     (Bq/kg and/or Bq/L of the BATCH itself) for comparison against
     concentration-based limits (clearance/exemption levels etc).

CALIBRATION CAVEAT (still applies, now made explicit and adjustable):
gas-proportional gross alpha/beta counters are calibrated against ONE
reference nuclide and report an equivalent activity in that nuclide's
terms — efficiency is energy-dependent, so "pure beta"/"pure alpha" is an
approximation, not a per-nuclide-calibrated measurement, UNLESS a manual
efficiency correction factor has been set on the counting run (see
AlphaBetaCountingRun.alpha/beta_efficiency_correction_factor). We do NOT
attempt to auto-derive that correction: the "pure" fraction is by
definition unidentified, so there is no nuclide to look an efficiency up
for without an assumption only the analyst can responsibly make. Left
uncorrected by default; the calibration nuclide (if recorded) is named in
a note so the equivalence is explicit rather than implied.
"""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ..models import RadiationType


def _concentration(value, sample, unit="SAMPLE"):
    """(Bq/kg, Bq/L) for a lab-entered `value`, given the unit the lab entered
    it in (Analysis.effective_result_unit):

      "KG"     -- already Bq/kg. Used as-is; NOT divided by the sample's mass
                  again (that would double-divide). No Bq/L figure is implied.
      "L"      -- already Bq/L. Used as-is, same reasoning.
      "SAMPLE" -- the whole-sample total in Bq (what every analysis entered
                  before result_unit existed is): divided by the sample's own
                  recorded mass and/or volume, as before.

    Either element is None when that basis can't be known. value may be None."""
    if value is None:
        return None, None
    if unit == "KG":
        return float(value), None
    if unit == "L":
        return None, float(value)
    per_kg = float(value) / float(sample.sample_mass_kg) if sample.sample_mass_kg else None
    per_l = float(value) / (float(sample.sample_volume_ml) / 1000.0) if sample.sample_volume_ml else None
    return per_kg, per_l


def _scale_to_batch(conc_per_kg, conc_per_l, batch):
    """A whole-batch Bq total from a concentration, preferring mass. (None, None)
    if neither the concentration nor the matching batch quantity is available."""
    if batch is None:
        return None, None
    if conc_per_kg is not None and batch.mass_kg:
        return conc_per_kg * float(batch.mass_kg), "mass"
    if conc_per_l is not None and batch.volume_m3:
        return conc_per_l * float(batch.volume_m3) * 1000.0, "volume"
    return None, None


def total_activity_breakdown(gamma_analysis, alpha_beta_analysis, batch=None, as_of=None):
    """
    gamma_analysis: an Analysis with detector_type=HPGE (or None)
    alpha_beta_analysis: an Analysis with detector_type=ALPHABETA (or None)
    batch: the WasteBatch to scale up to (or None — figures then stay at
           sample/concentration level and totals are not computed, since a
           "batch total" means nothing without a batch)
    as_of: date to decay-correct every nuclide activity to (default: today)

    Returns a dict:
      as_of,
      gamma_total_bq, pure_beta_bq, pure_alpha_bq, total_bq  (whole-batch Bq, or
        None where that stream couldn't be scaled — see warnings)
      concentration_bq_per_kg, concentration_bq_per_l  (whole-batch, from total_bq)
      gamma_lines: [{"nuclide", "sample_activity_bq", "batch_activity_bq", "basis"}]
      warnings: list of str
      gamma_analysis, alpha_beta_analysis
    """
    as_of = as_of or timezone.now().date()
    warnings = []

    # ---------- gamma: per-nuclide, scaled to the whole batch ----------
    gamma_lines = []
    gamma_total_bq = 0.0
    gamma_total_known = False

    beta_emit_conc_kg = beta_emit_conc_l = 0.0
    alpha_emit_conc_kg = alpha_emit_conc_l = 0.0
    have_beta_mass = have_beta_vol = have_alpha_mass = have_alpha_vol = False

    if gamma_analysis:
        gsample = gamma_analysis.sample
        gamma_unit = gamma_analysis.effective_result_unit
        for na in gamma_analysis.nuclide_activities.filter(radiation_type=RadiationType.GAMMA).select_related("radionuclide"):
            sample_bq = na.current_activity_bq(as_of=as_of) or 0.0
            conc_kg, conc_l = _concentration(sample_bq, gsample, gamma_unit)
            batch_bq, basis = _scale_to_batch(conc_kg, conc_l, batch)

            gamma_lines.append({
                "nuclide": na.radionuclide,
                "sample_activity_bq": sample_bq,
                "batch_activity_bq": batch_bq,
                "basis": basis,
            })

            if batch_bq is not None:
                gamma_total_bq += batch_bq
                gamma_total_known = True
            elif batch is not None:
                warnings.append(
                    _("%(n)s: sample %(s)s has no recorded mass or volume, so its activity couldn't "
                      "be scaled to the batch — the gamma total below likely understates the batch.")
                    % {"n": na.radionuclide, "s": gsample.sample_id}
                )

            beta_p = getattr(na.radionuclide, "beta_emission_probability", None)
            alpha_p = getattr(na.radionuclide, "alpha_emission_probability", None)
            if beta_p:
                if conc_kg is not None:
                    beta_emit_conc_kg += conc_kg * beta_p; have_beta_mass = True
                if conc_l is not None:
                    beta_emit_conc_l += conc_l * beta_p; have_beta_vol = True
            if alpha_p:
                if conc_kg is not None:
                    alpha_emit_conc_kg += conc_kg * alpha_p; have_alpha_mass = True
                if conc_l is not None:
                    alpha_emit_conc_l += conc_l * alpha_p; have_alpha_vol = True

    # ---------- gross alpha/beta: net (at concentration level) then scale ----------
    pure_beta_bq = pure_alpha_bq = None
    gross_beta_bq = gross_alpha_bq = None
    counting_run = getattr(alpha_beta_analysis, "counting_run", None) if alpha_beta_analysis else None

    def _net_and_scale(gross_value, have_mass, have_vol, emit_kg, emit_l, ab_sample, label, unit):
        """Returns (gross_batch_bq, pure_batch_bq) -- the raw gross reading scaled to the
        whole batch (no netting), and the gamma-netted "pure" reading also scaled.
        `gross_batch_bq` is what Total Alpha/Total Beta should show: the counting result,
        scaled up the same way gamma already is -- NOT the as-measured sample figure."""
        gross_kg, gross_l = _concentration(gross_value, ab_sample, unit)
        gross_batch_bq, _basis0 = _scale_to_batch(gross_kg, gross_l, batch)

        net_kg = net_l = None
        netted = False
        if gross_kg is not None and have_mass:
            net_kg = gross_kg - emit_kg; netted = True
        if gross_l is not None and have_vol:
            net_l = gross_l - emit_l; netted = True
        if not netted:
            net_kg, net_l = gross_kg, gross_l
            if have_mass or have_vol:
                warnings.append(
                    _("Gross %(label)s and the gamma-identified %(label)s emitters were measured on "
                      "samples with no shared mass/volume basis, so they couldn't be netted against "
                      "each other — pure %(label)s is the unmodified gross reading.") % {"label": label}
                )
        if net_kg is not None and net_kg < 0:
            warnings.append(
                _("Gross %(label)s concentration is lower than the %(label)s activity already identified "
                  "by gamma spectrometry — check counter calibration/geometry. Pure %(label)s floored at "
                  "0 (mass basis).") % {"label": label}
            )
            net_kg = 0.0
        if net_l is not None and net_l < 0:
            warnings.append(
                _("Gross %(label)s concentration is lower than the %(label)s activity already identified "
                  "by gamma spectrometry — check counter calibration/geometry. Pure %(label)s floored at "
                  "0 (volume basis).") % {"label": label}
            )
            net_l = 0.0
        pure_batch_bq, _basis = _scale_to_batch(net_kg, net_l, batch)
        if pure_batch_bq is None and batch is not None:
            warnings.append(
                _("Sample %(s)s (Alpha/Beta) has no recorded mass or volume, so total/pure %(label)s "
                  "couldn't be scaled to the batch.") % {"s": ab_sample.sample_id, "label": label}
            )
        return gross_batch_bq, pure_batch_bq

    if alpha_beta_analysis:
        ab_sample = alpha_beta_analysis.sample
        ab_unit = alpha_beta_analysis.effective_result_unit

        if alpha_beta_analysis.total_beta is not None:
            gross_beta_bq, pure_beta_bq = _net_and_scale(
                float(alpha_beta_analysis.total_beta), have_beta_mass, have_beta_vol,
                beta_emit_conc_kg, beta_emit_conc_l, ab_sample, "beta", ab_unit,
            )
            if pure_beta_bq is not None and counting_run and counting_run.beta_efficiency_correction_factor:
                pure_beta_bq *= counting_run.beta_efficiency_correction_factor
                warnings.append(
                    _("Pure beta includes a manual efficiency correction factor of %(f)s.")
                    % {"f": counting_run.beta_efficiency_correction_factor}
                )
            if pure_beta_bq is not None and counting_run and counting_run.beta_calibration_nuclide:
                warnings.append(
                    _("Pure beta is expressed as %(n)s-equivalent activity (the counter's beta "
                      "calibration source) — not a per-nuclide-calibrated measurement.")
                    % {"n": counting_run.beta_calibration_nuclide}
                )

        if alpha_beta_analysis.total_alpha is not None:
            gross_alpha_bq, pure_alpha_bq = _net_and_scale(
                float(alpha_beta_analysis.total_alpha), have_alpha_mass, have_alpha_vol,
                alpha_emit_conc_kg, alpha_emit_conc_l, ab_sample, "alpha", ab_unit,
            )
            if pure_alpha_bq is not None and counting_run and counting_run.alpha_efficiency_correction_factor:
                pure_alpha_bq *= counting_run.alpha_efficiency_correction_factor
                warnings.append(
                    _("Pure alpha includes a manual efficiency correction factor of %(f)s.")
                    % {"f": counting_run.alpha_efficiency_correction_factor}
                )
            if pure_alpha_bq is not None and counting_run and counting_run.alpha_calibration_nuclide:
                warnings.append(
                    _("Pure alpha is expressed as %(n)s-equivalent activity (the counter's alpha "
                      "calibration source) — not a per-nuclide-calibrated measurement.")
                    % {"n": counting_run.alpha_calibration_nuclide}
                )

    parts = [x for x in (gamma_total_bq if gamma_total_known else None, pure_beta_bq, pure_alpha_bq) if x is not None]
    total_bq = sum(parts) if parts else None

    concentration_bq_per_kg = (total_bq / float(batch.mass_kg)) if (total_bq is not None and batch and batch.mass_kg) else None
    concentration_bq_per_l = (total_bq / (float(batch.volume_m3) * 1000.0)) if (total_bq is not None and batch and batch.volume_m3) else None

    return {
        "as_of": as_of,
        "gamma_total_bq": gamma_total_bq if gamma_total_known else None,
        "gross_alpha_bq": gross_alpha_bq,
        "gross_beta_bq": gross_beta_bq,
        "pure_beta_bq": pure_beta_bq,
        "pure_alpha_bq": pure_alpha_bq,
        "total_bq": total_bq,
        "concentration_bq_per_kg": concentration_bq_per_kg,
        "concentration_bq_per_l": concentration_bq_per_l,
        "gamma_lines": gamma_lines,
        "warnings": warnings,
        "gamma_analysis": gamma_analysis,
        "alpha_beta_analysis": alpha_beta_analysis,
    }