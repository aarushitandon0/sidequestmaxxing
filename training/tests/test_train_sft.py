"""SFT script (P15): data mix, LR schedule, scoring, gating, and the loop on a fake Tinker."""

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

import common
import filter as filt
import gen_teacher
import make_recap_examples
import train_sft
from train_sft import EpochResult, lr_schedule, pass_rate


@pytest.fixture
def data_dir(ctx_dir: Path, tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    (d / "contexts").symlink_to(ctx_dir, target_is_directory=True)
    teacher = tmp_path / "teacher"
    for split in ("train", "val"):
        gen_teacher.main(
            [
                "--split",
                split,
                "--contexts",
                str(ctx_dir),
                "--out",
                str(teacher),
                "--backend",
                "fallback",
                "--limit",
                "300",
            ]
        )
        filt.main(
            [
                "--split",
                split,
                "--teacher",
                str(teacher / f"{split}.fallback.jsonl"),
                "--contexts",
                str(ctx_dir),
                "--out",
                str(d / "sft"),
                "--embedder",
                "hash",
            ]
        )
    make_recap_examples.main(["--synthetic", "--out", str(d / "sft_recap")])
    return d


def test_mix_has_recap_share(data_dir: Path) -> None:
    cfg = common.load_config(train_sft.CONFIG)
    rows = train_sft.load_mix(cfg, "train", None, 0, data_dir)
    recaps = sum(r.get("task") == "recap" for r in rows)
    assert 0.10 <= recaps / len(rows) <= 0.16
    assert rows == train_sft.load_mix(cfg, "train", None, 0, data_dir)  # deterministic
    assert len(train_sft.load_mix(cfg, "train", 25, 0, data_dir)) == 25


def test_lr_schedule_decays_linearly() -> None:
    assert lr_schedule(1e-3, 0, 10) == 1e-3
    assert lr_schedule(1e-3, 5, 10) == pytest.approx(5e-4)
    assert lr_schedule(1e-3, 10, 10) == 0.0


def test_best_epoch_prefers_pass_rate_then_val_nll() -> None:
    a = EpochResult(1e-4, 1, 1.0, 0.9, 0.80, 10)
    b = EpochResult(2e-4, 1, 1.0, 0.7, 0.80, 10)
    c = EpochResult(5e-5, 2, 1.0, 0.5, 0.70, 10)
    assert max([a, b, c], key=EpochResult.score) is b


def test_pass_rate_uses_production_validators(ctx_dir: Path) -> None:
    recs = list(common.read_jsonl(ctx_dir / "val.jsonl"))[:3]
    good = [json.loads(json.dumps(r)) for r in recs]
    from records import fallback_input

    from app.agents.fallback_engine import generate_fallback_quest

    texts = [json.dumps(generate_fallback_quest(fallback_input(r)).model_dump()) for r in good]
    rate, fails = pass_rate([texts[0], "not json", texts[2]], recs)
    assert rate == pytest.approx(2 / 3)
    assert fails == {"V1": 1}


def test_without_go_nothing_is_trained(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(train_sft, "TinkerSFT", lambda cfg: pytest.fail("must not touch Tinker"))
    assert train_sft.main(["--smoke", "--data", str(data_dir)]) == 0


# ---------------------------------------------------------------- fake Tinker for the loop


class _Future:
    def __init__(self, v: Any) -> None:
        self.v = v

    def result(self) -> Any:
        return self.v


class FakeTC:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def forward_backward(self, batch: list[Any], loss_fn: str) -> _Future:
        self.log.append(f"fb{len(batch)}")
        return _Future(types.SimpleNamespace(loss_fn_outputs=[{"logprobs": [-0.5]} for _ in batch]))

    def optim_step(self, adam: Any) -> _Future:
        self.log.append(f"opt{adam.learning_rate:.1e}")
        return _Future(types.SimpleNamespace(metrics={}))

    def forward(self, batch: list[Any], loss_fn: str) -> _Future:
        self.log.append("val")
        return _Future(types.SimpleNamespace(loss_fn_outputs=[{"logprobs": [-0.4]} for _ in batch]))

    def save_weights_and_get_sampling_client(self, name: str) -> str:
        return f"sampler:{name}"


def install_fake_tinker(monkeypatch: pytest.MonkeyPatch, log: list[str], answer: str) -> None:
    tinker = types.ModuleType("tinker")
    tinker.AdamParams = lambda **kw: types.SimpleNamespace(**kw)  # type: ignore[attr-defined]
    tinker.ServiceClient = lambda: types.SimpleNamespace(  # type: ignore[attr-defined]
        create_lora_training_client=lambda base_model, rank: FakeTC(log)
    )
    cb = types.ModuleType("tinker_cookbook")
    ckpt = types.ModuleType("tinker_cookbook.checkpoint_utils")
    ckpt.save_checkpoint = lambda **kw: {
        "sampler_path": f"tinker://run/{kw['name']}",  # type: ignore[attr-defined]
        "state_path": f"tinker://run/state/{kw['name']}",
    }
    sup = types.ModuleType("tinker_cookbook.supervised.common")
    sup.compute_mean_nll = lambda lps, ws: -sum(x[0] for x in lps) / len(lps)  # type: ignore[attr-defined]
    for name, mod in {
        "tinker": tinker,
        "tinker_cookbook": cb,
        "tinker_cookbook.checkpoint_utils": ckpt,
        "tinker_cookbook.supervised": types.ModuleType("x"),
        "tinker_cookbook.supervised.common": sup,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    cb.checkpoint_utils = ckpt  # type: ignore[attr-defined]

    class FakeChat:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        async def chat(self, msgs: Any, n: int, s: Any) -> list[dict[str, Any]]:
            return [{"text": answer}]

    import tinker_backend

    monkeypatch.setattr(tinker_backend, "TinkerChat", FakeChat)


def test_loop_on_fake_tinker(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log: list[str] = []
    install_fake_tinker(monkeypatch, log, "not json")  # every sampled quest fails V1
    cfg = {**common.load_config(train_sft.CONFIG), "batch_size": 8}
    sft = object.__new__(train_sft.TinkerSFT)
    sft.cfg, sft.tinker, sft.service = (
        cfg,
        sys.modules["tinker"],
        sys.modules["tinker"].ServiceClient(),
    )
    train = [types.SimpleNamespace(loss_fn_inputs={"weights": [1]}) for _ in range(20)]
    val = train[:3]
    records = list(common.read_jsonl(data_dir / "contexts" / "val.jsonl"))[:4]
    results: list[EpochResult] = []
    sft.run_lr(1e-3, 2, train, val, records, tmp_path, results.append)

    assert [r.epoch for r in results] == [1, 2]
    assert log.count("fb8") == 4  # 20 // 8 = 2 steps per epoch, ragged batch dropped
    assert log.count("val") == 2
    lrs = [float(x[3:]) for x in log if x.startswith("opt")]
    assert lrs[0] == pytest.approx(1e-3) and lrs == sorted(lrs, reverse=True)
    assert results[0].pass_rate == 0.0 and results[0].failure_ids == {"V1": 4}
    assert results[1].sampler_path == "tinker://run/lr1e-03-e2"
    assert len((tmp_path / "metrics.jsonl").read_text().splitlines()) == 4
