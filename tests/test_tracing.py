from pathlib import Path

from converter.core.config import Settings
from converter.observability.tracing import Tracer


def test_disabled_tracer_is_a_noop():
    tracer = Tracer(Settings(mlflow_enabled=False))
    assert not tracer.enabled
    with tracer.span("noop", input={"run_id": "r1"}) as span:
        assert span is None
    tracer.set_outputs(None, {"ignored": True})
    tracer.flush()


def test_local_mlflow_tracer_records_a_span(tmp_path: Path):
    database = tmp_path / "mlflow.db"
    tracer = Tracer(
        Settings(
            mlflow_enabled=True,
            mlflow_tracking_uri=f"sqlite:///{database}",
            mlflow_experiment_name="converter-tracing-test",
        )
    )
    assert tracer.enabled

    with tracer.span(
        "translate",
        input={"run_id": "r1"},
        metadata={"attempt": 0, "generation_round": 1},
    ) as span:
        assert span is not None
        tracer.set_outputs(span, {"updated_keys": ["c_code"]})

    tracer.flush()
    assert database.exists()
