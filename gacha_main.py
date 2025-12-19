# gacha_main.py — FULL GENSHIN-STYLE GACHA SYSTEM (CLEAN & STABLE)
# Drop in, copy/paste. Assumes bot_config provides DB_NAME, GACHA_CHANNEL_ID, MODERATOR_ROLE_IDS.

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random
import time
import typing
import logging
import traceback

from bot_config import DB_NAME, GACHA_CHANNEL_ID, MODERATOR_ROLE_IDS

# Basic logger so exceptions are visible in console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gacha")

# =====================================================
# CONFIG (tweakable)
# =====================================================

RATE_5_STAR = 0.006
RATE_4_STAR = 0.05

HARD_PITY_5 = 60         # guaranteed 5★ at this pull
SPECIAL_30_CHANCE = 0.5  # at pull 30 there's a 50% chance to upgrade to 5★; if it fails, guarantee a 4★

MAX_WISHES_AT_ONCE = 10  # validate amount

# =====================================================
# LOOT TABLE
# =====================================================

LOOT_TABLE = {
    3: [
        "Rusted Seax",
        "Padded Furs & Wood",
        "10% XP Multiplier Token (1 Use)",
        "50 XP Crystal",
        "100 XP Crystal",
        "1,000 Crowns"
    ],
    4: [
        "Huscarl Bearded Axe",
        "Huscarl Lamellar",
        "10% XP Multiplier Token (1 Week)",
        "250 XP Crystal",
        "10,000 Crowns",
        "The Einherjar’s Edge",
        "The Einherjar’s Hauberk"
    ],
    5: [
        "Exalted Grade Item",
        "20% XP Multiplier (1 Week)",
        "500 XP Crystal",
        "50,000 Crowns"
    ]
}

RARITY_EMOJI = {3: "▪️", 4: "🔸", 5: "🌟"}
RARITY_COLOR = {3: 0x90EE90, 4: 0xADD8E6, 5: 0xFFD700}

# =====================================================
# DATABASE HELPERS / INITIALIZER
# =====================================================

def db():
    # Always open a fresh connection; check_same_thread False reduces thread errors for async bots.
    return sqlite3.connect(DB_NAME, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread=False)

def init_db():
    """Create tables if they don't exist. Call at cog init."""
    with db() as conn:
        cur = conn.cursor()
        # pity: track both 5★ pity, 4★ pity, total pulls, and total_5_stars for leaderboards
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pity (
                user_id INTEGER PRIMARY KEY,
                pity_5_star INTEGER NOT NULL DEFAULT 0,
                pity_4_star INTEGER NOT NULL DEFAULT 0,
                total_pulls INTEGER NOT NULL DEFAULT 0,
                total_5_stars INTEGER NOT NULL DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                user_id INTEGER,
                item_name TEXT,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, item_name)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pull_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_name TEXT,
                rarity INTEGER,
                timestamp INTEGER
            )
        """)
        conn.commit()

# =====================================================
# PITY / STATE FUNCTIONS
# =====================================================

def get_pity(user_id: int) -> dict:
    """Return a dict with pity_5, pity_4, total, total_5. Ensures a row exists."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pity_5_star, pity_4_star, total_pulls, total_5_stars FROM pity WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if not row:
            # Insert a default row to ensure persistence & avoid race conditions elsewhere
            cur.execute(
                "INSERT INTO pity (user_id, pity_5_star, pity_4_star, total_pulls, total_5_stars) VALUES (?, 0, 0, 0, 0)",
                (user_id,)
            )
            conn.commit()
            return {"pity_5": 0, "pity_4": 0, "total": 0, "total_5": 0}
        return {"pity_5": row[0], "pity_4": row[1], "total": row[2], "total_5": row[3]}

def save_pity(user_id: int, pity_5: int, pity_4: int, total: int, total_5: int):
    """Upsert the user's pity counters and totals in a SQLite-compatible way."""
    try:
        with db() as conn:
            cur = conn.cursor()
            # Try a simple UPDATE first
            cur.execute("""
                UPDATE pity
                SET pity_5_star = ?, pity_4_star = ?, total_pulls = ?, total_5_stars = ?
                WHERE user_id = ?
            """, (pity_5, pity_4, total, total_5, user_id))
            if cur.rowcount == 0:
                # row didn't exist, do an insert
                cur.execute("""
                    INSERT INTO pity (user_id, pity_5_star, pity_4_star, total_pulls, total_5_stars)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, pity_5, pity_4, total, total_5))
            conn.commit()
    except Exception:
        logger.error("Failed to save pity for user %s:\n%s", user_id, traceback.format_exc())
        # Do not re-raise — we prefer to continue and let the caller handle user-notification.

# =====================================================
# INVENTORY / HISTORY
# =====================================================

def add_inventory(user_id: int, item: str):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO inventory (user_id, item_name, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, item_name) DO UPDATE SET quantity = quantity + 1
        """, (user_id, item))
        conn.commit()

