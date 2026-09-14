#!/usr/bin/env python3
"""
Komodo Core — multi-game Randovania-style UI scaffold
Games: ShadowMan PC, Turok 1 PC, Turok 2 PC, Turok Evolution PC

Backend tools live in sibling folders; this UI dispatches to them.
CLI works without customtkinter; GUI needs: pip install customtkinter

  python komodo_ui.py --list
  python komodo_ui.py --game turok1 --action shuffle-spawns --input Cartdata.dat --seed 42
  python komodo_ui.py --gui
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent


@dataclass
class GameAction:
    id: str
    label: str
    needs_file: bool
    needs_dir: bool
    tool: Path
    build_cmd: Callable[[Path, Optional[int], Optional[Path]], List[str]]


@dataclass
class GameDef:
    id: str
    name: str
    folder: Path
    actions: List[GameAction]
    notes: str


def _t1_shuffle(inp: Path, seed: Optional[int], out: Optional[Path]) -> List[str]:
    cmd = [sys.executable, str(ROOT / "Turok_1_PC" / "t1_tool.py"), "shuffle-spawns", str(inp)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if out is not None:
        cmd += ["-o", str(out)]
    return cmd


def _t2_shuffle(inp: Path, seed: Optional[int], out: Optional[Path]) -> List[str]:
    cmd = [sys.executable, str(ROOT / "Turok_2_PC" / "t2_tool.py"), "shuffle-spawns", str(inp)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if out is not None:
        cmd += ["-o", str(out)]
    return cmd


def _t2_biased(inp: Path, seed: Optional[int], out: Optional[Path], maps: str) -> List[str]:
    cmd = [sys.executable, str(ROOT / "Turok_2_PC" / "t2_tool.py"), "shuffle-spawns", str(inp), "--maps", maps]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if out is not None:
        cmd += ["-o", str(out)]
    return cmd


def _te_enemies(inp: Path, seed: Optional[int], out: Optional[Path]) -> List[str]:
    cmd = [sys.executable, str(ROOT / "Turok_Evolution_PC" / "te_tool.py"), "shuffle-enemies", str(inp)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if out is not None:
        cmd += ["-o", str(out)]
    return cmd


def _te_pickups(inp: Path, seed: Optional[int], out: Optional[Path]) -> List[str]:
    cmd = [sys.executable, str(ROOT / "Turok_Evolution_PC" / "te_tool.py"), "shuffle-pickups", str(inp)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if out is not None:
        cmd += ["-o", str(out)]
    return cmd


def _te_all(inp: Path, seed: Optional[int], out: Optional[Path]) -> List[str]:
    cmd = [sys.executable, str(ROOT / "Turok_Evolution_PC" / "te_tool.py"), "shuffle-all", str(inp)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if out is not None:
        cmd += ["-o", str(out)]
    return cmd


def _sm_shuffle(inp: Path, seed: Optional[int], out: Optional[Path]) -> List[str]:
    cmd = [sys.executable, str(ROOT / "ShadowMan_PC" / "rsc_tool.py"), "shuffle", str(inp)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if out is not None:
        cmd += ["-o", str(out)]
    return cmd


GAMES: Dict[str, GameDef] = {
    "shadowman": GameDef(
        id="shadowman",
        name="ShadowMan PC",
        folder=ROOT / "ShadowMan_PC",
        notes="quest.rsc item shuffle (stable)",
        actions=[
            GameAction("shuffle", "Shuffle quest items", True, False, ROOT / "ShadowMan_PC" / "rsc_tool.py", _sm_shuffle),
        ],
    ),
    "turok1": GameDef(
        id="turok1",
        name="Turok 1 PC",
        folder=ROOT / "Turok_1_PC",
        notes="Cartdata.dat section-8 spawn shuffle (212 records)",
        actions=[
            GameAction("shuffle-spawns", "Shuffle spawns", True, False, ROOT / "Turok_1_PC" / "t1_tool.py", _t1_shuffle),
        ],
    ),
    "turok2": GameDef(
        id="turok2",
        name="Turok 2 PC",
        folder=ROOT / "Turok_2_PC",
        notes="LSS section-8 spawn shuffle; optional map bias (blind/river/hubs)",
        actions=[
            GameAction("shuffle-spawns", "Shuffle spawns (all)", True, False, ROOT / "Turok_2_PC" / "t2_tool.py", _t2_shuffle),
        ],
    ),
    "evolution": GameDef(
        id="evolution",
        name="Turok Evolution PC",
        folder=ROOT / "Turok_Evolution_PC",
        notes="ATI path-swap: enemies / pickups (no RNC)",
        actions=[
            GameAction("shuffle-enemies", "Shuffle enemies", False, True, ROOT / "Turok_Evolution_PC" / "te_tool.py", _te_enemies),
            GameAction("shuffle-pickups", "Shuffle pickups", False, True, ROOT / "Turok_Evolution_PC" / "te_tool.py", _te_pickups),
            GameAction("shuffle-all", "Shuffle enemies+pickups", False, True, ROOT / "Turok_Evolution_PC" / "te_tool.py", _te_all),
        ],
    ),
}


def run_action(game_id: str, action_id: str, src: Path, seed: Optional[int], out: Optional[Path]) -> int:
    game = GAMES[game_id]
    action = next(a for a in game.actions if a.id == action_id)
    cmd = action.build_cmd(src, seed, out)
    print("Running:", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(action.tool.parent))
    return r.returncode


def run_gui() -> None:
    try:
        import customtkinter as ctk
        from tkinter import filedialog, messagebox
    except ImportError:
        print("GUI needs customtkinter: pip install customtkinter")
        print("CLI works without it — see --help")
        sys.exit(1)

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    class App(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.title("Komodo Core Randomizer")
            self.geometry("780x640")
            self.path: Optional[Path] = None

            hdr = ctk.CTkFrame(self, corner_radius=10)
            hdr.pack(padx=20, pady=15, fill="x")
            ctk.CTkLabel(hdr, text="KOMODO CORE RANDOMIZER", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(10, 2))
            ctk.CTkLabel(hdr, text="ShadowMan · Turok 1 · Turok 2 · Evolution", text_color="gray").pack(pady=(0, 10))

            body = ctk.CTkFrame(self, corner_radius=10)
            body.pack(padx=20, pady=5, fill="both", expand=True)

            left = ctk.CTkFrame(body, fg_color="transparent")
            left.grid(row=0, column=0, padx=15, pady=15, sticky="nw")
            ctk.CTkLabel(left, text="Game", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w")
            self.game_var = ctk.StringVar(value="evolution")
            for gid, g in GAMES.items():
                ctk.CTkRadioButton(left, text=g.name, variable=self.game_var, value=gid, command=self._refresh_actions).pack(anchor="w", pady=3)

            right = ctk.CTkFrame(body, fg_color="transparent")
            right.grid(row=0, column=1, padx=15, pady=15, sticky="nw")
            ctk.CTkLabel(right, text="Action", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w")
            self.action_var = ctk.StringVar(value="")
            self.action_box = ctk.CTkFrame(right, fg_color="transparent")
            self.action_box.pack(anchor="w")
            self.notes = ctk.CTkLabel(right, text="", text_color="gray", wraplength=320, justify="left")
            self.notes.pack(anchor="w", pady=(12, 0))

            row = ctk.CTkFrame(body, fg_color="transparent")
            row.grid(row=1, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
            ctk.CTkButton(row, text="Browse input", command=self._browse, width=120).pack(side="left", padx=5)
            self.lbl = ctk.CTkLabel(row, text="No file/folder selected", text_color="gray")
            self.lbl.pack(side="left", padx=8)
            ctk.CTkLabel(row, text="Seed:").pack(side="left", padx=(20, 4))
            self.seed = ctk.CTkEntry(row, width=100, placeholder_text="random")
            self.seed.pack(side="left")

            ctk.CTkButton(self, text="Generate", height=40, font=ctk.CTkFont(size=14, weight="bold"), command=self._run).pack(padx=20, pady=10, fill="x")
            self.log = ctk.CTkTextbox(self, height=160)
            self.log.pack(padx=20, pady=(0, 15), fill="x")
            self._refresh_actions()
            self._log("Select a game and input, then Generate.\n")

        def _log(self, msg: str) -> None:
            self.log.insert("end", msg)
            self.log.see("end")

        def _refresh_actions(self) -> None:
            for w in self.action_box.winfo_children():
                w.destroy()
            g = GAMES[self.game_var.get()]
            self.notes.configure(text=g.notes)
            if not g.actions:
                return
            self.action_var.set(g.actions[0].id)
            for a in g.actions:
                ctk.CTkRadioButton(self.action_box, text=a.label, variable=self.action_var, value=a.id).pack(anchor="w", pady=2)

        def _browse(self) -> None:
            g = GAMES[self.game_var.get()]
            a = next((x for x in g.actions if x.id == self.action_var.get()), g.actions[0])
            if a.needs_dir:
                p = filedialog.askdirectory(title="Select level root (e.g. Turok_Evolution_PC)")
            else:
                p = filedialog.askopenfilename(title="Select data file")
            if p:
                self.path = Path(p)
                self.lbl.configure(text=self.path.name, text_color="white")

        def _run(self) -> None:
            if not self.path:
                messagebox.showerror("Error", "Select input first")
                return
            raw = self.seed.get().strip()
            seed = int(raw) if raw.isdigit() else random.randint(100000, 999999)
            gid = self.game_var.get()
            aid = self.action_var.get()
            try:
                code = run_action(gid, aid, self.path, seed, None)
                self._log(f"\n[{gid}/{aid}] seed={seed} exit={code}\n")
                if code == 0:
                    messagebox.showinfo("Done", f"Seed {seed} finished (exit 0)")
                else:
                    messagebox.showerror("Failed", f"Tool exited {code}")
            except Exception as e:
                self._log(f"FAIL: {e}\n")
                messagebox.showerror("Failed", str(e))

    App().mainloop()


def main() -> None:
    ap = argparse.ArgumentParser(description="Komodo Core multi-game randomizer")
    ap.add_argument("--gui", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--game", choices=list(GAMES.keys()))
    ap.add_argument("--action", type=str)
    ap.add_argument("--input", type=Path)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()

    if args.list or (not args.gui and not args.game and len(sys.argv) == 1):
        print("Games:")
        for g in GAMES.values():
            print(f"  {g.id:12s}  {g.name}")
            print(f"               {g.notes}")
            for a in g.actions:
                print(f"               - {a.id}: {a.label}")
        if not args.gui:
            return

    if args.gui or (not args.game and len(sys.argv) == 1):
        run_gui()
        return

    if not args.game or not args.action or not args.input:
        ap.error("--game, --action, and --input required in CLI mode")
    sys.exit(run_action(args.game, args.action, args.input, args.seed, args.output))


if __name__ == "__main__":
    main()
