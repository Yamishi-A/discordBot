# gacha_main.py (MODIFIED to include $$ text commands)
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
# Separate utility for Interaction (Slash) and Context (Text)
def is_gacha_channel_interaction(interaction: discord.Interaction):
    return interaction.channel_id == GACHA_CHANNEL_ID

def is_gacha_channel_context(ctx: commands.Context):
    return ctx.channel.id == GACHA_CHANNEL_ID


# NOTE: Placeholder functions for SLASH commands (using interaction)
async def _process_wish(interaction: discord.Interaction, amount: int):
    # This is the full logic implementation that would happen here
    await interaction.response.send_message(f"Processing {amount} wish(es) for {interaction.user.mention} (Placeholder - SLASH).", ephemeral=True)

async def _process_inventory(interaction: discord.Interaction):
    await interaction.response.send_message(f"Showing inventory for {interaction.user.mention} (Placeholder - SLASH).", ephemeral=True)

async def _process_use(interaction: discord.Interaction, item: str):
    await interaction.response.send_message(f"Using item: {item} (Placeholder - SLASH).", ephemeral=True)

async def _process_history(interaction: discord.Interaction):
    await interaction.response.send_message(f"Showing pull history for {interaction.user.mention} (Placeholder - SLASH).", ephemeral=True)

async def _process_leaderboard(interaction: discord.Interaction):
    await interaction.response.send_message(f"Showing pull leaderboard (Placeholder - SLASH).", ephemeral=True)

async def _process_stats(interaction: discord.Interaction):
    await interaction.response.send_message(f"Showing stats for {interaction.user.mention} (Placeholder - SLASH).", ephemeral=True)


# --- NEW: Placeholder functions for TEXT commands (using ctx) ---
async def _text_process_wish(ctx: commands.Context, amount: int):
    await ctx.send(f"Processing {amount} wish(es) for {ctx.author.mention} (Placeholder - TEXT).")

async def _text_process_inventory(ctx: commands.Context):
    await ctx.send(f"Showing inventory for {ctx.author.mention} (Placeholder - TEXT).")

async def _text_process_use(ctx: commands.Context, item: str):
    await ctx.send(f"Using item: {item} (Placeholder - TEXT).")

async def _text_process_history(ctx: commands.Context):
    await ctx.send(f"Showing pull history for {ctx.author.mention} (Placeholder - TEXT).")

async def _text_process_leaderboard(ctx: commands.Context):
    await ctx.send(f"Showing pull leaderboard (Placeholder - TEXT).")

async def _text_process_stats(ctx: commands.Context):
    await ctx.send(f"Showing stats for {ctx.author.mention} (Placeholder - TEXT).")
# ---------------------------------------------------------------


# --- COG CLASS ---
class GachaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------- SLASH COMMANDS (Existing code adapted to new utility) ----------
    @app_commands.command(name="wish", description="Perform gacha pulls (1 or 10)")
    async def slash_wish(self, interaction: discord.Interaction, amount: int = 1):
        if not is_gacha_channel_interaction(interaction):
            # CHANGED: Use is_gacha_channel_interaction
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        
        await _process_wish(interaction, amount)

    @app_commands.command(name="inventory", description="View your inventory")
    async def slash_inventory(self, interaction: discord.Interaction):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        await _process_inventory(interaction)

    @app_commands.command(name="use", description="Use an item from your inventory")
    async def slash_use(self, interaction: discord.Interaction, item: str):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        await _process_use(interaction, item)

    @app_commands.command(name="history", description="View your recent pull history")
    async def slash_history(self, interaction: discord.Interaction):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        await _process_history(interaction)

    @app_commands.command(name="leaderboard", description="View the pull leaderboard")
    async def slash_leaderboard(self, interaction: discord.Interaction):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        await _process_leaderboard(interaction)

    @app_commands.command(name="stats", description="View your gacha stats")
    async def slash_stats(self, interaction: discord.Interaction):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        await _process_stats(interaction)


    # ---------- NEW: TEXT COMMANDS ($$ prefix) ----------
    
    @commands.command(name="wish", description="Perform gacha pulls (1 or 10)")
    async def text_wish(self, ctx: commands.Context, amount: int = 1):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel.")
            return
        await _text_process_wish(ctx, amount)

    @commands.command(name="inventory", description="View your inventory")
    async def text_inventory(self, ctx: commands.Context):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel.")
            return
        await _text_process_inventory(ctx)

    @commands.command(name="use", description="Use an item from your inventory")
    async def text_use(self, ctx: commands.Context, item: str):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel.")
            return
        await _text_process_use(ctx, item)

    @commands.command(name="history", description="View your recent pull history")
    async def text_history(self, ctx: commands.Context):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel.")
            return
        await _text_process_history(ctx)

    @commands.command(name="leaderboard", description="View the pull leaderboard")
    async def text_leaderboard(self, ctx: commands.Context):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel.")
            return
        await _text_process_leaderboard(ctx)

    @commands.command(name="stats", description="View your gacha stats")
    async def text_stats(self, ctx: commands.Context):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel.")
            return
        await _text_process_stats(ctx)

    # ---------- MODERATOR COMMAND (Slash & Text) ----------
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
    
    # NEW: Text version of the moderator command
    @commands.command(name="setpity", description="Set a user's pity values (moderator only)")
    async def text_setpity(self, ctx: commands.Context, member: discord.Member, pity_5: int = 0, pity_4: int = 0, total_pulls: int = 0):
        if not any(r.id in MODERATOR_ROLE_IDS for r in ctx.author.roles):
            await ctx.send("🚫 You do not have permission to use this command.") 
            return
        
        update_pity_data(member.id, pity_5, pity_4, total_pulls)
        await ctx.send(f"✅ Pity data for {member.mention} updated: 5-star pity: {pity_5}, 4-star pity: {pity_4}, Total pulls: {total_pulls}")

# --- COG SETUP FUNCTION ---
# ADDED: This function is required for asynchronous loading (setup_hook in bot.py)
async def setup(bot):
    await bot.add_cog(GachaCog(bot))
