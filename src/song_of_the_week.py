"""Escolhe a Song of the Week a partir do que foi ouvido no ListenBrainz.

Como funciona:
1. Busca as músicas mais ouvidas dos últimos 7 dias.
2. Remove as que já foram recomendadas em edições anteriores (histórico).
3. Dá preferência a artistas que não foram recomendados nas últimas 4
   edições. Se só houver artistas recentes, eles continuam valendo: a
   preferência nunca deixa a seção vazia.
4. Fica com as 10 mais ouvidas que sobraram e sorteia uma delas. Músicas
   com mais plays têm um pouco mais de chance: o peso é a raiz quadrada dos
   plays (4 plays pesam 2x mais que 1 play, e não 4x).
5. Se a semana não tiver nenhuma música nova, tenta os últimos 30 dias. Se
   ainda assim não houver, a seção não aparece nessa edição.

O histórico vem do CMS a cada execução (é ele quem registra a música quando
a edição é enviada aos assinantes) e chega aqui como uma lista de
{"artist", "title"}.

Escolha manual: se o CMS mandar uma música escolhida no painel
({"artist", "title"}), o sorteio não acontece e ela vale mesmo que já tenha
sido recomendada ou seja de um artista recente (o CMS já avisou isso). O
motor só busca álbum, capa e links.

Álbum e capa vêm da própria música ouvida no ListenBrainz (correspondência
com o MusicBrainz e o Cover Art Archive). Sem capa ali, o motor procura no
iTunes.
"""

import os
import random
import time

import itunes
import listenbrainz
from streaming_links import get_streaming_links

CANDIDATES = 10
RECENT_ARTIST_EDITIONS = 4
PERIODS = [7, 30]  # dias


def song_key(artist, title):
    """Identifica uma música sem diferenciar maiúsculas, minúsculas e espaços."""
    return f"{artist.strip().casefold()}|{title.strip().casefold()}"


def choose_track(tracks, history, rng=random):
    """Sorteia uma música entre as mais ouvidas que ainda não foram recomendadas.

    As músicas já recomendadas são retiradas antes do sorteio, em vez de
    sortear de novo quando cai uma repetida: o resultado é o mesmo, mas
    assim o sorteio nunca fica preso tentando várias vezes.
    """
    recommended = {song_key(item["artist"], item["title"]) for item in history}
    recent_artists = {
        item["artist"].strip().casefold()
        for item in history[-RECENT_ARTIST_EDITIONS:]
    }

    new_songs = [
        track
        for track in tracks
        if song_key(track["artist"], track["title"]) not in recommended
    ]

    # Artistas recomendados recentemente só entram se não houver outra opção.
    fresh_artists = [
        track
        for track in new_songs
        if track["artist"].strip().casefold() not in recent_artists
    ]

    candidates = (fresh_artists or new_songs)[:CANDIDATES]

    if not candidates:
        return None

    weights = [track["plays"] ** 0.5 for track in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def get_song_of_the_week(history, username=None, rng=random, choice=None):
    """Retorna {"artist", "title", "album", "image", "links", "source"} ou None.

    source é "manual" (escolhida no CMS) ou "draw" (sorteada). Qualquer
    problema com o ListenBrainz é avisado no log, mas não impede o envio da
    newsletter: a edição sai sem a seção (ou, na escolha manual, sem capa).
    """
    username = username or os.environ.get("LISTENBRAINZ_USERNAME")
    now = int(time.time())

    def recent_tracks():
        listens = listenbrainz.get_listens(username, now - PERIODS[-1] * 86400)
        return {days: listenbrainz.top_tracks(listens, now - days * 86400) for days in PERIODS}

    if choice:
        print(f"Song of the Week escolhida no CMS: {choice['artist']} — {choice['title']}.")
        track = {"artist": choice["artist"], "title": choice["title"], "album": None, "image": None}
        if username:
            # A música foi ouvida nos últimos dias: o álbum e a capa vêm de lá.
            try:
                wanted = song_key(track["artist"], track["title"])
                for listened in recent_tracks()[PERIODS[-1]]:
                    if song_key(listened["artist"], listened["title"]) == wanted:
                        track.update(album=listened["album"], image=listened["image"])
                        break
            except Exception as error:
                print(f"Não foi possível consultar o ListenBrainz ({error}).")
        return describe_track(track, "manual")

    if not username:
        print("ListenBrainz não configurado (LISTENBRAINZ_USERNAME). Edição sem Song of the Week.")
        return None

    try:
        tracks_by_period = recent_tracks()
        for period in PERIODS:
            track = choose_track(tracks_by_period[period], history, rng)
            if track:
                break
        else:
            print("Nenhuma música nova para recomendar. Edição sem Song of the Week.")
            return None

        return describe_track(track, "draw")
    except Exception as error:
        print(f"Não foi possível escolher a Song of the Week: {error}. Edição sem a seção.")
        return None


def describe_track(track, source):
    """Álbum, capa e links da música. Sem álbum e capa, a música vai assim mesmo.

    get_streaming_links nunca falha: na pior hipótese, devolve links de busca.
    """
    album, image = track.get("album"), track.get("image")

    if not image:
        try:
            info = itunes.get_track_info(track["artist"], track["title"])
            if info["image"]:
                album, image = info["album"], info["image"]
        except Exception as error:
            print(f"Capa não encontrada no iTunes ({error}).")

    if not image:
        print("Capa não encontrada. A música vai sem ela.")

    return {
        "artist": track["artist"],
        "title": track["title"],
        "album": album,
        "image": image,
        "links": get_streaming_links(track["artist"], track["title"]),
        "source": source,
    }
