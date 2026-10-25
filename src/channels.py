# La Blogothèque: só sessões completas, como "Naomi Greene | A Take Away Show"
# ou "Adèle Castillon | Live Session for The Collective by Stradivarius".
# Ficam de fora os fragmentos de uma música só, que trazem o nome da música
# antes da barra ("Rostam - The Road to Death | Live Session"), e também os
# shows de festival e as séries especiais.
LA_BLOGOTHEQUE_FULL_SESSION = (
    r"^(?P<artist>(?:(?!\s-\s)[^|])+?)\s*\|\s*(?P<program>A Take Away Show|Live Session)"
)

# Cada canal tem:
#   id               ID do canal no YouTube
#   keep / ignore    palavras do título para manter / descartar
#   title_pattern    (opcional) formato que o título precisa seguir, quando
#                    palavras não bastam para filtrar
#   min_duration     (opcional) duração mínima do vídeo, em segundos
#   section          (opcional) "extras" coloca o canal no Beyond the Stage
#   program          (opcional) nome do programa no título padronizado,
#                    "Artista — Programa" (veja titles.py)
#   artist_patterns  (opcional) como achar o nome do artista no título. O nome
#                    fica no grupo (?P<artist>…); um grupo (?P<program>…), se
#                    houver, substitui "program". Mais de um padrão: vale o
#                    primeiro que encaixar. Serve para o título padronizado e
#                    para buscar o gênero (só nas Live Sessions).

CHANNELS = {
    "KEXP": {
        "id": "UC3I2GFN_F8WudD_2jUZbojA",
        "keep": ["Full Performance"],
        "ignore": [],
        "program": "Live on KEXP",
        # "Death Cab For Cutie - Full Performance (Live on KEXP)"
        "artist_patterns": [r"^(?P<artist>.+?)\s+-\s+Full Performance"],
    },
    "Tiny Desk": {
        "id": "UC4eYXhJI4-7wSWc8UNRwD4A",
        "keep": ["Tiny Desk Concert"],
        "ignore": [],
        "program": "Tiny Desk Concert",
        # "Tim Bernardes: Tiny Desk Concert"
        "artist_patterns": [r"^(?P<artist>.+?):\s*Tiny Desk"],
    },
    "Audiotree": {
        "id": "UCWjmAUHmajb1-eo5WKk_22A",
        "keep": ["Full Session"],
        "ignore": [],
        "program": "Audiotree Live",
        # "Cold Steel on Audiotree Live (Full Session)"
        "artist_patterns": [r"^(?P<artist>.+?)\s+on Audiotree"],
    },
    "La Blogothèque": {
        "id": "UCFAKGci5lneha2x4XMbzYrQ",
        "keep": ["Take Away Show", "Live Session"],
        "ignore": [],
        "min_duration": 90,
        "title_pattern": LA_BLOGOTHEQUE_FULL_SESSION,
        # O programa vem do título: "A Take Away Show" ou "Live Session".
        "artist_patterns": [LA_BLOGOTHEQUE_FULL_SESSION],
    },
    "KCRW": {
        "id": "UC54U5gpKkaa_BpXRVNip2Dw",
        "keep": ["Live on KCRW"],
        "ignore": [],
        "min_duration": 600,
        "program": "Live on KCRW",
        # "Sébastien Tellier: Live on KCRW"
        "artist_patterns": [r"^(?P<artist>.+?):\s*Live on KCRW"],
    },
    "Cultura Livre": {
        "id": "UCBuFf6FSDclfDvRGJY1Q5Uw",
        "keep": ["CULTURA LIVRE"],
        "ignore": [],
        "min_duration": 600,
        "program": "Cultura Livre",
        # "CULTURA LIVRE | Fera Neném | 10/10/26"
        # "Fera Neném no Cultura Livre"
        "artist_patterns": [
            r"^Cultura Livre\s*\|\s*(?P<artist>[^|]+?)\s*\|",
            r"^(?P<artist>.+?)\s+no Cultura Livre",
        ],
    },
    "Amoeba Music": {
        "id": "UC9DkCKm4_VDztRRyge4mCJQ",
        "keep": ["In My Bag"],
        "ignore": [],
        # Não é música ao vivo: aparece em uma seção separada no fim do e-mail.
        "section": "extras",
        "program": "What's In My Bag?",
        # "Elvis Costello's "What's In My Bag?" | Amoeba Music"
        # "Daniel Lanois | What's in My Bag? (Teaser)"
        "artist_patterns": [
            r"^(?P<artist>.+?)['’]s\s+[\"“]?What['’]s In My Bag",
            r"^(?P<artist>.+?)\s*\|\s*What['’]s In My Bag",
        ],
    },
    "Pitchfork": {
        "id": "UC7kI8WjpCfFoMSNDuRh_4lA",
        # Over/Under: "Audrey Hobert Rates Podcasts, Don Toliver, and Disney Adults | Pitchfork".
        # O canal também publica cortes curtos do programa ("Audrey Hobert
        # Rates Don Toliver", com 31 s); a duração mínima deixa só o episódio.
        "keep": ["Rates", "Over/Under"],
        "ignore": [],
        "min_duration": 300,
        "section": "extras",
        "program": "Over/Under",
        "artist_patterns": [
            r"^(?P<artist>.+?)\s+Rates\s",
            r"^(?P<artist>.+?)\s+Does Pitchfork",
        ],
    },
}
