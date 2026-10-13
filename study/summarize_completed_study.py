"""Report every final result alongside the fixed development interpretation."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'final_results'
KEY=['dataset','period','O','L']
NAMES=['bike','beijing','traffic','household']
def read(name):return pd.read_csv(OUT/name,float_precision='round_trip')
def nice(value):return 'NA' if pd.isna(value) else f'{value:.6f}'
def table(frame):
    lines=['| '+' | '.join(map(str,frame.columns))+' |','| '+' | '.join(['---']*len(frame.columns))+' |']
    lines += ['| '+' | '.join(map(str,row))+' |' for row in frame.itertuples(index=False,name=None)]
    return '\n'.join(lines)

def main():
    manifest=json.loads((OUT/'run_manifest.json').read_text());assert manifest['status']=='complete'
    validation=json.loads((ROOT/'VALIDATION_RESULTS.json').read_text());assert validation['checks_failed']==0
    contrasts=read('primary_and_secondary_contrasts.csv');differences=read('selection_differences.csv')
    selected=read('selected_procedure_metrics.csv');candidate=read('candidate_metrics.csv');cases=read('case_audit.csv')
    development=pd.read_csv(ROOT/'development_results/combined_primary_summary.csv',float_precision='round_trip')
    summaries=[]
    for name in NAMES:
        g=contrasts[contrasts.dataset==name];row=dict(dataset=name,seed_n=len(g))
        for col in ['primary_C','measurement_effect','fitting_use_effect','factorial_interaction']:
            for agg in ['mean','min','max']:row[col+'_'+agg]=getattr(g[col],agg)()
        summaries.append(row)
    summary=pd.DataFrame(summaries);summary.to_csv(OUT/'contrast_summary.csv',index=False)
    setting=[]
    for key,g in selected.groupby(KEY,sort=False):
        s=g.set_index('strategy');ch=s.loc['chronological'];early=s.loc['earlier_validation'];random=s.loc[[f'random_{seed}' for seed in range(42,47)]]
        d=differences[(differences.dataset==key[0])&(differences.O==key[2])&(differences.L==key[3])]
        setting.append(dict(dataset=key[0],O=key[2],L=key[3],chronological_model=ch.selected_model,
            random_models='; '.join(f'{seed}:{s.loc[f"random_{seed}","selected_model"]}' for seed in range(42,47)),
            earlier_validation_model=early.selected_model,chronological_mae=ch.future_mae,random_mae_mean=random.future_mae.mean(),
            random_mae_min=random.future_mae.min(),random_mae_max=random.future_mae.max(),earlier_validation_mae=early.future_mae,
            delta_mean=d.delta_chron_minus_random.mean(),delta_min=d.delta_chron_minus_random.min(),delta_max=d.delta_chron_minus_random.max(),
            same_choice_n=int(d.same_choice.sum()),earlier_minus_random_mean=d.earlier_minus_random.mean(),earlier_minus_chron=float(d.earlier_minus_chron.iloc[0])))
    setting=pd.DataFrame(setting);setting.to_csv(OUT/'setting_summary.csv',index=False)
    primary=pd.DataFrame([{'Source':r.dataset,'Primary mean':nice(r.primary_C_mean),'Seed minimum':nice(r.primary_C_min),'Seed maximum':nice(r.primary_C_max)} for r in summary.itertuples()])
    secondary=pd.DataFrame([{'Source':r.dataset,**{label:f'{nice(getattr(r,col+"_mean"))} [{nice(getattr(r,col+"_min"))}, {nice(getattr(r,col+"_max"))}]' for label,col in [('Measurement','measurement_effect'),('Fitting use','fitting_use_effect'),('Factorial','factorial_interaction')]}} for r in summary.itertuples()])
    selectors=pd.DataFrame([{'Source':r.dataset,'O,L':f'{r.O},{r.L}','Chron model':r.chronological_model,'Random models':r.random_models,'Earlier model':r.earlier_validation_model,
        'Chron MAE':nice(r.chronological_mae),'Random MAE mean [min,max]':f'{nice(r.random_mae_mean)} [{nice(r.random_mae_min)}, {nice(r.random_mae_max)}]',
        'Earlier MAE':nice(r.earlier_validation_mae),'Δ mean [min,max]':f'{nice(r.delta_mean)} [{nice(r.delta_min)}, {nice(r.delta_max)}]'} for r in setting.itertuples()])
    native=candidate.pivot(index=['dataset','O','L'],columns='model',values='mae').reset_index();native.columns.name=None
    for col in ['persistence','Ridge','RF','HGB']:native[col]=native[col].map(nice)
    early=pd.DataFrame([{'Source':r.dataset,'O,L':f'{r.O},{r.L}','Earlier − random':nice(r.earlier_minus_random_mean),'Earlier − chron':nice(r.earlier_minus_chron)} for r in setting.itertuples()])
    audit=json.loads((OUT/'dataset_audit.json').read_text());history=json.loads((OUT/'PRE_RELEASE_HISTORY_AUDIT.json').read_text())
    eligibility=pd.DataFrame([{'Source':name,'Final eligible origins':int(cases[cases.dataset==name].future_n.iloc[0]),'Reserved finite hourly targets':next(a for a in audit if a['dataset']==name)['reserved_hourly_target_finite'],
        'Reserved missing hourly targets':next(a for a in audit if a['dataset']==name)['reserved_hourly_target_missing'],'Historical IQR':nice(history['historical_iqr'][name])} for name in NAMES])
    fig,axes=plt.subplots(1,2,figsize=(12,5.7),gridspec_kw={'width_ratios':[1.25,1]})
    for ax,values,labels,title in [(axes[0],development.primary_C_mean.to_numpy(),[f'{r.dataset.title()} {r.period}' for r in development.itertuples()],'Eight development source-period units'),
        (axes[1],summary.primary_C_mean.to_numpy(),[name.title() for name in NAMES],'Four reserved final source units')]:
        positions=np.arange(len(values));colors=['#cb7734' if v>0 else '#34799b' if v<0 else '#8d959f' for v in values]
        ax.barh(positions,values,color=colors,height=.56);ax.scatter(values,positions,c=colors,s=28,zorder=3)
        ax.set_yticks(positions,labels);ax.invert_yaxis();ax.axvline(0,color='#555',lw=.8)
        ax.set_title(title,fontsize=11);ax.set_xlabel('Primary C = Δ(24,0) − Δ(0,24)',fontsize=10)
        ax.spines[['top','right']].set_visible(False)
        bound=max(.0001,float(np.max(np.abs(values)))*.20)
        ax.set_xlim(min(0,float(np.min(values)))-bound,max(0,float(np.max(values)))+bound)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
        ax.tick_params(axis='x',labelsize=9)
        ax.grid(axis='x',alpha=.15)
    fig.suptitle('Availability-system contrast · separate descriptive units · no pooled inference',fontsize=11)
    fig.tight_layout();fig.savefig(OUT/'development_and_final_contrasts.png',dpi=180,bbox_inches='tight');plt.close(fig)
    directions='; '.join(f'{r.dataset}: '+('positive' if r.primary_C_mean>0 else 'negative' if r.primary_C_mean<0 else 'zero') for r in summary.itertuples())
    zeros=[r.dataset for r in summary.itertuples() if r.primary_C_min==0 and r.primary_C_max==0]
    beijing=setting[setting.dataset=='beijing'];favors_chron=int((beijing.delta_mean<0).sum());favors_random=int((beijing.delta_mean>0).sum())
    report=f'''# Completed availability study: development completion and reserved final results

## Outcome in easy words

The missing baseline is finished and the reserved final evaluation ran once. This turn completed **24 baseline fits plus {manifest['new_model_fits']} final refits**, with no selection refresh or tuning. The expansion now has all sixteen cases and 384 evidence-backed completed fits. Across the earlier and expanded development studies, four series contribute eight related source-period units. The final evaluation adds one terminal-window unit per series. **{validation['checks_passed']} final package checks passed; {validation['checks_failed']} failed.**

The final primary directions are **{directions}**. The zero sources are {', '.join(zeros)}. In these sources the carried-forward chronological and random selectors all chose RF in both primary settings, so their equal future errors and zero contrast follow from sharing the same refit. This does not prove that validation errors, selectors or availability systems are generally equivalent.

Beijing is the final source whose carried-forward chronological and random choices differ: chronological uses HGB and random uses RF. Its native future comparison favors chronological in {favors_chron} timing settings and random in {favors_random}; any remaining settings tie. The exact scores and availability contrast are retained below. There is no basis for universal chronological superiority, statistical equivalence, a new forecasting algorithm or guaranteed publication.

## Final primary result

{table(primary)}

Let R=(selected final MAE−fixed-menu best final MAE)/historical target IQR, and Δ=R_chron−R_random. Primary C=Δ(24,0)−Δ(0,24). Positive C means the chronological-minus-random gap is larger under physical observation delay than under an equally long extra fitting-use restriction; negative C means smaller. Both primary settings have identical t+31 label maturity, legal historical training membership and final origins. Features differ. This compares whole availability systems, not an isolated causal effect of feature age.

All five split seeds are retained and summarized by mean/min/max. They share data and future candidate refits; collapsed ranges indicate identical carried-forward choices here, not independent replication. No pooled p-value or confidence interval is reported. Four heterogeneous series and related development periods provide limited coverage.

![Separate development and final contrasts](final_results/development_and_final_contrasts.png)

The panels preserve the eight development units and four final units separately. The different horizontal scales aid reading and do not imply comparable uncertainty or independent repeated cohorts. Full-precision results are in the CSV files.

## Final eligibility and normalization

{table(eligibility)}

Every source-setting passed the frozen 500-history/100-final-origin and target-diversity gates. Final eligibility requires finite exact six-hour targets and finite persistence under both O values, with complete target hours ending before or at the original endpoint. The common historical IQR was computed before opening final measurements from development labels mature under the maximum t+55 restriction. Final outcomes never determine that scale.

## Every final selector and setting

Native MAE units are rental counts for Bike, µg/m³ for Beijing PM2.5, vehicles/hour for traffic, and mean kW for household power. Compare native errors within each source. A positive Δ favors random selection; a negative Δ favors chronological selection. Random means/ranges summarize five selectors sharing the same candidate refits, not five independently refitted future models.

{table(selectors)}

## Every fixed-menu candidate

{table(native)}

The best final candidate is a retrospective menu oracle used only for diagnostic regret. It is not a deployable choice made with final outcomes. Every candidate prediction, including unselected candidates, is retained. Numeric/categorical preprocessing and Ridge/RF/HGB hyperparameters remain unchanged.

## Declared secondary comparisons

Entries are mean [minimum, maximum] over five seeds. Measurement=Δ(24,0)−Δ(0,0), fitting use=Δ(0,24)−Δ(0,0), factorial=[Δ(24,24)−Δ(24,0)]−[Δ(0,24)−Δ(0,0)]. These remain secondary irrespective of the primary result.

{table(secondary)}

Earlier-validation comparisons, also secondary:

{table(early)}

## What was frozen and tested

The final plan was frozen after baseline validation and combined development interpretation, before numeric reserved measurements were inspected. All seven original T2 inner-only choices per source-setting were carried forward; FINAL_CHOICES.json retains candidate scores and original timestamps. They were re-locked before the release. No newly refreshed inner split or choice was fitted for this final test. The missing T1 baseline does not alter those T2 choices.

Deployment B is the original reserved boundary and C the original exclusive endpoint. Common candidate refits use all legal history before B, including additional development history after the earlier T2 deployment. This tests fixed selections transferring to a later deployment, not a refreshed validation-policy comparison or online adaptive learner. Fixed models predict the terminal block while legally arriving observations may update their feature vectors. Learner label arrays are NaN except at legal pre-B training rows.

Target observations for hour s arrive at s+1+O; learner fitting permission for origin-t labels is t+7+O+L. L changes label use only. Target lags and persistence stop at t−1−O; auxiliary covariates use t−1 under the inherited hypothetical completion rule. Recorded nominal time, DST ambiguity and missing actual release history remain limitations. Traffic duplicates follow exact consensus; household targets require sixty finite complete minute values and are averaged in kW. Partial endpoint hours are excluded by clock structure.

The release gate verifies protocol, code, choice, development and source hashes. An atomic once-only marker precedes the first numeric final load. The worker execution completed successfully with exactly {manifest['new_model_fits']} fits, {manifest['feasible_cases']} feasible settings and {manifest['infeasible_cases']} infeasible settings, in {manifest['elapsed_seconds']/60:.1f} minutes. No cached or additional inner fits were used. Reserved data is now used for this final evaluation; it must not be described as still untouched or reused to select another favorable plan.

Independent checks reconstructed raw reserved targets/aggregation, as-of features, persistence sources, every physical/permission clock, all training/final memberships, historical scales, candidate scores, inner-only choices, selected metrics and declared contrast algebra. They checked exactly shared primary memberships, common final origins, lock/release/fit ordering, source integrity, and schema-union single-stream gzip integrity. The inherited checks also verify training-only preprocessing. Validation logs and hashes preserve the evidence.

## Development completion and research claim

The additional baseline passed thirteen independent completed-case checks. Its seven selectors chose RF, so the existing four expansion primary contrasts remain unchanged, while all expansion baseline-dependent secondary values are now available. The completed development interpretation is DEVELOPMENT_FINDINGS.md. Earlier source studies remain exploratory; the new preparation was frozen before inspecting its development targets. This is not formal preregistration and public held-out historical regions are not newly collected external cohorts.

The supported scope is an auditable, limited comparison of fixed-menu model selection under separately defined observation and label-use availability. The results do not establish a general advantage for chronological validation. High rates of identical candidate choice constrain the primary diagnostic's sensitivity. Any manuscript should retain those null results, source/clock limits, the carried-forward final-choice definition and the failure/completion accounting. Novelty must still be checked against the existing literature before a publication claim.

The older saved packages remain unchanged. Previous expansion execution completed 360 fits with at most twenty-one interrupted inner jobs; this authorized completion adds twenty-four, giving 384 complete expansion fits and at most 405 expansion attempts. The final evaluation adds 48 separately authorized refits. Interrupted outputs are not counted as complete evidence. The older pilot is separate from these accounting totals.

## Files and reproduction

Start with README.md for exact commands. FINAL_PROTOCOL.md, FINAL_PLAN.json, FINAL_CHOICES.json and FINAL_FREEZE.json preserve the prescoring design. FINAL_EVALUATION_STARTED.json records the single execution. final_results contains all scores, predictions, feature/maturity records, membership, scales, audit files and fit timestamps. baseline_results and development_results retain the missing-case evidence and completed merge; development_reference identifies and preserves the original score/choice inputs. Raw official source archives and their attribution are included.

The completed output checker targets the bundled directories and performs no fitting or adaptive final selection. The once-only marker blocks another final execution in this workspace. Explicit reproduction in a separate copy requires removing that copy's final_results and marker while keeping the original evidence and freeze intact, then executing the same frozen runner; this is a replay, not a new uninspected final test. Trained weights are not distributed; deterministic pipelines, source bytes, splits and predictions are retained. Redundant compressed checkpoints are omitted after combined exports validate. The package checksum list verifies every included file.
'''
    (ROOT/'COMPLETED_STUDY_REPORT.md').write_text(report,encoding='utf-8')
    print(primary.to_string(index=False));print(setting[['dataset','O','L','chronological_model','random_models','delta_mean']].to_string(index=False))

if __name__=='__main__':main()
