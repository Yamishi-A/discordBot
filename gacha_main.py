# gacha_main.py (FIXED for discord.py v2.x slash commands)
import discord
from discord.ext import commands
import sqlite3
import random
import time
from discord import app_commands # <<< ADDED: Required for modern slash commands

# CHANGED: Updated import to use the list of IDs (if applicable)
from bot_config import GACHA_CHANNEL_ID, MODERATOR_ROLE_IDS, DB_NAME 

# --- LOOT POOLS & CONSTANTS ---
RATE_5_STAR = 0.006
RATE_4_STAR = 0.05

LOOT_TABLE = {
    3: [
        "Rusted Seax", "Padded Furs & Wood", "10% XP Multiplier Token (1 Use)",
        "50 XP Crystal", "100 XP Crystal", "1,000 Crowns"
    ],
    4: [
        "Huscarl Bearded Axe", "Huscarl Lamellar", "10% XP Multiplier Token (1 Week)",
        "250 XP Crystal", "10,000 Crowns", "The Einherjar's Edge", "The Einherjar's Hauberk"
    ],
    5: [
        "Exalted Grade Item", "20% XP Multiplier (1 Week)",
        "500 XP Crystal", "50,000 Crowns", "Legendary Warhorn"
    ]
}

# --- DATABASE HELPERS ---
def _get_conn():
    return sqlite3.connect(DB_NAME)

def get_user_pity_data(user_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM pity WHERE user_id = ?", (user_id,))
        data = c.fetchone()
        if data:
            return {"pity_5_star": data[1], "pity_4_star": data[2], "total_pulls": data[3]}
        return {"pity_5_star": 0, "pity_4_star": 0, "total_pulls": 0}
    finally:
        conn.close()

def update_pity_data(user_id, pity_5_star, pity_4_star, total_pulls):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO pity (user_id, pity_5_star, pity_4_star, total_pulls)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                pity_5_star = excluded.pity_5_star,
                pity_4_star = excluded.pity_4_star,
                total_pulls = excluded.total_pulls
        """, (user_id, pity_5_star, pity_4_star, total_pulls))
        conn.commit()
    finally:
        conn.close()

# --- UTILITY ---
def is_gacha_channel(interaction: discord.Interaction): # CHANGED: Uses Interaction
    return interaction.channel_id == GACHA_CHANNEL_ID

# NOTE: Placeholder functions. You must ensure the actual logic inside these
# uses 'interaction' instead of 'ctx' for responding, mentioning users, etc.
async def _process_wish(interaction: discord.Interaction, amount: int):
    await interaction.response.send_message(f"Processing {amount} wish(es) for {interaction.user.mention} (Placeholder).", ephemeral=True)

async def _process_inventory(interaction: discord.Interaction):
    await interaction.response.send_message(f"Showing inventory for {interaction.user.mention} (Placeholder).", ephemeral=True)

async def _process_use(interaction: discord.Interaction, item: str):
    await interaction.response.send_message(f"Using item: {item} (Placeholder).", ephemeral=True)

async def _process_history(interaction: discord.Interaction):
    await interaction.response.send_message(f"Showing pull history for {interaction.user.mention} (Placeholder).", ephemeral=True)

async def _process_leaderboard(interaction: discord.Interaction):
    await interaction.response.send_message(f"Showing pull leaderboard (Placeholder).", ephemeral=True)

async def _process_stats(interaction: discord.Interaction):
    await interaction.response.send_message(f"Showing stats for {interaction.user.mention} (Placeholder).", ephemeral=True)


# --- COG CLASS ---
class GachaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # CHANGED: All commands updated to use @app_commands.command
    # CHANGED: All signatures updated to use interaction: discord.Interaction
    @app_commands.command(name="wish", description="Perform gacha pulls (1 or 10)")
    async def slash_wish(self, interaction: discord.Interaction, amount: int = 1):
        if not is_gacha_channel(interaction):
            # CHANGED: Use interaction.response.send_message
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        
        await self._process_wish(interaction, amount)

    @app_commands.command(name="inventory", description="View your inventory")
    async def slash_inventory(self, interaction: discord.Interaction):
        if not is_gacha_channel(interaction):
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        await self._process_inventory(interaction)

    @app_commands.command(name="use", description="Use an item from your inventory")
    async def slash_use(self, interaction: discord.Interaction, item: str):
        if not is_gacha_channel(interaction):
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        await self._process_use(interaction, item)

    @app_commands.command(name="history", description="View your recent pull history")
    async def slash_history(self, interaction: discord.Interaction):
        if not is_gacha_channel(interaction):
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        await self._process_history(interaction)

    @app_commands.command(name="leaderboard", description="View the pull leaderboard")
    async def slash_leaderboard(self, interaction: discord.Interaction):
        if not is_gacha_channel(interaction):
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        await self._process_leaderboard(interaction)

    @app_commands.command(name="stats", description="View your gacha stats")
    async def slash_stats(self, interaction: discord.Interaction):
        if not is_gacha_channel(interaction):
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        await self._process_stats(interaction)

    # ---------- MODERATOR COMMAND ----------
    @app_commands.command(name="setpity", description="Set a user's pity values (moderator only)")
    async def slash_setpity(self, interaction: discord.Interaction, member: discord.Member, pity_5: int = 0, pity_4: int = 0, total_pulls: int = 0):
        # CHANGED: Check uses interaction.user.roles and MODERATOR_ROLE_IDS list
        if not any(r.id in MODERATOR_ROLE_IDS for r in interaction.user.roles):
            await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
            return
        
        update_pity_data(member.id, pity_5, pity_4, total_pulls)
        await interaction.response.send_message(
            f"✅ Pity data for {member.mention} updated: 5-star pity: {pity_5}, 4-star pity: {pity_4}, Total pulls: {total_pulls}", 
            ephemeral=True
        )

# --- COG SETUP FUNCTION ---
# ADDED: This function is required for asynchronous loading (setup_hook in bot.py)
async def setup(bot):
    await bot.add_cog(GachaCog(bot))
