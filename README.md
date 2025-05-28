# Poker Manager Bot

A bot that manages poker games by tracking game sessions through Rocket Chat and storing data in Google Sheets.

## Features

-   Connects to Rocket Chat server
-   Listens for poker game commands
-   Stores game data in Google Sheets
-   Organizes data by date
-   Tracks game status

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set up environment variables:

-   Copy `.env.example` to `.env`
-   Fill in your Rocket Chat credentials and Google Sheets information

3. Set up Google Sheets API:

-   Create a Google Cloud Project
-   Enable Google Sheets API
-   Create a service account and download the credentials JSON file
-   Share your Google Sheet with the service account email
-   Set the path to your credentials file in `.env`

## Usage

1. Start the bot:

```bash
python poker_bot.py
```

2. In Rocket Chat, use the command format:

```
!po [start_money] [num_players] [player_name]
```

Example:

```
!po 400 5 Tuyen
```

This will:

-   Record a new game with $400 starting money
-   For 5 players
-   Started by player "Tuyen"

## Data Storage

-   Each day gets its own sheet in the Google Sheets document
-   Each game session is recorded as a row with:
    -   Timestamp
    -   Starting Money
    -   Number of Players
    -   Player Name
    -   Game Status
