import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from etl.config import ROOT,database_url,DatabaseURL
from psycopg.types.json import set_json_loads
from etl.ingest import run_ingest
from etl.parsing import loads,dumps,decimal_value,stage_financial
from etl.storage import archive,source_path


def test_decimal_json_preserves_precision():
    raw=b'{"amount":12345678901234567890.12345678901234567890}'
    parsed=loads(raw)
    assert parsed['amount']==Decimal('12345678901234567890.12345678901234567890')
    assert loads(dumps(parsed))==parsed
    for value in ['NaN','Infinity',True,{},[]]:
        with pytest.raises(ValueError):
            decimal_value(value)
    with pytest.raises(ValueError):
        loads('{"a":1,"a":2}')


def test_invalid_period_preserved_as_issue():
    raw={'period_from_resolved':'2019-01-01','period_to_resolved':'2018-12-31',
         'consolidation_scope':'standalone','currency':'PLN','equity':'-100','total_assets':'100','liabilities_and_provisions':'200'}
    result,issues=stage_financial(raw)
    assert result['period_start'] is None
    assert result['fiscal_year']==2018
    assert result['reported_metrics']['equity']==Decimal(-100)
    assert 'invalid_period' in result['quality_codes']
    assert 'balance_mismatch' not in result['quality_codes']
    assert raw['period_from_resolved']=='2019-01-01'


def test_archive_never_overwrites(tmp_path):
    source=tmp_path/'source.json'
    b=b'{"x": 0}\n'
    source.write_bytes(b)
    sha=hashlib.sha256(b).hexdigest()
    stored=archive(source,tmp_path/'objects',sha,len(b))
    assert stored.read_bytes()==b
    assert archive(source,tmp_path/'objects',sha,len(b))==stored
    source.write_bytes(b'changed')
    with pytest.raises(ValueError,match='manifest'):
        archive(source,tmp_path/'objects',sha,len(b))
    assert stored.read_bytes()==b
    assert not list(stored.parent.glob('.ingest-*'))


@pytest.mark.parametrize('relative',['../outside.json','/absolute.json','C:/test.json','x\\y.json'])
def test_manifest_path_cannot_escape(tmp_path,relative):
    with pytest.raises(ValueError):
        source_path(tmp_path,relative)


@pytest.fixture(scope='module')
def isolated_database():
    # This exact database is created by this fixture, never a user/application database.
    from alembic import command
    from alembic.config import Config
    import os
    admin=database_url(test=True)
    base=admin.rsplit('/',1)[0]
    name='ci_test_'+uuid4().hex
    with psycopg.connect(base+'/postgres',autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    url=DatabaseURL(base+'/'+name)
    before=os.environ.get('DATABASE_ADMIN_URL')
    try:
        os.environ['DATABASE_ADMIN_URL']=url
        command.upgrade(Config(str(ROOT/'alembic.ini')),'head')
        yield url
    finally:
        if before is None:
            os.environ.pop('DATABASE_ADMIN_URL',None)
        else:
            os.environ['DATABASE_ADMIN_URL']=before
        with psycopg.connect(base+'/postgres',autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))


