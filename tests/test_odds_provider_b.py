from src.collectors.odds_provider_b import ProviderBScraper


def test_team_aliases_include_name_and_tag_forms():
    aliases = ProviderBScraper._team_aliases("Xi Lai Gaming", "XLG")
    assert "xi lai gaming" in aliases
    assert "xilaigaming" in aliases
    assert "xlg" in aliases


def test_extract_map_number_and_market_type_mapping():
    scraper = ProviderBScraper()

    assert scraper._extract_map_number("map 2 winner") == 2
    assert scraper._map_market_type("map 2 winner", 2) == "map2_winner"
    assert scraper._map_market_type("map 3 overtime", 3) == "map3_ot"
    assert scraper._map_market_type("total de rounds impares pares mapa 1", 1) is None
    assert scraper._map_market_type("match winner", None) == "match_winner"


def test_decimal_parser_handles_decimal_and_american():
    scraper = ProviderBScraper()

    assert scraper._to_decimal("1.95") == 1.95
    assert round(scraper._to_decimal("+120"), 2) == 2.20
    assert round(scraper._to_decimal("-110"), 4) == round(1 + (100 / 110), 4)


def test_parse_markets_from_node_maps_outcomes_correctly():
    scraper = ProviderBScraper()
    node = {
        "name": "Xi Lai Gaming vs NRG",
        "markets": [
            {
                "name": "Map 1 Winner",
                "outcomes": [
                    {"name": "home", "odds": "2.10"},
                    {"name": "away", "odds": "1.72"},
                ],
            },
            {
                "name": "Total Maps",
                "odds": [
                    {"line": 2.5, "over": "1.80", "under": "2.05"},
                ],
            },
        ],
    }

    parsed = scraper._parse_markets_from_node(node, team1="Xi Lai Gaming", team2="NRG")

    assert any(item["market_type"] == "map1_winner" and item["selection"] == "Xi Lai Gaming" for item in parsed)
    assert any(item["market_type"] == "map1_winner" and item["selection"] == "NRG" for item in parsed)
    assert any(item["market_type"] == "over_maps_2_5" for item in parsed)
    assert any(item["market_type"] == "under_maps_2_5" for item in parsed)


def test_extract_selection_price_pairs_parses_multiple_pairs():
    pairs = ProviderBScraper._extract_selection_price_pairs("Sim 5.80 Não 1.11")
    assert pairs == [("Sim", "5.80"), ("Não", "1.11")]


def test_extract_ot_entries_from_page_text_reads_yes_no():
    scraper = ProviderBScraper()
    text = (
        "Prorrogação (Mapa 1) Sim 5.80 Não 1.11 "
        "Prorrogação (Mapa 2) Sim 5.80 Não 1.11 "
        "Prorrogação (Mapa 3) Sim 5.80 Não 1.12"
    )
    entries = scraper._extract_ot_entries_from_page_text(text)
    got = {(item["market_type"], item["selection"], item["odds_value"]) for item in entries}
    assert ("map1_ot", "Sim", 5.8) in got
    assert ("map1_ot", "Não", 1.11) in got
    assert ("map2_ot", "Sim", 5.8) in got
    assert ("map2_ot", "Não", 1.11) in got
    assert ("map3_ot", "Sim", 5.8) in got
    assert ("map3_ot", "Não", 1.12) in got
