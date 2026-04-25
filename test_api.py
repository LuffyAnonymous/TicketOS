from app import app

app.config['LOGIN_DISABLED'] = True 

with app.test_client() as client:
    # Need to setup context.state.sent_order_rows
    import extensions as context
    from core.state import AppState
    context.state = AppState()
    context.state.sent_order_rows = [{"source": "LiveTicketGroup", "id": "TEST1", "event": "Ev"}]

    # Patch get_current_auth so it returns a dummy user
    import core.auth
    core.auth.get_current_auth = lambda: {"user": {"username": "admin", "role": "admin"}, "payload": {}}

    try:
        resp = client.post('/api/check-ticketsshop')
        print("STATUS:", resp.status_code)
        print("BODY:", resp.data.decode('utf-8')[:500])
    except Exception as e:
        import traceback
        traceback.print_exc()

