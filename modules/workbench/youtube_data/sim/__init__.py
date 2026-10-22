"""Providers that behave like the real ones, from a scenario file, with no network and no cost. They exist so the whole
road of a film — discovered, blocked, waiting for captions, read, announced — can be walked locally with the failures
the real providers have, and never so that a run can pass a deployment that has none of them: every film, transcript and
reading they produce is marked as simulated, and a process that is not running locally refuses to start with one chosen."""
