# 入学高校名プレフィックスBOT

Discordのロール名（高校名）を、メンバーのニックネームの左に自動で付けるBOTです。

例: ロール `〇〇高校` を持つ `たろう` さん → ニックネーム `〇〇高校 たろう`

## 機能

| コマンド / 動作 | 説明 | 権限 |
|---|---|---|
| 自動付与 | 高校ロールが付いた瞬間にニックネームを更新 | 自動 |
| `/syncschool` | サーバー全員に一括適用（既存メンバー向け） | ニックネーム管理 |
| `/setschool` | 自分のニックネームに付け直す | 全員 |
| `/resetschool` | 全員のプレフィックスを一括解除（リカバリー） | ニックネーム管理 |
| `/unsetschool` | 自分のニックネームから高校名を外す | 全員 |
| `/checkperms` | 権限・インテント・ロール順位の自己診断 | 全員 |
| `/history` | 直近の更新履歴（誰がどう変わったか）を表示 | ニックネーム管理 |

### 仕様
- **高校ロールの判定**: ロール名が `高校` または `高等学校` で終わるものを高校ロールとみなす（`bot.py` の `SCHOOL_SUFFIXES` で変更可）
- 複数の高校ロールを持つ場合はロール順位が最上位のものを採用
- 既にプレフィックスが付いている場合は付け直し（重複しない）
- 更新内容は `update.log` とログチャンネル（任意）に記録

## セットアップ

### 1. BOTを作成
1. https://discord.com/developers/applications で New Application
2. 左メニュー **Bot** → Reset Token でトークンを取得
3. **Privileged Gateway Intents** の **SERVER MEMBERS INTENT** を **ON**（必須）

### 2. サーバーに招待
OAuth2 → URL Generator で以下を選択した招待URLを生成して開く:
- Scopes: `bot`, `applications.commands`（両方必須）
- Bot Permissions: `Manage Nicknames`

### 3. ロール順位の設定（重要）
BOTのロールを、付与対象メンバーや高校ロールより**上**に配置してください。
Discordの仕様で、自分より上位のロールを持つメンバーや、サーバーオーナーの
ニックネームはBOTからは変更できません。

### 4. 環境変数
`.env.example` をコピーして `.env` を作り、値を埋めます。

```
DISCORD_TOKEN=BOTのトークン
GUILD_ID=サーバーID        # 任意。設定するとスラッシュコマンドが即時反映（推奨）
LOG_CHANNEL_ID=チャンネルID  # 任意。設定すると更新ログをそのチャンネルへ投稿
```

> サーバーID・チャンネルIDは、Discordの開発者モードをONにして
> 対象を右クリック →「IDをコピー」で取得できます。

### 5. 起動

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python bot.py
```

起動後、サーバーで `/checkperms` で設定を確認し、`/syncschool` で
既存メンバー全員に適用します。

## カスタマイズ
- 区切り文字を変えたい → `bot.py` の `SEPARATOR`（既定は半角スペース）
- 判定語尾を増やしたい → `SCHOOL_SUFFIXES` に追加（例: `"学園"`, `"中等教育学校"`）

## セキュリティ / プライバシー
- `.env`（トークン）と `update.log`（メンバー名・サーバー情報を含む）は
  `.gitignore` で除外済み。**リポジトリにコミットされません。**
- サーバー名・Discordユーザー名・各種IDはコードに一切ハードコードされておらず、
  すべて実行時の環境変数・Discord APIから取得します。
