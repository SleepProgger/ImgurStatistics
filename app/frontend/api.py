from app.app_ import app
from app.DB import get_db

@app.route('/api/user_points')
def get_user_points():
    db = get_db()
    pass