@pytest.fixture(scope='module')
def imported(isolated_database,tmp_path_factory):
    temp=tmp_path_factory.mktemp('real_export_ingest')
    source=temp/'source'
    (source/'raw/financials').mkdir(parents=True)
    (source/'raw/connections').mkdir(parents=True)
    keys=['0000000746','0000011858','0000736670']
    expected_metrics=0
    for key in keys:
        for kind in ['financials','connections']:
            relative=f'raw/{kind}/{key}.json'
            shutil.copyfile(ROOT/'firmy_b'/relative,source/relative)
            if kind=='financials':
                expected_metrics+=len(loads((source/relative).read_bytes())['metrics'])
    with (ROOT/'firmy_b/firmy.csv').open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        rows=[r for r in reader if r['krs'] in keys or not r['krs']]
        with (source/'firmy.csv').open('w',encoding='utf-8',newline='') as out:
            writer=csv.DictWriter(out,fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    manifest=[{'path':p.relative_to(source).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in source.rglob('*') if p.is_file()]
    mp=temp/'manifest.json'
    mp.write_text(json.dumps(manifest),encoding='utf-8')
    store=temp/'objects'
    batch=run_ingest(isolated_database,source,mp,store)
    return isolated_database,source,mp,store,batch,expected_metrics


@pytest.mark.integration
def test_real_data_import_lineage_and_resume(imported):
    url,source,mp,store,batch,n=imported
    with psycopg.connect(url) as conn:
        set_json_loads(loads,conn)
        assert conn.execute('SELECT count(*) FROM staging.financial_record').fetchone()[0]==n
        assert conn.execute('SELECT count(*) FROM core.company').fetchone()[0]==3
        assert conn.execute("SELECT count(*) FROM raw.quality_issue WHERE code='invalid_company_krs'").fetchone()[0]==1
        assert conn.execute("SELECT count(*) FROM raw.quality_issue WHERE code='invalid_period'").fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM staging.company_year_conflicts').fetchone()[0]>0
        for payload,pointer,metric_id,values in conn.execute('''SELECT r.parsed_payload,f.source_pointer,f.provider_metric_id,f.reported_metrics
            FROM staging.financial_record f JOIN raw.record r ON r.id=f.raw_record_id'''):
            original=payload['metrics'][int(pointer.split('/')[-1])]
            assert original['id']==metric_id
            assert len(original)==310
            if original['revenue_total'] is not None:
                assert Decimal(str(values['revenue_total']))==Decimal(original['revenue_total'])
        before=conn.execute('SELECT count(*) FROM raw.record').fetchone()[0]
    assert run_ingest(url,source,mp,store)==batch
    with psycopg.connect(url) as conn:
        assert conn.execute('SELECT count(*) FROM raw.record').fetchone()[0]==before
        assert conn.execute('SELECT count(*) FROM raw.capture').fetchone()[0]==7


@pytest.mark.integration
def test_verify_complete_payloads_and_trace(imported):
    from etl.verify import verify,trace
    url,source,mp,store,batch,n=imported
    result=verify(url,batch,source)
    assert result['status']=='passed'
    assert result['verified_files']==7
    assert result['verified_raw_records']==10  # Six JSON roots + four actual CSV rows.
    assert result['financial_records']==n
    assert result['promoted_value_mismatches']==0
    with psycopg.connect(url) as conn:
        record=conn.execute('SELECT id FROM staging.financial_record LIMIT 1').fetchone()[0]
    traced=trace(url,record,'revenue_total')
    assert traced['source_pointer'].startswith('/metrics/')
    assert traced['staged_value']==Decimal(str(traced['original_value']))


@pytest.mark.integration
def test_panel_publish_cohorts_exact_values_and_idempotence(imported,tmp_path):
    from analytics.build import build
    from analytics.verify import verify_panel
    from analytics.lineage import feature_trace
    import pyarrow.parquet as pq
    url,source,mp,store,batch,n=imported
    dataset=build(url,batch,tmp_path/'analytical')
    with psycopg.connect(url) as conn:
        set_json_loads(loads,conn)
        rows=conn.execute('SELECT company_id,year,selection_status,features FROM analytics.company_year WHERE dataset_id=%s',(dataset,)).fetchall()
        assert len(rows)==len({(r[0],r[1]) for r in rows})
        assert conn.execute('SELECT count(*) FROM analytics.selection_candidate WHERE dataset_id=%s',(dataset,)).fetchone()[0]==n
        assert any(status=='unresolved_multiple' and all(v is None for v in features.values()) for _,_,status,features in rows)
        assert conn.execute('SELECT research_ready FROM analytics.dataset WHERE id=%s',(dataset,)).fetchone()[0] is False
        path=tmp_path/'analytical'/dataset/'panel.parquet'
        assert pq.read_table(path).num_rows==len(rows)
    assert build(url,batch,tmp_path/'analytical')==dataset
    assert verify_panel(url,dataset)['verified_company_years']==len(rows)
    traced=feature_trace(url,dataset,'0000000746',2025,'revenue_growth')
    assert [i['year'] for i in traced['lineage']['inputs']]==[2025,2024]
    assert all(i['source']['source_pointer'].endswith('/revenue_total') for i in traced['lineage']['inputs'])


@pytest.mark.integration
def test_ingest_role_cannot_update_or_truncate(imported):
    url,*_=imported
    with psycopg.connect(url) as conn:
        conn.execute('GRANT USAGE ON SCHEMA raw,core,staging TO company_ingest')
        conn.execute('GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA raw,core,staging TO company_ingest')
    for statement in ['UPDATE raw.record SET locator=locator','DELETE FROM raw.record','TRUNCATE raw.record CASCADE']:
        with psycopg.connect(url) as conn:
            conn.execute('SET LOCAL ROLE company_ingest')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)


@pytest.mark.integration
def test_database_rejects_mutation(imported):
    url,*_=imported
    for command in ['UPDATE raw.record SET locator=locator','DELETE FROM raw.record','TRUNCATE raw.record CASCADE',
                    'UPDATE staging.financial_record SET currency=currency']:
        with psycopg.connect(url) as conn:
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
                conn.execute(command)


@pytest.mark.integration
def test_file_transaction_rolls_back_and_resumes(imported):
    url,source,mp,store,_,_=imported
    extra=source/'extra.csv'
    extra.write_text('a,b\n1,2,3\n',encoding='utf-8')
    manifest=json.loads(mp.read_text())
    manifest.append({'path':'extra.csv','bytes':extra.stat().st_size,'sha256':hashlib.sha256(extra.read_bytes()).hexdigest()})
    bad_manifest=mp.with_name('bad-manifest.json')
    bad_manifest.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='width mismatch'):
        run_ingest(url,source,bad_manifest,store)
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*) FROM raw.capture WHERE original_path='extra.csv'").fetchone()[0]==0
        assert conn.execute("SELECT status FROM raw.ingestion_event ORDER BY id DESC LIMIT 1").fetchone()[0]=='failed'
    extra.unlink()
    # Original completed batch still verifies and resumes with no duplicated records.
    run_ingest(url,source,mp,store)
