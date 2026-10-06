import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    if os.getenv("FLASK_DEBUG") == "1":
        app.run(host="127.0.0.1", port=port, debug=True)
    else:
        from waitress import serve

        print(f"MarketFlow web running on http://127.0.0.1:{port}  (Go API: {app.config['GO_API_URL']})")
        serve(app, host="127.0.0.1", port=port, threads=8)
