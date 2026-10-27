# Data provenance and checksums

## NIEM 6.0
- URL: https://docs.oasis-open.org/niemopen/niem-model/v6.0/os/niem-model-v6.0-os.zip
- Zip SHA-256: `2b899067b5312333935329e6e7665e1eb295f392a51d4a56bc9800dbcc42fcfa`

## HIT-UAV
- Source (commit-pinned in `scripts/download_datasets.py`): https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset
- train/val/test JSON SHA-256: `4e6e93966ec366ce63aa120f038c52e792b02811ff2ab2d43ef56e6561aceff1`, `9b34b423b6b1602b87e88b7f9864fa4273b73c280846ba6cb1b90c2e6761873e`, `f29545df4b27bb09fa705b0d2865f69f5ef7cdf81930b84dcc9dd0df63c71d19`
- Images: 2898, annotations: 24751
- Held-in zstd-dictionary training IDs (`firms_train_ids_500.json`): `751beab1cbdfea7146a903c722d101385669b7cf4f1f6298637ae85446505c7a`
- Those 500 IDs are NASA FIRMS detection IDs (`FIRMS_...`). The previous filename `hituav_train_Ids_500.json` did not match the contents. The file bytes are unchanged.

## NASA FIRMS Canada 24h snapshot
- Committed file: `data/sample/firms_canada_24h_snapshot.csv`
- Rows: 720
- SHA-256: `eceac7905c3aedd66578c8c2b1a01cde7f5fafc8ac387aa0359c2367a919bf1b`
- Retrieved (UTC): 2026-10-26T18:25:46.007716+00:00

## Corpus splits
- Total canonical detections: 25471
- Held-in (zstd dict train): 500
- Held-out (M1/M2/M3 eval): 5000
- Held-out corpus SHA-256: `863f7c7a7dab2bba67c70fdabe07d40d6deaf48dc299edb5e2d798e540130bfd`

## Sample thermal JPEG
- SHA-256: `92e92314e9b61d3ae59179ecf63200b623db63e317e6fb351cdb83adf53415ad`
