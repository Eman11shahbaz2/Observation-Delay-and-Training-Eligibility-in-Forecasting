# Frozen final evaluation: carried-forward selectors

12 October 2026, Asia/Karachi. Final protocol fixed after completed development interpretation and before inspecting any numeric reserved measurements. The user authorized this evaluation once. This is an internally frozen historical temporal holdout of public benchmark series, not formal preregistration or a new external cohort.

## Scope, terminal windows and carried-forward choices

Use all four existing source series and the entire originally reserved terminal regions; do not choose sources or subperiods after scoring. Exactly one final unit per source:

| Source | B: final deployment cutoff | C: exclusive evaluation endpoint |
| --- | --- | --- |
| Bike | 2012-08-07 20:00 | 2013-01-01 00:00 |
| Beijing Aotizhongxin | 2016-05-12 20:00 | 2017-03-01 00:00 |
| Traffic ATR 301 | 2017-07-20 02:00 | 2018-10-01 00:00 |
| Household | 2010-02-11 16:00 | 2010-11-26 21:00 |

Carry forward all seven original T2 inner-only model selections for each (O,L) setting: chronological, earlier_validation and random_42–46. FINAL_CHOICES.json retains original inner candidate MAEs and lock times and records a new final lock time. Reconstruct the choice from those inner scores with the unchanged persistence, Ridge, RF, HGB tie order. Do not select using T1/T2 common-future errors, the newly completed baseline result, or any reserved measurements. No selection refresh, tuning, additional candidates, initialization seeds, transformations or feature additions.

This tests the ability of previously chosen candidates to transfer to the later final deployment cutoff. It is not a new comparison of selectors refitted with freshly expanded inner validation windows, and is not an online adaptive learner. The additional history between the T2 deployment and final B is available to the common refit only. The narrow development claim in DEVELOPMENT_FINDINGS.md remains fixed irrespective of final results.

## Preparation and legal data access

Preserve inherited Bike/Beijing parsing, target units and covariates, and the frozen traffic consensus / household sixty-minute complete-mean rules. Traffic target is vehicles/hour and household target is average kW. No target interpolation, duplicate summation or incomplete-minute averaging. Exclude household partial first/last hours by their timestamp-defined endpoints before numeric conversion. Preserve nominal clock conventions without invented timezone/DST corrections. Source archives and selected source series are identified by unchanged metadata hashes.

The horizon is the hour [t+6,t+7). O∈{0,24} delays physical target observations to s+1+O; L∈{0,24} adds only label fitting-use permission, t+7+O+L. Target lags and persistence use t−1−O or earlier; target lags are 1,2,3,24,168 plus O. Persistence's maximum source gap remains 168 hours. Auxiliary recorded covariates use t−1 under the same hypothetical completion contract. Calendar features refer to the target hour. Actual provider reporting history is unavailable.

Before opening final measurements, reconstruct each source's guarded development prefix. Fix each setting's training origins with finite exact targets and finite persistence under both O values, t<B, and t+7+O+L≤B. Require at least 500 training origins and two distinct training target values. Compute the common source scale from development labels with t+55≤B using their target IQR. Save train counts and scales in PRE_RELEASE_HISTORY_AUDIT.json before final loading. Zero IQR leaves normalized values NA and native MAE reportable.

After the release freeze, load all declared numeric measurements to construct legally timed features and score the final region. Require the full source's pre-B feature snapshots and training labels to exactly match guarded development reconstruction. Models fit only the declared training origin rows; the label array supplied to each learner contains NaN everywhere except its legal training rows. Every preprocessing statistic is fitted only on these rows. A fixed fitted model may use observations arriving legally during the final interval through its as-of-origin feature vectors. There is no refitting or model-choice update during that interval.

Define final eligibility identically for all settings: finite exact t+6 target and finite persistence under O=0 and O=24, B≤t<C and t+7≤C. Require 100 final origins. Outcome missingness may be observed after release solely to apply these frozen rules. Retain all infeasible cases; do not relax rules, move boundaries, substitute sources or drop poor results. Complete target hours stay inside C. Retrospective evaluation may access their truth after physical arrival and permission time; the evaluator's truth does not enter fitting.

## Fits, outcomes and analysis

Fit each of Ridge, RF and HGB once per feasible source-setting on its common historical training pool. All seven carried-forward selectors share those predictions, together with persistence. Maximum budget is 4 sources ×4 settings ×3 fitted candidates = **48 new final refits**; no additional inner fits. Hyperparameters, seed 42 and preprocessing remain unchanged. Use three one-thread worker processes. Save every fitted candidate's predictions and native MAE/RMSE, historical IQR normalization, fit ledger and selected-procedure metrics. Check final O0,L24 and O24,L0 membership equality exactly and common final origin equality across all four settings.

Selection regret R=(selected final MAE−best fixed-menu final MAE)/historical IQR. The future menu oracle remains retrospective, not deployable. Let Δ_r=R_chron−R_random,r. Primary C_r=Δ_r(24,0)−Δ_r(0,24), retaining all five seeds separately. Positive C means the chronological-minus-random gap is larger under delayed measurements; negative C means smaller. This compares availability systems and is not an isolated causal feature-age effect.

Secondary measurement=Δ(24,0)−Δ(0,0), fitting-use=Δ(0,24)−Δ(0,0), factorial=[Δ(24,24)−Δ(24,0)]−[Δ(0,24)−Δ(0,0)], and earlier-validation versus chronological/random. Report every source/setting/candidate and within-source seed mean/min/max including all zeros. Seeds share candidate refits and data, so they are dependent. Report four source-level final units separately; no pooled p-value, confidence interval or post hoc primary change. Do not promote a secondary finding when primary ties or interpret ties as statistical equivalence.

## Freeze, once-only execution and validation

Before any numeric final loading, freeze this protocol, machine plan, all 112 carried-forward choices, completed development interpretation, baseline validation, source metadata/archive hashes and final execution/adapter/test code. FINAL_FREEZE.json records reserved_numeric_targets_inspected_before_freeze=false as a historical fact. A release gate checks every freeze hash and refuses numeric final loading if absent or changed. FINAL_EVALUATION_STARTED.json is atomically created before the first final load; no automatic second final execution is allowed in this workspace. Reproduction belongs in an explicit separate copy with its own documented replay marker, not adaptive rescoring.

Independent completed-output validation reconstructs reserved preparation, all origin membership, target truth, legality and preprocessing contracts, scales, candidate metrics, original inner-only choices, lock/fit/release ordering, all primary/secondary algebra, and one-stream schema-union gzip integrity. Keep source archives, code, freeze, audit evidence and prior result identities. The older saved packages remain unchanged. Record failures transparently; do not silently rerun or modify the frozen design after observing final scores. Final findings determine the scope of the research claim, not a promise of publication or confirmed novelty.
