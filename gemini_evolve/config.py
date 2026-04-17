"""Configuration for gemini-evolve."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvolutionConfig:
    """All knobs for a single evolution run."""

    # Gemini CLI paths
    gemini_home: Path = field(default_factory=lambda: Path.home() / ".gemini")

    # Model selection — all names must be valid CLI `-m` values (API-only
    # ids like `gemini-2.5-pro-preview-05-06` return ModelNotFoundError).
    mutator_model: str = "gemini-3-flash-preview"
    judge_model: str = "gemini-3-pro-preview"
    dataset_model: str = "gemini-3-flash-preview"

    # Evolution parameters
    population_size: int = 4
    generations: int = 5
    mutation_temperature: float = 0.9
    crossover_rate: float = 0.3

    # Constraints
    max_size_kb: float = 15.0
    max_growth_pct: float = 20.0
    min_improvement_pct: float = 2.0

    # Dataset
    dataset_size: int = 10
    train_ratio: float = 0.5
    val_ratio: float = 0.25

    # Output
    output_dir: Path = field(default_factory=lambda: Path("output"))

    @property
    def gemini_instructions_dir(self) -> Path:
        return self.gemini_home

    @property
    def sessions_dir(self) -> Path:
        """Gemini CLI stores session chats under tmp/*/chats/."""
        return self.gemini_home / "tmp"

    @property
    def commands_dir(self) -> Path:
        return self.gemini_home / "commands"

    @property
    def skills_dir(self) -> Path:
        return self.gemini_home / "skills"

    @classmethod
    def from_env(cls) -> EvolutionConfig:
        """Build config from environment variables."""
        kwargs: dict = {}
        if v := os.environ.get("GEMINI_EVOLVE_HOME"):
            kwargs["gemini_home"] = Path(v)
        if v := os.environ.get("GEMINI_EVOLVE_MUTATOR_MODEL"):
            kwargs["mutator_model"] = v
        if v := os.environ.get("GEMINI_EVOLVE_JUDGE_MODEL"):
            kwargs["judge_model"] = v
        if v := os.environ.get("GEMINI_EVOLVE_POPULATION"):
            kwargs["population_size"] = int(v)
        if v := os.environ.get("GEMINI_EVOLVE_GENERATIONS"):
            kwargs["generations"] = int(v)
        if v := os.environ.get("GEMINI_EVOLVE_OUTPUT"):
            kwargs["output_dir"] = Path(v)
        return cls(**kwargs)


# Evolution target types
EVOLUTION_TARGETS = {
    "instructions": {
        "pattern": "GEMINI.md",
        "description": "System instructions (GEMINI.md files)",
        "max_size_kb": 15.0,
    },
    "commands": {
        "pattern": "*.toml",
        "description": "Custom slash commands",
        "max_size_kb": 5.0,
    },
    "skills": {
        "pattern": "*.md",
        "description": "Skill definition files",
        "max_size_kb": 15.0,
    },
}
