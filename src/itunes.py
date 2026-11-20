"""Álbum e capa de uma música na busca do iTunes (sem chave de API).

Usada quando o ListenBrainz não sabe a capa (música sem correspondência no
MusicBrainz ou escolhida no CMS). Só vale um resultado com o mesmo título e o
mesmo artista (ou um dos artistas de um nome composto). Procura na loja dos
EUA e, se não achar, nas do Brasil e do Japão.
"""

import requests

from genres import artist_candidates, remove_accents

API_URL = "https://itunes.apple.com/search"
STORES = ["US", "BR", "JP"]
IMAGE_SIZE = "500x500bb"


def simplify(text):
    return " ".join(remove_accents(text).casefold().split())


def same_title(wanted, found):
    """Mesmo título, aceitando sufixos como "(Remastered)" ou "- Live"."""
    wanted, found = simplify(wanted), simplify(found)
    return found == wanted or found.startswith((wanted + " (", wanted + " -", wanted + " ["))


def same_artist(wanted, found):
    return bool({simplify(name) for name in artist_candidates(wanted)} & {simplify(name) for name in artist_candidates(found)})


def get_track_info(artist, title):
    """{"album", "image"} da música; os dois None se ela não for encontrada."""
    for store in STORES:
        response = requests.get(
            API_URL,
            params={"term": f"{artist} {title}", "entity": "song", "limit": 10, "country": store},
            timeout=30,
        )
        response.raise_for_status()

        for item in response.json().get("results", []):
            if same_title(title, item.get("trackName", "")) and same_artist(artist, item.get("artistName", "")):
                image = item.get("artworkUrl100") or None
                return {
                    "album": item.get("collectionName") or None,
                    "image": image.replace("100x100bb", IMAGE_SIZE) if image else None,
                }

    return {"album": None, "image": None}
