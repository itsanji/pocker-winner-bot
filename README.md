# Poker Manager Bot

A bot that manages poker games by tracking game sessions through Discord and storing data in Google Sheets.

## Features

-   Real-time poker game session management
-   Player tracking during active sessions
-   Profit/Loss tracking per player
-   Dynamic player join/leave handling
-   Game data storage in Google Sheets
-   Daily game history organization

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set up environment variables:

-   Copy `.env.example` to `.env`
-   Fill in your Discord credentials and Google Sheets information

3. Set up Google Sheets API:

-   Create a Google Cloud Project
-   Enable Google Sheets API
-   Create a service account and download the credentials JSON file
-   Share your Google Sheet with the service account email
-   Set the path to your credentials file in `.env`

## Usage

The bot uses a flow-based command system where each game session must be started before recording results.

### Game Flow Commands

1. **Start a Game Session**:

```
!po start <buy-in> <player1,player2,player3,...>
```

Example:

```
!po start 400 Tuyen,Cuong,Truong
```

This will:

-   Start a new game session
-   Set buy-in amount to $400
-   Register initial players: Tuyen, Cuong, and Truong

2. **Record Winner**:

```
!po <winner-name>
```

Example:

```
!po Tuyen
```

-   Records Tuyen as the winner of the current session
-   Calculates profits/losses automatically

3. **Remove Player**:

```
!po out <player-name>
```

Example:

```
!po out Cuong
```

-   Removes Cuong from the current session
-   Adjusts profit/loss calculations accordingly

4. **Add Player**:

```
!po in <player-name>
```

Example:

```
!po in Minh
```

-   Adds Minh to the current session
-   Includes them in profit/loss calculations

5. **View All Players' Profit/Loss**:

```
!po pnl
```

-   Displays current profit/loss for all players in the session

6. **View Specific Player's Profit/Loss**:

```
!po pnl <player-name>
```

Example:

```
!po pnl Tuyen
```

-   Shows profit/loss for Tuyen only

### Important Notes

-   You must start a game session with `!po start` before using other commands
-   The bot will remind you if you try to use commands without an active session
-   Players can join/leave during an active session
-   All game data is automatically recorded in Google Sheets
-   Each day's games are organized in separate sheets

## Data Storage

Each poker session gets its own sheet in the Google Sheets document, named with format: `Session_YYYY-MM-DD`. For example: `Session_2024-03-20`

The session sheet contains multiple tables:

### 1. Session Info

-   Date
-   Buy-in Amount
-   Initial Players
-   Final Winner
-   Total Pool Amount

### 2. Player Tracking

| Date       | Event Type | Player Name | Action   | Current Stack |
| ---------- | ---------- | ----------- | -------- | ------------- |
| 2024-03-20 | JOIN       | Tuyen       | Initial  | 400           |
| 2024-03-20 | OUT        | Cuong       | Left     | 0             |
| 2024-03-20 | IN         | Minh        | Joined   | 400           |
| 2024-03-20 | WIN        | Tuyen       | Won Game | 1200          |

### 3. Final Results

| Player Name | Buy-in | Rebuys | Final Stack | Net Profit/Loss |
| ----------- | ------ | ------ | ----------- | --------------- |
| Tuyen       | 400    | 0      | 1200        | +800            |
| Cuong       | 400    | 0      | 0           | -400            |
| Truong      | 400    | 0      | 200         | -200            |
| Minh        | 400    | 0      | 400         | 0               |

### Important Notes

-   Each session is tracked by date
-   Player actions are recorded with date
-   Stack sizes are updated after each significant event
-   Final results are calculated automatically when session ends
-   Historical data can be accessed by session date

## Error Handling

The bot includes helpful error messages for:

-   Commands used without active session
-   Invalid player names
-   Incorrect command format
-   Missing parameters
-   API connection issues
