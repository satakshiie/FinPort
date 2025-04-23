from app import app, db, Users
from werkzeug.security import generate_password_hash

with app.app_context():
    # Create a test user
    test_user = Users(
        name="JohnD",
        email="john1@example.com",
        password=generate_password_hash("1264")
    )

    db.session.add(test_user)
    db.session.commit()

    print("✅ Test user added to MySQL DB successfully!")