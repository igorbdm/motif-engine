"""Descobre os gêneros musicais (até três) do artista de cada vídeo.

Como funciona:
1. Acha o nome do artista no título do vídeo, usando os padrões de cada
   canal ("artist_patterns" em channels.py).
2. Se o artista estiver nas correções de gênero, usa os gêneros de lá. As
   correções são feitas no CMS e chegam a cada execução, com até três gêneros
   separados por vírgula ("post-punk, indie rock"). Uma correção vazia ("")
   esconde os selos daquele artista.
3. Senão, usa os gêneros já descobertos em semanas anteriores
   (data/artist_genres.json) ou pergunta ao MusicBrainz.
4. Se nada disso der certo, usa a categoria do vídeo no YouTube, que é mais
   genérica ("rock", "jazz", "pop"): um gênero só.

No MusicBrainz, as marcações (tags) são votadas pelos usuários e vêm
misturadas com ruído ("american", "seen live", "saxophone"). Por isso uma
marcação só vale se contiver uma palavra de gênero conhecida (GENRE_WORDS).
Valem as três mais votadas (no empate, a mais específica, isto é, a de nome
mais longo), sem repetir o que já foi escolhido: "hip hop" não entra depois
de "alternative hip hop", nem "post-punk revival" depois de "post-punk".

Cada vídeo recebe video["genres"] (lista, até três) e video["genre"] (o
primeiro, ou None), mantido para quem lê o formato antigo.

Os vídeos do Beyond the Stage (section "extras") não levam selo.

Qualquer problema é avisado no log e o vídeo simplesmente fica sem selo.
"""

import json
import re
import unicodedata
from pathlib import Path

import collector
import musicbrainz
from titles import extract_artist

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_PATH = DATA_DIR / "artist_genres.json"

# Marcações sem votos (ou com mais votos contra que a favor) não valem.
MIN_TAG_WEIGHT = 1

# Quantos gêneros cada artista leva no máximo.
MAX_GENRES = 3

GENRE_WORDS = {
    # rock, pop e derivados
    "rock", "pop", "indie", "alternative", "punk", "emo", "hardcore", "grunge",
    "metal", "shoegaze", "psychedelic", "psych", "garage", "surf", "rockabilly",
    "new wave", "no wave", "darkwave", "goth", "gothic", "industrial", "noise",
    "slowcore", "screamo", "britpop", "synthpop", "hyperpop", "chillwave",
    "experimental", "avant garde", "lo fi", "singer songwriter",
    # black music
    "jazz", "bebop", "swing", "fusion", "blues", "soul", "funk", "disco",
    "gospel", "r&b", "rnb", "hip hop", "rap", "trap", "grime", "drill",
    # eletrônica
    "electronic", "electronica", "techno", "house", "ambient", "downtempo",
    "trip hop", "idm", "dubstep", "drum and bass", "edm", "synthwave",
    "vaporwave",
    # folk, country e erudita
    "folk", "country", "americana", "bluegrass", "classical", "orchestral",
    "opera", "baroque", "chamber", "minimalism",
    # Brasil
    "mpb", "samba", "bossa nova", "forró", "axé", "pagode", "sertanejo",
    "tropicalia", "tropicália", "baile funk", "choro", "frevo", "maracatu",
    # resto do mundo
    "reggae", "dub", "ska", "dancehall", "afrobeat", "afrobeats", "highlife",
    "latin", "salsa", "cumbia", "bachata", "reggaeton", "tango", "bolero",
    "norteño", "corridos", "mariachi", "ranchera", "flamenco", "fado",
    "k pop", "j pop", "city pop", "world music",
}

# Categorias de assunto do YouTube que são gêneros musicais.
YOUTUBE_TOPICS = {
    "Christian_music": "christian",
    "Classical_music": "classical",
    "Country_music": "country",
    "Electronic_music": "electronic",
    "Hip_hop_music": "hip hop",
    "Independent_music": "indie",
    "Jazz": "jazz",
    "Music_of_Latin_America": "latin",
    "Pop_music": "pop",
    "Reggae": "reggae",
    "Rhythm_and_blues": "r&b",
    "Rock_music": "rock",
    "Soul_music": "soul",
}

# Separa nomes compostos: "Gillian Welch & David Rawlings",
# "Melissa Aldana with Gonzalo Rubalcaba", "Scott Ian of Anthrax",
# "Hélio Ziskind e Fera Neném".
ARTIST_SEPARATORS = re.compile(r"\s+(?:&|and|e|y|with|x|feat\.?|ft\.?|of)\s+|\s*,\s+", re.IGNORECASE)


def normalize(text):
    return " ".join(text.casefold().replace("-", " ").split())


def is_genre(tag):
    words = f" {normalize(tag)} "
    return any(f" {genre} " in words for genre in GENRE_WORDS)


def overlaps(a, b):
    """Uma marcação repete a outra quando uma contém a outra ("hip hop" e "alternative hip hop").
    "r&b" e "rnb" são a mesma coisa."""
    a, b = (f" {normalize(x).replace('r&b', 'rnb')} " for x in (a, b))
    return a in b or b in a


