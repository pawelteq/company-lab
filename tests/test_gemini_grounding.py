"""Unit tests for Gemini Grounding developer verification."""
import pytest
from unittest.mock import patch, MagicMock
from backend.gemini_grounding import (
    format_company_prompt,
    parse_gemini_response,
    verify_company,
    get_api_key,
)


def test_format_company_prompt():
    company = {
        "name": "PRO-BUD SP. Z O.O.",
        "krs": "0000123456",
        "nip": "1234567890",
        "city": "Kołobrzeg",
        "primary_pkd": "41.20.Z",
        "primary_pkd_description": "Roboty budowlane związane ze wznoszeniem budynków",
        "screening": {"reason": "Opis wskazuje na dewelopera", "status": "developer_candidate"}
    }
    prompt = format_company_prompt(company)
    assert "PRO-BUD SP. Z O.O." in prompt
    assert "0000123456" in prompt
    assert "Kołobrzeg" in prompt
    assert "41.20.Z" in prompt
    assert "deweloper" in prompt.lower()


def test_parse_gemini_response_tak():
    mock_data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                "WERDYKT: TAK\n"
                                "CZY_DEWELOPER: PRAWDA\n"
                                "PEWNOŚĆ: WYSOKA\n"
                                "PODSUMOWANIE: Tak, Pro-Bud prowadzi działalność deweloperską na terenie Kołobrzegu i Pomorza.\n"
                                "SZCZEGÓŁY:\n"
                                "- Spółka zrealizowała osiedla mieszkaniowe i apartamentowce w Kołobrzegu.\n"
                                "- Na oficjalnej stronie pro-bud.pl oferuje sprzedaż mieszkań z rynku pierwotnego.\n"
                            )
                        }
                    ]
                },
                "groundingMetadata": {
                    "webSearchQueries": ["PRO-BUD Kołobrzeg deweloper mieszkania"],
                    "groundingChunks": [
                        {
                            "web": {
                                "title": "PRO-BUD - Inwestycje mieszkaniowe",
                                "uri": "https://pro-bud.pl/inwestycje"
                            }
                        },
                        {
                            "web": {
                                "title": "RynekPierwotny.pl - PRO-BUD",
                                "uri": "https://rynekpierwotny.pl/deweloperzy/pro-bud"
                            }
                        }
                    ]
                }
            }
        ]
    }
    result = parse_gemini_response(mock_data)
    assert result["verdict"] == "TAK"
    assert result["is_developer"] is True
    assert result["confidence"] == "WYSOKA"
    assert "Pro-Bud prowadzi działalność deweloperską" in result["summary"]
    assert len(result["details"]) == 2
    assert len(result["sources"]) == 2
    assert result["sources"][0]["title"] == "PRO-BUD - Inwestycje mieszkaniowe"
    assert result["sources"][0]["url"] == "https://pro-bud.pl/inwestycje"
    assert len(result["search_queries"]) == 1


def test_parse_gemini_response_nie():
    mock_data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                "WERDYKT: NIE\n"
                                "CZY_DEWELOPER: FAŁSZ\n"
                                "PEWNOŚĆ: WYSOKA\n"
                                "PODSUMOWANIE: Firma działa wyłącznie jako hurtownia materiałów budowlanych, a nie deweloper.\n"
                                "SZCZEGÓŁY:\n"
                                "- Brak inwestycji deweloperskich i sprzedaży mieszkań.\n"
                                "- Działalność skupiona na sprzedaży hurtowej cementu i stali.\n"
                            )
                        }
                    ]
                },
                "groundingMetadata": {
                    "webSearchQueries": ["Hurtownia Budowlana KRS deweloper"],
                    "groundingChunks": []
                }
            }
        ]
    }
    result = parse_gemini_response(mock_data)
    assert result["verdict"] == "NIE"
    assert result["is_developer"] is False
    assert result["confidence"] == "WYSOKA"
    assert "hurtownia materiałów budowlanych" in result["summary"]


def test_verify_company_missing_key():
    with patch("backend.gemini_grounding.get_api_key", return_value=None):
        with pytest.raises(ValueError, match="Brak klucza Gemini API"):
            verify_company({"name": "Test"}, api_key="")


@patch("backend.gemini_grounding.httpx.Client")
def test_verify_company_success(mock_client_cls):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "WERDYKT: TAK\nCZY_DEWELOPER: PRAWDA\nPODSUMOWANIE: Tak, to deweloper.\nSZCZEGÓŁY:\n- Inwestycja X"}]
                },
                "groundingMetadata": {"webSearchQueries": ["test"]}
            }
        ]
    }
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    result = verify_company({"name": "Test Company"}, api_key="AIzaSyDummyKey")
    assert result["verdict"] == "TAK"
    assert result["is_developer"] is True
    assert result["summary"] == "Tak, to deweloper."
