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