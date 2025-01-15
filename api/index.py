import os
import psycopg2
from dotenv import load_dotenv
from flask import Flask, render_template, request
from hashids import Hashids
from werkzeug.exceptions import InternalServerError

load_dotenv()

app = Flask(__name__, static_folder='static')
domain_url = os.getenv("DOMAIN_URL", "https://bolted.site")
hashids_salt = os.getenv("HASHIDS_SALT")
hashids = Hashids(salt=hashids_salt, min_length=4)
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_SSLMODE = os.getenv("DB_SSLMODE")

connection = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    dbname=DB_NAME,
    sslmode=DB_SSLMODE
)

connection.autocommit = True
cursor = connection.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS urls (
        id SERIAL PRIMARY KEY,
        original_url VARCHAR(255) NOT NULL,
        short_url VARCHAR(255) NOT NULL
    )
""")

def is_valid(url):
    url = url.lower()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

def process_input(original_url):
    validated_url = is_valid(original_url)
    cursor.execute("INSERT INTO urls (original_url, short_url) VALUES (%s, %s) RETURNING id", (validated_url, ''))
    url_id = cursor.fetchone()[0]
    url_code = hashids.encode(url_id)
    complete_url = f"{domain_url}/{url_code}"
    cursor.execute("UPDATE urls SET short_url = %s WHERE id = %s", (complete_url, url_id))
    return complete_url

@app.route('/')
def index():
    google_analytics_id = os.getenv('GOOGLE_ANALYTICS_ID')
    clarity_id = os.getenv('CLARITY_ID')
    return render_template('index.html', google_analytics_id=google_analytics_id, clarity_id=clarity_id, bolted_url=None)

@app.route('/bolted', methods=['POST'])
def shorten():
    original_url = request.form['url']
    bolted_url = process_input(original_url)
    return render_template('index.html', bolted_url=bolted_url)

@app.route('/<url_code>')
def redirect(url_code):
    try:
        cursor.execute("SELECT original_url FROM urls WHERE short_url = %s", (f"{domain_url}/{url_code}",))
        result = cursor.fetchone()

        if result:
            original_url = result[0]
            return render_template('redirect.html', original_url=original_url)
        else:
            return "URL no encontrada"
    except psycopg2.Error as e:
        error_message = f"Error de PostgreSQL: {e}"
        app.logger.error(error_message)
        return "Error interno del servidor"

if __name__ == '__main__':
    app.run(debug=True, port=8000)
