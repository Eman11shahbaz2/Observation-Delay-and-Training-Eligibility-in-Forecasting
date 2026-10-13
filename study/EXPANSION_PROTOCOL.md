# Outcome-uninspected source extension: frozen preparation protocol

Date: 12 October 2026, Asia/Karachi. Written after timestamp-only preflight and before numeric target inspection of either new source. This is a prospective analysis plan for existing public benchmark data, not a registered study or newly collected external cohort. The prior two-source experiment remains exploratory and unchanged. Novelty remains unestablished.

## Question and fixed scope

Does physical target-observation delay change the chronological-versus-random model-selection regret differently from an equally long extra fitting-use restriction, when both settings have equal label maturity? Keep the previously declared primary contrast and candidate models; do not revise them based on the expansion's outcomes.

Use exactly UCI Metro Interstate Traffic Volume (492, DOI 10.24432/C5X60B), one MN DoT ATR 301 westbound I-94 station, and UCI Individual Household Electric Power Consumption (235, DOI 10.24432/C58K54), one Sceaux household. Do not treat repeated weather rows, electrical channels, split seeds or periods as independent datasets. Inclusion is based on timestamp feasibility and predetermined sources, never preferred scores. Both source archives and selected-member hashes are in TIMESTAMP_PREFLIGHT.json.

## Clock and target definitions

Use nominal source clock labels. Traffic metadata labels its timestamps local CST. Household metadata does not establish a timezone/UTC mapping or release-time history. Infer no DST correction, repeated-hour reconstruction or true elapsed UTC forecast horizon. These limitations remain in the report. A source timestamp s is interpreted as the beginning of an hour; hourly measurements complete at s+1 under the same hypothetical convention as the original study.

| Source | Exact six-hour-ahead target | Units | Preparation |
| --- | --- | --- | --- |
| Traffic | traffic_volume for hour [t+6,t+7) | vehicle count per hour | One consensus count per nominal hour |
| Household | mean Global_active_power for hour [t+6,t+7) | kW | Arithmetic mean of 60 complete minute-averaged power readings |

Household power is not an hourly energy sum. Exclude the initial 36-minute and final 3-minute partial hours from the grid endpoints based on timestamp structure alone. Every interior hour stays on the nominal grid. Require all 60 distinct expected minute timestamps with no duplicates. For the target, require all 60 finite, nonnegative readings; any missing/invalid reading makes that hour's target missing. Do not average only the available minutes or fill minute values. If an hour is structurally incomplete, all of its aggregated measurements are missing.

For traffic, consolidate all rows tagged with the same nominal hour. The target must be finite, nonnegative and integer-valued in every row, with exact agreement across the duplicates. If any value is missing/invalid or the values disagree, make that hourly target missing. Never sum duplicate counts, average conflicting counts, select a favorable row or weight duplicate hours more heavily. Numeric covariates use the same all-finite exact-consensus rule. For weather_main, encode the sorted unique category set as a compact JSON array; any missing/blank category makes the hour's category missing. That rule is independent of row ordering and target values. Distinct physical DST hours cannot be recovered from an ambiguous nominal timestamp; consensus handling does not resolve that limitation.

Convert declared nonnumeric/missing measurement tokens to missing values and record their counts during the later numerical loading stage. Do not interpolate targets or forward-fill labels. Missing feature values remain missing until training-only preprocessing. No source-value distribution or target agreement has been inspected while choosing these rules.

## Guarded loading and features

The timestamp audit verifies both sources are sorted. The later numeric loader must verify archive hashes, parse only the audited raw-row development prefix and assert every loaded timestamp is earlier than the reserved boundary **before** converting measurement strings to numbers. Reserved numeric values must not enter aggregation, missingness profiling, feature engineering, selection, scale fitting or scoring. Date-field preflight may inspect their timestamps. Raw public archives contain those values; this is a procedural analyst reservation.

Observation delay O is 0 or 24 hours; extra label fitting-use delay L is 0 or 24 hours. For the target value at s, physical arrival is s+1+O. For a forecast origin t, label-use permission is t+7+O+L. L never changes target-feature snapshots or persistence. These are simulated field-specific access contracts, not claims that either provider implements such reporting workflows.

| Feature role | Frozen inputs and legal cutoff |
| --- | --- |
| Target lags | Exact target values at t-(1+O), t-(2+O), t-(3+O), t-(24+O), t-(168+O) |
| Persistence candidate | Latest nonmissing target at or before t-1-O, at most 168 nominal hours behind that cutoff |
| Calendar | Hour, weekday and month sine/cosine for target hour t+6 |
| Traffic covariates | temp, rain_1h, snow_1h, clouds_all, weather_main at exactly t-1 after frozen consolidation |
| Household covariates | Hourly mean Global_reactive_power and Voltage at exactly t-1; each requires 60 finite minute readings independently of target completeness |

Covariates are hypothetically available after their hour completes, with no extra O or L delay, consistent with the original experiment's feature-role convention. Household auxiliary channels are independently named quantities, but they are measured in the same installation; simulated separate access is not evidence of actual separate provider release. Exclude traffic holiday/weather_description and household Global_intensity/Sub_metering_1/2/3; add no unlisted features or target transforms. The covariate lists are source-adapted and fixed before outcomes, so between-source comparisons do not isolate the effect of a shared identical feature vector. All four settings within a source use the same ledger.

