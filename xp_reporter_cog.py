# xp_reporter_cog.py (Fixed Activity Keys)
import discord
import re
import math 
from discord.ext import commands
from bot_config import INPUT_CHANNEL_IDS, OUTPUT_CHANNEL_IDS, SUBMISSION_APPROVER_ROLE_ID 

# --- XP & CROWN SYSTEM CONSTANTS ---
EMOJI_STR1 = "⭐"
EMOJI_STR2 = "📊"
EMOJI_STR3 = "✨"

BASE_CROWNS = 500

# --- TRAINING TIER DATA ---
def get_training_tier_data(level):
    """
    Calculates the base point gain and returns the Training Tier.
    """
    if 1 <= level <= 10:
        return {"base_xp": 100, "tier": 1}
    elif 11 <= level <= 20:
        return {"base_xp": 150, "tier": 2}
    elif 21 <= level <= 30:
        return {"base_xp": 200, "tier": 3}
    else:
        return {"base_xp": 100, "tier": 1}

# Activity Multipliers (FIXED: Added common variations for robustness)
ACTIVITY_MULTIPLIERS = {
    "solo training": 1.0,
    "wholesome training": 2.5,
    "wholesome roleplay": 2.5,  # <-- Added to handle "roleplay" submissions
    "battle training": 4.0,
    "battle roleplay": 4.0,    # <-- Added to handle "roleplay" submissions
    "afk farm i": 1.0,
    "afk farm ii": 1.0,
    "afk farm iii": 1.15,
    "troll mission": 1.0,
}

# --- REGEX ---
REGEX_CHARACTER_NAME = r"\*\*Character Name\(s\):\*\* (.*?)\n"
REGEX_CHARACTER_LEVEL = r"\*\*Character Level:\*\* (\d+)"
REGEX_PROGRESSION_TYPE = r"\*\*Type of Progression:\*\* (.*?)\n"
REGEX_CHANNEL_TO_XP_BOOST = r"\*\*Channel \(s\):\*\* .*?(?=\*\*Boost\(s\) for XP\*\*)"
REGEX_BOOSTS_XP = r"\*\*Boost\(s\) for XP:\*\* (.*?)\n"
REGEX_BOOSTS_CROWNS = r"\*\*Boost\(s\) for Crowns:\*\* (.*)"


def parse_boost_line(boosts_line):
    """Converts a boost string (e.g., '10%' or '2.5x') into an additive multiplier (e.g., 0.1 or 1.5)."""
    if boosts_line.lower() == 'n/a' or not boosts_line:
        return 0.0
    
    multiplier_additive = 0.0
    
    # 1. Look for percentage (e.g., 10%)
    percent_match = re.search(r"([\d\.]+)\s*%", boosts_line)
    if percent_match:
        try:
            multiplier_additive = float(percent_match.group(1)) / 100
        except:
            pass
        return multiplier_additive

    # 2. Look for 'x' multiplier (e.g., +2.5x or 2.5x)
    x_match = re.search(r"(\+?)\s*([\d\.]+)x", boosts_line, re.IGNORECASE)
    if x_match:
        try:
            multiplier_base = float(x_match.group(2))
            multiplier_additive = multiplier_base - 1.0
        except:
            pass
        return multiplier_additive
        
    return 0.0


class XPReporterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):

        if message.author.bot:
            return

        if message.channel.id not in INPUT_CHANNEL_IDS:
            return

        content = message.content
        data = {}
        
        flags = re.IGNORECASE | re.DOTALL

        # --- EXTRACT ALL FIELDS ---
        name_match = re.search(REGEX_CHARACTER_NAME, content, flags)
        level_match = re.search(REGEX_CHARACTER_LEVEL, content, flags)
        prog_match = re.search(REGEX_PROGRESSION_TYPE, content, flags)
        
        channel_block_match = re.search(REGEX_CHANNEL_TO_XP_BOOST, content, flags)
        
        boosts_xp_match = re.search(REGEX_BOOSTS_XP, content, flags)
        boosts_crowns_match = re.search(REGEX_BOOSTS_CROWNS, content, flags)
        
        # --- Format validation (All required fields must be present) ---
        if not (name_match and level_match and prog_match and boosts_xp_match and boosts_crowns_match):
            try:
                await message.add_reaction("❌")
            except:
                pass
            return

        # Extract data safely
        data['name'] = name_match.group(1).strip()
        
        try:
            data['level'] = int(level_match.group(1))
        except ValueError:
            data['level'] = 0

        data['progression'] = prog_match.group(1).strip()
        
        boosts_line_xp = boosts_xp_match.group(1).split('\n')[0].strip()
        boosts_line_crowns = boosts_crowns_match.group(1).split('\n')[0].strip()
        
        # --- PARSE SEPARATE BOOSTS ---
        trait_multiplier_additive_xp = parse_boost_line(boosts_line_xp)
        trait_multiplier_additive_crowns = parse_boost_line(boosts_line_crowns)
        
        # Normalize progression type
        prog_key = data['progression'].lower().split('[')[0].strip()
        base_multiplier = ACTIVITY_MULTIPLIERS.get(prog_key, None)

        # ---------------------------------------------------------------------
        # FLAG INVALID PROGRESSION TYPE
        # ---------------------------------------------------------------------
        if base_multiplier is None:
            approver_mention = f"<@&{SUBMISSION_APPROVER_ROLE_ID}>"
            await message.add_reaction("❓")

            await message.channel.send(
                f"🚨 **Flagged Submission for Review!** {approver_mention}\n\n"
                f"Unrecognized activity type: `{data['progression']}` (Submitted by {message.author.mention})\n"
                f"Please review this submission and apply XP manually."
            )
            return

        # --- XP & CROWN CALCULATION ---
        try:
            char_level = data['level']
            tier_data = get_training_tier_data(char_level)

            base_point_gain = tier_data["base_xp"]
            training_tier = tier_data["tier"]

            total_multiplier_xp = base_multiplier + trait_multiplier_additive_xp
            total_xp_gain = int(base_point_gain * total_multiplier_xp)

            if total_xp_gain <= 0:
                await message.add_reaction("⛔")
                return
            
            total_crown_gain = 0
            if prog_key in ["troll mission"]:
                total_multiplier_crowns = base_multiplier + trait_multiplier_additive_crowns
                total_crown_gain = math.ceil(BASE_CROWNS * total_multiplier_crowns)
            
        except Exception as e:
            print(f"XP Calculation Error:", e)
            await message.add_reaction("⛔")
            return

        # --- NON-XP REWARDS & FINAL MESSAGE ASSEMBLY ---
        non_xp_gains_list = []

        if prog_key in ["troll mission"]:
            if total_crown_gain > 0:
                non_xp_gains_list.append(f"{total_crown_gain:,} Crowns")
            non_xp_gains_list.append(f"{training_tier} Rift Token{'s' if training_tier > 1 else ''}")

        final_gains_line = f"{total_xp_gain:,} XP"
        if non_xp_gains_list:
            final_gains_line += ", " + ", ".join(non_xp_gains_list)

        # --- OUTPUT CHANNEL DETERMINATION ---
        try:
            input_index = INPUT_CHANNEL_IDS.index(message.channel.id)
            output_channel_id = OUTPUT_CHANNEL_IDS[input_index]
            output_channel = self.bot.get_channel(output_channel_id)
        except (ValueError, IndexError):
            output_channel = None 

        if output_channel:
            
            approved_message = f"""
{EMOJI_STR1} **Character Name(s):** {data['name']}
{EMOJI_STR2} **Type of Progression:** {data['progression']}
{EMOJI_STR3} **Gains:** {final_gains_line}
            """

            await output_channel.send(approved_message)
            await message.add_reaction("✅")
        else:
            print(f"[ERROR] Output channel not found or misconfigured for input channel ID: {message.channel.id}.")


def setup(bot):
    bot.add_cog(XPReporterCog(bot))
    print("XP Reporter Cog Loaded")