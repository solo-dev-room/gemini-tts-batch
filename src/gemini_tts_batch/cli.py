from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jsonschema import Draft202012Validator

DEFAULT_MODEL = "gemini-3.8-flash-tts"
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class RenderTask:
    scene_id: str
    line_id: str
    speaker_id: str
    text: str
    style: str
    voice: str
    model: str
    language_code: str | None
    output_file: Path
    fingerprint: str

    @property
    def key(self) -> str:
        return f"{self.scene_id}:{self.line_id}"


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"The root value must be an object: {path}")
    return data


def load_schema(name: str) -> dict[str, Any]:
    resource = files("gemini_tts_batch").joinpath("schemas", name)
    if resource.is_file():
        with as_file(resource) as path:
            return load_json(path)
    source_schema = Path(__file__).resolve().parents[2] / "schemas" / name
    return load_json(source_schema)


def validate_schema(data: dict[str, Any], schema_name: str, label: str) -> None:
    validator = Draft202012Validator(load_schema(schema_name))
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    if not errors:
        return
    details = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        details.append(f"  - {location}: {error.message}")
    raise ValueError(f"{label} validation failed:\n" + "\n".join(details))


def validate_unique_ids(episode: dict[str, Any]) -> None:
    scene_ids: set[str] = set()
    for scene in episode["scenes"]:
        scene_id = scene["id"]
        if scene_id in scene_ids:
            raise ValueError(f"Duplicate scene ID: {scene_id}")
        scene_ids.add(scene_id)

        line_ids: set[str] = set()
        for line in scene["lines"]:
            line_id = line["id"]
            if line_id in line_ids:
                raise ValueError(f"Duplicate line ID in {scene_id}: {line_id}")
            line_ids.add(line_id)


def resolve_output_dir(output_root: Path, relative_dir: str) -> Path:
    relative_path = Path(relative_dir)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("output.relative_dir must be a safe relative path without '..'")

    root = output_root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Output root does not exist or is not mounted: {root}")
    output_dir = (root / relative_path).resolve()
    try:
        output_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("Resolved output directory escapes the output root") from exc
    return output_dir


def combine_style(base_style: str | None, direction: str | None) -> str:
    return "。".join(value.strip() for value in (base_style, direction) if value and value.strip())


def fingerprint_for(*, model: str, voice: str, style: str, text: str) -> str:
    payload = json.dumps(
        {"model": model, "voice": voice, "style": style, "text": text},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_tasks(
    episode: dict[str, Any],
    voices: dict[str, Any],
    output_dir: Path,
    *,
    scenes: set[str],
    lines: set[str],
    speakers: set[str],
    model_override: str | None,
) -> list[RenderTask]:
    characters = voices["characters"]
    tts = episode.get("tts", {})
    model = model_override or tts.get("model") or DEFAULT_MODEL
    language_code = tts.get("language_code")
    tasks: list[RenderTask] = []

    for scene in episode["scenes"]:
        scene_id = scene["id"]
        if scenes and scene_id not in scenes:
            continue
        for line in scene["lines"]:
            line_id = line["id"]
            speaker_id = line["speaker"]
            qualified_line_id = f"{scene_id}:{line_id}"
            if lines and qualified_line_id not in lines:
                continue
            if speakers and speaker_id not in speakers:
                continue
            if speaker_id not in characters:
                raise ValueError(f"Unknown speaker '{speaker_id}' in {qualified_line_id}")

            character = characters[speaker_id]
            voice = line.get("voice") or character["voice"]
            style = combine_style(character.get("base_style"), line.get("direction"))
            text = line["text"]
            output_file = output_dir / scene_id / f"{line_id}_{speaker_id}.wav"
            tasks.append(
                RenderTask(
                    scene_id=scene_id,
                    line_id=line_id,
                    speaker_id=speaker_id,
                    text=text,
                    style=style,
                    voice=voice,
                    model=model,
                    language_code=language_code,
                    output_file=output_file,
                    fingerprint=fingerprint_for(model=model, voice=voice, style=style, text=text),
                )
            )

    return tasks


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "lines": {}}
    data = load_json(path)
    if data.get("schema_version") != 1 or not isinstance(data.get("lines"), dict):
        raise ValueError(f"Unsupported manifest format: {path}")
    return data


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def generate_audio(task: RenderTask, api_key: str) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    part = types.Part(
        text=task.text,
        speech_metadata=types.SpeechMetadata(style=task.style) if task.style else None,
    )

    speech_config_args: dict[str, Any] = {
        "voice_config": types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=task.voice)
        )
    }
    if task.language_code:
        speech_config_args["language_code"] = task.language_code

    response = client.models.generate_content(
        model=task.model,
        contents=[types.Content(role="user", parts=[part])],
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(**speech_config_args),
        ),
    )
    for response_part in response.parts or []:
        if response_part.inline_data and response_part.inline_data.data:
            return response_part.inline_data.data
    raise RuntimeError("Gemini returned no audio data")


