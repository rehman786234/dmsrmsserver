from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from databasemanager import DatabaseManager
from pydantic import BaseModel

app = FastAPI()
db = DatabaseManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
class DataRequest(BaseModel):
    last_sync_time: str  # ISO format datetime string
def check_data(last_sync_time):
    try:
        conn, cursor = db.getConnection()
        if conn is None or cursor is None:
            return {"error": "Failed to connect to the database."}
        if last_sync_time is None or last_sync_time.strip() == "null":
            cursor.execute("SELECT * FROM check_update")
            res = cursor.fetchall()
            return {
                "update_available": True,
                "message":'Download Data now',
                "data": res
            }
        # Execute your SQL query here
        cursor.execute("SELECT * FROM check_update WHERE updated_at > %s", (last_sync_time,))
        res = cursor.fetchall()
        if len(res) == 0:
            return {
                "message":'No new data available',
                'update_available': False
            }

        return {
            'update_available': True,
            "data": res,
            'message': 'New data available for download'
        }
    except Exception as e:
        return {"error": str(e)}
        
    except Exception as e:
        return {"error": str(e)}
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

@app.post('/api/v1/dmsdata/check_new_data')
def check_new_data(request: DataRequest):
    res = check_data(request.last_sync_time)
    return res

if __name__ == "__main__":
    uvicorn.run('main:app', host="0.0.0.0", port=9990)
