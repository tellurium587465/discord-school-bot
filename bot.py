import os
import logging
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
# 開発サーバーID（任意）。設定するとそのサーバーに即時同期される。
GUILD_ID = os.getenv("GUILD_ID")
# ログを投稿するチャンネルID（任意）。設定するとそのチャンネルへ更新内容を投稿。
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")

# ファイルログ設定（update.log に追記）
JST = timezone(timedelta(hours=9))
logging.basicConfig(
    filename="update.log",
    encoding="utf-8",
    level=logging.INFO,
    format="%(asctime)s %(message)s",
)


async def log_update(guild: discord.Guild, text: str):
    """ファイルとログチャンネルの両方に記録する。"""
    logging.info(text)
    print(text)
    if LOG_CHANNEL_ID:
        ch = guild.get_channel(int(LOG_CHANNEL_ID))
        if ch is not None:
            try:
                await ch.send(text)
            except discord.HTTPException:
                pass

# 高校ロールとみなす条件: ロール名がこれらの語尾で終わるもの
SCHOOL_SUFFIXES = ("高校", "高等学校")

# ニックネームと高校名の区切り文字（例: "〇〇高校 たろう"）
SEPARATOR = " "

intents = discord.Intents.default()
intents.members = True  # メンバー情報・ロール変更の検知に必須

bot = commands.Bot(command_prefix="!", intents=intents)


def get_school_role(member: discord.Member) -> discord.Role | None:
    """メンバーが持つ高校ロールを返す（複数あれば最上位を優先）。"""
    school_roles = [
        r for r in member.roles
        if r.name.endswith(SCHOOL_SUFFIXES)
    ]
    if not school_roles:
        return None
    # ロールの位置が高い（=より上位）ものを採用
    return max(school_roles, key=lambda r: r.position)


def school_prefixes(guild: discord.Guild) -> list[str]:
    """剥がす対象の高校プレフィックス一覧を返す。
    各高校ロールについて「高校名そのもの」と「高校を除いた幹」の両方を対象にする。
    例: ロール『湘南学院高校』→ ['湘南学院高校', '湘南学院'] を剥がせるようにする。
    長いものから順に並べ、誤って短い方を先に剥がさないようにする。
    """
    prefixes: set[str] = set()
    for r in guild.roles:
        if r.name.endswith(SCHOOL_SUFFIXES):
            prefixes.add(r.name)
            for suffix in SCHOOL_SUFFIXES:
                if r.name.endswith(suffix):
                    stem = r.name[: -len(suffix)]
                    if stem:
                        prefixes.add(stem)
    return sorted(prefixes, key=len, reverse=True)


# 高校名プレフィックスの直後に付きがちな区切り・記号（先頭から除去する）
LEADING_STRIP = " 　、，・･_-‐―ー|｜/／:：．.＃#"


def compute_base(member: discord.Member) -> str:
    """ニックネームから先頭の高校プレフィックスを（重複していても全部）取り除いた素の名前を返す。
    幹の直後が区切り文字でなくても剥がす（例: 『湘南学院、Tuwacha』『津久井浜ゆうご』にも対応）。
    """
    base = member.nick or member.name
    prefixes = school_prefixes(member.guild)
    changed = True
    while changed:
        changed = False
        # まず先頭の余分な区切り・記号を除去
        new = base.lstrip(LEADING_STRIP)
        if new != base:
            base = new
            changed = True
        # 先頭一致する高校プレフィックス（長い順）を剥がす
        for p in prefixes:
            if p and base.startswith(p):
                base = base[len(p):]
                changed = True
                break
    return base


def build_nickname(member: discord.Member, school_name: str) -> str | None:
    """高校名を頭に付けたニックネームを生成。既に付いていれば None。"""
    base = compute_base(member)
    new_nick = f"{school_name}{SEPARATOR}{base}" if base else school_name

    # Discordのニックネーム上限は32文字
    if len(new_nick) > 32:
        new_nick = new_nick[:32]

    if new_nick == (member.nick or member.name):
        return None
    return new_nick


