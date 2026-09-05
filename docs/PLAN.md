# Listening Studio — 実装計画

作成日: 2026-09-05
基準文書: `docs/SPEC.md`（唯一のプロダクト要件基準）、`docs/API.md`、`docs/SCHEMA.sql`、`docs/TASKS.md`

---

## 0. 確定した前提

| 項目 | 決定 | 理由 |
|---|---|---|
| リポジトリ | `~/Desktop/ListeningStudio` | ユーザー指定 |
| DB | Homebrew PostgreSQL | `SCHEMA.sql` が JSONB / `gen_random_uuid()` / UUID 型に依存。dev と prod を一致させる |
| TTS | **ローカル・ニューラルTTS（Kokoro-82M）** | APIキー不要・無料・オフライン・無制限。SPEC のアクセントモデルに適合 |
| 実行環境 | Apple M1 / 8GB RAM / macOS | **実測で RTF 0.22–0.24 を確認。実用範囲内** |

### 既に確認済みのローカル環境

- Python 3.12.3 / Node v23.11.0 / FFmpeg 8.0 / git / Homebrew — すべて利用可
- PostgreSQL 16.15 — **導入・起動済み**。`listening` ロール / `listening_studio` DB / `pgcrypto` 拡張 まで検証済み
- espeak-ng 1.52.0 / Kokoro 0.9.4 / PyTorch 2.14.0 — **導入・合成検証済み**
- Docker — 未インストール（不要）

---

## 1. 技術スタック

### Backend

| 層 | 採用 |
|---|---|
| Web | FastAPI + Uvicorn |
| ORM / Migration | SQLAlchemy 2.0（async）+ Alembic |
| DB Driver | psycopg 3 |
| Validation | Pydantic v2 / pydantic-settings |
| TTS（実動作） | Kokoro-82M（PyTorch, CPU）+ misaki/espeak-ng |
| Audio | FFmpeg / ffprobe をサブプロセス実行 |
| Storage | ローカルFS アダプタ（S3/R2 は同一インターフェースで後付け） |
| Test | pytest + pytest-asyncio + httpx ASGITransport |
| Lint | ruff（lint + format）+ mypy |

### Frontend

| 層 | 採用 |
|---|---|
| Framework | Next.js（App Router）+ TypeScript |
| Server state | TanStack Query |
| Style | Tailwind CSS |
| Test | Playwright（E2E）|
| Lint | ESLint + Prettier |

**Redux は入れない**（SPEC §19 の指示に従う）。

---

## 2. SPEC からの逸脱（明示）

SPEC の MVP 受け入れ条件「OpenAI TTS adapter 1つが実際に動作」は、APIを使わない方針により**そのままでは満たさない**。
以下の形で逸脱を最小化する。

| SPEC の要求 | 本実装 | 判断 |
|---|---|---|
| 実動作する adapter が1つ以上 | `KokoroAdapter` が実動作 | 趣旨を満たす |
| OpenAI adapter | **stub ではなく完全実装**。`OPENAI_API_KEY` 未設定時のみ無効化 | キー投入だけでコード変更ゼロで有効化 |
| Azure adapter | interface + stub（SPEC通り） | SPEC通り |
| ElevenLabs adapter | interface + stub（SPEC通り） | SPEC通り |

この逸脱は `README.md` と本計画書に記録し、隠さない。

---

## 3. `SCHEMA.sql` に必要な変更

引き継ぎ時点の `SCHEMA.sql` には、SPEC/API.md の要求を満たすのに不足がある。
初回 Alembic migration で以下を反映する。

### 3.1 provider の CHECK 制約にローカルプロバイダを追加（必須）

```sql
-- 現状: CHECK (provider IN ('openai', 'azure', 'elevenlabs'))
-- 変更: 'kokoro' を追加（MacSayAdapter 併設なら 'macos_say' も）
```

Kokoro を使う以上これは必須。

### 3.2 projects に「プロジェクト既定」の列を追加（必須）

SPEC §13 の effective voice / speed 解決は 3 段階:

```
segment override → speaker → project default
```

しかし現行スキーマの `projects` に project default が存在しない。追加する。

```sql
ALTER TABLE projects
  ADD COLUMN default_voice_id UUID REFERENCES voices(id),
  ADD COLUMN default_generation_speed NUMERIC(6,3) NOT NULL DEFAULT 1.0,
  ADD COLUMN sentence_pause_ms INTEGER NOT NULL DEFAULT 250,
  ADD COLUMN paragraph_pause_ms INTEGER NOT NULL DEFAULT 600;
```

