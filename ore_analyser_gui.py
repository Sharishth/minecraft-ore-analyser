"""Minecraft Ore Analyser: desktop app.

Pick a world, press Scan and build, and get the Excel report and the infographic. The app imports the
scripts in scripts/ as modules and calls their main() functions, exactly as the command line would:

    ore_scan.main(...)            Test 1 (small sample) and Test 2 (large sample)
    build_report.main(...)        Excel workbook
    build_infographic.main(...)   one-page PNG

Run:  python ore_analyser_gui.py          (needs: pip install -r requirements.txt)

Results go to output/<world name>/, so scanning a second world never overwrites the first.
"""
import contextlib
import os
import queue
import subprocess
import sys
import threading
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import ore_scan          # noqa: E402  (the scripts folder must be on sys.path first)
import build_report      # noqa: E402
import build_infographic  # noqa: E402
import mc_formats        # noqa: E402

AUTO = "Auto-detect (from level.dat)"
DEFAULTS = {"chunks1": 4000, "chunks2": 20000, "seed1": 42, "seed2": 7, "slice_width": 1024}


# ---------------- pipeline (no UI code: also used by the tests) ----------------

def find_world(path):
    """Return (world folder, message). A saves folder holding exactly one world resolves to that world."""
    if os.path.isfile(os.path.join(path, "level.dat")):
        return path, ""
    worlds = sorted(d for d in os.listdir(path) if os.path.isfile(os.path.join(path, d, "level.dat"))) \
        if os.path.isdir(path) else []
    if len(worlds) == 1:
        return os.path.join(path, worlds[0]), f"This is a saves folder; using its world '{worlds[0]}'."
    if worlds:
        return None, f"This is a saves folder with {len(worlds)} worlds ({', '.join(worlds)}). Pick one of them."
    return None, "No level.dat here. Pick a world folder (the one inside 'saves')."


def plan(settings):
    """Argument lists for the four steps, from a settings dict. Pure function, easy to test."""
    world, out = settings["world"], settings["out"]
    t1, t2 = os.path.join(out, "test1"), os.path.join(out, "test2")
    common = ["--dim", settings["dim"]]
    if settings.get("mc_version"):
        common += ["--mc-version", settings["mc_version"]]
    scans = [
        [world, *common, "--max-chunks", str(settings["chunks1"]), "--seed", str(DEFAULTS["seed1"]),
         "--out", t1, "--no-section"],
        [world, *common, "--max-chunks", str(settings["chunks2"]), "--seed", str(DEFAULTS["seed2"]),
         "--slice-width", str(settings.get("slice_width", DEFAULTS["slice_width"])), "--out", t2],
    ]
    build = ["--test1", t1, "--test2", t2, "--out-dir", out]
    if settings.get("modpack"):
        build += ["--modpack", settings["modpack"]]
    return scans, build


def run_pipeline(settings, log=print, rescan=True):
    """Scan twice (unless rescan is False) and build both outputs. Returns (report path, infographic path).

    Raises RuntimeError with a readable message when a step stops (the scripts stop with SystemExit).
    """
    scans, build = plan(settings)
    steps = []
    if rescan:
        steps += [("Test 1 scan", ore_scan.main, scans[0]), ("Test 2 scan", ore_scan.main, scans[1])]
    steps += [("Excel report", build_report.main, build), ("Infographic", build_infographic.main, build)]
    results = []
    for name, fn, argv in steps:
        log(f"--- {name} ---")
        try:
            results.append(fn(argv))
        except SystemExit as e:  # argparse errors and the scanner's own stop messages
            raise RuntimeError(f"{name} stopped: {e.code}") from None
    return results[-2], results[-1]


# ---------------- window ----------------

