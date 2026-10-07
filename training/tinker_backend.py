"""Thin wrapper over the Tinker SDK + Cookbook for chat sampling (P14-P16).

API verified against the official sources (2026-10-07, tinker 0.32.0 / tinker-cookbook
0.5.7; tinker-docs.thinkingmachines.ai itself was blocked from the build container):
  tinker.ServiceClient().create_sampling_client(base_model=… | model_path="tinker://…")
  sampling_client.sample_async(prompt=ModelInput, num_samples=n, sampling_params=SamplingParams)
  tinker_cookbook.model_info.get_recommended_renderer_names(model)
  tinker_cookbook.renderers.get_renderer(name, tokenizer) → build_generation_prompt(messages),
  get_stop_sequences(), parse_response(tokens) → (Message, termination)
Imports are lazy so dry runs and tests never need the SDK or TINKER_API_KEY.
"""

from dataclasses import dataclass
from typing import Any


def pick_renderer_name(model_name: str) -> str:
    """Thinking OFF, matching llama.cpp's `enable_thinking: false` at serving time."""
    from tinker_cookbook import model_info

    names = model_info.get_recommended_renderer_names(model_name)
    off = [n for n in names if n.endswith("_disable_thinking")]
    return str(off[0] if off else names[0])


@dataclass
class SampleSettings:
    temperature: float = 0.8
    top_p: float = 0.95
    max_tokens: int = 380
    seed: int | None = None


class TinkerChat:
    """Chat-style sampling from a base model or a trained checkpoint."""

    def __init__(
        self,
        model_name: str,
        model_path: str | None = None,
        service: Any = None,
        client: Any = None,
    ) -> None:
        import tinker
        from tinker_cookbook import renderers
        from tinker_cookbook.tokenizer_utils import get_tokenizer

        self.model_name = model_name
        self.service = service or tinker.ServiceClient()
        if client is not None:  # e.g. training_client.save_weights_and_get_sampling_client()
            self.client = client
        elif model_path:
            self.client = self.service.create_sampling_client(model_path=model_path)
        else:
            self.client = self.service.create_sampling_client(base_model=model_name)
        self.renderer_name = pick_renderer_name(model_name)
        self.renderer = renderers.get_renderer(self.renderer_name, get_tokenizer(model_name))
        self._types = tinker.types

    async def chat(
        self, messages: list[dict[str, str]], n: int, s: SampleSettings
    ) -> list[dict[str, Any]]:
        from tinker_cookbook.renderers import get_text_content

        prompt = self.renderer.build_generation_prompt(messages)
        params = self._types.SamplingParams(
            max_tokens=s.max_tokens,
            temperature=s.temperature,
            top_p=s.top_p,
            seed=s.seed,
            stop=self.renderer.get_stop_sequences(),
        )
        res = await self.client.sample_async(prompt=prompt, num_samples=n, sampling_params=params)
        out: list[dict[str, Any]] = []
        for seq in res.sequences:
            message, _ = self.renderer.parse_response(seq.tokens)
            out.append(
                {
                    "text": get_text_content(message),
                    "prompt_tokens": prompt.length,
                    "completion_tokens": len(seq.tokens),
                    "stop_reason": str(seq.stop_reason),
                }
            )
        return out
