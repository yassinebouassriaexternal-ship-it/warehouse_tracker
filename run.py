from app import create_app, db

app = create_app()

def main():
    app.run(debug=True)

if __name__ == '__main__':
    main()

# CLI command to initialize the database
def init_db():
    with app.app_context():
        db.create_all()
        print('Database initialized.')