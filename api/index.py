import os
import libsql_experimental as libsql
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from hashids import Hashids

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

domain_url = os.getenv("DOMAIN_URL", "https://bolted.site")
hashids_salt = os.getenv("HASHIDS_SALT")
hashids = Hashids(salt=hashids_salt, min_length=4)

turso_db_url = os.getenv("TURSO_DATABASE_URL")
turso_auth_token = os.getenv("TURSO_AUTH_TOKEN")

if not turso_db_url or not turso_auth_token:
    raise ValueError("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN environment variables are required")

class UrlInput(BaseModel):
    url: str

def get_db_connection():
    return libsql.connect(turso_db_url, auth_token=turso_auth_token)

def initialize_db():
    conn = get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_url TEXT NOT NULL,
                short_url TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()

def validate_url(url: str) -> str:
    url = url.lower()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

@app.post("/api/shorten")
async def shorten_url(url_input: UrlInput):
    validated_url = validate_url(url_input.url)
    
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO urls (original_url, short_url) VALUES (?, ?) RETURNING id",
            (validated_url, '')
        )
        result = cursor.fetchone()
        url_id = result[0]
        
        url_code = hashids.encode(url_id)
        complete_url = f"{domain_url}/{url_code}"
        
        conn.execute(
            "UPDATE urls SET short_url = ? WHERE id = ?",
            (complete_url, url_id)
        )
        conn.commit()
        
        return {"shortened_url": complete_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/redirect/{url_code}")
async def get_original_url(url_code: str):
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT original_url FROM urls WHERE short_url = ?",
            (f"{domain_url}/{url_code}",)
        )
        result = cursor.fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="URL not found")
        
        return {"original_url": result[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "url-shortener"}

initialize_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)