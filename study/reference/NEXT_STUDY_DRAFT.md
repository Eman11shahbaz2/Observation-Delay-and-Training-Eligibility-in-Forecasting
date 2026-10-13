# Controlled availability extension: draft v0.2

Dated 11 October 2026, after the 108-fit pilot and this method audit. **Exploratory follow-up draft; not preregistered, not a confirmation protocol, and not yet executed.** The original protocol and its final-window reservation remain intact.

## Question and timing intervention

The pilot varied a physical target-reporting delay, affecting both features and label maturity. This follow-up distinguishes that delay from an additional restriction on fitting access after the number is observed. It cannot identify a “feature-only physical delay” while permitting the same raw target to be observed immediately as a label.

Keep a six-hour point forecast at origin t, with target hour [t+6,t+7). For a target value recorded at hour s:

\[
a(s;O)=s+1+O,\qquad m(t;O,L)=t+7+O+L.
\]

a is physical arrival; m is permission to use that forecast label for fitting or inner scoring. The late fitting interface cannot delay evaluator access after the experiment is complete. Numeric final-region targets remain excluded from this development work.

| Setting | O: measurement arrival delay | L: extra fitting-use delay | Latest target-history timestamp at origin t | Label usable for origin t |
| --- | --- | --- | --- | --- |
| Baseline | 0 h | 0 h | t-1 | t+7 |
| Fitting-use delay only | 0 h | 24 h | t-1 | t+31 |
| Joint measurement delay | 24 h | 0 h | t-25 | t+31 |
| Measurement plus fitting-use delay | 24 h | 24 h | t-25 | t+55 |

O is applied consistently in predictor and label roles. L represents a separate learner interface, scheduled certification or workflow restriction. It is simulated; this study does not establish that either dataset's provider has such a workflow.

## Fixed scope and features

Use the same official Bike hourly aggregate and predetermined Beijing Aotizhongxin station, existing timestamp boundaries T1/T2, and only the already loaded development prefixes. Do not inspect the reserved final 20% region. These sources motivated the design; all new results on them remain exploratory.

Reuse the original feature ledger and preprocessing exactly. Target lags are t-(1+O), t-(2+O), t-(3+O), t-(24+O), t-(168+O). Persistence uses the latest nonmissing raw target at or before t-1-O, no more than 168 hours behind that cutoff. L does not change either feature snapshots or persistence. Calendar features describe the target hour. Recorded weather covariates remain at t-1 under the original hypothetical completion rule. No new target transforms, interactions or hyperparameter search.

Keep the original common historical/future eligibility mask: observed exact-time target and finite persistence under both O values. Individual missing features use training-only imputation. Missing labels are never filled. For each timing setting, require at least 500 inner training origins, 100 inner validation origins, 100 future origins and two distinct historical target values. Report every infeasible case rather than changing dates or series.

## Three selectors, one final refit

For each dataset-period and timing setting, A is the inner boundary, B the deployment cutoff and C the development future endpoint.

1. **Chronological:** train origins before A whose labels satisfy m<=A; validate origins [A,B) with m<=B.
2. **Random:** partition exactly the union of those eligible sets, preserving the chronological training and validation counts. Use split seeds **42, 43, 44, 45, 46**, reporting every seed.
3. **Earlier validation / later training:** sort that same union by origin. Hold its first n_validation origins for validation; train on the remaining n_train origins. All pool labels are usable by B. This is a retrospective historical comparator inspired by Cai & Ye's earlier-validation construction, not an exact reproduction of their deep-learning protocol.

Random and earlier-validation selectors do not replay a model causally trained before each inner validation origin. Their inputs are as-of-origin features, but model fitting can use later history within B. State this difference explicitly. Their total history remains earlier than the common future block.

Each selector chooses the original fixed menu by inner MAE; tie order persistence, Ridge, RF, HGB. Use precisely the original model settings, including RF/HGB seed 42 and early_stopping=False. The five random seeds vary splitting, not model initialization. Fit each candidate once per inner comparison. Inner-fit budgets are equal for an individual selector comparison; five random repeats are a stability analysis, not an equal-total-compute policy contest.

Refit each of the three fitted candidates **once** on all eligible origins before B whose labels satisfy m<=B, including inner-boundary exclusions that have matured. Every selector in the setting shares that refit and future predictions. Lock all seven choices (chronological, earlier-validation and five random) before future scoring. Fixed fitted models forecast [B,C); features may incorporate observations arriving legally during that interval. Complete target hours must end by C.

## Outcomes and declared contrasts

