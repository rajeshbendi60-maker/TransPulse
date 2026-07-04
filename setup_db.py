from app import db, create_app

print("Recreating database schema...")
app = create_app()

with app.app_context():
    # Wipes all old/fake tables completely
    db.drop_all()
    # Builds fresh tables matching your updated code
    db.create_all()
    print("Database schema updated successfully!")