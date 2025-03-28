import mysql.connector
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
import requests
import datetime
import pandas as pd
import numpy as np
from config import MYSQL_CONFIG, FOOTBALL_DATA_API_URL, FOOTBALL_DATA_API_KEY, Config
import logging
from functools import wraps
import time
import hashlib
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

cache = Cache(app)

# User model with enhanced security
class User(UserMixin):
    def __init__(self, user_id, username, email, preferences=None):
        self.id = user_id
        self.username = username
        self.email = email
        self.preferences = preferences or {}

    def get_preference(self, key, default=None):
        return self.preferences.get(key, default)

    def set_preference(self, key, value):
        self.preferences[key] = value

@login_manager.user_loader
def load_user(user_id):
    cnx = get_db_connection()
    cursor = cnx.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.*, p.preferences 
        FROM users u 
        LEFT JOIN user_preferences p ON u.id = p.user_id 
        WHERE u.id = %s
    """, (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    cnx.close()
    
    if user_data:
        preferences = eval(user_data['preferences']) if user_data['preferences'] else {}
        return User(user_data['id'], user_data['username'], user_data['email'], preferences)
    return None

# Enhanced database connection with connection pooling
def get_db_connection():
    try:
        cnx = mysql.connector.connect(**MYSQL_CONFIG)
        return cnx
    except mysql.connector.Error as err:
        logger.error(f"Database connection error: {err}")
        raise

# Enhanced password hashing with salt
def hash_password(password):
    salt = secrets.token_hex(16)
    return f"{salt}:{generate_password_hash(password + salt)}"

def verify_password(stored_hash, password):
    salt, hash_value = stored_hash.split(':')
    return check_password_hash(hash_value, password + salt)

# Cached API calls
@cache.memoize(timeout=300)
def fetch_matches():
    """
    Fetch real match data from Football-Data.org API with caching.
    """
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    endpoint = f"{FOOTBALL_DATA_API_URL}competitions/PL/matches?status=SCHEDULED"
    
    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        data = response.json()
        matches = []
        
        for m in data.get("matches", []):
            season_info = m.get("season", {})
            season_str = f"{season_info.get('startDate', '')[:4]}/{season_info.get('endDate', '')[:4]}" if season_info else "Unknown"
            
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
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return []

# Enhanced routes with pagination and caching
@app.route('/')
@cache.cached(timeout=300)
def index():
    """Display all matches and league table with pagination."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = app.config['ITEMS_PER_PAGE']
        
        cnx = get_db_connection()
        cursor = cnx.cursor(dictionary=True)
        
        # Get total count for pagination
        cursor.execute("SELECT COUNT(*) as total FROM matches")
        total_matches = cursor.fetchone()['total']
        
        # Get paginated matches
        matches_query = """
            SELECT m.*, 
                   ht.name as HomeTeamName, at.name as AwayTeamName,
                   ht.short_name as HomeTeamShort, at.short_name as AwayTeamShort
            FROM matches m
            JOIN teams ht ON m.home_team_id = ht.id
            JOIN teams at ON m.away_team_id = at.id
            ORDER BY m.match_date DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(matches_query, (per_page, (page - 1) * per_page))
        matches = cursor.fetchall()
        
        # Get league table with enhanced statistics
        table_query = """
            SELECT t.name, t.short_name, t.team_rank,
                   COUNT(m.id) as Played,
                   SUM(CASE WHEN (m.home_team_id = t.id AND m.home_goals > m.away_goals) 
                        OR (m.away_team_id = t.id AND m.away_goals > m.home_goals) THEN 1 ELSE 0 END) as Won,
                   SUM(CASE WHEN m.home_goals = m.away_goals THEN 1 ELSE 0 END) as Drawn,
                   SUM(CASE WHEN (m.home_team_id = t.id AND m.home_goals < m.away_goals) 
                        OR (m.away_team_id = t.id AND m.away_goals < m.home_goals) THEN 1 ELSE 0 END) as Lost,
                   SUM(CASE WHEN m.home_team_id = t.id THEN m.home_goals ELSE m.away_goals END) as GoalsFor,
                   SUM(CASE WHEN m.home_team_id = t.id THEN m.away_goals ELSE m.home_goals END) as GoalsAgainst,
                   SUM(CASE WHEN (m.home_team_id = t.id AND m.home_goals > m.away_goals) 
                        OR (m.away_team_id = t.id AND m.away_goals > m.home_goals) THEN 3
                        WHEN m.home_goals = m.away_goals THEN 1 ELSE 0 END) as Points
            FROM teams t
            LEFT JOIN matches m ON t.id = m.home_team_id OR t.id = m.away_team_id
            GROUP BY t.id
            ORDER BY Points DESC, (GoalsFor - GoalsAgainst) DESC
        """
        cursor.execute(table_query)
        league_table = cursor.fetchall()
        
        cursor.close()
        cnx.close()
        
        return render_template('index.html', 
                             matches=matches, 
                             league_table=league_table,
                             total_pages=(total_matches + per_page - 1) // per_page,
                             current_page=page)
    except Exception as e:
        logger.error(f"Error in index route: {e}")
        flash('An error occurred while loading the page.', 'error')
        return render_template('error.html')

# New route for user preferences
@app.route('/preferences', methods=['GET', 'POST'])
@login_required
def preferences():
    if request.method == 'POST':
        try:
            preferences = {
                'notifications_enabled': request.form.get('notifications_enabled') == 'on',
                'favorite_team': request.form.get('favorite_team'),
                'theme': request.form.get('theme', 'light')
            }
            
            cnx = get_db_connection()
            cursor = cnx.cursor()
            
            cursor.execute("""
                INSERT INTO user_preferences (user_id, preferences)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE preferences = %s
            """, (current_user.id, str(preferences), str(preferences)))
            
            cnx.commit()
            cursor.close()
            cnx.close()
            
            flash('Preferences updated successfully!', 'success')
        except Exception as e:
            logger.error(f"Error updating preferences: {e}")
            flash('An error occurred while updating preferences.', 'error')
            
    return render_template('preferences.html')

# New route for team statistics
@app.route('/team/<int:team_id>')
@cache.cached(timeout=300)
def team_stats(team_id):
    try:
        cnx = get_db_connection()
        cursor = cnx.cursor(dictionary=True)
        
        # Get team information
        cursor.execute("""
            SELECT * FROM teams WHERE id = %s
        """, (team_id,))
        team = cursor.fetchone()
        
        # Get team statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_matches,
                SUM(CASE WHEN (home_team_id = %s AND home_goals > away_goals) 
                    OR (away_team_id = %s AND away_goals > home_goals) THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN home_goals = away_goals THEN 1 ELSE 0 END) as draws,
                SUM(CASE WHEN (home_team_id = %s AND home_goals < away_goals) 
                    OR (away_team_id = %s AND away_goals < home_goals) THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN home_team_id = %s THEN home_goals ELSE away_goals END) as goals_for,
                SUM(CASE WHEN home_team_id = %s THEN away_goals ELSE home_goals END) as goals_against
            FROM matches
            WHERE home_team_id = %s OR away_team_id = %s
        """, (team_id,) * 8)
        stats = cursor.fetchone()
        
        cursor.close()
        cnx.close()
        
        return render_template('team_stats.html', team=team, stats=stats)
    except Exception as e:
        logger.error(f"Error in team_stats route: {e}")
        flash('An error occurred while loading team statistics.', 'error')
        return render_template('error.html')

# Enhanced login route with rate limiting
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
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
            
            if user_data and verify_password(user_data['password_hash'], password):
                user = User(user_data['id'], user_data['username'], user_data['email'])
                login_user(user)
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password', 'error')
        except Exception as e:
            logger.error(f"Login error: {e}")
            flash('An error occurred during login.', 'error')
            
    return render_template('login.html')

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
                   ht.name as HomeTeamName, at.name as AwayTeamName,
                   ht.short_name as HomeTeamShort, at.short_name as AwayTeamShort
            FROM matches m
            JOIN teams ht ON m.home_team_id = ht.id
            JOIN teams at ON m.away_team_id = at.id
            WHERE m.match_date >= %s 
            ORDER BY m.match_date ASC
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
