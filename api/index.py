import os
import psycopg2

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

db_config = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "dbname": os.getenv("DB_NAME"),
    "sslmode": os.getenv("DB_SSLMODE")
}

class UrlInput(BaseModel):
    url: str

def get_db_connection():
    return psycopg2.connect(**db_config)

def initialize_db():
    conn = get_db_connection()
    conn.autocommit = True
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                id SERIAL PRIMARY KEY,
                original_url VARCHAR(255) NOT NULL,
                short_url VARCHAR(255) NOT NULL
            )
        """)
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
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO urls (original_url, short_url) VALUES (%s, %s) RETURNING id",
                (validated_url, '')
            )
            url_id = cursor.fetchone()[0]
            url_code = hashids.encode(url_id)
            complete_url = f"{domain_url}/{url_code}"
            cursor.execute(
                "UPDATE urls SET short_url = %s WHERE id = %s",
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
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT original_url FROM urls WHERE short_url = %s",
                (f"{domain_url}/{url_code}",)
            )
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="URL not found")
            return {"original_url": result[0]}
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

initialize_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)