"""Operator-facing message catalog for English and French.

French values are an unreviewed machine-assisted draft. They need qualified
human review before any use. The two catalogs use the same keys.
"""

from __future__ import annotations

CATALOG: dict[str, dict[str, str]] = {
    "en": {
        "report.msgid": "MSGID",
        "report.kind": "TVGW-SPOT-STANDIN",
        "report.dtg": "DTG",
        "report.src": "SRC",
        "report.dom": "DOM",
        "report.svc": "SVC",
        "report.obj": "OBJ",
        "report.conf": "CONF",
        "report.id": "ID",
        "report.loc": "LOC",
        "report.alt": "ALT",
        "report.rmk": "RMK",
        "report.end": "ENDAT",
        "cli.root.help": "Laboratory edge-to-C2 message gateway prototype.",
        "cli.lang": (
            "Label language: en or fr. French strings are an unreviewed "
            "machine-assisted draft."
        ),
        "cli.validate.help": "Validate held-out detections and print the text report.",
        "cli.validate.limit": "Maximum number of held-out detections to validate.",
        "cli.validate.summary": "validated {ok}/{total}",
        "cli.validate.rejected": "rejected {detection_id}: {reason}",
        "cli.replay.help": "Replay one simulated-link scenario and print delivery counts.",
        "cli.replay.rate": "Simulated link rate in bits per second.",
        "cli.replay.loss": "Simulated link target loss rate between 0 and 1.",
        "cli.replay.seed": "Scenario seed.",
        "cli.replay.scheduling": "Queue scheduling: priority or fifo.",
        "cli.metrics.scheduling": "Queue scheduling for the served scenario: priority or fifo.",
        "cli.replay.generated": "generated P0={p0} P1={p1} P2={p2}",
        "cli.replay.delivered_within": "delivered_within P0={p0} P1={p1} P2={p2}",
        "cli.replay.delivered_late": "delivered_late P0={p0} P1={p1} P2={p2}",
        "cli.replay.failed": "failed P0={p0} P1={p1} P2={p2}",
        "cli.replay.expired": "expired P0={p0} P1={p1} P2={p2}",
        "cli.replay.retries": "retries {n}",
        "cli.metrics.help": "Laboratory metrics commands.",
        "cli.metrics.serve.help": "Run one simulated scenario and serve Prometheus text at /metrics.",
        "cli.metrics.host": "Bind address. Defaults to 127.0.0.1.",
        "cli.metrics.port": "TCP port. 0 selects an ephemeral port.",
        "cli.metrics.listening": "serving metrics at http://{host}:{port}/metrics",
        "error.unsupported_language": "unsupported language: {lang}; expected en or fr",
        "error.expected_int": "expected an integer for {name}",
        "error.expected_float": "expected a number for {name}",
        "error.loss_range": "loss must be between 0 and 1",
        "error.rate_positive": "rate-bps must be greater than 0",
        "error.limit_nonnegative": "limit must be greater than or equal to 0",
        "error.seed_nonnegative": "seed must be greater than or equal to 0",
        "error.scheduling": "scheduling must be priority or fifo",
        "error.port": "port must be an integer from 0 to 65535",
        "error.host_empty": "host must be a non-empty bind address",
        "error.malformed_percent_escape": "malformed percent escape",
    },
    "fr": {
        "report.msgid": "IDMSG",
        "report.kind": "TVGW-SPOT-PROVISOIRE",
        "report.dtg": "GDH",
        "report.src": "SRE",
        "report.dom": "DMN",
        "report.svc": "SRV",
        "report.obj": "CBL",
        "report.conf": "NCF",
        "report.id": "IDE",
        "report.loc": "LIE",
        "report.alt": "ALTI",
        "report.rmk": "REM",
        "report.end": "FIN",
        "cli.root.help": "Prototype de laboratoire de passerelle de messages bord vers C2.",
        "cli.lang": (
            "Langue des libellés : en ou fr. Les chaînes françaises sont un brouillon "
            "assisté par machine, non relu."
        ),
        "cli.validate.help": (
            "Valider des détections du corpus tenu à l'écart et imprimer le compte rendu textuel."
        ),
        "cli.validate.limit": "Nombre maximal de détections du corpus tenu à l'écart à valider.",
        "cli.validate.summary": "validées {ok}/{total}",
        "cli.validate.rejected": "rejetée {detection_id} : {reason}",
        "cli.replay.help": "Rejouer un scénario de lien simulé et imprimer les comptes de livraison.",
        "cli.replay.rate": "Débit du lien simulé, en bits par seconde.",
        "cli.replay.loss": "Taux de perte cible du lien simulé, entre 0 et 1.",
        "cli.replay.seed": "Graine du scénario.",
        "cli.replay.scheduling": "Ordonnancement de la file : priority ou fifo.",
        "cli.metrics.scheduling": "Ordonnancement du scénario exposé : priority ou fifo.",
        "cli.replay.generated": "générés P0={p0} P1={p1} P2={p2}",
        "cli.replay.delivered_within": "livrés dans le délai P0={p0} P1={p1} P2={p2}",
        "cli.replay.delivered_late": "livrés en retard P0={p0} P1={p1} P2={p2}",
        "cli.replay.failed": "échecs P0={p0} P1={p1} P2={p2}",
        "cli.replay.expired": "expirés P0={p0} P1={p1} P2={p2}",
        "cli.replay.retries": "retransmissions {n}",
        "cli.metrics.help": "Commandes de mesures de laboratoire.",
        "cli.metrics.serve.help": (
            "Exécuter un scénario simulé et exposer le texte Prometheus sur /metrics."
        ),
        "cli.metrics.host": "Adresse d'écoute. Valeur par défaut : 127.0.0.1.",
        "cli.metrics.port": "Port TCP. 0 choisit un port éphémère.",
        "cli.metrics.listening": "exposition des mesures à http://{host}:{port}/metrics",
        "error.unsupported_language": "langue non prise en charge : {lang} ; attendu : en ou fr",
        "error.expected_int": "entier attendu pour {name}",
        "error.expected_float": "nombre attendu pour {name}",
        "error.loss_range": "la perte doit être comprise entre 0 et 1",
        "error.rate_positive": "rate-bps doit être supérieur à 0",
        "error.limit_nonnegative": "limit doit être supérieur ou égal à 0",
        "error.seed_nonnegative": "seed doit être supérieur ou égal à 0",
        "error.scheduling": "scheduling doit être priority ou fifo",
        "error.port": "port doit être un entier de 0 à 65535",
        "error.host_empty": "host doit être une adresse d'écoute non vide",
        "error.malformed_percent_escape": "séquence d'échappement pourcent mal formée",
    },
}


def supported_languages() -> tuple[str, ...]:
    return tuple(sorted(CATALOG))


def translate(lang: str, key: str, **kwargs: str | int | float) -> str:
    try:
        template = CATALOG[lang][key]
    except KeyError as exc:
        raise KeyError(f"{lang}:{key}") from exc
    return template.format(**kwargs)


def unsupported_language_text(requested: str) -> str:
    en = CATALOG["en"]["error.unsupported_language"].format(lang=requested)
    fr = CATALOG["fr"]["error.unsupported_language"].format(lang=requested)
    return en + "\n" + fr + "\n"


def report_token_index() -> dict[str, str]:
    """Map a slash-report set token to its catalog key.

    English and French tokens must not collide with each other or with a
    different key.
    """
    index: dict[str, str] = {}
    for table in CATALOG.values():
        for key, token in table.items():
            if not key.startswith("report."):
                continue
            previous = index.get(token)
            if previous is not None and previous != key:
                raise RuntimeError(f"report token collision: {token!r} ({previous} vs {key})")
            index[token] = key
    return index


REPORT_TOKEN_TO_KEY = report_token_index()
