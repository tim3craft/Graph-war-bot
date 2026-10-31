import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import ctypes
import math
import os
import json
import heapq
from datetime import datetime

import cv2
import numpy as np
import win32gui
import win32ui
import win32process
import psutil

from PIL import Image, ImageTk


APP_TITLE = "TIM3CRAFT GraphWar Botter"

BG = "#0e0c14"
PANEL = "#14121e"
ACCENT = "#c896ff"
PURPLE = "#783cbe"
TEXT = "#eeeeff"
MUTED = "#9990aa"

HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "graphwar_grid_history.json"
)


class GraphWarBotter:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1250x850")
        self.root.minsize(950, 650)
        self.root.configure(bg=BG)

        self.windows = {}
        self.original_image = None
        self.photo = None
        self.zoom = 1.0

        self.points = []
        self.grid_bottom_left = None
        self.grid_top_right = None

        self.mode = "point"
        self.drag_index = None
        self.last_equation = None

        # DRAW MODE
        self.draw_stroke = []
        self.draw_paths = []
        self.is_drawing = False

        self.x_min = -25
        self.x_max = 25
        self.y_min = -15
        self.y_max = 15

        self.grid_history = []

        self.opponents = []
        self.teammates = []
        self.attack_paths = []

        self.obstacle_mask = None
        self.obstacle_contours = []

        self.path_grid_step = 6
        self.auto_mode_var = tk.StringVar(value="Professional")
        self.teammate_count_var = tk.StringVar(value="1")

        self.draw_amplitude_entry = None
        self.draw_cycles_entry = None

        self.build_ui()
        self.load_grid_history()
        self.refresh_windows()

    # ---------------- UI HELPERS ----------------

    def button(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg="#29213a",
            fg=TEXT,
            activebackground=PURPLE,
            activeforeground="white",
            relief="flat",
            bd=0,
            font=("Arial", 9, "bold"),
            padx=9,
            pady=7,
            cursor="hand2"
        )

    def label(self, parent, text):
        return tk.Label(
            parent,
            text=text,
            bg=PANEL,
            fg=TEXT,
            font=("Arial", 9, "bold")
        )

    def entry(self, parent, value):
        item = tk.Entry(
            parent,
            bg="#0d0b13",
            fg=TEXT,
            insertbackground="white",
            relief="flat",
            font=("Arial", 9)
        )
        item.insert(0, value)
        return item

    def add_setting(self, parent, name, value):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=10, pady=2)

        tk.Label(
            row,
            text=name,
            bg=PANEL,
            fg=MUTED,
            font=("Arial", 8)
        ).pack(side="left")

        item = self.entry(row, value)
        item.pack(side="right", fill="x", expand=True, padx=(5, 0))
        return item

    # ---------------- MAIN UI ----------------

    def build_ui(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=12, pady=10)

        tk.Label(
            header,
            text="TIM3CRAFT GRAPHWAR BOTTER",
            bg=BG,
            fg=ACCENT,
            font=("Arial", 17, "bold")
        ).pack(side="left")

        self.window_var = tk.StringVar()

        self.window_select = ttk.Combobox(
            header,
            textvariable=self.window_var,
            state="readonly",
            width=32
        )
        self.window_select.pack(side="right", padx=5)

        self.button(
            header, "Refresh", self.refresh_windows
        ).pack(side="right", padx=4)

        self.button(
            header, "Screenshot", self.take_screenshot
        ).pack(side="right", padx=4)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=5)

        self.left_panel = tk.Frame(body, bg=PANEL, width=270)
        self.left_panel.pack(side="left", fill="y", padx=(0, 10))
        self.left_panel.pack_propagate(False)

        self.controls_canvas = tk.Canvas(
            self.left_panel,
            bg=PANEL,
            highlightthickness=0,
            width=250
        )

        self.controls_scrollbar = ttk.Scrollbar(
            self.left_panel,
            orient="vertical",
            command=self.controls_canvas.yview
        )

        self.controls_canvas.configure(
            yscrollcommand=self.controls_scrollbar.set
        )

        self.controls_scrollbar.pack(side="right", fill="y")
        self.controls_canvas.pack(side="left", fill="both", expand=True)

        self.controls_inner = tk.Frame(
            self.controls_canvas,
            bg=PANEL
        )

        self.controls_window = self.controls_canvas.create_window(
            (0, 0),
            window=self.controls_inner,
            anchor="nw"
        )

        self.controls_inner.bind(
            "<Configure>",
            self.update_controls_scrollregion
        )

        self.controls_canvas.bind(
            "<Configure>",
            self.resize_controls_inner
        )

        self.controls_canvas.bind(
            "<Enter>",
            self.bind_controls_mousewheel
        )

        self.controls_canvas.bind(
            "<Leave>",
            self.unbind_controls_mousewheel
        )

        self.right_panel = tk.Frame(body, bg=PANEL)
        self.right_panel.pack(side="right", fill="both", expand=True)

        self.build_controls()
        self.build_viewer()

    def update_controls_scrollregion(self, event=None):
        self.controls_canvas.configure(
            scrollregion=self.controls_canvas.bbox("all")
        )

    def resize_controls_inner(self, event):
        self.controls_canvas.itemconfigure(
            self.controls_window,
            width=event.width
        )

    def bind_controls_mousewheel(self, event=None):
        self.root.bind_all(
            "<MouseWheel>",
            self.controls_mousewheel
        )

    def unbind_controls_mousewheel(self, event=None):
        self.root.unbind_all("<MouseWheel>")

    def controls_mousewheel(self, event):
        widget = self.root.winfo_containing(
            self.root.winfo_pointerx(),
            self.root.winfo_pointery()
        )

        current = widget

        while current is not None:
            if current == self.controls_canvas:
                self.controls_canvas.yview_scroll(
                    int(-1 * (event.delta / 120)),
                    "units"
                )
                return

            current = getattr(current, "master", None)

    # ---------------- CONTROLS ----------------

    def build_controls(self):
        p = self.controls_inner

        self.label(p, "GRID SETTINGS").pack(
            anchor="w", padx=12, pady=(10, 5)
        )

        self.xmin_entry = self.add_setting(p, "X minimum", "-25")
        self.xmax_entry = self.add_setting(p, "X maximum", "25")
        self.ymin_entry = self.add_setting(p, "Y minimum", "-15")
        self.ymax_entry = self.add_setting(p, "Y maximum", "15")

        self.button(
            p, "Set Bottom-Left", self.set_bottom_left
        ).pack(fill="x", padx=10, pady=(8, 3))

        self.button(
            p, "Set Top-Right", self.set_top_right
        ).pack(fill="x", padx=10, pady=3)

        self.button(
            p, "Clear Grid Bounds", self.clear_grid
        ).pack(fill="x", padx=10, pady=3)

        self.label(p, "GRID HISTORY").pack(
            anchor="w", padx=12, pady=(10, 4)
        )

        history_frame = tk.Frame(p, bg=PANEL)
        history_frame.pack(fill="x", padx=10)

        self.grid_list = tk.Listbox(
            history_frame,
            height=3,
            bg="#0d0b13",
            fg=TEXT,
            selectbackground=PURPLE,
            relief="flat",
            font=("Consolas", 8),
            exportselection=False
        )
        self.grid_list.pack(side="left", fill="both", expand=True)

        history_scroll = ttk.Scrollbar(
            history_frame,
            orient="vertical",
            command=self.grid_list.yview
        )
        history_scroll.pack(side="right", fill="y")
        self.grid_list.configure(yscrollcommand=history_scroll.set)

        history_buttons = tk.Frame(p, bg=PANEL)
        history_buttons.pack(fill="x", padx=10, pady=3)

        self.button(
            history_buttons, "Save", self.save_grid
        ).pack(side="left", fill="x", expand=True, padx=(0, 2))

        self.button(
            history_buttons, "Load", self.load_selected_grid
        ).pack(side="left", fill="x", expand=True, padx=2)

        self.button(
            history_buttons, "Delete", self.delete_selected_grid
        ).pack(side="left", fill="x", expand=True, padx=(2, 0))

        # POINT TOOLS

        self.label(p, "POINT TOOLS").pack(
            anchor="w", padx=12, pady=(10, 5)
        )

        self.button(
            p, "Add Points", self.set_point_mode
        ).pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Wave Generator", self.wave_dialog
        ).pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Undo Point", self.undo_point
        ).pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Clear Points", self.clear_points
        ).pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Generate Equation", self.generate_equation
        ).pack(fill="x", padx=10, pady=(8, 2))

        self.button(
            p, "Copy Equation", self.copy_equation
        ).pack(fill="x", padx=10, pady=2)

        # DRAW MODE

        self.label(p, "DRAW MODE").pack(
            anchor="w", padx=12, pady=(14, 5)
        )

        tk.Label(
            p,
            text="Draw a freehand path on the screenshot.",
            bg=PANEL,
            fg=MUTED,
            font=("Arial", 8),
            wraplength=235,
            justify="left"
        ).pack(anchor="w", padx=10, pady=(0, 5))

        self.button(
            p, "Start Drawing", self.start_drawing
        ).pack(fill="x", padx=10, pady=2)

        self.draw_amplitude_entry = self.add_setting(
            p, "Wave amplitude (pixels)", "18"
        )

        self.draw_cycles_entry = self.add_setting(
            p, "Sine cycles", "4"
        )

        self.button(
            p, "WAVE IT!", self.wave_drawn_path
        ).pack(fill="x", padx=10, pady=(5, 2))

        self.button(
            p, "Undo Drawing", self.undo_drawing
        ).pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Clear Drawing", self.clear_drawing
        ).pack(fill="x", padx=10, pady=2)

        # TEAMMATES

        self.label(p, "TEAMMATE SAFETY").pack(
            anchor="w", padx=12, pady=(12, 5)
        )

        tk.Label(
            p,
            text="Number of teammates (1-4)",
            bg=PANEL,
            fg=MUTED,
            font=("Arial", 8)
        ).pack(anchor="w", padx=10, pady=(3, 2))

        self.teammate_count_select = ttk.Combobox(
            p,
            textvariable=self.teammate_count_var,
            values=["1", "2", "3", "4"],
            state="readonly"
        )
        self.teammate_count_select.pack(fill="x", padx=10, pady=2)

        self.teammate_radius_entry = self.add_setting(
            p, "Safety radius (pixels)", "22"
        )

        self.button(
            p, "Mark Teammate Positions", self.mark_teammates
        ).pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Undo Teammate", self.undo_teammate
        ).pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Clear Teammates", self.clear_teammates
        ).pack(fill="x", padx=10, pady=2)

        # OPPONENTS

        self.label(p, "OPPONENTS").pack(
            anchor="w", padx=12, pady=(12, 5)
        )

        self.button(
            p, "Mark Opponent Positions", self.mark_opponents
        ).pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Undo Opponent", self.undo_opponent
        ).pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Clear Opponents", self.clear_opponents
        ).pack(fill="x", padx=10, pady=2)

        # AUTO KILLER

        self.label(p, "AUTO KILLER").pack(
            anchor="w", padx=12, pady=(12, 5)
        )

        tk.Label(
            p,
            text="Attack Style",
            bg=PANEL,
            fg=MUTED,
            font=("Arial", 8)
        ).pack(anchor="w", padx=10, pady=(4, 2))

        self.auto_mode_select = ttk.Combobox(
            p,
            textvariable=self.auto_mode_var,
            values=["Classic", "Professional"],
            state="readonly"
        )
        self.auto_mode_select.pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Detect Opponents + Black Dangers",
            self.detect_auto_targets
        ).pack(fill="x", padx=10, pady=2)

        self.auto_wave_entry = self.add_setting(
            p, "Wave amplitude", "18"
        )

        self.auto_cycles_entry = self.add_setting(
            p, "Wave cycles", "3"
        )

        self.black_thickness_entry = self.add_setting(
            p, "Min black thickness", "2.5"
        )

        self.button(
            p, "Calculate Wavy Attacks",
            self.calculate_auto_attacks
        ).pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Copy Auto Killer Equations",
            self.copy_auto_equations
        ).pack(fill="x", padx=10, pady=2)

        self.button(
            p, "Clear Auto Paths",
            self.clear_auto_attacks
        ).pack(fill="x", padx=10, pady=2)

        # ZOOM

        self.label(p, "ZOOM").pack(
            anchor="w", padx=12, pady=(12, 4)
        )

        zoom_frame = tk.Frame(p, bg=PANEL)
        zoom_frame.pack(fill="x", padx=10)

        self.button(
            zoom_frame, "-", lambda: self.change_zoom(-0.15)
        ).pack(side="left", fill="x", expand=True)

        self.zoom_label = tk.Label(
            zoom_frame,
            text="100%",
            bg=PANEL,
            fg=ACCENT,
            font=("Arial", 9, "bold")
        )
        self.zoom_label.pack(side="left", padx=8)

        self.button(
            zoom_frame, "+", lambda: self.change_zoom(0.15)
        ).pack(side="right", fill="x", expand=True)

        # POINT LIST

        self.label(p, "POINT LIST").pack(
            anchor="w", padx=12, pady=(10, 4)
        )

        list_frame = tk.Frame(p, bg=PANEL)
        list_frame.pack(fill="x", padx=10, pady=(0, 8))

        self.point_list = tk.Listbox(
            list_frame,
            bg="#0d0b13",
            fg=TEXT,
            selectbackground=PURPLE,
            relief="flat",
            font=("Consolas", 9),
            exportselection=False,
            height=8
        )
        self.point_list.pack(fill="both", expand=True)

        self.point_list.bind(
            "<<ListboxSelect>>", self.select_list_point
        )

    # ---------------- VIEWER ----------------

    def build_viewer(self):
        toolbar = tk.Frame(self.right_panel, bg=PANEL)
        toolbar.pack(fill="x", padx=8, pady=8)

        self.status = tk.Label(
            toolbar,
            text="Select GraphWar and take a screenshot.",
            bg=PANEL,
            fg=MUTED,
            font=("Arial", 9)
        )
        self.status.pack(side="left")

        frame = tk.Frame(self.right_panel, bg="#08070c")
        frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.canvas = tk.Canvas(
            frame,
            bg="#08070c",
            highlightthickness=0
        )

        self.hbar = ttk.Scrollbar(
            frame,
            orient="horizontal",
            command=self.canvas.xview
        )
        self.vbar = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=self.canvas.yview
        )

        self.canvas.configure(
            xscrollcommand=self.hbar.set,
            yscrollcommand=self.vbar.set
        )

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.canvas.bind("<Button-1>", self.canvas_click)
        self.canvas.bind("<B1-Motion>", self.canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.canvas_release)
        self.canvas.bind("<Button-3>", self.canvas_right_click)
        self.canvas.bind("<MouseWheel>", self.mousewheel_zoom)

    # ---------------- WINDOW DETECTION ----------------

    def refresh_windows(self):
        self.windows.clear()
        found = []

        def callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return

            title = win32gui.GetWindowText(hwnd)
            if not title:
                return

            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                name = process.name().lower()
                command = " ".join(process.cmdline()).lower()

                if (
                    "java" in name
                    or "graphwar" in title.lower()
                    or "graphwar" in command
                ):
                    label = f"{title} [{pid}]"
                    self.windows[label] = hwnd
                    found.append(label)

            except Exception:
                pass

        win32gui.EnumWindows(callback, None)
        self.window_select["values"] = found

        if found:
            selected = next(
                (item for item in found if "graphwar" in item.lower()),
                found[0]
            )
            self.window_var.set(selected)
            self.status.config(text=f"Found {len(found)} possible windows.")
        else:
            self.window_var.set("")
            self.status.config(text="No Java or GraphWar windows found.")

    # ---------------- SCREENSHOT ----------------

    def take_screenshot(self):
        hwnd = self.windows.get(self.window_var.get())

        if not hwnd or not win32gui.IsWindow(hwnd):
            messagebox.showerror("Screenshot", "Select a valid GraphWar window.")
            return

        if win32gui.IsIconic(hwnd):
            messagebox.showerror(
                "Screenshot",
                "Restore the GraphWar window before taking a screenshot."
            )
            return

        window_dc = None
        source_dc = None
        memory_dc = None
        bitmap = None

        try:
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]

            if width <= 0 or height <= 0:
                raise Exception("Invalid window size.")

            window_dc = win32gui.GetWindowDC(hwnd)
            source_dc = win32ui.CreateDCFromHandle(window_dc)
            memory_dc = source_dc.CreateCompatibleDC()

            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(source_dc, width, height)
            memory_dc.SelectObject(bitmap)

            result = ctypes.windll.user32.PrintWindow(
                hwnd, memory_dc.GetSafeHdc(), 2
            )

            if result != 1:
                result = ctypes.windll.user32.PrintWindow(
                    hwnd, memory_dc.GetSafeHdc(), 0
                )

            bits = bitmap.GetBitmapBits(True)

            image = Image.frombuffer(
                "RGB",
                (width, height),
                bits,
                "raw",
                "BGRX",
                0,
                1
            ).copy()

            self.original_image = image
            self.zoom = 1.0

            self.points.clear()
            self.grid_bottom_left = None
            self.grid_top_right = None

            self.opponents.clear()
            self.teammates.clear()
            self.attack_paths.clear()

            self.draw_stroke.clear()
            self.draw_paths.clear()
            self.is_drawing = False
            self.mode = "point"

            self.obstacle_mask = None
            self.obstacle_contours = []

            self.refresh_point_list()
            self.draw_scene()

            self.status.config(
                text=f"Screenshot captured: {width} x {height}"
            )

            if result != 1:
                messagebox.showwarning(
                    "Screenshot",
                    "PrintWindow did not report success. The image may be incomplete."
                )

        except Exception as error:
            messagebox.showerror("Screenshot Error", str(error))

        finally:
            if memory_dc:
                memory_dc.DeleteDC()

            if source_dc:
                source_dc.DeleteDC()

            if window_dc:
                win32gui.ReleaseDC(hwnd, window_dc)

            if bitmap:
                try:
                    win32gui.DeleteObject(bitmap.GetHandle())
                except Exception:
                    pass

    # ---------------- DRAWING ----------------

    def draw_scene(self):
        self.canvas.delete("all")

        if self.original_image is None:
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            return

        width = max(1, int(self.original_image.width * self.zoom))
        height = max(1, int(self.original_image.height * self.zoom))

        resized = self.original_image.resize(
            (width, height),
            Image.Resampling.LANCZOS
        )

        self.photo = ImageTk.PhotoImage(resized)

        self.canvas.create_image(
            0, 0,
            image=self.photo,
            anchor="nw",
            tags="screenshot"
        )

        self.canvas.configure(scrollregion=(0, 0, width, height))

        self.draw_overlays()
        self.zoom_label.config(text=f"{int(self.zoom * 100)}%")

    def draw_overlays(self):
        self.canvas.delete("overlay")

        if self.original_image is None:
            return

        if self.grid_bottom_left and self.grid_top_right:
            x1, y1 = self.image_to_canvas(*self.grid_bottom_left)
            x2, y2 = self.image_to_canvas(*self.grid_top_right)

            self.canvas.create_rectangle(
                x1, y2, x2, y1,
                outline=ACCENT,
                width=2,
                dash=(7, 4),
                tags="overlay"
            )

        # Detected black danger contours.

        for contour in self.obstacle_contours:
            points = contour.reshape(-1, 2)

            if len(points) < 2:
                continue

            coords = []

            for x, y in points:
                cx, cy = self.image_to_canvas(float(x), float(y))
                coords.extend((cx, cy))

            self.canvas.create_line(
                *coords,
                fill="#ffb347",
                width=max(2, int(2 * self.zoom)),
                tags="overlay"
            )

        # Teammate safety circles.

        try:
            safety_radius = max(1, float(self.teammate_radius_entry.get()))
        except Exception:
            safety_radius = 22

        for i, (x, y) in enumerate(self.teammates):
            cx, cy = self.image_to_canvas(x, y)
            radius = safety_radius * self.zoom

            self.canvas.create_oval(
                cx-radius, cy-radius,
                cx+radius, cy+radius,
                outline="#38ff87",
                width=2,
                dash=(5, 3),
                tags="overlay"
            )

            self.canvas.create_text(
                cx, cy-radius-10,
                text=f"TEAMMATE {i+1}",
                fill="#38ff87",
                font=("Arial", 8, "bold"),
                tags="overlay"
            )

        # Auto Killer paths.

        for path in self.attack_paths:
            if len(path) < 2:
                continue

            coords = []

            for x, y in path:
                cx, cy = self.image_to_canvas(x, y)
                coords.extend((cx, cy))

            self.canvas.create_line(
                *coords,
                fill="#00ffcc",
                width=max(2, int(3 * self.zoom)),
                smooth=True,
                tags="overlay"
            )

        # DRAW MODE: raw freehand stroke.

        if len(self.draw_stroke) >= 2:
            coords = []

            for x, y in self.draw_stroke:
                cx, cy = self.image_to_canvas(x, y)
                coords.extend((cx, cy))

            self.canvas.create_line(
                *coords,
                fill="#ff55cc",
                width=max(2, int(3 * self.zoom)),
                smooth=True,
                tags="overlay"
            )

        # DRAW MODE: generated sine paths.

        for path in self.draw_paths:
            if len(path) < 2:
                continue

            coords = []

            for x, y in path:
                cx, cy = self.image_to_canvas(x, y)
                coords.extend((cx, cy))

            self.canvas.create_line(
                *coords,
                fill="#00eaff",
                width=max(2, int(3 * self.zoom)),
                smooth=True,
                tags="overlay"
            )

        # Opponents.

        for i, (x, y) in enumerate(self.opponents):
            cx, cy = self.image_to_canvas(x, y)
            r = max(6, 7 * self.zoom)

            self.canvas.create_oval(
                cx-r, cy-r, cx+r, cy+r,
                outline="#ff4444",
                width=2,
                tags="overlay"
            )

            self.canvas.create_text(
                cx, cy-r-10,
                text=f"OPPONENT {i+1}",
                fill="#ff6666",
                font=("Arial", 8, "bold"),
                tags="overlay"
            )

        # Normal points.

        if len(self.points) > 1:
            coords = [
                self.image_to_canvas(x, y)
                for x, y in self.points
            ]

            for i in range(len(coords)-1):
                self.canvas.create_line(
                    coords[i][0], coords[i][1],
                    coords[i+1][0], coords[i+1][1],
                    fill=ACCENT,
                    width=2,
                    tags="overlay"
                )

        for i, point in enumerate(self.points):
            x, y = self.image_to_canvas(*point)
            radius = max(4, 5 * self.zoom)

            self.canvas.create_oval(
                x-radius, y-radius,
                x+radius, y+radius,
                fill=ACCENT,
                outline="white",
                width=1,
                tags="overlay"
            )

            self.canvas.create_text(
                x+10, y-12,
                text=str(i+1),
                fill="white",
                font=("Arial", 10, "bold"),
                tags="overlay"
            )

    def image_to_canvas(self, x, y):
        return x * self.zoom, y * self.zoom

    def canvas_to_image(self, event):
        x = self.canvas.canvasx(event.x) / self.zoom
        y = self.canvas.canvasy(event.y) / self.zoom
        return x, y

    # ---------------- DRAW MODE ----------------

    def start_drawing(self):
        if self.original_image is None:
            messagebox.showerror(
                "Draw Mode",
                "Take a screenshot first."
            )
            return

        self.mode = "draw"
        self.is_drawing = False
        self.draw_stroke.clear()

        self.draw_overlays()

        self.status.config(
            text="Draw Mode: hold LEFT MOUSE and draw your path."
        )

    def wave_drawn_path(self):
        if self.original_image is None:
            messagebox.showerror(
                "Draw Mode",
                "Take a screenshot first."
            )
            return

        if len(self.draw_stroke) < 3:
            messagebox.showerror(
                "Draw Mode",
                "Draw a path with at least three points first."
            )
            return

        try:
            amplitude = abs(float(self.draw_amplitude_entry.get()))
            cycles = float(self.draw_cycles_entry.get())

            if amplitude > 300:
                raise ValueError(
                    "Amplitude must be 300 pixels or less."
                )

            if cycles <= 0 or cycles > 30:
                raise ValueError(
                    "Cycles must be greater than 0 and no more than 30."
                )

        except Exception as error:
            messagebox.showerror("Draw Mode", str(error))
            return

        smooth_stroke = self.smooth_freehand_path(self.draw_stroke)

        if len(smooth_stroke) < 3:
            messagebox.showerror(
                "Draw Mode",
                "Your drawing is too short."
            )
            return

        waved_path = self.create_draw_wave(
            smooth_stroke,
            amplitude,
            cycles
        )

        if len(waved_path) < 2:
            messagebox.showerror(
                "Draw Mode",
                "Could not create a wave from that drawing."
            )
            return

        self.draw_paths.append(waved_path)

        self.mode = "point"
        self.is_drawing = False

        self.draw_overlays()

        self.status.config(
            text=f"Wave created! Amplitude: {amplitude:g}px | Cycles: {cycles:g}"
        )

    def smooth_freehand_path(self, path):
        if len(path) < 3:
            return list(path)

        # Remove points that are extremely close together.

        cleaned = [path[0]]

        for point in path[1:]:
            if math.hypot(
                point[0]-cleaned[-1][0],
                point[1]-cleaned[-1][1]
            ) >= 1.5:
                cleaned.append(point)

        if len(cleaned) < 3:
            return cleaned

        # Chaikin smoothing.

        smoothed = cleaned

        for _ in range(2):
            new_points = [smoothed[0]]

            for i in range(len(smoothed)-1):
                a = smoothed[i]
                b = smoothed[i+1]

                q = (
                    a[0]*0.75+b[0]*0.25,
                    a[1]*0.75+b[1]*0.25
                )

                r = (
                    a[0]*0.25+b[0]*0.75,
                    a[1]*0.25+b[1]*0.75
                )

                new_points.extend([q, r])

            new_points.append(smoothed[-1])
            smoothed = new_points

        return self.resample_route(
            smoothed,
            max(60, min(400, len(smoothed)))
        )

    def create_draw_wave(self, path, amplitude, cycles):
        if len(path) < 3:
            return path

        total_length = self.route_length(path)

        if total_length < 2:
            return path

        count = max(80, min(600, int(total_length / 2)))

        result = []

        for i in range(count+1):
            t = i / count
            distance = total_length * t

            center = self.interpolate_route(path, distance)

            before = self.interpolate_route(
                path,
                max(0, distance-2)
            )

            after = self.interpolate_route(
                path,
                min(total_length, distance+2)
            )

            dx = after[0]-before[0]
            dy = after[1]-before[1]

            length = math.hypot(dx, dy)

            if length < 0.001:
                result.append(center)
                continue

            # Normal direction to the drawn path.

            normal_x = -dy / length
            normal_y = dx / length

            # Sine wave with an envelope that keeps
            # the beginning and ending points in place.

            wave = (
                amplitude
                * math.sin(2 * math.pi * cycles * t)
                * math.sin(math.pi * t)
            )

            candidate = (
                center[0] + normal_x * wave,
                center[1] + normal_y * wave
            )

            # Keep the result inside the screenshot.

            candidate = (
                max(0, min(self.original_image.width, candidate[0])),
                max(0, min(self.original_image.height, candidate[1]))
            )

            result.append(candidate)

        return result

    def undo_drawing(self):
        if self.is_drawing:
            self.is_drawing = False
            self.draw_stroke.clear()
            self.mode = "point"

            self.draw_overlays()
            self.status.config(text="Current drawing cancelled.")
            return

        if self.draw_paths:
            self.draw_paths.pop()
            self.draw_overlays()
            self.status.config(text="Last generated drawing wave removed.")
            return

        if self.draw_stroke:
            self.draw_stroke.clear()
            self.draw_overlays()
            self.status.config(text="Drawing cleared.")
            return

        self.status.config(text="There are no drawings to undo.")

    def clear_drawing(self):
        self.draw_stroke.clear()
        self.draw_paths.clear()

        self.is_drawing = False

        if self.mode == "draw":
            self.mode = "point"

        self.draw_overlays()
        self.status.config(text="Draw Mode drawings cleared.")

    # ---------------- ZOOM ----------------

    def change_zoom(self, amount):
        if self.original_image is None:
            return

        self.zoom = max(0.25, min(4.0, self.zoom + amount))
        self.draw_scene()

    def mousewheel_zoom(self, event):
        self.change_zoom(0.1 if event.delta > 0 else -0.1)

    # ---------------- GRID CALIBRATION ----------------

    def set_point_mode(self):
        self.mode = "point"
        self.is_drawing = False
        self.status.config(text="Point mode: click to add points.")

    def set_bottom_left(self):
        if self.original_image is None:
            messagebox.showerror("Grid", "Take a screenshot first.")
            return

        self.mode = "bottom"
        self.is_drawing = False
        self.status.config(text="Click the bottom-left graph corner.")

    def set_top_right(self):
        if self.original_image is None:
            messagebox.showerror("Grid", "Take a screenshot first.")
            return

        self.mode = "top"
        self.is_drawing = False
        self.status.config(text="Click the top-right graph corner.")

    def clear_grid(self):
        self.grid_bottom_left = None
        self.grid_top_right = None

        self.refresh_point_list()
        self.draw_overlays()

        self.status.config(text="Grid bounds cleared. Saved grids are untouched.")

    def canvas_click(self, event):
        if self.original_image is None:
            return

        x, y = self.canvas_to_image(event)

        if self.mode == "draw":
            x = max(0, min(self.original_image.width, x))
            y = max(0, min(self.original_image.height, y))

            self.draw_stroke = [(x, y)]
            self.is_drawing = True

            self.draw_overlays()
            self.status.config(text="Drawing... release the mouse when finished.")
            return

        if self.mode == "bottom":
            self.grid_bottom_left = (x, y)
            self.mode = "point"
            self.draw_overlays()
            self.refresh_point_list()
            self.status.config(text="Bottom-left saved. Set top-right next.")
            return

        if self.mode == "top":
            self.grid_top_right = (x, y)
            self.mode = "point"
            self.draw_overlays()
            self.refresh_point_list()

            if self.grid_is_valid():
                self.status.config(text="Grid calibration complete.")
            else:
                self.status.config(
                    text="Invalid grid. Set bottom-left and top-right correctly."
                )
            return

        if self.mode == "teammates":
            try:
                count = int(self.teammate_count_var.get())
            except Exception:
                count = 1

            if len(self.teammates) >= count:
                self.status.config(text="You have marked all selected teammates.")
                self.mode = "point"
                return

            self.teammates.append((x, y))
            self.draw_overlays()

            if len(self.teammates) >= count:
                self.mode = "point"
                self.status.config(
                    text=f"Marked {len(self.teammates)} teammates. Safety zones enabled."
                )
            else:
                self.status.config(
                    text=f"Teammate {len(self.teammates)} marked. Click the next teammate."
                )
            return

        if self.mode == "opponents":
            self.opponents.append((x, y))
            self.draw_overlays()
            self.status.config(
                text=f"Marked opponent {len(self.opponents)}. Click another or choose Add Points."
            )
            return

        if not self.grid_is_valid():
            self.status.config(text="Set both grid corners before adding points.")
            return

        nearest = self.nearest_point(x, y)

        if nearest is not None:
            self.drag_index = nearest
            return

        self.points.append((x, y))
        self.refresh_point_list()
        self.draw_overlays()

    def canvas_drag(self, event):
        if self.original_image is None:
            return

        x, y = self.canvas_to_image(event)

        if self.mode == "draw" and self.is_drawing:
            x = max(0, min(self.original_image.width, x))
            y = max(0, min(self.original_image.height, y))

            if not self.draw_stroke or math.hypot(
                x-self.draw_stroke[-1][0],
                y-self.draw_stroke[-1][1]
            ) >= 1:
                self.draw_stroke.append((x, y))
                self.draw_overlays()

            return

        if self.drag_index is None:
            return

        x = max(0, min(self.original_image.width, x))
        y = max(0, min(self.original_image.height, y))

        self.points[self.drag_index] = (x, y)
        self.refresh_point_list()
        self.draw_overlays()

    def canvas_release(self, event):
        if self.mode == "draw" and self.is_drawing:
            x, y = self.canvas_to_image(event)

            if self.original_image is not None:
                x = max(0, min(self.original_image.width, x))
                y = max(0, min(self.original_image.height, y))

                if not self.draw_stroke or math.hypot(
                    x-self.draw_stroke[-1][0],
                    y-self.draw_stroke[-1][1]
                ) >= 1:
                    self.draw_stroke.append((x, y))

            self.is_drawing = False
            self.draw_overlays()

            if len(self.draw_stroke) >= 3:
                self.status.config(
                    text="Stroke captured. Press WAVE IT! to generate the sine path."
                )
            else:
                self.status.config(
                    text="Stroke too short. Draw a longer path."
                )

            return

        self.drag_index = None

    def canvas_right_click(self, event):
        if not self.points or self.mode == "draw":
            return

        x, y = self.canvas_to_image(event)
        nearest = self.nearest_point(x, y)

        if nearest is not None:
            del self.points[nearest]
            self.refresh_point_list()
            self.draw_overlays()

    def nearest_point(self, x, y):
        best = None
        best_distance = 15 / self.zoom

        for i, (px, py) in enumerate(self.points):
            distance = math.hypot(px-x, py-y)

            if distance < best_distance:
                best = i
                best_distance = distance

        return best

    def grid_is_valid(self):
        if self.grid_bottom_left is None or self.grid_top_right is None:
            return False

        bx, by = self.grid_bottom_left
        tx, ty = self.grid_top_right

        return tx > bx and by > ty

    # ---------------- TEAMMATES ----------------

    def mark_teammates(self):
        if self.original_image is None:
            messagebox.showerror("Teammates", "Take a screenshot first.")
            return

        try:
            count = int(self.teammate_count_var.get())
            if count < 1 or count > 4:
                raise ValueError("Choose between 1 and 4 teammates.")

            radius = float(self.teammate_radius_entry.get())
            if radius <= 0 or radius > 200:
                raise ValueError("Safety radius must be between 1 and 200 pixels.")

        except Exception as error:
            messagebox.showerror("Teammates", str(error))
            return

        self.teammates.clear()
        self.mode = "teammates"
        self.is_drawing = False
        self.draw_overlays()
        self.status.config(
            text=f"Click the position of teammate 1 of {count}."
        )

    def undo_teammate(self):
        if self.teammates:
            self.teammates.pop()
            self.draw_overlays()
            self.status.config(text="Last teammate position removed.")

    def clear_teammates(self):
        self.teammates.clear()
        self.draw_overlays()
        self.status.config(text="Teammate safety positions cleared.")

    # ---------------- OPPONENTS ----------------

    def mark_opponents(self):
        if self.original_image is None:
            messagebox.showerror("Opponents", "Take a screenshot first.")
            return

        self.mode = "opponents"
        self.is_drawing = False
        self.status.config(
            text="Click each opponent position. Select Add Points when finished."
        )

    def undo_opponent(self):
        if self.opponents:
            self.opponents.pop()
            self.draw_overlays()
            self.status.config(text="Last opponent position removed.")

    def clear_opponents(self):
        self.opponents.clear()
        self.attack_paths.clear()
        self.draw_overlays()
        self.status.config(text="Opponent positions cleared.")

    # ---------------- GRID RANGES ----------------

    def get_ranges(self):
        try:
            self.x_min = float(self.xmin_entry.get())
            self.x_max = float(self.xmax_entry.get())
            self.y_min = float(self.ymin_entry.get())
            self.y_max = float(self.ymax_entry.get())

            if self.x_max <= self.x_min:
                raise ValueError("X maximum must be greater than X minimum.")

            if self.y_max <= self.y_min:
                raise ValueError("Y maximum must be greater than Y minimum.")

            return True

        except Exception as error:
            messagebox.showerror("Grid Settings", str(error))
            return False

    def set_range_entries(self, xmin, xmax, ymin, ymax):
        for item, value in [
            (self.xmin_entry, xmin),
            (self.xmax_entry, xmax),
            (self.ymin_entry, ymin),
            (self.ymax_entry, ymax)
        ]:
            item.delete(0, tk.END)
            item.insert(0, str(value))

    def image_to_graph(self, x, y):
        bx, by = self.grid_bottom_left
        tx, ty = self.grid_top_right

        gx = self.x_min + (
            (x-bx)/(tx-bx)
        ) * (self.x_max-self.x_min)

        gy = self.y_min + (
            (by-y)/(by-ty)
        ) * (self.y_max-self.y_min)

        return gx, gy

    def graph_to_image(self, gx, gy):
        bx, by = self.grid_bottom_left
        tx, ty = self.grid_top_right

        x = bx + (
            (gx-self.x_min)/(self.x_max-self.x_min)
        ) * (tx-bx)

        y = by - (
            (gy-self.y_min)/(self.y_max-self.y_min)
        ) * (by-ty)

        return x, y

    # ---------------- GRID HISTORY ----------------

    def load_grid_history(self):
        if not os.path.exists(HISTORY_FILE):
            self.grid_history = []
            self.refresh_grid_list()
            return

        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)

            self.grid_history = data if isinstance(data, list) else []
            self.refresh_grid_list()

        except Exception as error:
            self.grid_history = []
            self.refresh_grid_list()
            messagebox.showwarning(
                "Grid History",
                f"Could not read grid history:\n{error}"
            )

    def write_grid_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as file:
                json.dump(self.grid_history, file, indent=4)
            return True

        except Exception as error:
            messagebox.showerror(
                "Grid History",
                f"Could not save grid history:\n{error}"
            )
            return False

    def refresh_grid_list(self):
        self.grid_list.delete(0, tk.END)

        for grid in self.grid_history:
            self.grid_list.insert(
                tk.END,
                grid.get("name", "Unnamed Grid")
            )

    def save_grid(self):
        if not self.grid_is_valid():
            messagebox.showerror("Save Grid", "Set both grid corners correctly first.")
            return

        if not self.get_ranges():
            return

        name = simpledialog.askstring(
            "Save Grid",
            "Enter a name for this grid:",
            parent=self.root
        )

        if name is None:
            return

        name = name.strip()

        if not name:
            messagebox.showerror("Save Grid", "Grid name cannot be empty.")
            return

        grid = {
            "name": name,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bottom_left": list(self.grid_bottom_left),
            "top_right": list(self.grid_top_right),
            "x_min": self.x_min,
            "x_max": self.x_max,
            "y_min": self.y_min,
            "y_max": self.y_max
        }

        self.grid_history.append(grid)

        if self.write_grid_history():
            self.refresh_grid_list()
            self.grid_list.selection_clear(0, tk.END)
            self.grid_list.selection_set(tk.END)
            self.grid_list.see(tk.END)
            self.status.config(text=f"Saved grid: {name}")

    def load_selected_grid(self):
        selection = self.grid_list.curselection()

        if not selection:
            messagebox.showinfo("Load Grid", "Select a grid from Grid History first.")
            return

        grid = self.grid_history[selection[0]]

        try:
            bottom = grid["bottom_left"]
            top = grid["top_right"]

            bottom_left = (float(bottom[0]), float(bottom[1]))
            top_right = (float(top[0]), float(top[1]))

            xmin = float(grid["x_min"])
            xmax = float(grid["x_max"])
            ymin = float(grid["y_min"])
            ymax = float(grid["y_max"])

            if xmax <= xmin or ymax <= ymin:
                raise ValueError("Invalid saved coordinate ranges.")

            if top_right[0] <= bottom_left[0] or bottom_left[1] <= top_right[1]:
                raise ValueError("Invalid saved grid corners.")

            if self.original_image is None:
                messagebox.showerror(
                    "Load Grid",
                    "Take a screenshot first. Saved grid coordinates are based on screenshot dimensions."
                )
                return

            self.grid_bottom_left = bottom_left
            self.grid_top_right = top_right

            self.x_min = xmin
            self.x_max = xmax
            self.y_min = ymin
            self.y_max = ymax

            self.set_range_entries(xmin, xmax, ymin, ymax)
            self.refresh_point_list()
            self.draw_overlays()

            self.status.config(
                text=f"Loaded grid: {grid.get('name', 'Unnamed Grid')}"
            )

        except Exception as error:
            messagebox.showerror("Load Grid", f"Could not load this grid:\n{error}")

    def delete_selected_grid(self):
        selection = self.grid_list.curselection()

        if not selection:
            messagebox.showinfo("Delete Grid", "Select a grid from Grid History first.")
            return

        index = selection[0]
        name = self.grid_history[index].get("name", "Unnamed Grid")

        if not messagebox.askyesno(
            "Delete Grid",
            f"Delete '{name}' from Grid History?"
        ):
            return

        del self.grid_history[index]

        if self.write_grid_history():
            self.refresh_grid_list()
            self.status.config(text=f"Deleted grid: {name}")

    # ---------------- POINT LIST ----------------

    def refresh_point_list(self):
        self.point_list.delete(0, tk.END)

        for i, point in enumerate(self.points):
            if self.grid_is_valid():
                gx, gy = self.image_to_graph(*point)
                self.point_list.insert(
                    tk.END,
                    f"{i+1}: ({gx:.2f}, {gy:.2f})"
                )
            else:
                self.point_list.insert(tk.END, f"Point {i+1}")

    def select_list_point(self, event):
        selection = self.point_list.curselection()

        if not selection or self.original_image is None:
            return

        index = selection[0]
        x, y = self.image_to_canvas(*self.points[index])

        self.canvas.xview_moveto(
            max(
                0,
                (x-self.canvas.winfo_width()/2) /
                max(1, self.original_image.width*self.zoom)
            )
        )

        self.canvas.yview_moveto(
            max(
                0,
                (y-self.canvas.winfo_height()/2) /
                max(1, self.original_image.height*self.zoom)
            )
        )

    def undo_point(self):
        if self.points:
            self.points.pop()
            self.refresh_point_list()
            self.draw_overlays()

    def clear_points(self):
        self.points.clear()
        self.refresh_point_list()
        self.draw_overlays()
        self.status.config(
            text="Points cleared. Screenshot and grid are still saved."
        )

    # ---------------- WAVE GENERATOR ----------------

    def wave_dialog(self):
        if not self.grid_is_valid():
            messagebox.showerror("Wave Generator", "Set the grid corners first.")
            return

        if not self.get_ranges():
            return

        window = tk.Toplevel(self.root)
        window.title("Wave Generator")
        window.geometry("300x340")
        window.configure(bg=PANEL)
        window.resizable(False, False)

        fields = {}

        defaults = [
            ("X start", str(self.x_min)),
            ("X end", str(self.x_max)),
            ("Center Y", "0"),
            ("Amplitude", "5"),
            ("Cycles", "2"),
            ("Number of points", "80")
        ]

        tk.Label(
            window,
            text="CREATE A WAVE",
            bg=PANEL,
            fg=ACCENT,
            font=("Arial", 13, "bold")
        ).pack(pady=12)

        for name, value in defaults:
            row = tk.Frame(window, bg=PANEL)
            row.pack(fill="x", padx=15, pady=4)

            tk.Label(
                row,
                text=name,
                bg=PANEL,
                fg=TEXT,
                font=("Arial", 9)
            ).pack(side="left")

            item = tk.Entry(
                row,
                bg="#0d0b13",
                fg=TEXT,
                insertbackground="white",
                relief="flat",
                width=10
            )
            item.insert(0, value)
            item.pack(side="right")
            fields[name] = item

        def create_wave():
            try:
                start = float(fields["X start"].get())
                end = float(fields["X end"].get())
                center = float(fields["Center Y"].get())
                amplitude = float(fields["Amplitude"].get())
                cycles = float(fields["Cycles"].get())
                count = int(fields["Number of points"].get())

                if end <= start:
                    raise ValueError("X end must be greater than X start.")

                if count < 3 or count > 500:
                    raise ValueError("Use between 3 and 500 points.")

                if start < self.x_min or end > self.x_max:
                    raise ValueError("Wave X range must stay inside the grid.")

                wave_points = []

                for i in range(count):
                    t = i / (count-1)
                    gx = start + (end-start)*t
                    gy = center + amplitude*math.sin(2*math.pi*cycles*t)

                    if gy < self.y_min or gy > self.y_max:
                        raise ValueError("Wave goes outside the grid. Reduce amplitude.")

                    wave_points.append(self.graph_to_image(gx, gy))

                self.points = wave_points
                self.refresh_point_list()
                self.draw_overlays()
                self.status.config(text="Wave generated.")
                window.destroy()

            except Exception as error:
                messagebox.showerror("Wave Generator", str(error))

        self.button(
            window, "Generate Wave", create_wave
        ).pack(fill="x", padx=15, pady=14)

    # ---------------- EQUATION GENERATOR ----------------

    def generate_equation(self):
        if not self.grid_is_valid():
            messagebox.showerror("Equation", "Set the grid corners first.")
            return

        if not self.get_ranges():
            return

        if len(self.points) < 2:
            messagebox.showerror("Equation", "Place at least two points first.")
            return

        graph_points = [
            self.image_to_graph(*point)
            for point in self.points
        ]

        graph_points.sort(key=lambda point: point[0])

        xs = [p[0] for p in graph_points]
        ys = [p[1] for p in graph_points]

        for i in range(1, len(xs)):
            if xs[i] <= xs[i-1]:
                messagebox.showerror(
                    "Equation",
                    "Two points have the same X coordinate. Move them apart."
                )
                return

        slopes = [
            (ys[i+1]-ys[i])/(xs[i+1]-xs[i])
            for i in range(len(xs)-1)
        ]

        base_slope = (slopes[0]+slopes[-1])/2
        knots = []
        coefficients = []

        for i in range(1, len(xs)-1):
            coefficient = (slopes[i]-slopes[i-1])/2
            knots.append(xs[i])
            coefficients.append(coefficient)

        intercept = ys[0]-base_slope*xs[0]

        for coefficient, knot in zip(coefficients, knots):
            intercept -= coefficient*abs(xs[0]-knot)

        def fmt(value):
            return f"{value:.6g}"

        parts = [fmt(intercept)]

        if base_slope >= 0:
            parts.append(f"+ {fmt(base_slope)}*x")
        else:
            parts.append(f"- {fmt(abs(base_slope))}*x")

        for coefficient, knot in zip(coefficients, knots):
            sign = "+" if coefficient >= 0 else "-"
            parts.append(
                f"{sign} {fmt(abs(coefficient))}*abs(x - ({fmt(knot)}))"
            )

        equation = "y = " + " ".join(parts)
        self.last_equation = equation

        result = tk.Toplevel(self.root)
        result.title("Generated Equation")
        result.geometry("650x420")
        result.configure(bg=PANEL)

        tk.Label(
            result,
            text="YOUR GRAPHWAR EQUATION",
            bg=PANEL,
            fg=ACCENT,
            font=("Arial", 14, "bold")
        ).pack(pady=12)

        text_box = tk.Text(
            result,
            bg="#0d0b13",
            fg=TEXT,
            insertbackground="white",
            relief="flat",
            wrap="word",
            font=("Consolas", 10)
        )
        text_box.pack(fill="both", expand=True, padx=12, pady=8)

        text_box.insert(tk.END, equation + "\n\n")
        text_box.insert(tk.END, "POINTS\n")

        for i, (x, y) in enumerate(graph_points):
            text_box.insert(
                tk.END,
                f"{i+1}: ({fmt(x)}, {fmt(y)})\n"
            )

        text_box.insert(tk.END, "\nSEGMENT SLOPES\n")

        for i, slope in enumerate(slopes):
            text_box.insert(tk.END, f"{i+1}: {fmt(slope)}\n")

    def copy_equation(self):
        if not self.last_equation:
            messagebox.showinfo("Copy Equation", "Generate an equation first.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_equation)
        self.root.update()
        self.status.config(text="Equation copied to clipboard.")

    # ---------------- AUTO DETECTION ----------------

    def detect_auto_targets(self):
        if self.original_image is None:
            messagebox.showerror("Auto Killer", "Take a screenshot first.")
            return

        if not self.grid_is_valid():
            messagebox.showerror("Auto Killer", "Calibrate your grid first.")
            return

        try:
            min_thickness = float(self.black_thickness_entry.get())

            if min_thickness < 1 or min_thickness > 20:
                raise ValueError("Minimum thickness must be between 1 and 20 pixels.")

        except Exception as error:
            messagebox.showerror("Black Danger Detection", str(error))
            return

        image = np.array(self.original_image.convert("RGB"))
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

        bx, by = self.grid_bottom_left
        tx, ty = self.grid_top_right

        left = max(0, int(bx))
        right = min(image.shape[1], int(tx))
        top = max(0, int(ty))
        bottom = min(image.shape[0], int(by))

        if right <= left or bottom <= top:
            messagebox.showerror("Auto Killer", "Invalid grid bounds.")
            return

        roi = hsv[top:bottom, left:right]

        color_mask = cv2.inRange(
            roi,
            np.array([0, 75, 65], dtype=np.uint8),
            np.array([179, 255, 255], dtype=np.uint8)
        )

        kernel = np.ones((3, 3), np.uint8)

        color_mask = cv2.morphologyEx(
            color_mask, cv2.MORPH_OPEN, kernel
        )

        color_mask = cv2.morphologyEx(
            color_mask, cv2.MORPH_CLOSE, kernel
        )

        contours, _ = cv2.findContours(
            color_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        detected_opponents = []

        for contour in contours:
            area = cv2.contourArea(contour)

            if area < 8 or area > 2500:
                continue

            perimeter = cv2.arcLength(contour, True)

            if perimeter <= 0:
                continue

            circularity = 4 * math.pi * area / (perimeter * perimeter)

            if circularity < 0.48:
                continue

            (cx, cy), radius = cv2.minEnclosingCircle(contour)

            if radius < 3 or radius > 35:
                continue

            detected_opponents.append(
                (float(cx+left), float(cy+top))
            )

        detected_opponents = [
            point for point in detected_opponents
            if all(
                math.hypot(
                    point[0]-teammate[0],
                    point[1]-teammate[1]
                ) > 18
                for teammate in self.teammates
            )
        ]

        self.opponents = self.remove_duplicate_points(
            self.opponents + detected_opponents,
            12
        )

        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        gray_roi = gray[top:bottom, left:right]

        dark_mask = cv2.inRange(
            gray_roi,
            np.array(0, dtype=np.uint8),
            np.array(65, dtype=np.uint8)
        )

        dark_mask = cv2.morphologyEx(
            dark_mask,
            cv2.MORPH_CLOSE,
            np.ones((3, 3), np.uint8)
        )

        distance = cv2.distanceTransform(
            dark_mask,
            cv2.DIST_L2,
            5
        )

        thick_core = np.where(
            distance >= min_thickness,
            255,
            0
        ).astype(np.uint8)

        clearance = cv2.dilate(
            thick_core,
            cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (11, 11)
            )
        )

        count, labels, stats, centroids = cv2.connectedComponentsWithStats(
            clearance,
            connectivity=8
        )

        cleaned = np.zeros_like(clearance)

        for i in range(1, count):
            area = stats[i, cv2.CC_STAT_AREA]

            if area >= 8:
                cleaned[labels == i] = 255

        self.obstacle_mask = np.zeros(
            (image.shape[0], image.shape[1]),
            dtype=np.uint8
        )

        self.obstacle_mask[top:bottom, left:right] = cleaned

        self.obstacle_contours, _ = cv2.findContours(
            cleaned,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        adjusted = []

        for contour in self.obstacle_contours:
            contour = contour.copy()
            contour[:, 0, 0] += left
            contour[:, 0, 1] += top
            adjusted.append(contour)

        self.obstacle_contours = adjusted
        self.attack_paths.clear()

        self.draw_overlays()

        self.status.config(
            text=f"Found {len(self.opponents)} opponents and "
                 f"{len(self.obstacle_contours)} thick black danger areas."
        )

        if not self.opponents:
            messagebox.showinfo(
                "Auto Killer",
                "No opponents were detected. You can mark them manually."
            )

        if not self.obstacle_contours:
            messagebox.showinfo(
                "Black Danger Detection",
                "No thick black danger marks were detected. "
                "Try lowering Min black thickness if needed."
            )

    def remove_duplicate_points(self, points, distance):
        result = []

        for point in points:
            if all(
                math.hypot(
                    point[0]-other[0],
                    point[1]-other[1]
                ) >= distance
                for other in result
            ):
                result.append(point)

        return result

    # ---------------- COLLISION DETECTION ----------------

    def point_blocked(self, x, y, padding=0):
        if self.original_image is None or not self.grid_is_valid():
            return True

        bx, by = self.grid_bottom_left
        tx, ty = self.grid_top_right

        if x < bx or x > tx or y < ty or y > by:
            return True

        if self.obstacle_mask is not None:
            ix = int(round(x))
            iy = int(round(y))

            ix = max(0, min(self.obstacle_mask.shape[1]-1, ix))
            iy = max(0, min(self.obstacle_mask.shape[0]-1, iy))

            if self.obstacle_mask[iy, ix] > 0:
                return True

        try:
            safety_radius = float(self.teammate_radius_entry.get())
        except Exception:
            safety_radius = 22

        for txp, typ in self.teammates:
            if math.hypot(x-txp, y-typ) < safety_radius + padding:
                return True

        return False

    def segment_blocked(self, a, b):
        distance = math.hypot(
            b[0]-a[0],
            b[1]-a[1]
        )

        samples = max(3, int(distance / 2))

        for i in range(samples+1):
            t = i / samples
            x = a[0] + (b[0]-a[0])*t
            y = a[1] + (b[1]-a[1])*t

            if self.point_blocked(x, y):
                return True

        return False

    # ---------------- PATHFINDING ----------------

    def find_safe_route(self, start, target):
        bx, by = self.grid_bottom_left
        tx, ty = self.grid_top_right

        step = max(3, int(self.path_grid_step))

        if self.point_blocked(*start) or self.point_blocked(*target):
            return None

        def to_cell(point):
            return (
                int(round((point[0]-bx)/step)),
                int(round((point[1]-ty)/step))
            )

        def to_pixel(cell):
            return (
                bx+cell[0]*step,
                ty+cell[1]*step
            )

        start_cell = to_cell(start)
        end_cell = to_cell(target)

        max_x = max(1, int((tx-bx)/step))
        max_y = max(1, int((by-ty)/step))

        def valid(cell):
            cx, cy = cell

            if cx < 0 or cy < 0 or cx > max_x or cy > max_y:
                return False

            px, py = to_pixel(cell)
            return not self.point_blocked(px, py)

        directions = [
            (1, 0, 1), (-1, 0, 1),
            (0, 1, 1), (0, -1, 1),
            (1, 1, 1.414), (1, -1, 1.414),
            (-1, 1, 1.414), (-1, -1, 1.414)
        ]

        frontier = [(0, start_cell)]
        came_from = {}
        cost_so_far = {start_cell: 0}

        found = False
        max_iterations = 50000
        iterations = 0

        while frontier and iterations < max_iterations:
            _, current = heapq.heappop(frontier)
            iterations += 1

            if current == end_cell:
                found = True
                break

            for dx, dy, move_cost in directions:
                neighbor = (
                    current[0]+dx,
                    current[1]+dy
                )

                if neighbor != end_cell and not valid(neighbor):
                    continue

                if dx != 0 and dy != 0:
                    side_a = (current[0]+dx, current[1])
                    side_b = (current[0], current[1]+dy)

                    if not valid(side_a) or not valid(side_b):
                        continue

                new_cost = cost_so_far[current] + move_cost

                if new_cost < cost_so_far.get(neighbor, float("inf")):
                    cost_so_far[neighbor] = new_cost

                    heuristic = math.hypot(
                        end_cell[0]-neighbor[0],
                        end_cell[1]-neighbor[1]
                    )

                    heapq.heappush(
                        frontier,
                        (new_cost+heuristic, neighbor)
                    )

                    came_from[neighbor] = current

        if not found:
            return None

        cells = [end_cell]
        current = end_cell

        while current != start_cell:
            current = came_from[current]
            cells.append(current)

        cells.reverse()

        # Build the unsimplified route.
        raw_route = [start]

        for cell in cells[1:-1]:
            raw_route.append(to_pixel(cell))

        raw_route.append(target)

        route = self.simplify_route(raw_route)

        # Verify simplified segments.
        safe_route = [route[0]]

        for point in route[1:]:
            if self.segment_blocked(safe_route[-1], point):
                # Use the original grid route instead of the
                # old undefined cells_to_pixels() function.
                raw_safe = [raw_route[0]]
                raw_is_safe = True

                for raw_point in raw_route[1:]:
                    if self.segment_blocked(raw_safe[-1], raw_point):
                        raw_is_safe = False
                        break

                    raw_safe.append(raw_point)

                if raw_is_safe:
                    return raw_safe

                return None

            safe_route.append(point)

        return safe_route

    def simplify_route(self, route):
        if len(route) <= 2:
            return route

        simplified = [route[0]]

        for i in range(1, len(route)-1):
            a = simplified[-1]
            b = route[i]
            c = route[i+1]

            ab = (b[0]-a[0], b[1]-a[1])
            bc = (c[0]-b[0], c[1]-b[1])

            cross = ab[0]*bc[1]-ab[1]*bc[0]

            if abs(cross) > 1:
                simplified.append(b)

        simplified.append(route[-1])
        return simplified

    def route_length(self, route):
        return sum(
            math.hypot(
                route[i+1][0]-route[i][0],
                route[i+1][1]-route[i][1]
            )
            for i in range(len(route)-1)
        )

    def interpolate_route(self, route, distance):
        if len(route) < 2:
            return route[0]

        remaining = distance

        for i in range(len(route)-1):
            a = route[i]
            b = route[i+1]

            length = math.hypot(
                b[0]-a[0],
                b[1]-a[1]
            )

            if remaining <= length:
                t = remaining/max(length, 0.0001)

                return (
                    a[0]+(b[0]-a[0])*t,
                    a[1]+(b[1]-a[1])*t
                )

            remaining -= length

        return route[-1]

    def resample_route(self, route, count=80):
        if not route:
            return []

        total = self.route_length(route)

        if total <= 0:
            return list(route)

        return [
            self.interpolate_route(route, total*i/count)
            for i in range(count+1)
        ]

    # ---------------- CLASSIC WAVE ----------------

    def create_wavy_route(self, route, amplitude, cycles):
        if len(route) < 2:
            return route

        total_length = self.route_length(route)

        if total_length < 2:
            return route

        count = max(50, min(400, int(total_length/3)))
        result = []

        for i in range(count+1):
            t = i/count
            distance = total_length*t

            center = self.interpolate_route(route, distance)

            before = self.interpolate_route(
                route, max(0, distance-2)
            )

            after = self.interpolate_route(
                route, min(total_length, distance+2)
            )

            dx = after[0]-before[0]
            dy = after[1]-before[1]
            length = math.hypot(dx, dy)

            if length < 0.001:
                result.append(center)
                continue

            px = -dy/length
            py = dx/length

            wave = (
                math.sin(2*math.pi*cycles*t)
                * amplitude
                * math.sin(math.pi*t)
            )

            candidate = (
                center[0]+px*wave,
                center[1]+py*wave
            )

            bx, by = self.grid_bottom_left
            tx, ty = self.grid_top_right

            candidate = (
                max(bx, min(tx, candidate[0])),
                max(ty, min(by, candidate[1]))
            )

            if self.point_blocked(*candidate, padding=3):
                candidate = center

            result.append(candidate)

        for i in range(len(result)-1):
            if self.segment_blocked(result[i], result[i+1]):
                return self.resample_route(route, count)

        return result

    # ---------------- PROFESSIONAL WAVE ----------------

    def create_professional_route(self, route, amplitude, cycles):
        if len(route) < 2:
            return route

        total_length = self.route_length(route)

        if total_length < 2:
            return route

        count = max(80, min(500, int(total_length/2.5)))
        result = []

        for i in range(count+1):
            t = i/count
            distance = total_length*t

            center = self.interpolate_route(route, distance)

            before = self.interpolate_route(
                route, max(0, distance-2)
            )

            after = self.interpolate_route(
                route, min(total_length, distance+2)
            )

            dx = after[0]-before[0]
            dy = after[1]-before[1]
            length = math.hypot(dx, dy)

            if length < 0.001:
                result.append(center)
                continue

            px = -dy/length
            py = dx/length

            wave1 = math.sin(2*math.pi*cycles*t)
            wave2 = math.cos(2*math.pi*cycles*1.5*t)
            wave3 = math.sin(2*math.pi*cycles*2.5*t)

            combined_wave = (
                wave1*0.60 +
                wave2*0.25 +
                wave3*0.15
            )

            envelope = math.sin(math.pi*t)
            offset = amplitude*envelope*combined_wave

            candidate = (
                center[0]+px*offset,
                center[1]+py*offset
            )

            bx, by = self.grid_bottom_left
            tx, ty = self.grid_top_right

            candidate = (
                max(bx, min(tx, candidate[0])),
                max(ty, min(by, candidate[1]))
            )

            if self.point_blocked(*candidate, padding=3):
                candidate = center

            result.append(candidate)

        for i in range(len(result)-1):
            if self.segment_blocked(result[i], result[i+1]):
                return self.resample_route(route, count)

        return result

    # ---------------- AUTO KILLER ----------------

    def calculate_auto_attacks(self):
        if not self.grid_is_valid():
            messagebox.showerror(
                "Auto Killer",
                "Calibrate your graph first."
            )
            return

        if not self.opponents:
            messagebox.showerror(
                "Auto Killer",
                "Mark opponents or detect them first."
            )
            return

        try:
            amplitude = abs(float(self.auto_wave_entry.get()))
            cycles = float(self.auto_cycles_entry.get())

            if amplitude > 150:
                raise ValueError("Amplitude must be 150 pixels or less.")

            if cycles <= 0 or cycles > 20:
                raise ValueError("Cycles must be between 0 and 20.")

        except Exception as error:
            messagebox.showerror("Auto Killer", str(error))
            return

        if self.points:
            start = self.points[-1]
        else:
            bx, by = self.grid_bottom_left
            tx, ty = self.grid_top_right
            start = (bx+20, (by+ty)/2)

        if self.point_blocked(*start):
            messagebox.showerror(
                "Auto Killer",
                "Your starting point is inside a danger area or teammate safety zone. "
                "Move your last point to a safe location."
            )
            return

        self.attack_paths = []
        failed = 0

        selected_style = self.auto_mode_var.get()

        for target in self.opponents:
            route = self.find_safe_route(start, target)

            if route is None:
                failed += 1
                continue

            if selected_style == "Professional":
                path = self.create_professional_route(
                    route,
                    amplitude,
                    cycles
                )
            else:
                path = self.create_wavy_route(
                    route,
                    amplitude,
                    cycles
                )

            unsafe = any(
                self.segment_blocked(path[i], path[i+1])
                for i in range(len(path)-1)
            )

            if unsafe:
                path = self.resample_route(route, 100)

                if any(
                    self.segment_blocked(path[i], path[i+1])
                    for i in range(len(path)-1)
                ):
                    failed += 1
                    continue

            self.attack_paths.append(path)

        self.draw_overlays()

        self.status.config(
            text=f"{selected_style}: {len(self.attack_paths)} safe paths. "
                 f"{failed} targets could not be reached. Display only."
        )

        if failed:
            messagebox.showwarning(
                "Auto Killer",
                f"{failed} target(s) could not be reached safely. "
                "Check the grid, black danger detection, and teammate positions."
            )

    def copy_auto_equations(self):
        if not self.attack_paths:
            messagebox.showinfo(
                "Auto Killer",
                "Calculate attack paths first."
            )
            return

        if not self.grid_is_valid():
            return

        if not self.get_ranges():
            return

        lines = []

        for index, path in enumerate(self.attack_paths, 1):
            graph_points = [
                self.image_to_graph(x, y)
                for x, y in path
            ]

            lines.append(f"ATTACK {index}")

            for x, y in graph_points:
                lines.append(f"({x:.4f}, {y:.4f})")

            lines.append("")

        result = "\n".join(lines)

        self.root.clipboard_clear()
        self.root.clipboard_append(result)
        self.root.update()

        self.status.config(text="Auto Killer coordinates copied!")

        messagebox.showinfo(
            "TIM3CRAFT",
            "All calculated attack path coordinates copied!"
        )

    def clear_auto_attacks(self):
        self.opponents.clear()
        self.attack_paths.clear()
        self.obstacle_mask = None
        self.obstacle_contours = []

        self.draw_overlays()
        self.status.config(text="Auto Killer overlays cleared.")


if __name__ == "__main__":
    root = tk.Tk()
    app = GraphWarBotter(root)
    root.mainloop()