import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import unittest.mock
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import collector
from utils import parse_date


class CollectorTests(unittest.TestCase):
    def test_contains_any_is_case_insensitive(self):
        self.assertTrue(collector.contains_any("A FULL performance", ["full performance"]))
        self.assertFalse(collector.contains_any("A concert", ["full performance"]))

    def test_get_uploads_playlist_id_swaps_prefix(self):
        self.assertEqual(
            collector.get_uploads_playlist_id("UC3I2GFN_F8WudD_2jUZbojA"),
            "UU3I2GFN_F8WudD_2jUZbojA",
        )

    def test_parse_duration_converts_youtube_duration_to_seconds(self):
        self.assertEqual(collector.parse_duration("PT10M"), 600)
        self.assertEqual(collector.parse_duration("PT1H2M3S"), 3723)
        self.assertEqual(collector.parse_duration("PT45S"), 45)

    def test_parse_duration_rejects_invalid_duration(self):
        with self.assertRaises(ValueError):
            collector.parse_duration("10 minutes")

    def test_get_feed_applies_minimum_duration(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        playlist_response = {
            "items": [
                {
                    "snippet": {
                        "title": "Short performance",
                        "publishedAt": recent,
                        "resourceId": {"videoId": "short"},
                    }
                },
                {
                    "snippet": {
                        "title": "Long performance",
                        "publishedAt": recent,
                        "resourceId": {"videoId": "long"},
                    }
                },
            ]
        }

        config = {
            "id": "UC3I2GFN_F8WudD_2jUZbojA",
            "keep": [],
            "ignore": [],
            "min_duration": 600,
        }

        with patch.object(
            collector,
            "fetch_playlist_page",
            return_value=playlist_response,
        ), patch.object(
            collector,
            "fetch_video_durations",
            return_value={
                "short": 599,
                "long": 600,
            },
        ):
            feed = collector.get_feed("Test Channel", config)

        self.assertEqual(
            [video["video_id"] for video in feed],
            ["long"],
        )


    def test_pitchfork_keeps_only_full_over_under_episodes(self):
        from channels import CHANNELS

        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        uploads = {
            "full": ("Audrey Hobert Rates Podcasts, Don Toliver, and Disney Adults | Pitchfork", 599),
            "clip": ("Audrey Hobert Rates Don Toliver", 31),
            "teaser": ("Audrey Hobert Does Pitchfork's Over/Under", 10),
            "other": ("Judeline's Perfect 10", 162),
        }
        playlist_response = {"items": [
            {"snippet": {"title": title, "publishedAt": recent, "resourceId": {"videoId": video_id}}}
            for video_id, (title, _) in uploads.items()
        ]}

        with patch.object(collector, "fetch_playlist_page", return_value=playlist_response), \
            patch.object(collector, "fetch_video_durations", side_effect=lambda ids: {
                video_id: uploads[video_id][1] for video_id in ids
            }):
            feed = collector.get_feed("Pitchfork", CHANNELS["Pitchfork"])

        self.assertEqual([video["video_id"] for video in feed], ["full"])
        self.assertEqual(feed[0]["section"], "extras")



class DateTests(unittest.TestCase):
    def test_collection_start_is_previous_friday_at_midnight(self):
        from main import get_collection_start

        start = get_collection_start(date(2026, 8, 28))

        self.assertEqual(start.isoformat(), "2026-08-21T00:00:00-03:00")

    def test_get_feed_stops_at_previous_edition_boundary(self):
        boundary = "2026-08-21T00:00:00+00:00"
        newer = "2026-08-22T10:00:00+00:00"

        playlist_response = {
            "items": [
                {
                    "snippet": {
                        "title": "New video",
                        "publishedAt": newer,
                        "resourceId": {"videoId": "new"},
                    }
                },
                {
                    "snippet": {
                        "title": "Boundary video",
                        "publishedAt": boundary,
                        "resourceId": {"videoId": "boundary"},
                    }
                },
                {
                    "snippet": {
                        "title": "Older video",
                        "publishedAt": "2026-08-20T23:00:00+00:00",
                        "resourceId": {"videoId": "old"},
                    }
                },
            ]
        }

        config = {
            "id": "UC3I2GFN_F8WudD_2jUZbojA",
            "keep": [],
            "ignore": [],
        }

        with patch.object(collector, "fetch_playlist_page", return_value=playlist_response):
            feed = collector.get_feed("Test Channel", config, since=parse_date(boundary))

        self.assertEqual([video["video_id"] for video in feed], ["new"])

    def test_edition_date_is_friday(self):
        from main import get_edition_date

        self.assertEqual(get_edition_date(date(2026, 8, 28)), date(2026, 8, 28))
        self.assertEqual(get_edition_date(date(2026, 8, 27)), date(2026, 8, 28))
        self.assertEqual(get_edition_date(date(2026, 8, 29)), date(2026, 9, 4))


class SongOfTheWeekTests(unittest.TestCase):
    def track(self, title, plays=1, artist="Artist"):
        return {"artist": artist, "title": title, "plays": plays}

    def test_never_picks_a_song_already_in_history(self):
        import random
        from song_of_the_week import choose_track

        tracks = [self.track("Old"), self.track("New")]
        history = [{"artist": "ARTIST", "title": " old "}]

        for seed in range(50):
            self.assertEqual(
                choose_track(tracks, history, random.Random(seed))["title"],
                "New",
            )

    def test_only_top_ten_new_songs_are_candidates(self):
        import random
        from song_of_the_week import choose_track

        tracks = [self.track(f"Song {index}") for index in range(15)]
        history = [{"artist": "Artist", "title": "Song 0"}]

        picked = {
            choose_track(tracks, history, random.Random(seed))["title"]
            for seed in range(300)
        }

        self.assertEqual(picked, {f"Song {index}" for index in range(1, 11)})

    def test_songs_with_more_plays_are_picked_more_often(self):
        import random
        from song_of_the_week import choose_track

        tracks = [self.track("Many", plays=16), self.track("Few", plays=1)]
        rng = random.Random(0)

        picks = [choose_track(tracks, [], rng)["title"] for _ in range(2000)]

        # Peso = raiz dos plays: 4 contra 1, ou seja, ~80% para "Many".
        self.assertAlmostEqual(picks.count("Many") / len(picks), 0.8, delta=0.04)

    def test_prefers_artists_not_recommended_recently(self):
        import random
        from song_of_the_week import choose_track

        tracks = [
            self.track("Hit", plays=50, artist="Recent"),
            self.track("Deep Cut", plays=1, artist="Fresh"),
        ]
        history = [{"artist": "recent", "title": "Older Song"}]

        for seed in range(50):
            self.assertEqual(
                choose_track(tracks, history, random.Random(seed))["artist"],
                "Fresh",
            )

    def test_recent_artist_is_still_picked_when_there_is_no_alternative(self):
        from song_of_the_week import choose_track

        tracks = [self.track("Another Song", artist="Recent")]
        history = [{"artist": "Recent", "title": "Older Song"}]

        self.assertEqual(choose_track(tracks, history)["title"], "Another Song")

    def test_artists_from_older_editions_are_no_longer_avoided(self):
        import random
        from song_of_the_week import RECENT_ARTIST_EDITIONS, choose_track

        history = [{"artist": "Old Favorite", "title": "First"}] + [
            {"artist": f"Artist {index}", "title": "Song"}
            for index in range(RECENT_ARTIST_EDITIONS)
        ]
        tracks = [
            self.track("Second", plays=1, artist="Old Favorite"),
            self.track("Other", plays=1, artist="Someone"),
        ]

        picked = {
            choose_track(tracks, history, random.Random(seed))["artist"]
            for seed in range(100)
        }

        self.assertEqual(picked, {"Old Favorite", "Someone"})

    def test_returns_none_when_every_song_was_recommended(self):
        from song_of_the_week import choose_track

        self.assertIsNone(choose_track(
            [self.track("Old")],
            [{"artist": "Artist", "title": "Old"}],
        ))

    def listen(self, title, artist="Artist", days_ago=1, client="listenbrainz", album=None, cover=None):
        import time

        metadata = {
            "artist_name": artist,
            "track_name": title,
            "release_name": album,
            "additional_info": {"submission_client": client},
        }
        if cover:
            metadata["mbid_mapping"] = {"caa_release_mbid": cover, "caa_id": 1}
        return {"listened_at": int(time.time()) - days_ago * 86400, "track_metadata": metadata}

    def test_falls_back_to_last_30_days_when_week_has_no_new_song(self):
        import song_of_the_week

        listens = [self.listen("Old", days_ago=1), self.listen("Monthly", days_ago=20, album="Record", cover="rel-1")]

        with patch.object(song_of_the_week.listenbrainz, "get_listens", return_value=listens), \
            patch.object(song_of_the_week.itunes, "get_track_info") as itunes, \
            patch.object(song_of_the_week, "get_streaming_links", return_value={"spotify": "https://s"}):
            pick = song_of_the_week.get_song_of_the_week([{"artist": "Artist", "title": "Old"}], "user")

        itunes.assert_not_called()
        self.assertEqual(pick, {
            "artist": "Artist",
            "title": "Monthly",
            "album": "Record",
            "image": "https://coverartarchive.org/release/rel-1/front-500",
            "links": {"spotify": "https://s"},
            "source": "draw",
        })

    def test_top_tracks_counts_plays_and_ignores_older_listens(self):
        import listenbrainz

        listens = [
            self.listen("Once", days_ago=1),
            self.listen("Twice", days_ago=2),
            self.listen("twice ", artist="artist", days_ago=3),
            self.listen("Too Old", days_ago=10),
        ]
        since = listens[0]["listened_at"] - 7 * 86400

        tracks = listenbrainz.top_tracks(listens, since)

        self.assertEqual([(track["title"], track["plays"]) for track in tracks], [("Twice", 2), ("Once", 1)])

    def test_same_play_sent_by_two_sources_counts_once(self):
        import listenbrainz

        spotify = self.listen("cityscape", artist="tommy oeffling, dylanwesch", cover="rel-1")
        lastfm = self.listen("cityscape", artist="tommy oeffling", client="ListenBrainz lastfm importer v2")
        lastfm["listened_at"] -= 151
        replay = self.listen("cityscape", artist="tommy oeffling, dylanwesch")
        replay["listened_at"] += 200  # tocou de novo pelo mesmo app: vale

        tracks = listenbrainz.top_tracks([spotify, lastfm, replay])

        self.assertEqual(sum(track["plays"] for track in tracks), 2)

    def test_get_listens_pages_back_until_since(self):
        import listenbrainz

        def page(*timestamps):
            return {"payload": {"listens": [{"listened_at": ts} for ts in timestamps]}}

        with patch.object(listenbrainz, "PAGE_SIZE", 2), \
            patch.object(listenbrainz, "call_api", side_effect=[page(50, 40), page(30, 20), page(10)]) as api:
            listens = listenbrainz.get_listens("user", since=25)

        self.assertEqual([listen["listened_at"] for listen in listens], [50, 40, 30])
        self.assertEqual(api.call_args_list[1].kwargs, {"count": 2, "max_ts": 40})
        self.assertEqual(api.call_count, 2)

    def test_manual_choice_skips_the_draw_even_if_already_recommended(self):
        import song_of_the_week

        history = [{"artist": "Artist", "title": "Old"}]
        listens = [self.listen("Old", album="Record", cover="rel-1"), self.listen("Other")]

        with patch.object(song_of_the_week.listenbrainz, "get_listens", return_value=listens), \
            patch.object(song_of_the_week, "choose_track") as draw, \
            patch.object(song_of_the_week, "get_streaming_links", return_value={"spotify": "https://s"}):
            pick = song_of_the_week.get_song_of_the_week(history, "user", choice={"artist": "Artist", "title": "Old"})

        draw.assert_not_called()
        self.assertEqual(pick, {
            "artist": "Artist",
            "title": "Old",
            "album": "Record",
            "image": "https://coverartarchive.org/release/rel-1/front-500",
            "links": {"spotify": "https://s"},
            "source": "manual",
        })

    def test_manual_choice_survives_listenbrainz_and_itunes_failure(self):
        import song_of_the_week

        with patch.object(song_of_the_week.listenbrainz, "get_listens", side_effect=RuntimeError("offline")), \
            patch.object(song_of_the_week.itunes, "get_track_info", side_effect=RuntimeError("offline")), \
            patch.object(song_of_the_week, "get_streaming_links", return_value={}):
            pick = song_of_the_week.get_song_of_the_week([], "user", choice={"artist": "Artist", "title": "Song"})

        self.assertEqual((pick["title"], pick["album"], pick["image"], pick["source"]), ("Song", None, None, "manual"))

    def test_listenbrainz_failure_does_not_block_the_newsletter(self):
        import song_of_the_week

        with patch.object(song_of_the_week.listenbrainz, "get_listens", side_effect=RuntimeError("offline")):
            self.assertIsNone(song_of_the_week.get_song_of_the_week([], "user"))

    def test_without_username_there_is_no_song(self):
        import song_of_the_week

        with patch.dict("os.environ", {}, clear=True), \
            patch.object(song_of_the_week.listenbrainz, "get_listens") as listens:
            self.assertIsNone(song_of_the_week.get_song_of_the_week([]))

        listens.assert_not_called()

    def test_cover_falls_back_to_itunes(self):
        import song_of_the_week

        listens = [self.listen("New", album="Single")]
        found = {"album": "Album", "image": "https://is1.mzstatic.com/x/500x500bb.jpg"}

        with patch.object(song_of_the_week.listenbrainz, "get_listens", return_value=listens), \
            patch.object(song_of_the_week.itunes, "get_track_info", return_value=found), \
            patch.object(song_of_the_week, "get_streaming_links", return_value={}):
            pick = song_of_the_week.get_song_of_the_week([], "user")

        self.assertEqual((pick["album"], pick["image"]), ("Album", found["image"]))

    def test_missing_cover_keeps_the_song(self):
        import song_of_the_week

        with patch.object(song_of_the_week.listenbrainz, "get_listens", return_value=[self.listen("New", album="Single")]), \
            patch.object(song_of_the_week.itunes, "get_track_info", side_effect=RuntimeError("404")), \
            patch.object(song_of_the_week, "get_streaming_links", return_value={}):
            pick = song_of_the_week.get_song_of_the_week([], "user")

        self.assertEqual(pick["title"], "New")
        self.assertEqual(pick["album"], "Single")
        self.assertIsNone(pick["image"])

    def test_itunes_only_accepts_the_same_song(self):
        import itunes

        def search(url, params, timeout):
            response = unittest.mock.Mock()
            response.json.return_value = {"results": [
                {"artistName": "Someone Else", "trackName": "Trip", "collectionName": "Wrong", "artworkUrl100": "https://a/100x100bb.jpg"},
                {"artistName": "jizue", "trackName": "Trip (Live)", "collectionName": "ROOM", "artworkUrl100": "https://b/100x100bb.jpg"},
            ]}
            return response

        with patch.object(itunes.requests, "get", side_effect=search):
            self.assertEqual(itunes.get_track_info("jizue", "trip"), {"album": "ROOM", "image": "https://b/500x500bb.jpg"})
            self.assertEqual(itunes.get_track_info("jizue", "Other"), {"album": None, "image": None})

    def run_main(self, branch, result):
        import main
        from song_of_the_week import load_history, save_to_history

        sender = unittest.mock.Mock()
        sender.send.return_value = result
        pick = {"artist": "Artist", "title": "Song", "image": None}
        video = {"channel": "KEXP", "title": "Video", "link": "https://www.youtube.com/watch?v=x"}

        with patch.object(main, "get_edition_date", return_value=date(2026, 8, 28)), \
            patch.dict("os.environ", {"GITHUB_REF_NAME": branch, "GITHUB_RUN_ID": "1"}, clear=True), \
            patch.object(main, "get_newsletter_sender", return_value=sender), \
            patch.object(main, "get_feed", return_value=[video]), \
            patch.object(main, "get_song_of_the_week", return_value=pick), \
            patch.object(main, "save_to_history", side_effect=lambda pick, edition_id: save_to_history(pick, edition_id, self.history_path)):
            main.main()

        return load_history(self.history_path)


class GenreTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tempdir = tempfile.TemporaryDirectory()
        self.cache_path = Path(self.tempdir.name) / "artist_genres.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_each_channel_title_becomes_artist_and_program(self):
        from channels import CHANNELS
        from titles import display_title

        examples = [
            ("KEXP", "Death Cab For Cutie - Full Performance (Live on KEXP)", "Death Cab For Cutie — Live on KEXP"),
            ("Tiny Desk", "Tim Bernardes: Tiny Desk Concert", "Tim Bernardes — Tiny Desk Concert"),
            ("Audiotree", "Cold Steel on Audiotree Live (Full Session)", "Cold Steel — Audiotree Live"),
            ("La Blogothèque", "Naomi Greene | A Take Away Show", "Naomi Greene — A Take Away Show"),
            ("La Blogothèque", "Piers Faccini & Ballaké Sissoko | A Take Away Show at @sudsarles", "Piers Faccini & Ballaké Sissoko — A Take Away Show"),
            ("La Blogothèque", "Adèle Castillon | Live Session for The Collective by Stradivarius", "Adèle Castillon — Live Session"),
            ("KCRW", "Sébastien Tellier: Live on KCRW", "Sébastien Tellier — Live on KCRW"),
            ("Cultura Livre", "CULTURA LIVRE | Fera Neném | 10/10/26", "Fera Neném — Cultura Livre"),
            # A grafia do artista é a do título do vídeo.
            ("Cultura Livre", "NIGÉRIA FUTEBOL CLUBE NO CULTURA LIVRE", "NIGÉRIA FUTEBOL CLUBE — Cultura Livre"),
            ("Amoeba Music", 'Elvis Costello\'s "What\'s In My Bag?" | Amoeba Music', "Elvis Costello — What's In My Bag?"),
            ("Amoeba Music", "Daniel Lanois | What's in My Bag? (Teaser)", "Daniel Lanois — What's In My Bag?"),
            ("Pitchfork", "Audrey Hobert Rates Podcasts, Don Toliver, and Disney Adults | Pitchfork", "Audrey Hobert — Over/Under"),
            ("Premier Guitar", "Rig Rundown: GA-20", "GA-20 — Rig Rundown"),
            ("Premier Guitar", "Pavement Rig Rundown", "Pavement — Rig Rundown"),
            ("Premier Guitar", "Crowbar Rig Rundown with Kirk Windstein, Pat Bruders & Matt Brunson", "Crowbar — Rig Rundown"),
            ("Premier Guitar", "Marcus King Band Rig Rundown with Drew Smithers [2026]", "Marcus King Band — Rig Rundown"),
            ("Premier Guitar", "How Geese Get Their Unhinged Live Sound | Rig Rundown", "Geese — Rig Rundown"),
            ("Premier Guitar", "How Drug Church Gets Their Sound | Rig Rundown", "Drug Church — Rig Rundown"),
            ("Premier Guitar", "Rig Rundown: Muse's Matt Bellamy & Chris Wolstenholme", "Muse — Rig Rundown"),
            ("Premier Guitar", "AC/DC's Angus Young & Stevie Young Rig Rundown", "AC/DC — Rig Rundown"),
            ("Premier Guitar", "Bring Me the Horizon's Lee Malia Rig Rundown", "Bring Me the Horizon — Rig Rundown"),
            ("Premier Guitar", "The Black Crowes' Rich Robinson Rig Rundown [2026]", "The Black Crowes — Rig Rundown"),
            ("Premier Guitar", "Hayley Williams' Band Rig Rundown with Joey Howard", "Hayley Williams — Rig Rundown"),
            ("Premier Guitar", "Rig Rundown: Dinosaur Jr 's J Mascis [2022]", "Dinosaur Jr — Rig Rundown"),
            ("Premier Guitar", "Your New Favorite Guitarist: Seth Lee Jones Rig Rundown", "Seth Lee Jones — Rig Rundown"),
            # Apóstrofo que faz parte do nome da banda.
            ("Premier Guitar", "Jane's Addiction Rig Rundown", "Jane's Addiction — Rig Rundown"),
            ("Premier Guitar", "Jane's Addiction's Dave Navarro Rig Rundown", "Jane's Addiction — Rig Rundown"),
            ("Premier Guitar", "Guns N' Roses Rig Rundown", "Guns N' Roses — Rig Rundown"),
            ("Premier Guitar", "Guns N' Roses' Slash, Duff McKagan & Richard Fortus Rig Rundown", "Guns N' Roses — Rig Rundown"),
            ("Premier Guitar", "Rig Rundown - Meshuggah's Fredrik Thordendal, Mårten Hagström, & Dick Lövgren", "Meshuggah — Rig Rundown"),
            ("Guitar Moves", "Gwenifer Raymond | Guitar Moves Interview", "Gwenifer Raymond — Guitar Moves"),
            ("Guitar Moves", "Marcus King | Guitar Moves interview", "Marcus King — Guitar Moves"),
            ("Guitar Moves", "Josh Homme of Queens of the Stone Age | Guitar Moves Interview", "Josh Homme — Guitar Moves"),
            ("Guitar Moves", "Albert Hammond Jr. of The Strokes | Guitar Moves Interview", "Albert Hammond Jr. — Guitar Moves"),
            ("Guitar Moves", "Slipknot's James Root | Guitar Moves Interview", "James Root — Guitar Moves"),
            ("Guitar Moves", "Lemmy | Guitar Moves Interview", "Lemmy — Guitar Moves"),
        ]

        for channel, title, expected in examples:
            with self.subTest(title=title):
                self.assertEqual(display_title(title, CHANNELS[channel]), expected)

    def test_guitar_programs_keep_only_full_episodes(self):
        from channels import CHANNELS

        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        cases = {
            "Premier Guitar": {
                "full": ("Thundercat Rig Rundown", 2400),
                "short": ("Thundercat Rig Rundown #shorts", 45),
                "trailer": ("Matt Sweeney's Fingerstyle Approach | Superwolves Rig Rundown Trailer", 700),
                "list": ("The Top 10 Rig Rundowns of 2025", 1800),
                "other": ("Fender's Modern Nashville Telecaster", 900),
            },
            "Guitar Moves": {
                "full": ("Gwenifer Raymond | Guitar Moves Interview", 1100),
                "short": ("Gwenifer Raymond | Guitar Moves Interview #shorts", 40),
                "clip": ("Matt Sweeney on Jake Bugg's Episode of Guitar Moves", 400),
            },
        }

        for channel, uploads in cases.items():
            with self.subTest(channel=channel):
                playlist_response = {"items": [
                    {"snippet": {"title": title, "publishedAt": recent, "resourceId": {"videoId": video_id}}}
                    for video_id, (title, _) in uploads.items()
                ]}
                with patch.object(collector, "fetch_playlist_page", return_value=playlist_response), \
                    patch.object(collector, "fetch_video_durations", side_effect=lambda ids: {
                        video_id: uploads[video_id][1] for video_id in ids
                    }):
                    feed = collector.get_feed(channel, CHANNELS[channel])

                self.assertEqual([video["video_id"] for video in feed], ["full"])
                self.assertEqual(feed[0]["section"], "extras")

    def test_title_outside_the_pattern_is_kept_as_is(self):
        from channels import CHANNELS
        from titles import display_title

        title = "KEXP Holiday Special 2026"
        self.assertEqual(display_title(title, CHANNELS["KEXP"]), title)
        self.assertEqual(display_title(title, {}), title)

    def test_la_blogotheque_keeps_only_complete_sessions(self):
        from channels import CHANNELS

        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        uploads = {
            "full_take_away": "Naomi Greene | A Take Away Show",
            "full_live_session": "Adèle Castillon | Live Session for The Collective by Stradivarius",
            "fragment_live_session": "Rostam - The Road to Death | Live Session",
            "fragment_take_away": "Voxtrot - Trouble | A Take Away Show",
            "festival": "Thylacine | Live at @arteconcert Festival 2022 (Paris)",
            "series": "Peter Broderick | The Sounds of Ireland",
        }
        playlist_response = {"items": [
            {"snippet": {"title": title, "publishedAt": recent, "resourceId": {"videoId": video_id}}}
            for video_id, title in uploads.items()
        ]}

        with patch.object(collector, "fetch_playlist_page", return_value=playlist_response), \
            patch.object(collector, "fetch_video_durations", side_effect=lambda ids: {video_id: 900 for video_id in ids}):
            feed = collector.get_feed("La Blogothèque", CHANNELS["La Blogothèque"])

        self.assertEqual(
            sorted(video["video_id"] for video in feed),
            ["full_live_session", "full_take_away"],
        )


    def test_compound_names_are_split_and_accents_removed(self):
        from genres import artist_candidates

        self.assertEqual(
            artist_candidates("Hélio Ziskind e Fera Neném"),
            [
                "Hélio Ziskind e Fera Neném", "Helio Ziskind e Fera Nenem",
                "Hélio Ziskind", "Helio Ziskind", "Fera Neném", "Fera Nenem",
            ],
        )
        self.assertEqual(
            artist_candidates("Scott Ian of Anthrax"),
            ["Scott Ian of Anthrax", "Scott Ian", "Anthrax"],
        )

    def test_only_tags_that_are_genres_are_used(self):
        from genres import pick_genre

        self.assertEqual(pick_genre([
            ("motherfuckin rabbits ejaculating sunshine", 100),
            ("brazilian", 90),
            ("saxophone", 80),
            ("seen live", 70),
            ("Indie Rock", 60),
        ]), "indie rock")
        self.assertEqual(pick_genre([("Alt-country", 100)]), "alt-country")
        self.assertIsNone(pick_genre([("french", 100), ("jazz", 0)]))

    def add_genres(self, videos, overrides=None, cache=None, **patches):
        import genres

        if cache is not None:
            genres.save_json(cache, self.cache_path)

        channels = {"KEXP": {"artist_patterns": [r"^(?P<artist>.+?)\s+-\s+Full Performance"]}}

        with patch.object(genres.musicbrainz, "find_artist", **patches.get("musicbrainz", {"return_value": None})) as find_artist, \
            patch.object(genres.collector, "fetch_video_topics", **patches.get("youtube", {"return_value": {}})):
            genres.add_genres(videos, channels, overrides, self.cache_path)

        return find_artist

    def video(self, artist="Wednesday"):
        return {
            "channel": "KEXP",
            "title": f"{artist} - Full Performance (Live on KEXP)",
            "video_id": "abc",
        }

    def test_musicbrainz_genre_is_used_and_cached(self):
        import genres

        video = self.video()
        artist = {"name": "Wednesday", "tags": [
            {"name": "american", "count": 9}, {"name": "indie rock", "count": 4}, {"name": "shoegaze", "count": 5},
        ]}
        self.add_genres([video], musicbrainz={"return_value": artist})

        self.assertEqual(video["genre"], "shoegaze")
        self.assertEqual(video["genres"], ["shoegaze", "indie rock"])
        self.assertEqual(genres.load_json(self.cache_path), {"wednesday": ["shoegaze", "indie rock"]})

    def test_cached_genre_skips_musicbrainz(self):
        video = self.video()
        find_artist = self.add_genres([video], cache={"wednesday": ["indie rock", "shoegaze"]})

        self.assertEqual(video["genres"], ["indie rock", "shoegaze"])
        self.assertEqual(video["genre"], "indie rock")
        find_artist.assert_not_called()

    def test_old_single_genre_cache_is_refreshed_from_musicbrainz(self):
        import genres

        video = self.video()
        artist = {"name": "Wednesday", "tags": [{"name": "indie rock", "count": 4}, {"name": "alt-country", "count": 3}]}
        self.add_genres([video], cache={"wednesday": "indie rock"}, musicbrainz={"return_value": artist})

        self.assertEqual(video["genres"], ["indie rock", "alt-country"])
        self.assertEqual(genres.load_json(self.cache_path), {"wednesday": ["indie rock", "alt-country"]})

    def test_old_single_genre_cache_is_kept_when_musicbrainz_is_down(self):
        import genres

        video = self.video()
        self.add_genres(
            [video],
            cache={"wednesday": "indie rock"},
            musicbrainz={"side_effect": genres.musicbrainz.Unavailable("HTTP 503")},
        )

        self.assertEqual(video["genres"], ["indie rock"])

    def test_up_to_three_genres_most_voted_without_repeating(self):
        from genres import pick_genres

        self.assertEqual(pick_genres([
            ("alternative hip hop", 2), ("hip hop", 1), ("experimental hip hop", 1), ("seen live", 9),
        ]), ["alternative hip hop", "experimental hip hop"])
        self.assertEqual(pick_genres([
            ("indie rock", 8), ("post-punk", 6), ("post-punk revival", 5), ("art rock", 1), ("dream pop", 1),
        ]), ["indie rock", "post-punk", "dream pop"])
        # No empate, a mais específica: "rock" não entra depois de "alternative rock".
        self.assertEqual(pick_genres([
            ("singer-songwriter", 4), ("rock", 2), ("alternative rock", 2), ("gothic rock", 2), ("darkwave", 1),
        ]), ["singer-songwriter", "alternative rock", "gothic rock"])
        self.assertEqual(pick_genres([("french", 9)]), [])

    def test_musicbrainz_outage_falls_back_to_youtube_without_insisting(self):
        import genres

        videos = [self.video("Wednesday"), self.video("Rostam")]
        find_artist = self.add_genres(
            videos,
            musicbrainz={"side_effect": genres.musicbrainz.Unavailable("HTTP 503")},
            youtube={"return_value": {"abc": ["https://en.wikipedia.org/wiki/Rock_music"]}},
        )

        self.assertEqual(find_artist.call_count, 1)
        self.assertEqual([video["genre"] for video in videos], ["rock", "rock"])
        self.assertFalse(self.cache_path.exists())

    def test_manual_override_wins_and_empty_override_hides_the_badge(self):
        corrected, hidden = self.video("Wednesday"), self.video("Rostam")
        self.add_genres(
            [corrected, hidden],
            overrides={"WEDNESDAY": "indie rock, Alt-Country, slowcore, emo", "Rostam": ""},
            cache={"wednesday": ["shoegaze"]},
            youtube={"return_value": {"abc": ["https://en.wikipedia.org/wiki/Pop_music"]}},
        )

        self.assertEqual(corrected["genres"], ["indie rock", "alt-country", "slowcore"])
        self.assertEqual(corrected["genre"], "indie rock")
        self.assertEqual(hidden["genres"], [])
        self.assertIsNone(hidden["genre"])

    def test_youtube_topic_is_the_fallback(self):
        video = self.video()
        self.add_genres([video], youtube={"return_value": {"abc": [
            "https://en.wikipedia.org/wiki/Music",
            "https://en.wikipedia.org/wiki/Rock_music",
        ]}})

        self.assertEqual(video["genre"], "rock")
        self.assertEqual(video["genres"], ["rock"])

    def test_failures_leave_videos_without_badge(self):
        video = self.video()
        self.add_genres(
            [video],
            musicbrainz={"side_effect": RuntimeError("offline")},
            youtube={"side_effect": RuntimeError("quota")},
        )

        self.assertIsNone(video["genre"])

    def test_beyond_the_stage_videos_are_not_looked_up(self):
        video = {
            "channel": "KEXP",
            "section": "extras",
            "title": "Wednesday - Full Performance (Live on KEXP)",
            "video_id": "abc",
        }
        find_artist = self.add_genres([video], youtube={"return_value": {"abc": [
            "https://en.wikipedia.org/wiki/Rock_music",
        ]}})

        self.assertIsNone(video["genre"])
        find_artist.assert_not_called()


class StreamingLinksTests(unittest.TestCase):
    def response(self, data):
        from unittest.mock import Mock

        return Mock(json=Mock(return_value=data), raise_for_status=Mock())

    def test_apple_music_ignores_other_versions_and_artists(self):
        import streaming_links

        results = {"results": [
            {"artistName": "A$AP Rocky", "trackName": "Life Is", "trackViewUrl": "https://wrong"},
            {"artistName": "Jessica Pratt", "trackName": "Life Is (Live)", "trackViewUrl": "https://live"},
            {"artistName": "Jessica Pratt", "trackName": "Life Is (feat. Someone)", "trackViewUrl": "https://studio"},
        ]}

        with patch.object(streaming_links.requests, "get", return_value=self.response(results)):
            self.assertEqual(streaming_links.find_apple_music("Jessica Pratt", "Life Is"), "https://studio")

        with patch.object(streaming_links.requests, "get", return_value=self.response({"results": results["results"][:2]})):
            self.assertIsNone(streaming_links.find_apple_music("Jessica Pratt", "Life Is"))

    def test_apple_music_removes_tracking_parameter(self):
        import streaming_links

        results = {"results": [{
            "artistName": "Jessica Pratt",
            "trackName": "Life Is",
            "trackViewUrl": "https://music.apple.com/us/album/life-is/1?i=2&uo=4",
        }]}

        with patch.object(streaming_links.requests, "get", return_value=self.response(results)):
            self.assertEqual(
                streaming_links.find_apple_music("Jessica Pratt", "Life Is"),
                "https://music.apple.com/us/album/life-is/1?i=2",
            )

    def test_youtube_music_only_accepts_topic_channel(self):
        import streaming_links

        items = {"items": [
            {"id": {"videoId": "fan"}, "snippet": {"channelTitle": "Some Fan", "title": "Life Is"}},
            {"id": {"videoId": "official"}, "snippet": {"channelTitle": "Jessica Pratt - Topic", "title": "Life Is"}},
        ]}

        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "key"}), \
            patch.object(streaming_links.requests, "get", return_value=self.response(items)):
            self.assertEqual(
                streaming_links.find_youtube_music("Jessica Pratt", "Life Is"),
                "https://music.youtube.com/watch?v=official",
            )

    def test_failures_fall_back_to_search_links(self):
        import streaming_links

        with patch.object(streaming_links, "find_apple_music", side_effect=RuntimeError("offline")), \
            patch.object(streaming_links, "find_youtube_music", return_value=None):
            links = streaming_links.get_streaming_links("Jessica Pratt", "Life Is")

        self.assertEqual(links, {
            "spotify": "https://open.spotify.com/search/Jessica%20Pratt%20Life%20Is",
            "apple_music": "https://music.apple.com/search?term=Jessica+Pratt+Life+Is",
            "youtube_music": "https://music.youtube.com/search?q=Jessica+Pratt+Life+Is",
            "tidal": "https://tidal.com/search?q=Jessica+Pratt+Life+Is",
        })

    def test_direct_links_replace_search_links(self):
        import streaming_links

        with patch.object(streaming_links, "find_apple_music", return_value="https://apple"), \
            patch.object(streaming_links, "find_youtube_music", return_value="https://ytm"):
            links = streaming_links.get_streaming_links("Artist", "Song")

        self.assertEqual(links["apple_music"], "https://apple")
        self.assertEqual(links["youtube_music"], "https://ytm")
        self.assertTrue(links["spotify"].startswith("https://open.spotify.com/search/"))


