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
            (r"/queuesocket", QueueSocketHandler),
            (r"/matchsocket/(.+)", MatchSocketHandler),
            (r"/match/(.+)", MatchHandler),
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
        global db
        db = torndb.Connection(db_url, "tactics", user=db_username, password=db_password)

        settings = dict(
            cookie_secret = secure_cookie_key,
            static_path = "static",
            xsrf_cookies = True,
            login_url = "/",
        )

        tornado.web.Application.__init__(self, handlers, **settings)


class BaseHandler(tornado.web.RequestHandler):
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
    cache_size = 100

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
        chat = {
            "id": str(uuid.uuid4()),
            "body": parsed["body"],
            "userid": self.get_secure_cookie("userid", max_age_days=1),
            }
        chat["html"] = tornado.escape.to_basestring(
            self.render_string("static/chatmessage.html", message=chat))

        ChatSocketHandler.update_cache(chat)
        ChatSocketHandler.send_updates(chat)

class QueueSocketHandler(tornado.websocket.WebSocketHandler):
    #Users waiting for a match
    match_queue = {}

    def open(self):
        user_id = self.get_secure_cookie("userid", max_age_days=1)
        #Test if user is authenticated. If not, close the socket down and exit
        if(not user_id):
            self.close()
            return

        #If there are other players waiting in the queue, let's match them!
        if( len(QueueSocketHandler.match_queue) > 0):
            #TODO: We're picking one opponent arbitrarily right now. Let's get a real matchmaking system eventually
            opponent = QueueSocketHandler.match_queue.popitem()
            match_id = uuid.uuid4()
            match_message = {
                "match_id": str(match_id),
            }
            #Send to both "ourselves" and the opponent
            self.write_message(match_message)
            opponent[1].write_message(match_message)
            #create the match!
            db.execute("INSERT INTO matches (id, player_one, player_two) VALUES (%s, %s, %s)",
                match_id, user_id, opponent[0])

        else:
            QueueSocketHandler.match_queue[user_id] = self

    def on_close(self):
        user_id = self.get_secure_cookie("userid", max_age_days=1)
        if(user_id):
            if(QueueSocketHandler.match_queue.get(user_id)):
                del QueueSocketHandler.match_queue[user_id]

class VersionHandler(BaseHandler):
    def get(self):
        response = { 'version': '0.0.1',
                     'last_build':  date.today().isoformat() }
        self.write(response)

class MatchHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, id):
        user_id = self.get_current_user()
        match = db.query("SELECT * FROM matches WHERE player_one=%s or player_two=%s LIMIT 1", user_id, user_id)
        if not match:
            #User is not in a match...
            raise tornado.web.HTTPError(404)
            return

        if match[0].id != id:
            raise tornado.web.HTTPError(403)

        self.render("static/game.html")

    #Make change to match state (IE: play the game)
    @tornado.web.authenticated
    def put(self, id):
        return  #TODO

    #Resign from match
    @tornado.web.authenticated
    def delete(self, id):
        return #TODO

#global so you can access it outside the handler
match_sockets = {}

class MatchSocketHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        user_id = self.get_secure_cookie("userid", max_age_days=1)
        #Test if user is authenticated. If not, close the socket down and exit
        if(not user_id):
            self.close()
            return

        #If we already have a match socket for this player, kill the old one
        if(match_sockets.get(user_id)):
            match_sockets[user_id].close()

        #Lookup what match this user is in
        match = db.query("SELECT * FROM matches WHERE player_one=%s or player_two=%s LIMIT 1", user_id, user_id)
        if not match:
            #User is not in a match...
            self.close()
            return

        #Add socket to list
        match_sockets[user_id] = self


    def on_close(self):
        user_id = self.get_secure_cookie("userid", max_age_days=1)
        if(user_id):
            if(match_sockets.get(user_id)):
                del match_sockets[user_id]

class RegisterUserHandler(BaseHandler):
    def post(self):
        name = self.get_argument('name', None)
        password1 = self.get_argument('password1', None)
        password2 = self.get_argument('password2', None)
        if not name or not password1 or not password2:
            raise tornado.web.HTTPError(400)

        if password1 != password2:
            raise tornado.web.HTTPError(422)

        if db.query("SELECT * FROM users WHERE name=%s", name):
            raise tornado.web.HTTPError(401)

        password1 = password1.encode('utf-8')
        hashed = bcrypt.hashpw(password1, bcrypt.gensalt())
        db.execute("INSERT INTO users (name, hash, elo) VALUES (%s, %s, 500)", name, hashed)

class LoginHandler(BaseHandler):
    def post(self):
        name = self.get_argument('name', None)
        password = self.get_argument('password', None)

        if not name or not password:
            raise tornado.web.HTTPError(403)

        rows = db.query("SELECT * from users WHERE name=%s LIMIT 1", name)
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
