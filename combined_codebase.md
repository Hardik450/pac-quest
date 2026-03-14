# Codebase Directory Dump

## `app.py`

```python
"""
PAC-HUNT Flask Backend — Complete Server-Side Logic
=====================================================
All game logic, answers, hints, and puzzle content are server-side.
No answers or secrets are exposed to the client.

Collections (MongoDB database: pac_hunt):
  • players      — registered players (username + email)
  • game_sessions— active game state per player
  • leaderboard  — top scores
  • scorecards   — full per-session scorecard on victory
"""

import hashlib
import os
import time
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import (Flask, jsonify, redirect, render_template,
                   request, session, url_for)
from dotenv import load_dotenv

load_dotenv()

try:
    from pymongo import MongoClient, DESCENDING
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False
    print("⚠  pymongo not installed. Run:  pip install 'pymongo[srv]'")

# ══════════════════════════════════════════════
# App & Config
# ══════════════════════════════════════════════

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pac-hunt-secret-key-change-in-prod')

LEVEL_TIME_LIMIT = 300
HINT_COSTS       = [0, 30, 60]
MAX_LIVES        = 3
TOTAL_LEVELS     = 4

MONGO_URI = os.environ.get('MONGO_URI', os.getenv("MONGODB_STRING"))
DB_NAME   = 'pac_hunt'

# ══════════════════════════════════════════════
# ALL GAME CONTENT — SERVER SIDE ONLY
# ══════════════════════════════════════════════

def _sha256(text):
    return hashlib.sha256(text.upper().strip().encode()).hexdigest()

# Answers — never sent to client
ANSWERS = {
    1: "I",
    2: "that",
    3: "want it",
    4: "way",
}
ANSWER_HASHES = {k: _sha256(v) for k, v in ANSWERS.items()}
ANSWER_HASHES["final"] = _sha256("I want it that way")

# Hints — served one at a time from backend only
HINTS = {
    1: [
        "The page you're looking for shows an error… a very specific error code that web developers know well.",
        "Once you're on the error page, look very carefully at ALL the text on that page. Some text might be styled to blend in…",
        "Look for text that is the same color as the background. Try selecting all text (Ctrl+A) on the 404 page!",
    ],
    2: [
        "The image above doesn't load… but the browser still knows something about it. What attributes does an image have?",
        "Right-click on the broken image → Inspect Element. Look at the HTML. The <img> tag has attributes like 'src' and 'alt'.",
        "Check the 'alt' attribute of the image — it contains a hidden message with the word!",
    ],
    3: [
        "The octopus-cat is GitHub's mascot! Visit the linked repository.",
        "On GitHub, find the 'commits' section (look for a clock icon or text saying 'X commits'). Click it to see the history.",
        "Click on an older commit to see what the README file looked like before. The secret word was removed but is visible in the history!",
    ],
    4: [
        "Think through how you would probably hear the voice of the web if it could talk to you directly…",
        "open dev tools and try to see how network request works",
        "In the network response headers of the '/api/secret-ping' request, look for a custom header called 'X-Secret-Word'.",
    ],
}

# Riddles and page content — served from backend
LEVEL_CONTENT = {
    1: {
        "title": "THE WHISPERING VOID",
        "story": "The first fragment of the secret phrase is hidden in a place where only those who know where to look can find it...",
        "riddle": [
            ('text', 'I am the '),
            ('emphasis', 'voice'),
            ('text', ' that speaks to developers,'),
            ('br',),
            ('text', 'Hidden in plain sight, yet '),
            ('emphasis', 'invisible'),
            ('text', ' to most.'),
            ('br',),
            ('text', 'When errors cry out, I catch their tears.'),
            ('br',),
            ('text', 'When secrets need telling, I whisper them here.'),
            ('br',), ('br',),
            ('highlight', 'Find the page that doesn\'t exist,'),
            ('br',),
            ('highlight', 'And look carefully at what hides in plain sight.'),
        ],
        "answer_label": "ENTER THE WORD YOU FOUND:",
        "has_action_link": True,
        "action_url": "/oops",
        "action_text": "🚪 ENTER THE VOID",
        "tutorial": None,
    },
    2: {
        "title": "THE BROKEN FRAME",
        "story": "Not everything on the web is as it appears... Sometimes what seems broken holds hidden meaning.",
        "riddle": [
            ('text', 'A picture speaks a thousand words,'),
            ('br',),
            ('text', 'But what of one that '),
            ('emphasis', 'refuses to appear'),
            ('text', '?'),
            ('br',), ('br',),
            ('text', 'The eyes see nothing but emptiness,'),
            ('br',),
            ('text', 'Yet beneath the '),
            ('emphasis', 'surface'),
            ('text', ', truth remains.'),
            ('br',), ('br',),
            ('highlight', 'Look not at what is shown,'),
            ('br',),
            ('highlight', 'But at what the image tries to tell you.'),
        ],
        "answer_label": "WHAT WORD IS HIDDEN IN THE IMAGE?",
        "has_broken_image": True,
        "tutorial": None,
    },
    3: {
        "title": "THE ARCHIVES OF TIME",
        "story": "The next fragment is hidden in the past… Where every change is remembered, but not always seen.",
        "riddle": [
            ('text', 'In the realm where code is '),
            ('emphasis', 'born'),
            ('text', ' and '),
            ('emphasis', 'reborn'),
            ('text', ','),
            ('br',),
            ('text', 'A cat with eight legs guards the kingdom.'),
            ('br',), ('br',),
            ('text', 'The present shows one truth,'),
            ('br',),
            ('text', 'But the '),
            ('emphasis', 'past holds another'),
            ('text', '.'),
            ('br',), ('br',),
            ('highlight', 'Dig through the history of changes,'),
            ('br',),
            ('highlight', 'And you shall find what was once there.'),
        ],
        "answer_label": "ENTER THE WORD FROM THE PAST:",
        "has_action_link": True,
        "action_url": "https://github.com/pushkar-hue/Tale-of-Time/tree/main",
        "action_text": "🐙 VISIT THE REPOSITORY",
        "action_external": True,
        "tutorial": {
            "title": "About Git & GitHub",
            "steps": [
                "GitHub is where developers store and share code",
                "Every change made to code is saved as a 'commit'",
                "You can view the history of all commits on any repository",
                "Sometimes, secrets are hidden in <strong>older commits</strong> that have since been changed",
                "Look for the 'commits' or 'history' section on GitHub!",
            ],
        },
    },
    4: {
        "title": "THE NETWORK WHISPERS",
        "story": "The final piece is hidden in the invisible conversations that happen every time you click a button…",
        "riddle": [
            ('text', 'When you click, a message flies,'),
            ('br',),
            ('emphasis', 'Invisible'),
            ('text', ' to untrained eyes.'),
            ('br',), ('br',),
            ('text', 'The Network knows what browsers say,'),
            ('br',),
            ('text', 'In '),
            ('emphasis', 'headers'),
            ('text', ' hidden, secrets lay.'),
            ('br',), ('br',),
            ('highlight', 'Click the button below,'),
            ('br',),
            ('highlight', 'Then watch what travels in the glow.'),
        ],
        "answer_label": "WHAT'S THE FINAL WORD(S)?",
        "has_secret_button": True,
        "tutorial": {
            "title": "About Network Requests",
            "steps": [
                "When websites communicate with servers, they send 'requests'",
                "Open DevTools (<span class='key-hint'>F12</span>) and go to the <strong>Network</strong> tab",
                "Click the button below WHILE the Network tab is open",
                "You'll see a new request appear — click on it!",
                "Look at the <strong>Response Headers</strong> section",
                "Headers contain metadata — including sometimes… secrets!",
            ],
        },
    },
}

# ══════════════════════════════════════════════
# MongoDB Connection
# ══════════════════════════════════════════════

_mongo_client = None
_db           = None

def get_db():
    global _mongo_client, _db
    if not MONGO_AVAILABLE:
        return None
    if _db is None:
        try:
            _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            _mongo_client.admin.command('ping')
            _db = _mongo_client[DB_NAME]
            _ensure_indexes(_db)
            print(f"Connected to MongoDB Atlas — database: '{DB_NAME}'")
        except Exception as e:
            print(f"MongoDB connection failed: {e}")
            _db = None
    return _db

def _ensure_indexes(db):
    db.leaderboard.create_index([("score", DESCENDING)])
    db.leaderboard.create_index([("completed_at", DESCENDING)])
    db.scorecards.create_index([("session_id", 1)], unique=True)
    db.scorecards.create_index([("completed_at", DESCENDING)])
    db.players.create_index([("username", 1)], unique=True)
    db.players.create_index([("email", 1)], unique=True)

# ══════════════════════════════════════════════
# MongoDB helpers
# ══════════════════════════════════════════════

def _compute_score(lives_remaining, total_time, total_hints):
    base = lives_remaining * 1000 + max(0, 1200 - total_time)
    hint_penalty = total_hints * 50
    return max(0, base - hint_penalty)

def _fmt_time(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"

def _serialize_doc(doc):
    if doc is None:
        return None
    if isinstance(doc.get("completed_at"), datetime):
        doc["completed_at"] = doc["completed_at"].strftime("%Y-%m-%d %H:%M UTC")
    if isinstance(doc.get("registered_at"), datetime):
        doc["registered_at"] = doc["registered_at"].strftime("%Y-%m-%d %H:%M UTC")
    doc.pop("_id", None)
    return doc

def mongo_register_player(username, email):
    db = get_db()
    if db is None:
        return {"ok": False, "error": "Database unavailable"}
    username = username.strip()
    email = email.strip().lower()
    if not username or not email:
        return {"ok": False, "error": "Username and email are required"}
    if len(username) < 2 or len(username) > 20:
        return {"ok": False, "error": "Username must be 2-20 characters"}
    if "@" not in email or "." not in email:
        return {"ok": False, "error": "Invalid email address"}

    existing_user = db.players.find_one({"username": username})
    existing_email = db.players.find_one({"email": email})

    if existing_user and existing_email:
        if existing_user["_id"] == existing_email["_id"]:
            return {"ok": True, "player_id": str(existing_user["_id"]),
                    "username": username, "returning": True}
        else:
            return {"ok": False, "error": "Username or email already taken by different accounts"}
    elif existing_user:
        return {"ok": False, "error": "Username already taken"}
    elif existing_email:
        return {"ok": False, "error": "Email already registered with a different username"}

    try:
        result = db.players.insert_one({
            "username": username,
            "email": email,
            "registered_at": datetime.now(timezone.utc),
            "games_played": 0,
            "games_completed": 0,
        })
        return {"ok": True, "player_id": str(result.inserted_id),
                "username": username, "returning": False}
    except Exception as e:
        return {"ok": False, "error": f"Registration failed: {str(e)}"}

def mongo_add_to_leaderboard(username, session_id, time_taken, lives_remaining, total_hints):
    db    = get_db()
    score = _compute_score(lives_remaining, time_taken, total_hints)
    entry = {
        "name":            username,
        "session_id":      session_id,
        "time_taken":      time_taken,
        "lives_remaining": lives_remaining,
        "hints_used":      total_hints,
        "score":           score,
        "display_time":    _fmt_time(time_taken),
        "completed_at":    datetime.now(timezone.utc),
    }
    if db is not None:
        db.leaderboard.insert_one(entry)
        return _get_top_leaderboard(db)
    entry["completed_at"] = entry["completed_at"].strftime("%Y-%m-%d %H:%M UTC")
    return [entry]

def _get_top_leaderboard(db, limit=10):
    return [_serialize_doc(d) for d in
            db.leaderboard.find({}, {"_id": 0})
                          .sort("score", DESCENDING)
                          .limit(limit)]

def mongo_get_leaderboard(limit=50):
    db = get_db()
    if db is None:
        return []
    return [_serialize_doc(d) for d in
            db.leaderboard.find({}, {"_id": 0})
                          .sort("score", DESCENDING)
                          .limit(limit)]

def mongo_save_scorecard(state, player_name):
    db = get_db()
    if db is None:
        return None
    session_id = state.get("session_id", str(uuid.uuid4()))
    total_hints = state.get("total_hints_used", 0)
    card = {
        "session_id":           session_id,
        "player_name":          player_name,
        "score":                _compute_score(state.get("lives", 0),
                                               state.get("total_time", 0), total_hints),
        "total_time":           state.get("total_time", 0),
        "display_time":         _fmt_time(state.get("total_time", 0)),
        "lives_remaining":      state.get("lives", 0),
        "lives_lost":           MAX_LIVES - state.get("lives", 0),
        "hints_used":           total_hints,
        "total_time_penalties": state.get("total_time_penalties", 0),
        "collected_words":      state.get("collected_words", []),
        "level_stats":          state.get("level_stats", []),
        "completed_at":         datetime.now(timezone.utc),
        "game_version":         "2.0",
    }
    try:
        db.scorecards.replace_one({"session_id": session_id}, card, upsert=True)
        return session_id
    except Exception as e:
        print(f"Scorecard save failed: {e}")
        return None

def mongo_get_scorecard(session_id):
    db = get_db()
    if db is None:
        return None
    doc = db.scorecards.find_one({"session_id": session_id}, {"_id": 0})
    return _serialize_doc(doc) if doc else None

def mongo_update_player_stats(username, completed=False):
    db = get_db()
    if db is None:
        return
    update = {"$inc": {"games_played": 1}}
    if completed:
        update["$inc"]["games_completed"] = 1
    db.players.update_one({"username": username}, update)

# ══════════════════════════════════════════════
# Flask Session helpers
# ══════════════════════════════════════════════

def new_game_state(username="Anonymous"):
    return {
        "session_id":           str(uuid.uuid4()),
        "username":             username,
        "lives":                MAX_LIVES,
        "current_level":        1,
        "level_start":          None,
        "time_penalty":         0,
        "hints_used":           0,
        "collected_words":      ["", "", "", ""],
        "started":              False,
        "total_time":           0,
        "level_stats":          [],
        "total_hints_used":     0,
        "total_time_penalties": 0,
        "levels_completed":     [],
    }

def get_state():
    if "game" not in session:
        session["game"] = new_game_state(session.get("username", "Anonymous"))
    return session["game"]

def save_state(state):
    session["game"] = state
    session.modified = True

def time_remaining(state):
    if not state.get("level_start"):
        return LEVEL_TIME_LIMIT
    elapsed = int(time.time() - state["level_start"])
    return max(0, LEVEL_TIME_LIMIT - elapsed - state.get("time_penalty", 0))

def require_game(f):
    """For page routes, redirect. For API routes, return JSON."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_state().get("started"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "No game in progress",
                                "redirect": url_for("index")}), 400
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

def require_registered(f):
    """For page routes, redirect. For API routes, return JSON."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("username"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Not registered",
                                "redirect": url_for("register")}), 401
            return redirect(url_for("register"))
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════════════
# Page Routes
# ══════════════════════════════════════════════

@app.route("/")
def index():
    if not session.get("username"):
        return redirect(url_for("register"))
    state       = get_state()
    in_progress = state.get("started") and state.get("current_level", 1) <= TOTAL_LEVELS
    return render_template("index.html",
                           in_progress=in_progress,
                           current_level=state.get("current_level", 1),
                           username=session.get("username", ""))

@app.route("/register")
def register():
    if session.get("username"):
        return redirect(url_for("index"))
    return render_template("register.html")

@app.route("/level/<int:level_num>")
@require_registered
@require_game
def level(level_num):
    state = get_state()
    if level_num < 1 or level_num > TOTAL_LEVELS:
        return redirect(url_for("index"))
    if level_num > state["current_level"]:
        return redirect(url_for("level", level_num=state["current_level"]))
    if state["current_level"] != level_num or not state.get("level_start"):
        state.update({"current_level": level_num, "level_start": time.time(),
                      "time_penalty": 0, "hints_used": 0})
        save_state(state)

    content = LEVEL_CONTENT[level_num]
    return render_template("level.html",
        level_num=level_num,
        lives=state["lives"],
        time_remaining=time_remaining(state),
        collected_words=state["collected_words"],
        current_level=state["current_level"],
        total_levels=TOTAL_LEVELS,
        content=content,
        username=session.get("username", ""))

@app.route("/oops")
@require_registered
@require_game
def oops():
    state = get_state()
    return render_template("oops.html",
        lives=state["lives"],
        time_remaining=time_remaining(state),
        current_level=state["current_level"],
        total_levels=TOTAL_LEVELS,
        collected_words=state["collected_words"])

@app.route("/victory")
@require_registered
@require_game
def victory():
    state = get_state()
    return render_template("victory.html",
                           collected_words=state["collected_words"],
                           username=session.get("username", ""))

@app.route("/gameover")
def gameover():
    username = session.get("username", "")
    session.pop("game", None)
    return render_template("gameover.html", username=username)

@app.route("/leaderboard")
def leaderboard():
    board = mongo_get_leaderboard(limit=50)
    return render_template("leaderboard.html", board=board,
                           db_ok=get_db() is not None)

@app.route("/scorecard/<session_id>")
def scorecard(session_id):
    card = mongo_get_scorecard(session_id)
    if not card:
        return redirect(url_for("leaderboard"))
    return render_template("scorecard.html", card=card)

# ══════════════════════════════════════════════
# API Routes
# ══════════════════════════════════════════════

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip()

    result = mongo_register_player(username, email)
    if result["ok"]:
        session["username"] = result["username"]
        session["email"] = email.lower()
        session.modified = True
        return jsonify({
            "ok": True,
            "username": result["username"],
            "returning": result.get("returning", False),
            "redirect": url_for("index")
        })
    return jsonify(result)

@app.route("/api/start", methods=["POST"])
@require_registered
def api_start():
    username = session.get("username", "Anonymous")
    session["game"] = new_game_state(username)
    state = session["game"]
    state["started"] = True
    state["level_start"] = time.time()
    save_state(state)
    mongo_update_player_stats(username, completed=False)
    return jsonify({"ok": True, "redirect": url_for("level", level_num=1)})

@app.route("/api/resume", methods=["POST"])
@require_registered
def api_resume():
    state = get_state()
    if not state.get("started"):
        return jsonify({"ok": False, "error": "No game in progress"})
    return jsonify({"ok": True, "redirect": url_for("level",
                   level_num=state.get("current_level", 1))})

@app.route("/api/state")
@require_registered
def api_state():
    state = get_state()
    return jsonify({
        "lives": state["lives"],
        "current_level": state["current_level"],
        "time_remaining": time_remaining(state),
        "collected_words": state["collected_words"],
        "hints_used": state["hints_used"],
        "username": session.get("username", ""),
    })

@app.route("/api/hint", methods=["POST"])
@require_registered
@require_game
def api_hint():
    data     = request.get_json() or {}
    hint_num = int(data.get("hint", 1))
    state    = get_state()
    lvl      = state["current_level"]

    if hint_num < 1 or hint_num > 3:
        return jsonify({"ok": False, "error": "Invalid hint number"})
    if hint_num > state["hints_used"] + 1:
        return jsonify({"ok": False, "error": "Unlock previous hints first"})
    if hint_num > state["hints_used"]:
        cost = HINT_COSTS[hint_num - 1]
        state["time_penalty"]         += cost
        state["total_time_penalties"]  = state.get("total_time_penalties", 0) + cost
        state["hints_used"]           = hint_num
        state["total_hints_used"]     = state.get("total_hints_used", 0) + 1
        save_state(state)

    # Return hint text from server
    hint_list = HINTS.get(lvl, ["", "", ""])
    hint_text = hint_list[hint_num - 1] if hint_num <= len(hint_list) else ""
    return jsonify({
        "ok": True,
        "time_remaining": time_remaining(state),
        "hint_num": hint_num,
        "hints_used": state["hints_used"],
        "hint_text": hint_text,
    })

@app.route("/api/answer", methods=["POST"])
@require_registered
@require_game
def api_answer():
    data   = request.get_json() or {}
    answer = str(data.get("answer", "")).strip()
    lvl    = int(data.get("level", 0))
    state  = get_state()

    if lvl != state["current_level"]:
        return jsonify({"ok": False, "correct": False, "error": "Level mismatch"})
    remaining = time_remaining(state)
    if remaining <= 0:
        return _handle_timeout(state)

    correct = (_sha256(answer) == ANSWER_HASHES.get(lvl))
    if correct:
        elapsed = int(time.time() - state["level_start"])
        state.setdefault("level_stats", []).append({
            "level": lvl, "time_taken": elapsed,
            "hints_used": state["hints_used"], "time_penalty": state["time_penalty"],
        })
        state["total_time"]        = state.get("total_time", 0) + elapsed
        state["collected_words"][lvl - 1] = ANSWERS[lvl]
        state.setdefault("levels_completed", []).append(lvl)

        # Save scorecard after every level for live tracking
        username = session.get("username", "Anonymous")
        mongo_save_scorecard(state, username)

        if lvl == TOTAL_LEVELS:
            # Update leaderboard immediately on completing all puzzle levels
            total_hints = state.get("total_hints_used", 0)
            mongo_add_to_leaderboard(
                username, state["session_id"],
                state["total_time"], state["lives"], total_hints
            )
            save_state(state)
            return jsonify({
                "ok": True, "correct": True,
                "redirect": url_for("victory"),
                "leaderboard_updated": True
            })

        state.update({"current_level": lvl + 1, "level_start": time.time(),
                      "time_penalty": 0, "hints_used": 0})
        save_state(state)
        return jsonify({
            "ok": True, "correct": True,
            "redirect": url_for("level", level_num=lvl + 1),
            "leaderboard_updated": True
        })
    save_state(state)
    return jsonify({"ok": True, "correct": False, "time_remaining": remaining})

@app.route("/api/final", methods=["POST"])
@require_registered
@require_game
def api_final():
    data    = request.get_json() or {}
    answer  = str(data.get("answer", "")).strip()
    state   = get_state()
    correct = (_sha256(answer) == ANSWER_HASHES["final"])
    if correct:
        username = session.get("username", "Anonymous")
        state["started"] = False
        mongo_update_player_stats(username, completed=True)
        mongo_save_scorecard(state, username)
        save_state(state)
        return jsonify({
            "ok": True, "correct": True,
            "session_id": state.get("session_id"),
            "scorecard_url": url_for("scorecard", session_id=state.get("session_id")),
            "redirect": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        })
    return jsonify({"ok": True, "correct": False})

@app.route("/api/secret-ping", methods=["POST"])
@require_registered
@require_game
def api_secret_ping():
    """Level 4 puzzle — secret is in the response header."""
    state = get_state()
    if state.get("current_level") != 4:
        return jsonify({"ok": True, "message": "Nothing to see here"})
    resp = jsonify({
        "ok": True,
        "message": "Check the response headers! Look for X-Secret-Word.",
    })
    resp.headers["X-Secret-Word"] = "way"
    resp.headers["X-Game"] = "PAC-HUNT"
    resp.headers["X-Hint"] = "The answer is in this header called X-Secret-Word"
    return resp

@app.route("/api/timeout", methods=["POST"])
@require_registered
@require_game
def api_timeout():
    return _handle_timeout(get_state())

def _handle_timeout(state):
    state["lives"] -= 1
    username = session.get("username", "Anonymous")
    if state["lives"] <= 0:
        save_state(state)
        mongo_save_scorecard(state, username)
        session.pop("game", None)
        return jsonify({"ok": True, "lives": 0, "redirect": url_for("gameover")})
    state["level_start"]  = time.time()
    state["time_penalty"] = 0
    save_state(state)
    return jsonify({"ok": True, "lives": state["lives"],
                    "time_remaining": LEVEL_TIME_LIMIT})

@app.route("/api/leaderboard/submit", methods=["POST"])
@require_registered
def api_leaderboard_submit():
    """Explicit leaderboard submission (backup — auto-saved on level complete)."""
    state = get_state()
    username = session.get("username", "Anonymous")

    session_id      = state.get("session_id", str(uuid.uuid4()))
    time_taken      = state.get("total_time", 0)
    lives_remaining = state.get("lives", MAX_LIVES)
    total_hints     = state.get("total_hints_used", 0)

    mongo_save_scorecard(state, username)
    top10 = mongo_add_to_leaderboard(username, session_id, time_taken, lives_remaining, total_hints)

    return jsonify({
        "ok":            True,
        "score":         _compute_score(lives_remaining, time_taken, total_hints),
        "leaderboard":   top10,
        "scorecard_url": url_for("scorecard", session_id=session_id),
    })

@app.route("/api/leaderboard")
def api_leaderboard_json():
    limit = min(int(request.args.get("limit", 50)), 100)
    board = mongo_get_leaderboard(limit=limit)
    return jsonify({"ok": True, "count": len(board), "leaderboard": board})

@app.route("/api/scorecard/<session_id>")
def api_scorecard_json(session_id):
    card = mongo_get_scorecard(session_id)
    if not card:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": True, "scorecard": card})

@app.route("/api/reset", methods=["POST"])
def api_reset():
    session.pop("game", None)
    return jsonify({"ok": True, "redirect": url_for("index")})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True, "redirect": url_for("register")})

@app.route("/api/health")
def api_health():
    db   = get_db()
    ok   = db is not None
    info = {"ok": True, "mongo": "connected" if ok else "disconnected",
            "pymongo": MONGO_AVAILABLE,
            "collections": list(db.list_collection_names()) if ok else []}
    return jsonify(info), 200 if ok else 503

# ══════════════════════════════════════════════
# Run
# ══════════════════════════════════════════════

if __name__ == "__main__":
    get_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
```