## Fixed dates and eligibility

The exact time partitions are frozen in TIMESTAMP_PREFLIGHT.json and follow the inherited elapsed-clock-span 50/60/70/80% cutpoints rounded upward to the hour.

| Source | Period | A: inner boundary | B: deployment cutoff | C: future endpoint |
| --- | --- | --- | --- | --- |
| Traffic | T1 | 2015-10-02 05:00 | 2016-05-08 04:00 | 2016-12-13 03:00 |
| Traffic | T2 | 2016-05-08 04:00 | 2016-12-13 03:00 | 2017-07-20 02:00 |
| Household | T1 | 2008-12-06 08:00 | 2009-04-29 11:00 | 2009-09-20 13:00 |
| Household | T2 | 2009-04-29 11:00 | 2009-09-20 13:00 | 2010-02-11 16:00 |

Traffic's final region begins 2017-07-20 02:00 and ends 2018-10-01 00:00 exclusive. Household's final region begins 2010-02-11 16:00 and ends 2010-11-26 21:00 exclusive. Keep both new final regions and the old sources' final regions unused in the development run.

Use the common eligibility intersection of finite exact-time targets and finite persistence at both O=0 and O=24, for all historical and future origins. A forecast origin need not itself have a source observation. There must be at least 500 inner training origins, 100 inner validation origins, 100 future origins and two distinct training target values for each selector. Missingness or conflicting traffic duplicates may reduce the timestamp-only potential counts. Record each infeasible case without moving boundaries, selecting another station/household, weakening completeness rules or dropping a disappointing source.

## Selectors, models and outcomes

Reuse the seven selectors: chronological, earlier_validation, random_42, random_43, random_44, random_45 and random_46. Chronological train origins are before A with labels usable by A; validation origins are [A,B) with labels usable by B. Every other selector partitions the exact union with identical train/validation counts. Earlier validation uses the first n_validation origins of that sorted union; its training set uses the rest. Random uses numpy.default_rng(seed).permutation of the original chronological train-then-validation union. Random and earlier-validation comparisons are retrospective, not causal origin-by-origin online training replays.

Select by inner MAE, with tie order persistence, Ridge, RF, HGB. Freeze the original settings: Ridge alpha=1, solver=lsqr, tol=1e-6, max_iter=10000; RF 100 trees, min_samples_leaf=5, max_features=1.0, bootstrap=True, random_state=42, n_jobs=1; HGB squared_error, learning_rate=.05, max_iter=100, max_leaf_nodes=15, l2_regularization=.1, early_stopping=False, random_state=42. Numeric median imputation with missing indicators, keep-empty-features and standard scaling; categorical missing-category imputation and dense unknown-safe one-hot encoding. Every preprocessing fit sees its assigned training rows only. No hyperparameter search, clipping, log transform, model-initialization seed change or cache borrowing.

Lock all seven choices before future evaluation. Fit each non-persistence candidate once on the common eligible history before B with labels usable by B, then predict the common future [B,C) while keeping complete target hours inside C. Features can use legally arriving observations within that block. The normalization scale is historical-target IQR using maximum O=24,L=24 maturity (t+55<=B), common across the four settings in each source-period. Zero IQR leaves normalized results undefined and raw MAE reportable.

Let R be common-refit selected MAE minus the fixed-menu best future MAE, divided by the scale. Let Δ_r(O,L)=R_chron-R_random,r. The primary contrast is C_r=Δ_r(24,0)-Δ_r(0,24). Verify the primary pair has identical label maturity, fitting-origin memberships and future origins; features differ. This is an availability-system contrast, not an isolated causal feature-staleness effect.

Secondary contrasts remain measurement Δ(24,0)-Δ(0,0), fitting use Δ(0,24)-Δ(0,0), factorial [Δ(24,24)-Δ(24,0)]-[Δ(0,24)-Δ(0,0)] and earlier-validation regret versus chronological/random. Save every seed and every setting. Report each of the four new source-period units separately, with descriptive five-seed mean/range. Do not pool p-values or confidence intervals across dependent settings, periods or seeds; do not promote a secondary result if the primary ties. A fixed-menu future oracle is diagnostic, not deployable.

If all 16 new settings are feasible, the execution stage is 384 new fits, with 448 inner-candidate, 64 future-candidate, 112 selected-procedure, 80 setting-seed-difference and 20 primary-contrast rows. The present preflight fits **zero** models. Its timestamp counts are potential counts, not confirmed numerical feasibility.

## Export reliability and progression

Use audit_exports.write_union_csv_gz for static snapshots and maturity exports: concatenate a union schema across sources, write one closed gzip stream, verify header/row counts and compressed integrity, then atomically replace the output. Do not append heterogeneous source schemas under one header. Preserve all old results and the old repair evidence unchanged. The new writer and preparation adapters have synthetic tests, including a poisoned reserved target and conflicting duplicate values.

Before executing on numeric values, freeze the actual expansion runner's byte hashes alongside this source protocol, source hashes and preflight. Add inherited timing/preprocessing checks and completed-output reconstruction checks. Do not run the old pilot main on the new archives. During execution report numerical feasibility, missingness and duplicate agreement without changing these rules. All claims and exclusions must be retained. Wider source coverage can strengthen a scoped replication-and-extension contribution; it does not establish a new algorithm, universal superiority or guaranteed acceptance.
