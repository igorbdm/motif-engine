"""Descobre o país de origem do artista de cada vídeo (para a bandeira).

Como funciona:
1. Acha o nome do artista no título do vídeo, como em genres.py.
2. Se o artista estiver nas correções de origem (feitas no CMS e enviadas a
   cada execução), usa o país de lá. Um país vazio ("") esconde a bandeira.
3. Senão, usa o país já descoberto em semanas anteriores
   (data/artist_countries.json) ou pergunta ao MusicBrainz.

No MusicBrainz, cada artista tem uma "área". Às vezes é o país; às vezes é
uma cidade ("Kuala Lumpur") ou um estado ("Texas"). Nesses casos o motor sobe
pela hierarquia de áreas até chegar ao país. Só vale um artista cujo nome seja
igual ao procurado (sem diferença de maiúsculas e acentos).

O país é o código ISO de duas letras ("BR", "US"). O CMS transforma o código
em bandeira. Artistas que o MusicBrainz não conhece ficam gravados com país
vazio, para não serem procurados toda semana; uma correção no CMS resolve.

Os vídeos do Beyond the Stage (section "extras") não levam bandeira.

O MusicBrainz pede no máximo uma consulta por segundo. Se ele estiver
ocupado, o motor tenta de novo algumas vezes; se não der, o artista fica sem
bandeira nesta edição e é procurado de novo na próxima. Nenhum erro impede a
coleta.
"""

import re
from pathlib import Path

from genres import artist_candidates, load_json, save_json
import musicbrainz
from titles import extract_artist

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_PATH = DATA_DIR / "artist_countries.json"

MAX_AREA_STEPS = 6
COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")


def country_from_area(area):
    """Código do país de uma área (país, estado ou cidade), ou None."""
    for step in range(MAX_AREA_STEPS):
        codes = area.get("iso-3166-1-codes") or []
        if codes:
            return codes[0]

        # Estados e províncias têm códigos como "US-TX".
        subdivisions = area.get("iso-3166-2-codes") or []
        if subdivisions:
            return subdivisions[0][:2]

        if not area.get("id"):
            return None

        details = musicbrainz.call_api(f"area/{area['id']}", inc="area-rels")
        if details.get("iso-3166-1-codes") or details.get("iso-3166-2-codes"):
            area = details
            continue

        parents = [
            relation["area"]
            for relation in details.get("relations", [])
            if relation.get("type") == "part of" and relation.get("direction") == "backward" and relation.get("area")
        ]
        if not parents:
            return None
        area = parents[0]

    return None


def country_from_musicbrainz(artist):
    """País do artista ("BR"), "" se o MusicBrainz não souber, ou musicbrainz.Unavailable."""
    for candidate in artist_candidates(artist):
        item = musicbrainz.find_artist(candidate)
        if not item:
            continue

        if COUNTRY_PATTERN.fullmatch(item.get("country") or ""):
            return item["country"]

        for key in ("area", "begin-area"):
            if item.get(key):
                country = country_from_area(item[key])
                if country:
                    return country

        # O artista certo existe, mas sem origem cadastrada.
        return ""

    return ""


def add_countries(videos, channels, overrides=None, cache_path=CACHE_PATH):
    """Preenche video["country"] em cada vídeo (código ISO ou None)."""
    try:
        overrides = {artist.casefold(): (country or "").upper() for artist, country in (overrides or {}).items()}
        cache = load_json(cache_path)
    except Exception as error:
        print(f"Não foi possível ler os arquivos de origem: {error}. Vídeos sem bandeira.")
        return

    cache_changed = False
    unavailable = False

    for video in videos:
        video["country"] = None

        if video.get("section") == "extras":
            continue

        patterns = channels.get(video["channel"], {}).get("artist_patterns", [])
        artist = extract_artist(video["title"], patterns)
        if not artist:
            continue

        key = artist.casefold()

        if key in overrides:
            video["country"] = overrides[key] or None
            continue

        if key not in cache and not unavailable:
            try:
                cache[key] = country_from_musicbrainz(artist)
                cache_changed = True
            except musicbrainz.Unavailable as error:
                # Fora do ar: não insiste nos outros artistas desta coleta.
                print(f"MusicBrainz indisponível ({error}). Os artistas restantes ficam sem bandeira nesta edição.")
                unavailable = True
            except Exception as error:
                print(f"Origem de {artist} não encontrada ({error}).")

        video["country"] = cache.get(key) or None

    if cache_changed:
        try:
            save_json(cache, cache_path)
        except Exception as error:
            print(f"Não foi possível salvar as origens descobertas: {error}.")
