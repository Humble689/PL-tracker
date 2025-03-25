# config.py
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', ''),
    'database': os.getenv('MYSQL_DATABASE', 'premier_league')
}

# Football Data API configuration
FOOTBALL_DATA_API_URL = 'http://api.football-data.org/v4/'
FOOTBALL_DATA_API_KEY = os.getenv('FOOTBALL_DATA_API_KEY', '')