def render(args: argparse.Namespace) -> int:
    load_dotenv()
    if args.retries < 1:
        raise ValueError("--retries must be at least 1")
    if args.delay < 0:
        raise ValueError("--delay must be zero or greater")
    episode_path = Path(args.episode)
    voices_path = Path(args.voices)
    episode = load_json(episode_path)
    voices = load_json(voices_path)
    validate_schema(episode, "episode.schema.json", "Episode")
    validate_schema(voices, "voices.schema.json", "Voices")
    validate_unique_ids(episode)

    configured_root = args.output_root or os.environ.get("GEMINI_TTS_OUTPUT_ROOT")
    if not configured_root:
        raise ValueError("Set --output-root or GEMINI_TTS_OUTPUT_ROOT")
    output_dir = resolve_output_dir(Path(configured_root), episode["output"]["relative_dir"])

    tasks = build_tasks(
        episode,
        voices,
        output_dir,
        scenes=set(args.scene),
        lines=set(args.line),
        speakers=set(args.speaker),
        model_override=args.model,
    )
    if not tasks:
        raise ValueError("No lines matched the selected filters")

    manifest_path = output_dir / MANIFEST_NAME
    manifest = load_manifest(manifest_path)
    manifest["episode_id"] = episode["id"]
    manifest_lines = manifest["lines"]

    mode = "EXECUTE" if args.execute else "DRY RUN"
    print(f"[{mode}] episode={episode['id']} lines={len(tasks)}")
    print(f"Output: {output_dir}")

    pending: list[RenderTask] = []
    for task in tasks:
        previous = manifest_lines.get(task.key, {})
        unchanged = task.output_file.exists() and previous.get("fingerprint") == task.fingerprint
        if unchanged and not args.force:
            print(f"[SKIP unchanged] {task.output_file}")
        else:
            pending.append(task)
            print(f"[GENERATE] {task.key} {task.speaker_id} -> {task.output_file}")

    if not args.execute:
        print(f"Dry run complete: {len(pending)} to generate, {len(tasks) - len(pending)} unchanged")
        return 0

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is required with --execute")

    generated = 0
    for index, task in enumerate(pending, start=1):
        task.output_file.parent.mkdir(parents=True, exist_ok=True)
        print(f"[{index}/{len(pending)}] Generating {task.key} with voice={task.voice}")
        last_error: Exception | None = None
        for attempt in range(1, args.retries + 1):
            try:
                audio = generate_audio(task, api_key)
                temporary = task.output_file.with_suffix(task.output_file.suffix + ".part")
                temporary.write_bytes(audio)
                temporary.replace(task.output_file)
                last_error = None
                break
            except Exception as exc:  # API failures are reported after bounded retries.
                last_error = exc
                if attempt < args.retries:
                    wait_seconds = min(2 ** (attempt - 1), 8)
                    print(f"  Attempt {attempt} failed; retrying in {wait_seconds}s: {exc}", file=sys.stderr)
                    time.sleep(wait_seconds)
        if last_error is not None:
            raise RuntimeError(f"Failed to generate {task.key}: {last_error}") from last_error

        manifest_lines[task.key] = {
            "scene_id": task.scene_id,
            "line_id": task.line_id,
            "speaker": task.speaker_id,
            "text": task.text,
            "style": task.style,
            "voice": task.voice,
            "model": task.model,
            "file": task.output_file.relative_to(output_dir).as_posix(),
            "fingerprint": task.fingerprint,
        }
        save_manifest(manifest_path, manifest)
        generated += 1
        if index < len(pending) and args.delay > 0:
            time.sleep(args.delay)

    print(f"Complete: generated={generated}, unchanged={len(tasks) - len(pending)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gemini-tts-batch")
    subparsers = parser.add_subparsers(dest="command", required=True)
    render_parser = subparsers.add_parser("render", help="Generate per-line WAV files")
    render_parser.add_argument("episode", help="Path to episode JSON")
    render_parser.add_argument("--voices", required=True, help="Path to voices JSON")
    render_parser.add_argument("--output-root", help="Local output root (or GEMINI_TTS_OUTPUT_ROOT)")
    render_parser.add_argument("--model", help="Override the model configured by the episode")
    render_parser.add_argument("--scene", action="append", default=[], help="Only render a scene ID")
    render_parser.add_argument(
        "--line", action="append", default=[], metavar="SCENE:LINE", help="Only render a qualified line ID"
    )
    render_parser.add_argument("--speaker", action="append", default=[], help="Only render a speaker ID")
    render_parser.add_argument("--execute", action="store_true", help="Call Gemini and write audio")
    render_parser.add_argument("--force", action="store_true", help="Regenerate unchanged lines")
    render_parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests")
    render_parser.add_argument("--retries", type=int, default=3, help="Maximum attempts per line")
    render_parser.set_defaults(handler=render)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

