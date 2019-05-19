import bottle
import os, sys, datetime
import string, random
from collections import defaultdict, namedtuple
from peewee import *

path = os.path.abspath(__file__)
dir_path = os.path.dirname(path)
app = bottle.Bottle()

DATABASE_NAME = "data.db"

questions = {}
contests = {}
question_dir = "files/questions"

Question = namedtuple("Question", "output statement")
Contest = namedtuple("Contest", "description questions start_time end_time")

db = SqliteDatabase(DATABASE_NAME)


class User(Model):
    username = CharField(unique=True)
    password = CharField()

    class Meta:
        database = db


class Session(Model):
    id = CharField(unique=True)
    username = CharField()

    class Meta:
        database = db


class Submission(Model):
    username = CharField()
    time = DateTimeField()
    question = IntegerField()
    contest = CharField()
    is_correct = BooleanField()

    class Meta:
        database = db
        indexes = (
            (("username","time"), True),
        )


db.connect()
db.create_tables([User, Session, Submission])

# dummy contests
contests["PRACTICE"] = Contest(
    description="practice questions",
    questions=[1, 2],
    start_time=datetime.datetime(day=1, month=1, year=1),
    end_time=datetime.datetime(day=1, month=1, year=9999),
)
contests["PASTCONTEST"] = Contest(
    description="somewhere in the past",
    questions=[1, 2],
    start_time=datetime.datetime(day=1, month=11, year=2018),
    end_time=datetime.datetime(day=1, month=12, year=2018),
)
contests["ONGOINGCONTEST"] = Contest(
    description="somewhere in the present",
    questions=[3, 4],
    start_time=datetime.datetime(day=1, month=4, year=2019),
    end_time=datetime.datetime(day=1, month=6, year=2019),
)
contests["FUTURECONTEST"] = Contest(
    description="somewhere in the future",
    questions=[5, 6],
    start_time=datetime.datetime(day=1, month=1, year=2020),
    end_time=datetime.datetime(day=1, month=10, year=2020),
)

for i in os.listdir(question_dir):
    if not i.isdigit():
        continue
    with open(os.path.join(question_dir, i, "output.txt"), "rb") as fl:
        output = fl.read()
    with open(os.path.join(question_dir, i, "statement.txt"), "r") as fl:
        statement = fl.read()
    questions[i] = Question(output=output, statement=statement)


def login_required(function):
    def login_redirect(*args, **kwargs):
        if not logggedIn():
            return bottle.template("home.html", message="Login required.")
        return function(*args, **kwargs)

    return login_redirect


@app.route("/")
def changePath():
    return bottle.redirect("/home")


@app.get("/home")
def home():
    if logggedIn():
        return bottle.redirect("/dashboard")
    return bottle.template("home.html", message="")


@app.get("/dashboard")
@login_required
def dashboard():
    return bottle.template("dashboard.html", contests=contests)


@app.get("/contest/<code>/<number>")
@login_required
def question(code, number):
    if not code in contests:
        return "Contest does not exist"
    if contests[code].start_time > datetime.datetime.now():
        return "The contest had not started yet."
    statement = questions[number].statement
    return bottle.template(
        "question.html", question_number=number, contest=code, question=statement
    )


@app.get("/contest/<code>")
@login_required
def contest(code):
    if not code in contests:
        return "Contest does not exist"
    if contests[code].start_time > datetime.datetime.now():
        return "The contest had not started yet."
    return bottle.template("contest.html", code=code, contest=contests[code])


@app.get("/question/<path:path>")
def download(path):
    return bottle.static_file(path, root=question_dir)


@app.get("/static/<filepath:path>")
def server_static(filepath):
    return bottle.static_file(filepath, root=os.path.join(dir_path, "static"))


@app.get("/ranking/<code>")
def contest_ranking(code):
    order = (
        Submission.select(
            Submission.username, fn.count(Submission.question).alias("score")
        )
        .where((Submission.is_correct == True) & (Submission.contest == code))
        .group_by(Submission.username)
        .order_by(fn.count(Submission.question).desc())
    )
    order = list(order.tuples())
    order = [
        (username, score, rank) for rank, (username, score) in enumerate(order, start=1)
    ]
    return bottle.template("rankings.html", people=order)


@app.get("/ranking")
def rankings():
    order = (
        Submission.select(
            Submission.username, fn.count(Submission.question).alias("score")
        )
        .where(Submission.is_correct == True)
        .group_by(Submission.username)
        .order_by(fn.count(Submission.question).desc())
    )
    order = list(order.tuples())
    order = [
        (username, score, rank) for rank, (username, score) in enumerate(order, start=1)
    ]
    return bottle.template("rankings.html", people=order)


def logggedIn():
    if not bottle.request.get_cookie("s_id"):
        return False
    return (
        Session.select().where(Session.id == bottle.request.get_cookie("s_id")).exists()
    )


def createSession(username):
    session_id = "".join(
        random.choice(string.ascii_letters + string.digits) for i in range(20)
    )
    bottle.response.set_cookie(
        "s_id",
        session_id,
        expires=datetime.datetime.now() + datetime.timedelta(days=30),
    )
    try:
        Session.create(id=session_id, username=username)
    except IntegrityError:
        return abort("Error! Please try again.")
    return bottle.redirect("/dashboard")


@app.post("/login")
def login():
    username = bottle.request.forms.get("username")
    password = bottle.request.forms.get("password")
    if (
        not User.select()
        .where((User.username == username) & (User.password == password))
        .exists()
    ):
        return bottle.template("home.html", message="Invalid credentials.")
    return createSession(username)


@app.post("/register")
def register():
    username = bottle.request.forms.get("username")
    password = bottle.request.forms.get("password")
    try:
        User.create(username=username, password=password)
    except IntegrityError:
        return bottle.template(
            "home.html", message="Username already exists. Select a different username"
        )
    return createSession(username)


@app.get("/logout")
def logout():
    Session.delete().where(Session.id == bottle.request.get_cookie("s_id")).execute()
    bottle.response.delete_cookie("s_id")
    return bottle.redirect("/home")


@app.post("/check/<code>/<number>")
@login_required
def file_upload(code, number):
    username = Session.get(Session.id == bottle.request.get_cookie("s_id")).username
    time = datetime.datetime.now()
    uploaded = bottle.request.files.get("upload").file.read()
    expected = questions[number].output
    expected = expected.strip()
    uploaded = uploaded.strip()
    ans = uploaded == expected
    try:
        Submission.create(
            username=username, question=number, time=time, contest=code, is_correct=ans
        )
    except:
        abort("Error in inserting submission to database.")
    if not ans:
        return "Wrong Answer!!"
    else:
        return "Solved! Great Job! "


@app.error(404)
def error404(error):
    return template("error.html", errorcode=error.status_code, errorbody=error.body)


bottle.run(app, host="localhost", port=8080)
