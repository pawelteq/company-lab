import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_data import Profile, missing, number


class AuditSemanticsTests(unittest.TestCase):
    def test_zero_and_negative_are_not_missing(self):
        self.assertFalse(missing(0))
        self.assertFalse(missing('0.00'))
        self.assertEqual(number('-12.3'),-12.3)
        self.assertIsNone(number('NaN'))
        self.assertIsNone(number('Infinity'))
        self.assertIsNone(number(True))

    def test_absent_null_zero_and_empty_container_differ(self):
        p=Profile()
        p.add({'value':None,'details':[]})
        p.add({'value':'0'})
        p.add({})
        f=p.result()['fields']
        self.assertEqual(f['value']['absent'],1)
        self.assertEqual(f['value']['null_or_blank'],1)
        self.assertEqual(f['value']['zero'],1)
        self.assertEqual(f['details']['empty_container'],1)


class RealExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=json.loads(Path('data/audit/summary.json').read_text(encoding='utf-8'))
        cls.q=json.loads(Path('data/audit/quality_details.json').read_text(encoding='utf-8'))

    def test_counts_reconcile(self):
        s=self.s
        n=s['profiles']['raw_metrics']['rows']
        self.assertEqual(sum(s['stats']['years'].values()),n)
        self.assertEqual(sum(self.q['unique_company_year_by_year'].values()),s['stats']['panel']['unique_company_year'])
        self.assertEqual(s['stats']['panel']['unique_company_year']+s['stats']['panel']['excess_company_year_records'],n)
        self.assertEqual(s['profiles']['firmy_finanse']['rows'],n)
        self.assertEqual(s['counts']['firmy'],s['counts']['financials'])
        self.assertEqual(s['profiles']['firmy']['rows']-s['counts']['firmy'],1)

    def test_every_source_file_unchanged_since_manifest(self):
        manifest=json.loads(Path('data/audit/source_manifest.json').read_text(encoding='utf-8'))
        root=Path('firmy_b')
        self.assertEqual({p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()},{f['path'] for f in manifest})
        for f in manifest:
            b=(root/f['path']).read_bytes()
            self.assertEqual(len(b),f['bytes'],f['path'])
            self.assertEqual(hashlib.sha256(b).hexdigest(),f['sha256'],f['path'])

    def test_known_invalid_period_is_reported(self):
        self.assertEqual(self.q['counts']['non_positive_period'],1)
        e=self.q['examples']['non_positive_period'][0]
        self.assertEqual(e['detail'],{'start':'2019-01-01','end':'2018-12-31'})

    def test_financial_columns_reconcile(self):
        self.assertEqual(self.s['stats']['csv_reconciliation']['id_missing_in_raw'],0)
        self.assertEqual(self.s['stats'].get('csv_value_mismatches',{}),{})
        for f in self.s['profiles']['raw_metrics']['fields'].values():
            self.assertEqual(f['present']+f['absent'],self.s['profiles']['raw_metrics']['rows'])
            self.assertEqual(f.get('nonempty',0)+f.get('null_or_blank',0),f['present'])


if __name__=='__main__':
    unittest.main()
