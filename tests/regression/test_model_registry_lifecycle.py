from __future__ import annotations

"""Regression: ModelRegistry lifecycle — promote, retire, audit, guards.

Validates:
- promote() sets champion status on target
- promote() demotes previous champion to challenger
- exactly 1 champion per family after promote
- retire() sets retired status
- retire() of champion triggers auto re-promotion of best challenger
- retire() of last active model raises RegistryError
- promote() of nonexistent model raises RegistryError
- audit_log entries written for promotion and retirement

Ref: specs/05 (champion/challenger lifecycle), wave2 GROUP F
"""

import json

import pytest

from midas.ml import ModelRegistry, ModelVersion, RegistryError


class FakeDB:
    """In-memory fake DataFlow for registry tests."""

    def __init__(self):
        self._tables: dict[str, list[dict]] = {"model_registry": [], "audit_log": []}
        self._next_id = {"model_registry": 1, "audit_log": 1}

    @property
    def express(self):
        return self

    async def create(self, table: str, row: dict) -> dict:
        row["id"] = self._next_id.get(table, 1)
        self._next_id[table] = row["id"] + 1
        self._tables.setdefault(table, []).append(dict(row))
        return row

    async def list(self, table: str, **kwargs) -> list[dict]:
        rows = self._tables.get(table, [])
        filter_dict = kwargs.get("filter") or {}
        if filter_dict:
            return [r for r in rows if all(r.get(k) == v for k, v in filter_dict.items())]
        return list(rows)

    async def update(self, table: str, row_id: int, fields: dict) -> dict | None:
        rows = self._tables.get(table, [])
        for row in rows:
            if row.get("id") == row_id:
                row.update(fields)
                return row
        return None

    async def upsert(self, table: str, row: dict) -> dict:
        target_id = row.get("id")
        rows = self._tables.get(table, [])
        for existing in rows:
            if existing.get("id") == target_id:
                existing.update(row)
                return existing
        return await self.create(table, row)

    def all_rows(self, table: str) -> list[dict]:
        return list(self._tables.get(table, []))


def _make_version(family: str, version: str, status: str = "shadow") -> ModelVersion:
    return ModelVersion(
        model_family=family,
        model_version=version,
        model_type="test",
        training_window_start="2025-01-01",
        training_window_end="2025-12-31",
        promotion_status=status,
    )


@pytest.fixture
async def db():
    return FakeDB()


@pytest.fixture
async def registry(db):
    return ModelRegistry(db)


# --- promote ---


@pytest.mark.asyncio
@pytest.mark.regression
async def test_promote_sets_champion(registry, db):
    await registry.register(_make_version("clf", "v1", "shadow"))
    await registry.register(_make_version("clf", "v2", "shadow"))

    result = await registry.promote("clf", "v2")
    assert result is True

    champion = await registry.get_champion("clf")
    assert champion is not None
    assert champion["model_version"] == "v2"
    assert champion["promotion_status"] == "champion"


@pytest.mark.asyncio
@pytest.mark.regression
async def test_promote_demotes_previous_champion(registry, db):
    await registry.register(_make_version("clf", "v1", "champion"))
    await registry.register(_make_version("clf", "v2", "shadow"))

    await registry.promote("clf", "v2")

    rows = db.all_rows("model_registry")
    v1 = [r for r in rows if r["model_version"] == "v1"][0]
    assert v1["promotion_status"] == "challenger"


@pytest.mark.asyncio
@pytest.mark.regression
async def test_exactly_one_champion_per_family(registry, db):
    await registry.register(_make_version("clf", "v1", "champion"))
    await registry.register(_make_version("clf", "v2", "shadow"))
    await registry.register(_make_version("clf", "v3", "shadow"))

    await registry.promote("clf", "v3")

    rows = db.all_rows("model_registry")
    family = [r for r in rows if r["model_family"] == "clf"]
    champions = [r for r in family if r["promotion_status"] == "champion"]
    assert len(champions) == 1
    assert champions[0]["model_version"] == "v3"


@pytest.mark.asyncio
@pytest.mark.regression
async def test_promote_nonexistent_raises(registry):
    with pytest.raises(RegistryError, match="not found"):
        await registry.promote("clf", "nonexistent")


# --- retire ---


@pytest.mark.asyncio
@pytest.mark.regression
async def test_retire_sets_retired(registry, db):
    await registry.register(_make_version("clf", "v1", "champion"))
    await registry.register(_make_version("clf", "v2", "shadow"))

    result = await registry.retire("clf", "v2")
    assert result is True

    rows = db.all_rows("model_registry")
    v2 = [r for r in rows if r["model_version"] == "v2"][0]
    assert v2["promotion_status"] == "retired"


@pytest.mark.asyncio
@pytest.mark.regression
async def test_retire_champion_triggers_repromotion(registry, db):
    await registry.register(_make_version("clf", "v1", "shadow"))
    await registry.register(_make_version("clf", "v2", "champion"))

    await registry.retire("clf", "v2")

    champion = await registry.get_champion("clf")
    assert champion is not None
    assert champion["model_version"] == "v1"


@pytest.mark.asyncio
@pytest.mark.regression
async def test_retire_last_active_model_raises(registry, db):
    await registry.register(_make_version("clf", "v1", "champion"))

    with pytest.raises(RegistryError, match="last active model"):
        await registry.retire("clf", "v1")


@pytest.mark.asyncio
@pytest.mark.regression
async def test_retire_nonexistent_raises(registry):
    with pytest.raises(RegistryError, match="not found"):
        await registry.retire("clf", "nonexistent")


# --- audit ---


@pytest.mark.asyncio
@pytest.mark.regression
async def test_audit_log_on_promotion(registry, db):
    await registry.register(_make_version("clf", "v1", "shadow"))

    await registry.promote("clf", "v1")

    audit_rows = db.all_rows("audit_log")
    promote_entries = [r for r in audit_rows if r["action"] == "model_promoted"]
    assert len(promote_entries) >= 1
    details = json.loads(promote_entries[-1]["details"])
    assert details["model_version"] == "v1"
    assert "previous_champion" in details


@pytest.mark.asyncio
@pytest.mark.regression
async def test_audit_log_on_retirement(registry, db):
    await registry.register(_make_version("clf", "v1", "champion"))
    await registry.register(_make_version("clf", "v2", "shadow"))

    await registry.retire("clf", "v2")

    audit_rows = db.all_rows("audit_log")
    retire_entries = [r for r in audit_rows if r["action"] == "model_retired"]
    assert len(retire_entries) >= 1
    details = json.loads(retire_entries[-1]["details"])
    assert details["model_version"] == "v2"
    assert details["was_champion"] is False
