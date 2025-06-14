import os
import re
import logging
from datetime import datetime
from typing import Dict, Optional
from dotenv import load_dotenv
import discord
from discord.ext import commands
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from game_session import GameSession

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
            
        # Active sessions per channel
        self.active_sessions: Dict[int, GameSession] = {}

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
        
        # Configure logging
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
        """Initialize Google Sheets API service"""
        try:
            service_account_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', 'service-account.json')
            
            if not os.path.exists(service_account_file):
                raise FileNotFoundError(
                    f"Service account file not found at {service_account_file}"
                )
            
            credentials = service_account.Credentials.from_service_account_file(
                service_account_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            return build('sheets', 'v4', credentials=credentials)
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Google Sheets: {str(e)}")
            raise

class Commands(commands.Cog):
    def __init__(self, bot: PokerPal):
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
            await ctx.send("❌ Invalid command. Use '!po help' to see available commands.")
            return

        command = args[0].lower()
        channel_id = ctx.channel.id

        # Handle commands that don't require active session first
        if command == 'help':
            await self.send_help(ctx)
            return
        elif command == 'events' or command == 'event':
            session = self.bot.active_sessions.get(channel_id)
            if not session:
                await ctx.send("❌ No active game session. Start one with !po start")
                return
            events_display = session.format_events()
            await ctx.send(events_display)
            return
        elif command == 'start':
            if len(args) < 3:
                await ctx.send("❌ Invalid start command. Format: !po start <buy-in> <player1,player2,...>")
                return
                
            try:
                buy_in = float(args[1])
                # Join all remaining args and split by comma, then strip whitespace
                players_str = ' '.join(args[2:])
                players = [p.strip() for p in players_str.split(',') if p.strip()]
                
                if not players:
                    await ctx.send("❌ No valid players provided. Format: !po start <buy-in> <player1,player2,...>")
                    return
                    
                # If there's an active session, end it first
                if channel_id in self.bot.active_sessions:
                    old_session = self.bot.active_sessions[channel_id]
                    success, message = old_session.get_player_pnl()
                    if success:
                        await ctx.send("📊 **Final Results of Previous Session:**\n" + message)
                    del self.bot.active_sessions[channel_id]
                    
                # Create new session
                session = GameSession(buy_in, players)
                self.bot.active_sessions[channel_id] = session
                
                # Send success message first
                total_prize = len(players) * buy_in
                message = [
                    "🎲 **New Poker Session Started!**",
                    f"💵 Buy-in: ${buy_in}",
                    f"👥 Players: {', '.join(players)}",
                    f"💰 Prize Pool: ${total_prize}",
                    f"\n🎮 Game #1 is starting now!"
                ]
                await ctx.send("\n".join(message))
                
                # Then update spreadsheet
                try:
                    await self.create_session_sheet(ctx, session)
                except Exception as e:
                    self.logger.error(f"Failed to create session sheet: {str(e)}")
                    await ctx.send("⚠️ Warning: Failed to save to spreadsheet, but game will continue.")
                
            except ValueError:
                await ctx.send("❌ Invalid buy-in amount. Please provide a number.")
                return
            except Exception as e:
                self.logger.error(f"Unexpected error in start command: {str(e)}")
                await ctx.send("❌ An error occurred while starting the session. Please try again.")
                return

        # All other commands require an active session
        session = self.bot.active_sessions.get(channel_id)
        if not session:
            await ctx.send("❌ No active game session. Start one with !po start")
            return

        if command == 'in':
            # Get player name by joining remaining args to handle spaces
            if len(args) < 2:
                await ctx.send("❌ Invalid command. Format: !po in <player-name>")
                return
                
            player_name = ' '.join(args[1:]).strip()
            if not player_name:
                await ctx.send("❌ Invalid command. Format: !po in <player-name>")
                return
                
            success, message = session.add_player(player_name)
            await ctx.send(message)
            if success:
                try:
                    await self.update_session_sheet(ctx, session)
                except Exception as e:
                    self.logger.error(f"Failed to update session sheet: {str(e)}")
                    await ctx.send("⚠️ Warning: Failed to save to spreadsheet, but game will continue.")

        elif command == 'out':
            # Get player name by joining remaining args to handle spaces
            if len(args) < 2:
                await ctx.send("❌ Invalid command. Format: !po out <player-name>")
                return
                
            player_name = ' '.join(args[1:]).strip()
            if not player_name:
                await ctx.send("❌ Invalid command. Format: !po out <player-name>")
                return
                
            success, message = session.remove_player(player_name)
            await ctx.send(message)
            if success:
                try:
                    await self.update_session_sheet(ctx, session)
                except Exception as e:
                    self.logger.error(f"Failed to update session sheet: {str(e)}")
                    await ctx.send("⚠️ Warning: Failed to save to spreadsheet, but game will continue.")

        elif command == 'win':
            if len(args) < 2:
                await ctx.send("❌ Invalid command. Format: !po win <player-name>")
                return
                
            winner = ' '.join(args[1:]).strip()
            success, message = session.set_winner(winner)
            await ctx.send(message)
            if success:
                try:
                    await self.update_session_sheet(ctx, session)
                except Exception as e:
                    self.logger.error(f"Failed to update session sheet: {str(e)}")
                    await ctx.send("⚠️ Warning: Failed to save to spreadsheet, but game will continue.")

        elif command == 'pnl':
            # Handle pnl for specific player with spaces in name
            player_name = None
            if len(args) > 1:
                player_name = ' '.join(args[1:]).strip()
                
            success, message = session.get_player_pnl(player_name)
            await ctx.send(message)
            
        elif command == 'end':
            success, message = session.get_player_pnl()
            if success:
                await ctx.send("📊 **Final Session Results:**\n" + message)
            del self.bot.active_sessions[channel_id]
            await ctx.send("👋 Session ended!")
            
    async def send_help(self, ctx: commands.Context):
        """Send help message"""
        help_text = """
🎮 **Poker Manager Bot Commands**

**Game Session Commands:**
`!po start <buy-in> <player1,player2,...>` - Start new session (ends current session if exists)
`!po in <player>` - Add player to session
`!po out <player>` - Remove player from session
`!po win <player>` - Record game winner (auto-starts next game)
`!po end` - End current session and show final results

**Information Commands:**
`!po events` - Show session history
`!po pnl` - Show all players' profit/loss
`!po pnl <player>` - Show specific player's profit/loss

**Example:**
```
!po start 500 Tuyen, Truong, Cuong
!po win Tuyen
!po in Hung
!po pnl
!po end
```
"""
        await ctx.send(help_text)

    async def create_session_sheet(self, ctx: commands.Context, session: GameSession):
        """Create a new sheet for the session"""
        try:
            base_sheet_name = f"Session_{session.date}"
            sheet_name = base_sheet_name
            counter = 1
            
            # Get existing sheets
            spreadsheet = self.sheets_service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            # Get list of existing sheet names
            existing_sheets = [
                sheet['properties']['title'] 
                for sheet in spreadsheet.get('sheets', [])
            ]
            
            # Find a unique name by adding counter if needed
            while sheet_name in existing_sheets:
                counter += 1
                sheet_name = f"{base_sheet_name}_{counter}"
            
            self.logger.info(f"Creating new sheet: {sheet_name}")
            
            # Store the sheet name in the session for later use
            session.sheet_name = sheet_name
            
            # Create new sheet with formatting
            request = {
                'requests': [
                    {
                        'addSheet': {
                            'properties': {
                                'title': sheet_name,
                                'gridProperties': {
                                    'rowCount': 200,
                                    'columnCount': 26  # Increased for more players
                                }
                            }
                        }
                    },
                    # Hide gridlines
                    {
                        'updateSheetProperties': {
                            'properties': {
                                'sheetId': None,  # Will be filled after sheet creation
                                'gridProperties': {
                                    'hideGridlines': True
                                }
                            },
                            'fields': 'gridProperties.hideGridlines'
                        }
                    }
                ]
            }
            
            # Create the sheet first
            response = self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=request
            ).execute()
            
            # Get the new sheet ID
            new_sheet_id = None
            for reply in response.get('replies', []):
                if 'addSheet' in reply:
                    new_sheet_id = reply['addSheet']['properties']['sheetId']
                    break
            
            if new_sheet_id is None:
                raise Exception("Failed to get new sheet ID")
            
            # Apply formatting
            format_request = {
                'requests': [
                    # Format header section
                    {
                        'repeatCell': {
                            'range': {
                                'sheetId': new_sheet_id,
                                'startRowIndex': 0,
                                'endRowIndex': 2,
                                'startColumnIndex': 0,
                                'endColumnIndex': 2
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'backgroundColor': {
                                        'red': 0.95,
                                        'green': 0.95,
                                        'blue': 0.95
                                    },
                                    'textFormat': {
                                        'bold': True
                                    }
                                }
                            },
                            'fields': 'userEnteredFormat(backgroundColor,textFormat)'
                        }
                    },
                    # Format player stats header
                    {
                        'repeatCell': {
                            'range': {
                                'sheetId': new_sheet_id,
                                'startRowIndex': 2,
                                'endRowIndex': 3,
                                'startColumnIndex': 0,
                                'endColumnIndex': 26
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'backgroundColor': {
                                        'red': 0.8,
                                        'green': 0.8,
                                        'blue': 0.95
                                    },
                                    'textFormat': {
                                        'bold': True
                                    }
                                }
                            },
                            'fields': 'userEnteredFormat(backgroundColor,textFormat)'
                        }
                    },
                    # Format player stats rows
                    {
                        'repeatCell': {
                            'range': {
                                'sheetId': new_sheet_id,
                                'startRowIndex': 3,
                                'endRowIndex': 7,
                                'startColumnIndex': 0,
                                'endColumnIndex': 26
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'backgroundColor': {
                                        'red': 0.95,
                                        'green': 0.95,
                                        'blue': 1.0
                                    }
                                }
                            },
                            'fields': 'userEnteredFormat(backgroundColor)'
                        }
                    },
                    # Format events header
                    {
                        'repeatCell': {
                            'range': {
                                'sheetId': new_sheet_id,
                                'startRowIndex': 8,
                                'endRowIndex': 9,
                                'startColumnIndex': 0,
                                'endColumnIndex': 5
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'backgroundColor': {
                                        'red': 0.8,
                                        'green': 0.9,
                                        'blue': 0.8
                                    },
                                    'textFormat': {
                                        'bold': True
                                    }
                                }
                            },
                            'fields': 'userEnteredFormat(backgroundColor,textFormat)'
                        }
                    },
                    # Add borders around player stats
                    {
                        'updateBorders': {
                            'range': {
                                'sheetId': new_sheet_id,
                                'startRowIndex': 2,
                                'endRowIndex': 7,
                                'startColumnIndex': 0,
                                'endColumnIndex': 26
                            },
                            'top': {
                                'style': 'SOLID',
                                'width': 1,
                                'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}
                            },
                            'bottom': {
                                'style': 'SOLID',
                                'width': 1,
                                'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}
                            },
                            'left': {
                                'style': 'SOLID',
                                'width': 1,
                                'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}
                            },
                            'right': {
                                'style': 'SOLID',
                                'width': 1,
                                'color': {'red': 0.7, 'green': 0.7, 'blue': 0.7}
                            }
                        }
                    }
                ]
            }
            
            # Apply formatting
            self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=format_request
            ).execute()
            
            self.logger.info(f"Successfully created sheet: {sheet_name}")
            
            # Add session info
            self.logger.info("Adding session info")
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A1:B2",
                valueInputOption='RAW',
                body={
                    'values': [
                        ["Date", session.date],
                        ["Buy-in Amount", session.buy_in]
                    ]
                }
            ).execute()
            
            # Add player stats header and initial data
            self.update_player_stats(session, sheet_name)
            
            # Add event tracking headers
            self.logger.info("Adding tracking headers")
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A9:E9",
                valueInputOption='RAW',
                body={
                    'values': [["Date", "Event Type", "Player Name", "Action", "Current Stack"]]
                }
            ).execute()
            
            # Add initial tracking data
            tracking_data = session.get_tracking_data()
            if tracking_data:
                self.logger.info("Adding initial tracking data")
                self.sheets_service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!A10:E10",
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body={'values': tracking_data}
                ).execute()
            
            self.logger.info(f"Successfully set up sheet: {sheet_name}")
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Error creating session sheet: {error_msg}")
            if "Invalid value" in error_msg:
                await ctx.send("❌ Error: Invalid characters in player names or values")
            elif "insufficient permissions" in error_msg.lower():
                await ctx.send("❌ Error: Bot doesn't have permission to access the spreadsheet")
            elif "not found" in error_msg.lower():
                await ctx.send("❌ Error: Spreadsheet not found. Please check the spreadsheet ID")
            else:
                await ctx.send("❌ Error creating game sheet. Please check bot permissions and spreadsheet settings.")
            raise

    def update_player_stats(self, session: GameSession, sheet_name: str):
        """Update the player statistics section in columns"""
        # Get all players who have ever been in the game
        all_players = sorted(list(set(session.player_join_game.keys())))
        
        # Create column headers (player names)
        headers = ["Games in Session", ""] + all_players
        
        # Create rows for each stat
        games_played = ["Games Played", session.game_count - 1]
        games_won = ["Games Won", ""]
        total_buyin = ["Total Buy-in", ""]
        net_pnl = ["Net P/L", ""]
        
        # Fill in stats for each player
        for player in all_players:
            # Games played by this player
            played = session.get_player_games_played(player)
            games_played.append(played)
            
            # Games won by this player
            won = session.win_counts.get(player, 0)
            games_won.append(won)
            
            # Total buy-in for this player
            buyin = session.buy_in * played
            total_buyin.append(buyin)
            
            # Net P/L for this player
            winnings = session.total_winnings.get(player, 0)
            pnl = winnings - buyin
            net_pnl.append(pnl)
        
        # Update the sheet
        self.sheets_service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet_name}!A3:Z7",
            valueInputOption='RAW',
            body={
                'values': [
                    headers,
                    games_played,
                    games_won,
                    total_buyin,
                    net_pnl
                ]
            }
        ).execute()

    async def update_session_sheet(self, ctx: commands.Context, session: GameSession):
        """Update the session sheet with new events"""
        try:
            # Use the stored sheet name from session creation
            if not hasattr(session, 'sheet_name'):
                raise Exception("Sheet name not found in session")
                
            sheet_name = session.sheet_name
            
            # Update player stats
            self.update_player_stats(session, sheet_name)
            
            # Update tracking data - clear existing data first
            self.sheets_service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A10:E1000"
            ).execute()
            
            # Then add all tracking data
            tracking_data = session.get_tracking_data()
            if tracking_data:
                self.sheets_service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!A10:E{9+len(tracking_data)}",
                    valueInputOption='RAW',
                    body={'values': tracking_data}
                ).execute()
            
        except Exception as e:
            self.logger.error(f"Error updating session sheet: {str(e)}")
            await ctx.send("⚠️ Error updating game sheet. Game will continue without sheet tracking.")

    async def finalize_session_sheet(self, ctx: commands.Context, session: GameSession):
        """Finalize the session sheet with results"""
        try:
            sheet_name = f"Session_{session.date}"
            
            # Update session info one last time
            await self.update_session_sheet(ctx, session)
            
            # Add final results headers
            results_start_row = 8 + len(session.get_tracking_data()) + 2
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A{results_start_row}:E{results_start_row}",
                valueInputOption='RAW',
                body={
                    'values': [["Player Name", "Buy-in", "Rebuys", "Final Stack", "Net Profit/Loss"]]
                }
            ).execute()
            
            # Add final results
            results = session.get_final_results()
            results_data = [[r["Player Name"], r["Buy-in"], r["Rebuys"], 
                           r["Final Stack"], r["Net Profit/Loss"]] for r in results]
            
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A{results_start_row+1}:E{results_start_row+len(results)}",
                valueInputOption='RAW',
                body={'values': results_data}
            ).execute()
            
            self.logger.info(f"Finalized session sheet: {sheet_name}")
            
        except Exception as e:
            self.logger.error(f"Error finalizing session sheet: {str(e)}")
            await ctx.send("⚠️ Error updating final results in sheet.")

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