## `static\css\style.css`

```css
/* ============================================
   PAC-HUNT v2 - Retro Arcade Theme
   ============================================ */

@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');

:root {
    --pacman-yellow: #FFFF00;
    --ghost-red: #FF0000;
    --ghost-pink: #FFB8FF;
    --ghost-cyan: #00FFFF;
    --ghost-orange: #FFB852;
    --maze-blue: #2121DE;
    --bg-black: #000000;
    --dot-white: #FFFF00;
    --text-glow: 0 0 10px #FFFF00, 0 0 20px #FFFF00, 0 0 30px #FFFF00;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Press Start 2P', cursive;
    background-color: var(--bg-black);
    color: white;
    min-height: 100vh;
    overflow-x: hidden;
}

/* Animated Background with Dots */
.game-bg {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: -1;
    background-image:
        radial-gradient(circle, var(--dot-white) 3px, transparent 3px);
    background-size: 40px 40px;
    opacity: 0.1;
    animation: moveDots 20s linear infinite;
}

@keyframes moveDots {
    0% { background-position: 0 0; }
    100% { background-position: 40px 40px; }
}

/* Maze Border Effect */
.maze-border {
    border: 4px solid var(--maze-blue);
    box-shadow:
        inset 0 0 20px rgba(33, 33, 222, 0.5),
        0 0 20px rgba(33, 33, 222, 0.5);
    border-radius: 10px;
}

/* ============================================
   Landing Page Styles
   ============================================ */

.landing-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 20px;
    text-align: center;
}

.game-title {
    font-size: 3rem;
    color: var(--pacman-yellow);
    text-shadow: var(--text-glow);
    margin-bottom: 20px;
    animation: flicker 2s infinite;
}

@keyframes flicker {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.8; }
}

.subtitle {
    font-size: 1rem;
    color: var(--ghost-cyan);
    margin-bottom: 40px;
    letter-spacing: 2px;
}

/* Pac-Man Animation */
.pacman-container {
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 40px 0;
    overflow: hidden;
    width: 300px;
}

.pacman {
    width: 60px;
    height: 60px;
    background: var(--pacman-yellow);
    border-radius: 50%;
    position: relative;
    animation: eat 0.5s infinite;
}

.pacman::before {
    content: '';
    position: absolute;
    top: 50%;
    right: 0;
    width: 50%;
    height: 50%;
    background: var(--bg-black);
    transform-origin: left center;
    animation: mouth 0.5s infinite;
}

@keyframes mouth {
    0%, 100% {
        clip-path: polygon(0 0, 100% 50%, 0 100%);
    }
    50% {
        clip-path: polygon(0 20%, 100% 50%, 0 80%);
    }
}

.dots {
    display: flex;
    gap: 15px;
    margin-left: 20px;
}

.dot {
    width: 12px;
    height: 12px;
    background: var(--dot-white);
    border-radius: 50%;
    animation: blink 1s infinite;
}

.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
.dot:nth-child(4) { animation-delay: 0.6s; }

@keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
}

/* Ghost Decorations */
.ghosts {
    display: flex;
    gap: 30px;
    margin: 30px 0;
}

.ghost {
    width: 50px;
    height: 60px;
    border-radius: 25px 25px 0 0;
    position: relative;
    animation: float 2s ease-in-out infinite;
}

.ghost::before {
    content: '';
    position: absolute;
    bottom: -10px;
    left: 0;
    width: 100%;
    height: 20px;
    background: inherit;
    clip-path: polygon(
        0% 0%, 20% 100%, 40% 0%, 60% 100%, 80% 0%, 100% 100%, 100% 0%
    );
}

.ghost.blinky { background: var(--ghost-red); }
.ghost.pinky { background: var(--ghost-pink); animation-delay: 0.5s; }
.ghost.inky { background: var(--ghost-cyan); animation-delay: 1s; }
.ghost.clyde { background: var(--ghost-orange); animation-delay: 1.5s; }

.ghost-eyes {
    position: absolute;
    top: 15px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    gap: 8px;
}

.ghost-eye {
    width: 12px;
    height: 14px;
    background: white;
    border-radius: 50%;
    position: relative;
}

.ghost-eye::after {
    content: '';
    position: absolute;
    width: 6px;
    height: 6px;
    background: blue;
    border-radius: 50%;
    top: 4px;
    left: 3px;
}

@keyframes float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-10px); }
}

/* Start Button */
.start-btn {
    font-family: 'Press Start 2P', cursive;
    font-size: 1.2rem;
    padding: 20px 40px;
    background: transparent;
    color: var(--pacman-yellow);
    border: 4px solid var(--pacman-yellow);
    cursor: pointer;
    transition: all 0.3s ease;
    text-transform: uppercase;
    letter-spacing: 3px;
    position: relative;
    overflow: hidden;
}

.start-btn::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: var(--pacman-yellow);
    transition: left 0.3s ease;
    z-index: -1;
}

.start-btn:hover {
    color: var(--bg-black);
}

.start-btn:hover::before {
    left: 0;
}

.start-btn:active {
    transform: scale(0.95);
}

/* Blinking Text */
.blink {
    animation: textBlink 1s infinite;
}

@keyframes textBlink {
    0%, 50% { opacity: 1; }
    51%, 100% { opacity: 0; }
}

/* ============================================
   Game HUD Styles
   ============================================ */

.game-hud {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    padding: 15px 30px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: rgba(0, 0, 0, 0.9);
    border-bottom: 3px solid var(--maze-blue);
    z-index: 1000;
}

.hud-section {
    display: flex;
    align-items: center;
    gap: 10px;
}

.hud-label {
    font-size: 0.7rem;
    color: var(--ghost-cyan);
}

.hud-value {
    font-size: 1rem;
    color: var(--pacman-yellow);
}

/* Lives Display */
.lives {
    display: flex;
    gap: 5px;
}

.life {
    width: 20px;
    height: 20px;
    background: var(--pacman-yellow);
    border-radius: 50%;
    clip-path: polygon(
        100% 50%,
        50% 50%,
        25% 6.7%,
        0% 50%,
        25% 93.3%,
        50% 50%
    );
    transition: all 0.3s ease;
}

.life.lost {
    background: #333;
    opacity: 0.3;
}

/* Timer */
.timer {
    font-size: 1.5rem;
    color: var(--pacman-yellow);
}

.timer.warning {
    color: var(--ghost-orange);
    animation: pulse 0.5s infinite;
}

.timer.danger {
    color: var(--ghost-red);
    animation: pulse 0.25s infinite;
}

@keyframes pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.1); }
}

/* Level Indicator */
.level-indicator {
    display: flex;
    gap: 8px;
}

.level-dot {
    width: 15px;
    height: 15px;
    border: 2px solid var(--maze-blue);
    border-radius: 50%;
    transition: all 0.3s ease;
}

.level-dot.active {
    background: var(--ghost-cyan);
    border-color: var(--ghost-cyan);
    box-shadow: 0 0 10px var(--ghost-cyan);
}

.level-dot.completed {
    background: var(--pacman-yellow);
    border-color: var(--pacman-yellow);
}

/* ============================================
   Level Container Styles
   ============================================ */

.level-container {
    max-width: 900px;
    margin: 100px auto 40px;
    padding: 40px;
}

.level-header {
    text-align: center;
    margin-bottom: 40px;
}

.level-number {
    font-size: 0.9rem;
    color: var(--ghost-cyan);
    margin-bottom: 10px;
}

.level-title {
    font-size: 1.5rem;
    color: var(--pacman-yellow);
    text-shadow: var(--text-glow);
    margin-bottom: 20px;
}

/* Riddle Box */
.riddle-box {
    background: linear-gradient(135deg, #1a1a2e 0%, #0f0f1a 100%);
    padding: 30px;
    margin: 30px 0;
    position: relative;
}

.riddle-box::before {
    content: '?';
    position: absolute;
    top: -15px;
    left: 20px;
    font-size: 2rem;
    color: var(--ghost-pink);
    text-shadow: 0 0 10px var(--ghost-pink);
}

.riddle-text {
    font-size: 0.75rem;
    line-height: 2.5;
    color: #ddd;
    text-align: center;
}

.riddle-emphasis {
    color: var(--ghost-cyan);
    text-decoration: underline;
}

/* Tutorial Box */
.tutorial-box {
    background: rgba(0,255,255,0.05);
    border: 2px dashed var(--ghost-cyan);
    padding: 20px 25px;
    margin: 25px 0;
    border-radius: 8px;
}

.tutorial-title {
    color: var(--ghost-cyan);
    font-size: .75rem;
    margin-bottom: 15px;
}

.tutorial-title::before {
    content: '💡';
    font-size: 1.2rem;
    margin-right: 10px;
}

.tutorial-steps {
    list-style: none;
    padding: 0;
}

.tutorial-steps li {
    font-size: .6rem;
    color: #ccc;
    margin: 10px 0;
    padding-left: 15px;
    position: relative;
    line-height: 1.8;
}

.tutorial-steps li::before {
    content: '►';
    color: var(--pacman-yellow);
    position: absolute;
    left: 0;
}

.key-hint {
    background: #222;
    border: 1px solid #555;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: .55rem;
    color: var(--pacman-yellow);
}

/* Buttons */
.btn {
    font-family: 'Press Start 2P', cursive;
    padding: 12px 24px;
    cursor: pointer;
    font-size: .65rem;
    text-decoration: none;
    display: inline-block;
    transition: all .2s ease;
    border: none;
}

.btn-primary {
    background: var(--pacman-yellow);
    color: var(--bg-black);
}

.btn-primary:hover {
    box-shadow: 0 0 20px var(--pacman-yellow);
    transform: scale(1.03);
}

.btn-secondary {
    background: transparent;
    color: var(--ghost-cyan);
    border: 2px solid var(--ghost-cyan);
}

.btn-secondary:hover {
    background: var(--ghost-cyan);
    color: #000;
}

.btn-hint {
    background: transparent;
    color: var(--ghost-pink);
    border: 2px solid var(--ghost-pink);
    margin: 5px;
    font-size: .55rem;
    padding: 8px 16px;
}

.btn-hint:hover {
    background: rgba(255,184,255,.15);
}

.action-buttons {
    text-align: center;
    margin: 25px 0;
    display: flex;
    gap: 15px;
    justify-content: center;
    flex-wrap: wrap;
}

/* Answer section */
.answer-section {
    margin: 30px 0;
    text-align: center;
}

.answer-label {
    display: block;
    font-size: .6rem;
    color: var(--ghost-cyan);
    margin-bottom: 15px;
}

.answer-input-group {
    display: flex;
    justify-content: center;
    gap: 10px;
    flex-wrap: wrap;
}

.answer-input {
    font-family: 'Press Start 2P', cursive;
    font-size: 1rem;
    padding: 15px 20px;
    background: #111;
    border: 3px solid var(--maze-blue);
    color: var(--pacman-yellow);
    text-transform: uppercase;
    text-align: center;
    width: 200px;
}

.answer-input:focus {
    outline: none;
    border-color: var(--pacman-yellow);
    box-shadow: 0 0 20px rgba(255, 255, 0, 0.3);
}

.answer-input::placeholder {
    color: #444;
    font-size: 0.7rem;
}

.submit-btn {
    font-family: 'Press Start 2P', cursive;
    font-size: 0.8rem;
    padding: 15px 30px;
    background: var(--pacman-yellow);
    color: var(--bg-black);
    border: none;
    cursor: pointer;
    transition: all 0.3s ease;
}

.submit-btn:hover {
    transform: scale(1.05);
    box-shadow: 0 0 20px var(--pacman-yellow);
}

/* Hint System */
.hint-container {
    margin: 20px 0;
    text-align: center;
}

.hint-text-dynamic {
    background: rgba(255, 184, 255, 0.1);
    border: 2px dashed var(--ghost-pink);
    padding: 20px;
    margin: 15px 0;
    font-size: 0.7rem;
    color: var(--ghost-pink);
    animation: fadeIn 0.5s ease;
    text-align: left;
}

/* Collected Words Display */
.collected-display {
    text-align: center;
    margin-bottom: 20px;
    padding: 15px;
    background: rgba(0, 0, 0, 0.5);
    border-radius: 10px;
}

.collected-label {
    font-size: 0.6rem;
    color: var(--ghost-cyan);
    margin-bottom: 10px;
}

.collected-words-shuffled {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 10px;
}

.collected-word {
    font-size: 0.8rem;
    color: var(--pacman-yellow);
    padding: 8px 15px;
    background: rgba(255, 255, 0, 0.1);
    border: 2px solid var(--pacman-yellow);
    border-radius: 5px;
}

.collected-word.placeholder {
    color: #333;
    border-color: #333;
    background: transparent;
}

/* ============================================
   404 Page Styles
   ============================================ */

.error-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    text-align: center;
    padding: 20px;
}

.error-code {
    font-size: 8rem;
    color: var(--ghost-red);
    text-shadow: 0 0 30px var(--ghost-red);
    animation: glitch 2s infinite;
}

@keyframes glitch {
    0%, 90%, 100% { transform: translate(0); }
    92% { transform: translate(-5px, 5px); }
    94% { transform: translate(5px, -5px); }
    96% { transform: translate(-5px, -5px); }
    98% { transform: translate(5px, 5px); }
}

.error-message {
    font-size: 1rem;
    color: var(--ghost-cyan);
    margin: 20px 0;
}

.error-ghost {
    font-size: 5rem;
    margin: 30px 0;
    animation: float 2s ease-in-out infinite;
}

.back-btn {
    margin-top: 30px;
}

/* ============================================
   Broken Image Puzzle
   ============================================ */

.puzzle-image-container {
    text-align: center;
    margin: 30px 0;
}

/* ============================================
   Final Answer Page
   ============================================ */

.final-container {
    max-width: 800px;
    margin: 100px auto;
    padding: 40px;
    text-align: center;
}

.word-slot {
    background: #111;
    border: 3px solid var(--maze-blue);
    padding: 15px 25px;
    min-width: 120px;
    font-size: .8rem;
}

.word-slot.filled {
    border-color: var(--pacman-yellow);
    color: var(--pacman-yellow);
}

.final-input {
    width: 100%;
    max-width: 500px;
    font-family: 'Press Start 2P', cursive;
    font-size: 1rem;
    padding: 20px;
    background: #111;
    border: 3px solid var(--maze-blue);
    color: var(--pacman-yellow);
    text-align: center;
    margin: 20px auto;
    display: block;
}

.final-input:focus {
    outline: none;
    border-color: var(--pacman-yellow);
    box-shadow: 0 0 20px rgba(255, 255, 0, 0.3);
}

/* ============================================
   Victory / Game Over
   ============================================ */

.victory-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    text-align: center;
    padding: 20px;
}

.victory-title {
    font-size: 2rem;
    color: var(--pacman-yellow);
    text-shadow: var(--text-glow);
    margin-bottom: 30px;
}

.trophy {
    font-size: 5rem;
    margin: 20px 0;
    animation: bounce 1s infinite;
}

@keyframes bounce {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-20px); }
}

.gameover-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    text-align: center;
    padding: 20px;
}

.gameover-title {
    font-size: 3rem;
    color: var(--ghost-red);
    text-shadow: 0 0 30px var(--ghost-red);
    margin-bottom: 30px;
    animation: flicker 0.5s infinite;
}

.gameover-ghost {
    font-size: 8rem;
    margin: 30px 0;
}

/* ============================================
   Modal Styles
   ============================================ */

.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.9);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 2000;
}

.modal-overlay.active {
    display: flex;
}

.modal {
    background: #111;
    padding: 40px;
    max-width: 500px;
    text-align: center;
}

.modal-title {
    font-size: 1.2rem;
    color: var(--pacman-yellow);
    margin-bottom: 20px;
}

.modal-text {
    font-size: 0.7rem;
    color: #ccc;
    margin-bottom: 30px;
    line-height: 2;
}

/* ============================================
   Leaderboard table
   ============================================ */

table th, table td {
    border-bottom: 1px solid #1a1a1a;
}

/* ============================================
   Responsive Design
   ============================================ */

@media (max-width: 768px) {
    .game-title {
        font-size: 1.8rem;
    }

    .game-hud {
        flex-wrap: wrap;
        gap: 10px;
        padding: 10px;
    }

    .level-container {
        margin: 80px 10px 20px;
        padding: 20px;
    }

    .riddle-text {
        font-size: 0.65rem;
    }

    .answer-input-group {
        flex-direction: column;
        align-items: center;
    }

    .error-code {
        font-size: 4rem;
    }

    .life {
        width: 16px;
        height: 16px;
    }
}

/* ============================================
   Utility Classes
   ============================================ */

.text-center { text-align: center; }
.text-yellow { color: var(--pacman-yellow); }
.text-cyan { color: var(--ghost-cyan); }
.text-pink { color: var(--ghost-pink); }
.text-red { color: var(--ghost-red); }
.mt-20 { margin-top: 20px; }
.mb-20 { margin-bottom: 20px; }
.hidden { display: none !important; }
```

