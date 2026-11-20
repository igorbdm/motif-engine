# Motif Engine

Motor de coleta da Music Weekly. Busca as performances da semana nos canais
acompanhados do YouTube, descobre até três gêneros e o país de origem de cada artista e escolhe a Song of
the Week no ListenBrainz. **Não envia e-mails**: quem monta, revisa e envia a edição
é o CMS da Motif (repositório `motif-site`).

Construído a partir do código da `motif-newsletter` (mesmos canais, filtros,
títulos, gêneros e regras da Song of the Week).

## Como o CMS usa o motor

1. Na hora da coleta, o CMS dispara o workflow **Coletar edição**
   (`.github/workflows/collect.yml`) com os parâmetros da edição e o estado que
   ele guarda: o histórico da Song of the Week, as correções de gênero e de origem e, se o
   editor escolheu a música no painel, `song_choice` (`{artist, title}`). Com
   ela, o sorteio não acontece: o motor só busca álbum, capa e links.
2. O workflow roda `src/main.py`, grava `results/<edition_key>.json` e faz
   commit desse arquivo e dos caches de gêneros e origens (`data/artist_genres.json`,
   `data/artist_countries.json`).
3. O CMS acompanha a execução pela API do GitHub e, quando ela termina, lê o
   resultado. Se a execução falhar, o CMS tenta de novo e avisa no painel.

O formato do resultado é o contrato `schema: 1`, o mesmo de
`modules/motif-newsletter/data/sample-edition.json` no `motif-site`:

- `song_of_the_week`: `{artist, title, album, image, links, source}` ou `null`. `source` é `manual`
  (escolhida no CMS) ou `draw` (sorteada); `links` traz `spotify`, `apple_music`, `youtube_music` e `tidal`.
- `videos`: cada um com `section` (`live` ou `extras`); `genres`, lista com até três gêneros (as tags mais
  votadas no MusicBrainz, sem repetir; `[]` se não houver); `genre`, o primeiro deles ou `null` (mantido para
  quem lê o formato antigo); `country`, código ISO de duas letras (ex. `BR`) ou `null`; `views`, visualizações
  na hora da coleta, ou `null`.
- `edition_key`, `request_id`, `window` (`start` e `end` da coleta), `run` e `warnings`.

## Configuração no GitHub

Segredos do repositório (Settings → Secrets and variables → Actions):

- `YOUTUBE_API_KEY`: chave da YouTube Data API v3.

O usuário do ListenBrainz (`igorbdm`) está no próprio workflow. ListenBrainz,
MusicBrainz, Cover Art Archive e iTunes não pedem chave.

No CMS, o token do GitHub precisa ser um *fine-grained token* com acesso só a
este repositório e as permissões **Actions: Read and write** e
**Contents: Read**.

## Rodar localmente

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests

# coleta real (precisa das chaves no ambiente)
EDITION_KEY=local-test REQUEST_ID=local-1 YOUTUBE_API_KEY=… LISTENBRAINZ_USERNAME=igorbdm python src/main.py
```

## Arquivos

| Arquivo | O que faz |
| --- | --- |
| `src/main.py` | Lê os parâmetros, coleta e grava o resultado |
| `src/channels.py` | Canais acompanhados e seus filtros |
| `src/collector.py` | Busca os vídeos no YouTube |
| `src/titles.py` | Título padronizado "Artista — Programa" |
| `src/genres.py` | Até três gêneros do artista (correções do CMS com gêneros separados por vírgula, cache, MusicBrainz, YouTube) |
| `src/song_of_the_week.py` | Sorteio da Song of the Week |
| `src/listenbrainz.py` | Músicas ouvidas no ListenBrainz (plays, álbum e capa) |
| `src/itunes.py` | Álbum e capa no iTunes, quando o ListenBrainz não tem a capa |
| `src/musicbrainz.py` | Acesso ao MusicBrainz (uma consulta por segundo), usado por gênero e origem |
| `src/countries.py` | País de origem do artista (correções do CMS, cache, MusicBrainz) |
| `src/streaming_links.py` | Links do Spotify, Apple Music, YouTube Music e Tidal |
| `src/utils.py` | Datas do feed do YouTube com fuso horário |
| `data/artist_genres.json` | Cache dos gêneros descobertos, uma lista por artista (atualizado pelo workflow; entradas antigas com um gênero só são consultadas de novo) |
| `data/artist_countries.json` | Cache das origens descobertas (atualizado pelo workflow; vazio = não encontrado) |
| `results/` | Um JSON por edição coletada |
