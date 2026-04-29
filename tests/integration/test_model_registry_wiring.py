"""Tier 2 integration tests for ModelRegistry facade wiring.

Tests that db.model_registry actually executes the registry methods
against a real DataFlow instance, verifying end-to-end behavior.

Ref: specs/05-model-pool-and-meta-router.md §3 (Inner Loop)
Ref: rules/facade-manager-detection.md
"""

import asyncio
import tempfile
import os

import pytest

from midas.fabric.engine import create_fabric, reset_fabric, MidasFabric
from midas.ml import ModelRegistry, ModelVersion, RegistryError


@pytest.fixture
def db():
    """Create a temp-file SQLite MidasFabric for integration tests."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_registry_wiring.db")
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
    """Start the database for async integration tests."""
    await db.start()
    yield db
    try:
        await db.close_async()
    except Exception:
        pass


class TestModelRegistryFacadeWiring:
    """Verify ModelRegistry is accessible via db.model_registry facade."""

    def test_db_has_model_registry_property(self, db):
        """db.model_registry returns a ModelRegistry instance."""
        registry = db.model_registry
        assert isinstance(registry, ModelRegistry)
        assert registry._db is db

    def test_db_model_registry_singleton(self, db):
        """Accessing db.model_registry twice returns the same instance."""
        r1 = db.model_registry
        r2 = db.model_registry
        assert r1 is r2

    @pytest.mark.asyncio
    async def test_facade_register_writes_row(self, started_db):
        """db.model_registry.register() writes a row and get() retrieves it."""
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
        result = await started_db.model_registry.register(mv)
        assert result is not None
        assert result.get("rows_affected", 0) >= 1

    @pytest.mark.asyncio
    async def test_facade_get_retrieves_registered_model(self, started_db):
        """db.model_registry.get() returns the registered model version."""
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
        await started_db.model_registry.register(mv)

        retrieved = await started_db.model_registry.get("ssl_transformer_v1", "v1.0.0")
        assert retrieved is not None
        assert retrieved["model_family"] == "ssl_transformer_v1"
        assert retrieved["model_version"] == "v1.0.0"

    @pytest.mark.asyncio
    async def test_facade_get_champion_returns_exact_match(self, started_db):
        """get_champion(model_family) returns the champion for that exact family.

        Bug fixed: get_champion previously used substring containment
        (pool_layer in model_type) which would match 'ssl_transformer_v1'
        when querying for pool_layer 'ssl'. Now uses exact match on
        model_family + promotion_status='champion'.
        """
        # Register a champion for ssl_transformer_v1
        champion = ModelVersion(
            model_family="ssl_transformer_v1",
            model_version="v2.0.0",
            model_type="ssl_transformer",
            training_window_start="2024-01-01",
            training_window_end="2024-12-31",
            promotion_status="champion",
            sample_count=60000,
            parameter_count=1_500_000,
            trained_at="2025-01-20T10:00:00",
        )
        await started_db.model_registry.register(champion)

        # Register a shadow for a different family that could collide via substring match
        shadow = ModelVersion(
            model_family="ssl_transformer_v2",
            model_version="v0.1.0",
            model_type="ssl_transformer_v2",
            training_window_start="2024-01-01",
            training_window_end="2024-12-31",
            promotion_status="shadow",
            sample_count=10000,
            parameter_count=200_000,
            trained_at="2025-02-01T10:00:00",
        )
        await started_db.model_registry.register(shadow)

        # get_champion should return the exact family match, not any family
        # containing "ssl_transformer" as a substring
        result = await started_db.model_registry.get_champion("ssl_transformer_v1")
        assert result is not None
        assert result["model_family"] == "ssl_transformer_v1"
        assert result["promotion_status"] == "champion"
        assert result["model_version"] == "v2.0.0"

    @pytest.mark.asyncio
    async def test_facade_promote_demotes_and_promotes(self, started_db):
        """promote() demotes existing champion and promotes target version.

        Bug fixed: promote() previously demoted champions but never updated
        the target model version's status. Now it demotes existing champions
        AND promotes the specified model_version to champion.
        """
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
        await started_db.model_registry.register(champion)

        # Register new version as shadow
        new_version = ModelVersion(
            model_family="ssm_v1",
            model_version="v2.0.0",
            model_type="deep_ssm",
            training_window_start="2024-01-01",
            training_window_end="2024-12-31",
            promotion_status="shadow",
            sample_count=15000,
            parameter_count=900_000,
            trained_at="2025-02-01T10:00:00",
        )
        await started_db.model_registry.register(new_version)

        # Promote v2.0.0
        success = await started_db.model_registry.promote("ssm_v1", "v2.0.0")
        assert success is True

        # Verify v2.0.0 is now champion
        new_champion = await started_db.model_registry.get_champion("ssm_v1")
        assert new_champion is not None
        assert new_champion["model_version"] == "v2.0.0"
        assert new_champion["promotion_status"] == "champion"

        # Verify v1.0.0 is now demoted to challenger
        old_champion = await started_db.model_registry.get("ssm_v1", "v1.0.0")
        assert old_champion["promotion_status"] == "challenger"

    @pytest.mark.asyncio
    async def test_facade_retire_marks_status_retired(self, started_db):
        """retire() marks the model as retired instead of being a no-op.

        Bug fixed: retire() previously returned True/False based on existence
        check without actually changing any data. Now it sets promotion_status
        to 'retired'.
        """
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
        await started_db.model_registry.register(mv)
        # Register a second model so retiring v1.0.0 doesn't hit the last-model guard
        mv2 = ModelVersion(
            model_family="deep_ssm_v1",
            model_version="v1.1.0",
            model_type="deep_ssm",
            training_window_start="2024-01-01",
            training_window_end="2024-12-31",
            promotion_status="champion",
            sample_count=16000,
            parameter_count=950_000,
            trained_at="2025-02-15T10:00:00",
        )
        await started_db.model_registry.register(mv2)

        # Retire the model
        retired = await started_db.model_registry.retire("deep_ssm_v1", "v1.0.0")
        assert retired is True

        # Verify the status is now 'retired'
        record = await started_db.model_registry.get("deep_ssm_v1", "v1.0.0")
        assert record["promotion_status"] == "retired"

    @pytest.mark.asyncio
    async def test_facade_retire_nonexistent_raises(self, started_db):
        """retire() raises RegistryError for nonexistent model."""
        with pytest.raises(RegistryError, match="not found"):
            await started_db.model_registry.retire("fake_family", "v0.0.0")

    @pytest.mark.asyncio
    async def test_facade_list_by_pool(self, started_db):
        """list_by_pool() returns models in the pool layer."""
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
            await started_db.model_registry.register(mv)

        repr_rows = await started_db.model_registry.list_by_pool("representation_learner")
        assert len(repr_rows) == 2
        families = {r["model_family"] for r in repr_rows}
        assert families == {"ssl_transformer_v1", "contrastive_v1"}

    @pytest.mark.asyncio
    async def test_facade_get_challengers(self, started_db):
        """get_challengers() returns shadow models in the pool."""
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
            await started_db.model_registry.register(mv)

        challengers = await started_db.model_registry.get_challengers("vae_v1")
        assert len(challengers) == 2
        assert all(r["promotion_status"] == "shadow" for r in challengers)

    @pytest.mark.asyncio
    async def test_facade_get_lineage(self, started_db):
        """get_lineage() returns all versions for a family."""
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
            await started_db.model_registry.register(mv)

        lineage = await started_db.model_registry.get_lineage("contrastive_v1")
        assert len(lineage) == 3
        versions = {r["model_version"] for r in lineage}
        assert versions == {"v1.0.0", "v1.1.0", "v1.2.0"}

    @pytest.mark.asyncio
    async def test_promote_nonexistent_version_raises(self, started_db):
        """promote() raises RegistryError when the target version doesn't exist."""
        mv = ModelVersion(
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
        await started_db.model_registry.register(mv)

        # Try to promote a nonexistent version
        with pytest.raises(RegistryError, match="not found"):
            await started_db.model_registry.promote("ssm_v1", "v99.0.0")
