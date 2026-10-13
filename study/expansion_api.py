"""Connect unchanged forecasting mechanics to frozen new-source adapters."""
import gzip
import io
import json
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
import forecast_pilot as original
from source_preparation import guarded_development_loader,finite_numeric

ROOT=Path(__file__).resolve().parent
CONFIG={
 'traffic':dict(target='traffic_volume',numeric=['temp','rain_1h','snow_1h','clouds_all'],categorical=['weather_main'],dates=['date_time']),
 'household':dict(target='Global_active_power',numeric=['Global_reactive_power','Voltage'],categorical=[],dates=['Date','Time'])}
original.CONFIG.update(CONFIG)
MODELS=original.MODELS
sha=original.sha
build_features=original.build_features
model_pipeline=original.model_pipeline
fit_predict=original.fit_predict
evaluate=original.evaluate

def load_development(name,meta=None,root=ROOT):
    """The meta argument retains the inherited runner API; audited metadata lives at root."""
    frame,audit=guarded_development_loader(name,root)
    cfg=CONFIG[name];index=frame.index
    audit.update(loaded_source_rows=audit['raw_source_rows_loaded'],grid_origins=len(index),
        first_loaded_timestamp=str(index.min()),last_loaded_timestamp=str(index.max()),
        reserved_start=str(json.loads((Path(root)/'TIMESTAMP_PREFLIGHT.json').read_text())['datasets'][name]['plan']['reserved_start']),
        target_name=cfg['target'],finite_hourly_target_n=int(np.isfinite(frame[cfg['target']]).sum()),
        missing_or_invalid_hourly_target_n=int((~np.isfinite(frame[cfg['target']])).sum()),
        covariate_missing_hourly_n={c:int(frame[c].isna().sum()) for c in cfg['numeric']+cfg['categorical']})
    return frame,audit

def profile_raw_development(name,root=ROOT):
    """Numerical diagnostics on the same guarded prefix only, after implementation freeze."""
    root=Path(root);meta=json.loads((root/'TIMESTAMP_PREFLIGHT.json').read_text())['datasets'][name]
    with zipfile.ZipFile(root/'source_archives'/f'{name}_official.zip') as z:payload=z.read(meta['selected_member'])
    data=gzip.decompress(payload) if meta['selected_member'].endswith('.gz') else payload
    dates=CONFIG[name]['dates'];target=CONFIG[name]['target']
    raw=pd.read_csv(io.BytesIO(data),sep=',' if name=='traffic' else ';',usecols=dates+[target],
        dtype=str,keep_default_na=False,nrows=meta['development_source_timestamp_rows'])
    if name=='traffic':times=pd.DatetimeIndex(pd.to_datetime(raw.date_time,format='%Y-%m-%d %H:%M:%S'))
    else:times=pd.DatetimeIndex(pd.to_datetime(raw.Date+' '+raw.Time,format='%d/%m/%Y %H:%M:%S'))
    if len(raw)!=meta['development_source_timestamp_rows'] or not (times<pd.Timestamp(meta['plan']['reserved_start'])).all():
        raise ValueError('Raw diagnostic crossed the reserved boundary.')
    values=finite_numeric(raw[target]);values=values.where(values>=0)
    if name=='traffic':values=values.where(values==np.floor(values))
    audit=dict(raw_target_rows_parsed=len(raw),raw_target_invalid_or_missing_n=int(values.isna().sum()),
        reserved_target_rows_parsed=0)
    if name=='traffic':
        grouped=pd.Series(values.to_numpy(),index=times).groupby(level=0)
        stats=grouped.agg(['size','count','min','max'])
        repeated=stats['size']>1;complete=stats['count']==stats['size']
        audit.update(development_unique_hour_n=len(stats),duplicate_extra_development_rows=int(repeated.mul(stats['size']-1).sum()),
            duplicate_development_groups=int(repeated.sum()),
            duplicate_target_consensus_groups=int((repeated&complete&(stats['min']==stats['max'])).sum()),
            duplicate_target_conflict_groups=int((repeated&complete&(stats['min']!=stats['max'])).sum()),
            duplicate_target_invalid_or_missing_groups=int((repeated&~complete).sum()))
    else:
        grouped=pd.Series(values.to_numpy(),index=times.floor('h')).groupby(level=0)
        stats=grouped.agg(['size','count'])
        audit.update(development_represented_hours=len(stats),partial_development_hours=int((stats['size']!=60).sum()),
            complete_clock_hours_with_missing_or_invalid_target_minutes=int(((stats['size']==60)&(stats['count']<60)).sum()))
    return audit
