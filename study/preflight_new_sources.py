"""Official-archive timestamp audit only. Never parse measurement/target columns."""
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile
import numpy as np
import pandas as pd
from replay_core import calendar_plan,chronological_split,label_ready

ROOT=Path(__file__).resolve().parent
SOURCES={
 'traffic':dict(uci_id=492,doi='10.24432/C5X60B',
     url='https://archive.ics.uci.edu/static/public/492/metro%2Binterstate%2Btraffic%2Bvolume.zip',
     metadata_url='https://archive.ics.uci.edu/dataset/492/metro+interstate+traffic+volume',
     member_suffix='Metro_Interstate_Traffic_Volume.csv.gz',delimiter=',',date_columns=['date_time']),
 'household':dict(uci_id=235,doi='10.24432/C58K54',
     url='https://archive.ics.uci.edu/static/public/235/individual%2Bhousehold%2Belectric%2Bpower%2Bconsumption.zip',
     metadata_url='https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption',
     member_suffix='household_power_consumption.txt',delimiter=';',date_columns=['Date','Time'])}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def bytes_sha(data):return hashlib.sha256(data).hexdigest()

def download(name,source):
    path=ROOT/'source_archives'/f'{name}_official.zip'
    if path.exists():return path
    request=urllib.request.Request(source['url'],headers={'User-Agent':'Timestamp-only research preflight'})
    with urllib.request.urlopen(request,timeout=30) as response:
        data=response.read(32*1024*1024+1)
    if len(data)>32*1024*1024:raise ValueError('Unexpected source archive size.')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip() is not None:raise ValueError('Invalid source ZIP.')
    path.write_bytes(data);return path

def read_timestamp_bytes(data,name):
    source=SOURCES[name]
    # Header inspection reads names only; measurement columns never enter the frame.
    headers=list(pd.read_csv(io.BytesIO(data),sep=source['delimiter'],nrows=0).columns)
    frame=pd.read_csv(io.BytesIO(data),sep=source['delimiter'],usecols=source['date_columns'],
                      dtype=str,keep_default_na=False)
    if name=='traffic':
        index=pd.DatetimeIndex(pd.to_datetime(frame.date_time,format='%Y-%m-%d %H:%M:%S',errors='raise'))
        if not (index==index.floor('h')).all():raise ValueError('Non-hourly traffic timestamps.')
    else:
        index=pd.DatetimeIndex(pd.to_datetime(frame.Date+' '+frame.Time,format='%d/%m/%Y %H:%M:%S',errors='raise'))
        if not (index==index.floor('min')).all():raise ValueError('Non-minute household timestamps.')
    if index.hasnans or index.tz is not None:raise ValueError('Missing or unexpected zoned timestamps.')
    return index,headers

def read_archive(path,name):
    with zipfile.ZipFile(path) as archive:
        names=[n for n in archive.namelist() if n.endswith(SOURCES[name]['member_suffix'])]
        if len(names)!=1:raise ValueError('Ambiguous selected member.')
        payload=archive.read(names[0])
    data=gzip.decompress(payload) if names[0].endswith('.gz') else payload
    index,headers=read_timestamp_bytes(data,name)
    return index,headers,dict(selected_member=names[0],selected_member_sha256=bytes_sha(payload),
        uncompressed_selected_data_sha256=bytes_sha(data))

def gap_summary(index,unit):
    unique=index.unique().sort_values()
    diffs=np.diff(unique.asi8)//pd.Timedelta(1,unit=unit).value
    ids=np.flatnonzero(diffs>1)
    records=[dict(last_observed=str(unique[i]),next_observed=str(unique[i+1]),missing_steps=int(diffs[i]-1))
             for i in ids]
    return dict(gap_count=len(records),largest_missing_run_steps=max([r['missing_steps'] for r in records],default=0),
                largest_gaps=sorted(records,key=lambda r:-r['missing_steps'])[:10])

def household_complete_hours(index):
    # Timestamp identities alone decide structural eligibility, including duplicate rejection.
    hour=index.floor('h')
    counts=pd.Series(1,index=hour).groupby(level=0).sum()
    duplicate_hours=pd.DatetimeIndex(index[index.duplicated(keep=False)].floor('h').unique())
    valid=(counts==60)&(~counts.index.isin(duplicate_hours))
    complete=pd.DatetimeIndex(counts.index[valid])
    if complete.empty:raise ValueError('No structurally complete household hours.')
    return complete,counts,duplicate_hours

