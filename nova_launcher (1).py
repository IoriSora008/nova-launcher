"""
Nova Launcher 3.0 : un launcher Minecraft façon Lunar Client
-------------------------------------------------------------
- Pages : Jouer / Mods / Explorer / Paramètres
- Profils (PvP, Survie, Shaders, Vanilla + les tiens) avec leurs propres mods
- Explorer : cherche n'importe quel mod Fabric sur Modrinth et ajoute-le en un clic
- Mods téléchargés automatiquement (avec leurs dépendances) pour ta version
- Une instance séparée par version de Minecraft
- Mode hors-ligne ou connexion Microsoft

Installation :  pip install customtkinter minecraft-launcher-lib requests
Lancer       :  python nova_launcher.py
"""

import json
import os
import re
import tempfile
import io
import random
import tkinter as tk
from datetime import datetime, timezone
import shutil
import subprocess
import sys
import threading
import uuid
import webbrowser
from pathlib import Path

import customtkinter as ctk
import minecraft_launcher_lib as mll
import requests
from tkinter import filedialog, messagebox

try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False

APP_NAME = "Nova Launcher"
APP_VERSION = "3.2.0"
GITHUB_REPO = "TON_PSEUDO/nova-launcher"   # remplacé automatiquement à la publication
# les réglages vivent dans un dossier fixe (indispensable une fois transformé en .exe)
BASE = Path(os.getenv("APPDATA") or (Path.home() / ".config")) / "NovaLauncher"
BASE.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = BASE / "config.json"
REDIRECT_URI = "http://localhost/"
MODRINTH = "https://api.modrinth.com/v2"
HEADERS = {"User-Agent": "NovaLauncher/3.0 (launcher perso)"}

ACCENT = "#22c55e"
ACCENT_HOVER = "#16a34a"
BG = "#0d0f14"
SIDEBAR = "#090b0f"
CARD = "#151820"
LINE = "#232733"
BTN = "#2c2f3d"
BTN_HOVER = "#3a3e50"
MUTED = "#8b8ea3"

# slug Modrinth, nom, description, catégorie
MODS = [
    ("sodium", "Sodium", "Moteur de rendu ultra rapide : beaucoup plus de FPS.", "Performance"),
    ("lithium", "Lithium", "Optimise la logique du jeu et réduit les lags.", "Performance"),
    ("ferrite-core", "FerriteCore", "Réduit fortement l'utilisation de la mémoire.", "Performance"),
    ("entityculling", "Entity Culling", "Ne dessine pas ce que tu ne peux pas voir.", "Performance"),
    ("moreculling", "More Culling", "Encore plus de culling : moins de rendu inutile.", "Performance"),
    ("immediatelyfast", "ImmediatelyFast", "Accélère l'affichage de l'interface et du texte.", "Performance"),
    ("dynamic-fps", "Dynamic FPS", "Baisse les FPS quand la fenêtre est en arrière-plan.", "Performance"),
    ("krypton", "Krypton", "Optimise la pile réseau : moins de lag en serveur.", "Performance"),
    ("c2me-fabric", "C2ME", "Génération et chargement des chunks en parallèle.", "Performance"),
    ("sodium-extra", "Sodium Extra", "Compteur de FPS, coordonnées et options de rendu.", "HUD"),
    ("betterf3", "BetterF3", "Un écran F3 clair, coloré et configurable.", "HUD"),
    ("appleskin", "AppleSkin", "Affiche la faim et la saturation sur la barre de vie.", "HUD"),
    ("jade", "Jade", "Infos sur le bloc ou l'entité visé(e).", "HUD"),
    ("xaeros-minimap", "Xaero's Minimap", "Une minimap claire avec waypoints.", "HUD"),
    ("journeymap", "JourneyMap", "Minimap et carte du monde complète.", "HUD"),
    ("zoomify", "Zoomify", "Zoom façon OptiFine, très configurable.", "Utilitaire"),
    ("ok-zoomer", "Ok Zoomer", "Un autre zoom, avec défilement et cinématique.", "Utilitaire"),
    ("mouse-tweaks", "Mouse Tweaks", "Gestion de l'inventaire plus rapide à la souris.", "Utilitaire"),
    ("shulkerboxtooltip", "Shulker Box Tooltip", "Voir le contenu d'un shulker sans l'ouvrir.", "Utilitaire"),
    ("no-chat-reports", "No Chat Reports", "Désactive la signature et le report des messages.", "Utilitaire"),
    ("modmenu", "Mod Menu", "Liste et configure tes mods en jeu.", "Utilitaire"),
    ("iris", "Iris Shaders", "Support des shaders (compatible Sodium).", "Visuel"),
    ("continuity", "Continuity", "Textures connectées (verre, bibliothèques…).", "Visuel"),
    ("lambdynamiclights", "LambDynamicLights", "Lumière dynamique : une torche en main éclaire.", "Visuel"),
    ("skinlayers3d", "3D Skin Layers", "Donne du relief aux couches de skin.", "Visuel"),
    ("fallingleaves", "Falling Leaves", "Des feuilles tombent des arbres.", "Visuel"),
    ("capes", "Capes", "Affiche les capes de la communauté.", "Visuel"),
]
CATALOG = {m[0]: m for m in MODS}

BASE_PERF = ["sodium", "lithium", "ferrite-core", "entityculling"]
PRESETS = {
    "PvP": BASE_PERF + ["sodium-extra", "zoomify", "betterf3", "appleskin", "modmenu"],
    "Survie": BASE_PERF + ["sodium-extra", "xaeros-minimap", "appleskin", "jade", "mouse-tweaks", "zoomify", "modmenu"],
    "Shaders": BASE_PERF + ["iris", "sodium-extra", "continuity", "lambdynamiclights", "modmenu"],
    "Vanilla": [],
}


