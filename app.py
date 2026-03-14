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
  • event_state  — admin-controlled event gate
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

# Admin password — SET THIS IN YOUR .env FILE FOR PRODUCTION
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'gdg-aceit-2024')

# ══════════════════════════════════════════════
# EVENT STATE — In-memory + MongoDB backed
# ══════════════════════════════════════════════

# In-memory cache for fast polling (MongoDB is source of truth)
_event_state_cache = {
    "status": "waiting",        # waiting | active | paused | finished
    "started_at": None,
    "message": "The hunt hasn't started yet. Please wait for the host!",
    "last_updated": None,
}

def _load_event_state_from_db():
    """Load event state from MongoDB into memory cache."""
    global _event_state_cache
    db = get_db()
    if db is None:
        return _event_state_cache
    doc = db.event_state.find_one({"_id": "current"})
    if doc:
        _event_state_cache = {
            "status": doc.get("status", "waiting"),
            "started_at": doc.get("started_at"),
            "message": doc.get("message", ""),
            "last_updated": doc.get("last_updated"),
        }
    return _event_state_cache

def _save_event_state_to_db(state):
    """Persist event state to MongoDB and update cache."""
    global _event_state_cache
    _event_state_cache = state
    db = get_db()
    if db is None:
        return
    state_doc = {**state, "_id": "current", "last_updated": datetime.now(timezone.utc)}
    db.event_state.replace_one({"_id": "current"}, state_doc, upsert=True)

def get_event_status():
    """Return current event status (uses cache, refreshes from DB periodically)."""
    global _event_state_cache
    # Refresh from DB every 5 seconds to handle multi-worker setups
    now = time.time()
    last = _event_state_cache.get("_cache_time", 0)
    if now - last > 5:
        _load_event_state_from_db()
        _event_state_cache["_cache_time"] = now
    return _event_state_cache

def is_event_active():
    """Check if the event is currently active (players can play)."""
    state = get_event_status()
    return state.get("status") == "active"


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

def mongo_get_registered_players():
    """Get all registered players for admin dashboard."""
    db = get_db()
    if db is None:
        return []
    return [_serialize_doc(d) for d in
            db.players.find({}, {"_id": 0, "username": 1, "email": 1,
                                  "registered_at": 1, "games_played": 1,
                                  "games_completed": 1})
                      .sort("registered_at", DESCENDING)]

def mongo_get_player_count():
    db = get_db()
    if db is None:
        return 0
    return db.players.count_documents({})

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

def require_event_active(f):
    """Block game actions if event hasn't started."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_event_active():
            status = get_event_status()
            if request.path.startswith("/api/"):
                return jsonify({
                    "ok": False,
                    "error": "Event not active",
                    "event_status": status.get("status", "waiting"),
                    "message": status.get("message", "Please wait for the host to start the event."),
                    "redirect": url_for("waiting_room")
                }), 403
            return redirect(url_for("waiting_room"))
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    """Require admin authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            if request.path.startswith("/api/admin"):
                return jsonify({"ok": False, "error": "Admin authentication required"}), 401
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════════════
# Page Routes
# ══════════════════════════════════════════════

@app.route("/")
def index():
    if not session.get("username"):
        return redirect(url_for("register"))
    # If event not active, send to waiting room
    if not is_event_active():
        return redirect(url_for("waiting_room"))
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

@app.route("/waiting")
@require_registered
def waiting_room():
    """Waiting room — players wait here until admin starts the event."""
    if is_event_active():
        return redirect(url_for("index"))
    status = get_event_status()
    return render_template("waiting.html",
                           username=session.get("username", ""),
                           event_status=status.get("status", "waiting"),
                           event_message=status.get("message", ""))

@app.route("/level/<int:level_num>")
@require_registered
@require_event_active
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
@require_event_active
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
# Admin Routes
# ══════════════════════════════════════════════

