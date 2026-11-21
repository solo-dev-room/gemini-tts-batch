# gemini-tts-batch

[日本語](README.md) | English

Generate scene-organized WAV files from a structured JSON script using Gemini TTS.

This tool is designed for small animation and video projects where scripts are versioned in Git while generated audio is stored outside the repository, such as in a Google Drive Desktop sync folder.

## What it does

- Validates episode and voice configuration JSON before making API calls.
- Creates one directory per scene.
- Creates one WAV file per line and speaker.
- Runs as a dry run by default, so API calls require an explicit `--execute`.
- Writes a manifest beside the generated audio for reproducible incremental runs.
- Supports filtering by scene, line, or speaker.

## Output layout

Given scene `s01`, line `l001`, and speaker `boss`, the output filename is generated as follows:

```text
{output root}/{episode output directory}/{scene id}/{line id}_{speaker id}.wav
```

Example:

```text
output/
└── EP001/02_Audio_WAV/
    ├── s01/
    │   ├── l001_boss.wav
    │   └── l002_chappy.wav
    ├── s02/
    │   └── l001_boss.wav
    └── manifest.json
```

The output root may be any local directory. To save into Google Drive, point it at a Google Drive Desktop sync folder; this tool does not require Drive API credentials.

The output root must already exist. This prevents an unavailable or unmounted sync folder from being silently recreated as an ordinary local directory.

## Installation

Requires Python 3.11 or later.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

Copy the environment template and set your local values:

```bash
cp .env.example .env
```

```dotenv
GEMINI_API_KEY=your-api-key
GEMINI_TTS_OUTPUT_ROOT=/absolute/path/to/your/output/root
```

Never commit `.env`.

## Quick start

Preview the files that would be generated without calling Gemini:

```bash
gemini-tts-batch render examples/episode.json --voices examples/voices.json
```

Generate the WAV files:

```bash
gemini-tts-batch render examples/episode.json \
  --voices examples/voices.json \
  --execute
```

Override the configured output root for a single run:

```bash
gemini-tts-batch render examples/episode.json \
  --voices examples/voices.json \
  --output-root /tmp/gemini-tts-output \
  --execute
```

Generate only selected content:

```bash
gemini-tts-batch render episode.json --voices voices.json --scene s03 --execute
gemini-tts-batch render episode.json --voices voices.json --speaker chappy --execute
gemini-tts-batch render episode.json --voices voices.json --line s03:l002 --execute
```

Use `--force` to regenerate files even when the manifest reports that the inputs have not changed.

## Episode JSON

The episode file is the source of truth for scenes and spoken lines.

```json
{
  "schema_version": 1,
  "id": "ep001",
  "title": "Example episode",
  "output": {
    "relative_dir": "EP001/02_Audio_WAV"
  },
  "tts": {
    "model": "gemini-3.8-flash-tts",
    "language_code": "ja-JP"
  },
  "scenes": [
    {
      "id": "s01",
      "title": "Opening",
      "lines": [
        {
          "id": "l001",
          "speaker": "boss",
          "text": "暇だなぁ……",
          "direction": "ぼやくように"
        }
      ]
    }
  ]
}
```

IDs must use lowercase ASCII letters, numbers, `_`, or `-`. Scene IDs must be unique within an episode. Line IDs must be unique within a scene and should remain stable even if lines are reordered.

The complete contract is defined in [`schemas/episode.schema.json`](schemas/episode.schema.json).

## Voices JSON

Voice settings are kept separately so multiple episodes can reuse the same cast.

```json
{
  "schema_version": 1,
  "characters": {
    "boss": {
      "display_name": "Boss",
      "voice": "Brio",
      "base_style": "A relaxed middle-aged man who becomes animated when excited"
    }
  }
}
```

A line may override `voice` or add a `direction`. The effective delivery style is the character's `base_style` followed by the line's `direction`.

The complete contract is defined in [`schemas/voices.schema.json`](schemas/voices.schema.json).

## Manifest and incremental generation

`manifest.json` records the model, voice, text, delivery style, output filename, and an input fingerprint for every successfully generated line.

If the target WAV exists and its fingerprint has not changed, the line is skipped. Changing the text, voice, style, or model generates a new WAV at the same stable filename. Use `--force` when you intentionally want a new take without changing those inputs.

## Safety defaults

- Dry run is the default.
- API calls only occur with `--execute`.
- Absolute paths and `..` are rejected in `output.relative_dir`.
- Partial responses are written to a temporary file before replacing the final WAV.
- API keys are read from the environment and never written to the manifest.
- Existing output files are never deleted automatically.

## License

Licensed under the [MIT License](LICENSE).

