from fastapi.testclient import TestClient

from src.api import app


client = TestClient(app)


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
