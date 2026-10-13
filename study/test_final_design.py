import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import numpy as np
import pandas as pd
import study_api as f
from run_full_experiment import SETTINGS
import source_preparation as prep

ROOT=Path(__file__).resolve().parent
class FinalDesignChecks(unittest.TestCase):
    def test_explicit_release_is_required_before_source_access(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(PermissionError):f.load_full('household',folder)
            with self.assertRaises(PermissionError):f.load_full('household',folder,allow_reserved=True)

    def test_changed_frozen_component_blocks_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'component.txt').write_text('frozen')
            freeze={'reserved_numeric_targets_inspected_before_freeze':False,'sha256':{'component.txt':f.sha(root/'component.txt')}}
            (root/'FINAL_FREEZE.json').write_text(json.dumps(freeze));f.verify_release(root)
            (root/'component.txt').write_text('changed')
            with self.assertRaises(PermissionError):f.verify_release(root)

    def test_endpoint_partial_minutes_are_excluded_before_numeric_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'source_archives').mkdir()
            times=pd.date_range('2020-01-01 17:24', '2020-01-01 20:02',freq='min')
            values=['POISON' if t.hour in (17,20) else str(t.hour-17) for t in times]
            raw=pd.DataFrame(dict(Date=times.strftime('%d/%m/%Y'),Time=times.strftime('%H:%M:%S'),
                Global_active_power=values,Global_reactive_power=values,Voltage=values))
            archive=root/'source_archives/household_official.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('data.txt',raw.to_csv(index=False,sep=';'))
            info=dict(archive_sha256=f.sha(archive),selected_member='data.txt',plan=dict(start='2020-01-01 18:00',reserved_start='2020-01-01 19:00',reserved_end_exclusive='2020-01-01 20:00'))
            original=prep.finite_numeric
            def guarded(values):
                self.assertNotIn('POISON',set(values));return original(values)
            with patch.object(f,'verify_release',return_value={}),patch.object(f,'source_metadata',return_value=info),patch.object(prep,'finite_numeric',side_effect=guarded):
                frame,audit=f.load_full('household',root,allow_reserved=True)
            np.testing.assert_array_equal(frame.Global_active_power,[1.,2.])
            self.assertEqual(audit['excluded_endpoint_rows'],39);self.assertEqual(audit['reserved_numeric_measurement_rows_converted'],60)

    def test_reserved_measurements_cannot_change_predeployment_features(self):
        index=pd.date_range('2020-01-01',periods=1000,freq='h');b=index[800]
        frame=pd.DataFrame(dict(cnt=np.arange(1000,dtype=float),temp=1.,hum=.5,windspeed=.2,weathersit='1'),index=index)
        changed=frame.copy();changed.loc[b:,'cnt']=1e12;changed.loc[b:,'temp']=1e12
        for o,l in SETTINGS:
            x,p,_=f.build_features(frame,'bike',o);xx,pp,_=f.build_features(changed,'bike',o)
            train=np.flatnonzero(index+pd.Timedelta(hours=7+o+l)<=b)
            pd.testing.assert_frame_equal(x.iloc[train],xx.iloc[train]);np.testing.assert_array_equal(p[train],pp[train])
            self.assertTrue((index[train]+pd.Timedelta(hours=7)<=b).all())

    def test_carried_choices_are_exact_T2_inner_minima(self):
        records=[]
        for name in ['earlier','expansion']:
            records += [r for r in json.loads((ROOT/f'development_reference/{name}/locked_choices.json').read_text()) if r['period']=='T2']
        self.assertEqual(len(records),112)
        self.assertEqual(len({(r['dataset'],r['O'],r['L'],r['strategy']) for r in records}),112)
        for row in records:
            scores=row['inner_mae_all_candidates'];winner=min(f.MODELS,key=lambda m:(scores[m],f.MODELS.index(m)))
            self.assertEqual(row['selected_model'],winner)
            self.assertLessEqual(pd.Timestamp(row['last_inner_fit_completed_utc']),pd.Timestamp(row['locked_utc']))

    def test_final_boundaries_preserve_all_original_reservations(self):
        expected={'bike':('2012-08-07 20:00','2013-01-01 00:00'),'beijing':('2016-05-12 20:00','2017-03-01 00:00'),
            'traffic':('2017-07-20 02:00','2018-10-01 00:00'),'household':('2010-02-11 16:00','2010-11-26 21:00')}
        for name,(b,c) in expected.items():
            plan=f.source_metadata(name)['plan'];self.assertEqual(pd.Timestamp(plan['reserved_start']),pd.Timestamp(b));self.assertEqual(pd.Timestamp(plan['reserved_end_exclusive']),pd.Timestamp(c))

if __name__=='__main__':unittest.main(verbosity=2)
