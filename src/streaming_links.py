"""Links da Song of the Week no Spotify, Apple Music e YouTube Music.

- Apple Music: busca da Apple (iTunes Search API), que não pede chave.
- YouTube Music: busca na API do YouTube (a mesma chave dos vídeos),
  procurando a faixa oficial publicada no canal "Artista - Topic".
- Spotify: link de busca. A API do Spotify pede um app próprio, com
  credenciais, e por enquanto não vale o trabalho.

Quando a busca falha ou o resultado não é a mesma música (versão ao vivo,
cover, outro artista), o link daquela plataforma vira um link de busca.
Assim os três links sempre aparecem e nenhum erro impede o envio.
"""

import os
import re
from urllib.parse import quote, quote_plus

import requests

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_MUSIC_CATEGORY = "10"


def normalize(text):
    """"Life Is (feat. Someone)" -> "life is".

    Só participações são ignoradas. "(Live)", "(Ao Vivo)", "[Remix]" etc.
    continuam no título, para não confundir a faixa com outra versão.
    """
    text = re.sub(r"\s*[\(\[](feat\.?|ft\.?|with) [^\)\]]*[\)\]]", "", text, flags=re.IGNORECASE)
    return " ".join(text.casefold().split())


def same_song(artist, title, found_artist, found_title):
    return normalize(artist) == normalize(found_artist) and normalize(title) == normalize(found_title)


def search_links(artist, title):
    term = f"{artist} {title}"
    return {
        "spotify": f"https://open.spotify.com/search/{quote(term)}",
        "apple_music": f"https://music.apple.com/search?term={quote_plus(term)}",
        "youtube_music": f"https://music.youtube.com/search?q={quote_plus(term)}",
    }


def find_apple_music(artist, title):
    response = requests.get(
        ITUNES_SEARCH_URL,
        params={"term": f"{artist} {title}", "entity": "song", "limit": 10},
        timeout=30,
    )
    response.raise_for_status()

    for track in response.json().get("results", []):
        if same_song(artist, title, track.get("artistName", ""), track.get("trackName", "")):
            # O "uo=4" é um parâmetro de rastreamento da Apple.
            return track["trackViewUrl"].replace("&uo=4", "")

    return None


def find_youtube_music(artist, title):
    api_key = os.environ.get("YOUTUBE_API_KEY")

    if not api_key:
        return None

    response = requests.get(
        YOUTUBE_SEARCH_URL,
        params={
            "part": "snippet",
            "q": f"{artist} {title}",
            "type": "video",
            "videoCategoryId": YOUTUBE_MUSIC_CATEGORY,
            "maxResults": 10,
            "key": api_key,
        },
        timeout=30,
    )
    response.raise_for_status()

    # As faixas oficiais ficam em canais gerados automaticamente pelo
    # YouTube, chamados "Artista - Topic", com o vídeo levando só o título.
    for item in response.json().get("items", []):
        snippet = item.get("snippet", {})
        channel = snippet.get("channelTitle", "")

        if not channel.endswith(" - Topic"):
            continue

        if same_song(artist, title, channel.removesuffix(" - Topic"), snippet.get("title", "")):
            return f"https://music.youtube.com/watch?v={item['id']['videoId']}"

    return None


def get_streaming_links(artist, title):
    """Retorna {"spotify", "apple_music", "youtube_music"}, sempre com os três."""
    links = search_links(artist, title)

    for platform, find in [("apple_music", find_apple_music), ("youtube_music", find_youtube_music)]:
        try:
            url = find(artist, title)
        except Exception as error:
            print(f"Link de {platform} não encontrado ({error}). Usando link de busca.")
            continue

        if url:
            links[platform] = url

    return links
