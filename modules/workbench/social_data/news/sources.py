"""Every feed this archive reads, as data. Adding one is a line here, reviewed like any change — which is the
determinism the collector is for: nothing decides at runtime what gets fetched.

Measured on 29 September 2026 (`docs/zrodla-newsow.html`): each answered 200 to this module's own User-Agent."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_INTERVAL_SECONDS = 120

# Not an official API and no validators on the answer, so every fetch is a full one: asked less often.
GOOGLE_NEWS_INTERVAL_SECONDS = 180


def _google_news(query: str) -> str:
    return f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


@dataclass(frozen=True, slots=True)
class NewsSource:
    """`id` is what a headline and a state row are filed under, so it never changes once deployed.
    `publisher` is only what a screen shows; an aggregator's items carry their own."""

    id: str
    publisher: str
    url: str
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS


SOURCES: tuple[NewsSource, ...] = (
    # The RSS only: its terms forbid automated collection, and reading the published feed is the use the
    # operator accepted on 29 September 2026. The live blog's entries are not in it and are not fetched.
    NewsSource("aljazeera", "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    NewsSource(
        "google-news-iran",
        "Google News",
        _google_news("Iran+when:1h"),
        GOOGLE_NEWS_INTERVAL_SECONDS,
    ),
    NewsSource(
        "google-news-hormuz",
        "Google News",
        _google_news("(Hormuz+OR+IRGC+OR+%22Iran+talks%22)+when:1h"),
        GOOGLE_NEWS_INTERVAL_SECONDS,
    ),
    NewsSource("tehrantimes", "Tehran Times", "https://www.tehrantimes.com/rss"),
    NewsSource("irna", "IRNA", "https://en.irna.ir/rss"),
    # Its own feed answers 403 from Azure's addresses (Cloudflare) and works from a home one, so it is not a User-Agent
    # problem and not one to route around. What Google News carries of it comes with the aggregator's delay.
    NewsSource(
        "google-news-timesofisrael",
        "Google News",
        _google_news("site:timesofisrael.com+(Iran+OR+Israel+OR+Hormuz+OR+Hezbollah)+when:1d"),
        GOOGLE_NEWS_INTERVAL_SECONDS,
    ),
    NewsSource("middleeasteye", "Middle East Eye", "https://www.middleeasteye.net/rss"),
    NewsSource("guardian-iran", "The Guardian", "https://www.theguardian.com/world/iran/rss"),
    NewsSource(
        "guardian-middleeast", "The Guardian", "https://www.theguardian.com/world/middleeast/rss"
    ),
    NewsSource("iranintl", "Iran International", "https://www.iranintl.com/en/feed"),
    NewsSource(
        "nyt-world", "The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"
    ),
    NewsSource(
        "nyt-middleeast",
        "The New York Times",
        "https://rss.nytimes.com/services/xml/rss/nyt/MiddleEast.xml",
    ),
    NewsSource("axios", "Axios", "https://api.axios.com/feed/"),
    NewsSource("bbc-middleeast", "BBC", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
    NewsSource("bbc-world", "BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
)

BY_ID: dict[str, NewsSource] = {source.id: source for source in SOURCES}
