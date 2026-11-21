# gemini-tts-batch

日本語 | [English](README.en.md)

構造化されたJSON台本から、Gemini TTSを使ってシーン別のWAVファイルを一括生成するツールです。

小規模なアニメ・動画制作を想定しています。台本と音声設定はGitで管理し、生成された音声はGoogle Drive Desktopの同期フォルダなど、リポジトリ外へ保存できます。

## できること

- APIを呼ぶ前に、エピソードと音声設定のJSONを検証
- シーンごとに出力フォルダを作成
- ライン・話者ごとに1つのWAVファイルを生成
- 通常はドライランで動作し、`--execute`を付けた場合だけAPIを実行
- 生成条件を`manifest.json`に記録し、変更がない音声をスキップ
- シーン、ライン、話者を指定した部分生成

## 出力形式

シーンIDが`s01`、ラインIDが`l001`、話者IDが`boss`の場合、次の規則でファイル名を生成します。

```text
{出力ルート}/{エピソードの出力先}/{シーンID}/{ラインID}_{話者ID}.wav
```

出力例：

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

出力ルートには任意のローカルフォルダを指定できます。Google Driveへ保存する場合は、Google Drive Desktopの同期フォルダを指定します。Google Drive APIの認証情報は必要ありません。

出力ルートは実行前に作成しておく必要があります。これにより、Google Driveがマウントされていないときに、同名の通常フォルダを誤って作成することを防ぎます。

## インストール

Python 3.11以上が必要です。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

環境変数のテンプレートをコピーし、自分の環境に合わせて設定します。

```bash
cp .env.example .env
```

```dotenv
GEMINI_API_KEY=your-api-key
GEMINI_TTS_OUTPUT_ROOT=/absolute/path/to/your/output/root
```

`.env`はGitへコミットしないでください。

## クイックスタート

まず、Gemini APIを呼ばずに生成予定のファイルを確認します。

```bash
gemini-tts-batch render examples/episode.json --voices examples/voices.json
```

問題がなければ、`--execute`を付けてWAVファイルを生成します。

```bash
gemini-tts-batch render examples/episode.json \
  --voices examples/voices.json \
  --execute
```

一度だけ別の出力ルートを使う場合は、コマンドで上書きできます。

```bash
gemini-tts-batch render examples/episode.json \
  --voices examples/voices.json \
  --output-root /tmp/gemini-tts-output \
  --execute
```

シーン、話者、ラインを限定して生成することもできます。

```bash
gemini-tts-batch render episode.json --voices voices.json --scene s03 --execute
gemini-tts-batch render episode.json --voices voices.json --speaker chappy --execute
gemini-tts-batch render episode.json --voices voices.json --line s03:l002 --execute
```

入力内容が変わっていない音声をあえて再生成する場合は、`--force`を付けます。

## エピソードJSON

エピソードJSONを、シーンと台詞の正本として扱います。

```json
{
  "schema_version": 1,
  "id": "ep001",
  "title": "サンプルエピソード",
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
      "title": "オープニング",
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

IDには半角英小文字、数字、`_`、`-`を使用できます。シーンIDはエピソード内で一意、ラインIDはシーン内で一意にします。台詞の順番を変更した場合も、既存のラインIDは原則として変更しません。

完全な形式は[`schemas/episode.schema.json`](schemas/episode.schema.json)で定義しています。

## 音声設定JSON

音声設定は台本と分離し、複数のエピソードから同じキャラクター設定を再利用できます。

```json
{
  "schema_version": 1,
  "characters": {
    "boss": {
      "display_name": "ボス",
      "voice": "Brio",
      "base_style": "普段は余裕があるが、興味が湧くとテンションが上がる中年男性"
    }
  }
}
```

ライン側の`voice`で音声を一時的に上書きできます。`direction`を指定した場合は、キャラクターの`base_style`にライン固有の演技指示を追加して生成します。

完全な形式は[`schemas/voices.schema.json`](schemas/voices.schema.json)で定義しています。

## manifestと差分生成

`manifest.json`には、正常に生成された各ラインのモデル、音声、台詞、演技指示、出力ファイル名、入力内容のフィンガープリントを記録します。

対象のWAVファイルが存在し、フィンガープリントも変わっていない場合、そのラインはスキップされます。台詞、音声、演技指示、モデルのいずれかを変更すると、同じ安定したファイル名でWAVを再生成します。

入力を変更せず別テイクを作りたい場合は、`--force`を使用します。

## 安全のための初期設定

- 通常はドライランで動作
- `--execute`を指定した場合だけAPIを実行
- `output.relative_dir`の絶対パスと`..`を拒否
- 生成途中のデータは一時ファイルへ書き、完了後にWAVへ置き換え
- APIキーは環境変数から読み込み、manifestには記録しない
- 既存の出力ファイルを自動削除しない

## ライセンス

[MIT License](LICENSE)で公開しています。