## `static\js\game.js`

```javascript
/**
 * PAC-HUNT Client v2 — Server-Authoritative
 * ==========================================
 * NO answers, hints, or game logic in client code.
 * All puzzle solutions are validated server-side.
 * Hints are fetched from the server on demand.
 */

"use strict";

// ─────────────────────────────────────────────
// HUD
// ─────────────────────────────────────────────

function initHUD(state) {
    renderLives(state.lives);
    renderLevelDots(state.current_level, state.total_levels || 4);
    updateTimerDisplay(state.time_remaining);
    renderCollectedWords(state.collected_words || []);
}

function renderLives(count) {
    const el = document.getElementById('lives');
    if (!el) return;
    el.innerHTML = '';
    for (let i = 0; i < 3; i++) {
        const life = document.createElement('div');
        life.className = 'life' + (i >= count ? ' lost' : '');
        el.appendChild(life);
    }
}

function renderLevelDots(current, total) {
    const el = document.getElementById('levelIndicator');
    if (!el) return;
    el.innerHTML = '';
    for (let i = 1; i <= total; i++) {
        const dot = document.createElement('div');
        dot.className = 'level-dot';
        if (i < current) dot.classList.add('completed');
        else if (i === current) dot.classList.add('active');
        el.appendChild(dot);
    }
}

function updateTimerDisplay(seconds) {
    const el = document.getElementById('timer');
    if (!el) return;
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    el.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    el.classList.remove('warning', 'danger');
    if (seconds <= 30) el.classList.add('danger');
    else if (seconds <= 60) el.classList.add('warning');
}

function renderCollectedWords(words) {
    const el = document.getElementById('collectedDisplay');
    if (!el) return;
    const filled = words.filter(Boolean);
    const missing = words.filter(w => !w).length;
    const shuffled = [...filled].sort(() => Math.random() - 0.5);

    el.innerHTML = '';
    shuffled.forEach(() => {
        const span = document.createElement('span');
        span.className = 'collected-word';
        span.textContent = '✓ FOUND';
        el.appendChild(span);
    });
    for (let i = 0; i < missing; i++) {
        const span = document.createElement('span');
        span.className = 'collected-word placeholder';
        span.textContent = '???';
        el.appendChild(span);
    }
}

// ─────────────────────────────────────────────
// Client-side countdown (display only — server is authoritative)
// ─────────────────────────────────────────────

let _timerInterval = null;
let _secondsLeft = 0;
let _ticking = false;

function startClientTimer(initialSeconds) {
    _secondsLeft = initialSeconds;
    if (_timerInterval) clearInterval(_timerInterval);
    _ticking = true;
    updateTimerDisplay(_secondsLeft);

    _timerInterval = setInterval(async () => {
        if (!_ticking) return;
        _secondsLeft = Math.max(0, _secondsLeft - 1);
        updateTimerDisplay(_secondsLeft);

        if (_secondsLeft <= 0) {
            clearInterval(_timerInterval);
            _ticking = false;
            await handleTimeout();
        }
    }, 1000);
}

function stopClientTimer() {
    _ticking = false;
    if (_timerInterval) clearInterval(_timerInterval);
}

async function handleTimeout() {
    try {
        const res = await fetch('/api/timeout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}'
        });
        const data = await res.json();

        if (data.redirect) {
            window.location.href = data.redirect;
            return;
        }

        renderLives(data.lives);
        showModal(
            "TIME'S UP!",
            `You lost a life! ${data.lives} ${data.lives === 1 ? 'life' : 'lives'} remaining.`,
            () => startClientTimer(data.time_remaining || 300)
        );
    } catch (err) {
        console.error('Timeout handler failed:', err);
        // Retry after a moment
        setTimeout(() => window.location.reload(), 2000);
    }
}

// ─────────────────────────────────────────────
// Answer submission
// ─────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const submitBtn = document.getElementById('submitAnswer');
    const answerInput = document.getElementById('answerInput');

    if (submitBtn && answerInput) {
        submitBtn.addEventListener('click', submitAnswer);
        answerInput.addEventListener('keypress', e => {
            if (e.key === 'Enter') submitAnswer();
        });
    }

    // Hint buttons — fetch hint text from server
    document.querySelectorAll('.hint-btn').forEach(btn => {
        const hintNum = parseInt(btn.dataset.hint || '1');
        btn.addEventListener('click', () => requestHint(hintNum));
    });
});

async function submitAnswer() {
    const input = document.getElementById('answerInput');
    const answer = input?.value?.trim();
    if (!answer) return;

    const level = window.PH_LEVEL;
    if (!level) return;

    try {
        const res = await fetch('/api/answer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answer, level })
        });
        const data = await res.json();

        if (!data.ok) {
            showFeedback(data.error || 'Error', 'error');
            if (data.redirect) {
                setTimeout(() => { window.location.href = data.redirect; }, 1500);
            }
            return;
        }

        if (data.correct) {
            stopClientTimer();
            showFeedback('✓ CORRECT! LEADERBOARD UPDATED!', 'success');
            setTimeout(() => { window.location.href = data.redirect; }, 1200);
        } else {
            input.classList.add('shake');
            setTimeout(() => input.classList.remove('shake'), 500);
            showFeedback('Wrong answer! Try again.', 'error');
            if (data.time_remaining !== undefined) {
                _secondsLeft = data.time_remaining;
                updateTimerDisplay(_secondsLeft);
            }
        }
    } catch (err) {
        console.error('Answer submission failed:', err);
        showFeedback('Network error! Try again.', 'error');
    }
}

// ─────────────────────────────────────────────
// Hints — fetched from server, no client-side storage
// ─────────────────────────────────────────────

async function requestHint(hintNum) {
    try {
        const res = await fetch('/api/hint', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ hint: hintNum })
        });
        const data = await res.json();

        if (!data.ok) {
            showFeedback(data.error || 'Hint error', 'error');
            return;
        }

        // Display hint text received from server
        const container = document.getElementById('hintContent');
        if (container && data.hint_text) {
            // Check if this hint is already displayed
            if (!document.getElementById(`hintDisplay${hintNum}`)) {
                const div = document.createElement('div');
                div.id = `hintDisplay${hintNum}`;
                div.className = 'hint-text-dynamic';
                div.innerHTML = `<strong>HINT ${hintNum}:</strong> ${data.hint_text}`;
                container.appendChild(div);
            }
        }

        if (data.time_remaining !== undefined) {
            _secondsLeft = data.time_remaining;
            updateTimerDisplay(_secondsLeft);
        }
    } catch (err) {
        console.error('Hint request failed:', err);
        showFeedback('Network error! Try again.', 'error');
    }
}

// ─────────────────────────────────────────────
// Modal
// ─────────────────────────────────────────────

function showModal(title, message, onClose) {
    const overlay = document.getElementById('modalOverlay');
    const titleEl = document.getElementById('modalTitle');
    const textEl = document.getElementById('modalText');
    const btn = document.getElementById('modalBtn');
    if (!overlay) return;

    if (titleEl) titleEl.textContent = title;
    if (textEl) textEl.textContent = message;
    overlay.classList.add('active');

    if (btn) {
        btn.onclick = () => {
            overlay.classList.remove('active');
            if (onClose) onClose();
        };
    }
}

// ─────────────────────────────────────────────
// Feedback toast
// ─────────────────────────────────────────────

function showFeedback(message, type = 'info') {
    // Remove any existing feedback
    document.querySelectorAll('.pac-feedback').forEach(el => el.remove());

    const el = document.createElement('div');
    el.className = 'pac-feedback';
    el.textContent = message;
    el.style.cssText = `
        position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
        padding:15px 30px;
        background:${type === 'error' ? '#ff0000' : type === 'success' ? '#00ff00' : '#00FFFF'};
        color:#000;font-family:'Press Start 2P',cursive;font-size:.7rem;
        z-index:3000;animation:slideUp .3s ease;border-radius:4px;
        white-space:nowrap;max-width:90vw;overflow:hidden;text-overflow:ellipsis;
    `;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
}

// ─────────────────────────────────────────────
// Injected animations
// ─────────────────────────────────────────────

const _style = document.createElement('style');
_style.textContent = `
    @keyframes shake {
        0%,100%{transform:translateX(0)}
        25%{transform:translateX(-10px)}
        75%{transform:translateX(10px)}
    }
    .shake{animation:shake .5s ease;border-color:#ff0000!important}
    @keyframes slideUp{
        from{transform:translate(-50%,100px);opacity:0}
        to{transform:translate(-50%,0);opacity:1}
    }
    @keyframes fall{
        to{transform:translateY(100vh);opacity:0}
    }
    @keyframes fadeIn{
        from{opacity:0;transform:translateY(-10px)}
        to{opacity:1;transform:translateY(0)}
    }
    .hidden{display:none!important}
`;
document.head.appendChild(_style);
```

## `templates\base.html`

```html
<!-- templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}PAC-HUNT{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    {% block head %}{% endblock %}
</head>
<body>
    <div class="game-bg"></div>
    {% block body %}{% endblock %}
    <script src="{{ url_for('static', filename='js/game.js') }}"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

## `templates\gameover.html`

```html
<!-- templates/gameover.html -->
{% extends "base.html" %}
{% block title %}GAME OVER | PAC-HUNT{% endblock %}

{% block body %}
<div class="gameover-container">
    <div class="gameover-ghost">👻</div>
    <h1 class="gameover-title">GAME OVER</h1>
    {% if username %}
    <p style="font-size:.7rem;color:var(--ghost-cyan);margin:10px 0;">
        Better luck next time, <span style="color:var(--pacman-yellow);">{{ username }}</span>!
    </p>
    {% endif %}
    <p style="font-size:.8rem;color:var(--ghost-cyan);margin:20px 0;">The ghosts got you!</p>
    <p style="font-size:.7rem;color:#666;margin:20px 0;line-height:2;">
        But don't worry, every great hunter<br>fails before they succeed!
    </p>
    <div class="action-buttons" style="margin-top:40px;">
        <button class="btn btn-primary" id="retryBtn">INSERT COIN TO RETRY</button>
        <a href="{{ url_for('leaderboard') }}" class="btn btn-secondary">🏆 LEADERBOARD</a>
    </div>
    <p class="blink" style="font-size:.6rem;color:var(--ghost-red);margin-top:40px;">PRESS START TO CONTINUE</p>
</div>
{% endblock %}

{% block scripts %}
<script>
document.getElementById('retryBtn').addEventListener('click', async () => {
    const res = await fetch('/api/reset', { method:'POST',
        headers:{'Content-Type':'application/json'}, body:'{}' });
    const data = await res.json();
    window.location.href = data.redirect;
});
</script>
{% endblock %}
```

## `templates\index.html`

```html
<!-- templates/index.html -->
{% extends "base.html" %}
{% block title %}PAC-HUNT | The Ultimate Treasure Hunt{% endblock %}

{% block body %}
<div class="landing-container">
    <h1 class="game-title">PAC-HUNT</h1>
    <p class="subtitle">THE ULTIMATE TREASURE HUNT</p>

    <div style="font-size:.6rem;color:var(--ghost-cyan);margin-bottom:10px;">
        Playing as: <span style="color:var(--pacman-yellow);">{{ username }}</span>
        <a href="#" id="logoutLink" style="color:var(--ghost-red);font-size:.5rem;margin-left:15px;text-decoration:none;">[LOGOUT]</a>
    </div>

    <div class="pacman-container">
        <div class="pacman"></div>
        <div class="dots">
            <div class="dot"></div><div class="dot"></div>
            <div class="dot"></div><div class="dot"></div>
        </div>
    </div>

    <div class="ghosts">
        <div class="ghost blinky"><div class="ghost-eyes"><div class="ghost-eye"></div><div class="ghost-eye"></div></div></div>
        <div class="ghost pinky"><div class="ghost-eyes"><div class="ghost-eye"></div><div class="ghost-eye"></div></div></div>
        <div class="ghost inky"><div class="ghost-eyes"><div class="ghost-eye"></div><div class="ghost-eye"></div></div></div>
        <div class="ghost clyde"><div class="ghost-eyes"><div class="ghost-eye"></div><div class="ghost-eye"></div></div></div>
    </div>

    <div class="rules-box maze-border" style="margin:30px auto;padding:25px;max-width:600px;">
        <h3 style="color:var(--ghost-cyan);font-size:.9rem;margin-bottom:20px;">📜 RULES OF THE HUNT</h3>
        <ul style="list-style:none;text-align:left;">
            <li style="margin:15px 0;font-size:.65rem;color:#ccc;"><span style="color:var(--pacman-yellow);">►</span> Complete 4 levels to find the secret phrase</li>
            <li style="margin:15px 0;font-size:.65rem;color:#ccc;"><span style="color:var(--pacman-yellow);">►</span> You have <span style="color:var(--ghost-red);">5 MINUTES</span> per level</li>
            <li style="margin:15px 0;font-size:.65rem;color:#ccc;"><span style="color:var(--pacman-yellow);">►</span> You have <span style="color:var(--pacman-yellow);">3 LIVES</span> — lose one if time runs out</li>
            <li style="margin:15px 0;font-size:.65rem;color:#ccc;"><span style="color:var(--pacman-yellow);">►</span> Hints available, but some cost time!</li>
            <li style="margin:15px 0;font-size:.65rem;color:#ccc;"><span style="color:var(--pacman-yellow);">►</span> Collect words and arrange them to form the secret phrase</li>
            <li style="margin:15px 0;font-size:.65rem;color:#ccc;"><span style="color:var(--pacman-yellow);">►</span> Leaderboard updates LIVE after every level!</li>
            <li style="margin:15px 0;font-size:.65rem;color:#ccc;"><span style="color:var(--pacman-yellow);">►</span> Think like a developer 🧑‍💻</li>
        </ul>
    </div>

    {% if in_progress %}
    <div style="display:flex;gap:20px;flex-wrap:wrap;justify-content:center;">
        <button class="start-btn blink" id="startGame">NEW GAME</button>
        <button class="start-btn" id="resumeGame" style="color:var(--ghost-cyan);border-color:var(--ghost-cyan);">
            ▶ RESUME LEVEL {{ current_level }}
        </button>
    </div>
    {% else %}
    <button class="start-btn blink" id="startGame">INSERT COIN TO START</button>
    {% endif %}

    <p style="margin-top:20px;">
        <a href="{{ url_for('leaderboard') }}" style="color:var(--ghost-orange);font-size:.6rem;text-decoration:none;">🏆 LIVE LEADERBOARD</a>
    </p>

    <p style="margin-top:20px;font-size:.5rem;color:#666;">Made with 💛 by GDG ACEIT</p>
</div>
{% endblock %}

{% block scripts %}
<script>
document.getElementById('startGame')?.addEventListener('click', async () => {
    const res = await fetch('/api/start', { method: 'POST',
        headers: {'Content-Type':'application/json'}, body: '{}' });
    const data = await res.json();
    if (data.ok) window.location.href = data.redirect;
});

document.getElementById('resumeGame')?.addEventListener('click', async () => {
    const res = await fetch('/api/resume', { method: 'POST',
        headers: {'Content-Type':'application/json'}, body: '{}' });
    const data = await res.json();
    if (data.ok) window.location.href = data.redirect;
});

document.getElementById('logoutLink')?.addEventListener('click', async (e) => {
    e.preventDefault();
    const res = await fetch('/api/logout', { method: 'POST',
        headers: {'Content-Type':'application/json'}, body: '{}' });
    const data = await res.json();
    window.location.href = data.redirect;
});
</script>
{% endblock %}
```

## `templates\leaderboard.html`

```html
<!-- templates/leaderboard.html -->
{% extends "base.html" %}
{% block title %}Leaderboard | PAC-HUNT{% endblock %}

{% block body %}
<div class="landing-container" style="padding-top:60px;">
    <h1 class="game-title" style="font-size:2rem;">🏆 LIVE LEADERBOARD</h1>
    <p class="subtitle" style="font-size:.7rem;">TOP HUNTERS — UPDATES IN REAL TIME</p>

    <div style="margin:10px 0;">
        {% if db_ok %}
        <span style="font-size:.5rem;padding:5px 12px;background:rgba(0,255,0,.1);border:1px solid #00ff00;color:#00ff00;border-radius:20px;">
            ● LIVE
        </span>
        {% else %}
        <span style="font-size:.5rem;padding:5px 12px;background:rgba(255,0,0,.1);border:1px solid var(--ghost-red);color:var(--ghost-red);border-radius:20px;">
            ● OFFLINE
        </span>
        {% endif %}
        <span id="lastUpdate" style="font-size:.45rem;color:#444;margin-left:10px;"></span>
    </div>

    <div id="leaderboardTable">
    {% if board %}
    <div class="maze-border" style="max-width:800px;width:100%;margin:25px auto;padding:25px;overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-size:.55rem;text-align:center;">
            <thead>
                <tr style="color:var(--ghost-cyan);border-bottom:2px solid var(--maze-blue);">
                    <th style="padding:10px;">#</th>
                    <th style="padding:10px;">PLAYER</th>
                    <th style="padding:10px;">SCORE</th>
                    <th style="padding:10px;">TIME</th>
                    <th style="padding:10px;">LIVES</th>
                    <th style="padding:10px;">HINTS</th>
                    <th style="padding:10px;">DATE</th>
                    <th style="padding:10px;">CARD</th>
                </tr>
            </thead>
            <tbody>
            {% for entry in board %}
                <tr style="border-bottom:1px solid #1a1a1a;color:
                    {%- if loop.index == 1 %}var(--pacman-yellow)
                    {%- elif loop.index == 2 %}#ccc
                    {%- elif loop.index == 3 %}var(--ghost-orange)
                    {%- else %}#666{% endif %};">
                    <td style="padding:12px;">
                        {% if loop.index == 1 %}🥇
                        {% elif loop.index == 2 %}🥈
                        {% elif loop.index == 3 %}🥉
                        {% else %}{{ loop.index }}{% endif %}
                    </td>
                    <td style="padding:12px;">{{ entry.name }}</td>
                    <td style="padding:12px;font-weight:bold;">{{ entry.score }}</td>
                    <td style="padding:12px;">{{ entry.display_time }}</td>
                    <td style="padding:12px;">{{ entry.lives_remaining }} ❤️</td>
                    <td style="padding:12px;">{{ entry.hints_used | default(0) }}</td>
                    <td style="padding:12px;font-size:.45rem;color:#444;">{{ entry.completed_at }}</td>
                    <td style="padding:12px;">
                        {% if entry.session_id %}
                        <a href="{{ url_for('scorecard', session_id=entry.session_id) }}"
                           style="color:var(--ghost-cyan);font-size:.5rem;text-decoration:none;">VIEW</a>
                        {% else %}—{% endif %}
                    </td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <div class="maze-border" style="max-width:500px;margin:40px auto;padding:40px;text-align:center;">
        <p style="color:#666;font-size:.7rem;line-height:2;">
            No scores yet!<br>Be the first to complete the hunt.
        </p>
    </div>
    {% endif %}
    </div>

    <div style="display:flex;gap:20px;margin-top:25px;flex-wrap:wrap;justify-content:center;">
        <a href="{{ url_for('index') }}" class="btn btn-primary">← BACK TO GAME</a>
        <button onclick="refreshLeaderboard()" class="btn btn-secondary" id="refreshBtn">🔄 REFRESH NOW</button>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
let autoRefreshInterval = null;

function refreshLeaderboard() {
    fetch('/api/leaderboard?limit=50')
        .then(r => r.json())
        .then(data => {
            if (!data.ok) return;
            document.getElementById('lastUpdate').textContent =
                'Updated: ' + new Date().toLocaleTimeString();

            const board = data.leaderboard;
            if (board.length === 0) return;

            let html = `<div class="maze-border" style="max-width:800px;width:100%;margin:25px auto;padding:25px;overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:.55rem;text-align:center;">
                <thead><tr style="color:var(--ghost-cyan);border-bottom:2px solid var(--maze-blue);">
                    <th style="padding:10px;">#</th>
                    <th style="padding:10px;">PLAYER</th>
                    <th style="padding:10px;">SCORE</th>
                    <th style="padding:10px;">TIME</th>
                    <th style="padding:10px;">LIVES</th>
                    <th style="padding:10px;">HINTS</th>
                    <th style="padding:10px;">DATE</th>
                    <th style="padding:10px;">CARD</th>
                </tr></thead><tbody>`;

            board.forEach((entry, i) => {
                const rank = i + 1;
                const color = rank === 1 ? 'var(--pacman-yellow)' :
                              rank === 2 ? '#ccc' :
                              rank === 3 ? 'var(--ghost-orange)' : '#666';
                const medal = rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : rank;
                const cardLink = entry.session_id
                    ? `<a href="/scorecard/${entry.session_id}" style="color:var(--ghost-cyan);font-size:.5rem;text-decoration:none;">VIEW</a>`
                    : '—';

                html += `<tr style="border-bottom:1px solid #1a1a1a;color:${color};">
                    <td style="padding:12px;">${medal}</td>
                    <td style="padding:12px;">${entry.name}</td>
                    <td style="padding:12px;font-weight:bold;">${entry.score}</td>
                    <td style="padding:12px;">${entry.display_time}</td>
                    <td style="padding:12px;">${entry.lives_remaining} ❤️</td>
                    <td style="padding:12px;">${entry.hints_used || 0}</td>
                    <td style="padding:12px;font-size:.45rem;color:#444;">${entry.completed_at}</td>
                    <td style="padding:12px;">${cardLink}</td>
                </tr>`;
            });

            html += '</tbody></table></div>';
            document.getElementById('leaderboardTable').innerHTML = html;
        })
        .catch(err => console.error('Leaderboard refresh failed:', err));
}

// Auto-refresh every 10 seconds
autoRefreshInterval = setInterval(refreshLeaderboard, 10000);
document.getElementById('lastUpdate').textContent = 'Auto-refreshes every 10s';
</script>
{% endblock %}
```

## `templates\level.html`

```html
<!-- templates/level.html -->
{% extends "base.html" %}
{% block title %}Level {{ level_num }} | PAC-HUNT{% endblock %}

{% block head %}
<style>
.hint-text-dynamic {
    background: rgba(255, 184, 255, 0.1);
    border: 2px dashed var(--ghost-pink);
    padding: 20px;
    margin: 15px 0;
    font-size: 0.7rem;
    color: var(--ghost-pink);
    animation: fadeIn 0.5s ease;
}
</style>
{% endblock %}

{% block body %}
<!-- HUD -->
<div class="game-hud">
    <div class="hud-section">
        <span class="hud-label">LIVES</span>
        <div class="lives" id="lives"></div>
    </div>
    <div class="hud-section">
        <span class="hud-label">TIME</span>
        <span class="timer" id="timer">05:00</span>
    </div>
    <div class="hud-section">
        <span class="hud-label">LEVEL</span>
        <div class="level-indicator" id="levelIndicator"></div>
    </div>
    <div class="hud-section">
        <span class="hud-label" style="font-size:.5rem;">{{ username }}</span>
    </div>
</div>

<!-- Level Content -->
<div class="level-container maze-border">
    <div class="level-header">
        <p class="level-number">LEVEL {{ level_num }} OF {{ total_levels }}</p>
        <h2 class="level-title">{{ content.title }}</h2>
    </div>

    <!-- Collected Words -->
    <div class="collected-display">
        <span class="collected-label">COLLECTED FRAGMENTS:</span>
        <div class="collected-words-shuffled" id="collectedDisplay"></div>
    </div>

    <!-- Story -->
    <div class="story-box" style="text-align:center;margin-bottom:30px;">
        <p style="font-size:.7rem;color:#888;line-height:2;">{{ content.story }}</p>
    </div>

    <!-- Riddle -->
    <div class="riddle-box maze-border">
        <p class="riddle-text">
            {% for part in content.riddle %}
                {% if part[0] == 'text' %}{{ part[1] }}
                {% elif part[0] == 'emphasis' %}<span class="riddle-emphasis">{{ part[1] }}</span>
                {% elif part[0] == 'highlight' %}<span style="color:var(--pacman-yellow);">{{ part[1] }}</span>
                {% elif part[0] == 'br' %}<br>
                {% endif %}
            {% endfor %}
        </p>
    </div>

    <!-- Tutorial (if present) -->
    {% if content.tutorial %}
    <div class="tutorial-box">
        <h4 class="tutorial-title">{{ content.tutorial.title }}</h4>
        <ul class="tutorial-steps">
            {% for step in content.tutorial.steps %}
            <li>{{ step | safe }}</li>
            {% endfor %}
        </ul>
    </div>
    {% endif %}

    <!-- Action button (level 1 & 3) -->
    {% if content.get('has_action_link') %}
    <div class="action-buttons">
        <a href="{{ content.action_url }}"
           {% if content.get('action_external') %}target="_blank" rel="noopener noreferrer"{% endif %}
           class="btn btn-primary">{{ content.action_text }}</a>
    </div>
    {% endif %}

    <!-- Broken image (level 2) — secret is in alt attribute -->
    {% if content.get('has_broken_image') %}
    <div class="puzzle-image-container">
        <p style="font-size:.7rem;color:var(--ghost-cyan);margin-bottom:15px;">Here's an important image… or is it?</p>
        <img src="/static/images/secret_word:that.png"
             
             id="secretImage"
             style="width:300px;height:200px;border:3px dashed #333;background:#111;display:block;margin:0 auto;">
        <p style="font-size:.6rem;color:#444;margin-top:15px;">Hmm, the image won't load… How strange 🤔</p>
    </div>
    {% endif %}

    <!-- Secret button (level 4) -->
    {% if content.get('has_secret_button') %}
    <div class="action-buttons">
        <button id="secretButton" class="btn btn-primary" style="font-size:.9rem;padding:25px 50px;">
            🎯 CLICK ME
        </button>
    </div>
    <p style="text-align:center;font-size:.6rem;color:#666;margin:20px 0;">
        you must hear the voice of that talks through your network
    </p>
    {% endif %}

    <!-- Hints — dynamically loaded from server -->
    <div class="hint-container">
        <button class="btn btn-hint hint-btn" data-hint="1">💡 HINT 1 (FREE)</button>
        <button class="btn btn-hint hint-btn" data-hint="2">💡 HINT 2 (-30 SEC)</button>
        <button class="btn btn-hint hint-btn" data-hint="3">💡 HINT 3 (-60 SEC)</button>
        <div id="hintContent"></div>
    </div>

    <!-- Answer Section -->
    <div class="answer-section">
        <label class="answer-label">{{ content.answer_label }}</label>
        <div class="answer-input-group">
            <input type="text" id="answerInput" class="answer-input"
                   placeholder="?????" maxlength="30" autocomplete="off">
            <button id="submitAnswer" class="submit-btn">SUBMIT</button>
        </div>
    </div>
</div>

<!-- Modal -->
<div class="modal-overlay" id="modalOverlay">
    <div class="modal maze-border">
        <h3 class="modal-title" id="modalTitle"></h3>
        <p class="modal-text" id="modalText"></p>
        <button class="btn btn-primary" id="modalBtn">CONTINUE</button>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
const INIT_STATE = {
    lives:          {{ lives }},
    time_remaining: {{ time_remaining }},
    current_level:  {{ level_num }},
    total_levels:   {{ total_levels }},
    collected_words: {{ collected_words | tojson }},
};
window.PH_LEVEL = {{ level_num }};
initHUD(INIT_STATE);
startClientTimer(INIT_STATE.time_remaining);

{% if content.get('has_secret_button') %}
document.getElementById('secretButton').addEventListener('click', function () {
    fetch('/api/secret-ping', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: '{}'
    }).then(r => {
        console.log('%c🎮 PAC-HUNT 🎮', 'font-size:16px;color:#FFFF00;font-weight:bold;');
        console.log('%cCheck the RESPONSE HEADERS of the "secret-ping" request in the Network tab!', 'color:#00FFFF;font-size:12px;');
        return r.json();
    }).then(data => {
        console.log('%cServer says: ' + data.message, 'color:#FFB8FF;font-size:11px;');
    });

    this.textContent = '✓ Request Sent! Check Network Tab → Response Headers';
    this.style.background = '#00FFFF';
    this.style.color = '#000';
});
{% endif %}
</script>
{% endblock %}
```

## `templates\level1.html`

```html
{% extends "level_base.html" %}
{% block title %}Level 1 | PAC-HUNT{% endblock %}
{% block level_title %}THE WHISPERING VOID{% endblock %}