pause の既定値は SPEC §28 の推奨デフォルトに一致させる。

### 3.3 Idempotency-Key の保存先を追加（必須）

API.md は render に `Idempotency-Key` を要求するが、`render_jobs` に該当列がない。

```sql
ALTER TABLE render_jobs ADD COLUMN idempotency_key TEXT;
CREATE UNIQUE INDEX idx_render_jobs_idem
  ON render_jobs(project_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
```

### 3.4 tts_cache に instructions を含める（要検討）

SPEC §14 のキャッシュキー定義には `instructions` が含まれるが、`tts_cache` テーブルに列がない。
`cache_key` 自体は instructions を含めて計算されるため機能上は問題ないが、
デバッグ可能性のため `instructions_hash TEXT` を追加する。

---

## 4. ディレクトリ構成

SPEC §18 / §19 に従う。

```
ListeningStudio/
  docker-compose.yml        # Postgres 用。Docker 未使用でも将来のため用意
  README.md
  .env.example
  docs/                     # 引き継ぎ文書一式 + 本計画書

  backend/
    pyproject.toml
    alembic.ini
    alembic/versions/
    app/
      main.py
      config.py
      api/routes/           # projects / voices / segments / renders / health
      domain/               # models / services / errors.py
      application/          # project_service / render_service / voice_service
      infrastructure/
        db/
        storage/            # local_storage.py（+ 将来 s3_storage.py）
        audio/              # ffmpeg_wrapper.py
        tts/
          base.py           # TTSRequest / TTSResult / TTSProvider
          registry.py
          kokoro_adapter.py     # ★実動作
          openai_adapter.py     # 完全実装（キー未設定時は無効）
          azure_adapter.py      # stub
          elevenlabs_adapter.py # stub
      schemas/
    tests/

  frontend/
    app/                    # / , /create , /projects/[id] , /voices
    components/
      script/  voice/  player/  timeline/
    lib/api/  lib/audio/  lib/types/
    hooks/
    e2e/                    # Playwright
```

### 層の分離を自動検査する

SPEC §26 の受け入れ条件「provider SDK が React / domain 層から import されていないこと」を、
**目視ではなくテストで担保する**。

`backend/tests/test_layering.py` で、`app/infrastructure/tts/` 以外のファイルが
`kokoro` / `openai` / `torch` / `azure` / `elevenlabs` を import していないことを AST で検査する。
frontend も同様に ESLint の `no-restricted-imports` で禁止する。

---

## 5. Kokoro アダプタの設計上の要点（実機検証済み）

### 5.1 検証で判明した事実

**利用可能な英語 voice は 28 個**（全54個中。他はスペイン語/フランス語/ヒンディー語/イタリア語/日本語/ポルトガル語/中国語）。

| プレフィックス | 意味 | 個数 | voice |
|---|---|---|---|
| `af_` | American Female | 11 | alloy, aoede, bella, heart, jessica, kore, nicole, nova, river, sarah, sky |
| `am_` | American Male | 9 | adam, echo, eric, fenrir, liam, michael, onyx, puck, santa |
| `bf_` | British Female | 4 | alice, emma, isabella, lily |
| `bm_` | British Male | 4 | daniel, fable, george, lewis |

命名規則から **accent と gender が確実に導出できる**（1文字目 a/b = American/British、2文字目 f/m = female/male）。
API.md の「metadata を捏造するな」に抵触しない、正当な導出である。

### 5.2 espeak-ng のパス問題（解決済み・実装必須）

`kokoro` が依存する `espeakng-loader` 0.2.4 の同梱 dylib には、
**ビルドマシンのパス（`/Users/runner/work/...`）が焼き込まれており、そのままでは合成が失敗する**。

```
Error processing file '/Users/runner/work/espeakng-loader/.../phontab': No such file or directory
```

`phonemizer` の `EspeakWrapper.set_data_path()` はクラス属性を書くだけで、この焼き込みを上書きできない。

**解決策（検証済み）**: Homebrew 版の dylib を使う。環境変数で指定する。

```bash
PHONEMIZER_ESPEAK_LIBRARY=/opt/homebrew/lib/libespeak-ng.dylib
ESPEAK_DATA_PATH=/opt/homebrew/share/espeak-ng-data
```

→ `EspeakBackend('en-us').phonemize(['hello world'])` が `həloʊ wɜːld` を返すことを確認済み。

**実装への反映**: この2つを `.env.example` と `config.py` に含め、
未設定時は OS ごとの既定パスを自動探索する。README の環境構築手順にも `brew install espeak-ng` を明記する。

### 5.3 アダプタ実装の要点

