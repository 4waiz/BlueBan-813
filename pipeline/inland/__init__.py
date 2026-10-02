"""Inland complement: Shawka Dam (Ras Al Khaimah), EnMAP L2A.

Namespaced copy of the separately built inland pipeline (water mask, RX anomaly,
fingerprint, 813 simulation on EnMAP, temporal baseline detector, provenance).
The modules are byte-identical to the delivered package. They are kept for
methodology transparency and for re-running against a future scene; BLUEBAN
does not execute them. The site's data source is the precomputed outputs in
data/inland/, summarised by scripts/inland/build_inland_bundle.py.

temporal.py needs pandas (``pip install -e ".[inland]"``); the other modules
need only numpy.
"""
