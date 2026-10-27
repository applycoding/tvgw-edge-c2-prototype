import io
import string

import pytest

from tvgw.cli import main
from tvgw.messages import CATALOG, supported_languages, translate


def _formatter_fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_catalog_keys_match_both_ways():
    assert supported_languages() == ("en", "fr")
    english = set(CATALOG["en"])
    french = set(CATALOG["fr"])
    assert english == french
    assert english
    for key in english:
        assert CATALOG["en"][key].strip()
        assert CATALOG["fr"][key].strip()
        assert _formatter_fields(CATALOG["en"][key]) == _formatter_fields(CATALOG["fr"][key])


def test_report_labels_differ_by_language():
    for key in (
        "report.msgid",
        "report.dtg",
        "report.end",
        "report.loc",
        "cli.validate.summary",
        "error.malformed_percent_escape",
    ):
        assert CATALOG["en"][key] != CATALOG["fr"][key]


def test_translate_unknown_language():
    with pytest.raises(KeyError):
        translate("de", "cli.root.help")


def test_french_and_english_help_and_validation(capsys):
    with pytest.raises(SystemExit) as french_help:
        main(["validate", "--lang", "fr", "--help"])
    assert french_help.value.code == 0
    french_out = " ".join(capsys.readouterr().out.split())
    assert "Valider des détections" in french_out
    assert "Validate held-out" not in french_out

    with pytest.raises(SystemExit) as english_help:
        main(["replay", "--lang", "en", "--help"])
    assert english_help.value.code == 0
    english_out = " ".join(capsys.readouterr().out.split())
    assert "Replay one simulated-link scenario" in english_out
    assert "Rejouer un scénario" not in english_out

    with pytest.raises(SystemExit) as bad_limit:
        main(["validate", "--lang", "fr", "--limit", "nope"])
    assert bad_limit.value.code == 2
    assert "entier attendu" in capsys.readouterr().err

    with pytest.raises(SystemExit) as bad_loss:
        main(["replay", "--lang", "en", "--loss", "2"])
    assert bad_loss.value.code == 2
    assert "loss must be between 0 and 1" in capsys.readouterr().err

    err = io.StringIO()
    with pytest.raises(SystemExit) as bad_lang:
        main(["replay", "--lang", "de", "--help"])
    assert bad_lang.value.code == 2
    captured = capsys.readouterr()
    assert "unsupported language: de" in captured.err
    assert "langue non prise en charge" in captured.err
    assert err.getvalue() == ""


def test_metrics_help_is_catalogued(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["metrics", "serve", "--lang", "fr", "--help"])
    assert caught.value.code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "texte Prometheus" in text
    assert "Run one simulated scenario" not in text
