# xp_reporter_main.py (FINAL VERSION - Rift Tokens & Multipliers Updated + TEMP DEBUG)
import discord
import re
import math 
import traceback
from discord.ext import commands
# Ensure your bot_config.py has the correct list import: SUBMISSION_APPROVER_ROLE_IDS
from bot_config import INPUT_CHANNEL_IDS, OUTPUT_CHANNEL_IDS, SUBMISSION_APPROVER_ROLE_IDS 

# --- XP & CROWN SYSTEM CONSTANTS ---
EMOJI_STR1 = "⭐"
EMOJI_STR2 = "📊"
EMOJI_STR3 = "✨"

BASE_CROWNS = 500

# --- TRAINING TIER DATA ---
def get_training_tier_data(level):
    """
    Calculates the base point gain and returns the Training Tier (TT) number.
    TT1 (1-10): 100 XP, Tier 1
    TT2 (11-20): 150 XP, Tier 2
    TT3 (21-30): 200 XP, Tier 3
    """
    if 1 <= level <= 10:
        return {"base_xp": 100, "tier": 1}
    elif 11 <= level <= 20:
        return {"base_xp": 150, "tier": 2}
    elif 21 <= level <= 30:
        return {"base_xp": 200, "tier": 3}
    else:
        # Default tier for levels outside 1-30 or 0
        return {"base_xp": 100, "tier": 1}

# Activity Multipliers (ONLY activities that will be processed automatically)
ACTIVITY_MULTIPLIERS = {
    "troll mission": 1.0,
    "solo training": 1.0,
    "afk farm i": 1.0,
    "afk farm ii": 1.0,
    "afk farm iii": 1.15,
}

# The only activities that will be automatically processed (lower case keys)
APPROVED_ACTIVITIES = list(ACTIVITY_MULTIPLIERS.keys())