class CountryTests(unittest.TestCase):
    """Origem dos artistas (bandeira). O MusicBrainz é sempre simulado."""

    def setUp(self):
        import countries

        self.countries = countries
        self.tempdir = tempfile.TemporaryDirectory()
        self.cache_path = Path(self.tempdir.name) / "artist_countries.json"
        self.channels = {"KEXP": {"artist_patterns": [r"^(?P<artist>.+?) - Full Performance"]}}

    def tearDown(self):
        self.tempdir.cleanup()

    def video(self, artist, section="live"):
        return {"channel": "KEXP", "section": section, "title": f"{artist} - Full Performance (Live on KEXP)"}

    def fake_api(self, responses):
        calls = []

        def call(path, **params):
            calls.append((path, params))
            key = params.get("query", path)
            return responses.get(key, {"artists": []})

        return call, calls

    def run_add(self, videos, responses, overrides=None):
        call, calls = self.fake_api(responses)
        with patch.object(self.countries.musicbrainz, "call_api", side_effect=call):
            self.countries.add_countries(videos, self.channels, overrides=overrides, cache_path=self.cache_path)
        return calls

    def test_country_comes_from_musicbrainz_and_is_cached(self):
        videos = [self.video("Maurício Pereira")]
        responses = {'artist:"Maurício Pereira"': {"artists": [{"name": "Maurício Pereira", "score": 100, "country": "BR"}]}}

        self.run_add(videos, responses)

        self.assertEqual(videos[0]["country"], "BR")
        self.assertEqual(json.loads(self.cache_path.read_text(encoding="utf-8")), {"maurício pereira": "BR"})

        # Na semana seguinte, o cache evita a consulta.
        again = [self.video("Maurício Pereira")]
        self.assertEqual(self.run_add(again, {}), [])
        self.assertEqual(again[0]["country"], "BR")

    def test_city_area_climbs_to_the_country(self):
        videos = [self.video("INOHA")]
        responses = {
            'artist:"INOHA"': {"artists": [{"name": "INOHA", "score": 100, "area": {"id": "san-antonio"}}]},
            "area/san-antonio": {"name": "San Antonio", "relations": [
                {"type": "part of", "direction": "backward", "area": {"id": "bexar"}},
                {"type": "part of", "direction": "forward", "area": {"id": "some-neighborhood"}},
            ]},
            "area/bexar": {"name": "Bexar County", "relations": [
                {"type": "part of", "direction": "backward", "area": {"id": "texas", "iso-3166-2-codes": ["US-TX"]}},
            ]},
        }

        self.run_add(videos, responses)

        self.assertEqual(videos[0]["country"], "US")

    def test_other_artists_with_similar_names_are_ignored(self):
        videos = [self.video("Robyn")]
        responses = {'artist:"Robyn"': {"artists": [
            {"name": "Robyn Hitchcock", "score": 95, "country": "GB"},
            {"name": "robyn", "score": 100, "country": "SE"},
        ]}}

        self.run_add(videos, responses)

        self.assertEqual(videos[0]["country"], "SE")

    def test_unknown_artist_is_cached_empty_and_has_no_flag(self):
        videos = [self.video("Nobody Knows")]

        self.run_add(videos, {})

        self.assertIsNone(videos[0]["country"])
        self.assertEqual(json.loads(self.cache_path.read_text(encoding="utf-8")), {"nobody knows": ""})

    def test_manual_override_wins_and_empty_override_hides_the_flag(self):
        videos = [self.video("Commemorate"), self.video("Robyn")]

        calls = self.run_add(videos, {}, overrides={"commemorate": "my", "Robyn": ""})

        self.assertEqual(calls, [])
        self.assertEqual([video["country"] for video in videos], ["MY", None])

    def test_beyond_the_stage_videos_are_not_looked_up(self):
        videos = [self.video("Daniel Lanois", section="extras")]

        self.assertEqual(self.run_add(videos, {}), [])
        self.assertIsNone(videos[0]["country"])

    def test_musicbrainz_outage_leaves_artists_for_the_next_edition(self):
        videos = [self.video("Robyn"), self.video("INOHA")]

        with patch.object(self.countries.musicbrainz, "call_api", side_effect=self.countries.musicbrainz.Unavailable("HTTP 503")) as api:
            self.countries.add_countries(videos, self.channels, cache_path=self.cache_path)

        # Depois da primeira falha, não insiste nos outros artistas e não grava nada.
        self.assertEqual(api.call_count, 1)
        self.assertEqual([video["country"] for video in videos], [None, None])
        self.assertFalse(self.cache_path.exists())

    def test_busy_server_is_retried(self):
        import requests

        busy = unittest.mock.Mock(status_code=503)
        ok = unittest.mock.Mock(status_code=200)
        ok.json.return_value = {"artists": []}

        import musicbrainz

        with patch.object(musicbrainz.requests, "get", side_effect=[busy, ok]) as get, \
            patch.object(musicbrainz.time, "sleep"):
            self.assertEqual(musicbrainz.call_api("artist", query="x"), {"artists": []})

        self.assertEqual(get.call_count, 2)