{% block level_body %}
<div class="story-box" style="text-align:center;margin-bottom:30px;">
    <p style="font-size:.7rem;color:#888;line-height:2;">
        The first fragment of the secret phrase is hidden in a place 
        where only those who know where to look can find it...
    </p>
</div>

<div class="riddle-box maze-border">
    <p class="riddle-text">
        "I am the <span class="riddle-emphasis">voice</span> that speaks to developers,<br>
        Hidden in plain sight, yet <span class="riddle-emphasis">invisible</span> to most.<br>
        When errors cry out, I catch their tears.<br>
        When secrets need telling, I whisper them here.<br><br>
        <span style="color:var(--pacman-yellow);">Find the page that doesn't exist,</span><br>
        <span style="color:var(--pacman-yellow);">And listen to what it has to say.</span>"
    </p>
</div>

<div class="action-buttons">
    <a href="{{ url_for('oops') }}" class="btn btn-primary">🚪 ENTER THE VOID</a>
</div>

<div class="hint-container">
    <button class="btn btn-hint hint-btn" data-hint="1">💡 HINT 1 (FREE)</button>
    <button class="btn btn-hint hint-btn" data-hint="2">💡 HINT 2 (-30 SEC)</button>
    <button class="btn btn-hint hint-btn" data-hint="3">💡 HINT 3 (-60 SEC)</button>

    <div class="hint-text" id="hint1">
        The page you're looking for shows an error… a very specific error code that web developers know well.
    </div>
    <div class="hint-text" id="hint2">
        Once you're on the error page, open the Developer Console.
        In Chrome: Right-click → Inspect → Console tab
    </div>
    <div class="hint-text" id="hint3">
        The word you're looking for is printed in the Console.
        It's yellow text that says "The secret word is: ____"
    </div>
