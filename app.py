import mysql.connector
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
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
from decimal import Decimal
import json
from models import db, User, Match, Team, UserPrediction

# Custom JSON encoder to handle Decimal values
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
app.json_encoder = CustomJSONEncoder

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

cache = Cache(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Enhanced database connection with connection pooling
def get_db_connection():
    """Get a database connection with connection pooling."""
    try:
        # Add connection pooling configuration
        config = MYSQL_CONFIG.copy()
        config.update({
            'pool_name': 'mypool',
            'pool_size': 5,
            'pool_reset_session': True,
            'connect_timeout': 10,  # Add timeout to prevent hanging
            'use_pure': True  # Use pure Python implementation for better compatibility
        })
        
        # Try to connect to the database
        logger.info(f"Attempting to connect to database at {config['host']}")
        cnx = mysql.connector.connect(**config)
        
        # Test the connection
        cursor = cnx.cursor()
        cursor.execute('SELECT 1')
        result = cursor.fetchone()
        cursor.close()
        
        if result and result[0] == 1:
            logger.info("Database connection test successful")
            return cnx
        else:
            logger.error("Database connection test failed")
            raise mysql.connector.Error("Connection test failed")
            
    except mysql.connector.Error as err:
        logger.error(f"Database connection error: {err}")
        if err.errno == mysql.connector.errorcode.ER_ACCESS_DENIED_ERROR:
            logger.error("Access denied: Check your username and password")
        elif err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
            logger.error("Database does not exist")
        elif err.errno == mysql.connector.errorcode.ER_CON_COUNT_ERROR:
            logger.error("Too many connections")
        elif err.errno == mysql.connector.errorcode.ER_CONNECTION_ERROR:
            logger.error("Connection error: Check if MySQL server is running")
        else:
            logger.error(f"Error {err.errno}: {err.msg}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error connecting to database: {e}")
        raise

# Enhanced password hashing with salt
def hash_password(password):
    salt = secrets.token_hex(16)
    return f"{salt}:{generate_password_hash(password + salt)}"

def verify_password(stored_hash, password):
    salt, hash_value = stored_hash.split(':')
    return check_password_hash(hash_value, password + salt)

def update_matches():
    """Fetch and update matches from the Football-Data.org API."""
    cnx = None
    cursor = None
    
    try:
        # Fetch matches from API
        logger.info("Fetching matches from API")
        matches = fetch_matches()
        
        if not matches:
            logger.warning("No matches returned from API")
            return
        
        logger.info(f"Retrieved {len(matches)} matches from API")
        
        try:
            cnx = get_db_connection()
            cursor = cnx.cursor()
            
            # Update teams first
            teams_data = set()
            for match in matches:
                teams_data.add((match['HomeTeamID'], match['HomeTeamName']))
                teams_data.add((match['AwayTeamID'], match['AwayTeamName']))
            
            logger.info(f"Updating {len(teams_data)} teams")
            
            # Insert or update teams
            for team_id, team_name in teams_data:
                try:
                    cursor.execute("""
                        INSERT INTO teams (id, name, short_name)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE name = VALUES(name)
                    """, (team_id, team_name, team_name[:3]))
                except mysql.connector.Error as err:
                    logger.error(f"Error updating team {team_id}: {err}")
                    # Continue with other teams even if one fails
            
            # Update matches
            logger.info(f"Updating {len(matches)} matches")
            for match in matches:
                try:
                    cursor.execute("""
                        INSERT INTO matches (
                            id, match_date, home_team_id, away_team_id,
                            home_goals, away_goals, result, season
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            match_date = VALUES(match_date),
                            home_goals = VALUES(home_goals),
                            away_goals = VALUES(away_goals),
                            result = VALUES(result),
                            season = VALUES(season)
                    """, (
                        match['id'],
                        match['MatchDate'],
                        match['HomeTeamID'],
                        match['AwayTeamID'],
                        match['HomeScore'],
                        match['AwayScore'],
                        match['Result'],
                        match['Season']
                    ))
                except mysql.connector.Error as err:
                    logger.error(f"Error updating match {match['id']}: {err}")
                    # Continue with other matches even if one fails
            
            cnx.commit()
            logger.info("Matches updated successfully")
            
        except mysql.connector.Error as err:
            logger.error(f"Database error in update_matches: {err}")
            if cnx:
                cnx.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
            if cnx:
                cnx.close()
                logger.info("Database connection closed")
        
    except Exception as e:
        logger.error(f"Error updating matches: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise

# Update the fetch_matches function to include more match data
@cache.memoize(timeout=300)
def fetch_matches():
    """
    Fetch real match data from Football-Data.org API with caching.
    """
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    endpoint = f"{FOOTBALL_DATA_API_URL}competitions/PL/matches"
    
    try:
        logger.info(f"Making API request to {endpoint}")
        response = requests.get(endpoint, headers=headers, timeout=10)
        
        # Check if the request was successful
        if response.status_code != 200:
            logger.error(f"API request failed with status code {response.status_code}: {response.text}")
            return []
            
        data = response.json()
        
        # Check if the response contains matches
        if "matches" not in data:
            logger.error(f"API response does not contain matches: {data}")
            return []
            
        matches = []
        logger.info(f"Processing {len(data['matches'])} matches from API")
        
        for m in data.get("matches", []):
            try:
                season_info = m.get("season", {})
                season_str = f"{season_info.get('startDate', '')[:4]}/{season_info.get('endDate', '')[:4]}" if season_info else "Unknown"
                
                utc_date = m.get("utcDate", "")
                try:
                    match_date = datetime.datetime.strptime(utc_date[:10], "%Y-%m-%d").date()
                except Exception as e:
                    logger.error(f"Error parsing date {utc_date}: {e}")
                    match_date = None

                # Get match result
                result = 'Scheduled'
                if m.get('status') == 'FINISHED':
                    home_goals = m.get('score', {}).get('fullTime', {}).get('home', 0)
                    away_goals = m.get('score', {}).get('fullTime', {}).get('away', 0)
                    if home_goals > away_goals:
                        result = 'Home Win'
                    elif away_goals > home_goals:
                        result = 'Away Win'
                    else:
                        result = 'Draw'
                elif m.get('status') == 'IN_PROGRESS':
                    result = 'Live'
     
                match = {
                    'id': m.get('id'),
                    'Season': season_str,
                    'HomeTeamID': m.get("homeTeam", {}).get("id"),
                    'AwayTeamID': m.get("awayTeam", {}).get("id"),
                    'HomeTeamName': m.get("homeTeam", {}).get("name"),
                    'AwayTeamName': m.get("awayTeam", {}).get("name"),
                    'HomeScore': m.get('score', {}).get('fullTime', {}).get('home', 0),
                    'AwayScore': m.get('score', {}).get('fullTime', {}).get('away', 0),
                    'HomeTeamRank': 0,  # Will be updated from league table
                    'AwayTeamRank': 0,  # Will be updated from league table
                    'Result': result,
                    'MatchDate': match_date,
                    'Status': m.get('status', 'SCHEDULED')
                }
                
                # Validate required fields
                if not all([match['id'], match['HomeTeamID'], match['AwayTeamID'], match['MatchDate']]):
                    logger.warning(f"Skipping match with missing required fields: {match}")
                    continue
                    
                matches.append(match)
            except Exception as e:
                logger.error(f"Error processing match: {e}")
                continue
        
        logger.info(f"Successfully processed {len(matches)} matches")
        return matches
        
    except requests.exceptions.Timeout:
        logger.error("API request timed out")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in fetch_matches: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return []

# Enhanced routes with pagination and caching
@app.route('/')
@cache.cached(timeout=300)
def index():
    """Display all matches and league table with pagination."""
    try:
        # Update matches to ensure fresh data
        try:
            update_matches()
        except Exception as e:
            logger.error(f"Error updating matches in index route: {str(e)}")
            flash('Unable to update matches. Showing existing data.', 'warning')
        
        page = request.args.get('page', 1, type=int)
        per_page = app.config['ITEMS_PER_PAGE']
        
        # Initialize variables
        matches = []
        league_table = []
        total_matches = 0
        cnx = None
        cursor = None
        
        try:
            # Get database connection with better error handling
            try:
                cnx = get_db_connection()
                logger.info("Database connection established successfully")
            except mysql.connector.Error as db_err:
                logger.error(f"Database connection error: {str(db_err)}")
                flash(f'Database connection error: {str(db_err)}', 'error')
                return render_template('error.html')
            
            cursor = cnx.cursor(dictionary=True)
            
            # Get total count for pagination
            try:
                cursor.execute("SELECT COUNT(*) as total FROM matches")
                result = cursor.fetchone()
                if result:
                    total_matches = result['total']
                else:
                    total_matches = 0
                logger.info(f"Total matches count: {total_matches}")
            except mysql.connector.Error as db_err:
                logger.error(f"Error counting matches: {str(db_err)}")
                flash(f'Error counting matches: {str(db_err)}', 'error')
                return render_template('error.html')
            
            if total_matches > 0:
                # Get paginated matches, ordered by match date
                try:
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
                    logger.info(f"Retrieved {len(matches)} matches")
                except mysql.connector.Error as db_err:
                    logger.error(f"Error fetching matches: {str(db_err)}")
                    flash(f'Error fetching matches: {str(db_err)}', 'error')
                    return render_template('error.html')
            
            # Get league table with enhanced statistics
            try:
                table_query = """
                    SELECT t.name, t.short_name, t.id as team_id,
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
                    GROUP BY t.id, t.name, t.short_name
                    ORDER BY Points DESC, (GoalsFor - GoalsAgainst) DESC
                """
                cursor.execute(table_query)
                league_table = cursor.fetchall()
                logger.info(f"Retrieved league table with {len(league_table)} teams")
                
                # Add team rank to each team
                for i, team in enumerate(league_table):
                    team['team_rank'] = i + 1
            except mysql.connector.Error as db_err:
                logger.error(f"Error fetching league table: {str(db_err)}")
                flash(f'Error fetching league table: {str(db_err)}', 'error')
                return render_template('error.html')
            
        except Exception as e:
            logger.error(f"Unexpected error in database operations: {str(e)}")
            flash(f'An unexpected error occurred: {str(e)}', 'error')
            return render_template('error.html')
        finally:
            # Ensure resources are properly closed
            if cursor:
                cursor.close()
            if cnx:
                cnx.close()
                logger.info("Database connection closed")
        
        if not matches and not league_table:
            flash('No data available. Please check back later.', 'info')
        
        return render_template('index.html', 
                             matches=matches, 
                             league_table=league_table,
                             total_pages=(total_matches + per_page - 1) // per_page,
                             current_page=page)
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
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
            user = User.query.filter_by(username=username).first()
            
            if user and user.check_password(password):
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
            # Check if username exists
            if User.query.filter_by(username=username).first():
                flash('Username already exists', 'error')
                return redirect(url_for('register'))
            
            # Check if email exists
            if User.query.filter_by(email=email).first():
                flash('Email already exists', 'error')
                return redirect(url_for('register'))
            
            # Create new user
            new_user = User(
                username=username,
                email=email
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            db.session.rollback()
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
            FROM user_predictions p
            JOIN matches m ON p.match_id = m.id
            JOIN teams ht ON m.home_team_id = ht.id
            JOIN teams at ON m.away_team_id = at.id
            WHERE p.user_id = %s
            ORDER BY p.predicted_at DESC
        """
        cursor.execute(predictions_query, (current_user.id,))
        predictions = cursor.fetchall()
        
        # Calculate correct predictions
        correct_predictions = sum(1 for p in predictions if p['result'] != 'Scheduled' and p['prediction'] == p['result'])
        
        cursor.close()
        cnx.close()
        
        return render_template('profile.html', predictions=predictions, correct_predictions=correct_predictions)
    except Exception as e:
        logger.error(f"Error in profile route: {e}")
        flash('An error occurred while loading your profile.', 'error')
        return render_template('error.html')

@app.route('/predictions')
@login_required
def predictions():
    # Get upcoming matches that haven't been played yet
    upcoming_matches = db.session.query(Match).filter(
        Match.match_date >= datetime.datetime.now().date(),
        Match.result == None
    ).order_by(Match.match_date).all()
    
    # Get user's existing predictions
    user_predictions = {
        pred.match_id: pred.prediction 
        for pred in db.session.query(UserPrediction).filter(
            UserPrediction.user_id == current_user.id
        ).all()
    }
    
    return render_template('predictions.html', 
                         matches=upcoming_matches,
                         user_predictions=user_predictions)

@app.route('/make_prediction/<int:match_id>', methods=['POST'])
@login_required
def make_prediction(match_id):
    prediction = request.form.get('prediction')
    
    if not prediction or prediction not in ['Home Win', 'Draw', 'Away Win']:
        flash('Invalid prediction', 'error')
        return redirect(url_for('predictions'))
    
    # Check if match exists and hasn't been played yet
    match = Match.query.get_or_404(match_id)
    if match.result is not None:
        flash('Cannot predict a match that has already been played', 'error')
        return redirect(url_for('predictions'))
    
    # Check if user already made a prediction for this match
    existing_prediction = UserPrediction.query.filter_by(
        user_id=current_user.id,
        match_id=match_id
    ).first()
    
    if existing_prediction:
        existing_prediction.prediction = prediction
        existing_prediction.predicted_at = datetime.datetime.now()
    else:
        new_prediction = UserPrediction(
            user_id=current_user.id,
            match_id=match_id,
            prediction=prediction,
            predicted_at=datetime.datetime.now()
        )
        db.session.add(new_prediction)
    
    db.session.commit()
    flash('Your prediction has been saved!', 'success')
    return redirect(url_for('predictions'))

def predict_match_outcome(match):
    """
    Predict the outcome of a match based on team rankings and historical data.
    Returns a tuple of (prediction, confidence).
    """
    try:
        # Get team rankings
        home_rank = match.get('HomeTeamRank', 0)
        away_rank = match.get('AwayTeamRank', 0)
        
        # Simple prediction based on team rankings
        if home_rank < away_rank:
            prediction = 'Home Win'
            confidence = 0.6
        elif away_rank < home_rank:
            prediction = 'Away Win'
            confidence = 0.6
        else:
            prediction = 'Draw'
            confidence = 0.4
            
        return prediction, confidence
    except Exception as e:
        logger.error(f"Error in prediction: {e}")
        return 'Unknown', 0.0

def init_db():
    """Initialize the database tables."""
    try:
        with app.app_context():
            # Create all tables
            db.create_all()
            
            # Check if tables exist
            cnx = get_db_connection()
            cursor = cnx.cursor()
            
            # Check if teams table exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    id INT PRIMARY KEY,
                    name VARCHAR(80) NOT NULL,
                    short_name VARCHAR(3) NOT NULL
                )
            """)
            
            # Check if matches table exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    id INT PRIMARY KEY,
                    season VARCHAR(9) NOT NULL,
                    match_date DATE NOT NULL,
                    home_team_id INT NOT NULL,
                    away_team_id INT NOT NULL,
                    home_goals INT DEFAULT 0,
                    away_goals INT DEFAULT 0,
                    home_team_rank INT DEFAULT 0,
                    away_team_rank INT DEFAULT 0,
                    result VARCHAR(20) NOT NULL DEFAULT 'Scheduled',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (home_team_id) REFERENCES teams(id),
                    FOREIGN KEY (away_team_id) REFERENCES teams(id)
                )
            """)
            
            # Check if user_predictions table exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_predictions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    match_id INT NOT NULL,
                    prediction VARCHAR(10) NOT NULL,
                    predicted_at DATETIME NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (match_id) REFERENCES matches(id)
                )
            """)
            
            cnx.commit()
            cursor.close()
            cnx.close()
            
            logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

if __name__ == '__main__':
    init_db()  # Initialize database tables
    app.run(debug=True, port=5000)
