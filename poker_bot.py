import os
import re
import json
import uuid
import time
import logging
import requests
from datetime import datetime
from typing import Tuple, Optional, Dict, List
from dotenv import load_dotenv
from rocketchat_API.rocketchat import RocketChat
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import websocket
import threading

class PokerBot:
    def __init__(self):
        load_dotenv()
        
        # Setup logging first
        self.setup_logging()
        
        # Initialize Rocket Chat connection
        self.server_url = os.getenv('ROCKET_CHAT_URL')
        self.username = os.getenv('ROCKET_CHAT_USER')
        self.password = os.getenv('ROCKET_CHAT_PASSWORD')
        self.rocket = RocketChat(
            self.username,
            self.password,
            server_url=self.server_url
        )
        
        # Initialize Google Sheets connection
        self.sheets_service = self._init_google_sheets()
        self.spreadsheet_id = os.getenv('GOOGLE_SHEETS_ID')
        if not self.spreadsheet_id:
            raise ValueError("GOOGLE_SHEETS_ID not found in environment variables")
        
        # WebSocket connection
        self.ws = None
        self.ws_connected = False
        self.is_logged_in = False
        self.is_subscribed = False
        self.room_id = None
        self.room_name = None
        
        # Message deduplication
        self.processed_messages = set()
        self.max_processed_messages = 1000  # Prevent memory growth
        
    def setup_logging(self):
        """Setup logging configuration"""
        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        # Get current date for log file name
        current_date = datetime.now().strftime('%Y-%m-%d')
        log_file = f'logs/chat_log_{current_date}.log'
        
        # Configure logging with minimal format
        logging.basicConfig(
            level=logging.INFO,  # Set to INFO for less verbose logs
            format='%(asctime)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        self.logger = logging.getLogger('PokerBot')
        
    def log_message(self, message_data: Dict):
        """Log a chat message with user and content"""
        try:
            timestamp = datetime.fromtimestamp(message_data.get('ts', {}).get('$date', 0) / 1000).strftime('%Y-%m-%d %H:%M:%S')
            username = message_data.get('u', {}).get('username', 'unknown')
            message = message_data.get('msg', '')
            room_name = self.room_name or 'unknown'
            
            log_entry = f"[{room_name}] {username}: {message}"
            self.logger.info(log_entry)
            
        except Exception as e:
            self.logger.error(f"Error logging message: {str(e)}")
    
    def get_available_rooms(self) -> List[Dict]:
        """Get list of available rooms"""
        rooms = []
        
        # Get public channels
        channels = self.rocket.channels_list().json()
        if channels.get('success'):
            for channel in channels.get('channels', []):
                rooms.append({
                    'id': channel['_id'],
                    'name': channel['name'],
                    'type': 'channel'
                })
        
        # Get private groups where bot is a member
        groups = self.rocket.groups_list().json()
        if groups.get('success'):
            for group in groups.get('groups', []):
                rooms.append({
                    'id': group['_id'],
                    'name': group['name'],
                    'type': 'private group'
                })
                
        return rooms
    
    def select_room(self) -> Tuple[str, str]:
        """Get room ID and name from environment variable or interactive selection"""
        # Check for ROOM_ID in environment
        env_room_id = os.getenv('ROOM_ID')
        if env_room_id:
            self.logger.info(f"Using room ID from environment: {env_room_id}")
            
            # Try to get room name from channels
            try:
                room_info = self.rocket.channels_info(room_id=env_room_id).json()
                if room_info.get('success'):
                    room_name = room_info['channel']['name']
                    self.logger.info(f"Found channel: {room_name}")
                    return env_room_id, room_name
            except:
                pass
                
            # Try to get room name from private groups
            try:
                room_info = self.rocket.groups_info(room_id=env_room_id).json()
                if room_info.get('success'):
                    room_name = room_info['group']['name']
                    self.logger.info(f"Found private group: {room_name}")
                    return env_room_id, room_name
            except:
                pass
                
            # If we can't get the name, just use the ID
            self.logger.warning("Could not get room name, using ID as name")
            return env_room_id, env_room_id
        
        # If no ROOM_ID in environment, do interactive selection
        rooms = self.get_available_rooms()
        
        if not rooms:
            raise ValueError("No available rooms found")
        
        # Print room list
        print("\nAvailable Rooms:")
        print("=" * 60)
        print(f"{'Number':<8} {'Name':<20} {'Type':<15} {'ID':<24}")
        print("-" * 60)
        
        for i, room in enumerate(rooms, 1):
            print(f"{i:<8} {room['name']:<20} {room['type']:<15} {room['id']:<24}")
        
        print("=" * 60)
        print("\nTip: You can set ROOM_ID in .env to skip this selection")
        
        # Get user selection
        while True:
            try:
                choice = input("\nSelect room number (or 'q' to quit): ")
                if choice.lower() == 'q':
                    raise KeyboardInterrupt
                    
                room_index = int(choice) - 1
                if 0 <= room_index < len(rooms):
                    selected_room = rooms[room_index]
                    self.logger.info(f"Selected room: {selected_room['name']} ({selected_room['type']})")
                    return selected_room['id'], selected_room['name']
                else:
                    print("Invalid selection. Please try again.")
            except ValueError:
                print("Please enter a valid number.")
            except KeyboardInterrupt:
                print("\nBot shutdown requested.")
                raise
    
    def parse_command(self, message: str) -> Optional[Tuple[float, int, str]]:
        """Parse the poker command message"""
        pattern = r'^!po\s+(\d+)\s+(\d+)\s+(\w+)$'
        match = re.match(pattern, message.strip())
        
        if not match:
            return None
            
        buy_in = float(match.group(1))      # Changed variable name to buy_in
        num_players = int(match.group(2))
        winner_name = match.group(3)         # Changed variable name to winner_name
        
        return buy_in, num_players, winner_name
    
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
                                    'columnCount': 7  # Increased for new columns
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

    def save_game(self, buy_in: float, num_players: int, winner_name: str):
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
            result = self.sheets_service.spreadsheets().values().append(
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
    
    def process_message(self, message: str) -> Optional[str]:
        """Process incoming message and return response"""
        self.logger.info(f"Processing message: {message}")
        
        # Handle ping command
        if message.strip() == '!ping':
            return 'pong'
            
        # Handle poker command
        parsed = self.parse_command(message)
        if not parsed:
            return None
            
        # Send immediate acknowledgment
        self.send_message("Processing your poker command... 🎲")
            
        buy_in, num_players, winner_name = parsed
        try:
            self.save_game(buy_in, num_players, winner_name)
            return f"Game recorded: {winner_name} won! 🏆\nBuy-in: ${buy_in}\nPlayers: {num_players}\nTotal Pool: ${buy_in * num_players}"
        except Exception as e:
            error_msg = f"Error recording game: {str(e)}"
            self.logger.error(error_msg)
            return error_msg

    def send_message(self, message: str):
        """Send message to Rocket Chat channel"""
        try:
            current_time = time.time()
            if hasattr(self, 'last_message_time') and \
               hasattr(self, 'last_message_content') and \
               current_time - self.last_message_time < 1 and \
               self.last_message_content == message:
                self.logger.debug("Skipping duplicate message send")
                return

            self.logger.info(f"Attempting to send message: {message}")
            response = self.rocket.chat_post_message(message, channel=self.room_id)
            
            if response.ok:
                self.logger.info("Message sent successfully")
                self.last_message_time = current_time
                self.last_message_content = message
            else:
                self.logger.error(f"Failed to send message. Status code: {response.status_code}")
                self.logger.error(f"Response content: {response.text}")
            
        except Exception as e:
            self.logger.error(f"Error sending message: {str(e)}", exc_info=True)

    def send_login(self):
        """Send login request"""
        try:
            login_msg = {
                "msg": "method",
                "method": "login",
                "id": f"login-{str(uuid.uuid4())}",
                "params": [{
                    "user": {"username": self.username},
                    "password": self.password
                }]
            }
            
            self.ws.send(json.dumps(login_msg))
            
        except Exception as e:
            self.logger.error(f"Login error: {str(e)}")

    def subscribe_to_room(self):
        """Subscribe to room messages"""
        try:
            sub_msg = {
                "msg": "sub",
                "id": str(uuid.uuid4()),
                "name": "stream-room-messages",
                "params": [
                    self.room_id,
                    {
                        "useCollection": False,
                        "args": [
                            {"$or": [{"t": {"$exists": False}}, {"t": ""}]},
                            {"$or": [{"t": "p"}, {"t": "c"}]},
                            {"roomParticipant": True},
                            {"roomType": {"$ne": "d"}}
                        ]
                    }
                ]
            }
            self.ws.send(json.dumps(sub_msg))
            self.logger.info(f"Sent subscription request for room: {self.room_name} (ID: {self.room_id})")
        except Exception as e:
            self.logger.error(f"Error subscribing to room: {str(e)}")
            # Try simpler subscription without args
            try:
                simple_sub_msg = {
                    "msg": "sub",
                    "id": str(uuid.uuid4()),
                    "name": "stream-room-messages",
                    "params": [
                        self.room_id,
                        {
                            "useCollection": False,
                            "args": []
                        }
                    ]
                }
                self.ws.send(json.dumps(simple_sub_msg))
                self.logger.info("Sent simplified subscription request")
            except Exception as e:
                self.logger.error(f"Error sending simplified subscription: {str(e)}")

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            
            # Handle initial connection
            if 'server_id' in data:
                connect_msg = {
                    "msg": "connect",
                    "version": "1",
                    "support": ["1"]
                }
                self.ws.send(json.dumps(connect_msg))
                self.logger.info("Connected to server")
                return
                
            msg_type = data.get('msg')
            self.logger.debug(f"Received message type: {msg_type}")
            
            # Handle different message types
            if msg_type == 'connected':
                self.ws_connected = True
                self.send_login()
                
            elif msg_type == 'result':
                # Handle login result
                if data.get('id') and data.get('id').startswith('login-'):
                    if data.get('result'):
                        self.logger.info("Login successful")
                        self.is_logged_in = True
                        self.subscribe_to_room()
                    else:
                        error_data = data.get('error', {})
                        self.logger.error(f"Login failed: {error_data.get('message', 'Unknown error')}")
                        self.is_logged_in = False
                        
            elif msg_type == 'ready':
                self.is_subscribed = True
                self.logger.info("Bot ready in room: " + self.room_name)
                
            elif msg_type == 'changed' and data.get('collection') == 'stream-room-messages':
                if not self.is_logged_in or not self.is_subscribed:
                    self.logger.warning("Not processing message - not logged in or subscribed")
                    return
                    
                # Extract the message content
                message_data = data['fields']['args'][0]
                msg_content = message_data.get('msg', '')
                msg_id = message_data.get('_id', '')
                sender_username = message_data.get('u', {}).get('username')
                
                self.logger.info(f"Received message - ID: {msg_id}, From: {sender_username}, Content: {msg_content}")
                
                # Skip if we've already processed this message
                if msg_id in self.processed_messages:
                    self.logger.debug(f"Skipping already processed message: {msg_id}")
                    return
                    
                # Add message ID to processed set
                self.processed_messages.add(msg_id)
                
                # Prevent set from growing too large
                if len(self.processed_messages) > self.max_processed_messages:
                    self.processed_messages.clear()
                
                # Only process command messages
                if msg_content.startswith('!'):
                    self.logger.info(f"Processing command from {sender_username}: {msg_content}")
                    response = self.process_message(msg_content)
                    if response:
                        self.logger.info(f"Sending response: {response}")
                        self.send_message(response)
                    else:
                        self.logger.warning(f"No response generated for command: {msg_content}")
                else:
                    self.logger.debug(f"Ignoring non-command message: {msg_content}")
                        
        except json.JSONDecodeError:
            self.logger.warning(f"Received invalid JSON message: {message}")
        except Exception as e:
            self.logger.error(f"Error processing message: {str(e)}", exc_info=True)

    def connect_websocket(self):
        """Establish WebSocket connection"""
        websocket_url = f"{self.server_url.replace('http', 'ws')}/websocket"
        
        # Disable default websocket trace as we have our own logging
        websocket.enableTrace(False)
        
        self.ws = websocket.WebSocketApp(
            websocket_url,
            on_message=self.on_message
        )

    def start(self):
        """Start the bot with WebSocket connection"""
        self.logger.info("Bot is starting...")
        
        try:
            # Select room to join
            self.room_id, self.room_name = self.select_room()
            self.logger.info(f"Connecting to room: {self.room_name}")
            
            self.connect_websocket()
            
            # Start WebSocket connection in a separate thread
            ws_thread = threading.Thread(target=self.ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
            
            # Keep the main thread running
            while True:
                time.sleep(1)
                if not self.ws_connected:
                    self.logger.error("WebSocket connection lost. Shutting down...")
                    break
                    
        except KeyboardInterrupt:
            self.logger.info("Bot is shutting down...")
        finally:
            if self.ws:
                self.ws.close()

if __name__ == "__main__":
    bot = PokerBot()
    bot.start() 