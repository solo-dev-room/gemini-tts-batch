from pathlib import Path

import pytest

from gemini_tts_batch.cli import (
    build_tasks,
    combine_style,
    resolve_output_dir,
    validate_unique_ids,
)


def test_output_layout_uses_scene_line_and_speaker(tmp_path: Path) -> None:
    episode = {
        "tts": {"model": "test-model"},
        "scenes": [
            {
                "id": "s01",
                "lines": [
                    {"id": "l001", "speaker": "boss", "text": "Hello", "direction": "Calm"}
                ],
            }
        ],
    }
    voices = {
        "characters": {
            "boss": {"voice": "Brio", "base_style": "Relaxed"},
        }
    }

    tasks = build_tasks(
        episode,
        voices,
        tmp_path,
        scenes=set(),
        lines=set(),
        speakers=set(),
        model_override=None,
    )

    assert tasks[0].output_file == tmp_path / "s01" / "l001_boss.wav"
    assert tasks[0].style == "Relaxed。Calm"


def test_output_directory_rejects_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="safe relative path"):
        resolve_output_dir(tmp_path, "../outside")


def test_duplicate_line_ids_are_rejected() -> None:
    episode = {
        "scenes": [
            {
                "id": "s01",
                "lines": [
                    {"id": "l001"},
                    {"id": "l001"},
                ],
            }
        ]
    }

    with pytest.raises(ValueError, match="Duplicate line ID"):
        validate_unique_ids(episode)


def test_combine_style_omits_empty_values() -> None:
    assert combine_style(" Calm ", "") == "Calm"

