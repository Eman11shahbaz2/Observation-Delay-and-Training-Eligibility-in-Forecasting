"""Availability and split mechanics only; no dataset fitting or scoring."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

HORIZON_HOURS=6
REPORTING_DELAYS=(0,6,24)

def hourly_index(times):
    index=pd.DatetimeIndex(times)
    if index.hasnans or index.has_duplicates:raise ValueError('Missing or duplicate timestamps require a documented resolution.')
    if not index.is_monotonic_increasing:raise ValueError('Timestamps must be sorted.')
    if not (index==index.floor('h')).all():raise ValueError('Expected nominal hourly timestamps.')
    if index.tz is not None:raise ValueError('Protocol uses source nominal clock labels without inferred time zones.')
    return index

def label_ready(origins,delay_hours,horizon_hours=HORIZON_HOURS):
    if delay_hours<0 or horizon_hours<0:raise ValueError('Negative delay/horizon.')
    return pd.DatetimeIndex(origins)+pd.Timedelta(hours=horizon_hours+1+delay_hours)

def latest_available(series,origin,delay_hours,max_gap_hours=168):
    """An hour labeled s is available at s+1+D; search only backward from that cutoff."""
    hourly_index(series.index)
    if delay_hours<0 or max_gap_hours<0:raise ValueError('Negative availability window.')
    cutoff=pd.Timestamp(origin)-pd.Timedelta(hours=1+delay_hours)
    window=series.loc[(series.index<=cutoff)&(series.index>=cutoff-pd.Timedelta(hours=max_gap_hours))].dropna()
    if window.empty:return np.nan,pd.NaT
    return float(window.iloc[-1]),window.index[-1]

def exact_targets(series,origins,horizon_hours=HORIZON_HOURS):
    """Timestamp join, never row shift: absent future timestamps remain missing."""
    hourly_index(series.index)
    index=pd.DatetimeIndex(origins)
    values=series.reindex(index+pd.Timedelta(hours=horizon_hours)).to_numpy()
    return pd.Series(values,index=index,name='target')

@dataclass
class Split:
    train:np.ndarray
    validation:np.ndarray
    common_history:np.ndarray
    future:np.ndarray

def chronological_split(origins,inner_cut,outer_cut,future_end,delay_hours,target_valid=None):
    index=hourly_index(origins);a,b,c=map(pd.Timestamp,(inner_cut,outer_cut,future_end))
    if not a<b<c:raise ValueError('Cutpoints must increase.')
    valid=np.ones(len(index),dtype=bool) if target_valid is None else np.asarray(target_valid,dtype=bool)
    if len(valid)!=len(index):raise ValueError('Target-valid mask length mismatch.')
    ready=label_ready(index,delay_hours)
    train=np.flatnonzero(valid&(index<a)&(ready<=a))
    validation=np.flatnonzero(valid&(index>=a)&(index<b)&(ready<=b))
    history=np.flatnonzero(valid&(index<b)&(ready<=b))
    # Keep the complete target hour inside the declared future block.
    target_hour_end=index+pd.Timedelta(hours=HORIZON_HOURS+1)
    future=np.flatnonzero(valid&(index>=b)&(index<c)&(target_hour_end<=c))
    return Split(train,validation,history,future)

def matched_random_split(split,seed=42):
    """Same membership pool and exact sample counts; no stratification for regression."""
    pool=np.concatenate([split.train,split.validation])
    if len(np.unique(pool))!=len(pool):raise ValueError('Overlapping inner partitions.')
    order=np.random.default_rng(seed).permutation(pool)
    n=len(split.validation)
    return Split(order[n:],order[:n],split.common_history.copy(),split.future.copy())

def calendar_plan(times):
    index=hourly_index(times)
    if len(index)<2:raise ValueError('Insufficient timestamp metadata.')
    start=index.min();end=index.max()+pd.Timedelta(hours=1)
    span=int((end-start)/pd.Timedelta(hours=1))
    cuts={str(f):start+pd.Timedelta(hours=int(np.ceil(span*f))) for f in (.5,.6,.7,.8)}
    return {'start':str(start),'end_exclusive':str(end),
            'development':[{'period':'T1','inner_cut':str(cuts['0.5']),'outer_cut':str(cuts['0.6']),'future_end':str(cuts['0.7'])},
                           {'period':'T2','inner_cut':str(cuts['0.6']),'outer_cut':str(cuts['0.7']),'future_end':str(cuts['0.8'])}],
            'reserved_start':str(cuts['0.8']),'reserved_end_exclusive':str(end)}
