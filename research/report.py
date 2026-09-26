from pathlib import Path
import json
import os
from etl.config import ROOT
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'.local'/'matplotlib'))
import psycopg
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from etl.storage import digest_file


def fmt(value):
    return 'brak' if value is None else f'{value:.5g}'


def render(url,run_id):
    with psycopg.connect(url,connect_timeout=10) as conn:
        row=conn.execute('SELECT results,artifact_manifest FROM research.run WHERE id=%s',(run_id,)).fetchone()
    if row is None:
        raise ValueError('Unknown research run')
    result,manifest=row
    for item in manifest:
        if digest_file(Path(item['path']))!=(item['sha256'],item['bytes']):
            raise ValueError('Research artifact differs from published results')
    output=ROOT/'data/research'/result['dataset_id']/str(run_id)/'reports'
    output.mkdir(exist_ok=True)
    qs=[s.get('primary_test',{}).get('bh_q_value') for s in result['studies']]
    available=[q for q in qs if q is not None]
    primary_summary=(f'Po korekcie BH {sum(q<0.05 for q in available)} z {len(available)} dostępnych testów głównych '
                     'przekracza próg istotności 5%. Brak istotności nie dowodzi braku zależności.')
    lines=['# R01–R04 — pierwsze wyniki eksploracyjne','',
        f"Run: `{run_id}`. Dataset: `{result['dataset_id']}`.",
        '**Klasa wniosku: zależność warunkowa w modelu, na prowizorycznych danych dostawcy. Nie jest to identyfikacja przyczynowa, zwalidowana predykcja ani rekomendacja.**','',
        primary_summary,
        'To nie dowodzi braku zależności: przedziały są szerokie, rozkłady skrajne, a część wyników zmienia się',
        'po winsoryzacji. Kolejny krok to diagnostyka zmiennych/mianowników i źródeł, nie rekomendowanie strategii.', '',
        '## Protokół','',
        'X w t=2018–2024, Y z dokładnego roku t+1. Pooled z efektami roku i FE firmy/roku na wspólnej próbie.',
        'SE klastrowane po firmie. Complete cases i iteracyjne usunięcie singletonów.',
        'Wariant główny bez przycinania; zaplanowana wrażliwość 1/99 percentyl X/Y przed kwadratem.',
        'Cztery testy pierwotne FE raw skorygowane BH FDR. Pozostałe p są nieskorygowane.',
        'Numeryczne skalowanie RMS jest odwróconą reparametryzacją; wszystkie współczynniki i CI są w oryginalnych jednostkach.',
        'Dane źródłowe ani panel nie zostały winsoryzowane. Progi i próbki są osobnymi artefaktami runu.', '',
        '## Testy pierwotne — FE bez przycinania','',
        '| Badanie | N firm | N obs. | Parametr | Współczynnik | 95% CI | p | q BH |','|---|---:|---:|---|---:|---|---:|---:|']
    for study in result['studies']:
        spec=study['specification']
        primary=next(e for e in study['estimates'] if e['model']=='firm_and_year_fe' and e['variant']=='untrimmed')
        if primary['status']=='estimated':
            c=primary['coefficients'][spec['primary_term']]
            lines.append(f"| {spec['id']} | {primary['n_companies']:,} | {primary['n_observations']:,} | {spec['primary_term']} | {fmt(c['coefficient'])} | [{fmt(c['ci95_low'])}; {fmt(c['ci95_high'])}] | {fmt(c['p_value'])} | {fmt(study.get('primary_test',{}).get('bh_q_value'))} |")
        else:
            lines.append(f"| {spec['id']} | — | — | {spec['primary_term']} | brak estymacji | — | — | — |")
    lines+=['','Wskaźniki są ułamkami. Parametr kwadratu nie jest samodzielnym efektem marginalnym ani dowodem optimum.','']
    for study in result['studies']:
        spec=study['specification']
        lines += [f"## {spec['id']}: {spec['title']}",'',
            f"Y: `{spec['outcome']}(t+1)`. X: `{spec['exposure']}(t)`"+(' i kwadrat' if spec['quadratic'] else '')+'.',
            'Controls: '+', '.join(spec['controls'])+'.', '',
            'Przepływ próby: '+json.dumps(study['sample_flow'],ensure_ascii=False)+'.', '']
        fig,axes=plt.subplots(1,2,figsize=(11,4.1))
        for axis,variant,title in zip(axes,['untrimmed','winsor_01_99'],['Bez przycinania','Winsoryzacja 1/99']):
            estimates=[e for e in study['estimates'] if e['variant']==variant]
            for index,e in enumerate(estimates):
                if e['status']!='estimated':
                    continue
                c=e['coefficients'][spec['primary_term']]
                if any(c[k] is None for k in ['coefficient','ci95_low','ci95_high']):
                    continue
                value=c['coefficient']
                axis.errorbar(value,index,xerr=[[max(0,value-c['ci95_low'])],[max(0,c['ci95_high']-value)]],fmt='o',color='#126c73',capsize=5)
            axis.axvline(0,color='#84949a',linewidth=1,linestyle='--')
            axis.set_yticks([0,1],['Pooled + rok','FE firma + rok'])
            axis.set_ylim(-.6,1.6)
            axis.invert_yaxis()
            axis.set_title(title)
            axis.set_xlabel('Współczynnik i 95% CI')
            axis.grid(axis='x',alpha=.15)
        fig.suptitle(spec['id']+' • '+spec['primary_term'],fontsize=13)
        fig.text(.5,.015,'Analiza eksploracyjna • osobne skale osi X • SE klastrowane po firmie',ha='center',fontsize=9)
        fig.tight_layout(rect=[0,.05,1,.92])
        plot=output/(spec['id']+'_coefficients.png')
        fig.savefig(plot,dpi=160)
        plt.close(fig)
        lines += [f'![Współczynniki {spec["id"]}]({plot.as_posix()})','']
        for e in study['estimates']:
            lines += [f"### {e['model']} / {e['variant']}",'']
            if e['status']!='estimated':
                lines += ['Nie oszacowano: '+e.get('error',e['status'])+'.','']
                continue
            lines += [f"N={e['n_observations']:,}, firmy={e['n_companies']:,}, R²={fmt(e['r_squared'])}, within R²={fmt(e['within_r_squared'])}.",
                '| Parametr | Współczynnik | SE | 95% CI | p |','|---|---:|---:|---|---:|']
            for name,c in e['coefficients'].items():
                if name.startswith('year_'):
                    continue
                lines.append(f"| {name} | {fmt(c['coefficient'])} | {fmt(c['standard_error'])} | [{fmt(c['ci95_low'])}; {fmt(c['ci95_high'])}] | {fmt(c['p_value'])} |")
            lines+=['']
        if 'liquidity_sensitivity' in study:
            lines+=['### R01 bez liquidity','',
                'Wariant na tej samej próbie oddziela zmianę specyfikacji od zmiany składu firm. Wariant poszerzony pokazuje selekcję przez braki liquidity.', '',
                '| Próba | N | Firmy | Leverage β | 95% CI |','|---|---:|---:|---:|---|']
            for name in ['same_sample','expanded_sample']:
                e=study['liquidity_sensitivity'][name]
                if e['status']=='estimated':
                    c=e['coefficients'][spec['exposure']]
                    lines.append(f"| {name} | {e['n_observations']:,} | {e['n_companies']:,} | {fmt(c['coefficient'])} | [{fmt(c['ci95_low'])}; {fmt(c['ci95_high'])}] |")
            lines+=['']
    lines += ['## Ograniczenia wspólne','',
        '- Niepotwierdzona semantyka mapowań i skala części pozycji dostawcy; brak historii publikacji.',
        '- Nominalne wzrosty, bez deflatorów; skrajne ilorazy od małych dodatnich mianowników.',
        '- Brak PKD i lokalizacji uniemożliwia jeszcze zaplanowane segmentacje branżowe/regionalne.',
        '- Możliwy confounding, odwrotna zależność i selekcja kohorty; FE + lag nie dowodzi przyczynowości.',
        '- Niewielka liczba lat i możliwa zależność wewnątrz grup kapitałowych ograniczają wnioskowanie.',
        '- R²/within R² to miary estymatora; mogą być ujemne. Nie są jakością prognozy poza próbą.',
        '- Winsoryzacja zmienia rozkład i estymand; nie wybieramy wariantu ze względu na atrakcyjny znak/p.', '',
        'Konfiguracja estymatora: [linearmodels PanelOLS.fit](https://bashtage.github.io/linearmodels/panel/panel/linearmodels.panel.model.PanelOLS.fit.html).',
        'Pełne parametry, progi winsoryzacji, próbki i wersje bibliotek są zapisane w `research.run` i artefaktach runu.', '']
    text='\n'.join(lines)
    (output/'report.md').write_text(text,encoding='utf-8')
    (ROOT/'docs/RESEARCH_RESULTS.md').write_text(text,encoding='utf-8')
    print('Research report: '+str(ROOT/'docs/RESEARCH_RESULTS.md'))
