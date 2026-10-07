"""LoRA SFT of the Quest Master on Tinker (P15, MASTERSPEC §10.4).

  python training/train_sft.py --smoke            # prints the plan; does nothing paid
  python training/train_sft.py --smoke --go       # smallest real run: 200 ex, 1 epoch, 1 LR
  python training/train_sft.py --go               # full sweep: 3 LRs x configured epochs

Per epoch it records train NLL, val NLL (forward pass on val SFT rows) and the validator
pass-rate of quests SAMPLED from the checkpoint on held-out val contexts with the production
prompt + sampling params. The best (LR, epoch) by pass-rate, then val NLL, is the pick.
Everything is appended to training/runs/RUNS.md; per-step metrics go to
training/runs/<run>/metrics.jsonl. Download the weights with scripts/export_model.py (P17).

Tinker calls follow tinker-cookbook 0.5.7 `recipes/sl_loop.py`: create_lora_training_client,
conversation_to_datum, forward_backward(..., "cross_entropy"), optim_step(AdamParams),
save_weights_and_get_sampling_client, checkpoint_utils.save_checkpoint.
"""

import argparse
import asyncio
import json
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common import (
    DATA,
    RUNS,
    append_runs_md,
    load_config,
    read_jsonl,
    rng,
    save_run_metadata,
    utc_stamp,
)
from records import messages, to_input, validation_context

from app.agents.quest_master import extract_json_text
from app.prompts import committed_hashes
from app.validators.core import validate_quest

CONFIG = Path(__file__).parent / "configs" / "sft.json"


@dataclass
class EpochResult:
    lr: float
    epoch: int
    train_nll: float
    val_nll: float | None
    pass_rate: float | None
    n_sampled: int
    sampler_path: str | None = None
    state_path: str | None = None
    failure_ids: dict[str, int] = field(default_factory=dict)

    def score(self) -> tuple[float, float]:
        """Higher is better: validator pass-rate first, then lower val NLL."""
        return (self.pass_rate or 0.0, -(self.val_nll if self.val_nll is not None else math.inf))


def load_mix(
    cfg: dict[str, Any], split: str, limit: int | None, seed: int, data: Path = DATA
) -> list[dict[str, Any]]:
    """Quest rows + ~recap_share recap rows (multi-task SFT, §7.7), deterministic order."""
    quest_path = data / "sft" / f"{split}.jsonl"
    quests = list(read_jsonl(quest_path)) if quest_path.exists() else []
    recap_path = data / "sft_recap" / f"{split}.jsonl"
    recaps = list(read_jsonl(recap_path)) if recap_path.exists() else []
    share = cfg["recap_share"]
    n_recap = min(len(recaps), round(len(quests) * share / (1 - share))) if recaps else 0
    rows = quests + recaps[:n_recap]
    rows.sort(key=lambda r: rng(seed, "mix", split, r["id"]).random())
    return rows[:limit] if limit else rows


def lr_schedule(base_lr: float, step: int, total: int) -> float:
    """Linear decay to 0 (recipes/sl_loop.py)."""
    return base_lr * max(0.0, 1.0 - step / max(1, total))


def pass_rate(texts: list[str], records: list[dict[str, Any]]) -> tuple[float, dict[str, int]]:
    fails: dict[str, int] = {}
    ok = 0
    for text, rec in zip(texts, records, strict=True):
        res = validate_quest(
            extract_json_text(text), validation_context(rec), to_input(rec).candidates
        )
        ok += res.ok
        for fid in res.failure_ids:
            fails[fid] = fails.get(fid, 0) + 1
    return (ok / len(records) if records else 0.0), fails


def runs_md_row(run: str, base: str, r: EpochResult) -> str:
    vn = f"{r.val_nll:.4f}" if r.val_nll is not None else "-"
    pr = f"{r.pass_rate:.1%}" if r.pass_rate is not None else "-"
    return (
        f"| {run} | {base} | {r.lr:.2e} | {r.epoch} | {r.train_nll:.4f} | {vn} | {pr} "
        f"(n={r.n_sampled}) | `{r.sampler_path or '-'}` |"
    )


