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
        "Scrap Grade Weapon", "Scrap Grade Armor",
        "50 XP Crystal", "100 XP Crystal",
        "10,000 Crowns"
    ],
    4: [
        "Named Grade Weapon", "Named Grade Armor",
        "250 XP Crystal", "25,000 Crowns"
    ],
    5: [
        "Exalted Grade Weapon", "Exalted Grade Armor",
        "20% XP Multiplier (1 Week)",
        "500 XP Crystal", "50,000 Crowns"
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

# =====================================================
# SETUP
# =====================================================

async def setup(bot):
    await bot.add_cog(GachaCog(bot))
