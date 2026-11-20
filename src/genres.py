"""Descobre o gênero musical do artista de cada vídeo.

Como funciona:
1. Acha o nome do artista no título do vídeo, usando os padrões de cada
   canal ("artist_patterns" em channels.py).
2. Se o artista estiver nas correções de gênero, usa o gênero de lá. As
   correções são feitas no CMS e chegam a cada execução. Um gênero vazio
   ("") esconde o selo daquele artista.
3. Senão, usa o gênero já descoberto em semanas anteriores
   (data/artist_genres.json) ou pergunta ao MusicBrainz.
4. Se nada disso der certo, usa a categoria do vídeo no YouTube, que é mais
   genérica ("rock", "jazz", "pop").

No MusicBrainz, as marcações (tags) são votadas pelos usuários e vêm
misturadas com ruído ("american", "seen live", "saxophone"). Por isso uma
marcação só vale se contiver uma palavra de gênero conhecida (GENRE_WORDS).
Vale a mais votada.

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


def pick_genre(tags):
    """Primeira marcação (da mais para a menos usada) que é um gênero."""
    for name, weight in tags:
        if weight >= MIN_TAG_WEIGHT and is_genre(name):
            return name.strip().casefold()
    return None


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


def genre_from_musicbrainz(artist):
    """Gênero do artista, ou None. Lança musicbrainz.Unavailable se o MusicBrainz estiver fora."""
    for candidate in artist_candidates(artist):
        item = musicbrainz.find_artist(candidate)
        if not item:
            continue

        tags = sorted(item.get("tags", []), key=lambda tag: int(tag.get("count") or 0), reverse=True)
        genre = pick_genre([(tag["name"], int(tag.get("count") or 0)) for tag in tags])
        if genre:
            return genre

    return None


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


def add_genres(videos, channels, overrides=None, cache_path=CACHE_PATH):
    """Preenche video["genre"] em cada vídeo (ou None, se não descobrir)."""
    try:
        overrides = {artist.casefold(): genre for artist, genre in (overrides or {}).items()}
        cache = load_json(cache_path)
    except Exception as error:
        print(f"Não foi possível ler os arquivos de gêneros: {error}. Vídeos sem selo de gênero.")
        return

    use_musicbrainz = True
    cache_changed = False
    not_found = set()
    needs_youtube = []

    for video in videos:
        video["genre"] = None

        # Os vídeos do Beyond the Stage não levam selo de gênero.
        if video.get("section") == "extras":
            continue

        patterns = channels.get(video["channel"], {}).get("artist_patterns", [])
        artist = extract_artist(video["title"], patterns)

        if artist:
            key = artist.casefold()

            if key in overrides:
                # Gênero vazio no arquivo de correções esconde o selo.
                video["genre"] = overrides[key] or None
                continue

            if key in cache:
                video["genre"] = cache[key]
                continue

            if use_musicbrainz and key not in not_found:
                try:
                    genre = genre_from_musicbrainz(artist)
                except musicbrainz.Unavailable as error:
                    # Fora do ar: não insiste nos outros artistas desta coleta.
                    print(f"MusicBrainz indisponível ({error}). Os gêneros restantes vêm do YouTube.")
                    use_musicbrainz = False
                    genre = None
                except Exception as error:
                    print(f"Gênero de {artist} não encontrado no MusicBrainz ({error}).")
                    genre = None
                if genre:
                    cache[key] = genre
                    cache_changed = True
                    video["genre"] = genre
                    continue
                not_found.add(key)

        if video.get("video_id"):
            needs_youtube.append(video)

    if needs_youtube:
        try:
            topics = collector.fetch_video_topics([video["video_id"] for video in needs_youtube])
            for video in needs_youtube:
                video["genre"] = genre_from_youtube_topics(topics.get(video["video_id"], []))
        except Exception as error:
            print(f"Não foi possível buscar as categorias no YouTube: {error}.")

    if cache_changed:
        try:
            save_json(cache, cache_path)
        except Exception as error:
            print(f"Não foi possível salvar os gêneros descobertos: {error}.")
