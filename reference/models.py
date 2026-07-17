from django.db import models

# Create your models here.
class Nuclides(models.Model):
    name = models.CharField(max_length=8)

    # store in seconds
    half_life = models.FloatField()

    # D-value MUST be in Bq
    d_value_bq = models.FloatField()

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

    is_sealed_source_common = models.BooleanField(default=False)

    def __str__(self):
        return self.name