from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    print("=== M World Luxury - Create Admin ===")

    username = 'MOSCOWW'
    email    = 'eriggap16@gmail.com'
    password = 'DENNIS234'

    existing = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()

    if existing:
        existing.password = generate_password_hash(password)
        existing.is_admin = True
        db.session.commit()
        print(f"✅ Admin '{username}' updated successfully!")
    else:
        admin = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print(f"✅ Admin '{username}' created successfully!")
        print(f"   Email:    {email}")
        print(f"   Login at: /admin")
