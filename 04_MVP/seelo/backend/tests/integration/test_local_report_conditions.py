"""하나의 측정 도중 API/CLI 전송 경로가 섞인 경우에도 비교 보고서를 거부한다."""

import pytest

from seelo.models.measurement import AiExecution
from seelo.services import report_service
from tests.report_world import completed_remeasure

pytestmark = pytest.mark.usefixtures("queue_app", "fake_mailer")


@pytest.mark.parametrize(
    "models,mixed",
    [
        (["api-model", "codex-cli/gpt-6.1-sol"], True),
        (["old-api-model", "new-api-model"], False),
        (["codex-cli/old", "codex-cli/new"], False),
    ],
)
async def test_transport_switch_within_run_is_not_hidden_by_last_model(db, models, mixed):
    world = await completed_remeasure(db)
    for repeat, model in enumerate(models, 1):
        db.add(
            AiExecution(
                run_id=world["run_id"],
                question_id=world["qids"][0],
                provider="openai",
                repeat_no=repeat,
                status="succeeded",
                model_id=model,
            )
        )
    await db.commit()
    if mixed:
        with pytest.raises(ValueError, match="report_conditions_mismatch"):
            await report_service._view(db, world["run_id"])
    else:
        view = await report_service._view(db, world["run_id"])
        assert view.models["openai"] == models[-1]
