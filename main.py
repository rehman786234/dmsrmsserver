from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from databasemanager import DatabaseManager

app = FastAPI()
db = DatabaseManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
def get_data():
    try:
        conn, cursor = db.getConnection()
        if conn is None or cursor is None:
            return {"error": "Failed to connect to the database."}

        # Execute your SQL query here
        cursor.execute("SELECT * FROM customers")  # Replace with your actual table name
        customers = cursor.fetchall()
        cursor.execute("SELECT * FROM products")  # Replace with your actual table name
        products = cursor.fetchall()
        cursor.execute("SELECT * FROM categories")  # Replace with your actual table name
        categories = cursor.fetchall()
        cursor.execute("SELECT * FROM customer_types")  # Replace with your actual table name
        customer_types = cursor.fetchall()
        cursor.execute("SELECT * FROM areas")  # Replace with your actual table name
        areas = cursor.fetchall()
        cursor.execute("SELECT * FROM sub_areas")  # Replace with your actual table name
        sub_areas = cursor.fetchall()
        return {"customers": customers, "products": products, "categories": categories, "customer_types": customer_types, "areas": areas, "sub_areas": sub_areas}
    except Exception as e:
        return {"error": str(e)}
@app.get('/api/v1/dmsdata/download/all')
def download_all_data():
    
    result = get_data()
    if "error" in result:
        return {"error": result["error"]}
    return result

if __name__ == "__main__":
    uvicorn.run('main:app', host="0.0.0.0", port=9990)