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
        
        # Initialize total_winnings and join game number for all players
        for player in players:
            self.total_winnings[player] = 0
            self.player_join_game[player] = 1  # Initial players joined at game 1
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
        self.total_winnings[player] = 0
        self.player_join_game[player] = self.game_count  # Track when this player joined
        self.add_event("IN", player, "Joined", self.buy_in)
        
        total_prize = len(self.active_players) * self.buy_in
        return True, f"✅ {player} joined the game with ${self.buy_in}\n💰 Current prize pool: ${total_prize}"
    
    def remove_player(self, player: str) -> Tuple[bool, str]:
        """Remove a player from the active session"""
        if player not in self.active_players:
            return False, f"❌ {player} is not in the game"
            
        stack = self.active_players.pop(player)
        self.add_event("OUT", player, "Left", stack)
        return True, f"👋 {player} left the game with ${stack}"
    
    def set_winner(self, winner: str) -> Tuple[bool, str]:
        """Set the winner for the current game and automatically start next game"""
        if winner not in self.active_players:
            return False, f"❌ {winner} is not in the game"
            
        total_pool = len(self.active_players) * self.buy_in
        
        # Update winner's total winnings
        self.total_winnings[winner] = self.total_winnings.get(winner, 0) + total_pool
        
        # Record win event
        self.add_event("WIN", winner, f"Won Game #{self.game_count}", total_pool)
        
        # Prepare message
        message = [
            f"🏆 {winner} won Game #{self.game_count}!",
            f"💰 Prize pool: ${total_pool}"
        ]
        
        # Automatically start next game
        self.game_count += 1
        
        # Reset all players' stacks for next game
        for player in self.active_players:
            self.active_players[player] = self.buy_in
            self.add_event("NEWGAME", player, f"Game #{self.game_count}", self.buy_in)
        
        message.append(f"\n🎲 Game #{self.game_count} has started automatically!")
        message.append(f"💵 All players reset to ${self.buy_in}")
        
        return True, "\n".join(message)
    
    def get_player_pnl(self, player: str = None) -> Tuple[bool, str]:
        """Calculate profit/loss for one or all players"""
        results = []
        
        # Header showing total games played
        header = [
            "📊 **Profit/Loss Summary**",
            f"Games played: {self.game_count - 1}",
            "─" * 30
        ]
        
        for p in self.total_winnings:
            if player and p != player:
                continue
                
            # Calculate total buy-in based on when player joined
            games_played = self.game_count - self.player_join_game[p]
            total_buyin = self.buy_in * games_played
            winnings = self.total_winnings.get(p, 0)
            pnl = winnings - total_buyin
            
            results.append(f"{p}:")
            results.append(f"  Games Played: {games_played}")
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
                event_lines.append(f"🏆 {player} {action} with ${stack}")
            elif event_type == "NEWGAME":
                event_lines.append(f"🎲 {action} started - All players reset to ${stack}")
                
        return "\n".join(header + [""] + event_lines) 