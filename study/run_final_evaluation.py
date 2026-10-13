"""One final evaluation of carried-forward T2 choices on four reserved regions."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
import platform
import time
import numpy as np
import pandas as pd
import sklearn
import study_api as f
import replay_core as core
from audit_exports import write_union_csv_gz
from run_full_experiment import SETTINGS,derive_comparisons

ROOT=Path(__file__).resolve().parent
def utc():return datetime.now(timezone.utc).isoformat()
def worker(model,x,y,train,evaluation):
    start=utc();pred,seconds=f.fit_predict(model,x,y,train,evaluation)
    return pred,seconds,start,utc()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'final_results')
    parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args();out=args.output.resolve()
    if args.workers<1:raise ValueError('Positive worker count required.')
    freeze=f.verify_release(ROOT)
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('Final output must be empty; do not repeat a scored final evaluation.')
    marker=ROOT/'FINAL_EVALUATION_STARTED.json'
    with marker.open('x') as stream:
        json.dump(dict(started_utc=utc(),output=str(out),freeze_sha256=f.sha(ROOT/'FINAL_FREEZE.json')),stream,indent=2)
    plan=json.loads((ROOT/'FINAL_PLAN.json').read_text());choices=json.loads((ROOT/'FINAL_CHOICES.json').read_text())
    manifest=dict(status='running',created_utc=utc(),expected_maximum_fits=48,new_model_fits=0,cached_model_fits=0,
        final_numeric_release_authorized=True,final_windows_scored=False,selection_refresh_fits=0,
        selection_origin='carried-forward locked T2 inner choices; no reserved-outcome selection',
        versions=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,sklearn=sklearn.__version__))
    def save():(out/'run_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    save();started=time.perf_counter();count=0
    metrics=[];selected=[];ledger=[];cases=[];audits=[];snapshots=[];maturities=[];memberships=[];scales=[];prediction_paths=[];exports={}
    (out/'checkpoints').mkdir()
    try:
        # Historical fitting/normalization is reconstructed before opening any final targets.
        historical={}
        for name in f.NAMES:
            dev,audit=f.load_development(name,ROOT);index=dev.index
            y=core.exact_targets(dev[f.CONFIG[name]['target']],index).to_numpy(dtype=float)
            prepared={o:f.build_features(dev,name,o) for o in (0,24)}
            valid=np.isfinite(y)&np.isfinite(prepared[0][1])&np.isfinite(prepared[24][1])
            b=pd.Timestamp(plan['datasets'][name]['reserved_start'])
            scale_ids=np.flatnonzero(valid&(index+pd.Timedelta(hours=55)<=b))
            q=np.quantile(y[scale_ids],[.25,.75]);scale=float(q[1]-q[0])
            train_ids={(o,l):np.flatnonzero(valid&(index+pd.Timedelta(hours=7+o+l)<=b)) for o,l in SETTINGS}
            np.testing.assert_array_equal(train_ids[0,24],train_ids[24,0])
            historical[name]=(dev,y,prepared,train_ids,scale_ids,scale)
            scales.append(pd.DataFrame(dict(dataset=name,period='FINAL',origin_grid_index=scale_ids,origin=index[scale_ids],y_true=y[scale_ids])))
        (out/'PRE_RELEASE_HISTORY_AUDIT.json').write_text(json.dumps(dict(completed_utc=utc(),reserved_numeric_targets_loaded=0,
            train_counts={name:{f'{o},{l}':len(ids) for (o,l),ids in h[3].items()} for name,h in historical.items()},
            historical_iqr={name:h[5] for name,h in historical.items()}),indent=2)+'\n')
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            for name in f.NAMES:
                frame,audit=f.load_full(name,ROOT,allow_reserved=True);audit['released_utc']=utc();audits.append(audit)
                (out/'dataset_audit.json').write_text(json.dumps(audits,indent=2)+'\n')
                index=frame.index;cfg=f.CONFIG[name];y=core.exact_targets(frame[cfg['target']],index).to_numpy(dtype=float)
                prepared={o:f.build_features(frame,name,o) for o in (0,24)}
                valid=np.isfinite(y)&np.isfinite(prepared[0][1])&np.isfinite(prepared[24][1])
                b,c=[pd.Timestamp(plan['datasets'][name][k]) for k in ['reserved_start','reserved_end_exclusive']]
                evaluation=np.flatnonzero(valid&(index>=b)&(index<c)&(index+pd.Timedelta(hours=7)<=c))
                dev,dev_y,dev_prepared,trains,scale_ids,scale=historical[name]
                for o,(x,p,used) in prepared.items():
                    pd.testing.assert_frame_equal(x.iloc[:len(dev)],dev_prepared[o][0],check_freq=False)
                    snap=x.reset_index(names='origin');snap.insert(0,'dataset',name);snap.insert(1,'O',o)
                    snap['origin_grid_index']=np.arange(len(index));snap['persistence']=p;snap['persistence_source_timestamp']=used;snap['eligible_origin']=valid
                    snapshots.append(snap)
                for o,l in SETTINGS:
                    train=trains[o,l];x,p,used=prepared[o]
                    np.testing.assert_array_equal(y[train],dev_y[train])
                    base=dict(dataset=name,period='FINAL',O=o,L=l)
                    feasible=len(train)>=500 and len(evaluation)>=100 and len(np.unique(dev_y[train]))>=2
                    cases.append(dict(**base,status='feasible' if feasible else 'infeasible',train_n=len(train),future_n=len(evaluation),
                        history_iqr=scale,scale_history_n=len(scale_ids),outer_cut=str(b),future_end=str(c)))
                    pd.DataFrame(cases).to_csv(out/'case_audit.csv',index=False)
                    maturities.append(pd.DataFrame(dict(**base,origin_grid_index=np.arange(len(index)),origin=index,
                        target_hour=index+pd.Timedelta(hours=6),physical_target_arrival=index+pd.Timedelta(hours=7+o),
                        label_usable_at=index+pd.Timedelta(hours=7+o+l),eligible_origin=valid)))
                    if not feasible:continue
                    for role,ids in [('train',train),('evaluation',evaluation)]:
                        memberships.append(pd.DataFrame(dict(**base,role=role,origin_grid_index=ids,origin=index[ids])))
                    # Only legal historical labels enter the learner, even in its array argument.
                    learner_y=np.full(len(index),np.nan);learner_y[train]=dev_y[train]
                    jobs={model:executor.submit(worker,model,x,learner_y,train,evaluation) for model in ('Ridge','RF','HGB')}
                    predictions=[];actual={}
                    for model in f.MODELS:
                        if model=='persistence':prediction=p[evaluation];seconds=0.
                        else:
                            prediction,seconds,start,end=jobs[model].result();count+=1
                            ledger.append(dict(**base,fit_id=count,model=model,train_n=len(train),eval_n=len(evaluation),
                                started_utc=start,completed_utc=end,seconds=seconds,cache_used=False))
                        score=f.evaluate(y[evaluation],prediction,scale);actual[model]=score
                        metrics.append(dict(**base,model=model,train_n=len(train),eval_n=len(evaluation),history_iqr=scale,seconds=seconds,**score))
                        predictions.append(pd.DataFrame(dict(**base,model=model,origin_grid_index=evaluation,origin=index[evaluation],y_true=y[evaluation],prediction=prediction)))
                    oracle=min(row['mae'] for row in actual.values())
                    for choice in choices['choices']:
                        if (choice['dataset'],choice['O'],choice['L'])!=(name,o,l):continue
                        score=actual[choice['selected_model']]
                        selected.append(dict(**base,strategy=choice['strategy'],selected_model=choice['selected_model'],
                            selection_source_period='T2',locked_utc=choices['locked_utc'],history_iqr=scale,
                            future_mae=score['mae'],future_rmse=score['rmse'],future_normalized_mae=score['normalized_mae'],
                            oracle_mae=oracle,normalized_selection_regret=(score['mae']-oracle)/scale if scale>0 else np.nan))
                    path=out/'checkpoints'/f'{name}_O{o}_L{l}_predictions.csv.gz'
                    exports[str(path.relative_to(out))]=write_union_csv_gz(predictions,path);prediction_paths.append(path)
                    for filename,rows in [('candidate_metrics.csv',metrics),('selected_procedure_metrics.csv',selected),('fit_ledger.csv',ledger)]:
                        pd.DataFrame(rows).to_csv(out/filename,index=False)
                    manifest['new_model_fits']=count;save();print(f'{count}/48 final refits complete: {name} O={o} L={l}',flush=True)
        for filename,frames in [('feature_snapshots.csv.gz',snapshots),('maturity_audit.csv.gz',maturities),('split_assignments.csv.gz',memberships),('scale_membership.csv.gz',scales)]:
            exports[filename]=write_union_csv_gz(frames,out/filename)
        exports['predictions.csv.gz']=write_union_csv_gz([pd.read_csv(p,float_precision='round_trip') for p in prediction_paths],out/'predictions.csv.gz')
        (out/'export_audit.json').write_text(json.dumps(exports,indent=2)+'\n')
        difference,contrast=derive_comparisons(pd.DataFrame(selected));difference.to_csv(out/'selection_differences.csv',index=False);contrast.to_csv(out/'primary_and_secondary_contrasts.csv',index=False)
        completed=sum(row['status']=='feasible' for row in cases)
        if count!=3*completed:raise ValueError('Incorrect final fit accounting.')
        manifest.update(status='complete',completed_utc=utc(),new_model_fits=count,feasible_cases=completed,infeasible_cases=len(cases)-completed,
            elapsed_seconds=time.perf_counter()-started,final_windows_scored=True,primary_source_units=contrast.dataset.nunique())
        save();print(json.dumps(manifest,indent=2),flush=True)
    except BaseException as exc:
        manifest.update(status='failed',failed_utc=utc(),error=repr(exc),new_model_fits=count);save();raise

if __name__=='__main__':main()
