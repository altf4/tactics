import tornado.escape
import tornado.ioloop
import tornado.web
import tornado.websocket
import MySQLdb.constants
import torndb
import ConfigParser
import bcrypt
import logging
import uuid
from datetime import date

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", IndexHandler),
            (r"/lobby", LobbyHandler),
            (r"/chatsocket", ChatSocketHandler),
            (r"/getgamebyid/([0-9]+)", GetGameByIdHandler),
            (r"/version", VersionHandler),
            (r"/register", RegisterUserHandler),
            (r"/login", LoginHandler)
        ]

        config = ConfigParser.RawConfigParser()
        config.read('settings.cfg')
        secure_cookie_key = config.get('server', 'secure_cookie_key')
        db_url = config.get('database', 'url')
        db_username = config.get('database', 'username')
        db_password = config.get('database', 'password')
        self.db = torndb.Connection(db_url, "tactics", user=db_username, password=db_password)

        settings = dict(
            cookie_secret = secure_cookie_key,
            static_path = "static",
            xsrf_cookies = True,
            login_url = "/",
        )

        tornado.web.Application.__init__(self, handlers, **settings)


class BaseHandler(tornado.web.RequestHandler):
    @property
    def db(self):
        return self.application.db

    def get_current_user(self):
        user_id = self.get_secure_cookie("userid", max_age_days=1)
        if not user_id:
            return None
        return user_id

class IndexHandler(BaseHandler):
    def get(self):
        self.render("static/index.html")

class LobbyHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("static/lobby.html", messages = ChatSocketHandler.cache)

class ChatSocketHandler(tornado.websocket.WebSocketHandler):
    waiters = set()
    cache = []
    cache_size = 200

    def open(self):
        ChatSocketHandler.waiters.add(self)

    def on_close(self):
        ChatSocketHandler.waiters.remove(self)

    @classmethod
    def update_cache(cls, chat):
        cls.cache.append(chat)
        if len(cls.cache) > cls.cache_size:
            cls.cache = cls.cache[-cls.cache_size:]

    @classmethod
    def send_updates(cls, chat):
        logging.info("sending message to %d waiters", len(cls.waiters))
        for waiter in cls.waiters:
            try:
                waiter.write_message(chat)
            except:
                logging.error("Error sending message", exc_info=True)

    def on_message(self, message):
        logging.info("got message %r", message)
        parsed = tornado.escape.json_decode(message)
        userid = self.get_secure_cookie("userid", max_age_days=1)
        chat = {
            "id": str(uuid.uuid4()),
            "body": parsed["body"],
            }
        chat["html"] = tornado.escape.to_basestring(
            self.render_string("static/chatmessage.html", user=userid, message=chat))

        ChatSocketHandler.update_cache(chat)
        ChatSocketHandler.send_updates(chat)

class VersionHandler(BaseHandler):
    def get(self):
        response = { 'version': '0.0.1',
                     'last_build':  date.today().isoformat() }
        self.write(response)

class GetGameByIdHandler(BaseHandler):
    def get(self, id):
        response = { 'id': int(id),
                     'name': 'Crazy Game',
                     'release_date': date.today().isoformat() }
        self.write(response)

class RegisterUserHandler(BaseHandler):
    def post(self):
        name = self.get_argument('name', None)
        password1 = self.get_argument('password1', None)
        password2 = self.get_argument('password2', None)
        if not name or not password1 or not password2:
            raise tornado.web.HTTPError(400)

        if password1 != password2:
            raise tornado.web.HTTPError(422)

        if self.db.query("SELECT * FROM users WHERE name=%s", name):
            raise tornado.web.HTTPError(401)

        password1 = password1.encode('utf-8')
        hashed = bcrypt.hashpw(password1, bcrypt.gensalt())
        self.db.execute("INSERT INTO users (name, hash) VALUES (%s, %s)", name, hashed)

class LoginHandler(BaseHandler):
    def post(self):
        name = self.get_argument('name', None)
        password = self.get_argument('password', None)

        if not name or not password:
            raise tornado.web.HTTPError(403)

        rows = self.db.query("SELECT * from users WHERE name=%s LIMIT 1", name)
        if not rows:
            raise tornado.web.HTTPError(403)

        password = password.encode('utf-8')
        if rows[0].hash == bcrypt.hashpw(password, rows[0].hash.encode('utf-8')) and rows[0].name == name:
            self.set_secure_cookie("userid", name, httponly=True, expires_days=1)
        else:
            raise tornado.web.HTTPError(403)

if __name__ == "__main__":
    application = Application()
    application.listen(8080)
    tornado.ioloop.IOLoop.instance().start()