class TinkerSFT:
    """The paid part. Constructed only with --go."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        import tinker
        from tinker_cookbook import renderers
        from tinker_cookbook.tokenizer_utils import get_tokenizer

        from tinker_backend import pick_renderer_name

        self.tinker = tinker
        self.cfg = cfg
        self.service = tinker.ServiceClient()
        self.renderer_name = pick_renderer_name(cfg["base_model"])
        self.renderer = renderers.get_renderer(self.renderer_name, get_tokenizer(cfg["base_model"]))

    def default_lr(self) -> float:
        from tinker_cookbook.hyperparam_utils import get_lr

        return float(get_lr(self.cfg["base_model"]))

    def datums(self, rows: list[dict[str, Any]]) -> list[Any]:
        from tinker_cookbook.renderers import TrainOnWhat
        from tinker_cookbook.supervised.data import conversation_to_datum

        return [
            conversation_to_datum(
                r["messages"],
                self.renderer,
                self.cfg["max_length"],
                TrainOnWhat.LAST_ASSISTANT_MESSAGE,
            )
            for r in rows
        ]

    def run_lr(
        self,
        lr: float,
        epochs: int,
        train: list[Any],
        val: list[Any],
        val_records: list[dict[str, Any]],
        log_dir: Path,
        on_epoch: Callable[[EpochResult], None],
    ) -> None:
        from tinker_cookbook import checkpoint_utils
        from tinker_cookbook.supervised.common import compute_mean_nll

        from tinker_backend import SampleSettings, TinkerChat

        tc = self.service.create_lora_training_client(
            base_model=self.cfg["base_model"], rank=self.cfg["lora_rank"]
        )
        bs = self.cfg["batch_size"]
        steps_per_epoch = len(train) // bs  # drop the ragged last batch (sl_loop.py)
        total = steps_per_epoch * epochs
        metrics_path = log_dir / "metrics.jsonl"
        step = 0
        for epoch in range(1, epochs + 1):
            order = sorted(
                range(len(train)), key=lambda i: rng(self.cfg["seed"], lr, epoch, i).random()
            )
            nlls: list[float] = []
            for b in range(steps_per_epoch):
                batch = [train[i] for i in order[b * bs : (b + 1) * bs]]
                cur = lr_schedule(lr, step, total)
                adam = self.tinker.AdamParams(learning_rate=cur, beta1=0.9, beta2=0.95, eps=1e-8)
                fb = tc.forward_backward(batch, loss_fn="cross_entropy")
                opt = tc.optim_step(adam)
                out = fb.result()
                opt.result()
                nll = compute_mean_nll(
                    [x["logprobs"] for x in out.loss_fn_outputs],
                    [d.loss_fn_inputs["weights"] for d in batch],
                )
                nlls.append(nll)
                with metrics_path.open("a") as f:
                    f.write(
                        json.dumps(
                            {
                                "lr": lr,
                                "epoch": epoch,
                                "step": step,
                                "lr_now": cur,
                                "train_nll": nll,
                            }
                        )
                        + "\n"
                    )
                step += 1

            val_nll = None
            if val:
                out = tc.forward(val, loss_fn="cross_entropy").result()
                val_nll = compute_mean_nll(
                    [x["logprobs"] for x in out.loss_fn_outputs],
                    [d.loss_fn_inputs["weights"] for d in val],
                )
            name = f"lr{lr:.0e}-e{epoch}"
            paths = checkpoint_utils.save_checkpoint(
                training_client=tc,
                name=name,
                log_path=str(log_dir),
                kind="both",
                loop_state={"epoch": epoch, "lr": lr},
                ttl_seconds=self.cfg["checkpoint_ttl_seconds"],
            )
            sampler = tc.save_weights_and_get_sampling_client(name=f"{name}-eval")
            chat = TinkerChat(self.cfg["base_model"], service=self.service, client=sampler)
            s = self.cfg["sampling"]
            settings = SampleSettings(
                s["temperature"], s["top_p"], s["max_tokens"], seed=self.cfg["seed"]
            )
            texts = asyncio.run(_sample_all(chat, val_records, settings))
            rate, fails = pass_rate(texts, val_records)
            on_epoch(
                EpochResult(
                    lr=lr,
                    epoch=epoch,
                    train_nll=sum(nlls) / max(1, len(nlls)),
                    val_nll=val_nll,
                    pass_rate=rate,
                    n_sampled=len(val_records),
                    sampler_path=paths.get("sampler_path"),
                    state_path=paths.get("state_path"),
                    failure_ids=fails,
                )
            )


async def _sample_all(chat: Any, records: list[dict[str, Any]], settings: Any) -> list[str]:
    sem = asyncio.Semaphore(16)

    async def one(rec: dict[str, Any]) -> str:
        async with sem:
            try:
                return str((await chat.chat(messages(rec), 1, settings))[0]["text"])
            except Exception:
                return ""

    return list(await asyncio.gather(*(one(r) for r in records)))


def plan(cfg: dict[str, Any], smoke: bool) -> dict[str, Any]:
    sm = cfg["smoke"] if smoke else {}
    return {
        "base_model": cfg["base_model"],
        "epochs": sm.get("epochs", cfg["epochs"]),
        "lr_multipliers": sm.get("lr_multipliers", cfg["lr_multipliers"]),
        "train_limit": sm.get("train_examples"),
        "val_pass_rate_contexts": sm.get("val_pass_rate_contexts", cfg["val_pass_rate_contexts"]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--data", type=Path, default=DATA, help="dir with sft/, sft_recap/, contexts/")
    ap.add_argument("--smoke", action="store_true", help="small subset, 1 epoch, 1 LR")
    ap.add_argument("--go", action="store_true", help="actually train on Tinker (PAID)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    p = plan(cfg, args.smoke)
    train_rows = load_mix(cfg, "train", p["train_limit"], cfg["seed"], args.data)
    val_rows = load_mix(cfg, "val", None, cfg["seed"], args.data)
    ctx_path = args.data / "contexts" / "val.jsonl"
    val_ctx = list(read_jsonl(ctx_path))[: p["val_pass_rate_contexts"]] if ctx_path.exists() else []
    tokens = sum(sum(len(m["content"]) for m in r["messages"]) for r in train_rows) / 3.5
    total_tokens = tokens * p["epochs"] * len(p["lr_multipliers"])
    summary = {
        **p,
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "val_contexts": len(val_ctx),
        "approx_train_tokens_per_epoch": round(tokens),
        "approx_train_tokens_total": round(total_tokens),
    }
    print(json.dumps(summary, indent=2))
    if not args.go:
        print("Plan only. Re-run with --go to train on Tinker (this spends money).")
        return 0
    if not train_rows or not val_ctx:
        print(
            "Missing data: run make_contexts.py, gen_teacher.py and filter.py first.",
            file=sys.stderr,
        )
        return 2

    run = f"sft_{'smoke' if args.smoke else 'full'}_{utc_stamp()}"
    log_dir = RUNS / run
    log_dir.mkdir(parents=True, exist_ok=True)
    sft = TinkerSFT(cfg)
    base_lr = cfg["learning_rate"] or sft.default_lr()
    results: list[EpochResult] = []
    append_runs_md(
        f"\n### {run}\n\nBase `{cfg['base_model']}`, LoRA r={cfg['lora_rank']}, "
        f"renderer `{sft.renderer_name}`, {len(train_rows)} train rows, seed {cfg['seed']}.\n\n"
        "| run | base | LR | epoch | train NLL | val NLL | val pass-rate | sampler |\n"
        "|---|---|---|---|---|---|---|---|"
    )

    def on_epoch(r: EpochResult) -> None:
        results.append(r)
        append_runs_md(runs_md_row(run, cfg["base_model"], r))
        print(
            f"lr={r.lr:.2e} epoch={r.epoch} train_nll={r.train_nll:.4f} val_nll={r.val_nll} "
            f"pass={r.pass_rate}"
        )

    train = sft.datums(train_rows)
    val = sft.datums(val_rows)
    for mult in p["lr_multipliers"]:
        sft.run_lr(base_lr * mult, p["epochs"], train, val, val_ctx, log_dir, on_epoch)
    best = max(results, key=EpochResult.score)
    append_runs_md(
        f"\n**Best:** LR {best.lr:.2e}, epoch {best.epoch}, "
        f"pass-rate {best.pass_rate or 0:.1%}, sampler `{best.sampler_path}`."
    )
    save_run_metadata(
        f"{run}/summary",
        {
            "stage": "train_sft",
            "config": cfg,
            "plan": p,
            "renderer": sft.renderer_name,
            "base_lr": base_lr,
            "results": [r.__dict__ for r in results],
            "best": best.__dict__,
            "prompt_hashes": committed_hashes(),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