1. **モデルロードはプロセス起動時に1回だけ**。リクエストごとにロードすると数秒かかる
2. **同期・CPUバウンドなので必ずスレッドプールへ逃がす** — `await anyio.to_thread.run_sync(...)`
3. **`KPipeline` は lang_code ごとにインスタンスが必要** — `'a'`(American) と `'b'`(British) の2つを保持する
4. **speed は Kokoro の合成時パラメータ** — `generation_speed` にそのまま対応づく
5. **出力は 24kHz の生波形** → soundfile で WAV → FFmpeg で MP3
6. **capability 宣言**（`supports_speed`, `supports_instructions`, `speed_range`）を持たせ、
   speed 非対応プロバイダが将来入っても FFmpeg `atempo` フォールバックで吸収できるようにする

---

### 5.4 性能実測値（Apple M1 / 8GB）

同一英文（15語）で計測。RTF = 生成時間 ÷ 音声長（小さいほど速い）。

| voice | speed | 生成時間 | 音声長 | RTF | 実測WPM |
|---|---|---|---|---|---|
| af_heart | 1.00 | 4.27s ※初回 | 7.12s | 0.60 | 126 |
| af_heart | 1.25 | **1.30s** | 5.97s | **0.22** | 151 |
| bm_george | 1.00 | 3.76s ※初回 | 7.80s | 0.48 | 115 |
| bm_george | 1.25 | **1.53s** | 6.47s | **0.24** | 139 |

**結論: 定常状態の RTF ≈ 0.22–0.24。実時間の約4倍速で生成できる。**
5分の音源なら約1分強。教材制作用途として十分に実用的。

初回のみモデルの遅延初期化で 3–4 秒余分にかかるため、**アプリ起動時にウォームアップ合成を1回走らせる**設計にする。

`KPipeline` のロードは American 5.7s / British 2.6s。**プロセス起動時に一度だけ**行う（リクエスト毎は不可）。

speed パラメータが音声長に正しく反映されることも確認済み（1.0→1.25 で 7.12s→5.97s）。

追加依存: spaCy の `en_core_web_sm`（12.8MB）が初回に暗黙ダウンロードされる。
これに依存させず、**依存として明示的に固定する**。

---

### 5.5 アクセント網羅の問題と対策（要判断）

**Kokoro の英語アクセントは American / British の2種類しかない。**

SPEC §9 の MVP UI は `American / British / Australian / Canadian / Other` を出すとしており、
受け入れ条件にも「accent で絞り込める」がある。Kokoro 単独では **Australian と Canadian が常に空**になる。

一方 macOS 内蔵 `say` は、検証の結果 **en_GB / en_AU / en_IE / en_IN / en_ZA / en_US** を持つ。

### 提案: `MacSayAdapter` を2つ目の実動作アダプタとして併設する

| プロバイダ | 役割 | アクセント |
|---|---|---|
| `kokoro` | **主**。自然さが必要な本番教材用 | american, british |
| `macos_say` | **補**。アクセント網羅とオフライン即応 | american, british, australian, irish, indian, south_african |

利点:

- accent フィルタが初日から実質的に機能する（受け入れ条件を満たす）
- 実装コストが小さい（`say` はサブプロセス呼び出し。FFmpeg 変換は既存ラッパを再利用）
- **レジストリに実動作プロバイダが2つ並ぶ**ため、SPEC の中核であるアダプタ抽象が机上でなく実証される
- Kokoro が M1 で遅すぎた場合の即時フォールバックにもなる

欠点: `macos_say` は macOS 専用。`provider` の CHECK 制約に追加が必要。

→ **この併設を採用するかは要判断。**

---

## 6. Phase 0 — Repository Bootstrap

完了条件: frontend と backend がローカルで起動する。

- [ ] monorepo ルート / `.gitignore` / `.env.example`
- [ ] `brew install postgresql@16` → `brew services start` → DB・ユーザー作成
- [ ] backend: venv + 依存 + `config.py`（pydantic-settings）
- [ ] backend: FastAPI 起動 + `GET /api/v1/health`
- [ ] Alembic 初期化 + `SCHEMA.sql` + §3 の変更を反映した初回 migration
- [ ] frontend: Next.js + TypeScript + Tailwind 生成
- [ ] frontend: API クライアントの雛形（`/health` を叩いて疎通表示）
- [ ] ruff / mypy / ESLint / Prettier 設定
- [ ] pytest スモークテスト
- [ ] Playwright 設定
- [ ] ルート `README.md`（ローカル起動手順）
- [ ] `docker-compose.yml`（Postgres。将来用）

---

