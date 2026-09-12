from dotenv import load_dotenv
import psycopg
import os

load_dotenv()

class DatabaseManager:

    def getConnection(self):
        try:
            print("Connecting to the database...")
            conn = psycopg.connect(
                os.getenv("DATABASE_URL")
            )

            cursor = conn.cursor(row_factory=dict_row)

            print("Connection Successful")

            return conn, cursor

        except Exception as e:
            print("Error connecting to the database:", e)
            return None, None

    def closeConnection(self, conn, cursor):
        if cursor:
            cursor.close()

        if conn:
            conn.close()
