from datetime import datetime
from typing import Dict, List, Optional, Tuple

class GameSession:
    def __init__(self, buy_in: float, players: List[str], date: str = None):
        self.date = date or datetime.now().strftime('%Y-%m-%d')
        self.buy_in = buy_in
        self.active_players = {player: buy_in for player in players}  # player: current_stack
        self.initial_players = players.copy()
        self.events = []  # List of (date, event_type, player, action, current_stack)
        self.winner = None
        self.is_active = True
        self.game_count = 1  # Start from game #1
        self.total_winnings = {}  # Track total winnings per player
        self.player_join_game = {}  # Track which game number each player joined at
        self.player_leave_game = {}  # Track which game number each player left at
        self.win_counts = {}  # Track number of wins per player
        
        # Initialize tracking data for all players
        for player in players:
            self.total_winnings[player] = 0
            self.player_join_game[player] = 1  # Initial players joined at game 1
            self.player_leave_game[player] = None  # None means still active
            self.win_counts[player] = 0  # Initialize win count
            # Record initial joins
            self.add_event("JOIN", player, "Initial", buy_in)
    
    def add_event(self, event_type: str, player: str, action: str, stack: float):
        """Record a new event in the session"""
        self.events.append((self.date, event_type, player, action, stack))
    
    def add_player(self, player: str) -> Tuple[bool, str]:
        """Add a player to the active session"""
        if player in self.active_players:
            return False, f"❌ {player} is already in the game"
            
        self.active_players[player] = self.buy_in
        self.total_winnings[player] = self.total_winnings.get(player, 0)  # Keep old winnings if they had any
        self.player_join_game[player] = self.game_count  # Track when this player joined
        self.player_leave_game[player] = None  # Reset leave game if they're rejoining
        self.win_counts[player] = self.win_counts.get(player, 0)  # Keep old win count if they had any
        self.add_event("IN", player, "Joined", self.buy_in)
        
        total_prize = len(self.active_players) * self.buy_in
        return True, f"✅ {player} joined the game with ${self.buy_in}\n💰 Current prize pool: ${total_prize}"
    
    def remove_player(self, player: str) -> Tuple[bool, str]:
        """Remove a player from the active session"""
        if player not in self.active_players:
            return False, f"❌ {player} is not in the game"
            
        stack = self.active_players.pop(player)
        self.player_leave_game[player] = self.game_count  # Track when they left
        self.add_event("OUT", player, "Left", stack)
        
        total_prize = len(self.active_players) * self.buy_in
        return True, f"👋 {player} left the game with ${stack}\n💰 New prize pool: ${total_prize}"
    
    def set_winner(self, winner: str) -> Tuple[bool, str]:
        """Set the winner for the current game and automatically start next game"""
        if winner not in self.active_players:
            return False, f"❌ {winner} is not in the game"
            
        total_pool = len(self.active_players) * self.buy_in
        
        # Update winner's total winnings and win count
        self.total_winnings[winner] = self.total_winnings.get(winner, 0) + total_pool
        self.win_counts[winner] = self.win_counts.get(winner, 0) + 1
        
        # Record win event
        self.add_event("WIN", winner, f"Won Game #{self.game_count}", total_pool)
        
        # Prepare message
        message = [
            f"🏆 {winner} won Game #{self.game_count}!",
            f"💰 Prize pool: ${total_pool}",
            f"👑 Wins: {self.win_counts[winner]}"
        ]
        
        # Automatically start next game
        self.game_count += 1
        
        # Reset all players' stacks for next game
        for player in self.active_players:
            self.active_players[player] = self.buy_in
            self.add_event("NEWGAME", player, f"Game #{self.game_count}", self.buy_in)
        
        message.append(f"\n🎲 Game #{self.game_count} has started automatically!")
        message.append(f"💵 All players reset to ${self.buy_in}")
        message.append(f"👥 Active players: {', '.join(self.active_players.keys())}")
        
        return True, "\n".join(message)
    
    def get_player_games_played(self, player: str) -> int:
        """Calculate actual number of games played by a player"""
        join_game = self.player_join_game.get(player, self.game_count)
        leave_game = self.player_leave_game.get(player)
        
        if leave_game is None:  # Player is still active
            return self.game_count - join_game
        else:  # Player has left
            return leave_game - join_game
    
    def get_player_pnl(self, player: str = None) -> Tuple[bool, str]:
        """Calculate profit/loss for one or all players"""
        results = []
        
        # Header showing total games played
        header = [
            "📊 **Profit/Loss Summary**",
            f"Games played: {self.game_count - 1}",
            "─" * 30
        ]
        
        # Get all players who have ever been in the game
        all_players = set(self.player_join_game.keys())
        
        for p in all_players:
            if player and p != player:
                continue
                
            # Calculate games played and buy-in based on join/leave times
            games_played = self.get_player_games_played(p)
            total_buyin = self.buy_in * games_played
            winnings = self.total_winnings.get(p, 0)
            pnl = winnings - total_buyin
            wins = self.win_counts.get(p, 0)
            
            # Add status indicator for active/inactive players
            status = "🟢" if p in self.active_players else "⭕"
            
            results.append(f"{status} {p}:")
            results.append(f"  Games Played: {games_played}")
            results.append(f"  Games Won: {wins}")
            results.append(f"  Total Buy-in: ${total_buyin}")
            results.append(f"  Total Won: ${winnings}")
            results.append(f"  Net P/L: {'+$' + str(pnl) if pnl > 0 else '-$' + str(abs(pnl)) if pnl < 0 else '$0'}")
            results.append("─" * 20)
            
        if not results:
            return False, f"❌ Player {player} not found"
            
        return True, "\n".join(header + results)
    
    def get_final_results(self) -> List[Dict]:
        """Get final results for spreadsheet"""
        results = []
        for player in set(self.initial_players) | set(self.active_players.keys()):
            final_stack = self.active_players.get(player, 0)
            pnl = final_stack - self.buy_in
            results.append({
                "Player Name": player,
                "Buy-in": self.buy_in,
                "Rebuys": 0,  # For future implementation
                "Final Stack": final_stack,
                "Net Profit/Loss": pnl
            })
        return results
    
    def get_session_info(self) -> Dict:
        """Get session info for spreadsheet"""
        return {
            "Date": self.date,
            "Buy-in Amount": self.buy_in,
            "Initial Players": ", ".join(self.initial_players),
            "Current Game": f"Game #{self.game_count}",
            "Total Pool": sum(self.active_players.values())
        }
    
    def get_tracking_data(self) -> List[Tuple]:
        """Get tracking data for spreadsheet"""
        return self.events
        
    def format_events(self) -> str:
        """Format events for display"""
        if not self.events:
            return "No events in current session"
            
        # Format header
        header = [
            "📋 **Session Events**",
            f"Date: {self.date}",
            f"Buy-in: ${self.buy_in}",
            f"Current Game: #{self.game_count}",
            f"Active Players: {len(self.active_players)}",
            f"Prize Pool: ${len(self.active_players) * self.buy_in}",
            f"Players: {', '.join(self.active_players.keys())}",
            "─" * 40
        ]
        
        # Format events
        event_lines = []
        for date, event_type, player, action, stack in self.events:
            if event_type == "JOIN":
                event_lines.append(f"➡️ {player} joined with ${stack}")
            elif event_type == "IN":
                event_lines.append(f"✅ {player} bought in with ${stack}")
            elif event_type == "OUT":
                event_lines.append(f"❌ {player} left the game")
            elif event_type == "WIN":
                wins = self.win_counts.get(player, 0)
                event_lines.append(f"🏆 {player} {action} with ${stack} (Win #{wins})")
            elif event_type == "NEWGAME":
                event_lines.append(f"🎲 {action} started - All players reset to ${stack}")
                
        return "\n".join(header + [""] + event_lines) 