# --- COG CLASS ---
class XPReporterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    # --- Actual Logic to Parse Submission (Multiline Key-Value) ---
    def _parse_xp_submission(self, message):
        """
        Parses the multiline message content for XP submission data.
        """
        content = message.content.strip()
        data = {}
        
        try:
            # 1. Character Name: Captures everything after the key up to the next newline.
            name_match = re.search(r"\*\*Character Name\(s\):\*\*(.*?)\n", content, re.IGNORECASE)
            data['name'] = name_match.group(1).strip() if name_match else None
            
            # 2. Character Level: Captures digits
            level_match = re.search(r"\*\*Character Level:\*\*\s*(\d+)", content, re.IGNORECASE)
            data['level'] = int(level_match.group(1).strip()) if level_match else None
            
            # 3. Progression Type: Captures everything after the key up to the next bold key or end of message.
            progression_match = re.search(r"\*\*Type of Progression:\*\*(.*?)(?=\*\*|\Z)", content, re.IGNORECASE | re.DOTALL)
            data['progression'] = progression_match.group(1).strip() if progression_match else None
            
            # 4. XP Boost: Captures digits followed by %
            xp_boost_match = re.search(r"\*\*Boost\(s\) for XP:\*\*\s*(\d+)%", content, re.IGNORECASE)
            # Store boost as a decimal multiplier (e.g., 10% -> 0.10)
            data['xp_boost'] = int(xp_boost_match.group(1).strip()) / 100 if xp_boost_match else 0.0
            
            # 5. Crowns Boost: Captures digits followed by %
            crowns_boost_match = re.search(r"\*\*Boost\(s\) for Crowns:\*\*\s*(\d+)%", content, re.IGNORECASE)
            # Store boost as a decimal multiplier
            data['crowns_boost'] = int(crowns_boost_match.group(1).strip()) / 100 if crowns_boost_match else 0.0
            
            # 6. Final check: Ignore if any crucial field is missing
            if not all([data['name'], data['level'], data['progression']]):
                return {'valid': False, 'reason': 'Missing Field'}
            
        except Exception:
            # If any regex or conversion fails (e.g., level isn't a number)
            return {'valid': False, 'reason': 'Format Error'}

        data['valid'] = True
        return data


    # --- Listener for XP Submission ---
    @commands.Cog.listener()
    async def on_message(self, message):
        # 1. Pre-check and Channel check
        if message.author.bot or message.channel.id not in INPUT_CHANNEL_IDS:
            return
        
        # Only process messages that look like submissions (starts with the character name field)
        if not message.content.strip().lower().startswith('**character name(s):**'):
            return 

        data = self._parse_xp_submission(message)
        
        # 2. Handle Parsing Failure (Incorrect format)
        if not data['valid']:
            await message.add_reaction('❌') # Deny reaction for format error
            # Send a helpful temporary message to the user in the input channel
            await message.channel.send(
                f"{message.author.mention}, your submission failed to parse. Please ensure it exactly matches the expected format, including the bold text and colons.",
                delete_after=15 # delete after 15 seconds to keep the channel clean
            )
            print(f"DEBUG: XP submission denied (Format Error) from {message.author.name}")
            return

        # 3. Handle Activity Validation (The user's core requirement)
        progression_key = data['progression'].lower()
        
        if progression_key not in APPROVED_ACTIVITIES:
            # Deny, ping mods (using the SUBMISSION_APPROVER_ROLE_IDS from bot_config)
            await message.add_reaction('❌') # Deny reaction for unknown activity
            
            mod_pings = " ".join([message.guild.get_role(rid).mention for rid in SUBMISSION_APPROVER_ROLE_IDS if message.guild.get_role(rid)])
            
            denial_embed = discord.Embed(
                title="🚫 Submission Denied - Unknown Activity",
                description=(
                    f"{message.author.mention}, the activity **'{data['progression']}'** is not an automatically recognized progression type. "
                    f"Only the following are automatically graded: {', '.join([a.title() for a in APPROVED_ACTIVITIES])}.\n\n"
                    f"If this is correct, {mod_pings} need to manually review and approve this submission."
                ),
                color=discord.Color.red()
            )
            # Send denial message in the input channel for immediate feedback
            await message.channel.send(embed=denial_embed)
            print(f"DEBUG: XP submission denied (Unknown Activity: {data['progression']}) from {message.author.name}")
            return
            
        # 4. Process Allowed Activity (Success)
        try:
            # --- TIER AND XP CALCULATION ---
            tier_data = get_training_tier_data(data['level'])
            training_tier = tier_data['tier']
            base_point_gain = tier_data['base_xp']
            
            # Get base multiplier for the approved activity
            base_multiplier = ACTIVITY_MULTIPLIERS.get(progression_key, 1.0) 
            
            # Calculate final XP multiplier: Base + (Base * User Boost)
            xp_boost_percent = data.get('xp_boost', 0.0)
            total_multiplier = base_multiplier + (base_multiplier * xp_boost_percent)

            # Calculate Gains (XP is rounded down, Crowns is rounded to nearest integer)
            final_xp_gain = math.floor(base_point_gain * total_multiplier)
            
            crowns_boost_percent = data.get('crowns_boost', 0.0)
            final_crown_gain = int(BASE_CROWNS * (1.0 + crowns_boost_percent))
            
            # --- RIFT TOKEN CALCULATION (NEW LOGIC) ---
            rift_tokens = 0
            
            # --- TEMPORARY DEBUGGING PRINTS (START) ---
            print(f"DEBUG_XP: Progression Key: {progression_key}")
            print(f"DEBUG_XP: Training Tier: {training_tier}")
            # --- TEMPORARY DEBUGGING PRINTS (END) ---

            if progression_key == "troll mission":
                # Rule: Troll Mission rewards: [Training Tier x 1] Rift Token
                rift_tokens = training_tier * 1
            
            # --- TEMPORARY DEBUGGING PRINT ---
            print(f"DEBUG_XP: Rift Tokens Calculated: {rift_tokens}")
            # --- END TEMPORARY DEBUGGING PRINT ---
            
            # --- Formatting and Output ---
            final_gains_line = f"{final_xp_gain} XP"
            non_xp_gains_list = [f"{final_crown_gain} Crowns"]
            
            if rift_tokens > 0:
                non_xp_gains_list.append(f"{rift_tokens} Rift Tokens") # Add Rift Tokens
                
            final_gains_line += ", " + ", ".join(non_xp_gains_list)


            # --- OUTPUT CHANNEL DETERMINATION ---
            try:
                input_index = INPUT_CHANNEL_IDS.index(message.channel.id)
                output_channel_id = OUTPUT_CHANNEL_IDS[input_index]
                output_channel = self.bot.get_channel(output_channel_id)
            except (ValueError, IndexError):
                output_channel = None 

            # Add reaction for success
            await message.add_reaction('✅')

            # --- SEND FINAL EMBED ---
            embed = discord.Embed(
                title=f"✅ Progression Logged: {data['progression'].title()}",
                description=f"Submitted by {message.author.mention}", # PINGS SENDER
                color=discord.Color.green()
            )
            embed.add_field(name="Character(s)", value=data['name'], inline=True)
            embed.add_field(name="Level", value=data['level'], inline=True)
            embed.add_field(name="Training Tier", value=f"TT{training_tier}", inline=True) # Display TT (New field)
            embed.add_field(name="Base Multiplier", value=f"{base_multiplier:.2f}x", inline=True)
            embed.add_field(name="XP Boost", value=f"{xp_boost_percent*100:.0f}%", inline=True)
            embed.add_field(name="Crowns Boost", value=f"{crowns_boost_percent*100:.0f}%", inline=True)
            embed.add_field(name=f"{EMOJI_STR1} Total Gains", value=f"**{final_gains_line}**", inline=False)
            embed.set_footer(text=f"Base XP: {base_point_gain} | Final Multiplier: {total_multiplier:.2f}x")

            print(f"✅ Successfully processed XP submission from {message.author.name}.")

            if output_channel:
                await output_channel.send(embed=embed)
            else:
                # Fallback to input channel
                await message.channel.send(embed=embed)
                
        except Exception as e:
            print(f"❌ ERROR PROCESSING XP SUBMISSION: {e}")
            traceback.print_exc()
            await message.channel.send(f"❌ An internal error occurred while calculating gains. Mod attention needed. ({message.author.mention})")
            await message.add_reaction('❓') # Reaction for internal error
            
# --- COG SETUP FUNCTION ---
async def setup(bot):
    await bot.add_cog(XPReporterCog(bot))
