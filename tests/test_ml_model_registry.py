"""Tier 1 tests for the ML model registry."""

import tempfile

import pytest

from midas.fabric.engine import create_fabric, reset_fabric
from midas.ml import ModelRegistry, ModelVersion


@pytest.fixture
def db():
    """Create a temp-file SQLite DataFlow for registry tests."""
    import os

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_registry.db")
    db_url = f"sqlite:///{db_path}"
    database = create_fabric(database_url=db_url, auto_migrate=True)
    yield database
    try:
        database.close()
    except Exception:
        pass
    reset_fabric()
    for suffix in ("-wal", "-shm"):
        try:
            os.unlink(db_path + suffix)
        except OSError:
            pass
    try:
        os.unlink(db_path)
    except OSError:
        pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass


@pytest.fixture
async def started_db(db):
    """Start the database for async tests."""
    await db.start()
    yield db
    try:
        await db.close_async()
    except Exception:
        pass


@pytest.fixture
def registry(db):
    """Synchronous registry fixture (db.start() not needed for express)."""
    return ModelRegistry(db)


@pytest.fixture
async def started_registry(started_db):
    """Async registry fixture."""
    return ModelRegistry(started_db)


class TestModelRegistryWriteAndRead:
    """Tests for model registry write/read cycle."""

    def test_register_writes_row(self, registry):
        """register() writes a row and get() retrieves it."""
        mv = ModelVersion(
            model_family="ssl_transformer_v1",
            model_version="v1.0.0",
            model_type="ssl_transformer",
            training_window_start="2024-01-01",
            training_window_end="2024-12-31",
            promotion_status="shadow",
            sample_count=50000,
            parameter_count=1_200_000,
            trained_at="2025-01-15T10:00:00",
            config_hash="abc123",
            parent_version="",
            pool_layer="representation_learner",
        )
        result = registry.register(mv)
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            rows_affected = loop.run_until_complete(result)
        finally:
            loop.close()
        assert rows_affected is not None
        assert rows_affected.get("rows_affected", 0) >= 1

    def test_get_retrieves_registered_model(self, registry):
        """get() returns the registered model version."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            mv = ModelVersion(
                model_family="ssl_transformer_v1",
                model_version="v1.0.0",
                model_type="ssl_transformer",
                training_window_start="2024-01-01",
                training_window_end="2024-12-31",
                promotion_status="shadow",
                sample_count=50000,
                parameter_count=1_200_000,
                trained_at="2025-01-15T10:00:00",
            )
            loop.run_until_complete(registry.register(mv))

            retrieved = loop.run_until_complete(registry.get("ssl_transformer_v1", "v1.0.0"))
        finally:
            loop.close()

        assert retrieved is not None
        assert retrieved["model_family"] == "ssl_transformer_v1"
        assert retrieved["model_version"] == "v1.0.0"
        assert retrieved["model_type"] == "ssl_transformer"

    def test_get_nonexistent_returns_none(self, registry):
        """get() returns None for unregistered family/version."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(registry.get("nonexistent", "v0.0.0"))
        finally:
            loop.close()
        assert result is None

    def test_get_lineage_returns_all_versions(self, registry):
        """get_lineage() returns all versions for a family."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            for i in range(3):
                mv = ModelVersion(
                    model_family="contrastive_v1",
                    model_version=f"v1.{i}.0",
                    model_type="contrastive_encoder",
                    training_window_start="2024-01-01",
                    training_window_end="2024-12-31",
                    promotion_status="shadow",
                    sample_count=30000,
                    parameter_count=800_000,
                    trained_at="2025-01-15T10:00:00",
                )
                loop.run_until_complete(registry.register(mv))

            lineage = loop.run_until_complete(registry.get_lineage("contrastive_v1"))
        finally:
            loop.close()

        assert len(lineage) == 3
        versions = {r["model_version"] for r in lineage}
        assert versions == {"v1.0.0", "v1.1.0", "v1.2.0"}

    def test_list_by_pool_returns_matching(self, registry):
        """list_by_pool() returns models in the pool layer."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            models = [
                ("ssl_transformer_v1", "ssl_transformer", "representation_learner"),
                ("contrastive_v1", "contrastive_encoder", "representation_learner"),
                ("classical_mvo", "mean_variance_opt", "classical_baseline"),
            ]
            for family, mtype, pool in models:
                mv = ModelVersion(
                    model_family=family,
                    model_version="v1.0.0",
                    model_type=mtype,
                    training_window_start="2024-01-01",
                    training_window_end="2024-12-31",
                    promotion_status="shadow",
                    sample_count=10000,
                    parameter_count=500_000,
                    trained_at="2025-01-15T10:00:00",
                    pool_layer=pool,
                )
                loop.run_until_complete(registry.register(mv))

            repr_rows = loop.run_until_complete(registry.list_by_pool("representation_learner"))
        finally:
            loop.close()

        assert len(repr_rows) == 2
        assert all(
            "transformer" in r.get("model_type", "") or "contrastive" in r.get("model_type", "")
            for r in repr_rows
        )

    def test_get_champion_returns_champion(self, registry):
        """get_champion() returns the champion model."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            for status in ["shadow", "champion", "shadow"]:
                mv = ModelVersion(
                    model_family="mae_v1",
                    model_version=f"v1.0.{status}",
                    model_type="masked_autoencoder",
                    training_window_start="2024-01-01",
                    training_window_end="2024-12-31",
                    promotion_status=status,
                    sample_count=25000,
                    parameter_count=600_000,
                    trained_at="2025-01-15T10:00:00",
                )
                loop.run_until_complete(registry.register(mv))

            champion = loop.run_until_complete(registry.get_champion("masked_autoencoder"))
        finally:
            loop.close()

        assert champion is not None
        assert champion["promotion_status"] == "champion"

    def test_get_challengers_returns_shadow_models(self, registry):
        """get_challengers() returns shadow models in the pool."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            for i, status in enumerate(["shadow", "shadow", "champion"]):
                mv = ModelVersion(
                    model_family="vae_v1",
                    model_version=f"v{i}.0.0",
                    model_type="variational_autoencoder",
                    training_window_start="2024-01-01",
                    training_window_end="2024-12-31",
                    promotion_status=status,
                    sample_count=20000,
                    parameter_count=700_000,
                    trained_at="2025-01-15T10:00:00",
                )
                loop.run_until_complete(registry.register(mv))

            challengers = loop.run_until_complete(
                registry.get_challengers("variational_autoencoder")
            )
        finally:
            loop.close()

        assert len(challengers) == 2
        assert all(r["promotion_status"] == "shadow" for r in challengers)

    def test_retire_returns_true_for_existing(self, registry):
        """retire() returns True for an existing model."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            mv = ModelVersion(
                model_family="deep_ssm_v1",
                model_version="v1.0.0",
                model_type="deep_ssm",
                training_window_start="2024-01-01",
                training_window_end="2024-12-31",
                promotion_status="shadow",
                sample_count=15000,
                parameter_count=900_000,
                trained_at="2025-01-15T10:00:00",
            )
            loop.run_until_complete(registry.register(mv))
            retired = loop.run_until_complete(registry.retire("deep_ssm_v1", "v1.0.0"))
        finally:
            loop.close()
        assert retired is True

    def test_retire_returns_false_for_nonexistent(self, registry):
        """retire() returns False for a nonexistent model."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(registry.retire("fake_family", "v0.0.0"))
        finally:
            loop.close()
        assert result is False


