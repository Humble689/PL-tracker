import mysql.connector
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import requests
import datetime
import pandas as pd
import numpy as np
from config import MYSQL_CONFIG, FOOTBALL_DATA_API_URL, FOOTBALL_DATA_API_KEY
import logging
from functools import wraps
import time
import hashlib

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this in production
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User model
class User(UserMixin):
    def __init__(self, user_id, username, email):
        self.id = user_id
        self.username = username
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    cnx = get_db_connection()
    cursor = cnx.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    cnx.close()
    if user_data:
        return User(user_data['id'], user_data['username'], user_data['email'])
    return None

# Helper: Get a new database connection
def get_db_connection():
    try:
        cnx = mysql.connector.connect(**MYSQL_CONFIG)
        return cnx
    except mysql.connector.Error as err:
        logger.error(f"Database connection error: {err}")
        raise

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

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
            'HomeTeamID': m.get("homeTeam", {}).get("id"),
            'AwayTeamID': m.get("awayTeam", {}).get("id"),
            'HomeGoals': 0,
            'AwayGoals': 0,
            'HomeTeamRank': 0,
            'AwayTeamRank': 0,
            'Result': 'Scheduled',
            'MatchDate': match_date
        }
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

# --- Enhanced Prediction Logic ---
def predict_match_outcome(match):
    """
    Enhanced prediction using team form and historical data.
    """
    try:
        cnx = get_db_connection()
        cursor = cnx.cursor(dictionary=True)
        
        # Get team rankings
        home_rank_query = "SELECT `Rank` FROM Teams WHERE TeamID = %s"
        cursor.execute(home_rank_query, (match['HomeTeamID'],))
        home_rank = cursor.fetchone()['Rank']
        
        away_rank_query = "SELECT `Rank` FROM Teams WHERE TeamID = %s"
        cursor.execute(away_rank_query, (match['AwayTeamID'],))
        away_rank = cursor.fetchone()['Rank']
        
        # Calculate prediction confidence
        rank_diff = abs(home_rank - away_rank)
        max_rank_diff = 19  # Maximum possible rank difference
        confidence = int((1 - (rank_diff / max_rank_diff)) * 100)
        
        # Simple prediction based on rankings
        if home_rank < away_rank:
            prediction = 'Home Win'
        elif away_rank < home_rank:
            prediction = 'Away Win'
        else:
            prediction = 'Draw'
            confidence = 50  # Lower confidence for draws
        
        cursor.close()
        cnx.close()
        
        return prediction, confidence
        
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return 'Unknown', 0

# --- Flask Routes ---
@app.route('/')
def index():
    """Display all matches and league table."""
    try:
        cnx = get_db_connection()
        cursor = cnx.cursor(dictionary=True)
        
        # Get matches with team names
        matches_query = """
            SELECT m.*, 
                   ht.Name as HomeTeamName, at.Name as AwayTeamName,
                   ht.ShortName as HomeTeamShort, at.ShortName as AwayTeamShort
            FROM Matches m
            JOIN Teams ht ON m.HomeTeamID = ht.TeamID
            JOIN Teams at ON m.AwayTeamID = at.TeamID
            ORDER BY m.MatchDate DESC
        """
        cursor.execute(matches_query)
        matches = cursor.fetchall()
        
        # Get league table
        table_query = """
            SELECT t.Name, t.ShortName, t.Rank,
                   COUNT(m.MatchID) as Played,
                   SUM(CASE WHEN (m.HomeTeamID = t.TeamID AND m.HomeGoals > m.AwayGoals) 
                        OR (m.AwayTeamID = t.TeamID AND m.AwayGoals > m.HomeGoals) THEN 1 ELSE 0 END) as Won,
                   SUM(CASE WHEN m.HomeGoals = m.AwayGoals THEN 1 ELSE 0 END) as Drawn,
                   SUM(CASE WHEN (m.HomeTeamID = t.TeamID AND m.HomeGoals < m.AwayGoals) 
                        OR (m.AwayTeamID = t.TeamID AND m.AwayGoals < m.HomeGoals) THEN 1 ELSE 0 END) as Lost,
                   SUM(CASE WHEN m.HomeTeamID = t.TeamID THEN m.HomeGoals ELSE m.AwayGoals END) as GoalsFor,
                   SUM(CASE WHEN m.HomeTeamID = t.TeamID THEN m.AwayGoals ELSE m.HomeGoals END) as GoalsAgainst
            FROM Teams t
            LEFT JOIN Matches m ON t.TeamID = m.HomeTeamID OR t.TeamID = m.AwayTeamID
            GROUP BY t.TeamID
            ORDER BY t.Rank
        """
        cursor.execute(table_query)
        league_table = cursor.fetchall()
        
        cursor.close()
        cnx.close()
        
        return render_template('index.html', matches=matches, league_table=league_table)
    except Exception as e:
        logger.error(f"Error in index route: {e}")
        flash('An error occurred while loading the page.', 'error')
        return render_template('error.html')

