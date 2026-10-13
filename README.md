# Observation Delay and Training Eligibility in Forecasting

This repository contains the code and recorded results for our comparison of observation delay and training eligibility across four public time series.

## Contents

- `study/`: experiment code, fixed protocols, model choices, results and verification records. Start with `COMPLETED_STUDY_REPORT.md`.
- `paper_materials/`: the main paper tables, historical IQR values and both figures. Detailed candidate and selector results are in `study/final_results/`; development results are in `study/development_results/` and `study/development_reference/`.
- `download_sources.py`: downloads the four original UCI datasets and checks their recorded hashes.

## Setup and verification

Use Python 3.12.14. From the repository root:

```bash
python -m pip install -r study/requirements.txt
python download_sources.py
cd study
python -m unittest discover -v
```

The completed study passed 83 checks and recorded 768 development fits and 48 final fits. The verification command checks existing evidence without fitting models.

The final evaluation has already been used once. To replay it, work in a separate copy, remove that copy's `final_results/` and `FINAL_EVALUATION_STARTED.json`, then run `python run_final_evaluation.py --workers 3 --output final_results` from `study/`. This reproduces an evaluated test; it is not a new holdout.

Official dataset links: [Bike](https://doi.org/10.24432/C5W894), [Beijing](https://doi.org/10.24432/C5RK5G), [Traffic](https://doi.org/10.24432/C5X60B), [Household](https://doi.org/10.24432/C58K54).

Original archives and trained model weights are not bundled. Earlier development prediction exports are not included; their scores and fit records are retained. Historical records support the frozen audit and may describe earlier incomplete stages. `PACKAGE_CHECKSUMS.sha256` covers this distribution; the original study checksum list is retained separately. No code reuse license has been assigned.
