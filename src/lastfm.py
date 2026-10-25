import os

import requests

API_URL = "https://ws.audioscrobbler.com/2.0/"

# Quando o Last.fm não tem a capa, ele devolve esta imagem genérica (uma
# estrela cinza). Nesse caso é melhor não mostrar imagem nenhuma.
PLACEHOLDER_IMAGE_ID = "2a96cbd8b46e442fc41c2b86b821562f"


def call_api(method, **params):
    api_key = os.environ.get("LASTFM_API_KEY")

    if not api_key:
        raise RuntimeError(
            "A variável LASTFM_API_KEY não foi configurada. "
            "Veja o README para saber como criar e configurar a chave."
        )

    response = requests.get(
        API_URL,
        params={
            "method": method,
            "api_key": api_key,
            "format": "json",
            **params,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    # O Last.fm responde erros com status 200 e um campo "error".
    if "error" in data:
        raise RuntimeError(f"Erro do Last.fm ({data['error']}): {data.get('message')}")

    return data


def get_top_tracks(username, period="7day", limit=50):
    """Músicas mais ouvidas no período, da mais para a menos ouvida.

    period pode ser "7day", "1month", "3month", "6month", "12month" ou
    "overall". "7day" são os últimos 7 dias até o momento da consulta.
    """
    data = call_api("user.gettoptracks", user=username, period=period, limit=limit)

    return [
        {
            "artist": track["artist"]["name"],
            "title": track["name"],
            "plays": int(track["playcount"]),
        }
        for track in data["toptracks"]["track"]
    ]


def get_artist_tags(artist):
    """Marcações do artista, da mais para a menos usada: [(nome, peso 0-100)]."""
    data = call_api("artist.gettoptags", artist=artist, autocorrect=1)

    return [
        (tag["name"], int(tag["count"]))
        for tag in data.get("toptags", {}).get("tag", [])
    ]


def get_track_info(artist, title):
    """Álbum e capa (300x300) da música. Cada um pode vir como None."""
    data = call_api("track.getinfo", artist=artist, track=title, autocorrect=1)
    album = data.get("track", {}).get("album") or {}

    image = None
    # A lista vai da menor para a maior imagem.
    for item in reversed(album.get("image", [])):
        url = item.get("#text")
        if url and PLACEHOLDER_IMAGE_ID not in url:
            image = url
            break

    return {
        "album": album.get("title") or None,
        "image": image,
    }
