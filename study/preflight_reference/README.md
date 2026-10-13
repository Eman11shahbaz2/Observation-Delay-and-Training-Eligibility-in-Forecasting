# Reporting-delay research: new-source preflight

Start with **FEASIBILITY_REPORT.md**. This package completes the timestamp-only check and freezes preparation rules for the two predetermined new sources. It contains **no empirical model fits, predictions or forecasting scores** for these sources.

Files:

- `EXPANSION_PROTOCOL.md`: full outcome-uninspected extension protocol, with source-specific preparation, exact dates, availability scenarios, unchanged candidates and declared contrasts.
- `TIMESTAMP_PREFLIGHT.json`, `potential_case_counts.csv`: complete source identities/hashes, timestamp counts, duplicates, gaps, boundaries and timing-only potential counts.
- `AUDIT_RULES.md`, `AUDIT_FREEZE.json`, `EXPANSION_FREEZE.json`: rules and recorded pre-inspection hashes.
- `source_archives/`: original official UCI archives, included unchanged with CC BY 4.0 attribution in `SOURCE_REGISTER.md`. They contain raw target values; only timestamps were parsed in this stage.
- `preflight_new_sources.py`: date-only archive audit. It excludes all measurement columns from pandas parsing.
- `source_preparation.py`: frozen preparation adapters and guarded development-prefix loader, tested only on synthetic fixtures at this stage.
- `audit_exports.py`: tested union-schema, single-stream, validated, atomic CSV.GZ export writer for the next runner.
- `SOURCE_CONFIG.json`: fixed target/covariate lists, timing settings, boundaries and source identities.
- `write_feasibility_report.py`: report/configuration generation.
- `test_*.py`, `validation.log`, `VALIDATION_RESULTS.json`: synthetic and completed timestamp/provenance checks.
- `reference/`, `AUDIT_REVISION_NOTES.md`: prior design/repair references and the initial audit helper, preserved for revision transparency. Do not run reference/preflight_initial.py as the current audit.
- `CHECKSUMS.sha256`: package integrity hashes.

Install requirements.txt in an isolated Python environment. From this directory:

```bash
python3 preflight_new_sources.py
python3 -m unittest discover -v
python3 write_feasibility_report.py
```

The bundled archives are reused rather than redownloaded when present. Date-field checks include the full timestamp span; the real-value loader is reserved for the later execution stage. Do not call it on the archives yet. Re-running report generation updates the recorded freeze time, so preserve the original package as the pre-outcome record.

The traffic target rule is exact duplicate consensus; the household target is hourly mean active power in kW requiring all 60 valid minutes. Gaps and invalid labels stay missing. Neither source's numeric feasibility is confirmed solely by this preflight. If all 16 new settings pass the later numerical gates, the follow-up run has a maximum 384 new fits. The new fitting runner is not included in this preflight package and must be frozen before target inspection.
