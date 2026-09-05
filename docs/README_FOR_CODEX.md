# Listening Studio — Codex Handoff

このフォルダは、英語リスニング教材生成ソフト **Listening Studio** を実装するための開発引き継ぎ一式です。

## まず読む順番

1. `SPEC.md`
2. `API.md`
3. `SCHEMA.sql`
4. `TASKS.md`
5. `.env.example`

## Codexへの最初の指示

以下をそのまま渡してよい。

> このリポジトリに Listening Studio を実装してください。
> `SPEC.md` を唯一のプロダクト要件の基準とし、`API.md` と `SCHEMA.sql` に従ってください。
> まず `TASKS.md` の Phase 0 → Phase 1 を完了し、MVPを動作可能にしてください。
> TTSプロバイダ固有ロジックは必ず adapter 層に閉じ込め、UIやdomain層からOpenAI/Azure/ElevenLabsのSDKを直接呼ばないでください。
> 不明点があっても、SPECに反しない範囲で合理的なデフォルトを採用し、実装を止めないでください。
> 変更ごとにテストを追加し、READMEにローカル起動手順を記載してください。

## 推奨技術

- Frontend: Next.js + TypeScript
- Backend: FastAPI + Python
- DB: PostgreSQL
- Audio processing: FFmpeg
- Object storage: S3-compatible storage / Cloudflare R2
- TTS: provider adapter pattern
  - OpenAI
  - Azure AI Speech
  - ElevenLabs

## プロダクトの一文定義

英文を貼り付け、声・アクセント・話速・話者を指定すると、自然な英語音声を生成し、
会話・試験音源・反復練習まで一つの画面で扱えるリスニング教材制作環境。

## MVPの完成条件

- 1人読み上げ
- 複数話者会話
- 声選択
- Accent / GenderによるVoice絞り込み
- Speed指定
- MP3生成
- Transcript表示/非表示
- A-B repeat
- Project保存
- OpenAI TTS adapter 1つが実際に動作
- Azure / ElevenLabs adapterのinterfaceとstubが存在
