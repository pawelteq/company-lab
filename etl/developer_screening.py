"""Conservative, explainable screening of provider descriptions, not verified labels.

Only the company's own summary is considered. PKD and names alone cannot qualify
a company. Website/brand mismatch, third-party mentions and missing descriptions
remain outside the default analytical shortlist.
"""
import re
import unicodedata

VERSION = 'summary-screening-v1'
NAME_SIGNAL_RE = re.compile(r'(?i)(?:\bdev(?:elop(?:ment|er)?)?\b|\bdeweloper\w*\b|\binwest\w*\b|\binvest\w*\b|\bnieruchom\w*\b|\bproperty\b|\breal estate\b|\bresiden\w*\b|\bapartament\w*\b|\bmieszkan\w*\b|\bosiedl\w*\b|\bdomy?\b)')
LABELS = {
    'developer_candidate': 'Deweloper według opisu',
    'other_activity': 'Opis innej działalności',
    'review': 'Do sprawdzenia',
    'missing_summary': 'Brak opisu',
}


def normalized(value):
    value = value.lower().replace('ł', 'l')
    return ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c))


def extract_summary(payload):
    company = payload.get('company') or {}
    direct = company.get('company_summary')
    if isinstance(direct, str) and direct.strip():
        return direct.strip(), '/company/company_summary'
    fallback = payload.get('companySummary')
    if isinstance(fallback, dict):
        for language in ('en', 'pl'):
            if isinstance(fallback.get(language), str) and fallback[language].strip():
                return fallback[language].strip(), '/companySummary/' + language
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip(), '/companySummary'
    return None, None


def identity_matches(name, summary, krs):
    mentioned = re.findall(r'\bKRS\s*(?:number\s*|:)?\s*(\d{10})\b', summary, re.I)
    if mentioned and any(value != krs for value in mentioned):
        return False
    stop = {'spolka','spolki','akcyjna','komandytowa','komandytowo','odpowiedzialnoscia',
            'ograniczona','jawna','likwidacji','upadlosci','polska','poland','group',
            'grupa','development','investments','investment','inwestycje','inwest',
            'construction','przedsiebiorstwo','budowlane','budownictwo','deweloper',
            'grupy','financing','pool','projekt','company','real','estate'}
    tokens = {t for t in re.findall(r'\w+', normalized(name or '')) if len(t) >= 3 and t not in stop}
    # Compare the description's subject, not an arbitrary client mentioned later.
    subject = re.split(r'\b(?:is|are|specializes|offers|provides|builds|develops|operates|sells|designs)\b',
                       normalized(summary), maxsplit=1)[0][:180]
    if tokens:
        return any(re.search(r'(?<!\w)' + re.escape(t) + r'(?!\w)', subject) for t in tokens)
    short = re.findall(r'\b\d[a-z]\b', normalized(name or ''))
    return bool(short and any(re.search(r'\b'+re.escape(t)+r'\b',subject) for t in short))


def classify(name, summary, krs=''):
    name_signal = bool(NAME_SIGNAL_RE.search(normalized(name or '')))
    base = {'status': 'missing_summary', 'reason': 'Brak company_summary. Sam kod PKD nie wystarcza do kwalifikacji.',
            'evidence': [], 'flags': [], 'method': VERSION, 'verified': False, 'segment': 'unknown',
            'name_signal': name_signal,
            'name_signal_reason': 'Nazwa zawiera słowo sugerujące nieruchomości/deweloperkę; wymaga sprawdzenia opisu lub strony.' if name_signal else None}
    if not summary:
        return base
    text = normalized(summary)
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])', summary)
    has = lambda pattern: bool(re.search(pattern, text))
    identity = identity_matches(name, summary, krs)
    if not identity:
        base['flags'].append('Opis może dotyczyć innej marki lub podmiotu; sprawdź przypisanie strony do KRS.')
    residential = has(r'\b(residential|apartments?|housing|homes?|mieszkan\w*|osiedl\w*)\b')
    commercial = has(r'\b(commercial|warehouses?|logistics|industrial|office|retail parks?|shopping|komercyjn\w*|magazyn\w*)\b')
    base['segment'] = 'mixed' if residential and commercial else 'residential' if residential else 'commercial' if commercial else 'unknown'
    positive_patterns = [
        r'\b(?:is|as) (?:an? |the )?(?:(?:leading|polish|experienced|residential|real estate|property|regional|warsaw-based)\s+){0,3}developer\b',
        r'\b(?:specializ\w*|engaged|involved|focus\w*|operat\w*)\b[^.!?]{0,90}\b(?:real estate|property) development\b',
        r'\b(?:is|as) (?:an? )?(?:real estate|property|residential) develop(?:ment company|er)\b',
        r'\b(?:builds?|constructs?|construction|building|development)\s+and\s+(?:sells?|sale)\b[^.!?]{0,65}\b(?:apartments?|houses?|homes?|residential)\b',
        r'\bdevelops\s+(?:(?:modern|new|residential|commercial|luxury)\s+)*(?:housing|estates|apartments|houses|properties|warehouses|office)\b',
        r'\b(?:jest|jako)\s+(?:firma\s+)?deweloper\w*\b',
    ]
    evidence = [s for s in sentences
                if (identity_matches(name, s, krs) or re.match(r'^(?:the company|they|it)\b', normalized(s)))
                and any(re.search(p, normalized(s)) for p in positive_patterns)]
    other = has(r'\b(?:portal|blog|publishes guides|online gaming|thatching tools|manufacturer|repair and production services|real estate agency|brokerage|estate agent|construction services|general contractor|construction company)\b')
    ambiguous = has(r'\b(?:not a|not an|does not|no longer|formerly|previously|used to|for developers|to developers|supports developers|supporting investors|clients include|customers include|software|online gaming|renewable energy|solar farms|wind farms)\b')
    if evidence and identity and (residential or commercial) and not ambiguous:
        base.update(status='developer_candidate', reason='Opis wskazuje wprost działalność deweloperską lub budowę i sprzedaż nieruchomości.', evidence=evidence)
    elif other and not evidence:
        base.update(status='other_activity', reason='Opis wskazuje portal, wykonawstwo, pośrednictwo, produkcję lub inną działalność. Nie potwierdza roli dewelopera.', evidence=sentences[:2])
    else:
        base.update(status='review', reason='Opis nie daje jednoznacznej kwalifikacji konkretnej spółki jako dewelopera.', evidence=evidence or sentences[:2])
    if ambiguous:
        base['flags'].append('Opis zawiera relacje z innymi podmiotami, zmianę działalności lub zaprzeczenie; wymaga interpretacji.')
    return base