def structural_audit(index,name):
    unique=index.unique().sort_values();unit='h' if name=='traffic' else 'min'
    freq='h' if name=='traffic' else 'min'
    expected=pd.date_range(unique.min(),unique.max(),freq=freq)
    counts=pd.Series(index).value_counts().sort_index()
    duplicates=counts[counts>1]
    audit=dict(source_rows=len(index),unique_timestamps=len(unique),source_was_sorted=index.is_monotonic_increasing,
        first_timestamp=str(unique.min()),last_timestamp=str(unique.max()),
        duplicate_extra_rows=int(index.duplicated().sum()),duplicate_timestamp_groups=len(duplicates),
        largest_timestamp_multiplicity=int(counts.max()),timestamp_multiplicity_histogram={str(k):int(v) for k,v in counts.value_counts().sort_index().items()},
        expected_clock_steps=len(expected),missing_clock_steps=len(expected.difference(unique)),
        clock_step_unit='hour' if name=='traffic' else 'minute',**gap_summary(index,unit))
    if name=='traffic':
        hourly_grid=pd.date_range(unique.min(),unique.max(),freq='h')
        present=hourly_grid.isin(unique)
        audit.update(hourly_grid_start=str(hourly_grid.min()),hourly_grid_end_exclusive=str(hourly_grid.max()+pd.Timedelta(hours=1)),
            present_clock_hours=int(present.sum()),missing_clock_hours=int((~present).sum()),
            structural_hourly_feasibility='Duplicates require frozen consolidation; target agreement not inspected.')
    else:
        complete,hour_counts,duplicate_hours=household_complete_hours(index)
        hourly_grid=pd.date_range(complete.min(),complete.max(),freq='h')
        present=hourly_grid.isin(complete)
        audit.update(hourly_grid_start=str(hourly_grid.min()),hourly_grid_end_exclusive=str(hourly_grid.max()+pd.Timedelta(hours=1)),
            structurally_complete_hours=len(complete),incomplete_represented_hours=int((hour_counts!=60).sum()),
            hours_with_duplicate_minute_stamps=len(duplicate_hours),
            observed_minutes_per_hour_histogram={str(k):int(v) for k,v in hour_counts.value_counts().sort_index().items()},
            incomplete_hour_examples=[dict(hour=str(t),observed_minutes=int(n)) for t,n in hour_counts[hour_counts!=60].items()][:10],
            missing_or_incomplete_interior_clock_hours=int((~present).sum()),
            structural_hourly_feasibility='Numeric completeness remains uninspected; all 60 finite minute values will be required.')
    audit['plan']=calendar_plan(hourly_grid)
    rows=[]
    audit['infeasible_timestamp_periods']=[]
    for period in audit['plan']['development']:
        a,b,c=[pd.Timestamp(period[key]) for key in ('inner_cut','outer_cut','future_end')]
        if not a<b<c:
            audit['infeasible_timestamp_periods'].append(dict(period=period['period'],reason='Insufficient clock span for distinct cutpoints.'))
            continue
        for o,l in ((0,0),(0,24),(24,0),(24,24)):
            # Exact target-hour timestamp presence is an upper bound on numerical eligibility.
            # A forecast origin need not itself have a source record.
            possible_target=pd.Series(present,index=hourly_grid).reindex(
                hourly_grid+pd.Timedelta(hours=6),fill_value=False).to_numpy(dtype=bool)
            split=chronological_split(hourly_grid,a,b,c,o+l,possible_target)
            rows.append(dict(dataset=name,period=period['period'],O=o,L=l,
                potential_inner_train_n=len(split.train),potential_inner_validation_n=len(split.validation),
                potential_common_history_n=len(split.common_history),potential_future_n=len(split.future),
                timestamp_count_gates_pass=(len(split.train)>=500 and len(split.validation)>=100 and len(split.future)>=100),
                numeric_feasibility_verified=False))
    audit['potential_case_counts']=rows
    boundary=pd.Timestamp(audit['plan']['reserved_start'])
    audit['development_source_timestamp_rows']=int((index<boundary).sum())
    audit['reserved_source_timestamp_rows']=int((index>=boundary).sum())
    return audit

def main():
    report=dict(created_utc=datetime.now(timezone.utc).isoformat(),stage='timestamp-only feasibility audit',
        models_fitted=0,scores_computed=0,target_columns_loaded_for_analysis=False,
        measurement_columns_loaded_for_analysis=False,target_missingness_profiled=False,
        audit_rules_sha256=sha(ROOT/'AUDIT_RULES.md'),script_sha256=sha(__file__),
        replay_core_sha256=sha(ROOT/'replay_core.py'),datasets={})
    (ROOT/'AUDIT_FREEZE.json').write_text(json.dumps({k:v for k,v in report.items() if k!='datasets'},indent=2))
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs={name:executor.submit(download,name,source) for name,source in SOURCES.items()}
        paths={name:job.result() for name,job in jobs.items()}
    rows=[]
    for name,source in SOURCES.items():
        index,headers,member=read_archive(paths[name],name)
        audit=structural_audit(index,name)
        report['datasets'][name]={**source,
            'archive_sha256':sha(paths[name]),'archive_size_bytes':paths[name].stat().st_size,
            'header_names':headers,**member,**audit}
        rows.extend(audit['potential_case_counts'])
        print(f'{name}: {len(index)} timestamp rows; {audit["duplicate_extra_rows"]} extra duplicate rows. No target inspection.',flush=True)
    report['completed_utc']=datetime.now(timezone.utc).isoformat()
    (ROOT/'TIMESTAMP_PREFLIGHT.json').write_text(json.dumps(report,indent=2))
    pd.DataFrame(rows).to_csv(ROOT/'potential_case_counts.csv',index=False)

if __name__=='__main__':main()
