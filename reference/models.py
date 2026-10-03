from django.db import models

# Create your models here.
class Nuclides(models.Model):
    name = models.CharField(max_length=8, unique=True)

    # store in seconds
    half_life = models.FloatField(null=True, blank=True)

    # D-value MUST be in Bq
    d_value_bq = models.FloatField(null=True, blank=True)

    # --- ADD THESE BELOW ---

    atomic_number = models.IntegerField(null=True, blank=True)
    mass_number = models.IntegerField(null=True, blank=True)

    decay_mode = models.CharField(max_length=50, null=True, blank=True)
    decay_constant = models.FloatField(null=True, blank=True)  # 1/sec

    specific_activity_bq_per_g = models.FloatField(null=True, blank=True)

    # Radiation emissions
    alpha_energy_mev = models.FloatField(null=True, blank=True)
    beta_max_energy_mev = models.FloatField(null=True, blank=True)
    gamma_energy_mev = models.FloatField(null=True, blank=True)
    gamma_yield = models.FloatField(null=True, blank=True)  # photons/decay
    

    neutron_emitter = models.BooleanField(default=False)
    neutron_yield_n_per_s = models.FloatField(null=True, blank=True)

    # Dose & shielding related
    dose_rate_constant_usv_m2_per_h_gbq = models.FloatField(null=True, blank=True)
    half_value_layer_lead_mm = models.FloatField(null=True, blank=True)
    half_value_layer_concrete_mm = models.FloatField(null=True, blank=True)

    # Radiological classification
    iaea_category = models.IntegerField(null=True, blank=True)

    # Misc
    parent_nuclide = models.CharField(max_length=20, null=True, blank=True)
    daughter_nuclide = models.CharField(max_length=20, null=True, blank=True)
    beta_emission_probability = models.FloatField(
        null=True, blank=True,
        help_text="Fraction (0-1) of this nuclide's decays that emit a beta particle. 1.0 for a "
                   "single-mode beta emitter (Cs-137, Co-60, Sr-90...); the real branching fraction "
                   "for a mixed-mode nuclide (e.g. K-40 = 0.8928, 89.28% beta / 10.72% EC); leave blank "
                   "if this nuclide doesn't emit beta at all.",
    )
    alpha_emission_probability = models.FloatField(
        null=True, blank=True,
        help_text="Same idea, for alpha emission. 1.0 for a pure alpha emitter (Am-241, Ra-226...); "
                   "the branching fraction for a mixed-mode nuclide; blank if not an alpha emitter.",
    )
    is_sealed_source_common = models.BooleanField(default=False)
    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        super().save(*args, **kwargs)
    def __str__(self):
        return self.name