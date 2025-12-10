# gacha_main.py (FINAL LOGIC IMPLEMENTATION with updated loot pools and PITY SYSTEM)
import discord
from discord.ext import commands
import sqlite3
import random
import time
from discord import app_commands

from bot_config import GACHA_CHANNEL_ID, MODERATOR_ROLE_IDS, DB_NAME 

# --- LOOT POOLS & CONSTANTS ---
RATE_5_STAR = 0.006  # 0.6% base rate
RATE_4_STAR = 0.05   # 5.0% base rate
PITY_5_STAR_HARD = 60 # New Hard Pity at 60 pulls
PITY_30_CHANCE = 0.5 # 50% chance at pull 30

# UPDATED: Loot table based on the new structure provided (using integer keys for logic)
LOOT_TABLE = {
    3: [
        "Scrap Grade Weapon", "Scrap Grade Armor", 
        "50 XP Crystal", "100 XP Crystal", 
        "10,000 Crowns", "5 Totems (Tamer)", "6 VP Items (Forager)"
    ],
    4: [
        "Named Grade Weapon", "Named Grade Armor",
        "250 XP Crystal", "25,000 Crowns",
        "10 Totems (Tamer)", "15 VP Items (Forager)"
    ],
    5: [
        "Exalted Grade Weapon", "Exalted Grade Armor", "20% XP Multiplier (1 Week)",
        "500 XP Crystal", "50,000 Crowns",
        "20 Totems (Tamer)", "25 VP Items (Forager)"
    ]
}

# --- DATABASE HELPERS (Functionality unchanged, logic uses 'pity_5_star' as main counter) ---
def _get_conn():
    return sqlite3.connect(DB_NAME)

def get_user_pity_data(user_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        # 'pity_5_star' column is used as the single main pity counter since last 5-star
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

def add_item_to_inventory(user_id, item_name):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO inventory (user_id, item_name, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, item_name) DO UPDATE SET
                quantity = quantity + 1
        """, (user_id, item_name))
        conn.commit()
    finally:
        conn.close()

def log_pull_history(user_id, item_name, rarity):
    conn = _get_conn()
    timestamp = int(time.time())
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO pull_history (user_id, item_name, rarity, timestamp)
            VALUES (?, ?, ?, ?)
        """, (user_id, item_name, rarity, timestamp))
        conn.commit()
    finally:
        conn.close()


# --- CORE GACHA PULL LOGIC (REWRITTEN) ---

def pull_gacha_single(user_id, pity_data):
    # Use pity_5_star as the single main pity counter since last 5-star
    pity = pity_data["pity_5_star"]
    pity += 1 # 1. Increment pity at start of pull

    rarity = 3
    
    # 2. HARD PITY (60)
    if pity >= PITY_5_STAR_HARD:
        rarity = 5
        
    # 3. 50/50 CHANCE (30)
    elif pity == 30:
        if random.random() < PITY_30_CHANCE: # 50% chance success
            rarity = 5
        else: # 50% chance failure, but it's the 30th pull, so it guarantees a 4-star
            rarity = 4
            
    # 4. SOFT PITY (Every 10 pulls, not covered by the above)
    elif pity % 10 == 0:
        rarity = 4
    
    # 5. RANDOM ROLL (Standard Rates) - only roll if no pity condition was met (rarity still 3)
    else:
        roll = random.random()
        if roll < RATE_5_STAR:
            rarity = 5
        elif roll < RATE_5_STAR + RATE_4_STAR:
            rarity = 4
        # else rarity remains 3

    # 6. Get Item & Update Pity
    item_name = random.choice(LOOT_TABLE[rarity])
    
    # Update pity_data dictionary for the next pull
    pity_data["pity_5_star"] = pity # Set the counter to the *new* pity value
    pity_data["total_pulls"] += 1
    
    if rarity == 5:
        pity_data["pity_5_star"] = 0 # Reset pity counter upon getting a 5-star
        pity_data["pity_4_star"] = 0 # Reset 4-star tracker too (for consistency/unused DB field)
    # Note: 4-star pull does not reset pity in this new system.
        
    return rarity, item_name, pity_data


# --- UTILITY (Kept as is) ---
def is_gacha_channel_interaction(interaction: discord.Interaction):
    return interaction.channel_id == GACHA_CHANNEL_ID

def is_gacha_channel_context(ctx: commands.Context):
    return ctx.channel.id == GACHA_CHANNEL_ID


# --- WISH PROCESSOR (Slash Command) ---
async def _process_wish(interaction: discord.Interaction, amount: int):
    # Defer the response for a long task
    await interaction.response.defer()
    
    user_id = interaction.user.id
    pity_data = get_user_pity_data(user_id)
    results = {5: [], 4: [], 3: []}
    
    # 1. Perform Gacha Pulls
    for _ in range(amount):
        rarity, item_name, pity_data = pull_gacha_single(user_id, pity_data)
        
        results[rarity].append(item_name)
        
        # 2. Database writes (Update pity, inventory, and history)
        add_item_to_inventory(user_id, item_name)
        log_pull_history(user_id, item_name, rarity)
        
    # 3. Update Pity Data (one final write)
    update_pity_data(user_id, pity_data["pity_5_star"], pity_data["pity_4_star"], pity_data["total_pulls"])
    
    # 4. Format and send results
    def format_item_list(items, rarity):
        if not items:
            return ""
        if rarity == 5:
            return "\n".join(f"**🌟 {item}**" for item in items)
        if rarity == 4:
            return "\n".join(f"🔸 *{item}*" for item in items)
        if rarity == 3:
            return "\n".join(f"▪️ {item}" for item in items)

    output = [f"**{interaction.user.mention}'s {amount} Wish Results**:\n"]
    
    if results[5]:
        output.append("### 🌟 5-STAR ITEM(S) 🌟")
        output.append(format_item_list(results[5], 5))
        
    if results[4]:
        output.append("\n### 🔸 4-STAR ITEM(S) 🔸")
        output.append(format_item_list(results[4], 4))

    if results[3]:
        output.append("\n**3-Star Item(s):**")
        output.append(format_item_list(results[3], 3))

    # Updated Pity Display to reflect the new 60-pull hard pity
    footer = (
        f"\n---\n"
        f"Pulls until Guaranteed 5-Star: **{PITY_5_STAR_HARD - pity_data['pity_5_star']}** "
        f"({pity_data['pity_5_star']}/{PITY_5_STAR_HARD})"
    )
    output.append(footer)
    
    # Use follow-up since the response was deferred
    await interaction.followup.send("\n".join(output))