# ------------------------------------------------------------------ config
def default_config():
    return {
        "username": "Joueur",
        "version": "",
        "ram_gb": 4,
        "game_dir": str(mll.utils.get_minecraft_directory()),
        "show_snapshots": False,
        "profile": "PvP",
        "profiles": {n: {"mods": {s: s in lst for s in CATALOG}} for n, lst in PRESETS.items()},
        "custom_titles": {},       # mods ajoutés via Explorer : slug -> titre
        "ms_client_id": "",
        "ms_refresh_token": "",
        "extra_jvm": "",
    }


def load_config():
    cfg = default_config()
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            old_mods = data.pop("mods", None)          # ancien format (v2)
            cfg.update(data)
            if old_mods and "profiles" not in data:
                cfg["profiles"]["Personnalisé"] = {"mods": old_mods}
        except Exception:
            pass
    if not cfg["profiles"]:
        cfg["profiles"] = default_config()["profiles"]
    if cfg["profile"] not in cfg["profiles"]:
        cfg["profile"] = next(iter(cfg["profiles"]))
    return cfg


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def offline_uuid(name):
    return str(uuid.uuid3(uuid.NAMESPACE_OID, "OfflinePlayer:" + name))


# ------------------------------------------------------------ mises à jour
def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def fetch_latest():
    """Dernière release GitHub (la même source que le site)."""
    if GITHUB_REPO.startswith("TON_"):
        return None
    r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", headers=HEADERS, timeout=10)
    if r.status_code != 200:
        return None
    d = r.json()
    asset = next((a for a in d.get("assets", []) if a["name"].lower().endswith(".exe")), None)
    return {"version": d["tag_name"].lstrip("v"), "notes": d.get("body") or "",
            "url": asset["browser_download_url"] if asset else d["html_url"],
            "is_asset": bool(asset), "page": d["html_url"]}


def apply_update(url, progress):
    """Télécharge le nouvel .exe puis le remplace après la fermeture du launcher."""
    exe = Path(sys.executable)
    new = exe.with_name(exe.stem + ".new.exe")
    with requests.get(url, stream=True, headers=HEADERS, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0)) or 1
        done = 0
        with open(new, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                done += len(chunk)
                progress(done / total)
    bat = Path(tempfile.gettempdir()) / "nova_update.bat"
    bat.write_text(f'@echo off\r\nping 127.0.0.1 -n 4 >nul\r\nmove /y "{new}" "{exe}" >nul\r\n'
                   f'start "" "{exe}"\r\ndel "%~f0"\r\n')
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=0x08000000 | 0x00000008)


# --------------------------------------------------------------- Modrinth
def modrinth_versions(slug_or_id, mc_version):
    r = requests.get(
        f"{MODRINTH}/project/{slug_or_id}/version",
        params={"loaders": json.dumps(["fabric"]), "game_versions": json.dumps([mc_version])},
        headers=HEADERS, timeout=20,
    )
    if r.status_code != 200:
        return []
    vs = r.json()
    releases = [v for v in vs if v.get("version_type") == "release"]
    return releases or vs


def modrinth_search(query, mc_version, index="relevance"):
    facets = [["project_type:mod"], ["categories:fabric"]]
    if mc_version:
        facets.append([f"versions:{mc_version}"])
    r = requests.get(
        f"{MODRINTH}/search",
        params={"query": query, "facets": json.dumps(facets), "limit": 20, "index": index},
        headers=HEADERS, timeout=20,
    )
    r.raise_for_status()
    return r.json().get("hits", [])


def sync_mods(instance_dir: Path, cache_dir: Path, mc_version: str, enabled, names, log):
    """Télécharge les mods activés (+ dépendances) et nettoie ceux désactivés."""
    mods_dir = instance_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / mc_version
    cache.mkdir(parents=True, exist_ok=True)
    manifest = instance_dir / ".nova_managed.json"

    if manifest.exists():
        try:
            for name in json.loads(manifest.read_text()).get("files", []):
                (mods_dir / name).unlink(missing_ok=True)
        except Exception:
            pass

    managed, seen, missing = [], set(), []

    def resolve(ref, label):
        if ref in seen:
            return
        seen.add(ref)
        versions = modrinth_versions(ref, mc_version)
        if not versions:
            missing.append(label)
            return
        v = versions[0]
        files = v.get("files", [])
        f = next((x for x in files if x.get("primary")), files[0] if files else None)
        if not f:
            missing.append(label)
            return
        target = cache / f["filename"]
        if not target.exists():
            log(f"Téléchargement : {label}")
            data = requests.get(f["url"], headers=HEADERS, timeout=60)
            data.raise_for_status()
            target.write_bytes(data.content)
        shutil.copy2(target, mods_dir / f["filename"])
        managed.append(f["filename"])
        for dep in v.get("dependencies", []):
            if dep.get("dependency_type") == "required" and dep.get("project_id"):
                resolve(dep["project_id"], "dépendance")

    resolve("fabric-api", "Fabric API")
    for slug in enabled:
        try:
            resolve(slug, names.get(slug, slug))
        except Exception as e:
            missing.append(f"{names.get(slug, slug)} ({e})")

    manifest.write_text(json.dumps({"files": managed}), encoding="utf-8")
    return missing


# ===================================================================== UI
def fmt_downloads(n):
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.1f}k" if n >= 1e3 else str(n)