For each setting and selector save inner/future MAE, future RMSE, chosen model, all candidate predictions and split membership. Use the IQR of historical labels usable by B under the maximum restriction O=24,L=24 as a common dataset-period scale. Future values never determine the scale. Zero IQR leaves normalized comparisons undefined and raw MAE reportable.

For each random seed r, define normalized common-refit selection regret as chosen MAE minus fixed-menu best future MAE, divided by the historical scale. Define

\[
\Delta_r(O,L)=R_{chron}(O,L)-R_{random,r}(O,L).
\]

**Primary mechanism contrast**, per dataset-period and seed:

\[
C_r=\Delta_r(24,0)-\Delta_r(0,24).
\]

Both settings make the label usable at t+31 and consequently give identical maturity rules and fitting-origin pools; only the physical observation stream, features and persistence differ. This is a controlled difference between two **availability systems**, not an isolated causal effect of feature staleness alone: changed features can affect fitting, selection and the future oracle.

Secondary contrasts: measurement effect Δ(24,0)-Δ(0,0); extra fitting-use effect Δ(0,24)-Δ(0,0); factorial interaction [Δ(24,24)-Δ(24,0)]-[Δ(0,24)-Δ(0,0)]. Report earlier-validation-minus-random and earlier-validation-minus-chronological regret as secondary comparisons. Nondirectional hypotheses: any contrast or model-choice change may be zero, positive or negative.

Report all four dataset-period units separately, and mean/range across the five split seeds within each unit. No pooled p-values or confidence intervals across these dependent settings, seeds or shared histories. Do not promote a secondary result because the primary contrast ties. Retrospective oracle regret remains a diagnostic of this fixed menu, not a deployable predictor.

## Fit budget and outputs

2 datasets × 2 periods × 4 timing settings × 3 fitted candidates × (1 chronological inner + 1 earlier-validation inner + 5 random inner + 1 common-history refit) = **384 maximum new fits**. Persistence is scored without fitting. The count is a maximum; any cache/reuse must be based on verified equality of inputs, origins, model/preprocessing parameters and seeds, and explicitly logged. Recompute output provenance rather than overwriting or silently borrowing old results.

If all cases are feasible, expect 448 inner candidate score rows (16 settings × 7 selectors/repeats × 4 candidates), 64 future candidate score rows, 112 selected-procedure rows, 80 chronological/random setting-seed differences and 20 primary contrast rows. Those counts do not describe independent evidence.

Produce a new isolated package with the dated finalized protocol, original source hashes, as-of snapshots, maturity audit, all predictions, every choice, fit accounting, full tables and a report explaining ties as well as wins/losses. Preserve the completed pilot package unchanged.

## Validation before fitting

Extend the existing loader and replay tests rather than replacing them. Verify: changing L does not change target-feature snapshots; changing O delays both raw feature arrival and label usability; (24,0) and (0,24) have equal label maturity; unavailable target changes cannot affect snapshots; chronological training is mature at A; every comparator label is usable by B; all selectors and settings share declared future origins; earlier-validation counts and ordering are correct; every selected model was locked before future evaluation; preprocessing sees only its assigned train rows; reserved targets never enter loading; recomputed prediction metrics and contrasts agree.

`availability_contract.py` implements only the new two-clock contract, with synthetic checks. It is not a full runner. Complete metadata/provenance checks and freeze this draft's final implementation decisions before any new outcome inspection. Any revision must be dated, explained and kept alongside this draft.

## Independent-source expansion after this experiment

Candidate additional sources are UCI Metro Interstate Traffic Volume (one I-94 monitoring station, DOI 10.24432/C5X60B) and Individual Household Electric Power Consumption (one Sceaux household, DOI 10.24432/C58K54). Official metadata supports hourly traffic and minute-averaged household power, respectively. No new source targets were downloaded or inspected during this audit.

These are candidates, not declared feasible confirmation datasets. First perform timestamp-only preflight, freeze duplicate handling for traffic, and specify the household target's hourly aggregation and missing-minute rule before outcome analysis. One household is one series; multiple weather rows or electrical channels do not become independent confirmations. Observation-clock/DST and actual arrival-history limits need explicit treatment. Select additional sources using documented feasibility and lineage, never preferred performance.

ElectricityLoadDiagrams20112014 was considered but not selected for the immediate draft: its official description documents DST-specific zero/aggregated observations and a much larger archive. This is a metadata/complexity decision, not a result-based exclusion. The two candidate additions may permit a prospective replication extension, but an internal temporal holdout still is not a newly collected external sample.

Do not use existing reserved final windows until the mechanism analysis and independently frozen expansion design are settled. Evidence from two extra sources would still support a limited scope, not universal superiority or guaranteed publication.