# --- WISH PROCESSOR (Text Command) ---
async def _text_process_wish(ctx: commands.Context, amount: int):
    user_id = ctx.author.id
    pity_data = get_user_pity_data(user_id)
    results = {5: [], 4: [], 3: []}
    
    # 1. Perform Gacha Pulls
    async with ctx.typing(): # Show that the bot is "typing" during the calculation
        for _ in range(amount):
            rarity, item_name, pity_data = pull_gacha_single(user_id, pity_data)
            
            results[rarity].append(item_name)
            
            # 2. Database writes
            add_item_to_inventory(user_id, item_name)
            log_pull_history(user_id, item_name, rarity)
            
        # 3. Update Pity Data
        update_pity_data(user_id, pity_data["pity_5_star"], pity_data["pity_4_star"], pity_data["total_pulls"])
    
    # 4. Format and send results
    def format_item_list(items, rarity):
        if not items:
            return ""
        if rarity == 5:
            return "\n".join(f"**🌟 {item}**" for item in items)
        if rarity == 4:
            return "\n".join(f"🔸 *{item}*" for item in items)
        if rarity == 3:
            return "\n".join(f"▪️ {item}" for item in items)

    output = [f"**{ctx.author.mention}'s {amount} Wish Results**:\n"]
    
    if results[5]:
        output.append("### 🌟 5-STAR ITEM(S) 🌟")
        output.append(format_item_list(results[5], 5))
        
    if results[4]:
        output.append("\n### 🔸 4-STAR ITEM(S) 🔸")
        output.append(format_item_list(results[4], 4))

    if results[3]:
        output.append("\n**3-Star Item(s):**")
        output.append(format_item_list(results[3], 3))

    # Updated Pity Display to reflect the new 60-pull hard pity
    footer = (
        f"\n---\n"
        f"Pulls until Guaranteed 5-Star: **{PITY_5_STAR_HARD - pity_data['pity_5_star']}** "
        f"({pity_data['pity_5_star']}/{PITY_5_STAR_HARD})"
    )
    output.append(footer)
    
    await ctx.send("\n".join(output))


# --- Placeholder functions (for non-wish commands) ---

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


# --- TEXT COMMAND PLACEHOLDERS ---
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


# --- COG CLASS (Commands) ---
class GachaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # SLASH COMMANDS
    @app_commands.command(name="wish", description="Perform gacha pulls (1 or 10)")
    async def slash_wish(self, interaction: discord.Interaction, amount: int = 1):
        if not is_gacha_channel_interaction(interaction):
            await interaction.response.send_message("🚫 Wrong channel.", ephemeral=True)
            return
        await _process_wish(interaction, amount) # Now calls the full logic

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


    # TEXT COMMANDS
    @commands.command(name="wish", description="Perform gacha pulls (1 or 10)")
    async def text_wish(self, ctx: commands.Context, amount: int = 1):
        if not is_gacha_channel_context(ctx):
            await ctx.send("🚫 Wrong channel.")
            return
        await _text_process_wish(ctx, amount) # Now calls the full logic

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


    # MODERATOR COMMAND (Slash & Text)
    @app_commands.command(name="setpity", description="Set a user's pity values (moderator only)")
    async def slash_setpity(self, interaction: discord.Interaction, member: discord.Member, pity_5: int = 0, pity_4: int = 0, total_pulls: int = 0):
        if not any(r.id in MODERATOR_ROLE_IDS for r in interaction.user.roles):
            await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
            return
        
        # Use pity_5 as the main counter for the new logic
        update_pity_data(member.id, pity_5, pity_4, total_pulls)
        await interaction.response.send_message(
            f"✅ Pity data for {member.mention} updated: Main Pity Counter: {pity_5}, Total pulls: {total_pulls}", 
            ephemeral=True
        )
    
    @commands.command(name="setpity", description="Set a user's pity values (moderator only)")
    async def text_setpity(self, ctx: commands.Context, member: discord.Member, pity_5: int = 0, pity_4: int = 0, total_pulls: int = 0):
        if not any(r.id in MODERATOR_ROLE_IDS for r in ctx.author.roles):
            await ctx.send("🚫 You do not have permission to use this command.") 
            return
        
        update_pity_data(member.id, pity_5, pity_4, total_pulls)
        await ctx.send(f"✅ Pity data for {member.mention} updated: Main Pity Counter: {pity_5}, Total pulls: {total_pulls}")


# --- COG SETUP FUNCTION ---
async def setup(bot):
    await bot.add_cog(GachaCog(bot))
