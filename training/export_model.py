"""Export the tuned model to the GGUF that sqm-llm serves (P17, docs/MODEL_EXPORT.md).

One step per call, in order. Steps that download, compute for long, or upload do nothing
without --go (they print the plan); `card` and `sha` are local and free.

  python training/export_model.py download --run <run>     # Tinker sampler weights -> adapter/
  python training/export_model.py merge    --run <run>     # cookbook build_hf_model -> merged/
  python training/export_model.py gguf     --run <run> --llama-cpp ~/llama.cpp  # -> Q4_K_M
  python training/export_model.py card     --run <run>     # README.md model card
  python training/export_model.py sha      --run <run>     # SHA-256, MODEL_URL, MODEL_SHA256
  python training/export_model.py publish  --run <run> --go  # PUBLIC HF repo (HF_TOKEN)

`<run>` is the train_sft run folder (training/runs/<run>/summary.json picks the best checkpoint).
Merge uses the cookbook's build_hf_model, not PEFT merge_and_unload: Tinker trains split
in_proj_q/k/v adapters on Qwen3.5's fused in_proj_qkv, which only the cookbook re-fuses (D-60).
Work files: training/data/export/<run>/ (gitignored); metadata: training/runs/<run>/export.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import common  # RUNS is read at call time (tests repoint it)
from common import DATA, TRAINING, load_config, save_run_metadata

log = logging.getLogger("export_model")
CONFIG = TRAINING / "configs" / "export.json"
STEPS = ("download", "merge", "gguf", "card", "sha", "publish")
PAID_OR_HEAVY = {"download", "merge", "gguf", "publish"}


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def model_url(repo: str, filename: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/main/{filename}"


def load_summary(run: str, base_model: str) -> dict[str, Any]:
    path = common.RUNS / run / "summary.json"
    if not path.exists():
        raise SystemExit(f"no SFT summary at {path}; run train_sft.py --go first")
    data: dict[str, Any] = json.loads(path.read_text())
    trained = (data.get("config") or {}).get("base_model")
    if trained != base_model:
        raise SystemExit(f"run {run} trained {trained}, export config says {base_model}")
    return data


def export_meta(run: str) -> dict[str, Any]:
    path = common.RUNS / run / "export.json"
    return json.loads(path.read_text()) if path.exists() else {}


def update_meta(run: str, **fields: Any) -> None:
    meta = {k: v for k, v in export_meta(run).items() if k not in ("git_rev", "written_at")}
    meta.update(stage="export_model", **fields)
    save_run_metadata(f"{run}/export", meta)


class Paths:
    def __init__(self, work: Path, cfg: dict[str, Any]) -> None:
        self.work = work
        self.adapter = work / "adapter"
        self.merged = work / "merged"
        self.bf16 = work / "model-bf16.gguf"
        self.gguf = work / cfg["gguf_file"]
        self.card = work / "README.md"


def gguf_commands(p: Paths, llama_cpp: Path, quant: str) -> list[list[str]]:
    """llama.cpp convert_hf_to_gguf.py (bf16) then llama-quantize (verified on master, D-60)."""
    quantize = llama_cpp / "build" / "bin" / "llama-quantize"
    return [
        [sys.executable, str(llama_cpp / "convert_hf_to_gguf.py"), str(p.merged),
         "--outfile", str(p.bf16), "--outtype", "bf16"],
        [str(quantize), str(p.bf16), str(p.gguf), quant],
    ]  # fmt: skip


def render_card(cfg: dict[str, Any], summary: dict[str, Any], sha: str | None) -> str:
    """Model card. Every number comes from summary.json (train_sft output), never typed here."""
    best = summary.get("best") or {}
    sft = summary.get("config") or {}
    plan = summary.get("plan") or {}
    pass_rate = best.get("pass_rate")
    lines = [
        "---",
        f"license: {cfg['license']}",
        f"base_model: {cfg['base_model']}",
        "tags: [gguf, lora, sft, tinker, llama.cpp]",
        "---",
        "",
        "# Sidequestmaxxing Quest Master",
        "",
        "Turns a small JSON context (nearby public places, weather, time, the player's level and "
        "interests) into one outdoor side quest as JSON. It's the model behind "
        f"[Sidequestmaxxing]({cfg['repo_url']}), an open-source game that gets people off the "
        "screen and out into their neighbourhood.",
        "",
        "## Model",
        f"- Base: [`{cfg['base_model']}`](https://huggingface.co/{cfg['base_model']}) "
        f"(licence: {cfg['license']}).",
        f"- Fine-tune: LoRA rank {sft.get('lora_rank', '?')} SFT on "
        "[Tinker](https://thinkingmachines.ai/tinker/), merged with the Tinker Cookbook, "
        f"converted with llama.cpp and quantized to {cfg['quant']}.",
        f"- File: `{cfg['gguf_file']}`" + (f" (SHA-256 `{sha}`)." if sha else "."),
        "",
        "## Training summary",
        "Generated from the training run's metadata "
        f"([`training/runs/`]({cfg['repo_url']}/tree/main/training/runs)).",
        f"- Epochs: {plan.get('epochs', '?')}; seed: {sft.get('seed', '?')}; "
        f"LR sweep multipliers: {plan.get('lr_multipliers', '?')}.",
        f"- Chosen checkpoint: LR {best.get('lr', '?')}, epoch {best.get('epoch', '?')}.",
        "- Validator pass-rate on held-out contexts (Tinker sampler, before quantization): "
        + (f"{pass_rate:.1%} (n={best.get('n_sampled')})." if pass_rate is not None else "n/a."),
        "- Data: synthetic contexts built from OpenStreetMap public places; teacher-written quests "
        "kept only if they passed the game's production validators (V1-V12).",
        f"- Evaluation of this exact GGUF: see [`evals/results.md`]({cfg['repo_url']}"
        "/blob/main/evals/results.md).",
        "",
        "## Intended use",
        "Serving the Sidequestmaxxing API with the system prompt in "
        f"[`prompts/`]({cfg['repo_url']}/tree/main/prompts) and llama.cpp `llama-server`. "
        "Output is meant to be checked by the game's validators, with a deterministic fallback.",
        "",
        "## Limitations",
        "- Trained for one narrow task and one JSON schema; not a general assistant.",
        "- It can still invent places or unsafe suggestions: never show its output without the "
        "validators (public places only, banned-term lint, safety note).",
        "- English only. Quantization to "
        f"{cfg['quant']} can lower quality compared with the bf16 merge.",
        "- No real user data was used in training.",
        "",
    ]
    return "\n".join(lines)


Runner = Callable[[list[str]], None]


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)  # noqa: S603 - fixed argv, no shell


def step_download(args: argparse.Namespace, cfg: dict[str, Any], p: Paths) -> None:
    path = args.sampler_path
    if not path:
        best = load_summary(args.run, cfg["base_model"]).get("best") or {}
        path = best.get("sampler_path")
    if not path:
        raise SystemExit("no sampler_path in summary.json; pass --sampler-path tinker://...")
    log.info("download %s -> %s", path, p.adapter)
    if not args.go:
        return
    from tinker_cookbook import weights

    weights.download(tinker_path=path, output_dir=str(p.adapter))
    update_meta(args.run, sampler_path=path)


def step_merge(args: argparse.Namespace, cfg: dict[str, Any], p: Paths) -> None:
    log.info("build_hf_model base=%s adapter=%s -> %s", cfg["base_model"], p.adapter, p.merged)
    if not args.go:
        return
    from tinker_cookbook import weights

    weights.build_hf_model(
        base_model=cfg["base_model"], adapter_path=str(p.adapter), output_path=str(p.merged)
    )
    update_meta(args.run, base_model=cfg["base_model"], merged="bfloat16")


def step_gguf(args: argparse.Namespace, cfg: dict[str, Any], p: Paths, run: Runner = _run) -> None:
    if not args.llama_cpp:
        raise SystemExit("--llama-cpp <path to a built llama.cpp checkout> is required")
    cmds = gguf_commands(p, args.llama_cpp, cfg["quant"])
    for c in cmds:
        log.info("$ %s", " ".join(c))
    if not args.go:
        return
    for c in cmds:
        run(c)
    update_meta(args.run, gguf_file=cfg["gguf_file"], quant=cfg["quant"])


def step_card(args: argparse.Namespace, cfg: dict[str, Any], p: Paths) -> None:
    sha = export_meta(args.run).get("sha256")
    p.work.mkdir(parents=True, exist_ok=True)
    p.card.write_text(render_card(cfg, load_summary(args.run, cfg["base_model"]), sha))
    log.info("wrote %s", p.card)


def step_sha(args: argparse.Namespace, cfg: dict[str, Any], p: Paths) -> None:
    if not p.gguf.exists():
        raise SystemExit(f"{p.gguf} not found; run the gguf step first")
    sha = sha256_file(p.gguf)
    fields: dict[str, Any] = {"sha256": sha, "gguf_bytes": p.gguf.stat().st_size}
    if cfg.get("hf_repo"):
        fields["model_url"] = model_url(cfg["hf_repo"], cfg["gguf_file"])
    update_meta(args.run, **fields)
    print(f"MODEL_URL={fields.get('model_url', '<set hf_repo in configs/export.json>')}")
    print(f"MODEL_SHA256={sha}")


def step_publish(args: argparse.Namespace, cfg: dict[str, Any], p: Paths) -> None:
    repo = cfg.get("hf_repo")
    if not repo:
        raise SystemExit("set hf_repo in training/configs/export.json first")
    meta = export_meta(args.run)
    if not p.gguf.exists() or not p.card.exists() or not meta.get("sha256"):
        raise SystemExit("run gguf, sha, then card before publish")
    if sha256_file(p.gguf) != meta["sha256"]:
        raise SystemExit("GGUF changed since the sha step; re-run sha and card")
    log.info("upload %s + README.md -> PUBLIC https://huggingface.co/%s", p.gguf.name, repo)
    if not args.go:
        return
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN is not set (a write token; never paste it into chat)")
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo_id=repo, token=token, private=False, repo_type="model", exist_ok=True)
    for src, dest in ((p.card, "README.md"), (p.gguf, p.gguf.name)):
        api.upload_file(path_or_fileobj=str(src), path_in_repo=dest, repo_id=repo, token=token)
    update_meta(args.run, hf_repo=repo, model_url=model_url(repo, p.gguf.name), published=True)
    print(f"MODEL_URL={model_url(repo, p.gguf.name)}")
    print(f"MODEL_SHA256={meta['sha256']}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("step", choices=STEPS)
    ap.add_argument("--run", required=True, help="train_sft run folder under training/runs/")
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--work", type=Path, help="default training/data/export/<run>")
    ap.add_argument("--sampler-path", help="override the best tinker://... sampler path")
    ap.add_argument("--llama-cpp", type=Path, help="built llama.cpp checkout (gguf step)")
    ap.add_argument("--go", action="store_true", help="actually download/compute/upload")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    sft_base = load_config(TRAINING / "configs" / "sft.json")["base_model"]
    if cfg["base_model"] != sft_base:
        raise SystemExit(f"export base_model {cfg['base_model']} != sft.json {sft_base}")
    p = Paths(args.work or DATA / "export" / args.run, cfg)
    if args.step in PAID_OR_HEAVY and not args.go:
        log.info("PLAN ONLY (add --go to run):")
    {
        "download": step_download,
        "merge": step_merge,
        "gguf": step_gguf,
        "card": step_card,
        "sha": step_sha,
        "publish": step_publish,
    }[args.step](args, cfg, p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
