import os
import re

import requests

from utils import parse_date

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
API_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
VIDEO_API_URL = "https://www.googleapis.com/youtube/v3/videos"
DURATION_PATTERN = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?")


def contains_any(text, terms):
    normalized_text = text.casefold()
    return any(term.casefold() in normalized_text for term in terms)


def get_uploads_playlist_id(channel_id):
    """Todo canal do YouTube tem uma playlist automática com todos os uploads.
    O ID dela é sempre igual ao ID do canal, trocando o prefixo 'UC' por 'UU'."""
    return "UU" + channel_id[2:]


def fetch_playlist_page(playlist_id, page_token=None):
    if not YOUTUBE_API_KEY:
        raise RuntimeError(
            "A variável YOUTUBE_API_KEY não foi configurada. "
            "Veja o README para saber como criar e configurar a chave."
        )

    params = {
        "part": "snippet",
        "playlistId": playlist_id,
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
    }

    if page_token:
        params["pageToken"] = page_token

    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()

    return response.json()


def parse_duration(duration):
    """Converte uma duração ISO 8601 do YouTube em segundos.

    Aceita o formato completo (ex.: "P1DT2H3M4S") e também "P0D",
    que o YouTube retorna para lives em andamento e estreias agendadas.
    """
    match = DURATION_PATTERN.fullmatch(duration)

    if not match or duration in ("P", "PT") or duration.endswith("T"):
        raise ValueError(f"Duração ISO 8601 inválida: {duration}")

    days, hours, minutes, seconds = (int(value or 0) for value in match.groups())

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def fetch_video_durations(video_ids):
    """Busca as durações de até 50 vídeos em uma única chamada à API."""
    if not video_ids:
        return {}

    if not YOUTUBE_API_KEY:
        raise RuntimeError(
            "A variável YOUTUBE_API_KEY não foi configurada. "
            "Veja o README para saber como criar e configurar a chave."
        )

    params = {
        "part": "contentDetails",
        "id": ",".join(video_ids),
        "key": YOUTUBE_API_KEY,
    }

    response = requests.get(VIDEO_API_URL, params=params, timeout=30)
    response.raise_for_status()

    durations = {}

    for item in response.json().get("items", []):
        content_details = item.get("contentDetails", {})
        duration = content_details.get("duration")

        # Alguns vídeos podem não retornar duração.
        # Nesse caso, simplesmente não adicionamos o vídeo ao dicionário.
        if not duration:
            continue

        durations[item["id"]] = parse_duration(duration)

    return durations


def fetch_video_topics(video_ids):
    """Busca as categorias de assunto (topicCategories) de vários vídeos.

    O YouTube devolve links da Wikipédia, como
    "https://en.wikipedia.org/wiki/Rock_music". A API aceita até 50 IDs por
    chamada, então a lista é dividida em lotes.
    """
    if not video_ids:
        return {}

    if not YOUTUBE_API_KEY:
        raise RuntimeError(
            "A variável YOUTUBE_API_KEY não foi configurada. "
            "Veja o README para saber como criar e configurar a chave."
        )

    topics = {}

    for start in range(0, len(video_ids), 50):
        params = {
            "part": "topicDetails",
            "id": ",".join(video_ids[start:start + 50]),
            "key": YOUTUBE_API_KEY,
        }

        response = requests.get(VIDEO_API_URL, params=params, timeout=30)
        response.raise_for_status()

        for item in response.json().get("items", []):
            topics[item["id"]] = item.get("topicDetails", {}).get("topicCategories", [])

    return topics


def get_feed(channel_name, config, since=None):
    playlist_id = get_uploads_playlist_id(config["id"])
    min_duration = config.get("min_duration")

    results = []
    page_token = None

    while True:
        data = fetch_playlist_page(playlist_id, page_token)

        stop_paging = False
        candidates = []

        for item in data.get("items", []):
            snippet = item["snippet"]
            title = snippet["title"]
            published = snippet["publishedAt"]
            video_id = snippet["resourceId"]["videoId"]

            # A playlist de uploads vem sempre do vídeo mais recente para o
            # mais antigo. Quando encontramos um vídeo anterior ao início da
            # edição, todos os próximos também estarão fora da janela.
            if since is not None and parse_date(published) <= since:
                stop_paging = True
                break

            # Se "keep" estiver vazio, nenhum filtro positivo é aplicado.
            if config.get("keep") and not contains_any(title, config["keep"]):
                continue

            if contains_any(title, config.get("ignore", [])):
                continue

            # Quando palavras não bastam, o título precisa seguir um formato.
            if config.get("title_pattern") and not re.search(config["title_pattern"], title, re.IGNORECASE):
                continue

            candidates.append({
                "channel": channel_name,
                "section": config.get("section", "live"),
                "title": title,
                "published": published,
                "link": f"https://www.youtube.com/watch?v={video_id}",
                "video_id": video_id,
            })

        # Só consulta a duração quando o canal possui um filtro mínimo.
        # A consulta é feita em lote para evitar uma chamada por vídeo.
        if min_duration is not None and candidates:
            durations = fetch_video_durations(
                [video["video_id"] for video in candidates]
            )

            candidates = [
                video
                for video in candidates
                if durations.get(video["video_id"], 0) >= min_duration
            ]

        results.extend(candidates)

        page_token = data.get("nextPageToken")

        if stop_paging or not page_token:
            break

    return sorted(
        results,
        key=lambda video: parse_date(video["published"]),
        reverse=True,
    )
