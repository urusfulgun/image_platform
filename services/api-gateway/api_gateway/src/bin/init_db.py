from sqlmodel import SQLModel
# Import your engine and models so SQLModel knows they exist
import api_gateway.domain.models
from api_gateway.db import create_db_and_tables

def init_db():
    print("Creating database tables...")
    create_db_and_tables()
    print("Database initialized successfully.")

if __name__ == "__main__":
    init_db()