def rel_date(iso):
    try:
        d = (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    except Exception:
        return ""
    if d < 1:
        return "aujourd’hui"
    if d < 31:
        return f"il y a {d} j"
    return f"il y a {d // 30} mois" if d < 365 else f"il y a {d // 365} an(s)"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1020x660")
        self.minsize(940, 600)
        self.configure(fg_color=BG)

        self.cfg = load_config()
        self.ms_account = None
        self.busy = False
        self.progress_max = 1
        self.mod_vars = {}
        self.added_buttons = {}
        self.explored = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()

        self.pages = {
            "play": self._build_play(),
            "mods": self._build_mods(),
            "explore": self._build_explore(),
            "settings": self._build_settings(),
        }
        self.render_mods()
        self.show("play")

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.refresh_versions()
        self.check_updates()

    # --------------------------------------------------------- profils
    def profile(self):
        return self.cfg["profiles"][self.cfg["profile"]]

    def mod_names(self):
        names = {s: m[1] for s, m in CATALOG.items()}
        names.update(self.cfg["custom_titles"])
        return names

    def _save_mods(self):
        if self.mod_vars:
            self.profile()["mods"] = {k: v.get() for k, v in self.mod_vars.items()}
        save_config(self.cfg)

    def switch_profile(self, name):
        self._save_mods()
        self.cfg["profile"] = name
        self.menu_profile.set(name)
        self.render_mods()
        n = sum(1 for on in self.profile()["mods"].values() if on)
        self.set_status(f"Profil « {name} » : {n} mod(s) activé(s).")
        save_config(self.cfg)

    def _refresh_profile_menu(self):
        self.menu_profile.configure(values=list(self.cfg["profiles"]))
        self.menu_profile.set(self.cfg["profile"])

    def new_profile(self):
        name = ctk.CTkInputDialog(title="Nouveau profil", text="Nom du profil :").get_input()
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.cfg["profiles"]:
            messagebox.showinfo(APP_NAME, "Ce profil existe déjà.")
            return
        self._save_mods()
        self.cfg["profiles"][name] = {"mods": dict(self.profile()["mods"])}
        self._refresh_profile_menu()
        self.switch_profile(name)

    def delete_profile(self):
        if len(self.cfg["profiles"]) <= 1:
            messagebox.showinfo(APP_NAME, "Il faut garder au moins un profil.")
            return
        name = self.cfg["profile"]
        if not messagebox.askyesno(APP_NAME, f"Supprimer le profil « {name} » ?"):
            return
        del self.cfg["profiles"][name]
        self.cfg["profile"] = next(iter(self.cfg["profiles"]))
        self.mod_vars = {}
        self._refresh_profile_menu()
        self.switch_profile(self.cfg["profile"])

    # ------------------------------------------------------- navigation
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=76, corner_radius=0, fg_color=SIDEBAR)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)
        ctk.CTkLabel(sb, text="✦", font=ctk.CTkFont(size=28), text_color=ACCENT).pack(pady=(20, 16))
        self.nav = {}
        for key, icon in (("play", "🚀"), ("mods", "🧩"), ("explore", "🌐"), ("settings", "⚙")):
            b = ctk.CTkButton(sb, text=icon, width=52, height=52, corner_radius=14, fg_color="transparent",
                              hover_color=CARD, font=ctk.CTkFont(size=22), command=lambda k=key: self.show(k))
            if key == "settings":
                b.pack(side="bottom", pady=(4, 16))
            else:
                b.pack(pady=4)
            self.nav[key] = b
        ctk.CTkLabel(sb, text=f"v{APP_VERSION}", text_color=MUTED, font=ctk.CTkFont(size=10)).pack(side="bottom")

    def show(self, key):
        for k, p in self.pages.items():
            p.grid_forget()
            self.nav[k].configure(fg_color="transparent")
        self.pages[key].grid(row=0, column=1, sticky="nsew", padx=22, pady=18)
        self.nav[key].configure(fg_color=CARD)
        if key == "explore" and not self.explored:
            self.explored = True
            self.do_search()

    def play_label(self):
        v = self.var_version.get()
        v = "" if v.startswith("Chargement") else v
        mods = any(self.profile()["mods"].values())
        return f"LANCER LE JEU\nNova {v} · {'Fabric' if mods else 'Vanilla'}"

    def update_play_label(self):
        n = sum(1 for on in self.profile()["mods"].values() if on)
        self.lbl_prof.configure(text=self.cfg["profile"])
        self.lbl_prof_sub.configure(text=f"{n} mod(s) activé(s)")
        if not self.busy:
            self.btn_play.configure(text=self.play_label())

    # ------------------------------------------------------------ Jouer
    def _build_play(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.lbl_side_user = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=16), text_color="#c9cde0")
        self.lbl_side_user.pack(side="left")
        ctk.CTkLabel(top, text="● Prêt", text_color=ACCENT).pack(side="right")

        hero = tk.Canvas(f, bg="#0a0d18", highlightthickness=0, height=290)
        hero.grid(row=1, column=0, sticky="ew")
        rnd = random.Random(7)
        stars = [(rnd.random(), rnd.random(), rnd.choice((1, 2, 2, 3))) for _ in range(110)]

        self.var_version = ctk.StringVar(value=self.cfg["version"])
        self.btn_play = ctk.CTkButton(hero, text="", width=350, height=78, corner_radius=16, fg_color=ACCENT,
                                      hover_color=ACCENT_HOVER, font=ctk.CTkFont(size=21, weight="bold"),
                                      command=self.play)
        sel = ctk.CTkFrame(hero, fg_color="#10142a", corner_radius=14)
        self.cmb_version = ctk.CTkComboBox(sel, variable=self.var_version, values=[self.cfg["version"] or "Chargement…"],
                                           state="readonly", width=120, height=32, button_color=ACCENT,
                                           button_hover_color=ACCENT_HOVER)
        self.cmb_version.pack(side="left", padx=(10, 6), pady=8)
        self.menu_profile = ctk.CTkOptionMenu(sel, values=list(self.cfg["profiles"]), width=120, height=32,
                                              fg_color=BTN, button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                                              command=self.switch_profile)
        self.menu_profile.set(self.cfg["profile"])
        self.menu_profile.pack(side="left", padx=4)
        ctk.CTkButton(sel, text="+", width=32, height=32, fg_color=BTN, hover_color=BTN_HOVER,
                      command=self.new_profile).pack(side="left", padx=2)
        ctk.CTkButton(sel, text="🗑", width=32, height=32, fg_color=BTN, hover_color="#a33",
                      command=self.delete_profile).pack(side="left", padx=2)
        self.var_snap = ctk.BooleanVar(value=self.cfg["show_snapshots"])
        ctk.CTkCheckBox(sel, text="Snapshots", width=20, variable=self.var_snap, fg_color=ACCENT,
                        hover_color=ACCENT_HOVER, command=self.refresh_versions).pack(side="left", padx=(8, 12))
        gear = ctk.CTkButton(hero, text="⚙", width=36, height=36, fg_color="#10142a", hover_color=BTN_HOVER,
                             command=lambda: self.show("settings"))
        w_btn = hero.create_window(0, 0, window=self.btn_play)
        w_sel = hero.create_window(0, 0, window=sel)
        w_gear = hero.create_window(0, 0, window=gear)

        def draw(_=None):
            w, h = max(hero.winfo_width(), 400), max(hero.winfo_height(), 200)
            hero.delete("bg")
            for i in range(24):
                t = i / 23
                col = "#%02x%02x%02x" % (int(10 + 14 * t), int(13 + 12 * t), int(24 + 40 * t))
                hero.create_rectangle(0, h * i / 24, w, h * (i + 1) / 24 + 1, fill=col, outline="", tags="bg")
            for x, y, sz in stars:
                hero.create_oval(x * w, y * h, x * w + sz, y * h + sz, fill="#cfd6ff", outline="", tags="bg")
            px, py = w * 0.84, h * 0.30
            hero.create_oval(px - 60, py - 60, px + 60, py + 60, fill="#2a3a80", outline="#4b63c9", width=2, tags="bg")
            hero.create_oval(px - 40, py - 44, px + 6, py - 8, fill="#3a50a8", outline="", tags="bg")
            hero.create_oval(px - 100, py - 18, px + 100, py + 18, outline="#7c8cff", width=2, tags="bg")
            hero.create_oval(w * 0.07, h * 0.5, w * 0.07 + 46, h * 0.5 + 46, fill="#3d8f5a", outline="#58c07f", width=2, tags="bg")
            hero.tag_lower("bg")
            hero.coords(w_btn, w / 2, h * 0.38)
            hero.coords(w_sel, w / 2, h * 0.77)
            hero.coords(w_gear, w - 30, h - 30)
        hero.bind("<Configure>", draw)

        self.lbl_status = ctk.CTkLabel(f, text="Prêt.", text_color=MUTED, anchor="w")
        self.lbl_status.grid(row=2, column=0, sticky="ew", pady=(12, 4))
        self.bar = ctk.CTkProgressBar(f, progress_color=ACCENT, height=8)
        self.bar.set(0)
        self.bar.grid(row=3, column=0, sticky="ew")
        ctk.CTkLabel(f, text="Raccourcis", font=ctk.CTkFont(size=16, weight="bold")).grid(row=4, column=0, sticky="w", pady=(16, 8))

        cards = ctk.CTkFrame(f, fg_color="transparent")
        cards.grid(row=5, column=0, sticky="ew")
        cards.grid_columnconfigure((0, 1, 2), weight=1, uniform="c")
        small = ctk.CTkFont(size=11, weight="bold")

        c1 = ctk.CTkFrame(cards, fg_color=CARD, corner_radius=16)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(c1, text="PROFIL ACTIF", text_color=MUTED, font=small).pack(anchor="w", padx=16, pady=(14, 0))
        self.lbl_prof = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_prof.pack(anchor="w", padx=16)
        self.lbl_prof_sub = ctk.CTkLabel(c1, text="", text_color=MUTED)
        self.lbl_prof_sub.pack(anchor="w", padx=16)
        ctk.CTkButton(c1, text="Gérer les mods", height=32, fg_color=BTN, hover_color=BTN_HOVER,
                      command=lambda: self.show("mods")).pack(anchor="w", padx=16, pady=(8, 14))

        c2 = ctk.CTkFrame(cards, fg_color=CARD, corner_radius=16)
        c2.grid(row=0, column=1, sticky="nsew", padx=6)
        ctk.CTkLabel(c2, text="EXPLORER", text_color=MUTED, font=small).pack(anchor="w", padx=16, pady=(14, 0))
        ctk.CTkLabel(c2, text="Des milliers de mods", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=16)
        ctk.CTkLabel(c2, text="Installe-les en un clic", text_color=MUTED).pack(anchor="w", padx=16)
        ctk.CTkButton(c2, text="Ouvrir l’explorateur", height=32, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=lambda: self.show("explore")).pack(anchor="w", padx=16, pady=(8, 14))

        c3 = ctk.CTkFrame(cards, fg_color=CARD, corner_radius=16)
        c3.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(c3, text="COMPTE", text_color=MUTED, font=small).pack(anchor="w", padx=16, pady=(14, 4))
        self.var_user = ctk.StringVar(value=self.cfg["username"])
        ctk.CTkEntry(c3, textvariable=self.var_user, height=32, placeholder_text="Pseudo").pack(fill="x", padx=16)
        self.lbl_account = ctk.CTkLabel(c3, text="Mode hors-ligne", text_color=MUTED)
        self.lbl_account.pack(anchor="w", padx=16, pady=(4, 0))
        ctk.CTkButton(c3, text="Connexion Microsoft", height=30, fg_color=BTN, hover_color=BTN_HOVER,
                      command=self.microsoft_login).pack(anchor="w", padx=16, pady=(4, 14))

        self._update_side_user()
        self.update_play_label()
        self.var_version.trace_add("write", lambda *a: self.update_play_label())
        return f

    def _build_mods(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(f, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(head, text="Mods", font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="📂 Dossier mods", width=130, fg_color=BTN, hover_color=BTN_HOVER,
                      command=self.open_mods_folder).pack(side="right")
        self.lbl_mods_profile = ctk.CTkLabel(head, text="", text_color=ACCENT)
        self.lbl_mods_profile.pack(side="left", padx=14)

        self.mods_scroll = ctk.CTkScrollableFrame(f, fg_color="transparent")
        self.mods_scroll.grid(row=1, column=0, sticky="nsew")
        self.mods_scroll.grid_columnconfigure((0, 1), weight=1, uniform="m")

        ctk.CTkLabel(f, text="Les réglages ci-dessous s'appliquent au profil actif. Les mods sont téléchargés "
                             "au lancement ; ceux qui n'existent pas pour ta version sont ignorés.",
                     text_color=MUTED, wraplength=720, justify="left"
                     ).grid(row=2, column=0, sticky="w", pady=(10, 0))
        return f

    def render_mods(self):
        for w in self.mods_scroll.winfo_children():
            w.destroy()
        self.mod_vars = {}
        self.lbl_mods_profile.configure(text=f"Profil : {self.cfg['profile']}")
        self.update_play_label()
        state = self.profile()["mods"]

        cats = {}
        for slug, _n, _d, cat in MODS:
            cats.setdefault(cat, []).append(slug)
        if self.cfg["custom_titles"]:
            cats["Mes mods (Explorer)"] = list(self.cfg["custom_titles"])

        r = 0
        for cat, slugs in cats.items():
            ctk.CTkLabel(self.mods_scroll, text=cat.upper(), text_color=ACCENT,
                         font=ctk.CTkFont(size=12, weight="bold")
                         ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(10, 4))
            r += 1
            for i, slug in enumerate(slugs):
                custom = slug in self.cfg["custom_titles"]
                name = self.cfg["custom_titles"][slug] if custom else CATALOG[slug][1]
                desc = "Mod ajouté depuis Modrinth." if custom else CATALOG[slug][2]
                card = ctk.CTkFrame(self.mods_scroll, fg_color=CARD, corner_radius=14)
                card.grid(row=r + i // 2, column=i % 2, sticky="nsew", padx=4, pady=4)
                ctk.CTkLabel(card, text=name, font=ctk.CTkFont(size=15, weight="bold")
                             ).pack(anchor="w", padx=16, pady=(12, 0))
                ctk.CTkLabel(card, text=desc, text_color=MUTED, wraplength=290, justify="left"
                             ).pack(anchor="w", padx=16, pady=(2, 6))
                line = ctk.CTkFrame(card, fg_color="transparent")
                line.pack(fill="x", padx=16, pady=(0, 12))
                var = ctk.BooleanVar(value=bool(state.get(slug, False)))
                self.mod_vars[slug] = var
                ctk.CTkSwitch(line, text="Activé", variable=var, progress_color=ACCENT,
                              command=self._save_mods).pack(side="left")
                if custom:
                    ctk.CTkButton(line, text="Retirer", width=64, height=24, fg_color=BTN, hover_color="#a33",
                                  command=lambda s=slug: self.remove_custom(s)).pack(side="right")
            r += (len(slugs) + 1) // 2

    def remove_custom(self, slug):
        self._save_mods()
        self.cfg["custom_titles"].pop(slug, None)
        for p in self.cfg["profiles"].values():
            p["mods"].pop(slug, None)
        save_config(self.cfg)
        self.render_mods()
        if slug in self.added_buttons:
            b = self.added_buttons.pop(slug)
            try:
                b.configure(text="Ajouter", state="normal", fg_color=ACCENT)
            except Exception:
                pass

    def instance_dir(self):
        v = self.var_version.get() or "default"
        return Path(self.cfg["game_dir"]) / "nova_instances" / v

    def open_mods_folder(self):
        d = self.instance_dir() / "mods"
        d.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(d)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(d)])
        else:
            subprocess.Popen(["xdg-open", str(d)])

    # ---------------------------------------------------------- Explorer
    def _build_explore(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)
        bar = ctk.CTkFrame(f, fg_color=CARD, corner_radius=14)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        bar.grid_columnconfigure(0, weight=1)
        self.var_search = ctk.StringVar()
        entry = ctk.CTkEntry(bar, textvariable=self.var_search, height=46, border_width=0, fg_color=CARD,
                             placeholder_text="🔍  Rechercher parmi des milliers de mods Fabric (Modrinth)…")
        entry.grid(row=0, column=0, sticky="ew", padx=(10, 6))
        entry.bind("<Return>", lambda e: self.do_search())
        self.var_sort = ctk.StringVar(value="Popularité")
        ctk.CTkOptionMenu(bar, values=["Popularité", "Pertinence", "Récents"], variable=self.var_sort, width=130,
                          height=34, fg_color=BTN, button_color=BTN, button_hover_color=BTN_HOVER,
                          command=lambda _: self.do_search()).grid(row=0, column=1, padx=(0, 10))
        self.results = ctk.CTkScrollableFrame(f, fg_color="transparent")
        self.results.grid(row=1, column=0, sticky="nsew")
        self.results.grid_columnconfigure(0, weight=1)
        self.lbl_search = ctk.CTkLabel(f, text="", text_color=MUTED, anchor="w")
        self.lbl_search.grid(row=2, column=0, sticky="w", pady=(8, 0))
        return f

    def do_search(self):
        q = self.var_search.get().strip()
        ver = self.var_version.get()
        ver = "" if ver.startswith("Chargement") else ver
        index = {"Popularité": "downloads", "Pertinence": "relevance", "Récents": "updated"}[self.var_sort.get()]
        self.lbl_search.configure(text="Recherche en cours…")

        def work():
            try:
                hits = modrinth_search(q, ver, index)
                self.after(0, lambda: self.show_results(hits, ver))
            except Exception as e:
                self.after(0, lambda: self.lbl_search.configure(text=f"Erreur de recherche : {e}"))
        threading.Thread(target=work, daemon=True).start()

    def load_icon(self, url, label):
        if not (HAS_PIL and url):
            return

        def work():
            try:
                img = Image.open(io.BytesIO(requests.get(url, headers=HEADERS, timeout=10).content)).convert("RGBA").resize((56, 56))

                def apply():
                    try:
                        ci = ctk.CTkImage(light_image=img, dark_image=img, size=(56, 56))
                        label.configure(image=ci, text="")
                        label.image = ci
                    except Exception:
                        pass
                self.after(0, apply)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def show_results(self, hits, ver):
        for w in self.results.winfo_children():
            w.destroy()
        self.added_buttons = {}
        self.lbl_search.configure(text=(f"{len(hits)} résultat(s) · Fabric" + (f" {ver}" if ver else "")) if hits
                                  else "Aucun résultat pour cette version. Essaie un autre mot-clé.")
        for i, h in enumerate(hits):
            slug, title = h["slug"], h["title"]
            row = ctk.CTkFrame(self.results, fg_color="transparent")
            row.grid(row=i * 2, column=0, sticky="ew")
            row.grid_columnconfigure(1, weight=1)
            icon = ctk.CTkLabel(row, text=title[:1].upper(), width=56, height=56, fg_color=CARD, corner_radius=12,
                                font=ctk.CTkFont(size=22, weight="bold"))
            icon.grid(row=0, column=0, padx=(4, 14), pady=12)
            self.load_icon(h.get("icon_url"), icon)
            mid = ctk.CTkFrame(row, fg_color="transparent")
            mid.grid(row=0, column=1, sticky="w")
            ctk.CTkLabel(mid, text=title, font=ctk.CTkFont(size=16, weight="bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(mid, text=(h.get("description") or "")[:110], text_color="#b6bacb", anchor="w",
                         justify="left", wraplength=380).pack(anchor="w")
            tags = [h.get("author", ""), "Fabric"] + [c.capitalize() for c in h.get("categories", [])[:2] if c != "fabric"]
            ctk.CTkLabel(mid, text="  •  ".join(t for t in tags if t), text_color=MUTED,
                         font=ctk.CTkFont(size=12), anchor="w").pack(anchor="w", pady=(2, 0))
            right = ctk.CTkFrame(row, fg_color="transparent")
            right.grid(row=0, column=2, padx=8)
            ctk.CTkLabel(right, text=f"⬇ {fmt_downloads(h.get('downloads', 0))}   🕐 {rel_date(h.get('date_modified', ''))}",
                         text_color="#b6bacb", font=ctk.CTkFont(size=12)).pack(anchor="e")
            btns = ctk.CTkFrame(right, fg_color="transparent")
            btns.pack(anchor="e", pady=(6, 0))
            ctk.CTkButton(btns, text="👁 Voir", width=76, height=34, fg_color=BTN, hover_color=BTN_HOVER,
                          command=lambda s=slug: webbrowser.open(f"https://modrinth.com/mod/{s}")).pack(side="left", padx=(0, 6))
            already = self.profile()["mods"].get(slug, False)
            btn = ctk.CTkButton(btns, text="Installé ✓" if already else "⬇ Installer", width=104, height=34,
                                fg_color="#12301f", hover_color="#1a4a2e", text_color="#4ade80",
                                state="disabled" if already else "normal")
            btn.configure(command=lambda s=slug, t=title, b=btn: self.add_mod(s, t, b))
            btn.pack(side="left")
            if already:
                self.added_buttons[slug] = btn
            ctk.CTkFrame(self.results, height=1, fg_color=LINE).grid(row=i * 2 + 1, column=0, sticky="ew")

    def add_mod(self, slug, title, btn):
        self._save_mods()
        if slug not in CATALOG:
            self.cfg["custom_titles"][slug] = title
        self.profile()["mods"][slug] = True
        save_config(self.cfg)
        self.render_mods()
        btn.configure(text="Installé ✓", state="disabled")
        self.added_buttons[slug] = btn
        self.set_status(f"{title} ajouté au profil « {self.cfg['profile']} ».")

    def _build_settings(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(f, text="Paramètres", font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w", pady=(0, 14))

        card = ctk.CTkFrame(f, fg_color=CARD, corner_radius=14)
        card.pack(fill="x")

        ctk.CTkLabel(card, text="Mémoire allouée (RAM)", text_color=MUTED).pack(anchor="w", padx=18, pady=(16, 0))
        r = ctk.CTkFrame(card, fg_color="transparent")
        r.pack(fill="x", padx=18, pady=(4, 12))
        self.var_ram = ctk.IntVar(value=self.cfg["ram_gb"])
        self.lbl_ram = ctk.CTkLabel(r, text=f"{self.cfg['ram_gb']} Go", width=60)
        ctk.CTkSlider(r, from_=1, to=16, number_of_steps=15, variable=self.var_ram, progress_color=ACCENT,
                      button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                      command=lambda v: self.lbl_ram.configure(text=f"{int(v)} Go")).pack(side="left", fill="x", expand=True)
        self.lbl_ram.pack(side="left", padx=(10, 0))

        ctk.CTkLabel(card, text="Dossier du jeu", text_color=MUTED).pack(anchor="w", padx=18)
        r = ctk.CTkFrame(card, fg_color="transparent")
        r.pack(fill="x", padx=18, pady=(4, 12))
        self.var_dir = ctk.StringVar(value=self.cfg["game_dir"])
        ctk.CTkEntry(r, textvariable=self.var_dir, height=34).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r, text="…", width=40, height=34, fg_color=BTN, hover_color=BTN_HOVER,
                      command=self.pick_dir).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(card, text="Arguments Java supplémentaires (optionnel)", text_color=MUTED).pack(anchor="w", padx=18)
        self.var_jvm = ctk.StringVar(value=self.cfg["extra_jvm"])
        ctk.CTkEntry(card, textvariable=self.var_jvm, height=34).pack(fill="x", padx=18, pady=(4, 16))

        ctk.CTkButton(f, text="Enregistrer", fg_color=ACCENT, hover_color=ACCENT_HOVER, width=140,
                      command=lambda: (self.persist(), self.set_status("Paramètres enregistrés."))
                      ).pack(anchor="w", pady=14)
        return f

    def pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_dir.get())
        if d:
            self.var_dir.set(d)

    # ----------------------------------------------------------- helpers
    def persist(self):
        self.cfg.update({
            "username": self.var_user.get().strip() or "Joueur",
            "version": self.var_version.get(),
            "ram_gb": int(self.var_ram.get()),
            "game_dir": self.var_dir.get(),
            "show_snapshots": self.var_snap.get(),
            "extra_jvm": self.var_jvm.get(),
        })
        self._save_mods()

    def _close(self):
        try:
            self.persist()
        except Exception:
            pass
        self.destroy()

    def set_status(self, text):
        self.after(0, lambda: self.lbl_status.configure(text=text))

    def set_max(self, m):
        self.progress_max = max(m, 1)
        self.after(0, lambda: self.bar.set(0))

    def set_progress(self, v):
        self.after(0, lambda: self.bar.set(min(v / self.progress_max, 1)))

    def set_busy(self, busy):
        self.busy = busy
        self.after(0, lambda: self.btn_play.configure(state="disabled" if busy else "normal",
                                                      text="EN COURS…" if busy else self.play_label()))

    def _update_side_user(self):
        self.lbl_side_user.configure(text=f"Bienvenue, Astronaute  ·  {self.var_user.get() or 'Joueur'}")

    # ------------------------------------------------------- mise à jour
    def check_updates(self):
        def work():
            try:
                info = fetch_latest()
            except Exception:
                return
            if info and vtuple(info["version"]) > vtuple(APP_VERSION):
                self.after(0, lambda: self.prompt_update(info))
        threading.Thread(target=work, daemon=True).start()

    def prompt_update(self, info):
        notes = info["notes"].strip()[:400]
        msg = (f"Nova Launcher {info['version']} est disponible (tu as la {APP_VERSION}).\n\n"
               f"{notes}\n\nMettre à jour maintenant ?")
        if not messagebox.askyesno("Mise à jour disponible", msg):
            return
        if not (getattr(sys, "frozen", False) and info["is_asset"]):
            webbrowser.open(info["page"])      # lancé depuis le .py : on ouvre la page de téléchargement
            return
        self.set_busy(True)
        self.set_max(1)

        def work():
            try:
                self.set_status("Téléchargement de la mise à jour…")
                apply_update(info["url"], self.set_progress)
                self.after(0, self.destroy)
            except Exception as e:
                self.set_busy(False)
                self.set_status(f"Mise à jour impossible : {e}")
        threading.Thread(target=work, daemon=True).start()

    # ----------------------------------------------------------- versions
    def refresh_versions(self):
        def work():
            try:
                allv = mll.utils.get_version_list()
            except Exception as e:
                self.set_status(f"Versions indisponibles : {e}")
                return
            types = {"release"} | ({"snapshot"} if self.var_snap.get() else set())
            ids = [v["id"] for v in allv if v["type"] in types]

            def apply():
                self.cmb_version.configure(values=ids)
                if self.var_version.get() not in ids and ids:
                    self.var_version.set(ids[0])
            self.after(0, apply)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------- connexion Microsoft
    def microsoft_login(self):
        if not self.cfg.get("ms_client_id", "").strip():
            cid = ctk.CTkInputDialog(
                title="Connexion Microsoft",
                text="Entre ton ID d'application Azure (voir le README).\n"
                     f"URI de redirection : {REDIRECT_URI}").get_input()
            if not cid:
                return
            self.cfg["ms_client_id"] = cid.strip()
            save_config(self.cfg)
        try:
            url, state, verifier = mll.microsoft_account.get_secure_login_data(
                self.cfg["ms_client_id"], REDIRECT_URI)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Impossible de préparer la connexion :\n{e}")
            return
        webbrowser.open(url)
        pasted = ctk.CTkInputDialog(
            title="Connexion Microsoft",
            text="Connecte-toi dans le navigateur. La page finale affichera une erreur : c'est normal.\n"
                 "Copie l'URL complète de la barre d'adresse et colle-la ici :").get_input()
        if not pasted:
            return

        def work():
            try:
                self.set_status("Connexion Microsoft…")
                code = mll.microsoft_account.parse_auth_code_url(pasted.strip(), state)
                acc = mll.microsoft_account.complete_login(
                    self.cfg["ms_client_id"], None, REDIRECT_URI, code, verifier)
                self.ms_account = acc
                self.cfg["ms_refresh_token"] = acc.get("refresh_token", "")
                save_config(self.cfg)
                self._after_login(acc["name"])
                self.set_status("Connecté.")
            except Exception as e:
                self.set_status("Échec de la connexion.")
                self.after(0, lambda: messagebox.showerror(APP_NAME, str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _after_login(self, name):
        def ui():
            self.var_user.set(name)
            self.lbl_account.configure(text="Connecté (Microsoft)")
            self._update_side_user()
        self.after(0, ui)

    def _try_refresh_login(self):
        if self.ms_account or not self.cfg.get("ms_refresh_token") or not self.cfg.get("ms_client_id"):
            return
        try:
            self.ms_account = mll.microsoft_account.complete_refresh(
                self.cfg["ms_client_id"], None, REDIRECT_URI, self.cfg["ms_refresh_token"])
            self.cfg["ms_refresh_token"] = self.ms_account.get("refresh_token", "")
            save_config(self.cfg)
            self._after_login(self.ms_account["name"])
        except Exception:
            self.ms_account = None

    # --------------------------------------------------------------- jouer
    def play(self):
        if self.busy:
            return
        v = self.var_version.get()
        if not v or v.startswith("Chargement"):
            messagebox.showwarning(APP_NAME, "Choisis une version.")
            return
        self.persist()
        self._update_side_user()
        self.set_busy(True)
        threading.Thread(target=self._play_thread, daemon=True).start()

    def _play_thread(self):
        try:
            cfg = self.cfg
            mc_dir = cfg["game_dir"]
            version = cfg["version"]
            Path(mc_dir).mkdir(parents=True, exist_ok=True)
            enabled = [s for s, on in self.profile()["mods"].items() if on]
            names = self.mod_names()
            use_fabric = bool(enabled) and mll.fabric.is_minecraft_version_supported(version)

            cb = {
                "setStatus": lambda t: self.set_status(t),
                "setProgress": lambda v: self.set_progress(v),
                "setMax": lambda m: self.set_max(m),
            }

            instance = Path(mc_dir) / "nova_instances" / version
            instance.mkdir(parents=True, exist_ok=True)

            if use_fabric:
                self.set_status("Installation de Fabric…")
                mll.fabric.install_fabric(version, mc_dir, callback=cb)
                launch_id = f"fabric-loader-{mll.fabric.get_latest_loader_version()}-{version}"
                self.set_status("Préparation des mods…")
                missing = sync_mods(instance, Path(mc_dir) / "nova_cache", version, enabled, names, self.set_status)
                if missing:
                    self.set_status("Indisponibles pour cette version : " + ", ".join(missing[:4]))
            else:
                self.set_status(f"Installation de Minecraft {version}…")
                mll.install.install_minecraft_version(version, mc_dir, callback=cb)
                launch_id = version
                if enabled:
                    self.set_status("Fabric indisponible pour cette version : lancement sans mods.")
                else:
                    # profil sans mods : retire les mods gérés pour un jeu vanilla propre
                    sync_mods_clean(instance)

            self._try_refresh_login()
            if self.ms_account:
                opts = {"username": self.ms_account["name"], "uuid": self.ms_account["id"],
                        "token": self.ms_account["access_token"]}
            else:
                n = cfg["username"]
                opts = {"username": n, "uuid": offline_uuid(n), "token": ""}

            jvm = [f"-Xmx{cfg['ram_gb']}G", f"-Xms{max(1, cfg['ram_gb'] // 2)}G"]
            jvm += cfg["extra_jvm"].split()
            opts.update({"jvmArguments": jvm, "launcherName": APP_NAME,
                         "launcherVersion": APP_VERSION, "gameDirectory": str(instance)})

            command = mll.command.get_minecraft_command(launch_id, mc_dir, opts)
            self.set_progress(0)
            kw = {"cwd": str(instance)}
            if sys.platform == "win32":
                kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(command, **kw)
            self.set_status("Minecraft est lancé. Bon jeu !")
            self.set_busy(False)
            proc.wait()
            self.set_status("Minecraft fermé.")
        except Exception as e:
            self.set_status("Erreur.")
            self.set_busy(False)
            self.after(0, lambda: messagebox.showerror(APP_NAME, f"{type(e).__name__}: {e}"))


def sync_mods_clean(instance_dir: Path):
    """Supprime les mods installés par le launcher (jamais ceux ajoutés à la main)."""
    manifest = instance_dir / ".nova_managed.json"
    if manifest.exists():
        try:
            for name in json.loads(manifest.read_text()).get("files", []):
                (instance_dir / "mods" / name).unlink(missing_ok=True)
            manifest.write_text(json.dumps({"files": []}), encoding="utf-8")
        except Exception:
            pass


if __name__ == "__main__":
    App().mainloop()
