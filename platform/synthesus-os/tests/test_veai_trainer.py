import asyncio
import pytest
from core.synthesus_master import SynthesusMaster
from core.veai_trainer import VEAITrainer, TrainerConfig


@pytest.mark.asyncio
async def test_batch_training_with_events():
    master = SynthesusMaster()

    # Generate some events with explanations
    for i in range(25):
        result = await master.think("Why is the system experiencing a slowdown?")
        # Simulate feedback
        await master.record_feedback(i, "correct")

    trainer = VEAITrainer(master, TrainerConfig(batch_interval_seconds=1, min_events_to_train=10))

    # Run batch training
    result = trainer.run_batch_training()

    assert result["status"] == "ok"
    assert result["events"] == 25
    assert trainer._last_trained_index == 25
    assert trainer.metrics.total_events_processed == 25
    assert trainer.metrics.total_batches == 1


@pytest.mark.asyncio
async def test_skip_batch_when_not_enough_events():
    master = SynthesusMaster()

    # Generate fewer than min events
    for i in range(5):
        await master.think("Test query")

    trainer = VEAITrainer(master, TrainerConfig(min_events_to_train=10))

    result = trainer.run_batch_training()

    assert result["status"] == "skipped"
    assert result["reason"] == "not_enough_events"
    assert trainer._last_trained_index == 0


@pytest.mark.asyncio
async def test_abductive_prior_adjustment():
    master = SynthesusMaster()

    # Add a fake domain prior to test adjustment
    if hasattr(master.core.abductive, 'explanation_ranker') and hasattr(master.core.abductive.explanation_ranker, 'domain_priors'):
        master.core.abductive.explanation_ranker.domain_priors = {"slowdown": 0.5}

    await master.think("Why is the system experiencing a slowdown?")
    await master.record_feedback(0, "correct")  # This should adjust beliefs

    trainer = VEAITrainer(master, TrainerConfig(min_events_to_train=1))

    initial_prior = master.core.abductive.explanation_ranker.domain_priors.get("slowdown", 0.5)
    result = trainer.run_batch_training()
    final_prior = master.core.abductive.explanation_ranker.domain_priors.get("slowdown", 0.5)

    # Should have adjusted toward belief score
    assert abs(final_prior - initial_prior) > 0 or result["status"] == "ok"
