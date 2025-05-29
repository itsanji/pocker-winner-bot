import os
import re
import logging
from datetime import datetime
from typing import Tuple, Optional
from dotenv import load_dotenv
import discord
from discord.ext import commands
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class PokerPal(commands.Bot):
    def __init__(self):
        # Initialize Discord bot with command prefix
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        
        # Setup logging first
        self.setup_logging()
        
        # Initialize Google Sheets connection
        self.sheets_service = self._init_google_sheets()
        self.spreadsheet_id = os.getenv('GOOGLE_SHEETS_ID')
        if not self.spreadsheet_id:
            raise ValueError("GOOGLE_SHEETS_ID not found in environment variables")

    async def setup_hook(self):
        """Setup hook to add commands"""
        await self.add_cog(Commands(self))

    def setup_logging(self):
        """Setup logging configuration"""
        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        # Get current date for log file name
        current_date = datetime.now().strftime('%Y-%m-%d')
        log_file = f'logs/discord_chat_log_{current_date}.log'
        
        # Configure logging with minimal format
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        self.logger = logging.getLogger('PokerPal')

    def _init_google_sheets(self):
        """Initialize Google Sheets API service with service account"""
        try:
            # Look for service account file in current directory first
            service_account_file = 'service-account.json'
            
            # If not in current directory, check environment variable
            if not os.path.exists(service_account_file):
                service_account_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', 'service-account.json')
            
            if not os.path.exists(service_account_file):
                raise FileNotFoundError(
                    f"Service account file not found. Please place service-account.json in the current directory "
                    f"or set GOOGLE_SERVICE_ACCOUNT_FILE in .env"
                )
            
            self.logger.info(f"Using service account file: {service_account_file}")
            
            # Create credentials
            credentials = service_account.Credentials.from_service_account_file(
                service_account_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # Build and return the service
            service = build('sheets', 'v4', credentials=credentials)
            self.logger.info("Successfully initialized Google Sheets service")
            return service
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Google Sheets: {str(e)}")
            raise

class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger
        self.sheets_service = bot.sheets_service
        self.spreadsheet_id = bot.spreadsheet_id

    @commands.command()
    async def ping(self, ctx: commands.Context):
        """Simple ping command"""
        await ctx.send('pong')

    @commands.command()
    async def po(self, ctx: commands.Context, *args):
        """Handle poker commands"""
        if not args:
            await ctx.send("❌ Invalid command format. Use '!po help' to see the correct usage.")
            return
            
        # Handle help command
        if args[0] == 'help':
            help_text = """🎲 **PokerPal Commands** 🎲

!po <buy-in> <players-count> <winner>
  - Records a poker game result
  - <buy-in>: Amount each player paid (e.g., 400)
  - <players-count>: Number of players (e.g., 5)
  - <winner>: Winner's name (e.g., Tuyen)

Example:
  !po 400 5 Tuyen
  → Records: $400 buy-in, 5 players, TUYEN won
  → Total pool: $2000 (400 × 5)

Other Commands:
  !ping - Check if bot is alive
  !po help - Show this help message

Note: Winner names are automatically converted to uppercase."""
            await ctx.send(help_text)
            return
            
        # Parse command
        command = f"!po {' '.join(args)}"
        parsed = self.parse_command(command)
        if not parsed:
            await ctx.send("❌ Invalid command format. Use '!po help' to see the correct usage.")
            return
            
        # Send processing message
        await ctx.send("Processing your poker command... 🎲")
        
        # Save game
        buy_in, num_players, winner_name = parsed
        try:
            result = self.save_game(buy_in, num_players, winner_name)
            await ctx.send(result)
        except Exception as e:
            error_msg = f"Error recording game: {str(e)}"
            self.logger.error(error_msg)
            await ctx.send(error_msg)

    def parse_command(self, message: str) -> Optional[Tuple[float, int, str]]:
        """Parse the poker command message"""
        pattern = r'^!po\s+(\d+)\s+(\d+)\s+(\w+)$'
        match = re.match(pattern, message.strip())
        
        if not match:
            return None
            
        buy_in = float(match.group(1))
        num_players = int(match.group(2))
        winner_name = match.group(3)
        
        return buy_in, num_players, winner_name

    def get_or_create_today_sheet(self) -> str:
        """Get or create today's sheet"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        try:
            # Get spreadsheet to check existing sheets
            spreadsheet = self.sheets_service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            # Check if today's sheet exists
            sheet_exists = any(
                sheet['properties']['title'] == today 
                for sheet in spreadsheet.get('sheets', [])
            )
            
            if not sheet_exists:
                self.logger.info(f"Creating new sheet for {today}")
                
                # Create new sheet
                request = {
                    'requests': [{
                        'addSheet': {
                            'properties': {
                                'title': today,
                                'gridProperties': {
                                    'rowCount': 1000,
                                    'columnCount': 7
                                }
                            }
                        }
                    }]
                }
                
                self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body=request
                ).execute()
                
                # Add headers
                self.sheets_service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f'{today}!A1:G1',
                    valueInputOption='RAW',
                    body={
                        'values': [['No.', 'Winner', 'Players', 'Buy-in', 'Total Pool', 'Losers', 'Lost Amount']]
                    }
                ).execute()
                
                self.logger.info(f"Successfully created sheet for {today}")
            
        except HttpError as e:
            error_details = json.loads(e.content.decode('utf-8'))
            self.logger.error(f"Google Sheets API error: {error_details.get('error', {}).get('message')}")
            raise
        except Exception as e:
            self.logger.error(f"Error managing sheet: {str(e)}")
            raise
            
        return today

    def save_game(self, buy_in: float, num_players: int, winner_name: str) -> str:
        """Save game information to Google Sheets"""
        sheet_name = self.get_or_create_today_sheet()
        
        try:
            # Get current row count to determine the next number
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f'{sheet_name}!A:A'
            ).execute()
            
            # Calculate the next number (excluding header row)
            next_number = len(result.get('values', [])) if 'values' in result else 1
            
            # Calculate total pool
            total_pool = buy_in * num_players
            
            # Format winner name in uppercase
            winner_name = winner_name.upper()
            
            # Append new row
            self.sheets_service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f'{sheet_name}!A:G',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={
                    'values': [[
                        next_number,          # No.
                        winner_name,          # Winner
                        num_players,          # Players
                        buy_in,              # Buy-in
                        total_pool,          # Total Pool
                        "",                  # Losers (to be filled manually)
                        ""                   # Lost Amount (to be filled manually)
                    ]]
                }
            ).execute()
            
            self.logger.info(f"Successfully recorded game: Winner {winner_name}, {num_players} players, ${buy_in} buy-in, total pool ${total_pool}")
            return f"Game recorded: {winner_name} won! 🏆\nBuy-in: ${buy_in}\nPlayers: {num_players}\nTotal Pool: ${total_pool}"
            
        except HttpError as e:
            error_details = json.loads(e.content.decode('utf-8'))
            error_msg = f"Error saving to Google Sheets: {error_details.get('error', {}).get('message')}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Error saving game: {str(e)}"
            self.logger.error(error_msg)
            raise Exception(error_msg)

async def main():
    # Load environment variables
    load_dotenv()
    
    # Get Discord token
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise ValueError("DISCORD_TOKEN not found in environment variables")
        
    # Create and start bot
    bot = PokerPal()
    await bot.start(token)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 