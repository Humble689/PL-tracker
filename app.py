import mysql.connector
from flask import Flask, render_template, redirect, url_for
import requests
import datetime
from config import MYSQL_CONFIG, FOOTBALL_DATA_API_URL, FOOTBALL_DATA_API_KEY

app = Flask(__name__)

# Helper: Get a new database connection
def get_db_connection():
    cnx = mysql.connector.connect(**MYSQL_CONFIG)
    return cnx

# --- Real Data Extraction using Football-Data.org API ---
def fetch_matches():
    """
    Fetch real match data from Football-Data.org API.
    Here we request scheduled matches for the English Premier League (competition code 'PL').
    Documentation: https://www.football-data.org/documentation/quickstart
    """
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    endpoint = f"{FOOTBALL_DATA_API_URL}competitions/PL/matches?status=SCHEDULED"
    response = requests.get(endpoint, headers=headers)
    data = response.json()
    matches = []
    for m in data.get("matches", []):
        # Create a season string from the season dates (if available)
        season_info = m.get("season", {})
        if season_info:
            start = season_info.get("startDate", "")[:4]
            end = season_info.get("endDate", "")[:4]
            season_str = f"{start}/{end}"
        else:
            season_str = "Unknown"

        # Parse match date (UTC) – only take the date part
        utc_date = m.get("utcDate", "")
        try:
            match_date = datetime.datetime.strptime(utc_date[:10], "%Y-%m-%d").date()
        except Exception:
            match_date = None

        match = {
            'Season': season_str,
            # Note: The API returns team IDs. In a full implementation,
            # you would map these to your Teams table.
            'HomeTeamID': m.get("homeTeam", {}).get("id"),
            'AwayTeamID': m.get("awayTeam", {}).get("id"),
            # For scheduled matches, goals are 0.
            'HomeGoals': 0,
            'AwayGoals': 0,
            # Dummy ranks – in a real project, compute or retrieve these from history
            'HomeTeamRank': 0,
            'AwayTeamRank': 0,
            'Result': 'Scheduled',
            'MatchDate': match_date
        }
        # Only add match if date is parsed correctly
        if match_date:
            matches.append(match)
    return matches

def update_matches():
    """
    Fetches match data from the API and inserts new records into the Matches table.
    Duplicate matches (based on MatchDate, HomeTeamID, and AwayTeamID) are skipped.
    """
    matches = fetch_matches()
    cnx = get_db_connection()
    cursor = cnx.cursor()
    
    for match in matches:
        # Check if the match already exists
        check_query = """
            SELECT MatchID FROM Matches 
            WHERE MatchDate = %s AND HomeTeamID = %s AND AwayTeamID = %s
        """
        cursor.execute(check_query, (match['MatchDate'], match['HomeTeamID'], match['AwayTeamID']))
        if cursor.fetchone() is None:
            insert_query = """
                INSERT INTO Matches 
                (Season, HomeTeamID, AwayTeamID, HomeGoals, AwayGoals, HomeTeamRank, AwayTeamRank, Result, MatchDate)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (
                match['Season'],
                match['HomeTeamID'],
                match['AwayTeamID'],
                match['HomeGoals'],
                match['AwayGoals'],
                match['HomeTeamRank'],
                match['AwayTeamRank'],
                match['Result'],
                match['MatchDate']
            ))
    cnx.commit()
    cursor.close()
    cnx.close()

# --- Dummy Prediction Logic ---
def predict_match_outcome(match):
    """
    Dummy prediction:
      - If HomeTeamRank is lower than AwayTeamRank (i.e. a better rank), predict 'Home Win'.
      - If higher, predict 'Away Win'.
      - Otherwise, predict 'Draw'.
    In a real system, use historical form, player stats, etc.
    """
    if match['HomeTeamRank'] < match['AwayTeamRank']:
        return 'Home Win'
    elif match['HomeTeamRank'] > match['AwayTeamRank']:
        return 'Away Win'
    else:
        return 'Draw'

# --- Flask Routes ---

@app.route('/')
def index():
    """Display all matches."""
    cnx = get_db_connection()
    cursor = cnx.cursor(dictionary=True)
    query = "SELECT * FROM Matches ORDER BY MatchDate DESC"
    cursor.execute(query)
    matches = cursor.fetchall()
    cursor.close()
    cnx.close()
    return render_template('index.html', matches=matches)

@app.route('/update')
def update():
    """Trigger data extraction and update the database."""
    update_matches()
    return redirect(url_for('index'))

@app.route('/predict')
def predict():
    """Display predictions for upcoming matches (today or in future)."""
    today = datetime.date.today()
    cnx = get_db_connection()
    cursor = cnx.cursor(dictionary=True)
    query = "SELECT * FROM Matches WHERE MatchDate >= %s ORDER BY MatchDate ASC"
    cursor.execute(query, (today,))
    upcoming_matches = cursor.fetchall()
    for match in upcoming_matches:
        match['Prediction'] = predict_match_outcome(match)
    cursor.close()
    cnx.close()
    return render_template('predictions.html', matches=upcoming_matches)

if __name__ == '__main__':
    app.run(debug=True)