def make_app():
    """Build the window (without starting its event loop)."""
    import customtkinter as ctk
    from tkinter import filedialog

    class QueueWriter:
        """File-like object that hands printed text to the UI thread."""

        def __init__(self, q):
            self.q = q

        def write(self, text):
            if text:
                self.q.put(("log", text))

        def flush(self):
            pass

    class App(ctk.CTk):
        def __init__(self):
            super().__init__()
            ctk.set_appearance_mode("system")
            self.title("Minecraft Ore Analyser")
            self.geometry("900x720")
            self.minsize(760, 600)
            self.q = queue.Queue()
            self.worker = None
            self.outputs = (None, None)
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(2, weight=1)

            ctk.CTkLabel(self, text="Minecraft Ore Analyser", font=ctk.CTkFont(size=22, weight="bold")).grid(
                row=0, column=0, padx=20, pady=(16, 4), sticky="w")

            form = ctk.CTkFrame(self)
            form.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
            form.grid_columnconfigure(1, weight=1)
            r = 0

            def label(text):
                ctk.CTkLabel(form, text=text).grid(row=r, column=0, padx=(12, 8), pady=6, sticky="w")

            label("World folder")
            self.world = ctk.CTkEntry(form, placeholder_text=r"...\.minecraft\saves\MyWorld")
            self.world.grid(row=r, column=1, pady=6, sticky="ew")
            self.world.bind("<FocusOut>", lambda _e: self.inspect_world())
            self.world.bind("<Return>", lambda _e: self.inspect_world())
            ctk.CTkButton(form, text="Browse", width=90, command=self.pick_world).grid(row=r, column=2, padx=12)
            r += 1
            self.detected = ctk.CTkLabel(form, text="", text_color=("gray30", "gray70"), anchor="w", justify="left",
                                         wraplength=560)
            self.detected.grid(row=r, column=1, columnspan=2, sticky="w")
            r += 1

            label("Minecraft version")
            # Newest release first, by release date (mc_formats.versions()).
            self.version = ctk.CTkOptionMenu(form, values=[AUTO] + mc_formats.versions(),
                                             command=lambda _v: self.show_family(), dynamic_resizing=False, width=260)
            self.version.grid(row=r, column=1, pady=6, sticky="w")
            r += 1
            self.family = ctk.CTkLabel(form, text="", text_color=("gray30", "gray70"), anchor="w", justify="left",
                                       wraplength=560)
            self.family.grid(row=r, column=1, columnspan=2, sticky="w")
            r += 1

            label("Dimension")
            self.dim = ctk.CTkOptionMenu(form, values=["overworld"], width=260, dynamic_resizing=False)
            self.dim.grid(row=r, column=1, pady=6, sticky="w")
            r += 1

            label("Modpack (optional)")
            self.modpack = ctk.CTkEntry(form, placeholder_text="shown in the report; the save does not record it")
            self.modpack.grid(row=r, column=1, pady=6, sticky="ew")
            r += 1

            label("Chunks to sample")
            sizes = ctk.CTkFrame(form, fg_color="transparent")
            sizes.grid(row=r, column=1, sticky="w")
            self.chunks1 = ctk.CTkEntry(sizes, width=90)
            self.chunks2 = ctk.CTkEntry(sizes, width=90)
            self.chunks1.insert(0, str(DEFAULTS["chunks1"]))
            self.chunks2.insert(0, str(DEFAULTS["chunks2"]))
            ctk.CTkLabel(sizes, text="Test 1").pack(side="left", padx=(0, 6))
            self.chunks1.pack(side="left")
            ctk.CTkLabel(sizes, text="Test 2").pack(side="left", padx=(16, 6))
            self.chunks2.pack(side="left")
            r += 1

            buttons = ctk.CTkFrame(form, fg_color="transparent")
            buttons.grid(row=r, column=0, columnspan=3, padx=12, pady=(10, 12), sticky="ew")
            self.run_btn = ctk.CTkButton(buttons, text="Scan and build", command=lambda: self.start(True))
            self.build_btn = ctk.CTkButton(buttons, text="Rebuild from last scan", fg_color="transparent",
                                           border_width=1, command=lambda: self.start(False))
            self.open_report = ctk.CTkButton(buttons, text="Open report", state="disabled",
                                             command=lambda: open_path(self.outputs[0]))
            self.open_png = ctk.CTkButton(buttons, text="Open infographic", state="disabled",
                                          command=lambda: open_path(self.outputs[1]))
            for b in (self.run_btn, self.build_btn, self.open_report, self.open_png):
                b.pack(side="left", padx=(0, 8))
            self.progress = ctk.CTkProgressBar(buttons, mode="indeterminate", width=140)

            self.log = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12), wrap="word")
            self.log.grid(row=2, column=0, padx=20, pady=(4, 8), sticky="nsew")
            self.status = ctk.CTkLabel(self, text="Close the world in Minecraft before scanning. "
                                                  "The save is only read, never changed.", anchor="w")
            self.status.grid(row=3, column=0, padx=20, pady=(0, 12), sticky="ew")
            self.show_family()
            self.after(100, self.poll)

        # --- world and version ---
        def pick_world(self):
            path = filedialog.askdirectory(title="Choose a Minecraft world folder")
            if path:
                self.world.delete(0, "end")
                self.world.insert(0, os.path.normpath(path))
                self.inspect_world()

        def inspect_world(self):
            path = self.world.get().strip()
            if not path:
                return
            world, msg = find_world(path)
            if world is None:
                self.detected.configure(text=msg, text_color="#c5221f")
                return
            if world != path:
                self.world.delete(0, "end")
                self.world.insert(0, world)
            info = ore_scan.read_world_info(world)
            dims = ore_scan.list_dimensions(world) or ["overworld"]
            self.dim.configure(values=dims)
            self.dim.set(dims[0])
            ver = info["mc_version"] or "unknown version"
            seed = info["world_seed"] or "not found"
            fam = mc_formats.family_for_data_version(info["data_version"])
            warn = ore_scan.version_warning(info)
            lines = [msg] if msg else []
            lines.append(f"Detected: Minecraft {ver}  |  world seed {seed}" +
                         (f"  |  save format {fam.key}" if fam else ""))
            if warn:
                lines.append(f"Warning: {warn}")
            self.detected.configure(text="\n".join(lines), text_color=("#b06000", "#f0b050") if warn else ("gray30", "gray70"))

        def show_family(self):
            v = self.version.get()
            if v == AUTO:
                self.family.configure(text="The folder layout and seed location are detected from the save.")
                return
            f = mc_formats.family_for_version(v)
            self.family.configure(text=f"Forces the {f.label} save format: {f.layout} folders, "
                                       f"seed in {f.seed_file}.")

        # --- running ---
        def settings(self):
            world = self.world.get().strip()
            if not world or find_world(world)[0] != world:
                raise ValueError("Choose a world folder first.")
            try:
                c1, c2 = int(self.chunks1.get()), int(self.chunks2.get())
            except ValueError:
                raise ValueError("Chunk counts must be whole numbers.") from None
            if not 0 < c1 < c2:
                raise ValueError("Test 2 must sample more chunks than Test 1 (it is the large, careful sample).")
            name = os.path.basename(os.path.normpath(world))
            return {"world": world, "out": os.path.join(ROOT, "output", name), "dim": self.dim.get(),
                    "mc_version": None if self.version.get() == AUTO else self.version.get(),
                    "modpack": self.modpack.get().strip(), "chunks1": c1, "chunks2": c2}

        def start(self, rescan):
            if self.worker and self.worker.is_alive():
                return
            try:
                s = self.settings()
            except ValueError as e:
                self.status.configure(text=str(e), text_color="#c5221f")
                return
            if not rescan and not os.path.isfile(os.path.join(s["out"], "test2", "world_info.json")):
                self.status.configure(text="No earlier scan of this world to rebuild from.", text_color="#c5221f")
                return
            self.log.delete("1.0", "end")
            for b in (self.run_btn, self.build_btn, self.open_report, self.open_png):
                b.configure(state="disabled")
            self.progress.pack(side="left", padx=8)
            self.progress.start()
            self.status.configure(text="Working... a large Test 2 can take a few minutes.",
                                  text_color=("gray10", "gray90"))
            self.worker = threading.Thread(target=self.work, args=(s, rescan), daemon=True)
            self.worker.start()

        def work(self, s, rescan):
            w = QueueWriter(self.q)
            try:
                with contextlib.redirect_stdout(w), contextlib.redirect_stderr(w):
                    out = run_pipeline(s, log=print, rescan=rescan)
                self.q.put(("done", out))
            except RuntimeError as e:
                self.q.put(("error", str(e)))
            except Exception:  # unexpected: show the traceback instead of dying silently
                self.q.put(("error", traceback.format_exc()))

        def poll(self):
            try:
                while True:
                    kind, val = self.q.get_nowait()
                    if kind == "log":
                        self.log.insert("end", val)
                        self.log.see("end")
                    else:
                        self.finish(kind, val)
            except queue.Empty:
                pass
            self.after(100, self.poll)

        def finish(self, kind, val):
            self.progress.stop()
            self.progress.pack_forget()
            self.run_btn.configure(state="normal")
            self.build_btn.configure(state="normal")
            if kind == "done":
                self.outputs = val
                self.open_report.configure(state="normal")
                self.open_png.configure(state="normal")
                self.status.configure(text=f"Done. Files are in {os.path.dirname(val[0])}",
                                      text_color=("#1e8e3e", "#5bd17a"))
            else:
                self.log.insert("end", "\n" + val + "\n")
                self.status.configure(text=val.splitlines()[-1] if val else "Failed.", text_color="#c5221f")

    return App()


def launch():
    make_app().mainloop()


def open_path(path):
    if not path:
        return
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 (opens our own output file with its default app)
    else:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", path], check=False)


if __name__ == "__main__":
    launch()
