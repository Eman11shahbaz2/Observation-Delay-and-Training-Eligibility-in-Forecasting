"""Frozen 108-fit reporting-delay development pilot; excludes reserved target rows."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import io
import json
import platform
import time
import warnings
import zipfile
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
import sklearn
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler,OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor,HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
import metadata_preflight as metadata
import replay_core as core

ROOT=Path(__file__).resolve().parent
MODELS=['persistence','Ridge','RF','HGB']
CONFIG={
 'bike':dict(target='cnt',numeric=['temp','hum','windspeed'],categorical=['weathersit'],dates=['dteday','hr']),
 'beijing':dict(target='PM2.5',numeric=['TEMP','PRES','DEWP','RAIN','WSPM'],categorical=['wd'],dates=['year','month','day','hour'])}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def csv_bytes(path,name):
    with zipfile.ZipFile(path) as outer:
        if name=='bike':return metadata.unique_member(outer,'hour.csv')
        nested=metadata.unique_member(outer,'PRSA2017_Data_20130301-20170228.zip')
        with zipfile.ZipFile(io.BytesIO(nested)) as inner:
            return metadata.unique_member(inner,'PRSA_Data_Aotizhongxin_20130301-20170228.csv')

def load_development(name,meta,root=ROOT):
    info=meta['datasets'][name];archive=root/'source_archives'/f'{name}_official.zip'
    if sha(archive)!=info['archive_sha256']:raise ValueError('Source archive mismatch.')
    times,_,digest=metadata.timestamps(archive,name)
    if digest!=info['selected_csv_sha256'] or not times.is_monotonic_increasing:raise ValueError('Source identity/order mismatch.')
    core.hourly_index(times)
    boundary=pd.Timestamp(info['plan']['reserved_start']);n=int((times<boundary).sum())
    data=csv_bytes(archive,name)
    config=CONFIG[name];columns=config['dates']+[config['target']]+config['numeric']+config['categorical']
    frame=pd.read_csv(io.BytesIO(data),nrows=n,usecols=columns,float_precision='round_trip')
    frame.index=times[:n]
    if len(frame)!=n or frame.index.max()>=boundary:raise ValueError('Reserved prefix boundary violation.')
    for col in [config['target']]+config['numeric']:frame[col]=pd.to_numeric(frame[col],errors='raise')
    for col in config['categorical']:frame[col]=frame[col].map(lambda v:np.nan if pd.isna(v) else str(v))
    grid=pd.date_range(pd.Timestamp(info['plan']['start']),boundary-pd.Timedelta(hours=1),freq='h')
    frame=frame.reindex(grid)
    audit={'dataset':name,'loaded_source_rows':n,'reserved_source_rows_not_loaded':len(times)-n,
           'grid_origins':len(grid),'first_loaded_timestamp':str(times[0]),'last_loaded_timestamp':str(times[n-1]),
           'reserved_start':str(boundary),'target_name':config['target']}
    return frame,audit

def build_features(frame,name,delay):
    index=core.hourly_index(frame.index);config=CONFIG[name];series=frame[config['target']]
    x=pd.DataFrame(index=index)
    for lag in (1,2,3,24,168):x[f'target_lag_{lag}']=series.reindex(index-pd.Timedelta(hours=lag+delay)).to_numpy()
    calendar=index+pd.Timedelta(hours=core.HORIZON_HOURS)
    for key,values,period in [('hour',calendar.hour,24),('weekday',calendar.dayofweek,7),('month',calendar.month-1,12)]:
        x[f'{key}_sin']=np.sin(2*np.pi*values/period);x[f'{key}_cos']=np.cos(2*np.pi*values/period)
    for col in config['numeric']+config['categorical']:
        x['observed_'+col]=frame[col].reindex(index-pd.Timedelta(hours=1)).to_numpy()
    # Forward fill occurs only in source-time order; query the legal past cutoff.
    valid=series.notna()
    last_time=pd.Series(index.where(valid),index=index).ffill()
    past_values=series.ffill();cutoff=index-pd.Timedelta(hours=1+delay)
    p=past_values.reindex(cutoff).to_numpy(dtype=float)
    used_time=pd.DatetimeIndex(last_time.reindex(cutoff))
    age=(cutoff-used_time)/pd.Timedelta(hours=1)
    legal=np.asarray((~used_time.isna())&(age>=0)&(age<=168))
    p[~legal]=np.nan
    if not (used_time[legal]+pd.Timedelta(hours=1+delay)<=index[legal]).all():raise ValueError('Persistence availability violation.')
    return x,p,used_time

def model_pipeline(name,x):
    numeric=list(x.select_dtypes(include='number'));categorical=[c for c in x if c not in numeric]
    transformers=[('numeric',Pipeline([('impute',SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)),('scale',StandardScaler())]),numeric)]
    if categorical:transformers.append(('categorical',Pipeline([('impute',SimpleImputer(strategy='constant',fill_value='__MISSING__',keep_empty_features=True)),('encode',OneHotEncoder(handle_unknown='ignore',sparse_output=False))]),categorical))
    pre=ColumnTransformer(transformers,sparse_threshold=0)
    models={'Ridge':Ridge(alpha=1.,solver='lsqr',tol=1e-6,max_iter=10000),
            'RF':RandomForestRegressor(n_estimators=100,min_samples_leaf=5,max_features=1.,bootstrap=True,random_state=42,n_jobs=1),
            'HGB':HistGradientBoostingRegressor(loss='squared_error',learning_rate=.05,max_iter=100,max_leaf_nodes=15,l2_regularization=.1,early_stopping=False,random_state=42)}
    return Pipeline([('preprocess',pre),('model',models[name])])

def fit_predict(name,x,y,train,evaluation):
    pipeline=model_pipeline(name,x);started=time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter('error',ConvergenceWarning)
        with threadpool_limits(limits=1):pipeline.fit(x.iloc[train],y[train]);p=pipeline.predict(x.iloc[evaluation])
    if not np.isfinite(p).all():raise ValueError('Nonfinite predictions.')
    return p,time.perf_counter()-started

def evaluate(y,p,scale):
    if not np.isfinite(y).all() or not np.isfinite(p).all():raise ValueError('Nonfinite metric input.')
    mae=float(np.mean(np.abs(y-p)));rmse=float(np.sqrt(np.mean((y-p)**2)))
    return {'mae':mae,'rmse':rmse,'normalized_mae':mae/scale if scale>0 else np.nan}

def write_csv_gz(frame,path):
    with gzip.open(path,'wt',encoding='utf-8',newline='') as stream:frame.to_csv(stream,index=False)

def plot(difference,interaction,out):
    fig,axes=plt.subplots(1,2,figsize=(11,4.6))
    colors={0:'#375b88',6:'#d49b3f',24:'#22908a'}
    groups=list(difference.groupby(['dataset','period'],sort=False));pos=np.arange(len(groups))
    for j,delay in enumerate(core.REPORTING_DELAYS):
        values=[g.set_index('delay_hours').loc[delay,'regret_difference_chron_minus_random'] for _,g in groups]
        axes[0].bar(pos+(j-1)*.23,values,width=.23,color=colors[delay],label=f'D={delay} h')
    labels=[f'{name}\n{period}' for (name,period),_ in groups]
    axes[0].set_xticks(pos,labels);axes[0].set_title('Selection-regret difference');axes[0].set_ylabel('Chronological − random (IQR normalized)');axes[0].legend(frameon=False)
    axes[1].bar(pos,interaction.primary_interaction_D24_minus_D0,color='#665a89')
    axes[1].set_xticks(pos,labels);axes[1].set_title('Primary delay interaction');axes[1].set_ylabel('Difference at D=24 minus difference at D=0')
    for ax in axes:ax.axhline(0,color='#777',linewidth=.8);ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Descriptive development evidence; related cases are not independent replications',fontsize=10)
    fig.tight_layout();fig.savefig(out/'selection_regret.png',dpi=170,bbox_inches='tight');plt.close(fig)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'results')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    meta=json.loads((ROOT/'METADATA_PREFLIGHT.json').read_text())
    if meta['protocol_sha256']!=sha(ROOT/'PROTOCOL.md'):raise ValueError('Frozen protocol changed.')
    if meta['preflight_script_sha256']!=sha(ROOT/'metadata_preflight.py'):raise ValueError('Metadata utility changed.')
    manifest={'status':'running','created_utc':datetime.now(timezone.utc).isoformat(),
              'protocol_sha256':sha(ROOT/'PROTOCOL.md'),'implementation_notes_sha256':sha(ROOT/'IMPLEMENTATION_NOTES.md'),
              'script_sha256':sha(__file__),'core_sha256':sha(ROOT/'replay_core.py'),'metadata_sha256':sha(ROOT/'METADATA_PREFLIGHT.json'),
              'versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__},
              'expected_maximum_fits':108,'reserved_target_rows_loaded':0,'reserved_windows_scored':False,
              'new_model_fits':0,'source_archive_hashes':{name:info['archive_sha256'] for name,info in meta['datasets'].items()}}
    def save_manifest():(out/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    save_manifest()
    inner,future,selected,locks,case_audit,predictions,assignments,snapshots,dataset_audit=[],[],[],[],[],[],[],[],[]
    count=0
    for name,info in meta['datasets'].items():
        frame,audit=load_development(name,meta);index=frame.index
        y=core.exact_targets(frame[CONFIG[name]['target']],index).to_numpy(dtype=float)
        prepared={d:build_features(frame,name,d) for d in core.REPORTING_DELAYS}
        common_input=np.logical_and.reduce([np.isfinite(prepared[d][1]) for d in core.REPORTING_DELAYS])
        valid=np.isfinite(y)&common_input
        audit.update(eligible_origins=int(valid.sum()),missing_target_origins=int((~np.isfinite(y)).sum()),
                     unavailable_common_persistence_origins=int((~common_input).sum()))
        dataset_audit.append(audit)
        (out/'dataset_audit.json').write_text(json.dumps(dataset_audit,indent=2))
        for d,(x,p,used) in prepared.items():
            snap=x.reset_index(names='origin');snap.insert(0,'dataset',name);snap.insert(1,'delay_hours',d)
            snap['persistence']=p;snap['persistence_source_timestamp']=used;snap['eligible_origin']=valid
            snapshots.append(snap)
        for period in info['plan']['development']:
            label=period['period'];a,b,c=[pd.Timestamp(period[k]) for k in ('inner_cut','outer_cut','future_end')]
            maxdelay_history=valid&(index<b)&(core.label_ready(index,24)<=b)
            quartiles=np.quantile(y[maxdelay_history],[.25,.75]) if maxdelay_history.any() else np.array([0.,0.])
            scale=float(quartiles[1]-quartiles[0])
            for d in core.REPORTING_DELAYS:
                x,persistence,used=prepared[d]
                ordered=core.chronological_split(index,a,b,c,d,valid);random=core.matched_random_split(ordered)
                history,evaluation=ordered.common_history,ordered.future
                status='feasible' if (len(ordered.train)>=500 and len(ordered.validation)>=100 and len(evaluation)>=100 and len(np.unique(y[ordered.train]))>=2) else 'infeasible'
                case_audit.append({'dataset':name,'period':label,'delay_hours':d,'status':status,'inner_train_n':len(ordered.train),
                                   'inner_validation_n':len(ordered.validation),'common_history_n':len(history),'future_n':len(evaluation),
                                   'history_iqr':scale,'inner_cut':str(a),'outer_cut':str(b),'future_end':str(c)})
                pd.DataFrame(case_audit).to_csv(out/'case_audit.csv',index=False)
                if status!='feasible':continue
                decisions=[]
                for design,split in [('chronological',ordered),('random',random)]:
                    for role,ids in [('train',split.train),('validation',split.validation)]:
                        assignments.append(pd.DataFrame({'dataset':name,'period':label,'delay_hours':d,'stage':'inner','design':design,
                                                         'role':role,'origin_grid_index':ids,'origin':index[ids]}))
                    scores={}
                    for model in MODELS:
                        if model=='persistence':p=persistence[split.validation];seconds=0.
                        else:
                            count+=1;print(f'Fit {count}/108: {name} {label} D={d} {design} {model}',flush=True)
                            p,seconds=fit_predict(model,x,y,split.train,split.validation)
                        metrics=evaluate(y[split.validation],p,scale);scores[model]=metrics['mae']
                        inner.append({'dataset':name,'period':label,'delay_hours':d,'design':design,'model':model,
                                      'train_n':len(split.train),'eval_n':len(split.validation),'history_iqr':scale,'seconds':seconds,**metrics})
                        predictions.append(pd.DataFrame({'dataset':name,'period':label,'delay_hours':d,'stage':'inner','design':design,'model':model,
                                                         'origin_grid_index':split.validation,'origin':index[split.validation],'y_true':y[split.validation],'prediction':p}))
                    winner=min(MODELS,key=lambda model:(scores[model],MODELS.index(model)))
                    decisions.append({'dataset':name,'period':label,'delay_hours':d,'strategy':design,'selected_model':winner,'inner_selection_mae':scores[winner]})
                    pd.DataFrame(inner).to_csv(out/'inner_candidate_metrics.csv',index=False)
                # Persist choices before any fitted future candidates are evaluated.
                locks.extend(decisions);(out/'locked_choices.json').write_text(json.dumps(locks,indent=2))
                for role,ids in [('train',history),('evaluation',evaluation)]:
                    assignments.append(pd.DataFrame({'dataset':name,'period':label,'delay_hours':d,'stage':'future','design':'common',
                                                     'role':role,'origin_grid_index':ids,'origin':index[ids]}))
                actual={}
                for model in MODELS:
                    if model=='persistence':p=persistence[evaluation];seconds=0.
                    else:
                        count+=1;print(f'Fit {count}/108: {name} {label} D={d} common future {model}',flush=True)
                        p,seconds=fit_predict(model,x,y,history,evaluation)
                    metrics=evaluate(y[evaluation],p,scale);actual[model]=metrics
                    future.append({'dataset':name,'period':label,'delay_hours':d,'model':model,'train_n':len(history),'eval_n':len(evaluation),
                                   'history_iqr':scale,'seconds':seconds,**metrics})
                    predictions.append(pd.DataFrame({'dataset':name,'period':label,'delay_hours':d,'stage':'future','design':'common','model':model,
                                                     'origin_grid_index':evaluation,'origin':index[evaluation],'y_true':y[evaluation],'prediction':p}))
                oracle=min(m['mae'] for m in actual.values())
                for choice in decisions:
                    metrics=actual[choice['selected_model']]
                    selected.append({**choice,'history_iqr':scale,'future_mae':metrics['mae'],'future_rmse':metrics['rmse'],
                                     'future_normalized_mae':metrics['normalized_mae'],'oracle_mae':oracle,
                                     'normalized_selection_regret':(metrics['mae']-oracle)/scale if scale>0 else np.nan})
                pd.DataFrame(future).to_csv(out/'future_candidate_metrics.csv',index=False)
                pd.DataFrame(selected).to_csv(out/'selected_procedure_metrics.csv',index=False)
                manifest['new_model_fits']=count;save_manifest()
    differences=[];selection=pd.DataFrame(selected)
    for (name,period,d),group in selection.groupby(['dataset','period','delay_hours'],sort=False):
        g=group.set_index('strategy');chron=g.loc['chronological'];rand=g.loc['random']
        differences.append({'dataset':name,'period':period,'delay_hours':d,'chronological_model':chron.selected_model,'random_model':rand.selected_model,
                            'same_choice':chron.selected_model==rand.selected_model,'chronological_mae':chron.future_mae,'random_mae':rand.future_mae,
                            'regret_difference_chron_minus_random':chron.normalized_selection_regret-rand.normalized_selection_regret})
    difference=pd.DataFrame(differences);difference.to_csv(out/'selection_differences.csv',index=False)
    interactions=[]
    for (name,period),group in difference.groupby(['dataset','period'],sort=False):
        g=group.set_index('delay_hours')
        if 0 in g.index and 24 in g.index:
            interactions.append({'dataset':name,'period':period,'difference_D0':g.loc[0,'regret_difference_chron_minus_random'],
                                 'difference_D24':g.loc[24,'regret_difference_chron_minus_random'],
                                 'primary_interaction_D24_minus_D0':g.loc[24,'regret_difference_chron_minus_random']-g.loc[0,'regret_difference_chron_minus_random']})
    interaction=pd.DataFrame(interactions);interaction.to_csv(out/'primary_interactions.csv',index=False)
    write_csv_gz(pd.concat(predictions,ignore_index=True),out/'predictions.csv.gz')
    write_csv_gz(pd.concat(assignments,ignore_index=True),out/'split_assignments.csv.gz')
    write_csv_gz(pd.concat(snapshots,ignore_index=True),out/'feature_snapshots.csv.gz')
    plot(difference,interaction,out)
    feasible=sum(row['status']=='feasible' for row in case_audit)
    if count!=9*feasible:raise ValueError('Unexpected fit count.')
    manifest.update(status='complete',completed_utc=datetime.now(timezone.utc).isoformat(),new_model_fits=count,feasible_cases=feasible,
                    infeasible_cases=len(case_audit)-feasible,inner_candidate_rows=len(inner),future_candidate_rows=len(future),selected_procedure_rows=len(selected))
    save_manifest();print('Completed.',flush=True);print(difference.to_string(index=False));print(interaction.to_string(index=False))

if __name__=='__main__':main()
