# utils/physics.py

import math

LN2 = math.log(2)

BQ_PER_CI = 3.7e10
BQ_PER_MCI = 3.7e7  # 1 mCi = 3.7e7 Bq

def mci_to_bq(v):
    return v * BQ_PER_MCI

def bq_to_mci(v):
    return v / BQ_PER_MCI