import jwt
from app import app
from config import JWT_SECRET
import extensions as context
from core.state import AppState

with app.test_client() as client:
    # Initialize app state
    context.state = AppState()
    context.state.sent_order_rows = [{"source": "LiveTicketGroup", "id": "TEST1", "event": "Ev"}]

    # Generate a valid authentication token
    token = jwt.encode({"username": "admin", "role": "admin"}, JWT_SECRET, algorithm="HS256")
    client.set_cookie('token', token)

    print("Testing GET /api/orders...")
    try:
        resp = client.get('/api/orders')
        print("GET /api/orders STATUS:", resp.status_code)
        print("GET /api/orders BODY:", resp.data.decode('utf-8')[:500])
    except Exception as e:
        import traceback
        traceback.print_exc()

    print("\nTesting POST /api/system/check-ticketsshop...")
    try:
        resp = client.post('/api/system/check-ticketsshop')
        print("POST STATUS:", resp.status_code)
        print("POST BODY:", resp.data.decode('utf-8')[:500])
    except Exception as e:
        import traceback
        traceback.print_exc()