</div>
{% endblock %}
```

## `templates\level2.html`

```html
{% extends "level_base.html" %}
{% block title %}Level 2 | PAC-HUNT{% endblock %}
{% block level_title %}THE BROKEN FRAME{% endblock %}
{% block answer_label %}WHAT WORD IS HIDDEN IN THE IMAGE?{% endblock %}

{% block level_body %}
<div class="story-box" style="text-align:center;margin-bottom:30px;">
    <p style="font-size:.7rem;color:#888;line-height:2;">
        Not everything on the web is as it appears...<br>
        Sometimes what seems broken holds hidden meaning.
    </p>
</div>

<div class="riddle-box maze-border">
    <p class="riddle-text">
        "A picture speaks a thousand words,<br>
        But what of one that <span class="riddle-emphasis">refuses to appear</span>?<br><br>
        The eyes see nothing but emptiness,<br>
        Yet beneath the <span class="riddle-emphasis">surface</span>, truth remains.<br><br>
        <span style="color:var(--pacman-yellow);">Look not at what is shown,</span><br>
        <span style="color:var(--pacman-yellow);">But at how it's written.</span>"
    </p>
</div>

<div class="puzzle-image-container">
    <p style="font-size:.7rem;color:var(--ghost-cyan);margin-bottom:15px;">Here's an important image… or is it?</p>
    <!-- THE SECRET IS IN THE SRC ATTRIBUTE -->
    <img src="GIVE.png" alt="If you can read this, you're on the right track!"
         id="secretImage"
         style="width:300px;height:200px;border:3px dashed #333;background:#111;display:block;margin:0 auto;">
    <p style="font-size:.6rem;color:#444;margin-top:15px;">Hmm, the image won't load… How strange 🤔</p>
