from flask import Blueprint

restream_bp = Blueprint(
    "restream",
    __name__,
    url_prefix="/restream",
)

from . import routes