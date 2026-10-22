"""Prompts as data, and one shape of reading. `prompts` and their `prompt_versions` replace the `profile` name the code
used to carry; a channel, a topic and a film point at a prompt, and a reading says which prompt and which version made it.
The reading itself becomes a summary, one text laid out by the prompt and a score: what used to be separate lists of
points, instruments and predictions is written into the text of the readings already stored, so nothing said is lost.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEEDED_NAME = "Rynkowy"
SEEDED_BODY = (
    "Streszcz film dla tradera, po polsku. Ułóż tekst w sekcjach z nagłówkami ##: „Główne tezy” (3–8 krótkich punktów "
    "tego, co autor rzeczywiście powiedział), „Instrumenty” (każdy instrument, o którym autor ma zdanie: nazwa, kierunek "
    "— wzrost, spadek albo neutralnie — i jak pewny siebie jest autor), „Prognozy” (konkretne, sprawdzalne twierdzenia "
    "z poziomem i terminem, jeśli padły; pomiń niejasne opinie) oraz „Ryzyka i zastrzeżenia”. Pomiń sekcję, o której "
    "film nic nie mówi."
)

_DIRECTION = {"bullish": "wzrost", "bearish": "spadek", "neutral": "neutralnie"}


def legacy_text(old: dict) -> str:
    """The lists of a reading in the old shape, written as the Markdown a prompt would have laid out."""
    parts: list[str] = []
    if old.get("key_points"):
        parts.append("## Główne tezy\n" + "\n".join(f"- {point}" for point in old["key_points"]))
    if old.get("instruments"):
        lines = []
        for view in old["instruments"]:
            epic = f" ({view['epic']})" if view.get("epic") else ""
            lines.append(
                f"- **{view['name']}**{epic} — {_DIRECTION.get(view['sentiment'], view['sentiment'])}, "
                f"przekonanie {view['conviction']}/5, horyzont {view['horizon']}"
            )
        parts.append("## Instrumenty\n" + "\n".join(lines))
    if old.get("predictions"):
        lines = []
        for prediction in old["predictions"]:
            detail = [f"poziom {prediction['level']}"] if prediction.get("level") is not None else []
            if prediction.get("by"):
                detail.append(f"do {prediction['by']}")
            lines.append(f"- {prediction['instrument']}: {prediction['claim']}" + (f" ({', '.join(detail)})" if detail else ""))
        parts.append("## Prognozy\n" + "\n".join(lines))
    if old.get("topics"):
        parts.append("**Tematy:** " + ", ".join(old["topics"]))
    return "\n\n".join(parts) or "Odczyt sprzed zmiany nie zawierał szczegółów poza streszczeniem."


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE prompts (
            id          bigserial PRIMARY KEY,
            name        text NOT NULL,
            seeded      boolean NOT NULL DEFAULT false,
            created_at  timestamptz NOT NULL DEFAULT now(),
            deleted_at  timestamptz,
            CONSTRAINT prompts_name_is_not_blank CHECK (btrim(name) <> '')
        )
        """
    )
    # A name is unique among the prompts still on offer; a deleted one keeps its row, and its name is free again.
    op.execute("CREATE UNIQUE INDEX prompts_name_idx ON prompts (lower(name)) WHERE deleted_at IS NULL")
    op.execute("CREATE UNIQUE INDEX prompts_one_seeded_idx ON prompts (seeded) WHERE seeded")
    op.execute(
        """
        CREATE TABLE prompt_versions (
            prompt_id   bigint NOT NULL REFERENCES prompts(id),
            version     integer NOT NULL,
            body        text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (prompt_id, version),
            CONSTRAINT prompt_versions_body_is_not_blank CHECK (btrim(body) <> '')
        )
        """
    )

    bind = op.get_bind()
    seeded = bind.execute(
        sa.text("INSERT INTO prompts (name, seeded) VALUES (:name, true) RETURNING id"), {"name": SEEDED_NAME}
    ).scalar_one()
    bind.execute(
        sa.text("INSERT INTO prompt_versions (prompt_id, version, body) VALUES (:id, 1, :body)"),
        {"id": seeded, "body": SEEDED_BODY},
    )

    # Everything that carried the one profile there was now carries the seeded prompt.
    for table in ("channels", "topics", "videos"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN prompt_id bigint REFERENCES prompts(id)")
        bind.execute(sa.text(f"UPDATE {table} SET prompt_id = :id"), {"id": seeded})
        op.execute(f"ALTER TABLE {table} ALTER COLUMN prompt_id SET NOT NULL, DROP COLUMN profile")

    op.execute(
        "ALTER TABLE readings ADD COLUMN prompt_id bigint REFERENCES prompts(id), ADD COLUMN prompt_version integer"
    )
    bind.execute(sa.text("UPDATE readings SET prompt_id = :id, prompt_version = 1"), {"id": seeded})
    for row in bind.execute(sa.text("SELECT video_id, result FROM readings")).mappings().all():
        old = row["result"] if isinstance(row["result"], dict) else json.loads(row["result"])
        new = {"summary_pl": old["summary_pl"], "text": legacy_text(old), "impact_score": old["impact_score"]}
        bind.execute(
            sa.text("UPDATE readings SET result = CAST(:result AS jsonb) WHERE video_id = :video_id"),
            {"result": json.dumps(new), "video_id": row["video_id"]},
        )
    op.execute(
        "ALTER TABLE readings ALTER COLUMN prompt_id SET NOT NULL, ALTER COLUMN prompt_version SET NOT NULL, "
        "DROP CONSTRAINT readings_pkey, DROP COLUMN profile, DROP COLUMN instruments"
    )
    op.execute("ALTER TABLE readings ADD PRIMARY KEY (video_id, prompt_id)")


def downgrade() -> None:
    """The schema, not the words: a reading keeps its new-shape document, and only the film's own prompt's reading stays."""
    op.execute(
        "DELETE FROM readings r USING videos v WHERE v.video_id = r.video_id AND r.prompt_id <> v.prompt_id"
    )
    op.execute(
        "ALTER TABLE readings DROP CONSTRAINT readings_pkey, ADD COLUMN profile text NOT NULL DEFAULT 'market', "
        "ADD COLUMN instruments text[] NOT NULL DEFAULT '{}', DROP COLUMN prompt_id, DROP COLUMN prompt_version"
    )
    op.execute("ALTER TABLE readings ADD PRIMARY KEY (video_id, profile)")
    op.execute("CREATE INDEX readings_instruments_idx ON readings USING gin (instruments)")
    for table in ("channels", "topics", "videos"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN profile text NOT NULL DEFAULT 'market', DROP COLUMN prompt_id")
    op.execute("DROP TABLE prompt_versions")
    op.execute("DROP TABLE prompts")
