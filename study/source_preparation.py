"""Frozen source adapters. This stage executes them on synthetic fixtures only."""
import io
import json
from pathlib import Path
import zipfile
import gzip
import numpy as np
import pandas as pd
from preflight_new_sources import sha,SOURCES,read_timestamp_bytes

TRAFFIC_NUMERIC=['temp','rain_1h','snow_1h','clouds_all']
HOUSEHOLD_NUMERIC=['Global_reactive_power','Voltage']

def finite_numeric(values):
    numeric=pd.to_numeric(values,errors='coerce').astype(float)
    return numeric.where(np.isfinite(numeric))

def consensus(values):
    """Every duplicate must contain the same finite numeric value; otherwise missing."""
    a=values.to_numpy(dtype=float)
    return float(a[0]) if len(a) and np.isfinite(a).all() and np.equal(a,a[0]).all() else np.nan

def prepare_traffic(frame):
    frame=frame.copy()
    frame.index=pd.DatetimeIndex(pd.to_datetime(frame.date_time,format='%Y-%m-%d %H:%M:%S'))
    for col in ['traffic_volume']+TRAFFIC_NUMERIC:frame[col]=finite_numeric(frame[col])
    target=frame.traffic_volume
    frame['traffic_volume']=target.where((target>=0)&(target==np.floor(target)))
    groups=frame.groupby(level=0,sort=True)
    out=pd.DataFrame({col:groups[col].agg(consensus) for col in ['traffic_volume']+TRAFFIC_NUMERIC})
    def category(values):
        if values.isna().any() or (values.astype(str).str.strip()=='').any():return np.nan
        # JSON avoids ambiguity if a category itself contains a separator.
        return json.dumps(sorted(set(values.astype(str))),ensure_ascii=False,separators=(',',':'))
    out['weather_main']=groups.weather_main.agg(category)
    return out

def prepare_household(frame):
    frame=frame.copy()
    frame.index=pd.DatetimeIndex(pd.to_datetime(frame.Date+' '+frame.Time,format='%d/%m/%Y %H:%M:%S'))
    columns=['Global_active_power']+HOUSEHOLD_NUMERIC
    for col in columns:frame[col]=finite_numeric(frame[col])
    frame['Global_active_power']=frame.Global_active_power.where(frame.Global_active_power>=0)
    hour=frame.index.floor('h')
    counts=pd.Series(1,index=hour).groupby(level=0).sum()
    duplicate_hours=frame.index[frame.index.duplicated(keep=False)].floor('h').unique()
    structural=(counts==60)&(~counts.index.isin(duplicate_hours))
    def complete_mean(values):
        a=values.to_numpy(dtype=float)
        return float(a.mean()) if len(a)==60 and np.isfinite(a).all() else np.nan
    out=frame[columns].groupby(hour,sort=True).agg(complete_mean)
    out.loc[~structural,:]=np.nan
    return out

def guarded_development_loader(name,root):
    """Parse numeric values only from the already audited sorted development prefix."""
    root=Path(root);meta=json.loads((root/'TIMESTAMP_PREFLIGHT.json').read_text())['datasets'][name]
    if not meta['source_was_sorted']:raise ValueError('Prefix loading requires timestamp-sorted source.')
    archive=root/'source_archives'/f'{name}_official.zip'
    if sha(archive)!=meta['archive_sha256']:raise ValueError('Source identity mismatch.')
    with zipfile.ZipFile(archive) as z:payload=z.read(meta['selected_member'])
    data=gzip.decompress(payload) if meta['selected_member'].endswith('.gz') else payload
    source=SOURCES[name];n=meta['development_source_timestamp_rows']
    covariates=TRAFFIC_NUMERIC+['weather_main'] if name=='traffic' else HOUSEHOLD_NUMERIC
    target='traffic_volume' if name=='traffic' else 'Global_active_power'
    columns=source['date_columns']+[target]+covariates
    # String parsing avoids hidden numeric inference; conversion occurs only after the boundary assertion.
    raw=pd.read_csv(io.BytesIO(data),sep=source['delimiter'],usecols=columns,nrows=n,dtype=str,keep_default_na=False)
    if name=='traffic':times=pd.DatetimeIndex(pd.to_datetime(raw.date_time,format='%Y-%m-%d %H:%M:%S'))
    else:times=pd.DatetimeIndex(pd.to_datetime(raw.Date+' '+raw.Time,format='%d/%m/%Y %H:%M:%S'))
    boundary=pd.Timestamp(meta['plan']['reserved_start'])
    if len(raw)!=n or times.hasnans or not (times<boundary).all():raise ValueError('Reserved prefix boundary violation.')
    hourly=prepare_traffic(raw) if name=='traffic' else prepare_household(raw)
    grid=pd.date_range(meta['plan']['start'],boundary-pd.Timedelta(hours=1),freq='h')
    return hourly.reindex(grid),dict(dataset=name,raw_source_rows_loaded=n,
        reserved_source_rows_not_loaded=meta['reserved_source_timestamp_rows'],reserved_numeric_target_rows_parsed=0)
