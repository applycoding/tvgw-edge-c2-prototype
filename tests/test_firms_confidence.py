from tvgw.sources.firms import _parse_confidence


def test_firms_confidence_full_words():
    assert _parse_confidence("low") == 0.30
    assert _parse_confidence("nominal") == 0.65
    assert _parse_confidence("high") == 0.90