</div>

<div class="hint-container">
    <button class="btn btn-hint hint-btn" data-hint="1">💡 HINT 1 (FREE)</button>
    <button class="btn btn-hint hint-btn" data-hint="2">💡 HINT 2 (-30 SEC)</button>
    <button class="btn btn-hint hint-btn" data-hint="3">💡 HINT 3 (-60 SEC)</button>

    <div class="hint-text" id="hint1">
        The image above doesn't load… but the browser still knows where it's TRYING to load from. Inspect the image element!
    </div>
    <div class="hint-text" id="hint2">
        Right-click on the broken image → Inspect. Look at the HTML code. Find the "src" attribute — it contains the filename.
    </div>
    <div class="hint-text" id="hint3">
        The src attribute shows: src="GIVE.png" — The word is the filename without the extension!
    </div>
</div>
{% endblock %}
```

## `templates\level3.html`

```html
{% extends "level_base.html" %}
{% block title %}Level 3 | PAC-HUNT{% endblock %}
{% block level_title %}THE ARCHIVES OF TIME{% endblock %}
{% block answer_label %}ENTER THE WORD FROM THE PAST:{% endblock %}

{% block level_body %}
<div class="story-box" style="text-align:center;margin-bottom:30px;">
    <p style="font-size:.7rem;color:#888;line-height:2;">
        The next fragment is hidden in the past…<br>
        Where every change is remembered, but not always seen.
    </p>
