# Availability-delay extension: protocol v0.1

Fixed on 11 October 2026 before downloading these source archives or inspecting
their target values. This is a protocol for a bounded exploratory extension,
not a registered study, a completed experiment or a claim of established novelty.
The bank pilot motivated the question; it is excluded from new confirmation data.

## Research question and scope

**In six-hour-ahead forecasting, does simulated target-reporting delay change which
historical validation procedure chooses a better model for a common future block?**

The delay simultaneously makes recent target measurements unavailable as predictors
and makes recent training outcomes immature. These are jointly simulated operational
effects; this study does not identify their separate causal contributions or measure
actual reporting delays at either provider. The raw sources have observation clocks,
not transaction logs documenting real arrival times or later revisions.

We use regression so original numeric outcomes remain intact, rather than inventing
binary classes or selecting a threshold after seeing their distributions. Algorithms
are familiar fixed baselines. No new neural architecture or adaptive weighting rule
is proposed. The possible contribution is a small auditable replication-and-extension
experiment; publishable novelty remains unresolved after the current search.

## Fixed data and targets

| Dataset | Series | Target | Selection rule |
| --- | --- | --- | --- |
| UCI Bike Sharing, DOI 10.24432/C5W894 | Hourly aggregate system | `cnt` for the hour beginning at origin + 6 hours | Use official `hour.csv`; no station search |
| UCI Beijing Multi-Site Air Quality, DOI 10.24432/C5RK5G | Aotizhongxin site | `PM2.5` for the hour beginning at origin + 6 hours | Site fixed before outcome inspection; do not choose by model scores |

These represent two independently sourced datasets and two application types.
One Beijing site is one series, not 12 independent confirmations. The two air-quality
and demand tasks cannot justify universal statements about finance or classification.

Sort by the provider's nominal hourly timestamps. Reject duplicates or malformed
times rather than resolving them using outcome values. Infer no time zone or DST
correction. All horizons denote six nominal clock hours. Provider alignment and
revision uncertainties limit claims about exact real-world elapsed time and arrival.
Timestamp preflight may inspect date fields, station identity, header structure,
counts and missing clock hours, but must not profile any target column.

Keep an hourly grid. Missing future targets remain missing; never fill labels or
use the sixth next row instead of the hour exactly six hours later. No interpolation
using later observations. Sort and join within the same series only.

## Availability scenarios and feature ledger

Primary comparison: reporting delays **D=0 and D=24 hours**. D=6 is a fixed secondary
sensitivity. Treat a record tagged hour s as a measurement for an hour that completes
at s+1. This is a conservative modeling convention, not verified provider timing.

The target measurement becomes available at s+1+D. At origin t, its latest legal
timestamp is t−1−D. The forecast label for origin t matures at t+6+1+D. If one raw
target value is both a predictor and a label, the same availability rule applies
to both roles: do not delay labels while allowing their identical underlying values
through current-target features.

| Inputs | As-of rule |
| --- | --- |
| Target-history lags | Exact timestamps t−(1+D), t−(2+D), t−(3+D), t−(24+D), t−(168+D) |
| Persistence candidate | Latest observed target at/before t−1−D, at most 168 hours earlier than that legal cutoff |
| Calendar | Sine/cosine of hour, weekday and month for the target hour; known from the clock |
| Bike observations | `temp`, `hum`, `windspeed`, `weathersit` at exactly t−1; hypothetical one-hour completion, no extra reporting delay |
| Beijing observations | `TEMP`, `PRES`, `DEWP`, `RAIN`, `wd`, `WSPM` at exactly t−1 under the same hypothetical completion rule |

Exclude future measured weather, concurrent target components `casual`/`registered`,
row IDs, station pooling, and every unlisted feature. No whole-file normalization
learned from outcomes. Bike weather values arrive already transformed by the source;
we do not claim those source transformations were estimated on a training prefix.
Missing feature values stay missing until train-only imputation. No centered rolling
statistics, future-filled values or label-derived calendars.

## Time partitions and equal budgets

Use only timestamp metadata to define S = first timestamp and E = last timestamp +
one hour. Round each fractional elapsed-span boundary upward to the next nominal
hour. These are time fractions, not row or target-value quantiles.

| Period | Inner boundary A | History cutoff B | Future endpoint C |
| --- | ---: | ---: | ---: |
| Development T1 | 50% | 60% | 70% |
| Development T2 | 60% | 70% | 80% |
| Reserved final region | — | 80% | 100% |

Preflight records exact dates before outcome analysis. For a delay D:

1. Chronological inner train: origins before A whose complete labels are available
   at or before A. Inner validation: origins in [A,B) whose labels mature by B.
2. Random inner comparison: randomly partition the union of those exact two eligible
   sets, seed 42, preserving their exact train and validation counts. One random
   split and one chronological split per model, with no stratification.