@app.route('/update')
@login_required
def update():
    """Trigger data extraction and update the database."""
    try:
        update_matches()
        flash('Matches updated successfully!', 'success')
    except Exception as e:
        logger.error(f"Error updating matches: {e}")
        flash('An error occurred while updating matches.', 'error')
    return redirect(url_for('index'))

@app.route('/predict')
def predict():
    """Display predictions for upcoming matches."""
    try:
        today = datetime.date.today()
        cnx = get_db_connection()
        cursor = cnx.cursor(dictionary=True)
        
        query = """
            SELECT m.*, 
                   ht.Name as HomeTeamName, at.Name as AwayTeamName,
                   ht.ShortName as HomeTeamShort, at.ShortName as AwayTeamShort
            FROM Matches m
            JOIN Teams ht ON m.HomeTeamID = ht.TeamID
            JOIN Teams at ON m.AwayTeamID = at.TeamID
            WHERE m.MatchDate >= %s 
            ORDER BY m.MatchDate ASC
        """
        cursor.execute(query, (today,))
        upcoming_matches = cursor.fetchall()
        
        for match in upcoming_matches:
            prediction, confidence = predict_match_outcome(match)
            match['Prediction'] = prediction
            match['Confidence'] = confidence
            
        cursor.close()
        cnx.close()
        
        return render_template('predictions.html', matches=upcoming_matches)
    except Exception as e:
        logger.error(f"Error in predict route: {e}")
        flash('An error occurred while generating predictions.', 'error')
        return render_template('error.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            cnx = get_db_connection()
            cursor = cnx.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user_data = cursor.fetchone()
            cursor.close()
            cnx.close()
            
            if user_data and user_data['password_hash'] == hash_password(password):
                user = User(user_data['id'], user_data['username'], user_data['email'])
                login_user(user)
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password', 'error')
        except Exception as e:
            logger.error(f"Login error: {e}")
            flash('An error occurred during login.', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))
        
        try:
            cnx = get_db_connection()
            cursor = cnx.cursor(dictionary=True)
            
            # Check if username exists
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                flash('Username already exists', 'error')
                return redirect(url_for('register'))
            
            # Check if email exists
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                flash('Email already exists', 'error')
                return redirect(url_for('register'))
            
            # Insert new user
            insert_query = """
                INSERT INTO users (username, email, password_hash)
                VALUES (%s, %s, %s)
            """
            cursor.execute(insert_query, (username, email, hash_password(password)))
            cnx.commit()
            
            cursor.close()
            cnx.close()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            flash('An error occurred during registration.', 'error')
            
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    try:
        cnx = get_db_connection()
        cursor = cnx.cursor(dictionary=True)
        
        # Get user's predictions
        predictions_query = """
            SELECT p.*, m.match_date, m.home_goals, m.away_goals, m.result,
                   ht.name as home_team_name, at.name as away_team_name
            FROM predictions p
            JOIN matches m ON p.match_id = m.id
            JOIN teams ht ON m.home_team_id = ht.id
            JOIN teams at ON m.away_team_id = at.id
            WHERE p.user_id = %s
            ORDER BY p.created_at DESC
        """
        cursor.execute(predictions_query, (current_user.id,))
        predictions = cursor.fetchall()
        
        # Calculate correct predictions
        correct_predictions = sum(1 for p in predictions if p['result'] != 'Scheduled' and p['predicted_result'] == p['result'])
        
        cursor.close()
        cnx.close()
        
        return render_template('profile.html', predictions=predictions, correct_predictions=correct_predictions)
    except Exception as e:
        logger.error(f"Error in profile route: {e}")
        flash('An error occurred while loading your profile.', 'error')
        return render_template('error.html')

@app.route('/make_prediction/<int:match_id>', methods=['POST'])
@login_required
def make_prediction(match_id):
    try:
        prediction = request.form.get('prediction')
        if not prediction:
            flash('No prediction selected', 'error')
            return redirect(url_for('predict'))
            
        cnx = get_db_connection()
        cursor = cnx.cursor()
        
        # Check if prediction already exists
        check_query = "SELECT id FROM predictions WHERE user_id = %s AND match_id = %s"
        cursor.execute(check_query, (current_user.id, match_id))
        if cursor.fetchone():
            # Update existing prediction
            update_query = """
                UPDATE predictions 
                SET predicted_result = %s, created_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND match_id = %s
            """
            cursor.execute(update_query, (prediction, current_user.id, match_id))
        else:
            # Insert new prediction
            insert_query = """
                INSERT INTO predictions (user_id, match_id, predicted_result)
                VALUES (%s, %s, %s)
            """
            cursor.execute(insert_query, (current_user.id, match_id, prediction))
            
        cnx.commit()
        cursor.close()
        cnx.close()
        
        flash('Prediction saved successfully!', 'success')
    except Exception as e:
        logger.error(f"Error saving prediction: {e}")
        flash('An error occurred while saving your prediction.', 'error')
        
    return redirect(url_for('predict'))

if __name__ == '__main__':
    app.run(debug=True)
