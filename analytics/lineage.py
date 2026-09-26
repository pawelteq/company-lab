"""Resolve stored feature definitions to exact source fields, across calendar years."""
import psycopg
from psycopg.types.json import set_json_loads
from etl.parsing import loads
from etl.verify import trace


def feature_trace(url,dataset,krs,year,feature):
    with psycopg.connect(url,connect_timeout=10) as conn:
        set_json_loads(loads,conn)
        defs={name:definition for name,definition in conn.execute('SELECT name,definition FROM analytics.feature_definition WHERE dataset_id=%s',(dataset,))}
        if feature not in defs:
            raise ValueError('Feature not found in dataset definition registry')
        meta=conn.execute('SELECT config,code_hash FROM analytics.dataset WHERE id=%s',(dataset,)).fetchone()
        rows={y:(selected,values,reasons) for y,selected,values,reasons in conn.execute('''SELECT p.year,p.selected_record_id,p.features,p.missing_reasons
            FROM analytics.company_year p JOIN core.company c ON c.company_id=p.company_id WHERE p.dataset_id=%s AND c.krs=%s''',(dataset,krs))}
    if year not in rows:
        raise ValueError('Company-year not present in this dataset')
    def walk(name,y,seen):
        if (name,y) in seen:
            raise ValueError('Cyclic feature definition')
        definition=defs[name]
        selected,values,reasons=rows.get(y,(None,{},{}))
        node={'feature':name,'year':y,'value':values.get(name),'reason':reasons.get(name,'missing_year' if y not in rows else None),
            'definition':definition}
        if definition['op']=='source':
            node['source']=trace(url,selected,definition['source']) if selected else None
        else:
            node['inputs']=[walk(i['name'],y+i['offset'],seen|{(name,y)}) for i in definition['inputs']]
        return node
    return {'dataset_id':str(dataset),'krs':krs,'config':meta[0],'code_hash':meta[1],'lineage':walk(feature,year,set())}