def strip_prefix(member: discord.Member) -> str | None:
    """高校名プレフィックスを除いた素のニックネームを返す。付いていなければ None。"""
    current = member.nick or member.name
    base = compute_base(member)
    if base and base != current:
        return base
    return None


async def revert_nickname(member: discord.Member) -> str:
    """高校名プレフィックスを取り除く（リカバリー用）。"""
    if member.bot:
        return "skip(bot)"
    stripped = strip_prefix(member)
    if stripped is None:
        return "unchanged"
    old = member.nick or member.name
    try:
        await member.edit(nick=stripped, reason="高校名プレフィックスを解除")
        await log_update(member.guild, f"↩️ 解除 {member} : 「{old}」→「{stripped}」")
        return f"ok -> {stripped}"
    except discord.Forbidden:
        return "error(forbidden)"
    except discord.HTTPException as e:
        return f"error({e})"


async def apply_nickname(member: discord.Member) -> str:
    """1メンバーにニックネームを適用。結果メッセージを返す。"""
    if member.bot:
        return "skip(bot)"

    role = get_school_role(member)
    if role is None:
        return "skip(no-school-role)"

    new_nick = build_nickname(member, role.name)
    if new_nick is None:
        return "unchanged"

    old = member.nick or member.name
    try:
        await member.edit(nick=new_nick, reason="入学高校名を自動付与")
        await log_update(member.guild, f"✏️ 付与 [{role.name}] {member} : 「{old}」→「{new_nick}」")
        return f"ok -> {new_nick}"
    except discord.Forbidden:
        return "error(forbidden: BOTのロールを対象より上に・権限を確認)"
    except discord.HTTPException as e:
        return f"error({e})"


@bot.event
async def on_ready():
    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"スラッシュコマンド同期(ギルド {GUILD_ID}・即時): {len(synced)}件")
        else:
            synced = await bot.tree.sync()
            print(f"スラッシュコマンド同期(グローバル・最大1時間): {len(synced)}件")
        for c in synced:
            print(f"  - /{c.name}")
    except Exception as e:
        print(f"コマンド同期失敗: {e}")
    print(f"ログイン: {bot.user} (id={bot.user.id})")
    print(f"  SERVER MEMBERS INTENT: {bot.intents.members}")
    for g in bot.guilds:
        perm = g.me.guild_permissions.manage_nicknames
        print(f"  [{g.name}] Manage Nicknames: {perm} / BOT最上位ロール: {g.me.top_role.name}(pos={g.me.top_role.position})")
        if not perm:
            print("    ⚠️ ニックネーム管理権限がありません。招待時の権限を確認してください。")


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """ロールが変わったら自動でニックネームを更新。"""
    if set(before.roles) == set(after.roles):
        return
    before_school = get_school_role(before)
    after_school = get_school_role(after)
    # 高校ロールに変化があったときだけ処理
    if before_school == after_school:
        return
    if after_school is not None:
        result = await apply_nickname(after)
        print(f"[on_member_update] {after} : {result}")


