from flask_login import login_required as flask_login_required

def login_required(func):
    """
    Alias local de flask_login.login_required
    Permet une importation homogène dans le projet.
    """
    return flask_login_required(func)
