from app import (
    create_app,
    db,
    _ensure_shared_driver_account,
    _ensure_default_admin,
)

print("=" * 60)
print("Recreating TransPulse Database...")
print("=" * 60)

app = create_app()

with app.app_context():
    # Remove all existing tables
    db.drop_all()

    # Create fresh schema
    db.create_all()

    # Create default system accounts
    _ensure_default_admin()
    _ensure_shared_driver_account()

    print("Database schema updated successfully!")
    print()
    print("DEFAULT LOGIN CREDENTIALS")
    print("----------------------------")
    print("ADMIN")
    print("Email         : admin@transpulse.com")
    print("Security Code : ATP-01")
    print("Password      : admin@tp")
    print()
    print("DRIVER")
    print("Email         : driver@transpulse.com")
    print("Password      : driver@tp")
    print("Driver Code   : DTP-001 (assigned by Admin)")