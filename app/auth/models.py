from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.role = row["role"]
        self.avatar = row["avatar_filename"] or "default.png"

        self.created_at = row["created_at"] if "created_at" in row.keys() else None
        self.last_login = row["last_login"] if "last_login" in row.keys() else None