## 7. Phase 1 — MVP Core

### 7.1 Backend（この順で実装）

1. **SQLAlchemy モデル + リポジトリ層**
2. **正規化エラーシステム** — SPEC §21 の全コードを例外クラス化し、
   FastAPI の exception handler で API.md のレスポンス形へ変換。`request_id` ミドルウェア込み。
   ※後回しにすると全エンドポイントに後付けする羽目になるので**先に作る**
3. **Voice Catalog** — Kokoro の voice を seed（accent/gender は id から導出）。
   `GET /voices` に provider / language / locale / accent / gender / enabled / q フィルタ
4. **Project CRUD** — soft delete（`deleted_at`）
5. **Parser**
   - 文分割: 略語（Mr. / Dr. / U.S. / e.g.）・小数・引用符に対応したトークナイザを使用。
     `.split(".")` は SPEC §12 で明確に禁止
   - 会話: `[A]` ブロック形式と `A:` インライン形式の両方
6. **`POST /projects/{id}/parse`** — speakers + segments を返す（永続化はトランザクション内で明示的に）
7. **Speaker CRUD / Segment PATCH** — TTS 影響フィールド変更時に該当 render を無効化
8. **TTS 抽象層** — `TTSRequest` / `TTSResult` / `TTSProvider` / `TTSProviderRegistry`（SPEC §7 準拠）
9. **KokoroAdapter**（実動作）→ OpenAI（完全実装）→ Azure / ElevenLabs（stub）
10. **TTS キャッシュ** — SPEC §14 のキー定義通り
11. **ローカルストレージアダプタ** — SPEC §17 のキー構造
12. **FFmpeg ラッパー** — 無音生成 / 連結 / loudnorm（EBU R128）/ 長さ取得 / フォーマット変換
13. **Render サービス** — effective voice・speed 解決 → segment 描画 → 無音挿入 → 正規化 → 連結
14. **`POST /segments/{id}/render`**（単一セグメント）と
    **`POST /projects/{id}/renders`**（ジョブ化 + ポーリング）。Idempotency-Key 対応

### 7.2 Frontend

1. API クライアント + 型定義（backend の Pydantic schema と対応させる）
2. `/create` — スクリプトエディタ / モード選択 / parse 実行 → セグメント一覧
3. `VoiceSelector` — provider・accent・gender・検索フィルタ（**クライアント側 200ms 未満**: SPEC §25）
4. `SpeakerVoicePanel` — 会話モードで話者ごとに voice / speed / pause
5. Speed スライダ（0.70–1.40: SPEC §10.1）
6. Generate ボタン → ジョブポーリング → 進捗表示
7. `ListeningPlayer` — play/pause/seek/playbackRate/volume/A-Bループ/Transcript表示切替
   **playback rate の変更が保存済み音声を変更しないこと**（SPEC §10.2）
8. `/projects/[id]` — 保存・再オープン・設定の永続化

---

## 8. MVP マージ前のテストゲート（TASKS.md より）

- [ ] parser 単体テスト（文分割・会話パース）
- [ ] TTS リクエストマッピングテスト（domain request → provider request）
- [ ] キャッシュキーのテスト
- [ ] effective voice / speed 解決の単体テスト
- [ ] project API 結合テスト
- [ ] render 結合テスト（**TTS はモック**。CI で実モデルを回さない）
- [ ] E2E: 単読 / 会話 / A-Bリピート
- [ ] **層分離テスト**（§4 参照）
- [ ] frontend バンドルに API シークレットが含まれないことの検査

---

## 9. リスクと対処

| リスク | 影響 | 対処 |
|---|---|---|
| ~~Kokoro が M1/8GB で遅い~~ | — | **解消。実測 RTF 0.22–0.24 で実時間の約4倍速。実用範囲内** |
| 初回のモデル/spaCyダウンロード | 数百MB | 起動時に一度だけ。README に明記し、spaCy モデルは依存として固定 |
| CI で重いモデルを回せない | テストが不安定 | `MockTTSProvider` を用意し、CI は必ずモックを使う |
| loudnorm 2パス処理が遅い | render が長い | セグメント単位ではピーク正規化、最終結合時のみ loudnorm |
| 8GB RAM | メモリ逼迫 | モデルはシングルトン。ワーカープロセスを増やさない |
| espeak-ng のパス問題 | 合成が全く動かない | **解消済**。Homebrew 版 dylib を環境変数で指定（§5.2）|
| Kokoro のアクセントが米英2種のみ | accent フィルタが空振り | `MacSayAdapter` 併設で豪/愛/印/南ア を補う（§5.5・要判断）|