</div>

<div class="riddle-box maze-border">
    <p class="riddle-text">
        "In the realm where code is <span class="riddle-emphasis">born</span> and <span class="riddle-emphasis">reborn</span>,<br>
        A cat with eight legs guards the kingdom.<br><br>
        The present shows one truth,<br>
        But the <span class="riddle-emphasis">past holds another</span>.<br><br>
        <span style="color:var(--pacman-yellow);">Dig through the history of changes,</span><br>
        <span style="color:var(--pacman-yellow);">And you shall find what was once there.</span>"
    </p>
</div>

<div class="tutorial-box">
    <h4 class="tutorial-title">About Git &amp; GitHub</h4>
    <ul class="tutorial-steps">
        <li>GitHub is where developers store and share code</li>
        <li>Every change made to code is saved as a "commit"</li>
        <li>You can view the history of all commits on any repository</li>
        <li>Sometimes, secrets are hidden in <strong>older commits</strong> that have since been changed</li>
        <li>Look for the "commits" or "history" section on GitHub!</li>
    </ul>
</div>

<div class="action-buttons">
    <a href="https://github.com/pushkar-hue/Tale-of-Time/tree/main"
       target="_blank" class="btn btn-primary">🐙 VISIT THE REPOSITORY</a>
</div>

<div class="hint-container">
    <button class="btn btn-hint hint-btn" data-hint="1">💡 HINT 1 (FREE)</button>
    <button class="btn btn-hint hint-btn" data-hint="2">💡 HINT 2 (-30 SEC)</button>
    <button class="btn btn-hint hint-btn" data-hint="3">💡 HINT 3 (-60 SEC)</button>

    <div class="hint-text" id="hint1">The octopus cat is GitHub! Look for a link to a GitHub repository.</div>
    <div class="hint-text" id="hint2">On GitHub, find the "commits" section (look for a clock icon or text saying "X commits"). Click it to see the history.</div>
    <div class="hint-text" id="hint3">Click on an older commit to see what the README file looked like before. The secret word was removed but is visible in the history!</div>
</div>
{% endblock %}
```

## `templates\level4.html`

```html
{% extends "level_base.html" %}
{% block title %}Level 4 | PAC-HUNT{% endblock %}
{% block level_title %}THE NETWORK WHISPERS{% endblock %}
{% block answer_label %}WHAT'S THE FINAL WORD(S)?{% endblock %}

{% block level_body %}
<div class="story-box" style="text-align:center;margin-bottom:30px;">
    <p style="font-size:.7rem;color:#888;line-height:2;">
        The final piece is hidden in the invisible conversations<br>
        that happen every time you click a button…
    </p>
</div>

<div class="riddle-box maze-border">
    <p class="riddle-text">
        "When you click, a message flies,<br>
        <span class="riddle-emphasis">Invisible</span> to untrained eyes.<br><br>
        The Network knows what browsers say,<br>
        In <span class="riddle-emphasis">headers</span> hidden, secrets lay.<br><br>
        <span style="color:var(--pacman-yellow);">Click the button below,</span><br>
        <span style="color:var(--pacman-yellow);">Then watch what travels in the glow.</span>"
    </p>
</div>

<div class="tutorial-box">
    <h4 class="tutorial-title">About Network Requests</h4>
    <ul class="tutorial-steps">
        <li>When websites communicate with servers, they send "requests"</li>
        <li>Open DevTools (<span class="key-hint">F12</span>) and go to the <strong>Network</strong> tab</li>
        <li>Click the button below WHILE the Network tab is open</li>
        <li>You'll see a new request appear — click on it!</li>
        <li>Look at the <strong>Request Headers</strong> or <strong>Response Headers</strong></li>
        <li>Headers contain metadata — including sometimes… secrets!</li>
    </ul>
</div>

<div class="action-buttons">
    <button id="secretButton" class="btn btn-primary" style="font-size:.9rem;padding:25px 50px;">
        🎯 CLICK ME (with Network tab open!)
    </button>
</div>
<p style="text-align:center;font-size:.6rem;color:#666;margin:20px 0;">
    Make sure Developer Tools → Network tab is open before clicking!
</p>

<div class="hint-container">
    <button class="btn btn-hint hint-btn" data-hint="1">💡 HINT 1 (FREE)</button>
    <button class="btn btn-hint hint-btn" data-hint="2">💡 HINT 2 (-30 SEC)</button>
    <button class="btn btn-hint hint-btn" data-hint="3">💡 HINT 3 (-60 SEC)</button>

    <div class="hint-text" id="hint1">Open DevTools (F12), then click on the "Network" tab. Now click the button and watch for a new request to appear.</div>
    <div class="hint-text" id="hint2">After clicking, you'll see a request appear. Click on it and look at the Response or Console for clues.</div>
    <div class="hint-text" id="hint3">Look in the Console — the secret words are: YOU UP</div>
</div>
{% endblock %}

{% block level_scripts %}
<script>
document.getElementById('secretButton').addEventListener('click', function () {
    fetch('/api/state')   // this call will appear in the Network tab
        .then(r => r.json())
        .then(() => {
            console.log('%c🎮 PAC-HUNT SECRET 🎮', 'font-size:20px;color:#FFFF00;font-weight:bold;');
            console.log('%c📡 The secret words are: YOU UP', 'color:#FFFF00;font-size:14px;background:#000;padding:5px;');
        });

    this.textContent = '✓ Request Sent! Check Network Tab';
    this.style.background = '#00FFFF';
    this.style.color = '#000';
});
</script>
{% endblock %}
```

## `templates\level_base.html`

```html
{% extends "base.html" %}
{% block head %}
<style>
/* Server-driven timer colour helpers applied by JS */
</style>
{% endblock %}

{% block body %}
<!-- HUD -->
<div class="game-hud">
    <div class="hud-section">
        <span class="hud-label">LIVES</span>
        <div class="lives" id="lives"></div>
    </div>
    <div class="hud-section">
        <span class="hud-label">TIME</span>
        <span class="timer" id="timer">05:00</span>
    </div>
    <div class="hud-section">
        <span class="hud-label">LEVEL</span>
        <div class="level-indicator" id="levelIndicator"></div>
    </div>
</div>

<!-- Level Content -->
<div class="level-container maze-border">
    <div class="level-header">
        <p class="level-number">LEVEL {{ level_num }} OF {{ total_levels }}</p>
        <h2 class="level-title">{% block level_title %}{% endblock %}</h2>
    </div>

    <!-- Collected Words -->
    <div class="collected-display">
        <span class="collected-label">COLLECTED FRAGMENTS:</span>
        <div class="collected-words-shuffled" id="collectedDisplay"></div>
    </div>

    {% block level_body %}{% endblock %}

    <!-- Answer Section -->
    <div class="answer-section">
        <label class="answer-label">{% block answer_label %}ENTER THE WORD YOU FOUND:{% endblock %}</label>
        <div class="answer-input-group">
            <input type="text" id="answerInput" class="answer-input"
                   placeholder="?????" maxlength="10" autocomplete="off">
            <button id="submitAnswer" class="submit-btn">SUBMIT</button>
        </div>
    </div>
</div>

<!-- Modal -->
<div class="modal-overlay" id="modalOverlay">
    <div class="modal maze-border">
        <h3 class="modal-title" id="modalTitle"></h3>
        <p class="modal-text" id="modalText"></p>
        <button class="btn btn-primary" id="modalBtn">CONTINUE</button>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
// Bootstrap HUD from server-rendered values
const INIT_STATE = {
    lives:          {{ lives }},
    time_remaining: {{ time_remaining }},
    current_level:  {{ level_num }},
    total_levels:   {{ total_levels }},
    collected_words: {{ collected_words | tojson }},
};
window.PH_LEVEL = {{ level_num }};
initHUD(INIT_STATE);
startClientTimer(INIT_STATE.time_remaining);
</script>
{% block level_scripts %}{% endblock %}
{% endblock %}
```

## `templates\oops.html`

```html
<!-- templates/oops.html -->
{% extends "base.html" %}
{% block title %}404 - Page Not Found | PAC-HUNT{% endblock %}

{% block body %}
<!-- HUD -->
<div class="game-hud">
    <div class="hud-section">
        <span class="hud-label">LIVES</span>
        <div class="lives" id="lives"></div>
    </div>
    <div class="hud-section">
        <span class="hud-label">TIME</span>
        <span class="timer" id="timer">05:00</span>
    </div>
    <div class="hud-section">
        <span class="hud-label">LEVEL</span>
        <div class="level-indicator" id="levelIndicator"></div>
    </div>
</div>

<div class="error-container" style="margin-top:80px;">
    <div class="error-code">404</div>
    <p class="error-message">OOPS! THIS PAGE GOT EATEN BY PAC-MAN!</p>
    <div class="error-ghost">👻</div>
    <p style="font-size:.7rem;color:#666;margin:20px 0;line-height:2;">
        The page you're looking for seems to have vanished<br>into the digital void…
    </p>
    <p style="font-size:.6rem;color:#444;margin:20px 0;">
        <em>Or did it? Maybe there's more here than meets the eye… 👀</em>
    </p>
    <p style="font-size:.55rem;color:#222;margin:10px 0;">
        Some secrets hide in plain sight...
    </p>

    <!-- The secret is hidden here with CSS — same color as background, only visible on text select -->
    <p class="hidden-secret" style="font-size:1rem;color:#000;margin:30px 0;padding:20px;user-select:text;
       -webkit-user-select:text;-moz-user-select:text;">
        The secret word is: I 
    </p>

    <a href="{{ url_for('level', level_num=1) }}" class="btn btn-secondary back-btn">← BACK TO LEVEL 1</a>
</div>
{% endblock %}

{% block scripts %}
<style>
/* Text is invisible normally but visible when selected */
.hidden-secret {
    color: #000000 !important;
    background: #000000;
}
.hidden-secret::selection {
    background: var(--pacman-yellow);
    color: #000;
}
.hidden-secret::-moz-selection {
    background: var(--pacman-yellow);
    color: #000;
}
</style>
<script>
const INIT_STATE = {
    lives:          {{ lives }},
    time_remaining: {{ time_remaining }},
    current_level:  {{ current_level }},
    total_levels:   {{ total_levels }},
    collected_words: {{ collected_words | tojson }},
};
initHUD(INIT_STATE);
startClientTimer(INIT_STATE.time_remaining);
</script>
{% endblock %}
```

## `templates\register.html`

```html
<!-- templates/register.html -->
{% extends "base.html" %}
{% block title %}Register | PAC-HUNT{% endblock %}

{% block body %}
<div class="landing-container">
    <h1 class="game-title" style="font-size:2.5rem;">PAC-HUNT</h1>
    <p class="subtitle">PLAYER REGISTRATION</p>

    <div class="pacman-container">
        <div class="pacman"></div>
        <div class="dots">
            <div class="dot"></div><div class="dot"></div>
            <div class="dot"></div><div class="dot"></div>
        </div>
    </div>

    <div class="maze-border" style="max-width:500px;width:100%;margin:30px auto;padding:35px;">
        <h3 style="color:var(--ghost-cyan);font-size:.8rem;margin-bottom:25px;">🎮 IDENTIFY YOURSELF, HUNTER</h3>

        <div style="margin-bottom:20px;">
            <label style="display:block;font-size:.55rem;color:var(--ghost-cyan);margin-bottom:8px;text-align:left;">
                USERNAME
            </label>
            <input type="text" id="regUsername"
                   class="answer-input" style="width:100%;text-align:left;font-size:.7rem;"
                   placeholder="Enter unique username" maxlength="20" autocomplete="off">
        </div>

        <div style="margin-bottom:25px;">
            <label style="display:block;font-size:.55rem;color:var(--ghost-cyan);margin-bottom:8px;text-align:left;">
                EMAIL
            </label>
            <input type="email" id="regEmail"
                   class="answer-input" style="width:100%;text-align:left;font-size:.7rem;text-transform:none;"
                   placeholder="Enter your email" maxlength="50" autocomplete="off">
        </div>

        <div id="regError" style="display:none;color:var(--ghost-red);font-size:.55rem;margin-bottom:15px;padding:10px;background:rgba(255,0,0,.1);border:1px solid var(--ghost-red);border-radius:4px;"></div>
        <div id="regSuccess" style="display:none;color:#00ff00;font-size:.55rem;margin-bottom:15px;padding:10px;background:rgba(0,255,0,.1);border:1px solid #00ff00;border-radius:4px;"></div>

        <button id="registerBtn" class="submit-btn" style="width:100%;font-size:.8rem;padding:18px;">
            REGISTER & PLAY 🎮
        </button>
    </div>

    <p style="font-size:.5rem;color:#444;margin-top:10px;">
        Already registered? Use the same username & email to continue.
    </p>

    <p style="margin-top:20px;">
        <a href="{{ url_for('leaderboard') }}" style="color:var(--ghost-orange);font-size:.6rem;text-decoration:none;">🏆 VIEW LEADERBOARD</a>
    </p>

    <p style="margin-top:20px;font-size:.5rem;color:#666;">Made with 💛 by GDG ACEIT</p>