@app.route("/admin/login", methods=["GET"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html")

@app.route("/admin")
@require_admin
def admin_dashboard():
    status = get_event_status()
    players = mongo_get_registered_players()
    player_count = len(players)
    board = mongo_get_leaderboard(limit=20)
    return render_template("admin.html",
                           event_status=status,
                           players=players,
                           player_count=player_count,
                           leaderboard=board,
                           db_ok=get_db() is not None)

# ══════════════════════════════════════════════
# Admin API Routes
# ══════════════════════════════════════════════

@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json() or {}
    password = str(data.get("password", ""))
    if password == ADMIN_PASSWORD:
        session["is_admin"] = True
        session.modified = True
        return jsonify({"ok": True, "redirect": url_for("admin_dashboard")})
    return jsonify({"ok": False, "error": "Invalid password"}), 401

@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    session.pop("is_admin", None)
    return jsonify({"ok": True, "redirect": url_for("admin_login")})

@app.route("/api/admin/event/start", methods=["POST"])
@require_admin
def api_admin_start_event():
    data = request.get_json() or {}
    message = data.get("message", "The hunt has begun! GO GO GO! 🎮")
    state = {
        "status": "active",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "last_updated": datetime.now(timezone.utc),
    }
    _save_event_state_to_db(state)
    return jsonify({"ok": True, "event_status": state})

@app.route("/api/admin/event/pause", methods=["POST"])
@require_admin
def api_admin_pause_event():
    data = request.get_json() or {}
    message = data.get("message", "The event is temporarily paused. Hold tight!")
    state = get_event_status()
    state["status"] = "paused"
    state["message"] = message
    _save_event_state_to_db(state)
    return jsonify({"ok": True, "event_status": state})

@app.route("/api/admin/event/resume", methods=["POST"])
@require_admin
def api_admin_resume_event():
    data = request.get_json() or {}
    message = data.get("message", "The hunt continues! 🎮")
    state = get_event_status()
    state["status"] = "active"
    state["message"] = message
    _save_event_state_to_db(state)
    return jsonify({"ok": True, "event_status": state})

@app.route("/api/admin/event/reset", methods=["POST"])
@require_admin
def api_admin_reset_event():
    """Reset event back to waiting state."""
    state = {
        "status": "waiting",
        "started_at": None,
        "message": "The hunt hasn't started yet. Please wait for the host!",
        "last_updated": datetime.now(timezone.utc),
    }
    _save_event_state_to_db(state)
    return jsonify({"ok": True, "event_status": state})

@app.route("/api/admin/event/finish", methods=["POST"])
@require_admin
def api_admin_finish_event():
    data = request.get_json() or {}
    message = data.get("message", "The hunt is over! Check the leaderboard for results! 🏆")
    state = {
        "status": "finished",
        "started_at": get_event_status().get("started_at"),
        "message": message,
        "last_updated": datetime.now(timezone.utc),
    }
    _save_event_state_to_db(state)
    return jsonify({"ok": True, "event_status": state})

@app.route("/api/admin/event/message", methods=["POST"])
@require_admin
def api_admin_update_message():
    """Update the broadcast message without changing event status."""
    data = request.get_json() or {}
    message = data.get("message", "")
    if not message:
        return jsonify({"ok": False, "error": "Message cannot be empty"})
    state = get_event_status()
    state["message"] = message
    _save_event_state_to_db(state)
    return jsonify({"ok": True, "event_status": state})

@app.route("/api/admin/event/status")
@require_admin
def api_admin_event_status():
    """Get current event status + live stats."""
    status = get_event_status()
    player_count = mongo_get_player_count()
    board = mongo_get_leaderboard(limit=10)

    # Get active game count from DB
    db = get_db()
    active_info = {}
    if db is not None:
        active_info = {
            "total_players": player_count,
            "total_completions": db.leaderboard.count_documents({}),
            "total_scorecards": db.scorecards.count_documents({}),
        }

    return jsonify({
        "ok": True,
        "event_status": {
            "status": status.get("status"),
            "started_at": status.get("started_at"),
            "message": status.get("message"),
        },
        "stats": active_info,
        "leaderboard_top": board,
    })

@app.route("/api/admin/players")
@require_admin
def api_admin_players():
    players = mongo_get_registered_players()
    return jsonify({"ok": True, "count": len(players), "players": players})

@app.route("/api/admin/nuke", methods=["POST"])
@require_admin
def api_admin_nuke():
    """DANGER: Reset ALL game data. Use with extreme caution."""
    data = request.get_json() or {}
    confirm = data.get("confirm", "")
    if confirm != "NUKE_EVERYTHING":
        return jsonify({"ok": False, "error": "Send confirm='NUKE_EVERYTHING' to proceed"}), 400

    db = get_db()
    if db is not None:
        db.leaderboard.delete_many({})
        db.scorecards.delete_many({})
        db.players.delete_many({})
        db.event_state.delete_many({})

    # Reset event state
    state = {
        "status": "waiting",
        "started_at": None,
        "message": "The hunt hasn't started yet. Please wait for the host!",
        "last_updated": datetime.now(timezone.utc),
    }
    _save_event_state_to_db(state)

    return jsonify({"ok": True, "message": "All data has been reset"})

# ══════════════════════════════════════════════
# Player-facing event status endpoint
# ══════════════════════════════════════════════

@app.route("/api/event/status")
def api_event_status():
    """Public endpoint for players to poll event status."""
    status = get_event_status()
    player_count = mongo_get_player_count()
    return jsonify({
        "ok": True,
        "status": status.get("status", "waiting"),
        "message": status.get("message", ""),
        "active": status.get("status") == "active",
        "player_count": player_count,
    })

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

        # If event is not active, redirect to waiting room
        if is_event_active():
            redirect_url = url_for("index")
        else:
            redirect_url = url_for("waiting_room")

        return jsonify({
            "ok": True,
            "username": result["username"],
            "returning": result.get("returning", False),
            "redirect": redirect_url
        })
    return jsonify(result)

@app.route("/api/start", methods=["POST"])
@require_registered
@require_event_active
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
@require_event_active
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
@require_event_active
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
@require_event_active
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
@require_event_active
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
    event = get_event_status()
    info = {"ok": True, "mongo": "connected" if ok else "disconnected",
            "pymongo": MONGO_AVAILABLE,
            "event_status": event.get("status", "unknown"),
            "collections": list(db.list_collection_names()) if ok else []}
    return jsonify(info), 200 if ok else 503

# ══════════════════════════════════════════════
# Run
# ══════════════════════════════════════════════

if __name__ == "__main__":
    get_db()
    _load_event_state_from_db()
    app.run(debug=True, host="0.0.0.0", port=5000)