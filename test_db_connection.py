import mysql.connector
from config import MYSQL_CONFIG

def test_connection():
    try:
        cnx = mysql.connector.connect(**MYSQL_CONFIG)
        print("Connection successful!")
        cnx.close()
    except mysql.connector.Error as err:
        print(f"Error: {err}")

if __name__ == "__main__":
    test_connection()