</div>
{% endblock %}

{% block scripts %}
<script>
document.getElementById('registerBtn').addEventListener('click', async () => {
    const username = document.getElementById('regUsername').value.trim();
    const email = document.getElementById('regEmail').value.trim();
    const errEl = document.getElementById('regError');
    const sucEl = document.getElementById('regSuccess');
    errEl.style.display = 'none';
    sucEl.style.display = 'none';

    if (!username || !email) {
        errEl.textContent = 'Please fill in both fields!';
        errEl.style.display = 'block';
        return;
    }

    const res = await fetch('/api/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ username, email })
    });
    const data = await res.json();

    if (data.ok) {
        sucEl.textContent = data.returning
            ? `Welcome back, ${data.username}! Redirecting...`
            : `Registered as ${data.username}! Redirecting...`;
        sucEl.style.display = 'block';
        setTimeout(() => { window.location.href = data.redirect; }, 1000);
    } else {
        errEl.textContent = data.error || 'Registration failed';
        errEl.style.display = 'block';
    }
});

['regUsername', 'regEmail'].forEach(id => {
    document.getElementById(id).addEventListener('keypress', e => {
        if (e.key === 'Enter') document.getElementById('registerBtn').click();
    });
});
</script>
{% endblock %}
```

## `templates\scorecard.html`

```html
<!-- templates/scorecard.html -->
{% extends "base.html" %}
{% block title %}Scorecard | PAC-HUNT{% endblock %}

{% block body %}
<div class="landing-container" style="padding-top:60px;">
    <h1 class="game-title" style="font-size:1.8rem;">📋 SCORECARD</h1>
    <p class="subtitle" style="font-size:.65rem;color:var(--ghost-cyan);">{{ card.player_name }}</p>

    <div class="maze-border" style="max-width:640px;width:100%;margin:30px auto;padding:35px;">

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:30px;">
            <div style="text-align:center;padding:20px;background:rgba(255,255,0,.05);border:2px solid var(--pacman-yellow);border-radius:6px;">
                <div style="font-size:2rem;color:var(--pacman-yellow);">{{ card.score }}</div>
                <div style="font-size:.5rem;color:#888;margin-top:8px;">TOTAL SCORE</div>
            </div>
            <div style="text-align:center;padding:20px;background:rgba(0,255,255,.05);border:2px solid var(--ghost-cyan);border-radius:6px;">
                <div style="font-size:2rem;color:var(--ghost-cyan);">{{ card.display_time }}</div>
                <div style="font-size:.5rem;color:#888;margin-top:8px;">TOTAL TIME</div>
            </div>
            <div style="text-align:center;padding:20px;background:rgba(255,0,0,.05);border:2px solid var(--ghost-red);border-radius:6px;">
                <div style="font-size:2rem;color:var(--ghost-red);">{{ card.lives_remaining }} / 3</div>
                <div style="font-size:.5rem;color:#888;margin-top:8px;">LIVES LEFT</div>
            </div>
            <div style="text-align:center;padding:20px;background:rgba(255,184,255,.05);border:2px solid var(--ghost-pink);border-radius:6px;">
                <div style="font-size:2rem;color:var(--ghost-pink);">{{ card.hints_used }}</div>
                <div style="font-size:.5rem;color:#888;margin-top:8px;">HINTS USED</div>
            </div>
        </div>

        {% if card.level_stats %}
        <h3 style="color:var(--ghost-cyan);font-size:.7rem;margin-bottom:15px;text-align:center;">LEVEL BREAKDOWN</h3>
        <table style="width:100%;border-collapse:collapse;font-size:.55rem;text-align:center;">
            <thead>
                <tr style="color:var(--ghost-cyan);border-bottom:2px solid var(--maze-blue);">
                    <th style="padding:10px;">LEVEL</th>
                    <th style="padding:10px;">TIME</th>
                    <th style="padding:10px;">HINTS</th>
                    <th style="padding:10px;">PENALTY</th>
                </tr>
            </thead>
            <tbody>
            {% for ls in card.level_stats %}
                <tr style="border-bottom:1px solid #222;color:#ccc;">
                    <td style="padding:10px;color:var(--pacman-yellow);">{{ ls.level }}</td>
                    <td style="padding:10px;">
                        {% set m = ls.time_taken // 60 %}
                        {% set s = ls.time_taken % 60 %}
                        {{ '%d:%02d'|format(m, s) }}
                    </td>
                    <td style="padding:10px;">{{ ls.hints_used }}</td>
                    <td style="padding:10px;color:{% if ls.time_penalty > 0 %}var(--ghost-red){% else %}#888{% endif %};">
                        -{{ ls.time_penalty }}s
                    </td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
        {% endif %}

        <div style="margin-top:25px;text-align:center;">
            <p style="font-size:.55rem;color:#666;margin-bottom:12px;">WORDS COLLECTED</p>
            <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
                {% for word in card.collected_words %}
                <span style="font-size:.6rem;padding:8px 14px;border:2px solid var(--pacman-yellow);color:var(--pacman-yellow);background:rgba(255,255,0,.08);border-radius:4px;">
                    {{ word or '???' }}
                </span>
                {% endfor %}
            </div>
        </div>

        <p style="font-size:.45rem;color:#444;margin-top:25px;text-align:center;">
            Completed: {{ card.completed_at }} &nbsp;|&nbsp; v{{ card.game_version | default('2.0') }}
        </p>
    </div>

    <div style="display:flex;gap:15px;flex-wrap:wrap;justify-content:center;">
        <a href="{{ url_for('leaderboard') }}" class="btn btn-primary">🏆 LEADERBOARD</a>
        <a href="{{ url_for('index') }}" class="btn btn-secondary">← PLAY AGAIN</a>
    </div>
</div>
{% endblock %}
```

## `templates\victory.html`

```html
<!-- templates/victory.html -->
{% extends "base.html" %}
{% block title %}VICTORY! | PAC-HUNT{% endblock %}

{% block body %}
<div class="victory-container" id="finalChallenge">
    <p class="level-number">FINAL CHALLENGE</p>
    <h1 class="level-title" style="font-size:1.5rem;">COMBINE THE WORDS!</h1>
    <p style="font-size:.6rem;color:var(--ghost-cyan);margin:10px 0;">
        Player: <span style="color:var(--pacman-yellow);">{{ username }}</span>
    </p>

    <div id="shuffledWordContainer" style="margin:40px 0;display:flex;gap:10px;justify-content:center;flex-wrap:wrap;"></div>

    <p style="font-size:.7rem;color:var(--ghost-cyan);margin:20px 0;line-height:2;">
        Arrange the words above into a famous phrase and enter it below!
    </p>

    <input type="text" id="finalAnswer" class="final-input"
           placeholder="ENTER THE COMPLETE PHRASE" autocomplete="off">

    <button id="finalSubmit" class="submit-btn" style="margin-top:20px;">CLAIM VICTORY! 🏆</button>

    <div id="finalError" style="display:none;color:var(--ghost-red);font-size:.6rem;margin-top:15px;"></div>
</div>

<div class="victory-container hidden" id="victoryScreen">
    <div class="trophy">🏆</div>
    <h1 class="victory-title">CONGRATULATIONS!</h1>
    <p style="font-size:.8rem;color:var(--ghost-cyan);margin:20px 0;">
        Well done, <span style="color:var(--pacman-yellow);">{{ username }}</span>!
        You've completed the PAC-HUNT!
    </p>
    <p style="font-size:.7rem;color:#888;margin:20px 0;">But wait… there's one more surprise…</p>
    <p style="font-size:1rem;color:var(--pacman-yellow);margin:30px 0;animation:blink 1s infinite;">🎉 YOU'VE BEEN RICK-ROLLED! 🎉</p>

    <div id="scoreDisplay" style="margin:20px 0;"></div>

    <button id="redirectBtn" class="btn btn-primary" style="margin:20px 0;padding:12px 24px;font-size:.9rem;">WATCH THE VIDEO 🎬</button>

    <div class="action-buttons">
        <a href="" id="scorecardLink" class="btn btn-secondary">📋 VIEW SCORECARD</a>
        <a href="{{ url_for('leaderboard') }}" class="btn btn-secondary">🏆 LEADERBOARD</a>
        <a href="{{ url_for('index') }}" class="btn btn-primary">PLAY AGAIN</a>
    </div>
    <p style="font-size:.5rem;color:#666;margin-top:40px;">Made with 💛 by GDG ACEIT</p>
</div>
{% endblock %}

{% block scripts %}
<script>
(function () {
    const words = {{ collected_words | tojson }};
    const container = document.getElementById('shuffledWordContainer');
    const displayWords = words.filter(w => w);
    const shuffled = [...displayWords].sort(() => Math.random() - 0.5);

    shuffled.forEach(w => {
        const el = document.createElement('div');
        el.className = 'word-slot filled';
        el.textContent = w;
        container.appendChild(el);
    });

    const RICKROLL = 'https://youtu.be/HlBYdiXdUa8?si=JiYUzXLOEotPOa0Y';

    document.getElementById('finalSubmit').addEventListener('click', async () => {
        const answer = document.getElementById('finalAnswer').value.trim();
        if (!answer) return;

        const res = await fetch('/api/final', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ answer })
        });
        const data = await res.json();
        if (data.correct) {
            document.getElementById('finalChallenge').classList.add('hidden');
            document.getElementById('victoryScreen').classList.remove('hidden');
            document.getElementById('redirectBtn').onclick = () => window.open(RICKROLL, '_blank');

            if (data.scorecard_url) {
                document.getElementById('scorecardLink').href = data.scorecard_url;
            }

            // Fetch and show score
            if (data.session_id) {
                fetch('/api/scorecard/' + data.session_id)
                    .then(r => r.json())
                    .then(sc => {
                        if (sc.ok) {
                            document.getElementById('scoreDisplay').innerHTML =
                                `<div class="maze-border" style="padding:20px;margin:15px auto;max-width:400px;">
                                    <p style="font-size:1.5rem;color:var(--pacman-yellow);">SCORE: ${sc.scorecard.score}</p>
                                    <p style="font-size:.6rem;color:var(--ghost-cyan);margin-top:10px;">
                                        Time: ${sc.scorecard.display_time} | Lives: ${sc.scorecard.lives_remaining}/3 | Hints: ${sc.scorecard.hints_used}
                                    </p>
                                </div>`;
                        }
                    })
                    .catch(err => console.error('Scorecard fetch failed:', err));
            }

            createConfetti();
            setTimeout(() => window.open(RICKROLL, '_blank'), 3000);
        } else {
            const err = document.getElementById('finalError');
            err.style.display = 'block';
            err.textContent = 'WRONG ORDER OR PHRASE! TRY AGAIN.';
            document.getElementById('finalAnswer').classList.add('shake');
            setTimeout(() => document.getElementById('finalAnswer').classList.remove('shake'), 500);
        }
    });

    document.getElementById('finalAnswer').addEventListener('keypress', e => {
        if (e.key === 'Enter') document.getElementById('finalSubmit').click();
    });

    function createConfetti() {
        const colors = ['#FFFF00','#FF0000','#00FFFF','#FFB8FF','#FFB852'];
        for (let i = 0; i < 100; i++) {
            const c = document.createElement('div');
            c.style.cssText = `position:fixed;width:10px;height:10px;
                background:${colors[Math.floor(Math.random()*colors.length)]};
                top:-10px;left:${Math.random()*100}vw;
                animation:fall ${2+Math.random()*3}s linear forwards;z-index:3000;`;
            document.body.appendChild(c);
            setTimeout(() => c.remove(), 5000);
        }
    }
})();
</script>
{% endblock %}
```

