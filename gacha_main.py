# gacha_main.py — FULL GENSHIN-STYLE GACHA SYSTEM (CLEAN & STABLE)

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random
import time

from bot_config import DB_NAME, GACHA_CHANNEL_ID, MODERATOR_ROLE_IDS

# =====================================================
# CONFIG
# =====================================================

RATE_5_STAR = 0.006
RATE_4_STAR = 0.05

HARD_PITY_5 = 60
SPECIAL_30_CHANCE = 0.5

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
# DATABASE
# =====================================================

def db():
    return sqlite3.connect(DB_NAME)

def get_pity(user_id: int):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT pity_5_star, total_pulls FROM pity WHERE user_id = ?",
            (user_id,)
        )
        row = cur.fetchone()
        return {
            "pity": row[0] if row else 0,
            "total": row[1] if row else 0
        }

def save_pity(user_id: int, pity: int, total: int):
    with db() as conn:
        conn.execute("""
            INSERT INTO pity (user_id, pity_5_star, pity_4_star, total_pulls)
            VALUES (?, ?, 0, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                pity_5_star = excluded.pity_5_star,
                total_pulls = excluded.total_pulls
        """, (user_id, pity, total))

def add_inventory(user_id: int, item: str):
    with db() as conn:
        conn.execute("""
            INSERT INTO inventory (user_id, item_name, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, item_name)
            DO UPDATE SET quantity = quantity + 1
        """, (user_id, item))

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
        return True

def get_inventory(user_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT item_name, quantity FROM inventory WHERE user_id = ? ORDER BY quantity DESC",
            (user_id,)
        ).fetchall()

def log_history(user_id: int, item: str, rarity: int):
    with db() as conn:
        conn.execute("""
            INSERT INTO pull_history (user_id, item_name, rarity, timestamp)
            VALUES (?, ?, ?, ?)
        """, (user_id, item, rarity, int(time.time())))

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
# GACHA LOGIC
# =====================================================

def roll_rarity(pity: int) -> int:
    if pity >= HARD_PITY_5:
        return 5
    if pity == 30:
        return 5 if random.random() < SPECIAL_30_CHANCE else 4
    if pity % 10 == 0:
        return 4

    r = random.random()
    if r < RATE_5_STAR:
        return 5
    if r < RATE_5_STAR + RATE_4_STAR:
        return 4
    return 3

def single_pull(state: dict):
    state["pity"] += 1
    state["total"] += 1

    rarity = roll_rarity(state["pity"])
    item = random.choice(LOOT_TABLE[rarity])

    if rarity == 5:
        state["pity"] = 0

    return rarity, item

async def do_wish(user, amount: int):
    state = get_pity(user.id)
    results = {3: [], 4: [], 5: []}

    for _ in range(amount):
        rarity, item = single_pull(state)
        results[rarity].append(item)
        add_inventory(user.id, item)
        log_history(user.id, item, rarity)

    save_pity(user.id, state["pity"], state["total"])
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
        title=f"💫 {user.display_name}'s {amount} Wish Results",
        description="\n".join(desc),
        color=RARITY_COLOR[highest]
    )

    remaining = HARD_PITY_5 - state["pity"]
    embed.set_footer(
        text=f"Pity: {state['pity']}/{HARD_PITY_5} • Guaranteed in {remaining} pulls"
    )
    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    return embed

# =====================================================
# COG
# =====================================================

class GachaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # -------- WISH --------
    @app_commands.command(name="wish")
    async def slash_wish(self, interaction: discord.Interaction, amount: int = 1):
        if interaction.channel_id != GACHA_CHANNEL_ID:
            return await interaction.response.send_message("Wrong channel.", ephemeral=True)

        await interaction.response.defer()
        results, state = await do_wish(interaction.user, amount)
        await interaction.followup.send(embed=wish_embed(interaction.user, amount, results, state))

    @commands.command(name="wish")
    async def text_wish(self, ctx, amount: int = 1):
        if ctx.channel.id != GACHA_CHANNEL_ID:
            return await ctx.send("Wrong channel.")
        results, state = await do_wish(ctx.author, amount)
        await ctx.send(embed=wish_embed(ctx.author, amount, results, state))

    # -------- PITY --------
    @app_commands.command(name="pity")
    async def slash_pity(self, interaction: discord.Interaction):
        state = get_pity(interaction.user.id)
        embed = discord.Embed(title="📊 Pity Status", color=discord.Color.gold())
        embed.add_field(name="5★ Pity", value=f"{state['pity']} / {HARD_PITY_5}", inline=False)
        embed.add_field(name="Total Pulls", value=str(state["total"]), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------- INVENTORY --------
    @app_commands.command(name="inventory")
    async def slash_inventory(self, interaction: discord.Interaction):
        items = get_inventory(interaction.user.id)
        embed = discord.Embed(title="🎒 Inventory", color=discord.Color.blue())
        if not items:
            embed.description = "Your inventory is empty."
        else:
            embed.description = "\n".join(f"**{i}** x{q}" for i, q in items[:20])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------- HISTORY --------
    @app_commands.command(name="history")
    async def slash_history(self, interaction: discord.Interaction):
        history = get_history(interaction.user.id)
        embed = discord.Embed(title="📜 Pull History", color=discord.Color.purple())
        if not history:
            embed.description = "No pulls yet."
        else:
            lines = []
            for item, rarity, ts in history:
                lines.append(f"{RARITY_EMOJI[rarity]} **{item}** (<t:{ts}:R>)")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------- USE ITEM --------
    @app_commands.command(name="use")
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
    
        save_pity(member.id, pity, total)
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
            rows = conn.execute("SELECT user_id, pity_5_star FROM pity ORDER BY pity_5_star DESC LIMIT 10").fetchall()
        embed = discord.Embed(title="🏆 5★ Pull Leaderboard", color=discord.Color.gold())
        if not rows:
            embed.description = "No data yet."
        else:
            for idx, (uid, pulls) in enumerate(rows, 1):
                user = self.bot.get_user(uid)
                name = user.display_name if user else f"User {uid}"
                embed.add_field(name=f"{idx}. {name}", value=f"{pulls} 5★ pulls", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------- TOP 5★ USERS --------
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
        embed.add_field(name="Pity", value=f"Hard pity at {HARD_PITY_5} pulls")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------- RATES --------
    @app_commands.command(name="rates", description="Check drop rates and pity info")
    async def slash_rates(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📊 Gacha Rates", color=discord.Color.light_grey())
        embed.add_field(name="3★ Items", value=f"{(1 - RATE_5_STAR - RATE_4_STAR)*100:.2f}%")
        embed.add_field(name="4★ Items", value=f"{RATE_4_STAR*100:.2f}%")
        embed.add_field(name="5★ Items", value=f"{RATE_5_STAR*100:.2f}%")
        embed.add_field(name="Pity Rules", value=f"Hard pity at {HARD_PITY_5} pulls\n30th pull 50% chance for 5★")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# =====================================================
# SETUP
# =====================================================

async def setup(bot):
    await bot.add_cog(GachaCog(bot))