class MainTests(unittest.TestCase):
    def environ(self, **values):
        return {"EDITION_KEY": "auto-2026-08-28", "REQUEST_ID": "e12-r1", **values}

    def test_parameters_default_to_friday_edition_and_previous_week(self):
        import main

        with patch.object(main, "get_edition_date", return_value=date(2026, 8, 28)):
            parameters = main.read_parameters(self.environ())

        self.assertEqual(parameters["edition_date"], date(2026, 8, 28))
        self.assertEqual(parameters["since"].isoformat(), "2026-08-21T00:00:00-03:00")
        self.assertEqual(parameters["song_history"], [])
        self.assertEqual(parameters["genre_overrides"], {})

    def test_parameters_come_from_the_cms(self):
        import main

        state = {
            "song_history": [{"artist": "Artist", "title": "Song", "edition": 3}, {"artist": ""}],
            "genre_overrides": {"Rostam": "", "Wednesday": "indie rock"},
        }
        parameters = main.read_parameters(self.environ(
            EDITION_DATE="2026-09-04", SINCE="2026-08-28T07:00:00-03:00", ENGINE_STATE=json.dumps(state),
        ))

        self.assertEqual(parameters["edition_date"], date(2026, 9, 4))
        self.assertEqual(parameters["since"].isoformat(), "2026-08-28T07:00:00-03:00")
        self.assertEqual(parameters["song_history"], [{"artist": "Artist", "title": "Song"}])
        self.assertEqual(parameters["genre_overrides"], {"Rostam": "", "Wednesday": "indie rock"})
        self.assertIsNone(parameters["song_choice"])

    def test_song_choice_comes_from_the_cms(self):
        import main

        for choice, expected in (
            ({"artist": " Artist ", "title": "Song"}, {"artist": "Artist", "title": "Song"}),
            ({"artist": "Artist", "title": ""}, None),
            ("Artist - Song", None),
        ):
            with self.subTest(choice=choice):
                parameters = main.read_parameters(self.environ(
                    EDITION_DATE="2026-09-04", ENGINE_STATE=json.dumps({"song_choice": choice}),
                ))
                self.assertEqual(parameters["song_choice"], expected)

    def test_invalid_keys_are_rejected(self):
        import main

        for values in ({"EDITION_KEY": "../etc"}, {"EDITION_KEY": ""}, {"REQUEST_ID": "a b"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                main.read_parameters(self.environ(**values))

    def collect(self, videos, pick):
        import main

        parameters = main.read_parameters(self.environ(
            EDITION_DATE="2026-08-28", ENGINE_STATE=json.dumps({"genre_overrides": {"Wednesday": "slowcore"}, "country_overrides": {"Wednesday": "us"}}),
        ))
        since_values = []

        def feed(name, config, since=None):
            since_values.append(since)
            return [video for video in videos if video["channel"] == name]

        with patch.object(main, "get_feed", side_effect=feed), \
            patch.object(main, "get_song_of_the_week", return_value=pick) as song, \
            patch("genres.musicbrainz.find_artist", return_value=None), \
            patch("genres.collector.fetch_video_topics", return_value={}), \
            patch.object(main, "fetch_video_views", return_value={"a": 1200, "b": 300}), \
            patch.dict("os.environ", {"GITHUB_RUN_ID": "42", "GITHUB_REPOSITORY": "igorbdm/motif-engine"}, clear=True):
            result = main.collect(parameters)

        self.assertEqual(len(since_values), len(main.CHANNELS))
        self.assertTrue(all(value.isoformat() == "2026-08-21T00:00:00-03:00" for value in since_values))
        song.assert_called_once_with([], choice=None)
        return result

    def test_result_follows_the_cms_contract(self):
        videos = [
            {"channel": "KEXP", "section": "live", "title": "Wednesday - Full Performance (Live on KEXP)",
             "published": "2026-08-22T10:00:00Z", "link": "https://www.youtube.com/watch?v=a", "video_id": "a"},
            {"channel": "Amoeba Music", "section": "extras", "title": "Daniel Lanois | What's in My Bag?",
             "published": "2026-08-23T10:00:00Z", "link": "https://www.youtube.com/watch?v=b", "video_id": "b"},
        ]
        pick = {"artist": "Artist", "title": "Song", "album": None, "image": None, "links": {}}

        result = self.collect(videos, pick)

        self.assertEqual(result["schema"], 1)
        self.assertEqual(result["edition_key"], "auto-2026-08-28")
        self.assertEqual(result["request_id"], "e12-r1")
        self.assertEqual(result["edition_date"], "2026-08-28")
        self.assertEqual(result["run"], {"id": 42, "url": "https://github.com/igorbdm/motif-engine/actions/runs/42"})
        self.assertEqual(result["song_of_the_week"], pick)
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["videos"], [
            {"id": "a", "title": "Wednesday - Full Performance (Live on KEXP)", "display_title": "Wednesday — Live on KEXP",
             "channel": "KEXP", "link": "https://www.youtube.com/watch?v=a", "section": "live", "genre": "slowcore", "genres": ["slowcore"],
             "country": "US", "views": 1200, "published": "2026-08-22T10:00:00Z"},
            {"id": "b", "title": "Daniel Lanois | What's in My Bag?", "display_title": "Daniel Lanois — What's In My Bag?",
             "channel": "Amoeba Music", "link": "https://www.youtube.com/watch?v=b", "section": "extras", "genre": None, "genres": [],
             "country": None, "views": 300, "published": "2026-08-23T10:00:00Z"},
        ])

    def test_views_failure_does_not_block_the_edition(self):
        import main

        videos = [{"video_id": "a"}, {"video_id": "b"}]
        warnings = []
        with patch.object(main, "fetch_video_views", side_effect=RuntimeError("quota")):
            main.add_views(videos, warnings)

        self.assertEqual([video["views"] for video in videos], [None, None])
        self.assertEqual(len(warnings), 1)

    def test_views_are_fetched_in_batches_of_50(self):
        import collector

        response = unittest.mock.Mock()
        response.json.side_effect = [
            {"items": [{"id": f"v{i}", "statistics": {"viewCount": str(i)}} for i in range(50)]},
            {"items": [{"id": "v50", "statistics": {}}]},
        ]
        with patch.object(collector, "YOUTUBE_API_KEY", "key"), \
            patch.object(collector.requests, "get", return_value=response) as get:
            views = collector.fetch_video_views([f"v{i}" for i in range(51)])

        self.assertEqual(get.call_count, 2)
        self.assertEqual(views["v49"], 49)
        self.assertNotIn("v50", views)

    def test_empty_week_is_reported_instead_of_failing(self):
        result = self.collect([], None)

        self.assertEqual(result["videos"], [])
        self.assertIsNone(result["song_of_the_week"])
        self.assertEqual(len(result["warnings"]), 2)

    def test_result_is_written_under_the_edition_key(self):
        import main

        with tempfile.TemporaryDirectory() as directory:
            path = main.write_result({"edition_key": "auto-2026-08-28", "videos": []}, Path(directory))
            self.assertEqual(path.name, "auto-2026-08-28.json")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["videos"], [])


if __name__ == "__main__":
    unittest.main()
