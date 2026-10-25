import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
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

    def test_falls_back_to_last_month_when_week_has_no_new_song(self):
        import song_of_the_week

        def top_tracks(username, period):
            return [self.track("Old")] if period == "7day" else [self.track("Monthly")]

        with patch.dict("os.environ", {"LASTFM_API_KEY": "key"}), \
            patch.object(song_of_the_week.lastfm, "get_top_tracks", side_effect=top_tracks), \
            patch.object(song_of_the_week.lastfm, "get_track_info", return_value={"album": "Record", "image": "https://example.com/c.jpg"}), \
            patch.object(song_of_the_week, "get_streaming_links", return_value={"spotify": "https://s"}):
            pick = song_of_the_week.get_song_of_the_week([{"artist": "Artist", "title": "Old"}], "user")

        self.assertEqual(pick, {
            "artist": "Artist",
            "title": "Monthly",
            "album": "Record",
            "image": "https://example.com/c.jpg",
            "links": {"spotify": "https://s"},
        })

    def test_lastfm_failure_does_not_block_the_newsletter(self):
        import song_of_the_week

        with patch.dict("os.environ", {"LASTFM_API_KEY": "key"}), \
            patch.object(song_of_the_week.lastfm, "get_top_tracks", side_effect=RuntimeError("offline")):
            self.assertIsNone(song_of_the_week.get_song_of_the_week([], "user"))

    def test_missing_cover_keeps_the_song(self):
        import song_of_the_week

        with patch.dict("os.environ", {"LASTFM_API_KEY": "key"}), \
            patch.object(song_of_the_week.lastfm, "get_top_tracks", return_value=[self.track("New")]), \
            patch.object(song_of_the_week.lastfm, "get_track_info", side_effect=RuntimeError("404")), \
            patch.object(song_of_the_week, "get_streaming_links", return_value={}):
            pick = song_of_the_week.get_song_of_the_week([], "user")

        self.assertEqual(pick["title"], "New")
        self.assertIsNone(pick["album"])
        self.assertIsNone(pick["image"])

    def test_track_info_ignores_lastfm_placeholder_cover(self):
        import lastfm

        placeholder = "https://lastfm.freetls.fastly.net/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f.png"
        response = {"track": {"album": {"title": "Record", "image": [{"#text": placeholder}]}}}

        with patch.object(lastfm, "call_api", return_value=response):
            self.assertEqual(
                lastfm.get_track_info("Artist", "Song"),
                {"album": "Record", "image": None},
            )

    def test_track_info_without_album(self):
        import lastfm

        with patch.object(lastfm, "call_api", return_value={"track": {"name": "Song"}}):
            self.assertEqual(
                lastfm.get_track_info("Artist", "Song"),
                {"album": None, "image": None},
            )

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
        ]

        for channel, title, expected in examples:
            with self.subTest(title=title):
                self.assertEqual(display_title(title, CHANNELS[channel]), expected)

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
        self.assertIsNone(pick_genre([("french", 100), ("jazz", 2)]))

    def add_genres(self, videos, overrides=None, cache=None, **patches):
        import genres

        if cache is not None:
            genres.save_json(cache, self.cache_path)

        channels = {"KEXP": {"artist_patterns": [r"^(?P<artist>.+?)\s+-\s+Full Performance"]}}

        with patch.dict("os.environ", {"LASTFM_API_KEY": "key"}), \
            patch.object(genres.lastfm, "get_artist_tags", **patches.get("lastfm", {"return_value": []})) as lastfm_tags, \
            patch.object(genres.collector, "fetch_video_topics", **patches.get("youtube", {"return_value": {}})):
            genres.add_genres(videos, channels, overrides, self.cache_path)

        return lastfm_tags

    def video(self, artist="Wednesday"):
        return {
            "channel": "KEXP",
            "title": f"{artist} - Full Performance (Live on KEXP)",
            "video_id": "abc",
        }

    def test_lastfm_genre_is_used_and_cached(self):
        import genres

        video = self.video()
        self.add_genres([video], lastfm={"return_value": [("shoegaze", 100)]})

        self.assertEqual(video["genre"], "shoegaze")
        self.assertEqual(genres.load_json(self.cache_path), {"wednesday": "shoegaze"})

    def test_cached_genre_skips_lastfm(self):
        video = self.video()
        lastfm_tags = self.add_genres([video], cache={"wednesday": "indie rock"})

        self.assertEqual(video["genre"], "indie rock")
        lastfm_tags.assert_not_called()

    def test_manual_override_wins_and_empty_override_hides_the_badge(self):
        corrected, hidden = self.video("Wednesday"), self.video("Rostam")
        self.add_genres(
            [corrected, hidden],
            overrides={"WEDNESDAY": "indie rock", "Rostam": ""},
            cache={"wednesday": "shoegaze"},
            youtube={"return_value": {"abc": ["https://en.wikipedia.org/wiki/Pop_music"]}},
        )

        self.assertEqual(corrected["genre"], "indie rock")
        self.assertIsNone(hidden["genre"])

    def test_youtube_topic_is_the_fallback(self):
        video = self.video()
        self.add_genres([video], youtube={"return_value": {"abc": [
            "https://en.wikipedia.org/wiki/Music",
            "https://en.wikipedia.org/wiki/Rock_music",
        ]}})

        self.assertEqual(video["genre"], "rock")

    def test_failures_leave_videos_without_badge(self):
        video = self.video()
        self.add_genres(
            [video],
            lastfm={"side_effect": RuntimeError("offline")},
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
        lastfm_tags = self.add_genres([video], youtube={"return_value": {"abc": [
            "https://en.wikipedia.org/wiki/Rock_music",
        ]}})

        self.assertIsNone(video["genre"])
        lastfm_tags.assert_not_called()


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
        })

    def test_direct_links_replace_search_links(self):
        import streaming_links

        with patch.object(streaming_links, "find_apple_music", return_value="https://apple"), \
            patch.object(streaming_links, "find_youtube_music", return_value="https://ytm"):
            links = streaming_links.get_streaming_links("Artist", "Song")

        self.assertEqual(links["apple_music"], "https://apple")
        self.assertEqual(links["youtube_music"], "https://ytm")
        self.assertTrue(links["spotify"].startswith("https://open.spotify.com/search/"))


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

    def test_invalid_keys_are_rejected(self):
        import main

        for values in ({"EDITION_KEY": "../etc"}, {"EDITION_KEY": ""}, {"REQUEST_ID": "a b"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                main.read_parameters(self.environ(**values))

    def collect(self, videos, pick):
        import main

        parameters = main.read_parameters(self.environ(
            EDITION_DATE="2026-08-28", ENGINE_STATE=json.dumps({"genre_overrides": {"Wednesday": "slowcore"}}),
        ))
        since_values = []

        def feed(name, config, since=None):
            since_values.append(since)
            return [video for video in videos if video["channel"] == name]

        with patch.object(main, "get_feed", side_effect=feed), \
            patch.object(main, "get_song_of_the_week", return_value=pick) as song, \
            patch("genres.lastfm.get_artist_tags", return_value=[]), \
            patch("genres.collector.fetch_video_topics", return_value={}), \
            patch.dict("os.environ", {"GITHUB_RUN_ID": "42", "GITHUB_REPOSITORY": "igorbdm/motif-engine"}, clear=True):
            result = main.collect(parameters)

        self.assertEqual(len(since_values), len(main.CHANNELS))
        self.assertTrue(all(value.isoformat() == "2026-08-21T00:00:00-03:00" for value in since_values))
        song.assert_called_once_with([])
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
             "channel": "KEXP", "link": "https://www.youtube.com/watch?v=a", "section": "live", "genre": "slowcore",
             "published": "2026-08-22T10:00:00Z"},
            {"id": "b", "title": "Daniel Lanois | What's in My Bag?", "display_title": "Daniel Lanois — What's In My Bag?",
             "channel": "Amoeba Music", "link": "https://www.youtube.com/watch?v=b", "section": "extras", "genre": None,
             "published": "2026-08-23T10:00:00Z"},
        ])

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
