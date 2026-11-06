"""Partie-Tracking, Engine, Spielstile und Erklärungen an der echten Partie testen."""

import os
import sys
import threading
import time

import chess
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chesslens.board_detect import extract_cells, find_board  # noqa: E402
from chesslens.engine import EngineWorker, SyncEngine, find_stockfish  # noqa: E402
from chesslens.explain import eval_words, explain  # noqa: E402
from chesslens.game_tracker import GameTracker  # noqa: E402
from chesslens.piece_recog import Profile, classify  # noqa: E402
from chesslens.styles import rank_choices  # noqa: E402
from chesslens import chess_util as cu  # noqa: E402
from tests.ground_truth import SHOTS, UPLOADS  # noqa: E402

PROFILE = os.path.join(os.path.dirname(__file__), "..", "chesslens", "assets", "profiles", "angelo-app.npz")


def main() -> None:
    prof = Profile.load(PROFILE)
    tracker = GameTracker()
    tracker.set_orientation(False)  # Schwarz unten
    tracker.stable_frames = 1

    # --- Tracking über alle Screenshots ---------------------------------
    print("== Partie-Tracking ==")
    for fname, fen, turn in SHOTS:
        img = cv2.imread(os.path.join(UPLOADS, fname))
        rect = find_board(img)
        cells = extract_cells(img, rect)
        res, _ = classify(cells, prof)
        screen = [[res[r][c].piece for c in range(8)] for r in range(8)]
        upd = tracker.update_from_screen(screen)
        got = tracker.board.board_fen()
        assert got == fen, f"{fname}: {got} != {fen}"
        mv = ", ".join(cu.san_de(tracker.board, m) for m in []) if False else ""
        print(f"{fname[:8]}: {'NEU ' if upd.new_game else ''}{'RESYNC ' if upd.resynced else ''}{[m.uci() for m in upd.moves]} turn={'w' if tracker.board.turn else 'b'} synced={tracker.synced}")
        assert ("w" if tracker.board.turn else "b") == turn, f"{fname}: Zugfarbe falsch"
    print("Zugliste:", " ".join(tracker.san_history()))

    # --- Engine --------------------------------------------------------
    path = find_stockfish()
    assert path, "Stockfish nicht gefunden"
    print("\n== Engine:", path)
    worker = EngineWorker(path, threads=2, hash_mb=128)
    results = []
    done = threading.Event()

    def on_update(r):
        results.append(r)
        if r.done:
            done.set()

    worker.on_update = on_update
    worker.start()
    sync = SyncEngine(path)

    # Stellung nach 9.Qf3 (Schwarz am Zug): Dxd4 gewinnt einen Bauern
    board = chess.Board("r1b1k2r/pp1n1ppp/3bpq2/1B1p4/N2P4/5Q2/PPP2PPP/R3K1NR b KQkq - 0 9")
    t0 = time.time()
    worker.analyse(board, multipv=5, seconds=2.0)
    done.wait(6)
    r = results[-1]
    print(f"Analyse fertig in {time.time() - t0:.1f}s, Tiefe {r.depth}, {len(r.lines)} Varianten, {len(results)} Updates")
    for l in r.lines:
        print("  ", cu.san_de(board, l.move), l.score_str(), " ".join(m.uci() for m in l.pv[:4]))
    assert r.lines[0].move == chess.Move.from_uci("f6d4"), "Erwartet Dxd4 als besten Zug"

    for style in ("engine", "aggressiv", "solide", "trickreich"):
        t0 = time.time()
        ch = rank_choices(board, r.lines, style, risk_cp=60, sync=sync)
        best = ch[0]
        print(f"\n[{style}] -> {cu.san_de(board, best.line.move)} ({best.line.score_str()}, Bonus {best.bonus}, Tags {best.tags}) in {time.time() - t0:.2f}s")
        for s in explain(board, best):
            print("   •", s)

    # Erklärungs-Test: Gabel Db4+ nach 10.Se2
    board2 = chess.Board("r1b1k2r/pp1n1ppp/3bp3/1B1p4/N2q4/5Q2/PPP1NPPP/R3K2R b KQkq - 0 10")
    results.clear(); done.clear()
    worker.analyse(board2, multipv=3, seconds=1.5)
    done.wait(5)
    r2 = results[-1]
    ch = rank_choices(board2, r2.lines, "engine")
    print("\nStellung nach 10.Se2 ->", cu.san_de(board2, ch[0].line.move), ch[0].line.score_str())
    for s in explain(board2, ch[0]):
        print("   •", s)
    print("Einschätzung:", eval_words(ch[0].line.score_cp, ch[0].line.mate))

    # Matt-Test
    board3 = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    results.clear(); done.clear()
    worker.analyse(board3, multipv=3, seconds=1.0)
    done.wait(4)
    ch = rank_choices(board3, results[-1].lines, "aggressiv", sync=sync)
    print("\nMatt-Test ->", cu.san_de(board3, ch[0].line.move), ch[0].line.score_str(), explain(board3, ch[0]))
    assert ch[0].line.move == chess.Move.from_uci("a1a8")

    # Abbruch-Test: neue Stellung während laufender Analyse
    results.clear(); done.clear()
    worker.analyse(board, multipv=3, seconds=5.0)
    time.sleep(0.3)
    worker.analyse(board2, multipv=3, seconds=1.0)
    done.wait(5)
    assert results[-1].board_fen == board2.fen(), "Letztes Ergebnis muss zur neuen Stellung gehören"
    print("\nAbbruch-Test OK")
    worker.stop()
    sync.quit()
    print("\nALLES OK")


if __name__ == "__main__":
    main()
