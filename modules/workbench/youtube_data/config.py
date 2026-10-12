"""Settings, and the refusals that keep a misconfigured process from starting. Whether this package runs at all is
decided one level up, by whether its database is configured; everything here is read only once it does."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `prefer`/`allow` still let the client fall back to plaintext if the server does not
# offer TLS — a remote database MUST be reached encrypted, not merely offered it.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}

# What each provider setting may name. The one place a new provider is announced to the configuration.
KNOWN_VIDEO_SOURCES = ("data_api", "sim")
KNOWN_TRANSCRIPT_PROVIDERS = ("direct", "gemini", "sim", "sim_gemini")
SIMULATED_TRANSCRIPT_PROVIDERS = ("sim", "sim_gemini")
KNOWN_ANALYSERS = ("openai", "sim")


def _identifiers(raw: str) -> frozenset[str]:
    """A comma-separated setting as a set, with blanks and stray spaces dropped."""
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # `database_user` selects between the two connection modes and is the only switch: set means identity mode over
    # TLS with no credential in the URL, unset means the URL as given, on loopback.
    database_url: str
    database_user: str | None = None

    # Identity mode only, and unset even there when running in Azure.
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # How long this package waits for another process to finish migrating.
    migration_lock_wait_seconds: float = 300.0

    # Two, not three: seven databases share one `B_Standard_B1ms` whose `max_connections` is 50, and
    # `scripts/tests/test_pool_budget.py` holds the total to 30 — which the packages before this one already fill to 29.
    # Enabling this package in production is the change that finds the third connection.
    database_pool_size: int = 2

    # Where films are found, where their words come from and who reads them. Each is a name, so replacing a provider is
    # a line in `.env`; what a name may be is `KNOWN_*` above. `data_api` is the one real source, on a free key; `sim` is
    # a scenario file and is refused in production. Everything defaults to the simulation: a checkout with nothing
    # configured works, and cannot be mistaken for a deployment that does.
    video_source: str = "sim"
    data_api_key: str | None = None
    # A list, first choice first. The next is asked when the one before did not let us in, and after "no captions" only
    # one that listens (`gemini`, `sim_gemini`) — the order production runs: free captions, then the model.
    transcript_providers: str = "sim,sim_gemini"
    # The languages captions are asked for when the source does not say what the film speaks, in order of preference.
    transcript_languages: str = "pl,en"
    # Gemini, handed the film's address: it listens, so a film with no captions is ordinary work for it. Billed in
    # tokens, limited by Google in hours of film a day (eight on the free tier), so the ceiling is seconds of film.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    # A film longer than this is written down in pieces: a whole hour in one answer risks a cut-off one.
    gemini_chunk_minutes: int = 30
    gemini_daily_video_seconds: int = 28_800
    # One piece of film is minutes of listening, not the seconds a listing takes.
    gemini_timeout_seconds: float = 600.0
    # A provider that refused us is not asked again for this long: from the cloud, captions are refused every time, and
    # asking costs a request and up to a minute before the chain reaches the provider that listens.
    provider_cooldown_minutes: int = 360

    # The model. Absent key is a supported state, not a refusal — the package discovers and transcribes, and every
    # reading stays empty, which `/state` says.
    analyser: str = "sim"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    analysis_model: str = "gpt-6-sol"
    # How much of a transcript one reading is given. An hour of speech is ~55k characters; this is well past the
    # longest film the loop accepts, so a cut is the exception and is announced to the model when it happens.
    analysis_max_chars: int = 300_000

    # The simulation: which scenario file (unset is the one that ships), and how many times faster than the wall clock it
    # runs — 24 is a day in an hour.
    sim_scenario: str | None = None
    sim_speed: float = 1.0

    # How often the loop passes, and how much of each step one pass may do. The rest waits for the next pass: a busy
    # hour must cost a bounded amount, and a step that stalls must not stall the ones after it.
    poll_interval_seconds: int = 1800
    discover_batch_limit: int = 50
    transcribe_batch_limit: int = 10
    analyse_batch_limit: int = 5
    announce_batch_limit: int = 10

    # When a film without captions is asked about again, in minutes: an hour, six, a day — automatic captions turn up
    # hours after upload — and then never. Every ask costs, so the last one is last; four misses is the ceiling.
    retry_delays_minutes: str = "60,360,1440"
    # A reading that fails this many times is no longer picked up by itself.
    reading_max_failures: int = 3

    # A film outside these is not worth a transcript: a short is a slogan, and a five-hour stream is a day of tokens.
    # Applied only where the source says how long the film is — a feed does not.
    min_video_seconds: int = 60
    max_video_seconds: int = 10_800

    # How long the watch list may grow, and what a topic gets when it is added without saying.
    max_channels: int = 100
    max_topics: int = 20
    topic_default_interval_minutes: int = 360
    topic_default_max_videos: int = 3

    # Each provider's day, in the provider's own unit, counted here rather than trusted to the provider's dashboard.
    # The source's is the YouTube Data API's 10,000 with room to spare; a topic search costs a hundred of them. Every
    # captions provider gets `daily_transcript_units`; Gemini has its own, above, in seconds of film.
    daily_source_units: int = 8000
    daily_transcript_units: int = 500
    daily_token_limit: int = 2_000_000

    # Who is told, by the name the operator bound at the door to Telegram — a package of this same process, so there is no
    # address to set. Its *absence* is a working configuration: the package reads exactly as before and tells nobody, which
    # `/state` reports.
    alert_destination: str | None = None
    # How impactful a film must be to be worth a notification under a `threshold` rule. Eight, for the reason the post
    # archive gives: the operator reads these on a phone, and a channel that speaks daily is one nobody looks at.
    alert_min_impact_score: int = 8
    # A film not announced within this long of being read is let go as quiet rather than announced in a heap later.
    alert_window_hours: int = 48

    # How this package names itself upstream, and how long it waits for a third party.
    provider_user_agent: str = "tradingcenter-youtube-data/0.1 (+https://github.com/MarekGrzeska)"
    provider_timeout_seconds: float = 20.0

    # Easy Auth authorizes an application, not a route, and both surfaces stand in one process — so which caller
    # reaches which of them is this package's own record.
    require_authenticated_principal: bool = False
    tool_caller_application_ids: str = ""
    rest_caller_application_ids: str = ""

    @property
    def tool_caller_ids(self) -> frozenset[str]:
        return _identifiers(self.tool_caller_application_ids)

    @property
    def rest_caller_ids(self) -> frozenset[str]:
        return _identifiers(self.rest_caller_application_ids)

    @property
    def transcript_provider_names(self) -> tuple[str, ...]:
        return tuple(part.strip() for part in self.transcript_providers.split(",") if part.strip())

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(part.strip() for part in self.transcript_languages.split(",") if part.strip())

    @property
    def alerts_configured(self) -> bool:
        return self.alert_destination is not None

    @property
    def retry_delays(self) -> tuple[int, ...]:
        return tuple(int(part) for part in self.retry_delays_minutes.split(",") if part.strip())

    @property
    def simulating(self) -> bool:
        return (
            self.video_source == "sim"
            or any(name in SIMULATED_TRANSCRIPT_PROVIDERS for name in self.transcript_provider_names)
            or self.analyser == "sim"
        )

    @property
    def model_configured(self) -> bool:
        """Whether a reading can be made at all: the simulated model always can, the real one needs its key."""
        return self.analyser == "sim" or bool(self.openai_api_key)

    @field_validator("database_url", "provider_user_agent", "analysis_model", "gemini_model")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that is present but empty.
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.strip()

    @field_validator("alert_min_impact_score")
    @classmethod
    def _within_the_score_range(cls, value: int) -> int:
        # The reading is 1..10, so a threshold outside it is a channel that is either silent for ever or one that says
        # everything — both of which look like a working configuration.
        if not 1 <= value <= 10:
            raise ValueError(f"ALERT_MIN_IMPACT_SCORE must be between 1 and 10; got {value}")
        return value

    @field_validator("data_api_key", "gemini_api_key", "openai_api_key", "openai_base_url", "alert_destination")
    @classmethod
    def _blank_secret_is_absent(cls, value: str | None) -> str | None:
        # A key line somebody stopped filling means the same as a line that is not there.
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("retry_delays_minutes")
    @classmethod
    def _delays_are_minutes(cls, value: str) -> str:
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if not all(part.isdigit() and int(part) > 0 for part in parts):
            raise ValueError(f"RETRY_DELAYS_MINUTES is a comma-separated list of positive whole minutes; got {value!r}")
        return value

    @field_validator("video_source")
    @classmethod
    def _known_source(cls, value: str) -> str:
        if value == "rss":
            raise ValueError(
                "VIDEO_SOURCE=rss is gone: a feed cannot say how long a film is, which the transcript providers price it "
                "by — set data_api (a free YouTube Data API key) or sim"
            )
        if value not in KNOWN_VIDEO_SOURCES:
            raise ValueError(f"VIDEO_SOURCE must be one of {', '.join(KNOWN_VIDEO_SOURCES)}; got {value!r}")
        return value

    @field_validator("analyser")
    @classmethod
    def _known_analyser(cls, value: str) -> str:
        if value not in KNOWN_ANALYSERS:
            raise ValueError(f"ANALYSER must be one of {', '.join(KNOWN_ANALYSERS)}; got {value!r}")
        return value

    @field_validator("transcript_providers")
    @classmethod
    def _known_transcript_providers(cls, value: str) -> str:
        names = [part.strip() for part in value.split(",") if part.strip()]
        if not names:
            raise ValueError("TRANSCRIPT_PROVIDERS names no provider")
        unknown = [name for name in names if name not in KNOWN_TRANSCRIPT_PROVIDERS]
        if unknown:
            raise ValueError(
                f"TRANSCRIPT_PROVIDERS names {', '.join(unknown)}; the ones this package has are "
                f"{', '.join(KNOWN_TRANSCRIPT_PROVIDERS)}"
            )
        return value

    @field_validator(
        "analysis_max_chars",
        "poll_interval_seconds",
        "discover_batch_limit",
        "transcribe_batch_limit",
        "analyse_batch_limit",
        "announce_batch_limit",
        "alert_window_hours",
        "reading_max_failures",
        "min_video_seconds",
        "max_video_seconds",
        "max_channels",
        "max_topics",
        "topic_default_interval_minutes",
        "topic_default_max_videos",
        "daily_source_units",
        "daily_transcript_units",
        "daily_token_limit",
        "gemini_chunk_minutes",
        "gemini_daily_video_seconds",
        "provider_cooldown_minutes",
    )
    @classmethod
    def _positive(cls, value: int, info: ValidationInfo) -> int:
        if value < 1:
            raise ValueError(f"{str(info.field_name).upper()} must be at least 1; got {value}")
        return value

    @field_validator("provider_timeout_seconds", "gemini_timeout_seconds", "sim_speed")
    @classmethod
    def _positive_seconds(cls, value: float, info: ValidationInfo) -> float:
        if value <= 0:
            raise ValueError(f"{str(info.field_name).upper()} must be positive; got {value}")
        return value

    @field_validator("database_user")
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        # `DATABASE_USER=` left in a .env is the same intent as the line being absent — local mode.
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("database_pool_size")
    @classmethod
    def _pool_is_usable(cls, value: int) -> int:
        if value < 1:
            raise ValueError(f"DATABASE_POOL_SIZE must be at least 1; got {value}")
        return value

    @model_validator(mode="after")
    def _a_simulation_is_not_a_deployment(self) -> Settings:
        # Identity mode is the database of a deployment, and the one switch the connection mode already hangs on. A
        # simulated provider there would fill a real archive with films that never existed, so it is refused by name.
        if self.database_user is None:
            return self
        chosen = [
            name
            for name, is_sim in (
                ("VIDEO_SOURCE", self.video_source == "sim"),
                (
                    "TRANSCRIPT_PROVIDERS",
                    any(name in SIMULATED_TRANSCRIPT_PROVIDERS for name in self.transcript_provider_names),
                ),
                ("ANALYSER", self.analyser == "sim"),
            )
            if is_sim
        ]
        if chosen:
            raise ValueError(
                f"{', '.join(chosen)} select the simulation, which is refused where DATABASE_USER is set — that is a "
                "deployment, and its archive must not fill with films that never existed"
            )
        return self

    @model_validator(mode="after")
    def _a_source_that_needs_a_key_has_one(self) -> Settings:
        # A wish and not a state: the source was *asked for*, so running without its key would be a silent downgrade to
        # a source that cannot do what was asked. Absent key for the *model* is the opposite — a supported state.
        if self.video_source == "data_api" and self.data_api_key is None:
            raise ValueError("VIDEO_SOURCE=data_api needs DATA_API_KEY — a free YouTube Data API key")
        if "gemini" in self.transcript_provider_names:
            if self.gemini_api_key is None:
                raise ValueError("TRANSCRIPT_PROVIDERS names gemini, which needs GEMINI_API_KEY")
            # Simulated films do not exist on YouTube, so a real model would be paid to listen to nothing.
            if self.video_source != "data_api":
                raise ValueError("TRANSCRIPT_PROVIDERS names gemini, which listens to real films — set VIDEO_SOURCE=data_api")
        return self

    @model_validator(mode="after")
    def _connection_mode_is_coherent(self) -> Settings:
        """The two connection modes, each with its own failure to refuse. Identity mode is off this machine, so TLS and
        no credential; local mode is the URL as given, and must be loopback."""
        parsed = urlparse(self.database_url)
        if self.database_user is not None:
            sslmode = parse_qs(parsed.query).get("sslmode", [None])[0]
            if sslmode not in _TLS_REQUIRING_SSLMODES:
                raise ValueError(
                    f"DATABASE_URL does not require TLS (sslmode={sslmode!r}). With "
                    "DATABASE_USER set this package connects to a database off this "
                    "machine, so the connection MUST be encrypted — set sslmode=require "
                    "(or verify-ca/verify-full)."
                )
            if parsed.username or parsed.password:
                raise ValueError(
                    "DATABASE_URL carries a username or password. With DATABASE_USER set "
                    "this package authenticates with an Entra token fetched at connection "
                    "time — a credential embedded in the URL is not read and should not "
                    "be there."
                )
            return self

        host = (parsed.hostname or "").lower()
        if not (host == "localhost" or host.startswith("127.") or host == "::1"):
            raise ValueError(
                f"DATABASE_URL points at {host!r} with no DATABASE_USER set. Without an "
                "identity this package only connects to a database on this machine's "
                "loopback — a remote database (production included) needs DATABASE_USER "
                "and an Entra identity, and local work belongs on the compose.yaml "
                "container."
            )
        return self
