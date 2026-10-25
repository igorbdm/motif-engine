from datetime import datetime, timezone


def parse_date(date_string):
    """Converte a data ISO recebida pelo feed para uma data com fuso horário."""
    published = datetime.fromisoformat(date_string.replace("Z", "+00:00"))

    if published.tzinfo is None:
        return published.replace(tzinfo=timezone.utc)

    return published
