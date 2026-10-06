# MarketFlow Web (Flask)

A browser front end for the MarketFlow Go backend. Flask renders the pages and talks to the Go API over HTTP; it has no database of its own and never touches the Go project's files.

**In scope:** log in (customer and seller), browse and search products, product detail with variants, cart, checkout (pickup), order tracking, seller order handling, customer profiles, chat.

## Run it

```powershell
cd C:\market_flow_flask
python -m venv .venv ; .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then edit SECRET_KEY and GO_API_URL
python run.py               # http://127.0.0.1:5000
```

Start the Go server first (`go run .` in `market_flow_app/server`, see `README.MD`). `GO_API_URL` defaults to `http://localhost:8080`. Use `FLASK_DEBUG=1 python run.py` for auto-reload.

## No database handy? Use the mock

```powershell
python dev/mock_go_api.py     # fake Go API on :8080, in memory
python run.py
python dev/smoke_test.py      # 78 end-to-end checks against the mock
```

Mock accounts (password `pass1234`): `maria` customer, `juan` seller (store 10), `lita` seller (store 20). `pedro` is a business owner and is correctly refused by the web login.

## How it fits together

| Piece | Where |
|---|---|
| Go API client (all backend calls) | `app/api.py` |
| Login, session, role gate | `app/auth.py`, `app/helpers.py` |
| Browse, product, cart, checkout | `app/shop.py` |
| Orders (buyer and store side) | `app/orders.py` |
| Chat (pages + JSON proxy for polling) | `app/chat.py`, `static/js/chat.js` |
| Profiles | `app/profile.py` |
| Uploaded images, proxied from Go | `/media/<path>` in `app/main.py` |

- **Auth:** `POST /api/v1/login`, then the JWT is kept in a signed, HttpOnly session cookie and sent as `Authorization: Bearer` on every call. The browser never sees the token. A 401 from Go logs the user out with a message.
- **Security:** every POST/DELETE needs a CSRF token; user ids always come from the session, never the request; checkout takes prices, sellers and stores from the server-side cart, not the form; redirects are same-site only.
- **Chat** polls every 4 seconds while the tab is visible (Go's rate limit is 30 messages a minute per user).
- **Sellers** are the `seller` role. They shop like customers and also get *Store orders*: accept, tick items, mark ready, complete, cancel.

## Things to know about the Go server

These come from reading its code; none are changed here.

1. **Order tracking route is broken for normal URLs.** `/api/v1/orders/{id}/tracking` can't parse the id (it checks `parts[4] == "tracking"`). The web app calls `/api/v1/orders/tracking/{id}/tracking`, which the handler does accept. This is verified against the mock only; if the real call fails, the progress strip still works from the order's current status, just without timestamps.
2. **Most endpoints trust `user_id` from the query or body** instead of the JWT (cart, orders, profile). The web app always sends the logged-in user's id, but anyone calling the Go API directly could pass someone else's.
3. **Checkout is pickup only.** Delivery needs rider selection and fees, which is out of scope here.
4. Order status, `complete` and `cancel` have owner rules in Go: after "mark ready" the order belongs to the employee who prepared it, so only they can complete it. The UI shows Go's error if another employee tries.
5. Cart rows don't carry a currency, so the web app looks it up per product (cached).
