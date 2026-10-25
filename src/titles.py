"""Padroniza o título dos vídeos como "Artista — Programa".

O nome do artista é recortado do título original com os padrões de cada
canal ("artist_patterns" em channels.py) e mantém a grafia do vídeo. O nome
do programa vem de "program" na configuração do canal ou, quando o canal tem
mais de um formato, do grupo (?P<program>…) do próprio padrão.

Quando o título não encaixa em nenhum padrão, o vídeo mantém o título
original.
"""

import re

SEPARATOR = " — "


def parse_title(title, patterns):
    """Os grupos do primeiro padrão que encaixar no título, ou None."""
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return {name: value.strip() for name, value in match.groupdict().items() if value}
    return None


def extract_artist(title, patterns):
    parsed = parse_title(title, patterns)
    return parsed.get("artist") if parsed else None


def display_title(title, config):
    parsed = parse_title(title, config.get("artist_patterns", []))
    if not parsed or not parsed.get("artist"):
        return title

    program = parsed.get("program") or config.get("program")
    if not program:
        return title

    return f"{parsed['artist']}{SEPARATOR}{program}"


def add_display_titles(videos, channels):
    """Preenche video["display_title"], usado no e-mail no lugar do título."""
    for video in videos:
        video["display_title"] = display_title(video["title"], channels.get(video["channel"], {}))