def remove_inventory(user_id: int, item: str) -> bool:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT quantity FROM inventory WHERE user_id = ? AND item_name = ?",
            (user_id, item)
        )
        row = cur.fetchone()
        if not row:
            return False

        if row[0] <= 1:
            cur.execute(
                "DELETE FROM inventory WHERE user_id = ? AND item_name = ?",
                (user_id, item)
            )
        else:
            cur.execute(
                "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_name = ?",
                (user_id, item)
            )
        conn.commit()
        return True

def get_inventory(user_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT item_name, quantity FROM inventory WHERE user_id = ? ORDER BY quantity DESC",
            (user_id,)
        ).fetchall()

def log_history(user_id: int, item: str, rarity: int):
    try:
        with db() as conn:
            conn.execute("""
                INSERT INTO pull_history (user_id, item_name, rarity, timestamp)
                VALUES (?, ?, ?, ?)
            """, (user_id, item, rarity, int(time.time())))
            conn.commit()
    except Exception:
        logger.error("Failed to log history for user %s:\n%s", user_id, traceback.format_exc())

def get_history(user_id: int, limit=20):
    with db() as conn:
        return conn.execute("""
            SELECT item_name, rarity, timestamp
            FROM pull_history
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()

# =====================================================
# GACHA LOGIC (FIXED)
# =====================================================

def roll_rarity(state: dict) -> int:
    """
    Determine rarity according to:
     - HARD_PITY_5 guaranteed 5★
     - special chance at 30th pull (if configured)
     - 4★ guaranteed every 10 pulls (tracked by pity_4)
     - otherwise normal rates
    """
    pity_5 = state["pity_5"]
    pity_4 = state["pity_4"]

    # HARD pity for 5★ (guaranteed)
    if pity_5 >= HARD_PITY_5:
        return 5

    # Special 30th pull behaviour: either upgrade to 5★ or fallback to guaranteed 4★
    if pity_5 == 30:
        if random.random() < SPECIAL_30_CHANCE:
            return 5
        else:
            return 4

    # 4★ guarantee (every 10 pulls without 4/5): using pity_4 counter
    if pity_4 >= 10:
        return 4

    # Normal random roll
    r = random.random()
    if r < RATE_5_STAR:
        return 5
    if r < RATE_5_STAR + RATE_4_STAR:
        return 4
    return 3

def single_pull(state: dict):
    """
    state is a dict returned by get_pity with keys: pity_5, pity_4, total, total_5
    We increment counters BEFORE the roll to match typical gacha counting (pull 1 increments from 0->1).
    """
    # increment counters
    state["pity_5"] += 1
    state["pity_4"] += 1
    state["total"] += 1

    rarity = roll_rarity(state)
    # choose an item from the rarity pool
    item = random.choice(LOOT_TABLE[rarity])

    # Apply resets and bookkeeping
    if rarity == 5:
        state["pity_5"] = 0
        state["pity_4"] = 0  # 5★ also resets the 4★ pity
        state["total_5"] += 1
    elif rarity == 4:
        state["pity_4"] = 0

    return rarity, item

async def do_wish(user: typing.Union[discord.User, discord.Member], amount: int):
    # validate amount
    amount = max(1, min(amount, MAX_WISHES_AT_ONCE))
    state = get_pity(user.id)
    results = {3: [], 4: [], 5: []}

    for _ in range(amount):
        rarity, item = single_pull(state)
        results[rarity].append(item)
        try:
            add_inventory(user.id, item)
            log_history(user.id, item, rarity)
        except Exception:
            # If inventory/history fails, log it but continue — avoid crashing the whole wish.
            logger.error("Inventory/history error for user %s: %s", user.id, traceback.format_exc())

    # Save updated pity and totals (safe save)
    save_pity(user.id, state["pity_5"], state["pity_4"], state["total"], state["total_5"])
    return results, state

# =====================================================
# EMBEDS
# =====================================================

def wish_embed(user, amount, results, state):
    highest = max((r for r in results if results[r]), default=3)

    desc = []
    for r in (5, 4, 3):
        if results[r]:
            desc.append(f"### {RARITY_EMOJI[r]} {r}-Star")
            for item in results[r]:
                desc.append(f"> **{item}**")

    embed = discord.Embed(
        title=f"💫 {getattr(user, 'display_name', getattr(user, 'name', 'Player'))}'s {amount} Wish Results",
        description="\n".join(desc) if desc else "No results (this shouldn't happen).",
        color=RARITY_COLOR.get(highest, 0xFFFFFF)
    )

    remaining = max(0, HARD_PITY_5 - state["pity_5"])
    embed.set_footer(
        text=f"Pity: {state['pity_5']}/{HARD_PITY_5} • Guaranteed in {remaining} pulls"
    )
    try:
        # some gateway users may not have avatar property; guard it
        avatar_url = None
        if hasattr(user, "avatar") and getattr(user, "avatar"):
            # discord.py Member/User avatar objects can be None or have .url
            try:
                avatar_url = user.avatar.url
            except Exception:
                avatar_url = None
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
    except Exception:
        # ignore safely
        pass
    return embed

# =====================================================
# COG
# =====================================================

class GachaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        init_db()  # ensure DB/tables exist on cog load

    # -------- WISH (slash) --------
    @app_commands.command(name="wish", description="Perform gacha pulls (1-10)")
    async def slash_wish(self, interaction: discord.Interaction, amount: int = 1):
        if interaction.channel_id != GACHA_CHANNEL_ID:
            return await interaction.response.send_message("Wrong channel.", ephemeral=True)

        # clamp amount server-side for safety
        amount = max(1, min(amount, MAX_WISHES_AT_ONCE))

        # Defer early to give us time for DB/processing.
        # If anything goes wrong after this, we'll respond via followup so the user doesn't get stuck.
        await interaction.response.defer()

        try:
            results, state = await do_wish(interaction.user, amount)
            embed = wish_embed(interaction.user, amount, results, state)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            # Log the traceback and inform the user instead of leaving them with the thinking state
            logger.error("Error handling /wish: %s\n%s", e, traceback.format_exc())
            # If followup fails too, try to use a non-deferred response (last resort)
            try:
                await interaction.followup.send(content="❌ An error occurred while processing your wish. The error has been logged.", ephemeral=True)
            except Exception:
                # final fallback: try to send a direct ephemeral response (this will raise if already responded/deferred in certain ways)
                try:
                    await interaction.response.send_message("❌ An error occurred while processing your wish. The error has been logged.", ephemeral=True)
                except Exception:
                    logger.error("Failed to notify user after wish error: %s", traceback.format_exc())

    # -------- WISH (text command) --------
    @commands.command(name="wish")
    async def text_wish(self, ctx, amount: int = 1):
        if ctx.channel.id != GACHA_CHANNEL_ID:
            return await ctx.send("Wrong channel.")
        amount = max(1, min(amount, MAX_WISHES_AT_ONCE))
        try:
            results, state = await do_wish(ctx.author, amount)
            await ctx.send(embed=wish_embed(ctx.author, amount, results, state))
        except Exception:
            logger.error("Error handling text !wish: %s", traceback.format_exc())
            await ctx.send("❌ An error occurred while processing your wish. Check the bot logs.")

    # -------- PITY --------
    @app_commands.command(name="pity", description="Check your 5★ pity and total pulls")
    async def slash_pity(self, interaction: discord.Interaction):
        state = get_pity(interaction.user.id)
        embed = discord.Embed(title="📊 Pity Status", color=discord.Color.gold())
        embed.add_field(name="5★ Pity", value=f"{state['pity_5']} / {HARD_PITY_5}", inline=False)
        embed.add_field(name="Total Pulls", value=str(state["total"]), inline=False)
        embed.add_field(name="Total 5★ Obtained", value=str(state["total_5"]), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------- INVENTORY --------
    @app_commands.command(name="inventory", description="View your inventory items")
    async def slash_inventory(self, interaction: discord.Interaction):
        items = get_inventory(interaction.user.id)
        embed = discord.Embed(title="🎒 Inventory", color=discord.Color.blue())
        if not items:
            embed.description = "Your inventory is empty."
        else:
            embed.description = "\n".join(f"**{i}** x{q}" for i, q in items[:20])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------- HISTORY --------
    @app_commands.command(name="history", description="See your recent pulls")
    async def slash_history(self, interaction: discord.Interaction):
        history = get_history(interaction.user.id)
        embed = discord.Embed(title="📜 Pull History", color=discord.Color.purple())
        if not history:
            embed.description = "No pulls yet."
        else:
            lines = []
            for item, rarity, ts in history:
                lines.append(f"{RARITY_EMOJI.get(rarity,'')} **{item}** (<t:{ts}:R>)")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------- USE ITEM --------
    @app_commands.command(name="use", description="Use an item from your inventory")
    async def slash_use(self, interaction: discord.Interaction, item: str):
        if remove_inventory(interaction.user.id, item):
            await interaction.response.send_message(f"✅ Used **{item}**.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ You don't own that item.", ephemeral=True)

    # -------- HELP --------
    @app_commands.command(name="help", description="Show all Gacha commands")
    async def slash_help(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📝 Gacha Commands Help", color=discord.Color.green())
        commands_info = {
            "/wish <amount>": "Perform a gacha pull (1-10 at a time).",
            "/pity": "Check your current 5★ pity and total pulls.",
            "/inventory": "View your inventory items.",
            "/history": "See your most recent pulls (last 20).",
            "/use <item>": "Use an item from your inventory.",
            "/leaderboard": "View the top players by total 5★ pulls.",
            "/banner": "See the current banner and featured items.",
            "/rates": "Check drop rates, pity rules, and special chances.",
            "/top5stars": "See users with the most 5★ pulls."
        }
        for cmd, desc in commands_info.items():
            embed.add_field(name=cmd, value=desc, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------- SET PITY (MODERATOR ONLY) --------
    @app_commands.command(name="setpity", description="Set a user's 5★ pity and total pulls (Mods only)")
    @app_commands.checks.has_any_role(*MODERATOR_ROLE_IDS)
    async def slash_setpity(self, interaction: discord.Interaction, member: discord.Member, pity: int, total: int):
        if pity < 0 or total < 0:
            return await interaction.response.send_message("❌ Pity and total pulls must be 0 or higher.", ephemeral=True)

        # Fetch current total_5 to preserve unless explicitly changed (we don't have a param for it)
        current = get_pity(member.id)
        save_pity(member.id, pity, current["pity_4"], total, current["total_5"])
        await interaction.response.send_message(f"✅ {member.display_name}'s pity set to {pity} and total pulls to {total}.", ephemeral=True)

    @slash_setpity.error
    async def slash_setpity_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingAnyRole):
            await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ An error occurred: {error}", ephemeral=True)

    # -------- LEADERBOARD --------
    @app_commands.command(name="leaderboard", description="Top players by total 5★ pulls")
    async def slash_leaderboard(self, interaction: discord.Interaction):
        with db() as conn:
            rows = conn.execute("SELECT user_id, total_5_stars FROM pity ORDER BY total_5_stars DESC LIMIT 10").fetchall()
        embed = discord.Embed(title="🏆 5★ Pull Leaderboard", color=discord.Color.gold())
        if not rows:
            embed.description = "No data yet."
        else:
            for idx, (uid, pulls) in enumerate(rows, 1):
                user = self.bot.get_user(uid)
                name = user.display_name if user else f"User {uid}"
                embed.add_field(name=f"{idx}. {name}", value=f"{pulls} 5★ pulls", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------- TOP 5★ USERS (alias) --------
    @app_commands.command(name="top5stars", description="Users with the most 5★ pulls")
    async def slash_top5stars(self, interaction: discord.Interaction):
        await self.slash_leaderboard(interaction)  # Alias to leaderboard

    # -------- BANNER --------
    @app_commands.command(name="banner", description="See current banner info")
    async def slash_banner(self, interaction: discord.Interaction):
        embed = discord.Embed(title="✨ Current Banner", color=discord.Color.teal())
        embed.add_field(name="Featured 5★ Items", value="\n".join(LOOT_TABLE[5]), inline=False)
        embed.add_field(name="Featured 4★ Items", value="\n".join(LOOT_TABLE[4]), inline=False)
        embed.add_field(name="5★ Rate", value=f"{RATE_5_STAR*100:.2f}%")
        embed.add_field(name="4★ Rate", value=f"{RATE_4_STAR*100:.2f}%")
        embed.add_field(name="Pity", value=f"Hard pity at {HARD_PITY_5} pulls\n30th pull {int(SPECIAL_30_CHANCE*100)}% chance for 5★ else 4★", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------- RATES --------
    @app_commands.command(name="rates", description="Check drop rates and pity info")
    async def slash_rates(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📊 Gacha Rates", color=discord.Color.light_grey())
        embed.add_field(name="3★ Items", value=f"{(1 - RATE_5_STAR - RATE_4_STAR)*100:.2f}%")
        embed.add_field(name="4★ Items", value=f"{RATE_4_STAR*100:.2f}%")
        embed.add_field(name="5★ Items", value=f"{RATE_5_STAR*100:.2f}%")
        embed.add_field(name="Pity Rules", value=f"Hard pity at {HARD_PITY_5} pulls\n30th pull {int(SPECIAL_30_CHANCE*100)}% chance for 5★ else guaranteed 4★\n4★ guarantee every 10 pulls without 4/5", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# =====================================================
# SETUP
# =====================================================

async def setup(bot):
    await bot.add_cog(GachaCog(bot))