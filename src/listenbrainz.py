"""Músicas ouvidas no ListenBrainz (https://listenbrainz.org).

As músicas ouvidas no ListenBrainz são públicas: basta o nome do usuário, sem
chave de API. Cada música ouvida pode vir com a correspondência no MusicBrainz
("mbid_mapping"), que traz o álbum e a capa no Cover Art Archive.
"""

import re

import requests

API_URL = "https://api.listenbrainz.org/1"
HEADERS = {"User-Agent": "motif-engine/1.1 (+https://github.com/igorbdm/motif-engine)"}
PAGE_SIZE = 1000  # máximo aceito pela API
MAX_PAGES = 10
COVER_URL = "https://coverartarchive.org/release/{release}/front-500"

# A mesma música enviada por duas origens (ex.: conexão com o Spotify e
# importação do Last.fm) aparece duas vezes, com poucos minutos de diferença.
DUPLICATE_WINDOW = 10 * 60
ARTIST_SEPARATORS = re.compile(r"\s*(?:,|&|\bfeat\.?|\bft\.?)\s+", re.IGNORECASE)


def call_api(path, **params):
    response = requests.get(f"{API_URL}/{path}", params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def get_listens(username, since):
    """Músicas ouvidas desde o timestamp since, da mais recente para a mais antiga."""
    listens = []
    max_ts = None

    # Vai do presente para o passado, página por página, até passar de since.
    for _ in range(MAX_PAGES):
        params = {"count": PAGE_SIZE, **({"max_ts": max_ts} if max_ts else {})}
        page = call_api(f"user/{username}/listens", **params)["payload"]["listens"]
        listens.extend(listen for listen in page if listen["listened_at"] >= since)

        if len(page) < PAGE_SIZE or page[-1]["listened_at"] < since:
            break
        max_ts = page[-1]["listened_at"]

    return listens


def first_artist(name):
    return ARTIST_SEPARATORS.split(name.strip(), maxsplit=1)[0].casefold()


def remove_duplicates(listens):
    """Tira a segunda cópia de uma música enviada por duas origens ao mesmo tempo."""
    kept = []

    for listen in sorted(listens, key=lambda item: item["listened_at"]):
        metadata = listen["track_metadata"]
        song = (first_artist(metadata["artist_name"]), metadata["track_name"].strip().casefold())
        client = (metadata.get("additional_info") or {}).get("submission_client")

        # Cada música guardada absorve no máximo uma cópia: tocar de novo logo
        # depois continua contando.
        original = next((
            other for other in kept[-10:]
            if listen["listened_at"] - other["listened_at"] <= DUPLICATE_WINDOW
            and other["song"] == song
            and other["client"] != client
            and not other["has_copy"]
        ), None)
        if original:
            original["has_copy"] = True
        else:
            kept.append({**listen, "song": song, "client": client, "has_copy": False})

    return kept


def album_and_cover(metadata):
    mapping = metadata.get("mbid_mapping") or {}
    release = mapping.get("caa_release_mbid")

    return {
        "album": (metadata.get("release_name") or "").strip() or None,
        "image": COVER_URL.format(release=release) if release and mapping.get("caa_id") else None,
    }


def top_tracks(listens, since=0):
    """Músicas ouvidas desde since, da mais para a menos ouvida.

    Cada uma vem como {"artist", "title", "plays", "album", "image"}. Empates
    ficam com a ouvida mais recentemente na frente.
    """
    tracks = {}

    # Da mais recente para a mais antiga: o nome exibido é o da última vez que tocou.
    for listen in reversed(remove_duplicates(listens)):
        if listen["listened_at"] < since:
            continue

        metadata = listen["track_metadata"]
        artist = metadata["artist_name"].strip()
        title = metadata["track_name"].strip()
        if not artist or not title:
            continue

        track = tracks.setdefault(f"{artist.casefold()}|{title.casefold()}", {
            "artist": artist, "title": title, "plays": 0, "last": 0, "album": None, "image": None,
        })
        track["plays"] += 1
        track["last"] = max(track["last"], listen["listened_at"])

        # Fica com o álbum da primeira música ouvida que tiver capa.
        if not track["image"]:
            info = album_and_cover(metadata)
            if info["image"] or not track["album"]:
                track.update(info)

    ordered = sorted(tracks.values(), key=lambda track: (track["plays"], track["last"]), reverse=True)
    for track in ordered:
        del track["last"]
    return ordered
