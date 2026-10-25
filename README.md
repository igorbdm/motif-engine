# Motif Engine

Motor de coleta da Music Weekly. Busca as performances da semana nos canais
acompanhados do YouTube, descobre o gênero de cada artista e escolhe a Song of
the Week no Last.fm. **Não envia e-mails**: quem monta, revisa e envia a edição
é o CMS da Motif (repositório `motif-site`).

Construído a partir do código da `motif-newsletter` (mesmos canais, filtros,
títulos, gêneros e regras da Song of the Week).

## Como o CMS usa o motor

1. Na hora da coleta, o CMS dispara o workflow **Coletar edição**
   (`.github/workflows/collect.yml`) com os parâmetros da edição e o estado que
   ele guarda: o histórico da Song of the Week e as correções de gênero.
2. O workflow roda `src/main.py`, grava `results/<edition_key>.json` e faz
   commit desse arquivo e do cache de gêneros (`data/artist_genres.json`).
3. O CMS acompanha a execução pela API do GitHub e, quando ela termina, lê o
   resultado. Se a execução falhar, o CMS tenta de novo e avisa no painel.

O formato do resultado é o contrato `schema: 1`, o mesmo de
`modules/motif-newsletter/data/sample-edition.json` no `motif-site`:
`song_of_the_week` (ou `null`), `videos` (`section` `live` ou `extras`,
`genre` ou `null`), mais `edition_key`, `request_id`, `window`, `run` e
`warnings`.

## Configuração no GitHub

Segredos do repositório (Settings → Secrets and variables → Actions):

- `YOUTUBE_API_KEY`: chave da YouTube Data API v3;
- `LASTFM_API_KEY`: chave da API do Last.fm.

O usuário do Last.fm (`igor8`) está no próprio workflow.

No CMS, o token do GitHub precisa ser um *fine-grained token* com acesso só a
este repositório e as permissões **Actions: Read and write** e
**Contents: Read**.

## Rodar localmente

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests

# coleta real (precisa das chaves no ambiente)
EDITION_KEY=local-test REQUEST_ID=local-1 YOUTUBE_API_KEY=… LASTFM_API_KEY=… LASTFM_USERNAME=igor8 python src/main.py
```

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `src/main.py` | Lê os parâmetros, coleta e grava o resultado |
| `src/channels.py` | Canais acompanhados e seus filtros |
| `src/collector.py` | Busca os vídeos no YouTube |
| `src/titles.py` | Título padronizado "Artista — Programa" |
| `src/genres.py` | Gênero do artista (correções do CMS, cache, Last.fm, YouTube) |
| `src/song_of_the_week.py` | Sorteio da Song of the Week |
| `src/streaming_links.py` | Links do Spotify, Apple Music e YouTube Music |
| `data/artist_genres.json` | Cache dos gêneros descobertos (atualizado pelo workflow) |
| `results/` | Um JSON por edição coletada |
