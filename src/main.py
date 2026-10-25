"""Coleta os dados de uma edição da Music Weekly e grava o resultado em JSON.

O CMS (motif-site) dispara o workflow "Coletar edição" com os parâmetros da
edição e, depois, lê o arquivo results/<edition_key>.json pela API do GitHub.
O motor não envia nada: montagem, revisão e envio ficam no CMS.

Parâmetros (variáveis de ambiente, preenchidas pelo workflow):
  EDITION_KEY   identificador da edição no CMS, ex.: "auto-2026-10-30"
  REQUEST_ID    identificador deste pedido; volta no resultado para o CMS
                saber que o arquivo é da execução que ele pediu
  EDITION_DATE  data da edição (AAAA-MM-DD); padrão: a próxima sexta-feira
  SINCE         início da coleta (ISO 8601); padrão: meia-noite da edição
                anterior, sete dias antes, no horário de São Paulo
  ENGINE_STATE  JSON com o estado guardado no CMS:
                {"song_history": [{"artist", "title"}], "genre_overrides": {"artista": "gênero"}}
"""

import json
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from channels import CHANNELS
from collector import get_feed
from genres import add_genres
from song_of_the_week import get_song_of_the_week
from titles import add_display_titles

SCHEMA = 1
TIMEZONE = ZoneInfo("America/Sao_Paulo")
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def get_edition_date(today=None):
    today = today or datetime.now(TIMEZONE).date()
    days_until_friday = (4 - today.weekday()) % 7
    return today + timedelta(days=days_until_friday)


def get_collection_start(edition_date):
    previous_edition = edition_date - timedelta(days=7)
    return datetime.combine(previous_edition, time.min, tzinfo=TIMEZONE)


def read_parameters(environ=None):
    environ = os.environ if environ is None else environ

    edition_key = environ.get("EDITION_KEY", "").strip()
    if not KEY_PATTERN.fullmatch(edition_key):
        raise ValueError(f"EDITION_KEY inválido: {edition_key!r}. Use letras minúsculas, números e hífens.")

    request_id = environ.get("REQUEST_ID", "").strip()
    if not KEY_PATTERN.fullmatch(request_id):
        raise ValueError(f"REQUEST_ID inválido: {request_id!r}.")

    edition_date = environ.get("EDITION_DATE", "").strip()
    edition_date = date.fromisoformat(edition_date) if edition_date else get_edition_date()

    since = environ.get("SINCE", "").strip()
    if since:
        since = datetime.fromisoformat(since.replace("Z", "+00:00"))
        if since.tzinfo is None:
            since = since.replace(tzinfo=TIMEZONE)
    else:
        since = get_collection_start(edition_date)

    state = json.loads(environ.get("ENGINE_STATE", "").strip() or "{}")
    if not isinstance(state, dict):
        raise ValueError("ENGINE_STATE precisa ser um objeto JSON.")

    history = [
        {"artist": str(item["artist"]), "title": str(item["title"])}
        for item in state.get("song_history", [])
        if isinstance(item, dict) and item.get("artist") and item.get("title")
    ]
    overrides = {
        str(artist): str(genre or "")
        for artist, genre in (state.get("genre_overrides") or {}).items()
    }

    return {
        "edition_key": edition_key,
        "request_id": request_id,
        "edition_date": edition_date,
        "since": since,
        "song_history": history,
        "genre_overrides": overrides,
    }


def video_entry(video):
    """Só o que o CMS usa, no formato do contrato (schema 1)."""
    return {
        "id": video["video_id"],
        "title": video["title"],
        "display_title": video.get("display_title") or video["title"],
        "channel": video["channel"],
        "link": video["link"],
        "section": video.get("section", "live"),
        "genre": video.get("genre"),
        "published": video["published"],
    }


def collect(parameters):
    videos = []
    for name, config in CHANNELS.items():
        videos.extend(get_feed(name, config, since=parameters["since"]))

    warnings = []
    if videos:
        add_genres(videos, CHANNELS, overrides=parameters["genre_overrides"])
        add_display_titles(videos, CHANNELS)
    else:
        warnings.append("Nenhum vídeo novo encontrado nos canais acompanhados.")

    pick = get_song_of_the_week(parameters["song_history"])
    if not pick:
        warnings.append("Edição sem Song of the Week (veja o log da execução).")

    run_id = os.environ.get("GITHUB_RUN_ID")
    repository = os.environ.get("GITHUB_REPOSITORY")

    return {
        "schema": SCHEMA,
        "edition_key": parameters["edition_key"],
        "request_id": parameters["request_id"],
        "edition_date": parameters["edition_date"].isoformat(),
        "window": {
            "start": parameters["since"].isoformat(),
            "end": datetime.now(TIMEZONE).replace(microsecond=0).isoformat(),
        },
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "run": {
            "id": int(run_id) if run_id else None,
            "url": f"https://github.com/{repository}/actions/runs/{run_id}" if run_id and repository else None,
        },
        "song_of_the_week": pick,
        "videos": [video_entry(video) for video in videos],
        "warnings": warnings,
    }


def write_result(result, results_dir=RESULTS_DIR):
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{result['edition_key']}.json"
    with open(path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return path


def main():
    parameters = read_parameters()
    result = collect(parameters)
    path = write_result(result)

    live = sum(1 for video in result["videos"] if video["section"] == "live")
    extras = len(result["videos"]) - live
    pick = result["song_of_the_week"]
    print(f"Edição {result['edition_key']} ({result['edition_date']}): {live} Live Sessions, {extras} Beyond the Stage.")
    print(f"Song of the Week: {pick['artist']} — {pick['title']}." if pick else "Sem Song of the Week.")
    for warning in result["warnings"]:
        print(f"Aviso: {warning}")
    print(f"Resultado gravado em {path.relative_to(path.parent.parent)}.")


if __name__ == "__main__":
    main()
