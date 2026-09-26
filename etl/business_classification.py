"""Versioned user-defined heuristics; never a claim of verified business activity."""
import json
import math
import re
import statistics
from pathlib import Path
from etl.developer_screening import normalized

RULES = json.loads(Path(__file__).with_name('business_rules.json').read_text(encoding='utf-8'))
VERSION = RULES['version']

def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None

def annual_financials(profile):
    """Full calendar-year standalone PLN. Conflicting duplicates remain missing."""
    years = {}
    for f in profile.get('financials') or []:
        start = str(f.get('period_from_resolved') or f.get('sf_period_from') or '')[:10]
        end = str(f.get('period_to_resolved') or f.get('sf_period_to') or '')[:10]
        if f.get('currency') != 'PLN' or f.get('consolidation_scope') != 'standalone':
            continue
        if not re.fullmatch(r'\d{4}-01-01', start) or end != start[:4]+'-12-31':
            continue
        values = (number(f.get('revenue_total')), number(f.get('profit_net')))
        years.setdefault(int(end[:4]), set()).add(values)
    return [{'year': y, 'revenue': next(iter(v))[0] if len(v)==1 else None,
             'profit': next(iter(v))[1] if len(v)==1 else None, 'conflict': len(v)>1}
            for y,v in sorted(years.items())]

def matches(text, words):
    return [word for word in words if re.search(r'(?<!\w)'+re.escape(normalized(word))+r'(?!\w)', text)]

def classify_profile(p):
    name = normalized(p.get('name') or '')
    old = p.get('screening') or {}
    pkd = re.sub(r'[^A-Z0-9]', '', str((p.get('primary_pkd') or {}).get('code') or '').upper())
    annual = annual_financials(p)
    latest = annual[-1] if annual else {}
    recent = annual[-4:]
    revenues = [r['revenue'] for r in recent]
    consecutive = len(recent)>=3 and all(b['year']==a['year']+1 for a,b in zip(recent,recent[1:]))
    stable = consecutive and all(v is not None and v>0 for v in revenues) and statistics.pstdev(revenues)/statistics.mean(revenues)<=.20 and max(revenues)/min(revenues)<=1.5
    jump = any(b['year']==a['year']+1 and a['revenue'] is not None and b['revenue'] is not None and 0<=a['revenue']<=100000 and b['revenue']>=max(1000000,10*a['revenue']) for a,b in zip(annual,annual[1:]))
    positive = matches(name,RULES['developer'])
    negative = matches(name,RULES['exclusions'])
    strong = matches(name,['development','developer','deweloper','spv'])
    spv = bool(re.search(r'\b(?:projekt|inwestycja)\s+\d+\b|\b(?:etap|faza)\s+(?:\d+|[ivxlcdm]+)\b|\bspv\b',name))
    brand = matches(name,['robyg','lokum','spravia','marvipol','murapol','atal','archicom','cavatina','panattoni','7r','cordia','j.w. construction','jw construction','develia','inpro'])
    # A brand alone does not establish a project; require additional name text.
    stripped = re.sub(r'\b(?:spolka|z|ograniczona|odpowiedzialnoscia|sp|zoo|o|s|a|sa|akcyjna|komandytowa)\b','',name)
    brand_project = bool(brand and re.search(r'\w{3,}|\d+', stripped.replace(normalized(brand[0]),'').strip()))
    spv = spv or brand_project
    exceptional = matches(name,['biuro projektowe','biuro architektoniczne','pracownia architektoniczna','handel materialami','sprzedaz materialow','hurtownia','sklad budowlany'])
    nonconstruction = matches(name,['posrednictwo nieruchomosci','biuro nieruchomosci','agencja nieruchomosci','zarzadzanie nieruchomosciami','administracja nieruchomosci','zarzadca','spoldzielnia mieszkaniowa','wspolnota mieszkaniowa','rzeczoznawca','hurtownia','sklad budowlany','sprzedaz materialow','handel materialami','transport','trans-bud','betoniarnia','kruszywa'])
    ambiguous_bud = bool(re.search(r'\bbud\b|\w+bud\b|\bbud\w+',name))
    if strong or spv:
        kind, reason = ('spv' if spv else 'developer'), 'Mocny sygnał deweloperski / wzorzec spółki projektowej w nazwie.'
    elif pkd=='6812A' and not exceptional:
        kind, reason = 'developer','Główne PKD 68.12.A ma pierwszeństwo.'
    elif exceptional:
        kind, reason = 'other','Nazwa wprost wskazuje biuro projektowe lub handel materiałami: '+', '.join(exceptional)
    elif old.get('segment') in ('residential','commercial','mixed') or old.get('status')=='developer_candidate':
        kind, reason = 'developer','Wcześniejszy opis lub segment wskazuje działalność deweloperską.'
    elif negative:
        kind, reason = ('other' if nonconstruction or exceptional else 'contractor'), 'Słowa wykluczające w nazwie: '+', '.join(negative)
    elif old.get('status')=='other_activity':
        description = normalized(p.get('summary') or '')
        construction = matches(description,['wykonawca','generalny wykonawca','uslugi budowlane','remonty','construction services','contractor','roboty budowlane'])
        kind, reason = ('contractor' if construction else 'other'), 'Wcześniejszy opis innej działalności: '+str(old.get('reason') or '')
    elif pkd=='4110Z' and jump:
        kind, reason = 'spv','PKD 41.10.Z i skok przychodu po roku o małej sprzedaży — prawdopodobny projekt.'
    elif ambiguous_bud and (latest.get('revenue') or 0)>5000000:
        kind, reason = 'needs_web_grounding','Neutralna nazwa budowlana, przychód >5 mln PLN i brak rozstrzygającego opisu.'
    elif stable:
        kind, reason = 'contractor','Pomocnicza heurystyka: 3–4 kolejne lata, CV ≤20%, maksimum/minimum ≤1,5, dodatnie przychody.'
    elif positive:
        kind, reason = 'developer','Sygnały w nazwie (kwalifikacja heurystyczna): '+', '.join(positive)
    else:
        kind, reason = 'review','Za mało danych do rozstrzygnięcia; samo „bud” jest neutralne.'
    inactive = bool(matches(name,['w likwidacji','w upadlosci'])) or p.get('provider_status')=='inactive' or bool(p.get('is_currently_suspended'))
    active = False if inactive else True if p.get('provider_status')=='active' else None
    return {'version':VERSION,'business_type':kind,'reason':reason,'verified':False,'is_active':active,
            'name_evidence':positive,'exclusions':negative,'probable_spv':spv or kind=='spv',
            'revenue_stable':bool(stable),'revenue_jump':jump,'annual_period':str(latest['year'])+'-12-31' if latest else None,
            'annual_revenue':latest.get('revenue'),'annual_profit':latest.get('profit'),'annual_currency':'PLN' if latest else None,
            'annual_years':len(annual),'grounding_status':'pending_provider' if kind=='needs_web_grounding' else 'not_required',
            'grounding_query':f"{p.get('name') or ''} {p.get('city') or ''} inwestycje mieszkaniowe sprzedaż mieszkań deweloper" if kind=='needs_web_grounding' else None}
