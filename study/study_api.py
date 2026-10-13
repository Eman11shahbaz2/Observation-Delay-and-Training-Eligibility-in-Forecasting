"""Unchanged forecasting mechanics, explicit release gate for final measurements."""
import gzip
import io
import json
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
import forecast_pilot as original
import expansion_api as expansion
import metadata_preflight as metadata
from source_preparation import prepare_traffic,prepare_household

ROOT=Path(__file__).resolve().parent
NAMES=('bike','beijing','traffic','household')
CONFIG=original.CONFIG
MODELS=original.MODELS
sha=original.sha
build_features=original.build_features
fit_predict=original.fit_predict
evaluate=original.evaluate

def source_metadata(name,root=ROOT):
    filename='METADATA_PREFLIGHT.json' if name in ('bike','beijing') else 'TIMESTAMP_PREFLIGHT.json'
    return json.loads((Path(root)/filename).read_text())['datasets'][name]

def load_development(name,root=ROOT):
    if name in ('bike','beijing'):
        return original.load_development(name,json.loads((Path(root)/'METADATA_PREFLIGHT.json').read_text()),root)
    return expansion.load_development(name,root=root)

def verify_release(root=ROOT):
    root=Path(root);path=root/'FINAL_FREEZE.json'
    if not path.exists():raise PermissionError('Final measurements are reserved until the complete plan is frozen.')
    freeze=json.loads(path.read_text())
    if freeze['reserved_numeric_targets_inspected_before_freeze'] is not False:raise PermissionError('Invalid release freeze.')
    for name,digest in freeze['sha256'].items():
        if sha(root/name)!=digest:raise PermissionError('Frozen final component changed: '+name)
    return freeze

def load_full(name,root=ROOT,allow_reserved=False):
    if not allow_reserved:raise PermissionError('Explicit frozen final-evaluation release required.')
    root=Path(root);verify_release(root)
    info=source_metadata(name,root);archive=root/'source_archives'/f'{name}_official.zip'
    if sha(archive)!=info['archive_sha256']:raise ValueError('Archive identity changed.')
    cfg=CONFIG[name];plan=info['plan'];start=pd.Timestamp(plan['start']);end=pd.Timestamp(plan['reserved_end_exclusive'])
    boundary=pd.Timestamp(plan['reserved_start']);columns=cfg['dates']+[cfg['target']]+cfg['numeric']+cfg['categorical']
    if name in ('bike','beijing'):
        times,_,digest=metadata.timestamps(archive,name)
        if digest!=info['selected_csv_sha256']:raise ValueError('Selected source identity changed.')
        raw=pd.read_csv(io.BytesIO(original.csv_bytes(archive,name)),usecols=columns,float_precision='round_trip')
        raw.index=times
        if not times.is_unique or not times.is_monotonic_increasing:raise ValueError('Invalid source timestamps.')
        retained=raw[(times>=start)&(times<end)].copy()
        for col in [cfg['target']]+cfg['numeric']:retained[col]=pd.to_numeric(retained[col],errors='raise')
        for col in cfg['categorical']:retained[col]=retained[col].map(lambda v:np.nan if pd.isna(v) else str(v))
        hourly=retained;retained_times=retained.index
    else:
        with zipfile.ZipFile(archive) as z:payload=z.read(info['selected_member'])
        data=gzip.decompress(payload) if info['selected_member'].endswith('.gz') else payload
        raw=pd.read_csv(io.BytesIO(data),sep=',' if name=='traffic' else ';',usecols=columns,dtype=str,keep_default_na=False)
        times=pd.DatetimeIndex(pd.to_datetime(raw.date_time,format='%Y-%m-%d %H:%M:%S')) if name=='traffic' else pd.DatetimeIndex(pd.to_datetime(raw.Date+' '+raw.Time,format='%d/%m/%Y %H:%M:%S'))
        if times.hasnans or not times.is_monotonic_increasing:raise ValueError('Invalid source timestamps.')
        mask=(times>=start)&(times<end);retained=raw.loc[mask].copy();retained_times=times[mask]
        hourly=prepare_traffic(retained) if name=='traffic' else prepare_household(retained)
    grid=pd.date_range(start,end-pd.Timedelta(hours=1),freq='h')
    frame=hourly.reindex(grid)
    reserved=frame.index>=boundary
    audit=dict(dataset=name,raw_source_rows=len(raw),measurement_rows_converted=len(retained),
        excluded_endpoint_rows=len(raw)-len(retained),reserved_numeric_measurement_rows_converted=int((retained_times>=boundary).sum()),
        grid_origins=len(frame),reserved_hourly_target_finite=int(np.isfinite(frame.loc[reserved,cfg['target']]).sum()),
        reserved_hourly_target_missing=int((~np.isfinite(frame.loc[reserved,cfg['target']])).sum()),
        reserved_start=str(boundary),reserved_end_exclusive=str(end),explicit_release_after_freeze=True)
    return frame,audit
