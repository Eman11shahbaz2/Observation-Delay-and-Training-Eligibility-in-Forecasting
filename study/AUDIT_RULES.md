# New-source timestamp audit: rules fixed before downloading

Date: 12 October 2026, Asia/Karachi. The preceding exploratory development experiment is complete. This stage assesses only metadata and timestamp structure for the two predetermined new sources: UCI Metro Interstate Traffic Volume (492, DOI 10.24432/C5X60B) and Individual Household Electric Power Consumption (235, DOI 10.24432/C58K54).

Download only official archives. Inspect archive/member identity, byte hashes, header names and timestamp columns. Use `usecols` to exclude all measurement and target columns from numeric parsing. Full raw archives contain those values, but this audit must not compute their distributions, missing-value rates, duplicate-value agreement, features, model predictions or scores. No target-driven exclusion or date selection. Read-only date-field checks may include the reserved portion.

Traffic timestamps must parse in the official date_time column at nominal hourly resolution. Report duplicate timestamps and their multiplicities, chronological order, missing clock hours and gap lengths. Do not resolve duplicate targets in this stage. The later preparation protocol must declare an outcome-independent duplicate rule before inspecting values.

Household Date and Time must parse exactly as dd/mm/yyyy HH:MM:SS, at nominal minute resolution. Count duplicate timestamps, missing nominal minutes, per-hour minute counts and structurally complete hours. An hour is structurally complete only if it contains all 60 distinct expected minute stamps with no duplicates. Use the first and last structurally complete hours as the target-grid endpoints; internal incomplete hours remain represented as missing. Numeric completeness remains unverified until the later guarded loading stage.

Do not infer timezone offsets or DST corrections. Traffic documentation labels the clock local CST; household metadata does not establish an arrival-time or unambiguous UTC timeline. All subsequent horizons are nominal clock hours, with these limitations reported explicitly.

Generate T1/T2 boundaries from the first/last hourly grid endpoints using the unchanged elapsed-span 50/60/70/80% rule, rounded upward to the hour. Reserve the final 20% of nominal span. Report timestamp-only potential training/validation/future counts for all four O,L settings and max-55-hour label-maturity scale membership. These upper-bound counts do not establish finite labels/persistence, target diversity or final numerical feasibility.

Stop on malformed fields, non-minute/non-hour alignment or ambiguous archive identity. A dataset with structural issues stays in the report with an explained decision; do not replace it based on results. No forecasting models are fitted in this stage.
