"""Instruction mutation engine using Gemini CLI."""

from __future__ import annotations

import random

from .cli_runner import run_gemini_cli


MUTATION_STRATEGIES = [
    "clarity",
    "restructure",
    "condense",
    "expand_edge_cases",
    "add_examples",
    "reorder_priority",
    "sharpen_constraints",
]

MUTATE_PROMPT = """\
You are an expert at optimizing AI agent system instructions.

Your task: Apply the "{strategy}" mutation strategy to improve these instructions.

Strategy descriptions:
- clarity: Rewrite ambiguous sections for precision. Remove jargon that doesn't add value.
- restructure: Reorganize sections for better logical flow. Group related rules.
- condense: Remove redundancy and verbosity while preserving all meaning.
- expand_edge_cases: Add handling for edge cases the instructions currently miss.
- add_examples: Add concrete examples where abstract rules exist.
- reorder_priority: Move the most important rules earlier. Front-load critical behavior.
- sharpen_constraints: Make vague rules ("try to...", "generally...") into clear directives.

Context from evaluation:
{feedback}

Current instructions:
---
{instructions}
---

Rules:
1. Preserve the core identity and purpose — improve, don't rewrite from scratch
2. Keep the same format (markdown with frontmatter if present)
3. Do NOT add meta-commentary about your changes
4. Output ONLY the improved instructions, nothing else
"""

CROSSOVER_PROMPT = """\
You are combining the best parts of two instruction variants.

Variant A (score: {score_a:.2f}):
---
{variant_a}
---

Variant B (score: {score_b:.2f}):
---
{variant_b}
---

Combine the strongest sections from each variant into a single improved version.
Resolve any conflicts by preferring the approach from the higher-scoring variant.
Output ONLY the combined instructions.
"""


class Mutator:
    """Generates instruction variants through Gemini CLI."""

    def __init__(self, model: str | None = None, *, no_mcp: bool = False):
        self.model = model
        self.no_mcp = no_mcp

    def mutate(
        self,
        instructions: str,
        strategy: str | None = None,
        feedback: str = "",
        temperature: float = 0.9,
    ) -> str:
        if strategy is None:
            strategy = random.choice(MUTATION_STRATEGIES)

        prompt = MUTATE_PROMPT.format(
            strategy=strategy,
            feedback=feedback or "No specific feedback yet.",
            instructions=instructions,
        )
        result = run_gemini_cli(
            prompt=prompt,
            model=self.model,
            timeout_seconds=300,
            no_mcp=self.no_mcp,
        )
        return result.response if result.ok else ""

    def crossover(
        self,
        variant_a: str,
        score_a: float,
        variant_b: str,
        score_b: float,
    ) -> str:
        prompt = CROSSOVER_PROMPT.format(
            score_a=score_a,
            variant_a=variant_a,
            score_b=score_b,
            variant_b=variant_b,
        )
        result = run_gemini_cli(
            prompt=prompt,
            model=self.model,
            timeout_seconds=300,
            no_mcp=self.no_mcp,
        )
        return result.response if result.ok else ""

    def generate_population(
        self,
        instructions: str,
        size: int = 4,
        feedback: str = "",
        temperature: float = 0.9,
    ) -> list[str]:
        """Generate a diverse population of mutated variants (parallel CLI calls)."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        strategies = random.sample(
            MUTATION_STRATEGIES, min(size, len(MUTATION_STRATEGIES))
        )
        while len(strategies) < size:
            strategies.append(random.choice(MUTATION_STRATEGIES))

        variants = []
        with ThreadPoolExecutor(max_workers=min(size, 4)) as pool:
            futures = {
                pool.submit(
                    self.mutate, instructions,
                    strategy=s, feedback=feedback, temperature=temperature,
                ): s
                for s in strategies
            }
            for future in as_completed(futures):
                variant = future.result()
                if variant and variant != instructions:
                    variants.append(variant)
        return variants
