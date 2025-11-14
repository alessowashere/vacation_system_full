
# helper to initialize DB tables (if running without Alembic)
from app.db import engine, Base
print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Done.")
