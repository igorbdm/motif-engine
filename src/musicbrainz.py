"""Acesso ao MusicBrainz, usado para a origem (countries.py) e o gênero (genres.py).

O MusicBrainz pede no máximo uma consulta por segundo. Se ele estiver
ocupado, a consulta é repetida algumas vezes antes de desistir (Unavailable).
"""

import time
import unicodedata

import requests

API_URL = "https://musicbrainz.org/ws/2"
HEADERS = {"User-Agent": "motif-engine/1.1 (+https://github.com/igorbdm/motif-engine)"}
REQUEST_INTERVAL = 1.1
RETRIES = 4
MIN_SCORE = 90

_last_request = 0.0


class Unavailable(Exception):
    """O MusicBrainz não respondeu; o artista é procurado de novo na próxima coleta."""


def call_api(path, **params):
    global _last_request

    for attempt in range(RETRIES):
        wait = _last_request + REQUEST_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()

        try:
            response = requests.get(f"{API_URL}/{path}", params={**params, "fmt": "json"}, headers=HEADERS, timeout=30)
        except requests.RequestException as error:
            last_error = error
        else:
            if response.status_code in (429, 503):
                last_error = f"HTTP {response.status_code}"
            else:
                response.raise_for_status()
                return response.json()

        time.sleep(2 * (attempt + 1))

    raise Unavailable(str(last_error))


def same_name(a, b):
    """Mesmo nome, sem diferenciar maiúsculas, acentos e espaços."""
    def simplify(text):
        text = "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))
        return " ".join(text.casefold().split())

    return simplify(a) == simplify(b)


def find_artist(name):
    """Artista do MusicBrainz com exatamente esse nome (o mais relevante), ou None.

    O resultado da busca já traz país, área e marcações (tags) do artista.
    """
    query = '"' + name.replace("\\", "").replace('"', "") + '"'
    for item in call_api("artist", query=f"artist:{query}", limit=5).get("artists", []):
        if int(item.get("score") or 0) >= MIN_SCORE and same_name(name, item.get("name", "")):
            return item
    return None
