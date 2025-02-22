import requests
from bs4 import BeautifulSoup
import mysql.connector
import pandas as pd
import datetime
from flask import Flask, render_template, redirect, url_for  # Import Flask and necessary modules
from sklearn.model_selection import train_test_split

app = Flask(__name__)  # Create an instance of the Flask app

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score


# Establish a connection to the MySQL database
try:
    db_connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Postagemark8#",  # Update this if a password is required
        database="premier_league_stats"
    )
    cursor = db_connection.cursor()
    # Test the connection
    cursor.execute("SELECT 1")
    print("Connection successful!")
    cursor.fetchall()  # Fetch all results to avoid unread result error
except mysql.connector.Error as err:
    print(f"Error: {err}")
finally:
    cursor.close()  # Ensure the cursor is closed after use
    db_connection.close()  # Close the database connection
    

def get_db_connection():
    db_config = {
        'host': 'localhost',
        'user': 'root',
        'password': 'Postagemark8#',
        'database': 'premier_league_stats'
    }
    return mysql.connector.connect(**db_config)


# --- Data Scraping Function ---
def scrape_data():
  
  
    url = 'https://www.premierleague.com/clubs'  
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("Error fetching data:", response.status_code)
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    data = []
    
    # Example: assume the page has a table with class "statsTable" containing rows:
    # [Date, Home Team, Away Team, Home Score, Away Score, Home Form, Away Form]
    table = soup.find('table', {'class': 'statsTable'})
    if not table:
        print("No stats table found on page.")
        return data

    rows = table.find_all('tr')
    for row in rows[1:]:  # skip header row
        cols = row.find_all('td')
        if len(cols) >= 7:
            match_date = cols[0].text.strip()  # expected format: YYYY-MM-DD
            try:
                # Validate/convert the date string:
                match_date = datetime.datetime.strptime(match_date, "%Y-%m-%d").date()
            except Exception as e:
                continue  # Skip rows with invalid date format
            
            home_team = cols[1].text.strip()
            away_team = cols[2].text.strip()
            try:
                home_score = int(cols[3].text.strip())
                away_score = int(cols[4].text.strip())
                home_form = float(cols[5].text.strip())
                away_form = float(cols[6].text.strip())
            except ValueError:
                continue  # Skip rows with non-numeric values

            data.append({
                'date': match_date,
                'home_team': home_team,
                'away_team': away_team,
                'home_score': home_score,
                'away_score': away_score,
                'home_form': home_form,
                'away_form': away_form
            })
    return data

# --- Database Update Function ---
def update_database(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    for match in data:
        # Check if the match (by date and teams) already exists
        cursor.execute("SELECT id FROM matches WHERE date=%s AND home_team=%s AND away_team=%s", 
                       (match['date'], match['home_team'], match['away_team']))
        result = cursor.fetchone()
        if result:
            # Update existing record
            cursor.execute("""
                UPDATE matches
                SET home_score=%s, away_score=%s, home_form=%s, away_form=%s
                WHERE id=%s
            """, (match['home_score'], match['away_score'], match['home_form'], match['away_form'], result[0]))
        else:
            # Insert new record
            cursor.execute("""
                INSERT INTO matches (date, home_team, away_team, home_score, away_score, home_form, away_form)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (match['date'], match['home_team'], match['away_team'], match['home_score'], match['away_score'], match['home_form'], match['away_form']))
    conn.commit()
    cursor.close()
    conn.close()

# --- Prediction Function ---
def predict_outcomes():
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM matches", conn)
    conn.close()
    
    if df.empty or len(df) < 10:
        return None, None  # Not enough data for training
    
    # Create target: outcome (1 = Home Win, 0 = Draw, -1 = Away Win)
    def outcome(row):
        if row['home_score'] > row['away_score']:
            return 1
        elif row['home_score'] == row['away_score']:
            return 0
        else:
            return -1
    df['outcome'] = df.apply(outcome, axis=1)
    
    # Use features: historical form metrics (home_form and away_form)
    features = df[['home_form', 'away_form']]
    target = df['outcome']
    
    X_train, X_test, y_train, y_test = train_test_split(features, target, test_size=0.2, random_state=42)
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    predictions = model.predict(X_test)
    acc = accuracy_score(y_test, predictions)
    
    # Predict outcomes for the latest 5 matches (ordered by date)
    latest_matches = df.sort_values(by='date', ascending=False).head(5)
    X_latest = latest_matches[['home_form', 'away_form']]
    latest_preds = model.predict(X_latest)
    
    results = latest_matches[['date', 'home_team', 'away_team']].copy()
    results['predicted_outcome'] = latest_preds
    results['predicted_label'] = results['predicted_outcome'].map({1: 'Home Win', 0: 'Draw', -1: 'Away Win'})
    return results, acc

# --- Flask Routes ---
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, date, home_team, away_team, home_score, away_score, home_form, away_form FROM matches ORDER BY date DESC")
    matches = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('index.html', matches=matches)

@app.route('/update')  

def update():
    data = scrape_data()
    if data:
        update_database(data)
    return redirect(url_for('index'))

@app.route('/predict')
def predict():
    results, accuracy = predict_outcomes()
    if results is None:
        prediction_message = "Not enough data to build a predictive model."
        results_html = None
    else:
        prediction_message = f"Model Accuracy: {accuracy*100:.2f}%"
        results_html = results.to_html(classes='table table-striped', index=False)
    return render_template('predict.html', prediction_message=prediction_message, results_html=results_html)

if __name__ == '__main__':
    app.run(debug=True)
