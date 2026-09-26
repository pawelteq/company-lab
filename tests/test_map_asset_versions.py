"""Keep iframe map cache-busters tied to the files they load."""
from hashlib import sha256
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _token(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()[:12]


def test_financial_map_asset_versions_match_content():
    map_dir = ROOT / "frontend" / "public" / "maps"
    script = map_dir / "poland.js"
    document = map_dir / "poland.html"
    component = ROOT / "frontend" / "src" / "FinancialMap.tsx"

    script_reference = re.search(r'poland\.js\?v=([a-f0-9]{12})', document.read_text(encoding="utf-8"))
    assert script_reference, "poland.html musi mieć 12-znakową wersję poland.js"
    assert script_reference.group(1) == _token(script)

    document_reference = re.search(
        r'poland\.html\?financial=1&amp;v=([a-f0-9]{12})|poland\.html\?financial=1&v=([a-f0-9]{12})',
        component.read_text(encoding="utf-8"),
    )
    assert document_reference, "FinancialMap musi wersjonować poland.html jego skrótem treści"
    assert next(group for group in document_reference.groups() if group) == _token(document)
