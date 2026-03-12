from src.collectors.odds_collector import _sanitize_entries


def test_sanitize_entries_keeps_requested_betano_markets():
    entries = [
        {"market_type": "correct_score", "selection": "2 - 1", "odds_value": 4.45},
        {"market_type": "over_maps", "selection": "Mais de 2.5", "odds_value": 2.02},
        {"market_type": "over_maps", "selection": "Menos de 2.5", "odds_value": 1.75},
        {"market_type": "map1_ot", "selection": "Sim", "odds_value": 5.80, "map_number": 1},
        {"market_type": "map1_ot", "selection": "Não", "odds_value": 1.11, "map_number": 1},
        {"market_type": "handicap_match", "selection": "XLG Esports -1.5", "odds_value": 5.40},
        {"market_type": "handicap_match", "selection": "NRG Esports +1.5", "odds_value": 1.12},
        {"market_type": "map1_pistol_1h", "selection": "XLG Esports", "odds_value": 2.00, "map_number": 1},
        {"market_type": "map1_pistol", "selection": "NRG Esports", "odds_value": 1.75, "map_number": 1},
        {"market_type": "map1_pistol_correct_score", "selection": "1-1", "odds_value": 1.83, "map_number": 1},
    ]

    cleaned = _sanitize_entries(
        entries=entries,
        bookmaker="betano",
        team1="Xi Lai Gaming",
        team2="NRG",
        team1_tag="XLG",
        team2_tag="NRG",
    )

    got = {
        (item["market_type"], item["selection"], item["map_number"])
        for item in cleaned
    }

    assert ("correct_score", "2-1", None) in got
    assert ("over_maps", "Over 2.5", None) in got
    assert ("over_maps", "Under 2.5", None) in got
    assert ("map1_ot", "Yes", 1) in got
    assert ("map1_ot", "No", 1) in got
    assert ("handicap_match", "Xi Lai Gaming -1.5", None) in got
    assert ("handicap_match", "NRG +1.5", None) in got
    assert ("map1_pistol_1h", "Xi Lai Gaming", 1) in got
    assert ("map1_pistol", "NRG", 1) in got
    assert ("map1_pistol_correct_score", "1-1", 1) in got


def test_sanitize_entries_drops_invalid_joined_winner_rows():
    entries = [
        {"market_type": "map1_winner", "selection": "XLG Esports", "odds_value": 2.55, "map_number": 1},
        {"market_type": "map1_winner", "selection": "NRG Esports", "odds_value": 1.47, "map_number": 1},
        {"market_type": "map1_winner", "selection": "XLG Esports NRG Esports", "odds_value": 2.55, "map_number": 1},
    ]

    cleaned = _sanitize_entries(
        entries=entries,
        bookmaker="betano",
        team1="Xi Lai Gaming",
        team2="NRG",
        team1_tag="XLG",
        team2_tag="NRG",
    )

    selections = {item["selection"] for item in cleaned}
    assert "Xi Lai Gaming" in selections
    assert "NRG" in selections
    assert "XLG Esports NRG Esports" not in selections


def test_sanitize_entries_preserves_handicap_and_total_maps_lines():
    entries = [
        {"market_type": "handicap_match", "selection": "XLG Esports -1.5", "odds_value": 5.40},
        {"market_type": "handicap_match", "selection": "NRG Esports +1.5", "odds_value": 1.12},
        {"market_type": "over_maps", "selection": "Mais de 2.5", "odds_value": 2.02},
        {"market_type": "over_maps", "selection": "Menos de 2.5", "odds_value": 1.75},
    ]

    cleaned = _sanitize_entries(
        entries=entries,
        bookmaker="betano",
        team1="Xi Lai Gaming",
        team2="NRG",
        team1_tag="XLG",
        team2_tag="NRG",
    )

    got = {(item["market_type"], item["selection"]) for item in cleaned}
    assert ("handicap_match", "Xi Lai Gaming -1.5") in got
    assert ("handicap_match", "NRG +1.5") in got
    assert ("over_maps", "Over 2.5") in got
    assert ("over_maps", "Under 2.5") in got
