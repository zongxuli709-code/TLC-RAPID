# -*- coding: utf-8 -*-
"""Simple English launcher GUI for TLC-RAPID."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from app_metadata import APP_LICENSE, APP_VERSION, COPYRIGHT_NOTICE, SOURCE_URL, get_git_commit
from app_paths import app_root
from utils.load_user_config import (
    USER_INPUT_DIR,
    count_images,
    is_blocking_issue,
    load_concentrations,
    load_settings,
    update_settings_values,
    validate_user_input,
)

ROOT = app_root()

# Colors
BG = "#f0f2f5"
CARD_BG = "#ffffff"
HEADER_BG = "#1f4e79"
GREEN = "#1b7a3d"
GREEN_BG = "#e8f5ec"
RED = "#b00020"
RED_BG = "#fdecea"
GRAY = "#6b7280"
GRAY_BG = "#f3f4f6"
AMBER = "#9a6b00"
BLUE = "#1f4e79"

IMAGING_CHOICES = (
    ("366nm", "366 nm fluorescence (recommended for UV plates)"),
    ("visible", "Visible light"),
    ("254nm", "254 nm"),
    ("auto", ""),  # no hint text
)
METHOD_CHOICES = (
    ("quadratic", ""),
    ("isotonic", ""),
)


def _open_path(path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        if path.suffix:
            path.write_text("", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _latest_results_dir() -> Path | None:
    base = ROOT / "runs" / "predict-seg"
    if not base.is_dir():
        return None
    candidates = [p for p in base.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


class StepCard:
    """Visual step card with status border / title mark."""

    def __init__(self, parent: tk.Widget, title: str) -> None:
        self.title = title
        self.outer = tk.Frame(parent, bg=BG, highlightthickness=0)
        # shadow-like bottom/right strip
        self.shadow = tk.Frame(self.outer, bg="#d1d5db")
        self.shadow.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 3))
        self.card = tk.Frame(
            self.shadow,
            bg=CARD_BG,
            highlightbackground="#d1d5db",
            highlightthickness=1,
            padx=2,
            pady=2,
        )
        self.card.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 2))

        self.title_label = tk.Label(
            self.card,
            text=title,
            font=("Segoe UI", 10, "bold"),
            bg=CARD_BG,
            fg="#111827",
            anchor="w",
        )
        self.title_label.pack(fill="x", padx=12, pady=(10, 2))

        # divider
        self.divider = tk.Frame(self.card, bg="#e5e7eb", height=1)
        self.divider.pack(fill="x", padx=12, pady=(0, 6))

        self.body = tk.Frame(self.card, bg=CARD_BG)
        self.body.pack(fill="x", padx=12, pady=(0, 12))

    def pack(self, **kwargs) -> None:
        self.outer.pack(**kwargs)

    def set_state(self, state: str) -> None:
        """state: pending | ready | done | error"""
        styles = {
            "pending": (GRAY_BG, "#9ca3af", GRAY, self.title),
            "ready": (GREEN_BG, GREEN, GREEN, f"✅ {self.title}"),
            "done": (GREEN_BG, GREEN, GREEN, f"✅ {self.title}"),
            "error": (RED_BG, RED, RED, f"⚠ {self.title}"),
        }
        bg, border, fg, text = styles.get(state, styles["pending"])
        self.card.configure(bg=bg, highlightbackground=border, highlightthickness=2)
        self.title_label.configure(bg=bg, fg=fg, text=text)
        self.divider.configure(bg=border if state != "pending" else "#e5e7eb")
        self.body.configure(bg=bg)
        for child in self.body.winfo_children():
            try:
                child.configure(bg=bg)
            except tk.TclError:
                pass
            for sub in getattr(child, "winfo_children", lambda: [])():
                try:
                    if isinstance(sub, tk.Label):
                        sub.configure(bg=bg)
                    elif isinstance(sub, tk.Frame):
                        sub.configure(bg=bg)
                except tk.TclError:
                    pass


class LauncherApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"TLC-RAPID v{APP_VERSION}")
        self.geometry("740x680")
        self.minsize(660, 600)
        self.configure(bg=BG)

        self._running = False
        self._analysis_done = False  # Open results only after a successful run
        self._proc: subprocess.Popen | None = None

        settings = load_settings()
        self.imaging_var = tk.StringVar(value=str(settings.get("imaging_mode", "auto")))
        self.method_var = tk.StringVar(value=str(settings.get("quantification_method", "quadratic")))

        self._build()
        self.refresh_status()
        if not any(is_blocking_issue(i) for i in validate_user_input()):
            self.show_ready_hint()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        pad = {"padx": 16, "pady": 6}

        header = tk.Frame(self, bg=HEADER_BG)
        header.pack(fill="x")
        tk.Label(
            header,
            text=f"TLC-RAPID v{APP_VERSION}",
            font=("Segoe UI", 18, "bold"),
            fg="white",
            bg=HEADER_BG,
        ).pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(
            header,
            text="TLC spot detection and quantification",
            font=("Segoe UI", 10),
            fg="#d6e4f0",
            bg=HEADER_BG,
        ).pack(anchor="w", padx=16, pady=(0, 12))
        ttk.Button(header, text="License / About", command=self.show_about).place(
            relx=1.0, x=-16, y=16, anchor="ne"
        )

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, **pad)

        tk.Label(
            body,
            text="Follow the steps below, then click Start Analysis.",
            font=("Segoe UI", 10),
            bg=BG,
            fg="#333333",
        ).pack(anchor="w", pady=(4, 10))

        # Step 1
        self.step1 = StepCard(body, "Step 1 - Add TLC images")
        self.step1.pack(fill="x", pady=(0, 10))
        row1 = tk.Frame(self.step1.body, bg=CARD_BG)
        row1.pack(fill="x")
        self.images_status = tk.Label(row1, text="", font=("Segoe UI", 10), anchor="w", bg=CARD_BG)
        self.images_status.pack(side="left", fill="x", expand=True)
        ttk.Button(row1, text="Open images folder", command=self.open_images).pack(side="right")

        # Step 2
        self.step2 = StepCard(body, "Step 2 - Set standard concentrations")
        self.step2.pack(fill="x", pady=(0, 10))
        row2 = tk.Frame(self.step2.body, bg=CARD_BG)
        row2.pack(fill="x")
        self.conc_status = tk.Label(row2, text="", font=("Segoe UI", 10), anchor="w", bg=CARD_BG)
        self.conc_status.pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Edit concentrations", command=self.open_concentrations).pack(side="right")

        # Step 3
        self.step3 = StepCard(body, "Step 3 - Analysis options")
        self.step3.pack(fill="x", pady=(0, 10))
        opts = tk.Frame(self.step3.body, bg=CARD_BG)
        opts.pack(fill="x")

        tk.Label(opts, text="Imaging mode:", font=("Segoe UI", 10), bg=CARD_BG).grid(
            row=0, column=0, sticky="w"
        )
        imaging_combo = ttk.Combobox(
            opts,
            textvariable=self.imaging_var,
            values=[c[0] for c in IMAGING_CHOICES],
            state="readonly",
            width=12,
        )
        imaging_combo.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.imaging_hint = tk.Label(opts, text="", font=("Segoe UI", 9), fg="#555555", bg=CARD_BG)
        self.imaging_hint.grid(row=0, column=2, sticky="w", padx=(10, 0))
        imaging_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_option_hints())

        tk.Label(opts, text="Quantification:", font=("Segoe UI", 10), bg=CARD_BG).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        method_combo = ttk.Combobox(
            opts,
            textvariable=self.method_var,
            values=[c[0] for c in METHOD_CHOICES],
            state="readonly",
            width=12,
        )
        method_combo.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 0))
        self.method_hint = tk.Label(opts, text="", font=("Segoe UI", 9), fg="#555555", bg=CARD_BG)
        self.method_hint.grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(8, 0))
        method_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_option_hints())
        self._update_option_hints()

        # Actions
        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x", pady=(8, 4))
        self.start_btn = ttk.Button(actions, text="Start Analysis", command=self.start_analysis)
        self.start_btn.pack(side="left")
        ttk.Button(actions, text="Refresh status", command=self._refresh_clicked).pack(side="left", padx=8)
        self.results_btn = ttk.Button(
            actions, text="Open results", command=self.open_results, state="disabled"
        )
        self.results_btn.pack(side="left")

        self.ready_label = tk.Label(
            body,
            text="",
            font=("Segoe UI", 10, "bold"),
            bg=BG,
            anchor="w",
        )
        self.ready_label.pack(fill="x", pady=(4, 2))

        # Log
        log_frame = ttk.LabelFrame(body, text="Status")
        log_frame.pack(fill="both", expand=True, pady=4)
        self.log = tk.Text(log_frame, height=10, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=8, pady=8)
        self.log.configure(state="disabled")

        tip = (
            "Tip: After each image, a Help window and an image window open. "
            "Left-click = ADD, Right-click = DELETE, press S to continue, Esc to skip."
        )
        tk.Label(
            body, text=tip, font=("Segoe UI", 9), fg="#666666", bg=BG, wraplength=700, justify="left"
        ).pack(anchor="w", pady=(2, 0))

    def show_about(self) -> None:
        """Display the AGPL appropriate legal notice from the interactive UI."""
        messagebox.showinfo(
            "License / About TLC-RAPID",
            f"TLC-RAPID v{APP_VERSION}\n"
            f"Source commit: {get_git_commit(ROOT)}\n\n"
            f"{COPYRIGHT_NOTICE}\n"
            f"License: {APP_LICENSE}\n\n"
            "This program comes with ABSOLUTELY NO WARRANTY. You may convey it "
            "under the GNU Affero General Public License v3.\n\n"
            f"Source code: {SOURCE_URL}\n"
            f"Full license: {ROOT / 'LICENSE'}",
        )

    def _set_results_enabled(self, enabled: bool) -> None:
        self.results_btn.configure(state="normal" if enabled else "disabled")

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", text)
        self.log.configure(state="disabled")

    def _update_option_hints(self) -> None:
        imaging = self.imaging_var.get()
        method = self.method_var.get()
        self.imaging_hint.configure(text=next((h for k, h in IMAGING_CHOICES if k == imaging), ""))
        self.method_hint.configure(text=next((h for k, h in METHOD_CHOICES if k == method), ""))

    def refresh_status(self) -> None:
        settings = load_settings()
        source = Path(settings["source"])
        source.mkdir(parents=True, exist_ok=True)
        n = count_images(source)

        if n > 0:
            self.images_status.configure(
                text=f"✅ {n} image(s) in user_input/images/", fg=GREEN
            )
            self.step1.set_state("done")
        else:
            self.images_status.configure(
                text="Missing - put .jpg / .png files in user_input/images/",
                fg=RED,
            )
            self.step1.set_state("error")

        conc = load_concentrations()
        default = conc.get("_default", [])
        conc_file = USER_INPUT_DIR / "standard_concentrations.csv"
        if conc_file.exists():
            self.conc_status.configure(
                text=f"✅ Standards: {', '.join(str(x) for x in default)}  (n={len(default)})",
                fg=GREEN,
            )
            self.step2.set_state("done")
        else:
            self.conc_status.configure(
                text="Using built-in defaults - click Edit to set your own values",
                fg=AMBER,
            )
            self.step2.set_state("pending")

        if not self._running:
            if self.imaging_var.get() not in {c[0] for c in IMAGING_CHOICES}:
                self.imaging_var.set(str(settings.get("imaging_mode", "auto")))
            if self.method_var.get() not in {c[0] for c in METHOD_CHOICES}:
                self.method_var.set(str(settings.get("quantification_method", "quadratic")))
            self._update_option_hints()

        # Step 3 is always configurable; mark ready when steps 1-2 allow start
        issues = validate_user_input()
        errors = [i for i in issues if is_blocking_issue(i)]
        if errors:
            self.step3.set_state("pending")
            self.ready_label.configure(
                text="Cannot start yet - fix the red step(s) above.", fg=RED
            )
            if not self._running:
                self.start_btn.configure(state="disabled")
            lines = ["Setup issues:"]
            for e in errors:
                lines.append(f"  - {e.title}")
                for step in e.next_steps:
                    lines.append(f"      -> {step}")
            if not self._running:
                self._set_log("\n".join(lines) + "\n")
        else:
            self.step3.set_state("ready")
            if not self._running:
                self.ready_label.configure(text="Ready to start.", fg=GREEN)
                self.start_btn.configure(state="normal")

        # Open results: only after a successful analysis in this session
        self._set_results_enabled(self._analysis_done and not self._running)

    def show_ready_hint(self) -> None:
        self._set_log(
            "Checklist OK.\n"
            "1) Confirm concentrations match your plate (left to right).\n"
            "2) Choose imaging mode (use 366nm for fluorescence plates).\n"
            "3) Click Start Analysis.\n"
        )

    def _refresh_clicked(self) -> None:
        self.refresh_status()
        if not self._running and not any(is_blocking_issue(i) for i in validate_user_input()):
            self.show_ready_hint()

    def open_images(self) -> None:
        settings = load_settings()
        source = Path(settings["source"])
        source.mkdir(parents=True, exist_ok=True)
        _open_path(source)
        self.after(800, self.refresh_status)

    def open_concentrations(self) -> None:
        path = USER_INPUT_DIR / "standard_concentrations.csv"
        USER_INPUT_DIR.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(
                "image_filename,standard_1,standard_2,standard_3,standard_4,standard_5,notes\n"
                "(default),0.125,0.2,0.25,0.5,1,Default concentrations for all images\n",
                encoding="utf-8-sig",
            )
        _open_path(path)
        self.after(800, self.refresh_status)

    def open_results(self) -> None:
        if not self._analysis_done:
            messagebox.showinfo(
                "No results yet",
                "Run Start Analysis first. This button unlocks when analysis finishes successfully.",
            )
            return
        path = _latest_results_dir()
        if path is None:
            messagebox.showwarning(
                "Results not found",
                "No results folder found under runs/predict-seg/.",
            )
            return
        _open_path(path)

    def start_analysis(self) -> None:
        if self._running:
            return
        self.refresh_status()
        issues = validate_user_input()
        errors = [i for i in issues if is_blocking_issue(i)]
        if errors:
            messagebox.showerror(
                "Cannot start",
                errors[0].title + "\n\n" + "\n".join(errors[0].next_steps),
            )
            return

        try:
            update_settings_values(
                {
                    "imaging_mode": self.imaging_var.get(),
                    "quantification_method": self.method_var.get(),
                }
            )
        except Exception as e:
            messagebox.showerror("Settings error", str(e))
            return

        if not messagebox.askyesno(
            "Start analysis?",
            "Analysis will start now.\n\n"
            "• First run may take 1-2 minutes to load the model.\n"
            "• After each image, a Help window and an image window open:\n"
            "    Left-click = ADD\n"
            "    Right-click = DELETE\n"
            "    Press S = save and go to next image\n"
            "    Esc = skip manual marking\n\n"
            "Continue?",
        ):
            return

        self._running = True
        self._set_results_enabled(False)
        self.start_btn.configure(state="disabled")
        self.ready_label.configure(text="Analysis running... please wait.", fg=BLUE)
        self._set_log("Starting analysis...\n")

        threading.Thread(target=self._run_subprocess, daemon=True).start()

    def _run_subprocess(self) -> None:
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--run"]
        else:
            cmd = [sys.executable, str(ROOT / "run_analysis.py"), "--run"]

        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                self.after(0, self._append_log, line)
            code = self._proc.wait()
            self.after(0, self._on_finished, code)
        except Exception as e:
            self.after(0, self._on_finished, -1, str(e))

    def _on_finished(self, code: int, error: str | None = None) -> None:
        self._running = False
        self._proc = None
        self.start_btn.configure(state="normal")
        if error:
            self._analysis_done = False
            self.ready_label.configure(text="Failed to start analysis.", fg=RED)
            self._append_log(f"\nERROR: {error}\n")
            messagebox.showerror("Analysis failed", error)
            self.refresh_status()
            return

        if code == 0:
            self._analysis_done = True
            self.ready_label.configure(text="Analysis complete. Open results is now available.", fg=GREEN)
            self._append_log(
                "\nDone.\n"
                "Next: Open results -> quantitative_analysis_all_images.xlsx\n"
                "Filter Spot_Type = sample -> read Calculated_Concentration.\n"
            )
            self._set_results_enabled(True)
            if messagebox.askyesno("Done", "Analysis finished.\n\nOpen the results folder now?"):
                self.open_results()
        elif code == 2:
            self._analysis_done = True
            self.ready_label.configure(
                text="Analysis partially complete. Review Image_Status before using results.",
                fg=AMBER,
            )
            self._append_log(
                "\nWARNING: Some images could not be quantified.\n"
                "Open quantitative_analysis_all_images.xlsx and review the Image_Status sheet.\n"
            )
            self._set_results_enabled(True)
            if messagebox.askyesno(
                "Partial result",
                "Some images failed quantification.\n\nOpen the results folder and review Image_Status now?",
            ):
                self.open_results()
        else:
            self._analysis_done = False
            self.ready_label.configure(text="Analysis failed. No valid quantification was produced.", fg=RED)
            self._append_log(
                f"\nProcess exited with code {code}.\n"
                "Review Image_Status in the result workbook and error_log.txt.\n"
            )
            messagebox.showerror(
                "Analysis failed",
                "No image was quantified successfully. Review Image_Status and error_log.txt.",
            )
        self.refresh_status()

    def _on_close(self) -> None:
        if self._running and self._proc is not None:
            if not messagebox.askyesno(
                "Quit?",
                "Analysis is still running. Quit anyway?\n(The analysis process may continue briefly.)",
            ):
                return
            try:
                self._proc.terminate()
            except Exception:
                pass
        self.destroy()


def run_gui() -> None:
    app = LauncherApp()
    app.mainloop()
