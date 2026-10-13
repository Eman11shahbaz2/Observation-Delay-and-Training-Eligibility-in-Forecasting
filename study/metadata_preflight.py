"""Download official archives and inspect timestamp columns only; no target profiling."""
import hashlib
import io
import json
import urllib.request
import zipfile
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
from replay_core import calendar_plan,hourly_index

ROOT=Path(__file__).resolve().parent
SOURCES={
 'bike':{'url':'https://archive.ics.uci.edu/static/public/275/bike%2Bsharing%2Bdataset.zip','doi':'10.24432/C5W894'},
 'beijing':{'url':'https://archive.ics.uci.edu/static/public/501/beijing%2Bmulti%2Bsite%2Bair%2Bquality%2Bdata.zip','doi':'10.24432/C5RK5G'}}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def unique_member(archive,suffix):
    names=[n for n in archive.namelist() if n.endswith(suffix)]
    if len(names)!=1:raise ValueError(f'Expected exactly one member ending in {suffix!r}.')
    return archive.read(names[0])

def timestamps(path,name):
    with zipfile.ZipFile(path) as outer:
        if name=='bike':
            data=unique_member(outer,'hour.csv')
            frame=pd.read_csv(io.BytesIO(data),usecols=['dteday','hr'])
            if not frame.hr.between(0,23).all():raise ValueError('Invalid hours.')
            times=pd.to_datetime(frame.dteday,format='%Y-%m-%d')+pd.to_timedelta(frame.hr,unit='h')
        else:
            nested=unique_member(outer,'PRSA2017_Data_20130301-20170228.zip')
            with zipfile.ZipFile(io.BytesIO(nested)) as inner:
                data=unique_member(inner,'PRSA_Data_Aotizhongxin_20130301-20170228.csv')
            frame=pd.read_csv(io.BytesIO(data),usecols=['year','month','day','hour'])
            times=pd.to_datetime(frame[['year','month','day','hour']])
    return pd.DatetimeIndex(times),len(frame),hashlib.sha256(data).hexdigest()

def main():
    archives=ROOT/'source_archives';archives.mkdir(exist_ok=True)
    report={'created_utc':datetime.now(timezone.utc).isoformat(),
            'status':'metadata_only','target_columns_loaded_for_analysis':False,
            'models_fitted':0,'scores_computed':0,'protocol_sha256':digest(ROOT/'PROTOCOL.md'),
            'preflight_script_sha256':digest(__file__),'datasets':{}}
    for name,source in SOURCES.items():
        path=archives/f'{name}_official.zip'
        if not path.exists():
            with urllib.request.urlopen(source['url'],timeout=30) as response:payload=response.read()
            if len(payload)>20*1024**2:raise ValueError('Unexpected archive size.')
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                if archive.testzip() is not None:raise ValueError('Invalid ZIP.')
            path.write_bytes(payload)
        index,n,member_hash=timestamps(path,name)
        duplicate_count=int(index.duplicated().sum());was_sorted=index.is_monotonic_increasing
        # Sorting uses timestamps only. Duplicate resolution is explicitly not automatic.
        index=hourly_index(index.sort_values())
        grid=pd.date_range(index.min(),index.max(),freq='h')
        report['datasets'][name]={**source,'rows':n,'unique_timestamps':len(index),
            'duplicate_timestamps':duplicate_count,'source_was_sorted':was_sorted,
            'missing_clock_hours':len(grid.difference(index)),
            'archive_sha256':digest(path),'selected_csv_sha256':member_hash,
            'plan':calendar_plan(index)}
        print(name,': timestamp preflight passed;',n,'rows. No target analysis.')
    (ROOT/'METADATA_PREFLIGHT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__':main()
