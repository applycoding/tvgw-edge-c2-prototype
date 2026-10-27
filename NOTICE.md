# NOTICES AND ATTRIBUTIONS

## Repository code
Copyright 2026 Arpan Bom. Licensed under Apache License 2.0.

## OASIS NIEMOpen 6.0
Project: NIEMOpen Version: 6.0; Copyright (c) OASIS Open 2025. All Rights Reserved.
Used under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

## HIT-UAV Infrared Thermal Dataset
Licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) on GitHub (not public domain).
Zenodo record 7633134 metadata may declare CC0 1.0; this repository attributes under CC BY 4.0 conservatively.
Suo, J., Wang, T., Zhang, X., Chen, H., Zhou, W., & Shi, W. (2023).
HIT-UAV: A high-altitude infrared thermal dataset for Unmanned Aerial Vehicle-based object detection.
Scientific Data, 10, 227. https://doi.org/10.1038/s41597-023-02066-6

**Modified / derived in this repo:** the sample thermal JPEG (`data/sample/sample_thermal_0_100_30_0_03307.jpg`), the held-in ID list `data/sample/firms_train_ids_500.json` (NASA FIRMS record IDs used to train the zstd dictionary; these are not HIT-UAV IDs), and canonical detection records derived from upstream JSON annotations (synthetic Calgary GPS tracks for HIT-UAV items).

## NASA FIRMS Active Fire Data
NASA Earth Science Data and Information System (ESDIS) open data policy applies.
Acknowledgment: *We acknowledge the use of data and imagery from NASA's Land, Atmosphere Near real-time Capability for EOS (LANCE) system and the NASA FIRMS application (https://firms.modaps.eosdis.nasa.gov), part of NASA's Earth Science Data and Information System (ESDIS).*

## Third-party Python packages
lxml (BSD-3-Clause), zstandard (BSD-3-Clause), numpy (BSD-3-Clause), cbor2 (MIT),
PyYAML (MIT), pytest (MIT), matplotlib (PSF-based), Pillow (MIT-CMU), hypothesis (MPL-2.0).