@bot.tree.command(name="syncschool", description="サーバー全員に高校名プレフィックスを一括適用します（管理者用）")
@app_commands.checks.has_permissions(manage_nicknames=True)
async def syncschool(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    guild = interaction.guild
    ok = unchanged = skipped = errors = 0
    for member in guild.members:
        result = await apply_nickname(member)
        if result.startswith("ok"):
            ok += 1
        elif result == "unchanged":
            unchanged += 1
        elif result.startswith("skip"):
            skipped += 1
        else:
            errors += 1
    await log_update(guild, f"📋 /syncschool by {interaction.user} : 更新{ok}/変更なし{unchanged}/対象外{skipped}/失敗{errors}")
    await interaction.followup.send(
        f"一括適用完了\n"
        f"・更新: {ok}\n"
        f"・変更なし: {unchanged}\n"
        f"・対象外: {skipped}\n"
        f"・失敗: {errors}",
        ephemeral=True,
    )


@bot.tree.command(name="setschool", description="自分のニックネームに高校名を付け直します")
async def setschool(interaction: discord.Interaction):
    result = await apply_nickname(interaction.user)
    await interaction.response.send_message(f"結果: {result}", ephemeral=True)


@bot.tree.command(name="history", description="最近の更新履歴（誰がどう変わったか）を表示します")
@app_commands.describe(count="表示する件数（既定20・最大50）")
@app_commands.checks.has_permissions(manage_nicknames=True)
async def history(interaction: discord.Interaction, count: int = 20):
    count = max(1, min(count, 50))
    try:
        with open("update.log", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []
    # ニックネーム変更行（付与/解除）だけ抽出
    changes = [ln.rstrip("\n") for ln in lines if ("✏️" in ln or "↩️" in ln)]
    recent = changes[-count:]
    if not recent:
        await interaction.response.send_message("まだ更新履歴はありません。", ephemeral=True)
        return
    body = "\n".join(recent)
    if len(body) > 1900:
        body = body[-1900:]
    await interaction.response.send_message(f"**直近{len(recent)}件の更新履歴**\n```\n{body}\n```", ephemeral=True)


@bot.tree.command(name="resetschool", description="サーバー全員の高校名プレフィックスを一括解除します（管理者用・リカバリー）")
@app_commands.checks.has_permissions(manage_nicknames=True)
async def resetschool(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    ok = unchanged = skipped = errors = 0
    for member in interaction.guild.members:
        result = await revert_nickname(member)
        if result.startswith("ok"):
            ok += 1
        elif result == "unchanged":
            unchanged += 1
        elif result.startswith("skip"):
            skipped += 1
        else:
            errors += 1
    await interaction.followup.send(
        f"一括解除完了\n・解除: {ok}\n・対象なし: {unchanged}\n・対象外: {skipped}\n・失敗: {errors}",
        ephemeral=True,
    )


@bot.tree.command(name="unsetschool", description="自分のニックネームから高校名を外します")
async def unsetschool(interaction: discord.Interaction):
    result = await revert_nickname(interaction.user)
    await interaction.response.send_message(f"結果: {result}", ephemeral=True)


@bot.tree.command(name="checkperms", description="BOTの権限・設定が足りているか自己診断します")
async def checkperms(interaction: discord.Interaction):
    guild = interaction.guild
    me = guild.me
    lines = ["**BOT自己診断**"]

    # 1. Manage Nicknames 権限
    perm = me.guild_permissions.manage_nicknames
    lines.append(f"{'✅' if perm else '❌'} ニックネームの管理 (Manage Nicknames): {perm}")

    # 2. SERVER MEMBERS INTENT（メンバーが取得できているか）
    intent_ok = len(guild.members) > 1 or bot.intents.members
    lines.append(f"{'✅' if bot.intents.members else '❌'} SERVER MEMBERS INTENT: {bot.intents.members}")

    # 3. ロール順位: BOTより上位のメンバー数（=変更できない相手）
    higher = [
        m for m in guild.members
        if not m.bot and m.top_role >= me.top_role and m != guild.owner
    ]
    if higher:
        names = ", ".join(m.display_name for m in higher[:5])
        more = f" 他{len(higher) - 5}名" if len(higher) > 5 else ""
        lines.append(f"⚠️ BOTロール順位が低く変更できないメンバー: {len(higher)}名 ({names}{more})")
        lines.append("　→ サーバー設定→ロール でBOTのロールを上へ移動してください")
    else:
        lines.append("✅ ロール順位: 一般メンバーより上にあります")
    lines.append("ℹ️ サーバーオーナーのニックネームはDiscord仕様上、誰も変更できません")

    if perm and bot.intents.members and not higher:
        lines.append("\n**結論: 権限・設定は十分です** 👍")
    else:
        lines.append("\n**結論: 上記の❌/⚠️を解消してください**")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@syncschool.error
@resetschool.error
async def perm_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "このコマンドには「ニックネームの管理」権限が必要です。"
    else:
        msg = f"エラー: {error}"
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN が設定されていません（.env を確認）")
    bot.run(TOKEN)
