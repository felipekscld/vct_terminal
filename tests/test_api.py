from fastapi.testclient import TestClient

from src.api import app
from src.db.connection import get_db


client = TestClient(app)


def _ensure_match(match_id: int) -> None:
    event_id = 999001
    team1_id = 999011
    team2_id = 999012
    with get_db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO events (id, name)
               VALUES (?, ?)""",
            (event_id, "Test Event"),
        )
        conn.execute(
            """INSERT OR IGNORE INTO teams (id, name, tag)
               VALUES (?, ?, ?)""",
            (team1_id, "Test Team A", "TTA"),
        )
        conn.execute(
            """INSERT OR IGNORE INTO teams (id, name, tag)
               VALUES (?, ?, ?)""",
            (team2_id, "Test Team B", "TTB"),
        )
        conn.execute(
            """INSERT OR IGNORE INTO matches
               (id, event_id, team1_id, team2_id, bo_type, status, date, time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (match_id, event_id, team1_id, team2_id, "bo3", "upcoming", "2026-01-01", "12:00"),
        )


def test_health_endpoint():
    response = client.get('/api/health')
    assert response.status_code == 200
    payload = response.json()
    assert 'status' in payload
    assert 'db_ok' in payload


def test_matches_endpoint_shape():
    response = client.get('/api/matches?limit=5')
    assert response.status_code == 200
    payload = response.json()
    assert 'items' in payload
    assert isinstance(payload['items'], list)


def test_config_roundtrip_minimal():
    get_response = client.get('/api/config')
    assert get_response.status_code == 200
    current = get_response.json()

    payload = {
        'bankroll': {
            'total': current['bankroll']['total'],
            'max_stake_pct': current['bankroll']['max_stake_pct'],
            'daily_limit': current['bankroll']['daily_limit'],
            'event_limit': current['bankroll']['event_limit'],
            'kelly_fraction': current['bankroll']['kelly_fraction'],
        }
    }

    put_response = client.put('/api/config', json=payload)
    assert put_response.status_code == 200
    assert 'bankroll' in put_response.json()


def test_auto_odds_partial_success(monkeypatch):
    match_id = 999101
    _ensure_match(match_id)

    def fake_collect(mid):
        assert mid == match_id
        return {
            "inserted": 4,
            "bookmakers": {
                "betano": {"scraped": 4, "inserted": 4, "source": "betano_scraping", "error": None},
                "bet365": {
                    "scraped": 0,
                    "inserted": 0,
                    "source": "disabled",
                    "error": "Integracao automatica da bet365 desativada neste projeto.",
                },
            },
        }

    monkeypatch.setattr("src.api.collect_odds_from_sites", fake_collect)

    response = client.post(f"/api/matches/{match_id}/odds/auto")
    assert response.status_code == 200
    payload = response.json()
    assert payload["inserted"] == 4
    assert payload["source"] == "betano_scraping"
    assert payload["partial_success"] is True
    assert any("bet365" in warning.lower() for warning in payload["warnings"])


def test_auto_odds_failure_when_nothing_inserted(monkeypatch):
    match_id = 999102
    _ensure_match(match_id)

    def fake_collect(_):
        return {
            "inserted": 0,
            "bookmakers": {
                "betano": {"scraped": 0, "inserted": 0, "source": "betano_scraping", "error": "Nao encontrado"},
                "bet365": {
                    "scraped": 0,
                    "inserted": 0,
                    "source": "disabled",
                    "error": "Integracao automatica da bet365 desativada neste projeto.",
                },
            },
        }

    monkeypatch.setattr("src.api.collect_odds_from_sites", fake_collect)

    response = client.post(f"/api/matches/{match_id}/odds/auto")
    assert response.status_code == 502
    payload = response.json()
    assert payload["error"] == "auto_scrape_failed"
    assert payload["inserted"] == 0
    assert len(payload["warnings"]) == 2
