import mysql.connector
from config import MYSQL_CONFIG

def setup_database():
    # First connect without database to create it
    config = MYSQL_CONFIG.copy()
    config.pop('database', None)
    
    try:
        # Connect to MySQL server
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        # Create database if it doesn't exist
        cursor.execute("CREATE DATABASE IF NOT EXISTS premier_league")
        print("Database 'premier_league' created successfully")
        
        # Close connection
        cursor.close()
        conn.close()
        
        # Now connect to the database to import schema
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        
        # Select the database
        cursor.execute("USE premier_league")
        
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(128) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create teams table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                short_name VARCHAR(3) NOT NULL,
                team_rank INT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create matches table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INT AUTO_INCREMENT PRIMARY KEY,
                season VARCHAR(9) NOT NULL,
                home_team_id INT NOT NULL,
                away_team_id INT NOT NULL,
                home_goals INT DEFAULT 0,
                away_goals INT DEFAULT 0,
                home_team_rank INT DEFAULT 0,
                away_team_rank INT DEFAULT 0,
                result VARCHAR(20) NOT NULL DEFAULT 'Scheduled',
                match_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (home_team_id) REFERENCES teams(id),
                FOREIGN KEY (away_team_id) REFERENCES teams(id)
            )
        """)
        
        # Create user_predictions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_predictions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                match_id INT NOT NULL,
                prediction VARCHAR(10) NOT NULL CHECK (prediction IN ('Home Win', 'Draw', 'Away Win')),
                predicted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (match_id) REFERENCES matches(id),
                UNIQUE KEY unique_user_match (user_id, match_id)
            )
        """)
        
        # Create user_preferences table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INT PRIMARY KEY,
                preferences TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Insert sample teams if teams table is empty
        cursor.execute("SELECT COUNT(*) FROM teams")
        if cursor.fetchone()[0] == 0:
            teams_data = [
                ('Arsenal', 'ARS', 1),
                ('Aston Villa', 'AVL', 2),
                ('Brighton', 'BHA', 3),
                ('Burnley', 'BUR', 4),
                ('Chelsea', 'CHE', 5),
                ('Crystal Palace', 'CRY', 6),
                ('Everton', 'EVE', 7),
                ('Leeds', 'LEE', 8),
                ('Leicester', 'LEI', 9),
                ('Liverpool', 'LIV', 10),
                ('Manchester City', 'MCI', 11),
                ('Manchester United', 'MUN', 12),
                ('Newcastle', 'NEW', 13),
                ('Norwich', 'NOR', 14),
                ('Southampton', 'SOU', 15),
                ('Tottenham', 'TOT', 16),
                ('Watford', 'WAT', 17),
                ('West Ham', 'WHU', 18),
                ('Wolves', 'WOL', 19),
                ('Brentford', 'BRE', 20)
            ]
            cursor.executemany("""
                INSERT INTO teams (name, short_name, team_rank)
                VALUES (%s, %s, %s)
            """, teams_data)
        
        conn.commit()
        print("Tables created and sample data inserted successfully")
        
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    setup_database() 