"""Atomic single-stream CSV.GZ exports with a cross-dataset union schema."""
import csv
import gzip
from pathlib import Path
import tempfile
import pandas as pd

def write_union_csv_gz(frames,path):
    frames=list(frames)
    if not frames:raise ValueError('No frames supplied.')
    if any(not frame.columns.is_unique for frame in frames):raise ValueError('Duplicate column names.')
    combined=pd.concat(frames,ignore_index=True,sort=False)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    descriptor=tempfile.NamedTemporaryFile(prefix=path.name+'.',suffix='.tmp',dir=path.parent,delete=False)
    temp=Path(descriptor.name);descriptor.close()
    try:
        with gzip.open(temp,'wt',encoding='utf-8',newline='',compresslevel=9) as stream:
            combined.to_csv(stream,index=False)
        count=0
        with gzip.open(temp,'rt',encoding='utf-8',newline='') as stream:
            reader=csv.reader(stream)
            if next(reader)!=list(combined.columns):raise ValueError('Export header mismatch.')
            for row in reader:
                if len(row)!=len(combined.columns):raise ValueError('Export row schema mismatch.')
                count+=1
        if count!=len(combined):raise ValueError('Export row count mismatch.')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return dict(rows=len(combined),columns=list(combined.columns),compression='one gzip stream',atomic_replacement=True)