def pick_genres(tags, limit=MAX_GENRES):
    """Até `limit` marcações que são gêneros: as mais votadas, a mais específica no empate, sem repetir."""
    candidates = [
        (name.strip().casefold(), weight)
        for name, weight in tags
        # "alternative/indie rock" é um agrupamento do MusicBrainz, não um gênero.
        if weight >= MIN_TAG_WEIGHT and is_genre(name) and "/" not in name
    ]
    candidates.sort(key=lambda item: (-item[1], -len(item[0])))
    chosen = []
    for name, _ in candidates:
        if not any(overlaps(name, other) for other in chosen):
            chosen.append(name)
        if len(chosen) == limit:
            break
    return chosen


def pick_genre(tags):
    """A marcação mais votada que é um gênero (ou None)."""
    genres = pick_genres(tags, limit=1)
    return genres[0] if genres else None


def parse_override(value):
    """Correção do CMS ("post-punk, indie rock") → lista de até três gêneros; vazio → []."""
    genres = []
    for part in str(value or "").split(","):
        part = part.strip().casefold()
        if part and part not in genres:
            genres.append(part)
    return genres[:MAX_GENRES]


def remove_accents(text):
    return "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def artist_candidates(name):
    """O nome completo primeiro e, depois, cada parte de um nome composto.

    Cada nome também é tentado sem acentos, porque os títulos nem sempre
    escrevem o artista como ele está cadastrado ("NIGÉRIA" x "Nigeria").
    """
    candidates = []
    for part in [name] + ARTIST_SEPARATORS.split(name):
        part = part.strip()
        for option in (part, remove_accents(part)):
            if option and option not in candidates:
                candidates.append(option)
    return candidates


def genres_from_musicbrainz(artist):
    """Até três gêneros do artista ([] se não achar). Lança musicbrainz.Unavailable se o MusicBrainz estiver fora."""
    for candidate in artist_candidates(artist):
        item = musicbrainz.find_artist(candidate)
        if not item:
            continue

        genres = pick_genres([(tag["name"], int(tag.get("count") or 0)) for tag in item.get("tags", [])])
        if genres:
            return genres

    return []


def genre_from_youtube_topics(topics):
    for url in topics:
        topic = url.rsplit("/", 1)[-1]
        if topic in YOUTUBE_TOPICS:
            return YOUTUBE_TOPICS[topic]
    return None


def load_json(path):
    if not path.exists():
        return {}

    with open(path, encoding="utf-8") as file:
        return json.load(file)


def save_json(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def set_genres(video, genres):
    video["genres"] = list(genres)[:MAX_GENRES]
    video["genre"] = video["genres"][0] if video["genres"] else None


def add_genres(videos, channels, overrides=None, cache_path=CACHE_PATH):
    """Preenche video["genres"] (até três) e video["genre"] (o primeiro, ou None) em cada vídeo."""
    try:
        overrides = {artist.casefold(): parse_override(genre) for artist, genre in (overrides or {}).items()}
        cache = load_json(cache_path)
    except Exception as error:
        print(f"Não foi possível ler os arquivos de gêneros: {error}. Vídeos sem selo de gênero.")
        for video in videos:
            set_genres(video, [])
        return

    use_musicbrainz = True
    cache_changed = False
    not_found = set()
    needs_youtube = []

    for video in videos:
        set_genres(video, [])

        # Os vídeos do Beyond the Stage não levam selo de gênero.
        if video.get("section") == "extras":
            continue

        patterns = channels.get(video["channel"], {}).get("artist_patterns", [])
        artist = extract_artist(video["title"], patterns)

        if artist:
            key = artist.casefold()

            if key in overrides:
                # Correção vazia esconde os selos.
                set_genres(video, overrides[key])
                continue

            cached = cache.get(key)
            # O cache antigo guardava um gênero só (texto): vale como reserva, mas o
            # MusicBrainz é consultado de novo para trazer os três.
            stale = isinstance(cached, str)
            if isinstance(cached, list) and cached:
                set_genres(video, cached)
                continue

            if use_musicbrainz and key not in not_found:
                try:
                    genres = genres_from_musicbrainz(artist)
                except musicbrainz.Unavailable as error:
                    # Fora do ar: não insiste nos outros artistas desta coleta.
                    print(f"MusicBrainz indisponível ({error}). Os gêneros restantes vêm do YouTube.")
                    use_musicbrainz = False
                    genres = []
                except Exception as error:
                    print(f"Gênero de {artist} não encontrado no MusicBrainz ({error}).")
                    genres = []
                if genres:
                    cache[key] = genres
                    cache_changed = True
                    set_genres(video, genres)
                    continue
                if not stale:
                    not_found.add(key)

            if stale and cached:
                set_genres(video, [cached])
                continue

        if video.get("video_id"):
            needs_youtube.append(video)

    if needs_youtube:
        try:
            topics = collector.fetch_video_topics([video["video_id"] for video in needs_youtube])
            for video in needs_youtube:
                genre = genre_from_youtube_topics(topics.get(video["video_id"], []))
                set_genres(video, [genre] if genre else [])
        except Exception as error:
            print(f"Não foi possível buscar as categorias no YouTube: {error}.")

    if cache_changed:
        try:
            save_json(cache, cache_path)
        except Exception as error:
            print(f"Não foi possível salvar os gêneros descobertos: {error}.")