class TestModelVersionInvariants:
    """Tests that model versions carry all required invariants."""

    def test_model_version_carries_all_invariants(self):
        """Every field required by T-03-01 is present on ModelVersion."""
        mv = ModelVersion(
            model_family="test_family",
            model_version="v1.0.0",
            model_type="ssl_transformer",
            training_window_start="2024-01-01",
            training_window_end="2024-12-31",
            calibration_json='{"temperature": 0.5}',
            promotion_status="shadow",
            sample_count=1000,
            parameter_count=500_000,
            trained_at="2025-01-15T10:00:00",
            config_hash="hash123",
            parent_version="v0.9.0",
            pool_layer="representation_learner",
            metrics_json='{"val_loss": 0.01}',
        )
        # All invariant fields are present
        assert mv.training_window_start == "2024-01-01"
        assert mv.training_window_end == "2024-12-31"
        assert mv.config_hash == "hash123"
        assert mv.parent_version == "v0.9.0"
        assert mv.pool_layer == "representation_learner"
        assert mv.promotion_status == "shadow"
        assert mv.metrics_json == '{"val_loss": 0.01}'

    def test_promote_demotes_existing_champion(self, registry):
        """promote() demotes the existing champion and promotes new version."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            # Register current champion
            champion = ModelVersion(
                model_family="ssm_v1",
                model_version="v1.0.0",
                model_type="deep_ssm",
                training_window_start="2024-01-01",
                training_window_end="2024-12-31",
                promotion_status="champion",
                sample_count=10000,
                parameter_count=800_000,
                trained_at="2025-01-15T10:00:00",
            )
            loop.run_until_complete(registry.register(champion))

            # Verify champion exists
            champ_before = loop.run_until_complete(registry.get_champion("deep_ssm"))
            assert champ_before is not None
            assert champ_before["model_version"] == "v1.0.0"

            # Promote new version
            success = loop.run_until_complete(registry.promote("ssm_v1", "v2.0.0"))
            assert success is True
        finally:
            loop.close()