3. Refit all fitted candidates on the identical complete historical pool before B,
   including only labels available by B. Inner-boundary exclusions are reintroduced
   for this common refit when they have matured. Lock each selector's model before
   future scores are calculated.
4. Predict the identical origins in [B,C) with the complete target hour ending by C.
   Use only measurements available at each prediction origin. Models remain fixed
   throughout that block; legally arriving past measurements may update features.

Random validation is a retrospective interpolation comparator; it may mix historical
times within B. It is not described as a causal replay of training at every validation
origin. Equal counts/fits do not erase the inherent difference in temporal training
composition. Both methods have the same final-history exposure and future records.

For comparisons across delay scenarios, use the intersection of evaluation origins
with observed true targets and available persistence inputs for all three D values.
This mask is computed once according to the declared rule, never from predictions.
Save counts and source indices. Future-label missingness is used only for evaluation,
and means findings are conditional on observed labels. Do not remove difficult cases
after seeing scores. Final-region target columns do not enter development loading,
feature engineering, selection, eligibility or evaluation.

## Fixed candidates and preprocessing

Selectable menu and tie order: persistence, Ridge, Random Forest, histogram gradient
boosting. Persistence is selectable to avoid assuming fitted models beat a simple
forecast. No clipping, log-target transform, weights or hyperparameter search.

- Ridge: alpha=1, solver=lsqr, tol=1e-6, max_iter=10000.
- RF regressor: 100 trees, min_samples_leaf=5, max_features=1.0, bootstrap=True,
  random_state=42, n_jobs=1.
- HistGradientBoostingRegressor: squared_error loss, learning_rate=.05,
  max_iter=100, max_leaf_nodes=15, l2_regularization=.1, early_stopping=False,
  random_state=42.

For all fitted models: numeric median imputation with missingness indicators and
keep-empty-features enabled; standard scaling; categorical missing category and
dense one-hot encoding with unknown-category handling. Fit every preprocessing
operation on the corresponding training set only. Stop on nonconvergence rather
than silently dropping a candidate. Record exact Python/library versions and hashes.

If all combinations are feasible: 2 datasets × 2 periods × 3 delays × 3 fitted
models × (2 inner fits + 1 common-history fit) = **108 new fits**. There are 96 inner
candidate evaluations and 48 future-candidate evaluations, including persistence;
24 selected-procedure records and 12 paired case-period-delay comparisons.
These are dependent evaluations, not independent sample counts for inference.

## Metrics, estimand and hypotheses

Select by inner mean absolute error (MAE), lower is better. For each future block,
save MAE, RMSE, chosen candidate, all candidate scores and aligned predictions.

Define a scale using the IQR of observed historical labels that have matured by B
under the maximum delay D=24, common to all D scenarios. No future statistics enter
that scale. Report normalized MAE = MAE/IQR. If IQR is zero, keep raw MAE and mark
the normalized comparison undefined; never choose another normalizer after seeing
results. For the fixed menu, retrospective selection regret is selected normalized
MAE minus the lowest normalized MAE among its common-history future candidates.
The future oracle is a diagnostic, never a deployable selector.

Primary within-dataset/period estimand:

Δ(D) = regret_chronological(D) − regret_random(D).

Negative Δ favors chronological selection. The primary delay interaction is
Δ(24) − Δ(0), with every dataset and period reported separately. D=6 is secondary.
The baseline hypotheses are descriptive and nondirectional: model choice or regret
may change with availability; neither selector is assumed to win. Same choices
produce zero difference but do not establish general equivalence. Do not pool a
p-value across 12 dependent cases or select the best-looking period as the claim.

## Eligibility, failures and progression

For each scenario require at least 500 inner training rows, 100 inner validation
rows, 100 future evaluation rows and at least two distinct historical target values.
These are feasibility gates, not performance filters. Insufficient cases stay in
the report as infeasible; do not silently move cutpoints, swap sites, impute labels,
increase delay levels, or replace a disappointing dataset.

This stage's deliverable is the protocol, metadata-only feasibility report and tested
replay mechanics. No empirical forecasting score is produced here. The next execution
stage should implement the full candidate fitting/evaluation runner and validate
as-of snapshots, label maturity, choices and alignment before its bounded development
run. Report all development outcomes before deciding whether to invest in a larger
study. Novelty and generalizability need additional independent datasets and a wider
audit; a larger number of fits is not itself a contribution.

Reserve the final 20% within each source. A later same-source test is an internal
temporal holdout, not a new external sample. Public benchmark labels are downloadable;
we can claim no analyst inspection by this workflow, not technical access control or
absolute independence from all existing published results. Any protocol revision must
be dated, explained and frozen before further outcome inspection.
