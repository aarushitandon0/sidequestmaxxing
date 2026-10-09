"""Export (P17): plan-only default, gguf commands, SHA, model card, publish guards. No network."""

import hashlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

import common
import export_model


@pytest.fixture
def run(tmp_path: Path) -> str:
    name = "sft-test"
    d = common.RUNS / name
    d.mkdir(parents=True)
    summary = {
        "config": {"base_model": "Qwen/Qwen3.5-4B", "lora_rank": 32, "seed": 0},
        "plan": {"epochs": 3, "lr_multipliers": [0.5, 1.0, 2.0]},
        "best": {"lr": 4e-4, "epoch": 2, "pass_rate": 0.87, "n_sampled": 100,
                 "sampler_path": "tinker://abc/sampler_weights/e2"},
    }  # fmt: skip
    (d / "summary.json").write_text(json.dumps(summary))
    return name


@pytest.fixture
def cfg_path(tmp_path: Path) -> Path:
    cfg = json.loads((export_model.CONFIG).read_text(encoding="utf-8"))
    cfg["hf_repo"] = "someone/sqm-quest-master"
    path = tmp_path / "export.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def call(step: str, run: str, cfg: Path, work: Path, *extra: str) -> int:
    return export_model.main(
        [step, "--run", run, "--config", str(cfg), "--work", str(work), *extra]
    )


def fake_weights(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []
    weights = types.SimpleNamespace(
        download=lambda **kw: calls.append(("download", kw)),
        build_hf_model=lambda **kw: calls.append(("build_hf_model", kw)),
    )
    pkg = types.ModuleType("tinker_cookbook")
    pkg.weights = weights  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tinker_cookbook", pkg)
    return calls


def test_heavy_steps_are_plan_only_without_go(
    run: str, cfg_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_weights(monkeypatch)
    work = tmp_path / "w"
    for step in ("download", "merge"):
        assert call(step, run, cfg_path, work) == 0
    assert call("gguf", run, cfg_path, work, "--llama-cpp", str(tmp_path)) == 0
    assert calls == []
    assert not (common.RUNS / run / "export.json").exists()


def test_download_and_merge_use_cookbook(
    run: str, cfg_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_weights(monkeypatch)
    work = tmp_path / "w"
    call("download", run, cfg_path, work, "--go")
    call("merge", run, cfg_path, work, "--go")
    assert calls[0] == ("download", {"tinker_path": "tinker://abc/sampler_weights/e2",
                                     "output_dir": str(work / "adapter")})  # fmt: skip
    assert calls[1] == ("build_hf_model", {"base_model": "Qwen/Qwen3.5-4B",
                                           "adapter_path": str(work / "adapter"),
                                           "output_path": str(work / "merged")})  # fmt: skip
    meta = json.loads((common.RUNS / run / "export.json").read_text(encoding="utf-8"))
    assert meta["sampler_path"] == "tinker://abc/sampler_weights/e2"
    assert meta["merged"] == "bfloat16"


def test_gguf_commands_convert_then_quantize(tmp_path: Path) -> None:
    cfg = json.loads(export_model.CONFIG.read_text(encoding="utf-8"))
    p = export_model.Paths(tmp_path, cfg)
    llama = Path("/llama")
    convert, quant = export_model.gguf_commands(p, llama, "Q4_K_M")
    # Expectations are built from the same Path, so the separators match whatever OS runs this.
    assert convert[1:] == [str(llama / "convert_hf_to_gguf.py"), str(p.merged), "--outfile",
                           str(p.bf16), "--outtype", "bf16"]  # fmt: skip
    assert quant == [str(llama / "build/bin/llama-quantize"), str(p.bf16), str(p.gguf), "Q4_K_M"]


def test_base_model_mismatch_refuses(run: str, cfg_path: Path, tmp_path: Path) -> None:
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["base_model"] = "Qwen/Qwen3-8B"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(SystemExit):
        call("card", run, cfg_path, tmp_path / "w")


def test_sha_card_and_publish_guards(
    run: str, cfg_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    work = tmp_path / "w"
    with pytest.raises(SystemExit):  # no GGUF yet
        call("sha", run, cfg_path, work)
    work.mkdir()
    gguf = work / json.loads(cfg_path.read_text(encoding="utf-8"))["gguf_file"]
    gguf.write_bytes(b"GGUF fake model bytes")
    want = hashlib.sha256(b"GGUF fake model bytes").hexdigest()

    assert call("sha", run, cfg_path, work) == 0
    out = capsys.readouterr().out
    assert f"MODEL_SHA256={want}" in out
    assert (
        "MODEL_URL=https://huggingface.co/someone/sqm-quest-master/resolve/main/"
        "sidequestmaxxing-quest-master-Q4_K_M.gguf"
    ) in out

    call("card", run, cfg_path, work)
    card = (work / "README.md").read_text(encoding="utf-8")
    for needle in ("license: apache-2.0", "base_model: Qwen/Qwen3.5-4B", "## Training summary",
                   "## Intended use", "## Limitations", "87.0% (n=100)", want,
                   "github.com/aarushitandon0/sidequestmaxxing"):  # fmt: skip
        assert needle in card

    uploads: list[dict[str, Any]] = []

    class FakeApi:
        def create_repo(self, **kw: Any) -> None:
            assert kw["private"] is False
            uploads.append(kw)

        def upload_file(self, **kw: Any) -> None:
            uploads.append(kw)

    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(HfApi=FakeApi))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert call("publish", run, cfg_path, work) == 0  # plan only
    assert uploads == []
    with pytest.raises(SystemExit, match="HF_TOKEN"):
        call("publish", run, cfg_path, work, "--go")
    monkeypatch.setenv("HF_TOKEN", "hf_test_not_real")
    assert call("publish", run, cfg_path, work, "--go") == 0
    assert [u.get("path_in_repo") for u in uploads[1:]] == ["README.md", gguf.name]
    assert (
        json.loads((common.RUNS / run / "export.json").read_text(encoding="utf-8"))["published"]
        is True
    )

    gguf.write_bytes(b"different bytes")  # GGUF changed after sha: refuse
    with pytest.raises(SystemExit, match="changed"):
        call("publish", run, cfg_path, work, "--go")
