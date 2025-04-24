from app import create_app

def main():
    app = create_app()
    # you can add host/port here if needed
    app.run(debug=True)

if __name__ == '__main__':
    main()