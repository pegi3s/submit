import streamlit as st
import os
import json
import subprocess
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
import re
import socket
import configparser
import shlex
import requests
import urllib.request
import urllib.parse
import ssl
from streamlit_scroll_to_top import scroll_to_here

# ----------------------------
# CONFIG
# ----------------------------
BASE_PATH = "/data"
DB_FILE = os.path.join("/submit_history", "projects_history.json")

os.makedirs(BASE_PATH, exist_ok=True)

config = configparser.ConfigParser()
# Try reading from /opt/ first (container) then fallback to local directory
config.read(["/opt/.config.ini", ".config.ini"])

# GitHub
GITHUB_USER = config.get("GitHub", "user", fallback=None)
GITHUB_TOKEN = config.get("GitHub", "token", fallback=None)
GITHUB_EMAIL = config.get("GitHub", "email", fallback=None)
GITHUB_REPO = config.get("GitHub", "repo", fallback=None)
GITHUB_REPO_OWNER = config.get("GitHub", "repo_owner", fallback="pegi3s")
GITHUB_BRANCH = config.get("GitHub", "branch", fallback="master")

# DockerHub
docker_user = config.get("DockerHub", "user", fallback=None)
docker_token = config.get("DockerHub", "token", fallback=None)
DOCKERHUB_ORG = config.get("DockerHub", "org", fallback="pegi3s")

# Remote
REMOTE_HOST = config.get("Remote", "host", fallback=None)
REMOTE_USER = config.get("Remote", "username", fallback=None)
REMOTE_PASS = config.get("Remote", "password", fallback=None)
REMOTE_DIR = config.get("Remote", "dir", fallback=None)

# BDIP Tools
BDIP_RESULTS_PATH = config.get("BDIPTools", "results_path", fallback=None)
BDIP_CONFIG_PATH = config.get("BDIPTools", "config_path", fallback=None)
BDIP_DOCKERFILES_PATH = config.get("Dockerfiles", "path", fallback=None)
BDIP_HOST_DOCKER_GROUP = config.get("BDIPTools", "docker_group", fallback=None)
BDIP_HOST_USER_ID = config.get("BDIPTools", "host_user_id", fallback=None)
BDIP_HOST_USER_GROUP = config.get("BDIPTools", "host_user_group", fallback=None)

# ----------------------------
# SESSION INIT
# ----------------------------
if "current_page" not in st.session_state:
    st.session_state.current_page = "Home"

if "active_project" not in st.session_state:
    st.session_state.active_project = None

if "open_manager" not in st.session_state:
    st.session_state.open_manager = False

if "docker_done" not in st.session_state:
    st.session_state.docker_done = False

if "github_done" not in st.session_state:
    st.session_state.github_done = False

if 'scroll_to_top' not in st.session_state:
    st.session_state.scroll_to_top = False

if "new_version_form" not in st.session_state:

    st.session_state.new_version_form = {

        # navigation
        "step": 1,

        # project
        "project": "",
        "manual_project": "",

        # version
        "base": "",
        "version": "",
        "use_detected_version": "Yes",

        # validation
        "version_exists": False,

        # github/docker
        "github_done": False,
        "docker_done": False,

        # logs
        "logs": "",
    }

form = st.session_state.new_version_form

if st.session_state.scroll_to_top:
    scroll_to_here(0, key='top')

    st.session_state.scroll_to_top = False

def scroll():
    st.session_state.scroll_to_top = True

# ----------------------------
# NAVIGATION
# ----------------------------
def change_page(name):
    st.session_state.current_page = name
    st.query_params.clear()
    scroll()
    st.rerun()

def go_to_step(step_number):
    form = st.session_state.new_version_form
    form["step"] = step_number
    scroll()
    st.rerun()

def render_navigation(
    back_step=None,
    next_step=None,
    next_disabled=False,
    next_label="Next →",
    back_label="← Back",
    next_key=None
):
    col0, col1, col2 = st.columns([7,1,1])

    with col1:
        if back_step is not None:
            if st.button(
                back_label,
                use_container_width=True
            ):
                go_to_step(back_step)

    with col2:
        if next_step is not None:
            if st.button(
                next_label,
                use_container_width=True,
                disabled=next_disabled,
                key=next_key
            ):
                go_to_step(next_step)

def go_to_new_image_step(step_number):
    st.session_state.new_image_step = step_number
    scroll()
    st.rerun()

def render_new_image_navigation(
    back_step=None,
    next_step=None,
    next_disabled=False,
    next_label="Next →",
    back_label="← Back",
    next_key=None
):
    col0, col1, col2 = st.columns([7,1,1])

    with col1:
        if back_step is not None:
            if st.button(
                back_label,
                use_container_width=True
            ):
                go_to_new_image_step(back_step)

    with col2:
        if next_step is not None:
            if st.button(
                next_label,
                use_container_width=True,
                disabled=next_disabled,
                key=next_key
            ):
                go_to_new_image_step(next_step)

def reset_new_version():

    st.session_state.new_version_form = {

        "step": 1,

        "project": "",
        "manual_project": "",

        "base": "",
        "version": "",
        "use_detected_version": "Yes",

        "version_exists": False,

        "github_done": False,
        "docker_done": False,

        "logs": "",
    }

def reset_new_image():
    for key in [
        "new_image_step",
        "project_type",
        "project",
        "manual_project",
        "base",
        "ontology_has_suggestions",
        "github_done",
        "docker_done",
        "test_data_done",
        "logs",
        "log_box",
    ]:
        st.session_state.pop(key, None)

def append_log(message, level="INFO"):

    form = st.session_state.new_version_form

    prefix = {
        "INFO":    "[INFO]    ",
        "SUCCESS": "[SUCCESS] ",
        "WARNING": "[WARNING] ",
        "ERROR":   "[ERROR]   ",
        "STEP":    "[STEP]    ",
    }.get(level, "[INFO] ")

    form["logs"] += f"{prefix}{message}\n"

    if "log_box" in st.session_state:
        st.session_state.log_box.code(form["logs"])

@st.cache_data(ttl=3600)
def get_remote_metadata():
    """Fetch global metadata.json from the repository."""
    try:
        url = "https://raw.githubusercontent.com/pegi3s/dockerfiles/master/metadata/metadata.json"
        context = ssl._create_unverified_context()

        with urllib.request.urlopen(url, context=context) as response:
            data = json.loads(response.read().decode())
            return data

    except Exception as e:
        print(f"Error fetching metadata: {e}")
        return []

def get_project_metadata(project_name):
    """Retrieve metadata for a specific project."""
    data = get_remote_metadata()

    if isinstance(data, list):
        for item in data:
            if item.get("name") == project_name:
                return item

    elif isinstance(data, dict):
        return data.get(project_name)

    return {}

def get_terminal_terms(ontology, relations):

    children = set(relations.keys())
    parents = set(relations.values())

    leaf_terms = children - parents

    return sorted(leaf_terms)

def get_ontology_path(term_id, terms_map, relations):
    """Builds the 'Parent > Child' path recursively for intuitive visualization."""
    if not term_id:
        return ""
    path = [terms_map.get(term_id, term_id)]
    current_id = term_id

    # 10-level limit to prevent infinite recursion in case of errors in the .obo file
    for _ in range(10):
        parent_id = relations.get(current_id)
        if not parent_id or parent_id not in terms_map:
            break
        path.insert(0, terms_map[parent_id])
        current_id = parent_id

    return " > ".join(path)

@st.dialog("⚠️ Unsaved Submission")
def show_unsaved_submission_dialog():

    st.warning(
        "The current submission process will be lost if you leave this page."
    )

    st.markdown(
        """
        <div style="
            font-size:16px;
            margin-top:10px;
            margin-bottom:20px;
            color:#374151;
        ">
            Are you sure you want to leave this page?
        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2 = st.columns(2)

    # ============================
    # CONFIRM LEAVE
    # ============================
    with col1:

        if st.button(
            "✅ Yes, leave page",
            use_container_width=True
        ):

            reset_new_version()

            st.session_state["show_submission_dialog"] = False

            change_page("Home")

            st.rerun()

    # ============================
    # CANCEL
    # ============================
    with col2:

        if st.button(
            "❌ Cancel",
            use_container_width=True
        ):

            st.session_state["show_submission_dialog"] = False

            st.rerun()

@st.dialog("⚠️ Unsaved Submission")
def show_unsaved_new_image_dialog():

    st.warning(
        "The current submission process will be lost if you leave this page."
    )

    st.markdown(
        """
        <div style="
            font-size:16px;
            margin-top:10px;
            margin-bottom:20px;
            color:#374151;
        ">
            Are you sure you want to leave this page?
        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "✅ Yes, leave page",
            use_container_width=True,
            key="leave_new_image"
        ):

            reset_new_image()

            st.session_state["show_new_image_dialog"] = False

            change_page("Home")

            st.rerun()

    with col2:

        if st.button(
            "❌ Cancel",
            use_container_width=True,
            key="cancel_new_image_leave"
        ):

            st.session_state["show_new_image_dialog"] = False

            st.rerun()

@st.dialog("Edit README")
def edit_readme_dialog(readme_path):

    content = readme_path.read_text(encoding="utf-8")

    edited = st.text_area(
        "README",
        value=content,
        height=500
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("💾 Save README", use_container_width=True):

            readme_path.write_text(
                edited,
                encoding="utf-8"
            )

            st.success("README updated")

            st.rerun()

    with col2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()
            
@st.dialog("Edit Metadata")
def edit_metadata_dialog(metadata_path):

    content = metadata_path.read_text(encoding="utf-8")

    edited = st.text_area(
        "metadata.json",
        value=content,
        height=500
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "💾 Save Metadata",
            use_container_width=True
        ):

            try:
                parsed = json.loads(edited)

                metadata_path.write_text(
                    json.dumps(
                        parsed,
                        indent=4,
                        ensure_ascii=False
                    ),
                    encoding="utf-8"
                )

                st.success("Metadata updated")
                st.rerun()

            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")

    with col2:
        if st.button(
            "Cancel",
            use_container_width=True
        ):
            st.rerun()

@st.dialog("Edit Ontology Terms")
def edit_ontology_dialog(path, ontology, ontology_ids, relations):

    terminal_terms = get_terminal_terms(
        ontology,
        relations
    )

    search = st.text_input(
        "🔍 Filter ontology terms"
    )

    if search:

        display_terms = [
            oid
            for oid in terminal_terms
            if (
                search.lower() in oid.lower()
                or search.lower() in ontology.get(oid, "").lower()
            )
        ]

    else:

        display_terms = terminal_terms

    st.caption(
        f"{len(display_terms)} terminal ontology terms shown"
    )

    selected_terms = []

    for oid in display_terms:

        checked = oid in ontology_ids

        term_name = ontology.get(
            oid,
            "Unknown"
        )

        path_str = get_ontology_path(
            oid,
            ontology,
            relations
        )

        with st.container(border=True):

            col1, col2, col3 = st.columns(
                [0.08, 0.72, 0.20],
                vertical_alignment="center"
            )

            with col1:

                value = st.checkbox(
                    "Select ontology term",
                    value=checked,
                    key=f"edit_ontology_{oid}",
                    label_visibility="collapsed",
                )

            with col2:

                st.markdown(
                    f"""
                    <div style="font-weight:600;">
                        {term_name}
                    </div>

                    <div style="
                        font-family:monospace;
                        font-size:12px;
                        color:#6b7280;
                    ">
                        {oid}
                    </div>

                    <div style="
                        font-size:13px;
                        color:#6b7280;
                        margin-top:4px;
                    ">
                        {path_str}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col3:

                if value:

                    st.markdown(
                        """
                        <div style="
                            background:#dcfce7;
                            color:#166534;
                            border:1px solid #86efac;
                            border-radius:999px;
                            padding:4px 8px;
                            text-align:center;
                            font-size:12px;
                            font-weight:600;
                        ">
                            Selected
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                else:

                    st.markdown(
                        """
                        <div style="
                            color:#9ca3af;
                            text-align:center;
                            font-size:12px;
                        ">
                            Available
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        if value:
            selected_terms.append(oid)

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "💾 Save Ontology",
            use_container_width=True,
        ):

            content = path.read_text(
                encoding="utf-8"
            )

            lines = [
                line
                for line in content.splitlines()
                if not re.match(
                    r"^DIO:\d+$",
                    line.strip()
                )
            ]

            lines.extend(selected_terms)

            path.write_text(
                "\n".join(lines) + "\n",
                encoding="utf-8",
            )

            st.success(
                "Ontology updated successfully."
            )

            st.rerun()

    with col2:

        if st.button(
            "Cancel",
            use_container_width=True,
        ):
            st.rerun()

# --- FUNCTION TO READ ONTOLOGY FROM GITHUB ---
@st.cache_data(ttl=3600)
def get_remote_dio_data():
    ontology = {}
    relations = {} 
    diaf_data = []
    context = ssl._create_unverified_context()

    # 1. Load dio.obo (ID -> Name + relations)
    try:
        obo_url = "https://raw.githubusercontent.com/pegi3s/dockerfiles/master/metadata/dio.obo"
        with urllib.request.urlopen(obo_url, context=context) as response:
            content = response.read().decode("utf-8")

            term_id = None

            for line in content.splitlines():
                line = line.strip()

                if line.startswith("id:"):
                    term_id = line.split("id:")[1].strip()

                elif line.startswith("name:") and term_id:
                    ontology[term_id] = line.split("name:")[1].strip()

                elif line.startswith("is_a:") and term_id:
                    parent_id = line.split("is_a:")[1].split()[0].strip()
                    relations[term_id] = parent_id

                elif line == "":
                    term_id = None

    except Exception as e:
        print(f"Error loading dio.obo: {e}")

    # 2. Load dio.diaf
    try:
        diaf_url = "https://raw.githubusercontent.com/pegi3s/dockerfiles/master/metadata/dio.diaf"
        with urllib.request.urlopen(diaf_url, context=context) as response:
            content = response.read().decode("utf-8")
            for line in content.splitlines():
                if "\t" in line:
                    parts = line.split("\t")
                    diaf_data.append({"id": parts[0].strip(), "tool": parts[1].strip()})
    except Exception as e:
        print(f"Error loading dio.diaf: {e}")

    return ontology, relations, diaf_data

# --- HELPER FUNCTION FOR HIERARCHY ---
def get_ontology_path(term_id, terms_map, relations):
    """Builds the 'Parent > Child' path recursively for intuitive visualization."""
    if not term_id:
        return ""
    path = [terms_map.get(term_id, term_id)]
    current_id = term_id

    # 10-level limit to prevent infinite recursion in case of errors in the .obo file
    for _ in range(10):
        parent_id = relations.get(current_id)
        if not parent_id or parent_id not in terms_map:
            break
        path.insert(0, terms_map[parent_id])
        current_id = parent_id

    return " > ".join(path)


st.set_page_config(
    page_title="BDIP Submit",
    layout="wide" 
)

# CSS
def blue_css():
    # ============================
    # CSS
    # ============================
    st.markdown("""
    <style>

    .step-section {
        padding: 34px;
        border-radius: 26px;
        margin-bottom: 25px;
        position: relative;
        overflow: hidden;

        background: linear-gradient(
            145deg,
            rgba(59,130,246,0.10),
            rgba(59,130,246,0.03)
        );

        border: 1px solid rgba(59,130,246,0.15);

        backdrop-filter: blur(10px);
    }

    .step-section::before {
        content: "";
        position: absolute;
        top: -80px;
        right: -80px;

        width: 260px;
        height: 260px;

        border-radius: 50%;

        background: rgba(59,130,246,0.08);
    }

    .step-badge {
        display: inline-flex;
        align-items: center;
        gap: 10px;

        padding: 10px 18px;

        border-radius: 14px;

        background: rgba(59,130,246,0.12);

        color: #2563eb;

        font-size: 15px;
        font-weight: 700;

        margin-bottom: 14px;
    }

    .step-title {
        font-size: 34px;
        font-weight: 700;
        color: var(--text-color);

        margin-bottom: 10px;
        letter-spacing: -0.5px;
    }

    .step-description {
        font-size: 15px;
        line-height: 1.7;
        color: var(--text-color);

        max-width: 720px;
    }

    /* ============================
    FORM CARD
    ============================ */

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 22px !important;
        padding: 24px !important;

        background: rgba(255,255,255,0.72) !important;

        border: 1px solid rgba(255,255,255,0.6) !important;

        backdrop-filter: blur(12px);

        box-shadow:
            0 1px 2px rgba(0,0,0,0.04),
            0 8px 24px rgba(15,23,42,0.05);
    }

    </style>
    """, unsafe_allow_html=True)

def orange_css():
    # ============================
    # CSS
    # ============================
    st.markdown("""
    <style>

    .step-section {
        padding: 34px;
        border-radius: 26px;
        margin-bottom: 25px;
        position: relative;
        overflow: hidden;

        background: linear-gradient(
            145deg,
            rgba(249,115,22,0.12),
            rgba(251,146,60,0.04)
        );

        border: 1px solid rgba(249,115,22,0.18);

        backdrop-filter: blur(10px);
    }

    .step-section::before {
        content: "";
        position: absolute;
        top: -80px;
        right: -80px;

        width: 260px;
        height: 260px;

        border-radius: 50%;

        background: rgba(251,146,60,0.10);
    }

    .step-badge {
        display: inline-flex;
        align-items: center;
        gap: 10px;

        padding: 10px 18px;

        border-radius: 14px;

        background: rgba(249,115,22,0.14);

        color: #ea580c;

        font-size: 15px;
        font-weight: 700;

        margin-bottom: 14px;
    }

    .step-title {
        font-size: 34px;
        font-weight: 700;
        color: var(--text-color);

        margin-bottom: 10px;
        letter-spacing: -0.5px;
    }

    .step-description {
        font-size: 15px;
        line-height: 1.7;
        color: var(--text-color);

        max-width: 720px;
    }

    /* ============================
    FORM CARD
    ============================ */

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 22px !important;
        padding: 24px !important;

        background: rgba(255,255,255,0.78) !important;

        border: 1px solid rgba(251,146,60,0.18) !important;

        backdrop-filter: blur(12px);

        box-shadow:
            0 1px 2px rgba(0,0,0,0.04),
            0 8px 24px rgba(249,115,22,0.08);
    }

    </style>
    """, unsafe_allow_html=True)

def green_css():
    # ============================
    # CSS
    # ============================
    st.markdown("""
    <style>

    .step-section {
        padding: 34px;
        border-radius: 26px;
        margin-bottom: 25px;
        position: relative;
        overflow: hidden;

        background: linear-gradient(
            145deg,
            rgba(16,185,129,0.12),
            rgba(52,211,153,0.04)
        );

        border: 1px solid rgba(16,185,129,0.18);

        backdrop-filter: blur(10px);
    }

    .step-section::before {
        content: "";
        position: absolute;
        top: -80px;
        right: -80px;

        width: 260px;
        height: 260px;

        border-radius: 50%;

        background: rgba(52,211,153,0.10);
    }

    .step-badge {
        display: inline-flex;
        align-items: center;
        gap: 10px;

        padding: 10px 18px;

        border-radius: 14px;

        background: rgba(16,185,129,0.14);

        color: #059669;

        font-size: 15px;
        font-weight: 700;

        margin-bottom: 14px;
    }

    .step-title {
        font-size: 34px;
        font-weight: 700;
        color: var(--text-color);

        margin-bottom: 10px;
        letter-spacing: -0.5px;
    }

    .step-description {
        font-size: 15px;
        line-height: 1.7;
        color: var(--text-color);

        max-width: 720px;
    }

    /* ============================
    FORM CARD
    ============================ */

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 22px !important;
        padding: 24px !important;

        background: rgba(255,255,255,0.78) !important;

        border: 1px solid rgba(52,211,153,0.18) !important;

        backdrop-filter: blur(12px);

        box-shadow:
            0 1px 2px rgba(0,0,0,0.04),
            0 8px 24px rgba(16,185,129,0.08);
    }

    </style>
    """, unsafe_allow_html=True)

def yellow_css():
    # ============================
        # CSS
        # ============================
        st.markdown("""
        <style>

        .step-section {
            padding: 34px;
            border-radius: 26px;
            margin-bottom: 25px;
            position: relative;
            overflow: hidden;

            background: linear-gradient(
                145deg,
                rgba(139,92,246,0.12),
                rgba(168,85,247,0.04)
            );

            border: 1px solid rgba(139,92,246,0.18);

            backdrop-filter: blur(10px);
        }

        .step-section::before {
            content: "";
            position: absolute;
            top: -80px;
            right: -80px;

            width: 260px;
            height: 260px;

            border-radius: 50%;

            background: rgba(168,85,247,0.10);
        }

        .step-badge {
            display: inline-flex;
            align-items: center;
            gap: 10px;

            padding: 10px 18px;

            border-radius: 14px;

            background: rgba(139,92,246,0.14);

            color: #7c3aed;

            font-size: 15px;
            font-weight: 700;

            margin-bottom: 14px;
        }

        .step-title {
            font-size: 34px;
            font-weight: 700;
            color: var(--text-color);

            margin-bottom: 10px;
            letter-spacing: -0.5px;
        }

        .step-description {
            font-size: 15px;
            line-height: 1.7;
            color: var(--text-color);

            max-width: 720px;
        }

        /* ============================
        FORM CARD
        ============================ */

        [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 22px !important;
            padding: 24px !important;

            background: rgba(255,255,255,0.78) !important;

            border: 1px solid rgba(168,85,247,0.18) !important;

            backdrop-filter: blur(12px);

            box-shadow:
                0 1px 2px rgba(0,0,0,0.04),
                0 8px 24px rgba(139,92,246,0.08);
        }

        </style>
        """, unsafe_allow_html=True)

def purple_css():
    # ============================
    # CSS
    # ============================
    st.markdown("""
    <style>

    .step-section {
        padding: 34px;
        border-radius: 26px;
        margin-bottom: 25px;
        position: relative;
        overflow: hidden;

        background: linear-gradient(
            145deg,
            rgba(139,92,246,0.12),
            rgba(168,85,247,0.04)
        );

        border: 1px solid rgba(139,92,246,0.18);

        backdrop-filter: blur(10px);
    }

    .step-section::before {
        content: "";
        position: absolute;
        top: -80px;
        right: -80px;

        width: 260px;
        height: 260px;

        border-radius: 50%;

        background: rgba(168,85,247,0.10);
    }

    .step-badge {
        display: inline-flex;
        align-items: center;
        gap: 10px;

        padding: 10px 18px;

        border-radius: 14px;

        background: rgba(139,92,246,0.14);

        color: #7c3aed;

        font-size: 15px;
        font-weight: 700;

        margin-bottom: 14px;
    }

    .step-title {
        font-size: 34px;
        font-weight: 700;
        color: var(--text-color);

        margin-bottom: 10px;
        letter-spacing: -0.5px;
    }

    .step-description {
        font-size: 15px;
        line-height: 1.7;
        color: var(--text-color);

        max-width: 720px;
    }

    /* ============================
    FORM CARD
    ============================ */

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 22px !important;
        padding: 24px !important;

        background: rgba(255,255,255,0.78) !important;

        border: 1px solid rgba(168,85,247,0.18) !important;

        backdrop-filter: blur(12px);

        box-shadow:
            0 1px 2px rgba(0,0,0,0.04),
            0 8px 24px rgba(139,92,246,0.08);
    }

    </style>
    """, unsafe_allow_html=True)

def blue_2_css():
    # ============================
    # CSS (BLUE / INDIGO THEME)
    # ============================
    st.markdown("""
    <style>

    .step-section {
        padding: 34px;
        border-radius: 26px;
        margin-bottom: 25px;
        position: relative;
        overflow: hidden;

        background: linear-gradient(
            145deg,
            rgba(79,70,229,0.10),
            rgba(59,130,246,0.03)
        );

        border: 1px solid rgba(79,70,229,0.18);

        backdrop-filter: blur(10px);
    }

    .step-section::before {
        content: "";
        position: absolute;
        top: -80px;
        right: -80px;

        width: 260px;
        height: 260px;

        border-radius: 50%;

        background: rgba(99,102,241,0.10);
    }

    .step-badge {
        display: inline-flex;
        align-items: center;
        gap: 10px;

        padding: 10px 18px;

        border-radius: 14px;

        background: rgba(79,70,229,0.12);

        color: #4338ca;

        font-size: 15px;
        font-weight: 700;

        margin-bottom: 14px;
    }

    .step-title {
        font-size: 34px;
        font-weight: 700;
        color: var(--text-color);

        margin-bottom: 10px;
        letter-spacing: -0.5px;
    }

    .step-description {
        font-size: 15px;
        line-height: 1.7;
        color: #6b7280;

        max-width: 720px;
    }

    /* ============================
    FORM CARD
    ============================ */

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 22px !important;
        padding: 24px !important;

        background: rgba(255,255,255,0.72) !important;

        border: 1px solid rgba(255,255,255,0.6) !important;

        backdrop-filter: blur(12px);

        box-shadow:
            0 1px 2px rgba(0,0,0,0.04),
            0 8px 24px rgba(15,23,42,0.05);
    }

    </style>
    """, unsafe_allow_html=True)


# HOME PAGE
if st.session_state.current_page == "Home":

    # =========================
    # NAV VIA QUERY PARAMS
    # =========================
    query = st.query_params
    if "nav" in query:
        mapping = {
            "new_image": "New Image",
            "new_version": "New Version Image",
            "tools": "BDIP Tools",
            "test_image": "Test Docker Image"
        }
        if query["nav"] in mapping:
            change_page(mapping[query["nav"]])

    # =========================
    # SVG ICONS
    # =========================
    box_svg = """
    <svg width="52" height="52" viewBox="0 0 64 64" fill="none">
        <rect width="64" height="64" rx="16" fill="#DBEAFE"/>
        <path d="M14 22L32 14L50 22L32 30L14 22Z" fill="#3B82F6"/>
        <path d="M14 22V42L32 50V30L14 22Z" fill="#2563EB"/>
        <path d="M50 22V42L32 50V30L50 22Z" fill="#60A5FA"/>
    </svg>
    """

    version_svg = """
    <svg width="52" height="52" viewBox="0 0 64 64" fill="none">
        <rect width="64" height="64" rx="16" fill="#FEF3C7"/>
        <circle cx="32" cy="32" r="16" fill="#F59E0B"/>
        <path d="M32 24V40" stroke="white" stroke-width="4" stroke-linecap="round"/>
        <path d="M24 32H40" stroke="white" stroke-width="4" stroke-linecap="round"/>
    </svg>
    """

    doc_svg = """
    <svg width="52" height="52" viewBox="0 0 64 64" fill="none">
        <rect width="64" height="64" rx="16" fill="#DCFCE7"/>
        <path d="M22 14H36L46 24V48H22V14Z" fill="#10B981"/>
        <path d="M36 14V24H46" fill="#6EE7B7"/>
        <path d="M28 32H40" stroke="white" stroke-width="3" stroke-linecap="round"/>
        <path d="M28 38H40" stroke="white" stroke-width="3" stroke-linecap="round"/>
    </svg>
    """

    tools_svg = """
    <svg width="52" height="52" viewBox="0 0 64 64" fill="none">
        <rect width="64" height="64" rx="16" fill="#FEE2E2"/>
        <path d="M38 18L46 26L30 42L22 44L24 36L38 18Z" fill="#EF4444"/>
        <circle cx="42" cy="22" r="4" fill="#FCA5A5"/>
    </svg>
    """
    
    test_svg = """
    <svg width="52" height="52" viewBox="0 0 64 64" fill="none">
        <rect width="64" height="64" rx="16" fill="#DBEAFE"/>
        <circle cx="32" cy="32" r="16" fill="#3B82F6"/>
        <path d="M28 24L42 32L28 40V24Z" fill="white"/>
    </svg>
    """

    # =========================
    # CSS
    # =========================
    st.markdown("""
    <style>
        [data-testid="stSidebar"] {display: none;}

        .block-container {
            max-width: 1100px;
            margin: auto;
            padding-top: 2rem;
        }

        .hero-title {
            font-size: 52px;
            font-weight: 700;
            text-align: center;
            letter-spacing: -1px;
        }

        .hero-sub {
            font-size: 22px;
            text-align: center;
            margin-bottom: 30px;
            opacity: 0.8;
        }

        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(25px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .card-link {
            text-decoration: none !important;
            color: inherit !important;
            display: block;
            -webkit-tap-highlight-color: transparent;
        }

        .card-link:hover,
        .card-link:visited,
        .card-link:active {
            text-decoration: none !important;
            color: inherit !important;
        }
        
        .card-title {
            color: inherit;
        }

        .card-sub {
            color: inherit;
            opacity: 0.7;
        }

        .custom-card {
            height: 200px;
            border-radius: 18px;
            position: relative;
            overflow: hidden;

            backdrop-filter: blur(8px);
            padding: 25px;
            text-align: center;
            color: inherit;
            transition: all 0.25s ease;
            display: flex;
            flex-direction: column;
            justify-content: center;
            cursor: pointer;
            animation: fadeInUp 0.5s ease forwards;
            margin-bottom: 20px;
        }

        /* =========================
        BLUE
        ========================= */

        .custom-card.blue {
            border: 1px solid rgba(59,130,246,0.18);
            background: linear-gradient(
                145deg,
                rgba(59,130,246,0.06),
                rgba(255,255,255,0.02)
            );
        }

        .custom-card.blue:hover {
            border-color: #3b82f6;
            box-shadow: 0 12px 30px rgba(59,130,246,0.22);
        }

        /* =========================
        ORANGE
        ========================= */

        .custom-card.orange {
            border: 1px solid rgba(245,158,11,0.18);
            background: linear-gradient(
                145deg,
                rgba(245,158,11,0.06),
                rgba(255,255,255,0.02)
            );
        }

        .custom-card.orange:hover {
            border-color: #f59e0b;
            box-shadow: 0 12px 30px rgba(245,158,11,0.22);
        }

        /* =========================
        GREEN
        ========================= */

        .custom-card.green {
            border: 1px solid rgba(16,185,129,0.18);
            background: linear-gradient(
                145deg,
                rgba(16,185,129,0.06),
                rgba(255,255,255,0.02)
            );
        }

        .custom-card.green:hover {
            border-color: #10b981;
            box-shadow: 0 12px 30px rgba(16,185,129,0.22);
        }

        /* =========================
        RED
        ========================= */

        .custom-card.red {
            border: 1px solid rgba(239,68,68,0.18);
            background: linear-gradient(
                145deg,
                rgba(239,68,68,0.06),
                rgba(255,255,255,0.02)
            );
        }

        .custom-card.red:hover {
            border-color: #ef4444;
            box-shadow: 0 12px 30px rgba(239,68,68,0.22);
        }
        
        .custom-card.indigo {
            border: 1px solid rgba(99,102,241,0.18);
            background: linear-gradient(
                145deg,
                rgba(99,102,241,0.06),
                rgba(255,255,255,0.02)
            );
        }

        .custom-card.indigo:hover {
            border-color: #6366f1;
            box-shadow: 0 12px 30px rgba(99,102,241,0.22);
        }

        /* =========================
        ICONS
        ========================= */

        .custom-card svg {
            transition: all 0.25s ease;
        }

        .custom-card:hover svg {
            transform: scale(1.08);
        }

        /* =========================
        GLASS EFFECT
        ========================= */

        .custom-card::before {
            content: "";
            position: absolute;
            top: -35%;
            right: -15%;
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: rgba(255,255,255,0.08);
        }

        /* =========================
        ACTIVE
        ========================= */

        .custom-card:active {
            transform: scale(0.98);
        }

        .card-title {
            font-size: 20px;
            font-weight: 600;
            margin-top: 10px;
            color: var(--text-color);
        }

        .card-sub {
            font-size: 13px;
            color: var(--text-color);
            margin-top: 6px;
        }
    </style>
    """, unsafe_allow_html=True)

    # =========================
    # HERO
    # =========================
    st.markdown('<div class="hero-title">pegi3s BDIP</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-sub">Submission Platform</div>', unsafe_allow_html=True)

    st.caption("Choose what you want to do:")

    # =========================
    # CARD FUNCTION
    # =========================
    def card(title, subtitle, svg, link, color):
        st.markdown(f"""
        <a href="{link}" target="_self" class="card-link">
            <div class="custom-card {color}">
                <div style="margin-bottom:12px">{svg}</div>
                <div class="card-title">{title}</div>
                <div class="card-sub">{subtitle}</div>
            </div>
        </a>
        """, unsafe_allow_html=True)

    # =========================
    # GRID
    # =========================
    c1, c2 = st.columns(2)
    c3, c4 = st.columns(2)
    left, center, right = st.columns([1, 2, 1])

    with c1:
        card("New Image", "Submit a new Docker image", box_svg, "?nav=new_image", "blue")

    with c2:
        card("New Version", "Submit new version from existing image", version_svg, "?nav=new_version", "orange")

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    with c3:
        _wm_params = {}
        if GITHUB_REPO_OWNER and GITHUB_REPO:
            _wm_params["repo"] = f"{GITHUB_REPO_OWNER}/{GITHUB_REPO}"
        if GITHUB_BRANCH:
            _wm_params["branch"] = GITHUB_BRANCH
        if GITHUB_TOKEN:
            _wm_params["token"] = GITHUB_TOKEN
        if GITHUB_USER:
            _wm_params["author"] = GITHUB_USER
        if GITHUB_EMAIL:
            _wm_params["email"] = GITHUB_EMAIL
        _wm_qs = "&".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in _wm_params.items())
        _wm_url = f"http://localhost:4200/{'?' + _wm_qs if _wm_qs else ''}"
        card("BDIP Web Manager", "Manage and edit metadata", doc_svg, _wm_url, "green")

    with c4:
        card("BDIP Tools", "Tools & utilities", tools_svg, "?nav=tools", "red")

    with center:
        card(
            "Test Docker Image",
            "Run and validate an existing Docker image",
            test_svg,
            "?nav=test_image",
            "indigo"
        )

    st.stop()


# ----------------------------
# NEW VERSION IMAGE (UNIFIED)
# ----------------------------
elif st.session_state.current_page == "New Version Image":

    col1, col2 = st.columns([7,1])
    
    with col1:
        st.header("Submit New Version Image")
    
    with col2:
        st.markdown("<div style='height: 12px'></div>", unsafe_allow_html=True)
        # Button Back to Home
        if st.button("← Back to Home"):
            if form["step"] == 7:
                reset_new_version()
                change_page("Home")
                st.rerun()
            else:
                st.session_state["show_submission_dialog"] = True

    # ============================
    # SHOW DIALOG
    # ============================
    if st.session_state.get("show_submission_dialog", False):

        show_unsaved_submission_dialog()

    # ============================
    # INIT
    # ============================
    form = st.session_state.new_version_form

    # ============================
    # HANDLE CLICK VIA QUERY PARAM
    # ============================
    params = st.query_params
    if "step" in params:
        try:
            new_step = int(params["step"])
            if 1 <= new_step <= 8:
                form["step"] = new_step
                st.query_params.clear()
                st.rerun()
        except:
            pass

    # ============================
    # STEPPER
    # ============================
    def render_stepper():

        steps = [
            ("project", "Project"),
            ("version", "Version"),
            ("files", "Files"),
            ("metadata", "Metadata"),
            ("github", "GitHub"),
            ("docker", "DockerHub"),
            ("done", "Done"),
        ]

        current = form["step"]
        total = len(steps)
        progress = int((current - 1) / (total - 1) * 100)

        # CSS
        st.markdown(f"""
        <style>
        .stepper-wrapper {{
            position: relative;
            margin-bottom: 30px;
        }}

        .stepper {{
            display: grid;
            grid-template-columns: repeat(7, 1fr); /* nÃºmero de steps */
            align-items: center;
            position: relative;
            z-index: 2;
        }}

        .step {{
            text-align: center;
        }}

        .circle {{
            width: 42px;
            height: 42px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto;
            background: white;
            transition: all 0.25s ease;
            position: relative;
        }}

        .done {{
            background:#10b981;
            color:white;
        }}

        .active {{
            background:#3b82f6;
            color:white;
            transform: scale(1.15);
            box-shadow: 0 0 0 4px rgba(59,130,246,0.15);
        }}

        .todo {{
            background:#e5e7eb;
            color:#666;
        }}

        .label {{
            font-size:12px;
            margin-top:6px;
        }}

        .icon svg {{
            width:20px;
            height:20px;
            stroke:currentColor;
            fill:none;
            stroke-width:2;
            stroke-linecap:round;
            stroke-linejoin:round;
        }}

        .progress-line {{
            position: absolute;
            top: 21px;
            left: calc(100% / 7 / 2);
            right: calc(100% / 7 / 2);
            height: 6px;
            background: #e5e7eb;
            border-radius: 10px;
            z-index: 0;
        }}

        .progress-fill {{
            height: 100%;
            width: {progress}%;
            background: linear-gradient(90deg, #10b981, #2563eb);
            border-radius: 10px;
            transition: width 0.5s ease-in-out;
        }}

        .step:hover .circle {{
            transform: scale(1.15);
            box-shadow: 0 5px 15px rgba(59,130,246,0.25);
        }}
        </style>
        """, unsafe_allow_html=True)

        # SVG icons
        def icon(svg):
            return f'<div class="icon">{svg}</div>'

        ICONS = {
            "project": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M3 7l9-4 9 4-9 4-9-4z"/>
                <path d="M3 12l9 4 9-4"/>
                <path d="M3 17l9 4 9-4"/>
            </svg>
            '''),

            "version": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M12 5v14M5 12h14"/>
            </svg>
            '''),

            "validation": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M5 13l4 4L19 7"/>
            </svg>
            '''),

            "files": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M6 2h9l5 5v15H6z"/>
                <path d="M14 2v6h6"/>
            </svg>
            '''),

            "metadata": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M4 6h16"/>
                <path d="M4 12h16"/>
                <path d="M4 18h16"/>
            </svg>
            '''),

            "github": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M9 19c-4 1-4-2-6-3"/>
                <path d="M15 22v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 19 4.77 5.07 5.07 0 0 0 18.91 1S17.73.65 15 2.48a13.38 13.38 0 0 0-6 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77 5.44 5.44 0 0 0 3.5 8.52c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
            </svg>
            '''),

            "docker": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M3 7l9-4 9 4-9 4-9-4z"/>
                <path d="M3 7v10l9 4 9-4V7"/>
                <path d="M12 11v10"/>
                <path d="M16 13v4"/>
            </svg>
            '''),

            "done": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M5 13l4 4L19 7"/>
            </svg>
            ''')
        }
        
        # HTML (no problematic indentation)
        html = f'<div class="stepper-wrapper"><div class="progress-line"><div class="progress-fill"></div></div><div class="stepper">'

        for i, (key, label) in enumerate(steps, 1):
            state = "done" if i < current else "active" if i == current else "todo"

            html += f'<div class="step"><div class="circle {state}">{ICONS[key]}</div><div class="label">{label}</div></div>'

        html += '</div></div>'

        st.markdown(html, unsafe_allow_html=True)

    render_stepper()
    st.divider()

    step = form["step"]
    
    # ============================
    # STEP 1 - PROJECT
    # ============================
    if step == 1:

        # ============================ 
        # HERO START 
        # ============================ 
        blue_css()
        st.markdown(""" <div class="step-section"> <div class="step-badge"> Project Selection </div> <div class="step-title"> Select Project </div> <div class="step-description"> Choose an existing BDIP project to submit a new Docker image version. </div> <div class="form-card"> """, unsafe_allow_html=True)

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            # ============================
            # PROJECTS
            # ============================
            projects = [
                p.name for p in Path(BASE_PATH).iterdir()
                if p.is_dir() and (p / "for_submission").exists()
            ]

            project_options = ["-- Select --"] + projects

            selected_index = 0

            if form["project"] in projects:
                selected_index = project_options.index(form["project"])

            selected_project = st.selectbox(
                "Project",
                project_options,
                index=selected_index
            )

            manual_project = st.text_input(
                "Or type project manually",
                value=form["manual_project"],
                placeholder="e.g. fastqc-0.11.9"
            )

            # SAVE STATE
            form["manual_project"] = manual_project

            if selected_project != "-- Select --":
                form["project"] = selected_project

            project = (
                manual_project.strip()
                if manual_project.strip()
                else form["project"]
            )
            
            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # VALIDATIONS
            # ============================
            is_valid = False
            validation_error = None

            if project and project != "-- Select --":

                submission_dir = Path(BASE_PATH) / project / "for_submission"

                if not submission_dir.exists():

                    validation_error = "Invalid project (missing for_submission)"

                else:

                    def split(name):
                        m = re.match(r"(.+)-(\d+\.\d+.*)", name)
                        return m.groups() if m else (name, None)

                    base, _ = split(project)

                    try:

                        url = (
                            f"https://raw.githubusercontent.com/"
                            f"{GITHUB_REPO_OWNER}/{GITHUB_REPO}/master/metadata/metadata.json"
                        )

                        response = requests.get(url)
                        response.raise_for_status()

                        metadata_list = response.json()

                        exists_in_metadata = any(
                            item.get("name") == base
                            for item in metadata_list
                        )

                        if exists_in_metadata:
                            is_valid = True
                        else:
                            validation_error = (
                                f"Image '{base}' does not exist in metadata"
                            )

                    except Exception as e:

                        validation_error = f"Metadata validation failed: {e}"

            # ============================
            # VALIDATION MESSAGE
            # ============================
            if validation_error:
                st.error(validation_error)

            elif is_valid:
                st.success("Project validated successfully")

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # ACTIONS
            # ============================
            render_navigation(
                next_step=2,
                next_disabled=not is_valid
            )

            if is_valid:

                form["project"] = project

                def split(name):
                    m = re.match(r"(.+)-(\d+\.\d+.*)", name)
                    return m.groups() if m else (name, None)

                base, _ = split(project)

                form["base"] = base

    # ============================
    # STEP 2  - VERSION + VALIDATION
    # ============================
    elif step == 2:

        project = form["project"]
        
        # ============================
        # HERO
        # ============================
        orange_css()
        st.markdown("""<div class="step-section"><div class="step-badge">Version Configuration</div><div class="step-title">Define Version</div><div class="step-description">Choose the version that will be submitted and validate if it already exists in the GitHub repository.</div></div>""", unsafe_allow_html=True)

        # ============================
        # FORM CARD
        # ============================
        form_container = st.container(border=True)

        with form_container:

            # ============================
            # SPLIT PROJECT
            # ============================
            def split(name):
                m = re.match(r"(.+)-(\d+\.\d+.*)", name)
                return m.groups() if m else (name, None)

            base, suggested = split(project)

            form["base"] = base

            st.markdown("### Version Setup")

            # ============================
            # VERSION INPUT
            # ============================
            if not suggested:

                st.warning("⚠️ No version detected in project name.")

                version = st.text_input(
                    "Enter version",
                    value=form["version"],
                    placeholder="e.g. 1.2.0"
                )

            else:

                st.info(f"Detected version: {suggested}")

                use_index = (
                    0
                    if form["use_detected_version"] == "Yes"
                    else 1
                )

                use = st.radio(
                    "Use detected version?",
                    ["Yes", "No"],
                    horizontal=True,
                    index=use_index
                )

                form["use_detected_version"] = use

                if use == "Yes":

                    version = suggested

                    st.text_input(
                        "Version",
                        value=version,
                        disabled=True
                    )

                else:

                    version = st.text_input(
                        "Enter version",
                        value=form["version"],
                        placeholder="e.g. 1.2.0"
                    )

            form["version"] = version

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # FORMAT VALIDATION
            # ============================
            version_valid = bool(
                version
                and re.match(r"^\d+\.\d+(\.\d+)?$", version)
            )

            if version and not version_valid:

                st.warning(
                    "Version format should be like 1.2 or 1.2.3"
                )

            # ============================
            # GITHUB VALIDATION
            # ============================
            exists = False
            versions = []

            if version_valid:

                with st.spinner("Checking GitHub versions..."):

                    try:

                        url = (
                            f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO}/contents/{base}"
                        )

                        response = requests.get(url)

                        if response.status_code == 200:

                            versions = [
                                i["name"]
                                for i in response.json()
                                if i["type"] == "dir"
                            ]

                        exists = version in versions

                        form["version_exists"] = exists

                        st.markdown("#### Validation")

                        if exists:

                            st.error(
                                f"❌ Version '{version}' already exists"
                            )

                        else:

                            st.success(
                                f"✅ Version '{version}' is available"
                            )

                        with st.expander("Existing versions"):

                            if versions:
                                st.write(", ".join(versions))
                            else:
                                st.write("No versions found")

                    except Exception as e:

                        st.error(f"Validation failed: {e}")

                        exists = True

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # NAVIGATION
            # ============================
            render_navigation(
                back_step=1,
                next_step=3,
                next_disabled=(
                    not version_valid
                    or exists
                )
            )
        
    # ============================
    # STEP 3 - FILES
    # ============================
    elif step == 3:

        # ============================
        # HERO
        # ============================
        green_css()
        st.markdown("""<div class="step-section"><div class="step-badge">Files Inspection</div><div class="step-title">Review Submission Files</div><div class="step-description">Preview the files that will be included in the submission before continuing to metadata and publication.</div></div>""", unsafe_allow_html=True)

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            project = form["project"]

            submission_dir = (
                Path(BASE_PATH)
                / project
                / "for_submission"
            )

            files = [
                f for f in submission_dir.iterdir()
                if f.name != "test_data"
            ]

            st.markdown("### Files Preview")

            for f in files:
                st.write("-", f.name)

            st.markdown("<br>", unsafe_allow_html=True)

            dockerfile_path = submission_dir / "Dockerfile"

            if dockerfile_path.exists():

                with st.expander("Dockerfile"):

                    st.code(
                        dockerfile_path.read_text(),
                        language="dockerfile"
                    )

            readme_path = submission_dir / "README.md"

            if readme_path.exists():

                with st.expander("README"):
                    if st.button(
                        "Edit README ✏️",
                        key="edit_readme_btn"
                    ):
                        edit_readme_dialog(readme_path)

                    st.markdown(
                        readme_path.read_text()
                    )

            st.markdown("<br>", unsafe_allow_html=True)

            render_navigation(
                back_step=2,
                next_step=4
            )

    # ============================
    # STEP 4 - METADATA
    # ============================
    elif step == 4:

        # ============================
        # HERO
        # ============================
        yellow_css()
        st.markdown("""<div class="step-section"><div class="step-badge">Metadata Review</div><div class="step-title">Preview Metadata Changes</div><div class="step-description">Review the metadata updates that will be applied to the repository before publishing the new version.</div></div>""", unsafe_allow_html=True)

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            base = form["base"]
            version = form["version"]

            url = f"https://raw.githubusercontent.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO}/master/metadata/metadata.json"

            response = requests.get(url)
            response.raise_for_status()

            metadata_list = response.json()

            metadata_obj = next(
                (
                    i for i in metadata_list
                    if i["name"] == base
                ),
                None
            )

            if not metadata_obj:

                st.error("Tool not found in metadata")
                st.stop()

            today = datetime.now().strftime("%d/%m/%Y")

            preview = metadata_obj.copy()

            prev = metadata_obj.get("latest")

            preview["recommended"] = [
                {
                    "version": version,
                    "date": today
                }
            ]

            preview["latest"] = version

            if prev:

                preview.setdefault(
                    "no_longer_tested",
                    []
                )

                if prev not in preview["no_longer_tested"]:

                    preview["no_longer_tested"].append(prev)

            st.markdown("### Updated Metadata")

            with st.expander("Metadata Preview (Updated)"):

                st.json(preview)

            st.markdown("<br>", unsafe_allow_html=True)

            render_navigation(
                back_step=3,
                next_step=5
            )

    # ============================
    # STEP 5 - GITHUB
    # ============================
    elif step == 5:

        # ============================
        # INIT SESSION STATE
        # ============================
        if "github_logs" not in st.session_state:
            st.session_state.github_logs = []

        if "github_done" not in form:
            form["github_done"] = False

        # ============================
        # HERO
        # ============================
        purple_css()
        st.markdown("""<div class="step-section"><div class="step-badge">GitHub Submission</div><div class="step-title">Publish to GitHub</div><div class="step-description">Push the new version files and metadata updates to the GitHub repository.</div></div>""", unsafe_allow_html=True)

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            # ============================
            # SUCCESS STATE
            # ============================
            if form["github_done"]:

                st.success(
                    "This version has already been submitted to GitHub."
                )

            # ============================
            # CONFIRMATION
            # ============================
            confirm = st.checkbox(
                "I confirm everything is correct",
                disabled=form["github_done"]
            )

            # ============================
            # LOG BOX
            # ============================
            log_box = st.empty()

            existing_logs = "\n".join(
                st.session_state.github_logs
            )

            if existing_logs:

                log_box.code(existing_logs)

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # PUSH BUTTON
            # ============================
            push_clicked = st.button(
                "Push to GitHub",
                disabled=form["github_done"]
            )

            if push_clicked:

                if not confirm:

                    st.error("Please confirm first")
                    st.stop()

                try:

                    # ============================
                    # LOG HELPER
                    # ============================
                    def add_log(message, level="INFO"):

                        line = f"[{level}] {message}"

                        st.session_state.github_logs.append(line)

                        log_box.code(
                            "\n".join(
                                st.session_state.github_logs
                            )
                        )

                    # ============================
                    # START
                    # ============================
                    add_log(
                        "Starting GitHub push",
                        "STEP"
                    )

                    repo_url = (
                        f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO}.git"
                    )

                    with tempfile.TemporaryDirectory() as tmpdir:

                        repo_path = Path(tmpdir)

                        add_log("Cloning repository")

                        subprocess.run(
                            [
                                "git",
                                "clone",
                                "--depth",
                                "1",
                                repo_url,
                                str(repo_path)
                            ],
                            check=True
                        )

                        base = form["base"]
                        version = form["version"]
                        project = form["project"]

                        submission_dir = (
                            Path(BASE_PATH)
                            / project
                            / "for_submission"
                        )

                        target_path = (
                            repo_path
                            / base
                            / version
                        )

                        target_path.mkdir(
                            parents=True,
                            exist_ok=True
                        )

                        add_log(
                            f"Copying files to {base}/{version}"
                        )

                        def silent_copy(src, dst):

                            if src.is_file():

                                shutil.copy(src, dst)

                            else:

                                shutil.copytree(
                                    src,
                                    dst,
                                    dirs_exist_ok=True
                                )

                        for item in submission_dir.iterdir():

                            if item.name == "test_data":
                                continue

                            silent_copy(
                                item,
                                target_path / item.name
                            )

                        # ============================
                        # UPDATE METADATA
                        # ============================
                        add_log("Updating metadata")

                        metadata_path = (
                            repo_path
                            / "metadata"
                            / "metadata.json"
                        )

                        metadata_list = json.load(
                            open(metadata_path)
                        )

                        today = datetime.now().strftime(
                            "%d/%m/%Y"
                        )

                        for item in metadata_list:

                            if item["name"] == base:

                                prev = item.get("latest")

                                item["recommended"] = [
                                    {
                                        "version": version,
                                        "date": today
                                    }
                                ]

                                item["latest"] = version

                                if prev:

                                    item.setdefault(
                                        "no_longer_tested",
                                        []
                                    )

                                    if prev not in item["no_longer_tested"]:

                                        item["no_longer_tested"].append(prev)

                        json.dump(
                            metadata_list,
                            open(metadata_path, "w"),
                            indent=2
                        )

                        # ============================
                        # CONFIGURE GIT
                        # ============================
                        add_log(
                            "Configuring git user"
                        )

                        subprocess.run(
                            [
                                "git",
                                "config",
                                "user.email",
                                GITHUB_EMAIL
                            ],
                            cwd=repo_path,
                            check=True
                        )

                        subprocess.run(
                            [
                                "git",
                                "config",
                                "user.name",
                                GITHUB_USER
                            ],
                            cwd=repo_path,
                            check=True
                        )

                        # ============================
                        # GIT ADD
                        # ============================
                        add_log("Adding files")

                        subprocess.run(
                            ["git", "add", "."],
                            cwd=repo_path,
                            check=True
                        )

                        # ============================
                        # COMMIT
                        # ============================
                        add_log("Committing changes")

                        subprocess.run(
                            [
                                "git",
                                "commit",
                                "-m",
                                f"Add {base} version {version}"
                            ],
                            cwd=repo_path,
                            check=True
                        )

                        # ============================
                        # PUSH
                        # ============================
                        add_log("Pushing to repository")

                        subprocess.run(
                            [
                                "git",
                                "push",
                                "origin",
                                "master"
                            ],
                            cwd=repo_path,
                            check=True
                        )

                        # ============================
                        # SUCCESS
                        # ============================
                        add_log(
                            "GitHub push completed",
                            "SUCCESS"
                        )

                        st.success(
                            "Successfully pushed to GitHub"
                        )

                        form["github_done"] = True

                        st.rerun()

                except subprocess.CalledProcessError as e:

                    add_log(str(e), "ERROR")

                    st.error("Git command failed")

                except Exception as e:

                    add_log(str(e), "ERROR")

                    st.error("Unexpected error")

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # NAVIGATION
            # ============================
            render_navigation(
                back_step=4,
                next_step=6,
                next_disabled=not form["github_done"],
                next_key="github_next"
            )
    
    # ============================
    # STEP 6 - DOCKER
    # ============================
    elif step == 6:

        # ============================
        # INIT SESSION STATE
        # ============================
        if "docker_logs" not in st.session_state:
            st.session_state.docker_logs = []

        if "docker_done" not in form:
            form["docker_done"] = False

        # ============================
        # HERO
        # ============================
        blue_2_css()
        st.markdown("""<div class="step-section"><div class="step-badge">DockerHub Submission</div><div class="step-title">Push Docker Image</div><div class="step-description">Build, tag and publish the Docker image to DockerHub, including both version and latest tags.</div></div>""", unsafe_allow_html=True)

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            base = form["base"]
            version = form["version"]
            project = form["project"]

            image_src = f"pegi3s/{base}:{version}"
            image_dst_version = f"{DOCKERHUB_ORG}/{base}:{version}"
            image_dst_latest = f"{DOCKERHUB_ORG}/{base}:latest"

            submission_dir = (
                Path(BASE_PATH)
                / project
                / "for_submission"
            )

            # ============================
            # SUCCESS STATE
            # ============================
            if form["docker_done"]:

                st.success(
                    "This Docker image has already been submitted."
                )

            # ============================
            # CONFIRMATION
            # ============================
            confirm = st.checkbox(
                "I confirm Docker image is ready",
                disabled=form["docker_done"]
            )

            # ============================
            # LOG BOX
            # ============================
            log_box = st.empty()

            existing_logs = "\n".join(
                st.session_state.docker_logs
            )

            if existing_logs:

                log_box.code(existing_logs)

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # PUSH BUTTON
            # ============================
            push_clicked = st.button(
                "Push to DockerHub",
                disabled=form["docker_done"]
            )

            if push_clicked:

                if not confirm:

                    st.error("Please confirm first")
                    st.stop()

                try:

                    # ============================
                    # LOG HELPER
                    # ============================
                    def add_log(message, level="INFO"):

                        line = f"[{level}] {message}"

                        st.session_state.docker_logs.append(line)

                        log_box.code(
                            "\n".join(
                                st.session_state.docker_logs
                            )
                        )

                    # ============================
                    # START
                    # ============================
                    add_log(
                        "Starting Docker process",
                        "STEP"
                    )

                    # ============================
                    # CHECK IMAGE
                    # ============================
                    add_log("Checking local image")

                    result = subprocess.run(
                        ["docker", "images", "-q", image_src],
                        capture_output=True,
                        text=True
                    )

                    if not result.stdout.strip():

                        add_log(
                            "Image not found locally, building",
                            "WARNING"
                        )

                        build = subprocess.run(
                            [
                                "docker",
                                "build",
                                "-t",
                                image_src,
                                str(submission_dir)
                            ],
                            capture_output=True,
                            text=True
                        )

                        if build.returncode != 0:

                            add_log(
                                "Docker build failed",
                                "ERROR"
                            )

                            st.code(build.stderr)

                            st.stop()

                        add_log(
                            "Image built successfully",
                            "SUCCESS"
                        )

                    else:

                        add_log(
                            "Local image found",
                            "SUCCESS"
                        )

                    # ============================
                    # LOGIN
                    # ============================
                    add_log("Logging into DockerHub")

                    login = subprocess.run(
                        [
                            "docker",
                            "login",
                            "-u",
                            docker_user,
                            "--password-stdin"
                        ],
                        input=docker_token,
                        capture_output=True,
                        text=True
                    )

                    if login.returncode != 0:

                        add_log(
                            "Docker login failed",
                            "ERROR"
                        )

                        st.code(login.stderr)

                        st.stop()

                    add_log(
                        "Login successful",
                        "SUCCESS"
                    )

                    # ============================
                    # TAGGING
                    # ============================
                    add_log("Tagging images")

                    subprocess.run(
                        [
                            "docker",
                            "tag",
                            image_src,
                            image_dst_version
                        ],
                        check=True
                    )

                    subprocess.run(
                        [
                            "docker",
                            "tag",
                            image_src,
                            image_dst_latest
                        ],
                        check=True
                    )

                    # ============================
                    # PUSH VERSION
                    # ============================
                    add_log("Pushing version image")

                    push1 = subprocess.run(
                        [
                            "docker",
                            "push",
                            image_dst_version
                        ],
                        capture_output=True,
                        text=True
                    )

                    if push1.returncode != 0:

                        add_log(
                            "Failed to push version",
                            "ERROR"
                        )

                        st.code(push1.stderr)

                        st.stop()

                    # ============================
                    # PUSH LATEST
                    # ============================
                    add_log("Pushing latest image")

                    push2 = subprocess.run(
                        [
                            "docker",
                            "push",
                            image_dst_latest
                        ],
                        capture_output=True,
                        text=True
                    )

                    if push2.returncode != 0:

                        add_log(
                            "Failed to push latest",
                            "ERROR"
                        )

                        st.code(push2.stderr)

                        st.stop()

                    # ============================
                    # SUCCESS
                    # ============================
                    add_log(
                        "Docker push completed",
                        "SUCCESS"
                    )

                    # ============================
                    # README SUBMIT
                    # ============================
                    readme_path = submission_dir / "README.md"

                    if readme_path.exists():
                        append_log("Updating README to DockerHub")

                        auth = requests.post(
                            "https://hub.docker.com/v2/users/login/",
                            json={"username": docker_user, "password": docker_token}
                        )

                        if auth.status_code != 200:
                            append_log("DockerHub authentication failed", "ERROR")
                        else:
                            token = auth.json().get("token")

                            repo_url = f"https://hub.docker.com/v2/repositories/{DOCKERHUB_ORG}/{base}/"

                            headers = {
                                "Authorization": f"JWT {token}",
                                "Content-Type": "application/json"
                            }

                            data = {
                                "full_description": readme_path.read_text()
                            }

                            response = requests.patch(repo_url, headers=headers, json=data)

                            if response.status_code == 200:
                                append_log("README updated successfully", "SUCCESS")
                            else:
                                append_log("README update failed", "ERROR")

                    else:
                        append_log("README.md not found, skipped", "WARNING")

                    st.success(
                        "DockerHub push successful"
                    )

                    form["docker_done"] = True

                    st.rerun()

                except Exception as e:

                    add_log(str(e), "ERROR")

                    st.error(
                        f"Unexpected error: {e}"
                    )

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # NAVIGATION
            # ============================
            render_navigation(
                back_step=5,
                next_step=7,
                next_disabled=not form["docker_done"]
            )
        
    # ============================
    # STEP 7 - DONE
    # ============================
    elif step == 7:

        base = form["base"]
        version = form["version"]

        github_url = f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO}/tree/master/{base}/{version}"
        docker_url = f"https://hub.docker.com/r/{DOCKERHUB_ORG}/{base}"

        st.markdown("""
        <style>
        .success-box {
            text-align: center;
            padding: 40px 20px;
            border-radius: 18px;
            background: linear-gradient(145deg, rgba(16,185,129,0.12), rgba(59,130,246,0.08));
            border: 1px solid rgba(16,185,129,0.25);
            animation: fadeInUp 0.6s ease;
        }

        .success-icon {
            font-size: 60px;
            margin-bottom: 10px;
        }

        .success-title {
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 10px;
        }

        .success-sub {
            font-size: 16px;
            opacity: 0.8;
            margin-bottom: 25px;
        }

        .info-box {
            margin-top: 20px;
            padding: 20px;
            border-radius: 12px;
            background: rgba(148,163,184,0.08);
            font-size: 14px;
        }

        .link-btn {
            display: inline-block;
            margin: 8px;
            padding: 10px 18px;
            border-radius: 10px;
            background: #3b82f6;
            color: white !important;
            text-decoration: none;
            font-weight: 500;
            transition: 0.2s;
        }

        .link-btn:hover {
            background: #2563eb;
            transform: translateY(-2px);
        }

        .secondary-btn {
            background: #10b981;
        }

        .secondary-btn:hover {
            background: #059669;
        }
        </style>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="success-box">
            <div class="success-icon">✅</div>
            <div class="success-title">Submission Completed</div>
            <div class="success-sub">
                Your image <b>{base}:{version}</b> was successfully updated and submitted
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()


# ----------------------------
# BDIP TOOLS
# ----------------------------
elif st.session_state.current_page == "BDIP Tools":
    
    col1, col2 = st.columns([7,1])
    
    with col1:
        st.header("BDIP Tools")
    
    with col2:
        st.markdown("<div style='height: 12px'></div>", unsafe_allow_html=True)
        # Button Back to Home
        if st.button("← Back to Home"):
            change_page("Home")

    project_path = BDIP_DOCKERFILES_PATH or os.getcwd()

    config_path = os.path.join(project_path, ".config.ini")
    dockerfiles_path = os.path.join(project_path, "dockerfiles")
    tools_folder = os.path.join(project_path, "bdip_tools_folder")

    os.makedirs(dockerfiles_path, exist_ok=True)
    os.makedirs(tools_folder, exist_ok=True)

    user_args = st.text_input(
        "Arguments (optional)",
        placeholder="list-usual-commands"
    )

    if st.button("🛠️ Run BDIP Tools", key="run_bdip_tools"):

        # Create a visible area for the output immediately
        st.markdown("---")
        st.markdown("### 📋 Tools Output")
        output_box = st.empty()
        output_box.code("Initializing...", language="bash")

        try:
            st.info("🔍 Checking BDIP Tools image...")

            # =========================
            # CHECK IMAGE
            # =========================
            check = subprocess.run(
                ["docker", "image", "inspect", "pegi3s/bdip-tools"],
                capture_output=True,
                text=True
            )

            if check.returncode != 0:
                st.warning("⚠️ Image not found locally. Pulling...")

                pull = subprocess.Popen(
                    ["docker", "pull", "pegi3s/bdip-tools"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )

                logs = ""

                for line in pull.stdout:
                    logs += line
                    output_box.code(logs)

                pull.wait()

                if pull.returncode != 0:
                    if "network is unreachable" in logs:
                        st.error("🌐 Network error: Docker cannot reach DockerHub (IPv6 issue)")
                    else:
                        st.error("❌ Failed to pull BDIP Tools image")

                    st.stop()

                st.success("✅ Image pulled successfully")

            else:
                st.success("✅ Image already available")

            # =========================
            # RUN CONTAINER
            # =========================
            st.info("Running BDIP Tools...")
            
            uid = os.getuid()
            gid = os.getgid()

            docker_gid_cmd = subprocess.run(
                "getent group docker | cut -d: -f3",
                shell=True,
                capture_output=True,
                text=True
            )

            docker_gid = docker_gid_cmd.stdout.strip() or "999"

            cmd = [
                "docker", "run", "--rm",
                "--group-add", f"{BDIP_HOST_DOCKER_GROUP}",
                "--user", f"{BDIP_HOST_USER_ID}:{BDIP_HOST_USER_GROUP}",
                "-v", "/var/run/docker.sock:/var/run/docker.sock",
                "-v", f"{BDIP_CONFIG_PATH}/.config.ini:/home/bdip-user/.config/bdip-tools/config.ini",
                "-v", f"{BDIP_DOCKERFILES_PATH}:{BDIP_DOCKERFILES_PATH}",
                "-v", f"{BDIP_RESULTS_PATH}:/results",
                "-v", "/home/bdip-user/.cache/bdip-tools:/home/bdip-user/.cache/bdip-tools",
                "-v", "/tmp:/tmp",        
                "-w", "/results",
                "pegi3s/bdip-tools"
            ]
            
            if user_args:
                cmd += shlex.split(user_args)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            # Re-using the same output_box defined above
            logs =" ".join(cmd) + "  " 
            #logs=""  

            for line in process.stdout:
                logs += line
                output_box.code(logs)

            process.wait()

            if process.returncode != 0:
                st.error("❌ BDIP Tools failed")
            else:
                st.success("✅ BDIP Tools finished successfully")

        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")

    st.divider()


# ----------------------------
# NEW IMAGE
# ----------------------------
if st.session_state.current_page == "New Image":
    
    col1, col2 = st.columns([7,1])
    
    with col1:
        st.header("Submit New Image")
    
    with col2:
        st.markdown("<div style='height: 12px'></div>", unsafe_allow_html=True)
        # Button Back to Home
        if st.button("← Back to Home"):
            if st.session_state.get("new_image_step", 0) == 8:
                reset_new_image()
                change_page("Home")
                st.rerun()
            else:
                st.session_state["show_new_image_dialog"] = True

    # ============================
    # SHOW DIALOG
    # ============================
    if st.session_state.get("show_new_image_dialog", False):
        show_unsaved_new_image_dialog()

    # ============================
    # INIT
    # ============================
    if "new_image_step" not in st.session_state:
        st.session_state.new_image_step = 0

    # ============================
    # HANDLE CLICK VIA QUERY PARAM
    # ============================
    params = st.query_params
    if "step" in params:
        try:
            new_step = int(params["step"])
            if 0 <= new_step <= 8:
                st.session_state.new_image_step = new_step
                st.query_params.clear()
                st.rerun()
        except:
            pass

    # ============================
    # STEP 0 - PROJECT TYPE
    # ============================
    if st.session_state.new_image_step == 0:
        
        # ============================
        # CSS
        # ============================
        st.markdown("""
        <style>

        .type-hero {
            padding: 38px;
            border-radius: 28px;
            margin-bottom: 28px;
            position: relative;
            overflow: hidden;

            background: linear-gradient(
                145deg,
                rgba(59,130,246,0.10),
                rgba(59,130,246,0.03)
            );

            border: 1px solid rgba(59,130,246,0.15);

            backdrop-filter: blur(10px);
        }

        .type-hero::before {
            content: "";
            position: absolute;
            top: -90px;
            right: -90px;

            width: 280px;
            height: 280px;

            border-radius: 50%;

            background: rgba(59,130,246,0.08);
        }

        .type-badge {
            display: inline-flex;
            align-items: center;
            gap: 10px;

            padding: 10px 18px;

            border-radius: 14px;

            background: rgba(59,130,246,0.12);

            color: #2563eb;

            font-size: 14px;
            font-weight: 700;

            margin-bottom: 14px;
        }

        .type-title {
            font-size: 36px;
            font-weight: 800;
            letter-spacing: -1px;

            margin-bottom: 12px;
        }

        .type-description {
            font-size: 15px;
            line-height: 1.7;
            color: #6b7280;

            max-width: 760px;
        }

        .card-button button {
            height: 240px !important;

            border-radius: 24px !important;

            border: 1px solid rgba(59,130,246,0.14) !important;

            background:
                linear-gradient(
                    145deg,
                    rgba(255,255,255,0.95),
                    rgba(248,250,252,0.90)
                ) !important;

            transition: all 0.25s ease !important;

            box-shadow:
                0 1px 2px rgba(0,0,0,0.04),
                0 10px 30px rgba(15,23,42,0.06);
        }

        .card-button button:hover {
            transform: translateY(-6px);

            border: 1px solid rgba(59,130,246,0.28) !important;

            box-shadow:
                0 10px 35px rgba(59,130,246,0.12);
        }

        .disabled-card button {
            opacity: 0.55;
        }

        .type-card {
            position: absolute;
            inset: 0;

            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: flex-start;

            padding: 28px;

            pointer-events: none;
        }

        .type-icon {
            width: 62px;
            height: 62px;

            border-radius: 18px;

            display: flex;
            align-items: center;
            justify-content: center;

            margin-bottom: 18px;

            background: linear-gradient(
                145deg,
                rgba(59,130,246,0.16),
                rgba(59,130,246,0.10)
            );

            color: #2563eb;

            font-size: 28px;
        }

        .type-card-title {
            font-size: 22px;
            font-weight: 700;

            margin-bottom: 10px;
        }

        .type-card-description {
            font-size: 14px;
            line-height: 1.7;

            color: #6b7280;
        }

        .coming-soon {
            margin-top: 18px;

            padding: 6px 12px;

            border-radius: 999px;

            background: rgba(59,130,246,0.10);

            color: #2563eb;

            font-size: 12px;
            font-weight: 700;
        }

        </style>
        """, unsafe_allow_html=True)

        # ============================
        # HERO
        # ============================
        st.markdown("""<div class="type-hero"><div class="type-badge">New Image Submission</div><div class="type-title">Select Project Type</div><div class="type-description">Choose the submission workflow for your new image. Available options depend on the project structure and configuration.</div></div>""", unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Regular", use_container_width=True):
                st.session_state.project_type = "regular"
                st.session_state.new_image_step = 1
                st.rerun()

        with col2:
            if st.button("From Image (with Dockerfile)", use_container_width=True):
                st.session_state.project_type = "from_image_with_df"
                st.session_state.new_image_step = 1
                st.rerun()

        with col3:
            st.button("From Image (without Dockerfile)", disabled=True, use_container_width=True)

        st.divider()

        st.stop()

    # ============================
    # STEPPER
    # ============================
    def render_stepper():

        steps = [
            ("project", "Project"),
            ("files", "Files"),
            ("metadata", "Metadata"),
            ("ontology", "Ontology"),
            ("github", "GitHub"),
            ("docker", "DockerHub"),
            ("test", "Test Data"),
            ("done", "Done"),
        ]

        current = st.session_state.new_image_step
        total = len(steps)
        progress = int((current - 1) / (total - 1) * 100)

        # CSS
        st.markdown(f"""
        <style>
        .stepper-wrapper {{
            position: relative;
            margin-bottom: 30px;
        }}

        .stepper {{
            display: grid;
            grid-template-columns: repeat(8, 1fr); /* nÃºmero de steps */
            align-items: center;
            position: relative;
            z-index: 2;
        }}

        .step {{
            text-align: center;
        }}

        .circle {{
            width: 42px;
            height: 42px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto;
            background: white;
            transition: all 0.25s ease;
            position: relative;
        }}

        .done {{
            background:#10b981;
            color:white;
        }}

        .active {{
            background:#3b82f6;
            color:white;
            transform: scale(1.15);
            box-shadow: 0 0 0 4px rgba(59,130,246,0.15);
        }}

        .todo {{
            background:#e5e7eb;
            color:#666;
        }}

        .label {{
            font-size:12px;
            margin-top:6px;
        }}

        .icon svg {{
            width:20px;
            height:20px;
            stroke:currentColor;
            fill:none;
            stroke-width:2;
            stroke-linecap:round;
            stroke-linejoin:round;
        }}

        .progress-line {{
            position: absolute;
            top: 21px;
            left: calc(100% / 8 / 2);
            right: calc(100% / 8 / 2);
            height: 6px;
            background: #e5e7eb;
            border-radius: 10px;
            z-index: 0;
        }}

        .progress-fill {{
            height: 100%;
            width: {progress}%;
            background: linear-gradient(90deg, #10b981, #2563eb);
            border-radius: 10px;
            transition: width 0.5s ease-in-out;
        }}

        .step:hover .circle {{
            transform: scale(1.15);
            box-shadow: 0 5px 15px rgba(59,130,246,0.25);
        }}
        </style>
        """, unsafe_allow_html=True)

        # SVG icons
        def icon(svg):
            return f'<div class="icon">{svg}</div>'

        ICONS = {
            "project": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M3 7l9-4 9 4-9 4-9-4z"/>
                <path d="M3 12l9 4 9-4"/>
                <path d="M3 17l9 4 9-4"/>
            </svg>
            '''),

            "ontology": icon('''
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <rect x="10" y="3" width="4" height="4" rx="1"/>
                <rect x="4" y="17" width="4" height="4" rx="1"/>
                <rect x="16" y="17" width="4" height="4" rx="1"/>
                <line x1="12" y1="7" x2="12" y2="12"/>
                <line x1="12" y1="12" x2="6" y2="17"/>
                <line x1="12" y1="12" x2="18" y2="17"/>
            </svg>
            '''),

            "test": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M3 7h6l2 2h10v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                <path d="M3 7V5a2 2 0 0 1 2-2h4l2 2h10a2 2 0 0 1 2 2"/>
                <path d="M8 13h8"/>
                <path d="M8 17h5"/>
            </svg>
            '''),

            "files": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M6 2h9l5 5v15H6z"/>
                <path d="M14 2v6h6"/>
            </svg>
            '''),

            "metadata": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M4 6h16"/>
                <path d="M4 12h16"/>
                <path d="M4 18h16"/>
            </svg>
            '''),

            "github": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M9 19c-4 1-4-2-6-3"/>
                <path d="M15 22v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 19 4.77 5.07 5.07 0 0 0 18.91 1S17.73.65 15 2.48a13.38 13.38 0 0 0-6 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77 5.44 5.44 0 0 0 3.5 8.52c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
            </svg>
            '''),

            "docker": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M3 7l9-4 9 4-9 4-9-4z"/>
                <path d="M3 7v10l9 4 9-4V7"/>
                <path d="M12 11v10"/>
                <path d="M16 13v4"/>
            </svg>
            '''),

            "done": icon('''
            <svg viewBox="0 0 24 24">
                <path d="M5 13l4 4L19 7"/>
            </svg>
            ''')
        }
        
        # HTML (no problematic indentation)
        html = f'<div class="stepper-wrapper"><div class="progress-line"><div class="progress-fill"></div></div><div class="stepper">'

        for i, (key, label) in enumerate(steps, 1):
            state = "done" if i < current else "active" if i == current else "todo"

            html += f'<div class="step"><div class="circle {state}">{ICONS[key]}</div><div class="label">{label}</div></div>'

        html += '</div></div>'

        st.markdown(html, unsafe_allow_html=True)

    render_stepper()
    st.divider()

    step = st.session_state.new_image_step

    # ============================
    # STEP 1 - PROJECT
    # ============================
    if step == 1:

        # ============================ 
        # HERO START 
        # ============================ 
        blue_css()
        st.markdown(""" <div class="step-section"> <div class="step-badge"> Project Selection </div> <div class="step-title"> Select Project </div> <div class="step-description"> Choose an existing project structure to submit a new Docker image. </div> <div class="form-card"> """, unsafe_allow_html=True)

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            # ============================
            # PROJECTS
            # ============================
            projects = [
                p.name for p in Path(BASE_PATH).iterdir()
                if p.is_dir() and (p / "for_submission").exists()
            ]

            project_options = ["-- Select --"] + projects

            selected_index = 0

            if st.session_state.get("project") in projects:
                selected_index = project_options.index(st.session_state.get("project"))

            selected_project = st.selectbox(
                "Project",
                project_options,
                index=selected_index
            )

            manual_project = st.text_input(
                "Or type project manually",
                value=st.session_state.get("manual_project", ""),
                placeholder="e.g. fastqc"
            )

            # SAVE STATE
            st.session_state.manual_project = manual_project

            if selected_project != "-- Select --":
                st.session_state.project = selected_project

            project = (
                manual_project.strip()
                if manual_project.strip()
                else st.session_state.get("project", "")
            )
            
            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # VALIDATIONS
            # ============================
            is_valid = False
            validation_error = None

            if project and project != "-- Select --":

                submission_dir = Path(BASE_PATH) / project / "for_submission"

                if not submission_dir.exists():

                    validation_error = "Invalid project (missing for_submission)"

                else:

                    base = re.sub(r"[-_]?v?\d+(\.\d+)*$", "", project)

                    try:

                        url = (
                            f"https://raw.githubusercontent.com/"
                            f"{GITHUB_REPO_OWNER}/{GITHUB_REPO}/master/metadata/metadata.json"
                        )

                        response = requests.get(url)
                        response.raise_for_status()

                        metadata_list = response.json()

                        exists_in_metadata = any(
                            item.get("name") == base
                            for item in metadata_list
                        )

                        if exists_in_metadata:
                            validation_error = (
                                f"❌ Image '{base}' already exists in metadata.\n\n"
                                "Use 'New Version Image' instead."
                            )
                        else:
                            is_valid = True

                    except Exception as e:

                        validation_error = f"Metadata validation failed: {e}"

            # ============================
            # VALIDATION MESSAGE
            # ============================
            if validation_error:
                st.error(validation_error)

            elif is_valid:
                st.success("Project validated successfully")

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # ACTIONS
            # ============================
            render_new_image_navigation(
                next_step=2,
                next_disabled=not is_valid
            )

            if is_valid:

                st.session_state.project = project
                st.session_state.base = base

    # ============================
    # STEP 2 - FILES
    # ============================
    elif step == 2:

        # ============================
        # HERO
        # ============================
        green_css()
        st.markdown("""<div class="step-section"><div class="step-badge">Files Review</div><div class="step-title">Files Preview</div><div class="step-description">Review the files included in your submission package, including Dockerfile and documentation.</div></div>""", unsafe_allow_html=True)

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            project = st.session_state.project
            submission_dir = Path(BASE_PATH) / project / "for_submission"

            files = [f for f in submission_dir.iterdir() if f.name != "test_data"]

            st.markdown("### Files in Submission")
            for f in files:
                st.write("-", f.name)
            
            st.markdown("<br>", unsafe_allow_html=True)

            dockerfile_path = submission_dir / "Dockerfile"
            if dockerfile_path.exists():
                with st.expander("Dockerfile"):
                    st.code(dockerfile_path.read_text(), language="dockerfile")

            readme_path = submission_dir / "README.md"
            if readme_path.exists():
                with st.expander("README"):
                    if st.button(
                        "Edit README ✏️",
                        key="edit_readme_btn"
                    ):
                        edit_readme_dialog(readme_path)
                        
                    st.markdown(readme_path.read_text())
                    
            readme_path = submission_dir / "README_dockerhub.md"
            if readme_path.exists():
                with st.expander("README DockerHub"):
                    st.markdown(readme_path.read_text())
            
            license_files = list(
                submission_dir.glob("LICENSE*")
            ) + list(
                submission_dir.glob("License*")
            ) + list(
                submission_dir.glob("license*")
            )
            
            if license_files:
                license_file = license_files[0]
                with st.expander("License"):
                    st.text(license_file.read_text())

            st.markdown("<br>", unsafe_allow_html=True)

            render_new_image_navigation(
                back_step=1,
                next_step=3,
                next_disabled=False
            )

    # ============================
    # STEP 3 - METADATA
    # ============================
    elif step == 3:

        # ============================
        # HERO
        # ============================
        yellow_css()
        st.markdown("""<div class="step-section"><div class="step-badge">Metadata Review</div><div class="step-title">Metadata Preview</div><div class="step-description">Review the metadata configuration for your Docker image.</div></div>""", unsafe_allow_html=True)

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            project = st.session_state.project
            path = Path(BASE_PATH) / project / "for_submission" / "metadata.json"

            if path.exists():
                with st.expander("Metadata Preview"):
                    if st.button(
                        "Edit Metadata ✏️",
                        key="edit_metadata_btn"
                    ):
                        edit_metadata_dialog(path)
                    
                    st.json(json.load(open(path)))
                    
            else:
                st.warning("No metadata.json")

            st.markdown("<br>", unsafe_allow_html=True)

            render_new_image_navigation(
                back_step=2,
                next_step=4,
                next_disabled=False
            )

    # ============================
    # STEP 4 - ONTOLOGY
    # ============================
    elif step == 4:

        # ============================
        # HERO
        # ============================
        orange_css()
        st.markdown("""<div class="step-section"><div class="step-badge">Ontology Terms</div><div class="step-title">Ontology Validation</div><div class="step-description">Review and validate the ontology terms associated with your image.</div></div>""", unsafe_allow_html=True)

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            project = st.session_state.project
            path = Path(BASE_PATH) / project / "for_submission" / "ontology.diaf"

            if not path.exists():
                st.warning("No ontology.diaf")
                st.session_state.ontology_has_suggestions = False
                
                st.markdown("<br>", unsafe_allow_html=True)
                render_new_image_navigation(
                    back_step=3,
                    next_step=5,
                    next_disabled=False
                )
                st.stop()

            content = path.read_text()

            # ============================
            # EXTRACT IDS + SUGGESTIONS
            # ============================
            ontology_ids = re.findall(r"(DIO:\d+)", content)
            suggestions = re.findall(r"SUGGESTION:\s*(.*)", content)

            # guardar estado global (IMPORTANTE)
            st.session_state.ontology_has_suggestions = len(suggestions) > 0

            # ============================
            # SUGGESTIONS UI (PRO)
            # ============================
            if suggestions:

                suggestions_html = "".join(
                    [f"<div class='suggestion-item'> - {s}</div>" for s in suggestions]
                )

                st.markdown(f"""
                <style>
                .suggestion-box {{
                    border-radius: 14px;
                    padding: 18px 20px;
                    border: 1px solid rgba(245,158,11,0.4);
                    background: linear-gradient(145deg, rgba(245,158,11,0.08), rgba(245,158,11,0.03));
                    margin-bottom: 15px;
                }}
                .suggestion-header {{
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    font-weight: 600;
                    font-size: 16px;
                    margin-bottom: 10px;
                }}
                .suggestion-badge {{
                    background: #f59e0b;
                    color: white;
                    font-size: 11px;
                    padding: 3px 8px;
                    border-radius: 6px;
                    font-weight: 600;
                }}
                .suggestion-list {{
                    margin-top: 12px;
                    font-size: 14px;
                }}
                .suggestion-item {{
                    margin-bottom: 4px;
                }}
                </style>

                <div class="suggestion-box">
                <div class="suggestion-header">
                ⚠️ Suggestions detected
                <span class="suggestion-badge">ACTION REQUIRED</span>
                </div>

                <div>
                Please validate ontology suggestions before continuing.
                </div>

                <div class="suggestion-list">
                {suggestions_html}
                </div>
                </div>
                """, unsafe_allow_html=True)

                if st.button("🔧 Open Web Manager"):
                    change_page("Home")

            # ============================
            # LOAD REMOTE ONTOLOGY
            # ============================
            try:
                ontology, relations, diaf_data = get_remote_dio_data()
            except Exception as e:
                st.error(f"Error loading ontology data: {e}")
                st.stop()

            # ============================
            # UI STYLE
            # ============================
            st.markdown("""
            <style>

            .ontology-card {
                border: 1px solid rgba(255,255,255,0.08);
                border-left: 6px solid;

                border-radius: 16px;

                padding: 14px 18px;
                margin-bottom: 14px;

                background: rgba(255,255,255,0.72);

                backdrop-filter: blur(10px);

                box-shadow:
                    0 1px 2px rgba(0,0,0,0.04),
                    0 6px 18px rgba(15,23,42,0.05);
            }

            .ontology-title {
                font-size: 18px;
                font-weight: 700;

                color: var(--text-color);
            }

            .ontology-id {
                font-size: 12px;

                color: rgba(107,114,128,0.9);

                margin-top: 2px;
            }

            /* ============================
            DARK MODE
            ============================ */

            [data-theme="dark"] .ontology-card {
                background: rgba(17,24,39,0.72);

                border: 1px solid rgba(255,255,255,0.06);

                box-shadow:
                    0 1px 2px rgba(0,0,0,0.3),
                    0 8px 24px rgba(0,0,0,0.25);
            }

            [data-theme="dark"] .ontology-title {
                color: #f8fafc;
            }

            [data-theme="dark"] .ontology-id {
                color: rgba(203,213,225,0.75);
            }

            </style>
            """, unsafe_allow_html=True)

            def get_style_from_path(path):
                if not path:
                    return "#9ca3af"
                return "#6b7280"

            # ============================
            # RENDER CARDS
            # ============================
            if ontology_ids:

                for oid in ontology_ids:

                    name = ontology.get(oid, "Unknown")
                    path_str = get_ontology_path(oid, ontology, relations)

                    color = get_style_from_path(path_str)

                    st.markdown(
                        f"""
                        <div class="ontology-card" style="border-left-color: {color};">
                            <div class="ontology-title">{name}</div>
                            <div class="ontology-id">{oid}</div>
                            {"<div style='margin-top:8px;'>🧬 <b>Path:</b> " + path_str + "</div>" if path_str else ""}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            else:
                st.warning("No ontology terms found in ontology.diaf")

            st.markdown("<br>", unsafe_allow_html=True)

            if st.button(
                "✏️ Edit Ontology Terms"
            ):
                edit_ontology_dialog(
                    path,
                    ontology,
                    ontology_ids,
                    relations
                )
            
            # ============================
            # NAVIGATION
            # ============================
            st.markdown("<br>", unsafe_allow_html=True)

            blocked = st.session_state.get("ontology_has_suggestions", False)

            render_new_image_navigation(
                back_step=3,
                next_step=5,
                next_disabled=blocked
            )
            
            if blocked:
                st.caption("🚫 Resolve suggestions to continue")

    # ============================
    # STEP 5 - GITHUB
    # ============================
    elif step == 5:

        # ============================
        # INIT SESSION STATE
        # ============================
        if "new_image_github_logs" not in st.session_state:
            st.session_state.new_image_github_logs = []

        if "github_done" not in st.session_state:
            st.session_state.github_done = False

        # ============================
        # HERO
        # ============================
        purple_css()
        st.markdown("""<div class="step-section"><div class="step-badge">GitHub Submission</div><div class="step-title">Submit to GitHub</div><div class="step-description">Push your Docker image configuration and files to the GitHub repository.</div></div>""", unsafe_allow_html=True)

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            # ============================
            # SUCCESS STATE
            # ============================
            if st.session_state.github_done:

                st.success(
                    "This image has already been submitted to GitHub."
                )

            # ============================
            # CONFIRMATION
            # ============================
            confirm = st.checkbox(
                "I confirm everything is correct",
                disabled=st.session_state.github_done
            )

            # ============================
            # LOG BOX
            # ============================
            log_box = st.empty()

            existing_logs = "\n".join(
                st.session_state.new_image_github_logs
            )

            if existing_logs:

                log_box.code(existing_logs)

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # PUSH BUTTON
            # ============================
            push_clicked = st.button(
                "Push to GitHub",
                disabled=st.session_state.github_done
            )

            if push_clicked:

                if not confirm:
                    st.error("Please confirm first")
                    st.stop()

                try:

                    # ============================
                    # LOG HELPER
                    # ============================
                    def add_log(message, level="INFO"):

                        line = f"[{level}] {message}"

                        st.session_state.new_image_github_logs.append(line)

                        log_box.code(
                            "\n".join(
                                st.session_state.new_image_github_logs
                            )
                        )

                    add_log("Starting GitHub push", "STEP")

                    repo_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO}.git"
                    
                    with tempfile.TemporaryDirectory() as tmpdir:

                        repo_path = Path(tmpdir)

                        add_log("Cloning repository", "INFO")

                        subprocess.run(
                            ["git", "clone", "--depth", "1", repo_url, str(repo_path)],
                            check=True
                        )

                        project = st.session_state.project
                        submission_dir = Path(BASE_PATH) / project / "for_submission"

                        metadata_path = submission_dir / "metadata.json"

                        if not metadata_path.exists():
                            st.error("metadata.json not found in for_submission")
                            st.stop()

                        metadata_local = json.load(open(metadata_path))

                        base = metadata_local.get("name")
                        version = metadata_local.get("latest")

                        if not base or not version:
                            st.error("metadata.json must contain 'name' and 'latest'")
                            st.stop()

                        target_path = repo_path / base / version

                        target_path.mkdir(
                            parents=True,
                            exist_ok=True
                        )

                        add_log(
                            f"Copying files to {base}/{version}",
                            "INFO"
                        )

                        EXCLUDE = {
                            "test_data",
                            "metadata.json",
                            "ontology.diaf"
                        }

                        def silent_copy(src, dst):

                            if src.is_file():

                                shutil.copy(src, dst)

                            else:

                                shutil.copytree(
                                    src,
                                    dst,
                                    dirs_exist_ok=True
                                )

                        for item in submission_dir.iterdir():

                            if item.name in EXCLUDE:
                                continue

                            silent_copy(
                                item,
                                target_path / item.name
                            )

                        add_log("Merging metadata.json", "INFO")

                        remote_metadata_path = (
                            repo_path
                            / "metadata"
                            / "metadata.json"
                        )

                        local_metadata_path = (
                            submission_dir
                            / "metadata.json"
                        )

                        if (
                            local_metadata_path.exists()
                            and remote_metadata_path.exists()
                        ):

                            remote_metadata = json.load(
                                open(remote_metadata_path)
                            )

                            local_metadata = json.load(
                                open(local_metadata_path)
                            )

                            base_name = local_metadata.get("name")

                            found = False

                            for item in remote_metadata:

                                if item.get("name") == base_name:

                                    add_log(
                                        f"Updating metadata for {base_name}",
                                        "INFO"
                                    )

                                    item.update(local_metadata)

                                    found = True

                                    break

                            if not found:

                                add_log(
                                    f"Adding new metadata for {base_name}",
                                    "INFO"
                                )

                                remote_metadata.append(local_metadata)

                            json.dump(
                                remote_metadata,
                                open(remote_metadata_path, "w"),
                                indent=2
                            )

                        else:

                            add_log(
                                "Metadata merge skipped",
                                "WARNING"
                            )

                        add_log(
                            "Merging ontology (dio.diaf)",
                            "INFO"
                        )

                        local_ontology = (
                            submission_dir
                            / "ontology.diaf"
                        )

                        remote_ontology = (
                            repo_path
                            / "metadata"
                            / "dio.diaf"
                        )

                        if (
                            local_ontology.exists()
                            and remote_ontology.exists()
                        ):

                            project_name = base

                            remote_lines = set(
                                line.strip()
                                for line in remote_ontology.read_text().splitlines()
                                if line.strip()
                            )

                            new_entries = set()

                            for line in local_ontology.read_text().splitlines():

                                line = line.strip()

                                if not line or line.startswith("#"):
                                    continue

                                if line.startswith("SUGGESTION:"):
                                    continue

                                if line.startswith("DIO:"):

                                    term = line.split()[0]

                                    new_entries.add(
                                        f"{term}\t{project_name}"
                                    )

                            merged = sorted(
                                remote_lines.union(new_entries)
                            )

                            remote_ontology.write_text(
                                "\n".join(merged) + "\n"
                            )

                            add_log(
                                f"Added {len(new_entries)} ontology terms",
                                "SUCCESS"
                            )

                        else:

                            add_log(
                                "Ontology merge skipped",
                                "WARNING"
                            )

                        subprocess.run(
                            [
                                "git",
                                "config",
                                "user.email",
                                GITHUB_EMAIL
                            ],
                            cwd=repo_path,
                            check=True
                        )

                        subprocess.run(
                            [
                                "git",
                                "config",
                                "user.name",
                                GITHUB_USER
                            ],
                            cwd=repo_path,
                            check=True
                        )

                        add_log(
                            "Committing changes",
                            "INFO"
                        )

                        subprocess.run(
                            ["git", "add", "--all"],
                            cwd=repo_path,
                            check=True
                        )

                        result = subprocess.run(
                            ["git", "status", "--porcelain"],
                            cwd=repo_path,
                            capture_output=True,
                            text=True
                        )

                        if not result.stdout.strip():

                            add_log(
                                "No changes to commit",
                                "WARNING"
                            )

                        else:

                            subprocess.run(
                                [
                                    "git",
                                    "commit",
                                    "-m",
                                    f"Add {base} version {version}"
                                ],
                                cwd=repo_path,
                                check=True
                            )

                            add_log(
                                "Pushing to GitHub",
                                "INFO"
                            )

                            subprocess.run(
                                [
                                    "git",
                                    "push",
                                    "origin",
                                    "master"
                                ],
                                cwd=repo_path,
                                check=True
                            )

                            add_log(
                                "GitHub push completed",
                                "SUCCESS"
                            )

                            st.success(
                                "Successfully pushed"
                            )

                            st.session_state.github_done = True

                            st.rerun()

                except subprocess.CalledProcessError as e:

                    add_log(str(e), "ERROR")

                    st.error("Git command failed")

                except Exception as e:

                    add_log(str(e), "ERROR")

                    st.error("Unexpected error")

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # NAVIGATION
            # ============================
            render_new_image_navigation(
                back_step=4,
                next_step=6,
                next_disabled=not st.session_state.github_done
            )

    # ============================
    # STEP 6 - DOCKER
    # ============================
    elif step == 6:

        # ============================
        # INIT SESSION STATE
        # ============================
        if "new_image_docker_logs" not in st.session_state:
            st.session_state.new_image_docker_logs = []

        if "docker_done" not in st.session_state:
            st.session_state.docker_done = False

        # ============================
        # HERO
        # ============================
        blue_2_css()
        st.markdown("""<div class="step-section"><div class="step-badge">DockerHub Submission</div><div class="step-title">Push to DockerHub</div><div class="step-description">Build and push your Docker image to DockerHub with automated README submission.</div></div>""", unsafe_allow_html=True)

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            project = st.session_state.project

            submission_dir = (
                Path(BASE_PATH)
                / project
                / "for_submission"
            )

            metadata_local = json.load(
                open(submission_dir / "metadata.json")
            )

            base = metadata_local.get("name")
            version = metadata_local.get("latest")

            image_src = f"pegi3s/{base}:{version}"

            image_dst_version = (
                f"{DOCKERHUB_ORG}/{base}:{version}"
            )

            image_dst_latest = (
                f"{DOCKERHUB_ORG}/{base}:latest"
            )

            # ============================
            # SUCCESS STATE
            # ============================
            if st.session_state.docker_done:

                st.success(
                    "This image has already been pushed to DockerHub."
                )

            # ============================
            # CONFIRMATION
            # ============================
            confirm = st.checkbox(
                "I confirm Docker image is ready",
                disabled=st.session_state.docker_done
            )

            # ============================
            # LOG BOX
            # ============================
            log_box = st.empty()

            existing_logs = "\n".join(
                st.session_state.new_image_docker_logs
            )

            if existing_logs:

                log_box.code(existing_logs)

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # PUSH BUTTON
            # ============================
            push_clicked = st.button(
                "Push to DockerHub",
                disabled=st.session_state.docker_done
            )

            if push_clicked:

                if not confirm:

                    st.error("Please confirm first")

                    st.stop()

                try:

                    # ============================
                    # LOG HELPER
                    # ============================
                    def add_log(message, level="INFO"):

                        line = f"[{level}] {message}"

                        st.session_state.new_image_docker_logs.append(
                            line
                        )

                        log_box.code(
                            "\n".join(
                                st.session_state.new_image_docker_logs
                            )
                        )

                    # ============================
                    # START
                    # ============================
                    add_log(
                        "Starting Docker process",
                        "STEP"
                    )

                    result = subprocess.run(
                        ["docker", "images", "-q", image_src],
                        capture_output=True,
                        text=True
                    )

                    if not result.stdout.strip():

                        add_log(
                            "Image not found locally, building",
                            "INFO"
                        )

                        build = subprocess.run(
                            [
                                "docker",
                                "build",
                                "-t",
                                image_src,
                                str(submission_dir)
                            ],
                            capture_output=True,
                            text=True
                        )

                        if build.returncode != 0:

                            st.error("Build failed")

                            st.code(build.stderr)

                            add_log(
                                "Docker build failed",
                                "ERROR"
                            )

                            st.stop()

                        add_log(
                            "Image built successfully",
                            "SUCCESS"
                        )

                    else:

                        add_log(
                            "Local image found",
                            "INFO"
                        )

                    # ============================
                    # LOGIN
                    # ============================
                    add_log(
                        "Logging into DockerHub",
                        "INFO"
                    )

                    login = subprocess.run(
                        [
                            "docker",
                            "login",
                            "-u",
                            docker_user,
                            "--password-stdin"
                        ],
                        input=docker_token,
                        capture_output=True,
                        text=True
                    )

                    if login.returncode != 0:

                        st.error("Docker login failed")

                        add_log(
                            "Docker login failed",
                            "ERROR"
                        )

                        st.stop()

                    add_log(
                        "Login successful",
                        "SUCCESS"
                    )

                    # ============================
                    # TAGGING
                    # ============================
                    add_log(
                        "Tagging images",
                        "INFO"
                    )

                    subprocess.run(
                        [
                            "docker",
                            "tag",
                            image_src,
                            image_dst_version
                        ],
                        check=True
                    )

                    subprocess.run(
                        [
                            "docker",
                            "tag",
                            image_src,
                            image_dst_latest
                        ],
                        check=True
                    )

                    # ============================
                    # PUSH VERSION
                    # ============================
                    add_log(
                        "Pushing version",
                        "INFO"
                    )

                    subprocess.run(
                        [
                            "docker",
                            "push",
                            image_dst_version
                        ],
                        check=True
                    )

                    # ============================
                    # PUSH LATEST
                    # ============================
                    add_log(
                        "Pushing latest",
                        "INFO"
                    )

                    subprocess.run(
                        [
                            "docker",
                            "push",
                            image_dst_latest
                        ],
                        check=True
                    )

                    add_log(
                        "Docker push completed",
                        "SUCCESS"
                    )

                    st.success(
                        "DockerHub push successful"
                    )

                    # ============================
                    # README SUBMIT
                    # ============================
                    readme_path = (
                        submission_dir
                        / "README.md"
                    )

                    if readme_path.exists():

                        add_log(
                            "Submitting DockerHub README",
                            "STEP"
                        )

                        auth = requests.post(
                            "https://hub.docker.com/v2/users/login/",
                            json={
                                "username": docker_user,
                                "password": docker_token
                            }
                        )

                        if auth.status_code != 200:

                            add_log(
                                "DockerHub API authentication failed",
                                "ERROR"
                            )

                            st.stop()

                        token = auth.json().get("token")

                        readme_content = (
                            readme_path.read_text()
                        )

                        repo_url = (
                            f"https://hub.docker.com/v2/repositories/{DOCKERHUB_ORG}/{base}/"
                        )

                        headers = {
                            "Authorization": f"JWT {token}",
                            "Content-Type": "application/json"
                        }

                        data = {
                            "full_description": readme_content
                        }

                        response = requests.patch(
                            repo_url,
                            headers=headers,
                            json=data
                        )

                        add_log(
                            "Submitting DockerHub README",
                            "STEP"
                        )

                        if response.status_code == 200:

                            add_log(
                                "README submitted to DockerHub",
                                "SUCCESS"
                            )

                        else:

                            add_log(
                                f"README submission failed: {response.text}",
                                "ERROR"
                            )

                    else:

                        add_log(
                            "README.md not found (skipped)",
                            "WARNING"
                        )

                    # ============================
                    # SUCCESS
                    # ============================
                    st.success(
                        "README submit successful"
                    )

                    st.session_state.docker_done = True

                    st.rerun()

                except Exception as e:

                    add_log(str(e), "ERROR")

                    st.error("Unexpected error")

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # NAVIGATION
            # ============================
            render_new_image_navigation(
                back_step=5,
                next_step=7,
                next_disabled=not st.session_state.docker_done
            )


    # ============================
    # STEP 7 - TEST DATA
    # ============================
    elif step == 7:

        # ============================
        # INIT SESSION STATE
        # ============================
        if "test_data_logs" not in st.session_state:
            st.session_state.test_data_logs = []

        if "test_data_done" not in st.session_state:
            st.session_state.test_data_done = False

        # ============================
        # HERO
        # ============================
        green_css()

        st.markdown(
            """<div class="step-section"><div class="step-badge">Test Validation</div><div class="step-title">Test Data</div><div class="step-description">Upload validation datasets to Evolution6 for automated testing and reproducibility verification.</div></div>""",
            unsafe_allow_html=True
        )

        # ============================
        # FORM CONTAINER
        # ============================
        form_container = st.container(border=True)

        with form_container:

            project = st.session_state.project

            submission_dir = (
                Path(BASE_PATH)
                / project
                / "for_submission"
            )

            test_data_dir = (
                submission_dir
                / "test_data"
            )

            metadata = json.load(
                open(submission_dir / "metadata.json")
            )

            # ============================
            # HELPERS
            # ============================
            def extract_filename(url):

                return (
                    url.split("/")[-1]
                    if url else None
                )

            def remote_file_exists(remote_path):
                
                result = subprocess.run(
                    [
                        "sshpass", "-p", REMOTE_PASS,
                        "ssh",
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "UserKnownHostsFile=/dev/null",
                        f"{REMOTE_USER}@{REMOTE_HOST}",
                        f'test -e "{remote_path}"'
                    ],
                    capture_output=True,
                    text=True
                )

                return result.returncode == 0


            def upload_file(local_path, remote_path):

                subprocess.run(
                    [
                        "sshpass", "-p", REMOTE_PASS,
                        "scp",
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "UserKnownHostsFile=/dev/null",
                        str(local_path),
                        f"{REMOTE_USER}@{REMOTE_HOST}:{remote_path}"
                    ],
                    check=True
                )

            # ============================
            # FILES
            # ============================
            input_file = extract_filename(
                metadata.get("test_data_url")
            )

            output_file = extract_filename(
                metadata.get("test_results_url")
            )

            # ============================
            # SUCCESS STATE
            # ============================
            if st.session_state.test_data_done:

                st.success(
                    "Test data has already been uploaded."
                )

            # ============================
            # CONFIRMATION
            # ============================
            confirm = st.checkbox(
                "I confirm test data is ready",
                disabled=st.session_state.test_data_done
            )

            # ============================
            # LOG BOX
            # ============================
            log_box = st.empty()

            existing_logs = "\n".join(
                st.session_state.test_data_logs
            )

            if existing_logs:

                log_box.code(existing_logs)

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # UPLOAD BUTTON
            # ============================
            upload_clicked = st.button(
                "Upload to Evolution6",
                disabled=st.session_state.test_data_done
            )

            if upload_clicked:

                if not confirm:

                    st.error(
                        "Please confirm first"
                    )

                    st.stop()

                try:

                    # ============================
                    # LOG HELPER
                    # ============================
                    def add_log(message, level="INFO"):

                        line = f"[{level}] {message}"

                        st.session_state.test_data_logs.append(line)

                        log_box.code(
                            "\n".join(
                                st.session_state.test_data_logs
                            )
                        )

                    # ============================
                    # START
                    # ============================
                    add_log(
                        "Starting test data upload",
                        "STEP"
                    )

                    # ============================
                    # INPUT FILE
                    # ============================
                    if input_file:

                        local_input = (
                            test_data_dir
                            / "input_test_data"
                            / input_file
                        )

                        remote_input = (
                            f"{REMOTE_DIR}/input_test_data/{input_file}"
                        )

                        if local_input.exists():

                            add_log(
                                f"Checking remote input file: {input_file}"
                            )

                            if remote_file_exists(remote_input):

                                add_log(
                                    f"Input file already exists on server: {input_file}",
                                    "INFO"
                                )

                            else:

                                add_log(
                                    f"Uploading input file: {input_file}"
                                )

                                upload_file(
                                    local_input,
                                    remote_input
                                )

                                add_log(
                                    f"Uploaded input file {input_file}",
                                    "SUCCESS"
                                )

                        else:

                            add_log(
                                f"Input file not found: {input_file}",
                                "ERROR"
                            )

                    # ============================
                    # OUTPUT FILE
                    # ============================
                    if output_file:

                        local_output = (
                            test_data_dir
                            / "output_test_data"
                            / output_file
                        )

                        remote_output = (
                            f"{REMOTE_DIR}/output_test_data/{output_file}"
                        )

                        if local_output.exists():

                            add_log(
                                f"Checking remote output file: {output_file}"
                            )

                            if remote_file_exists(remote_output):

                                add_log(
                                    f"Output file already exists on server: {output_file}",
                                    "INFO"
                                )

                            else:

                                add_log(
                                    f"Uploading output file: {output_file}"
                                )

                                upload_file(
                                    local_output,
                                    remote_output
                                )

                                add_log(
                                    f"Uploaded output file {output_file}",
                                    "SUCCESS"
                                )

                        else:

                            add_log(
                                f"Output file not found: {output_file}",
                                "ERROR"
                            )

                    # ============================
                    # SUCCESS
                    # ============================
                    add_log(
                        "Test data upload completed",
                        "SUCCESS"
                    )

                    st.success(
                        "Upload completed"
                    )

                    st.session_state.test_data_done = True

                    st.rerun()

                except subprocess.CalledProcessError as e:

                    add_log(
                        str(e),
                        "ERROR"
                    )

                    st.error(
                        "SCP upload failed"
                    )

                except Exception as e:

                    add_log(
                        str(e),
                        "ERROR"
                    )

                    st.error(
                        "Unexpected error"
                    )

            st.markdown("<br>", unsafe_allow_html=True)

            # ============================
            # NAVIGATION
            # ============================
            render_new_image_navigation(
                back_step=6,
                next_step=8,
                next_disabled=not st.session_state.get(
                    "test_data_done",
                    False
                )
            )

    # ============================
    # STEP 8 - DONE
    # ============================
    elif step == 8:

        # ============================
        # CSS
        # ============================
        st.markdown("""
        <style>

        .step-section {
            padding: 34px;
            border-radius: 26px;
            margin-bottom: 25px;
            position: relative;
            overflow: hidden;

            background: linear-gradient(
                145deg,
                rgba(16,185,129,0.12),
                rgba(52,211,153,0.04)
            );

            border: 1px solid rgba(16,185,129,0.18);

            backdrop-filter: blur(10px);
        }

        .step-section::before {
            content: "";
            position: absolute;
            top: -80px;
            right: -80px;

            width: 260px;
            height: 260px;

            border-radius: 50%;

            background: rgba(52,211,153,0.10);
        }

        .success-box {
            text-align: center;
            padding: 40px 20px;
            border-radius: 18px;
            background: linear-gradient(145deg, rgba(16,185,129,0.12), rgba(59,130,246,0.08));
            border: 1px solid rgba(16,185,129,0.25);
        }

        .success-icon {
            font-size: 60px;
        }

        .success-title {
            font-size: 28px;
            font-weight: 700;
            margin-top: 10px;
        }

        .success-sub {
            opacity: 0.8;
            margin-top: 10px;
        }

        </style>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="success-box">
            <div class="success-icon">✅</div>
            <div class="success-title">Submission Completed</div>
            <div class="success-sub">
                Project <b>{st.session_state.project}</b> is successfully submitted
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Submit Another"):
            st.session_state.new_image_step = 0
            st.rerun()

    st.divider()


# ----------------------------
# TEST DOCKER IMAGE
# ----------------------------
elif st.session_state.current_page == "Test Docker Image":
    col1, col2 = st.columns([7,1])
    
    with col1:
        st.header("⚙️ Build & Test (Submission Package)")
    
    with col2:
        st.markdown("<div style='height: 12px'></div>", unsafe_allow_html=True)
        # Button Back to Home
        if st.button("← Back to Home"):
            change_page("Home")

    # -------------------------------------------------
    # PROJECT SELECTION
    # -------------------------------------------------

    projects_root = Path(BASE_PATH)

    available_projects = [
        p.name
        for p in projects_root.iterdir()
        if p.is_dir() and (p / "for_submission").exists()
    ]

    selected_project = st.selectbox(
        "Select project", ["-- Select --"] + available_projects
    )

    manual_project = st.text_input("Or type project name manually")

    project = manual_project.strip() if manual_project else selected_project

    if not project or project == "-- Select --":
        st.warning("Please select or enter a project")
        st.stop()

    submission_dir = Path(BASE_PATH) / project / "for_submission"

    if not submission_dir.exists():
        st.error(f"Project '{project}' does not contain a for_submission folder")
        st.stop()

    st.session_state.active_project = project

    st.success(f"Using project: {project}")

    # -------------------------------------------------
    # PATHS
    # -------------------------------------------------

    dockerfile_path = submission_dir / "Dockerfile"
    metadata_path = submission_dir / "metadata.json"

    input_dir = submission_dir / "test_data" / "input_test_data"
    output_dir = submission_dir / "test_data" / "output_test_data"

    missing_items = []

    if not dockerfile_path.exists():
        missing_items.append("Dockerfile")
    
    # -------------------------------------------------
    # LOAD METADATA
    # -------------------------------------------------

    metadata = None

    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            st.success("Loaded metadata from submission folder")
        except Exception as e:
            st.warning(f"Failed to read local metadata: {e}")
            st.stop()

    def split_project_name(project_name):
        """
        Ex: clustalomega-2.5.0 → ("clustalomega", "2.5.0")
        """
        match = re.match(r"(.+)-(\d+\.\d+.*)", project_name)

        if match:
            base = match.group(1)
            version = match.group(2)
            return base, version

        return project_name, None

    if not metadata:
        st.warning("No metadata from submission folder")
        st.info("Fetching metadata from GitHub...")

        try:
            base, version = split_project_name(project)

            st.caption(f"Detected base: {base} | version: {version}")

            metadata = get_project_metadata(base)

            if metadata:
                st.success("Metadata loaded from GitHub")
            else:
                st.warning("Failed to fetch metadata from GitHub")
                missing_items.append("metadata (local or GitHub)")

        except Exception as e:
            st.error(f"Error fetching metadata: {e}")
            st.stop()
    
    if missing_items:
        st.error(
            "❌ **Cannot Build and Test Docker Image**\n\n"
            "This feature requires the following:\n\n"
            "- Dockerfile in the for_submission folder\n"
            "- metadata.json (locally or available on GitHub)\n\n"
            f"Missing: {', '.join(missing_items)}\n\n"
            "Please ensure all required files are available before continuing."
        )
        
        st.warning("⚠️ Projects of type **'From Image (without Dockerfile)'** do not support build or test.")
        
        st.stop()

    # -------------------------------------------------
    # BUILD IMAGE
    # -------------------------------------------------

    st.subheader("Build Image")

    if st.button("🚀 Build Docker Image"):
        if not dockerfile_path.exists():
            st.error("Dockerfile not found.")
            st.stop()

        build_cmd = [
            "docker",
            "build",
            "-t",
            f"pegi3s/{project.lower()}",
            str(submission_dir),
        ]

        st.info("Starting Docker build...")

        progress_bar = st.progress(0)
        status_text = st.empty()

        log_lines = []

        process = subprocess.Popen(
            build_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )

        progress = 0

        while True:
            line = process.stdout.readline()

            if not line:
                break

            log_lines.append(line)

            progress = min(progress + 1, 95)
            progress_bar.progress(progress)

            status_text.text(line.strip())

        process.wait()
        progress_bar.progress(100)

        full_log = "".join(log_lines)

        with st.expander("📄 Build Log"):
            st.code(full_log)

        if process.returncode == 0:
            st.success("✅ Docker image built successfully!")
        else:
            st.error("❌ Build failed")
            st.code("\n".join(log_lines[-20:]))

    st.divider()

    # -------------------------------------------------
    # INPUT FILES
    # -------------------------------------------------

    st.subheader("Available Input Files")

    if input_dir.exists():
        files = list(input_dir.iterdir())

        if files:
            for f in files:
                st.write("📄", f.name)
        else:
            st.warning("No input files found")
    else:
        st.warning("Input folder not found")

    # -------------------------------------------------
    # COMMAND LOGIC
    # -------------------------------------------------

    def build_command_from_metadata(metadata):
        general = metadata.get("invocation_general", "")
        specific = metadata.get("test_invocation_specific", "")
        return f"{general}{specific}".strip()

    def normalize_paths(command):
        command = command.replace("/data/test/data/", str(input_dir.resolve()) + "/")
        command = command.replace(
            "/data/test/results/", str(output_dir.resolve()) + "/"
        )
        return command

    def adapt_docker_invocation(invocation):
        container_name = socket.gethostname()

        # substitui volumes -v ...:/data → --volumes-from
        invocation = re.sub(
            r"-v\s+\S+:/data", f"--volumes-from {container_name}", invocation
        )

        return invocation

    # -------------------------------------------------
    # COMMAND UI
    # -------------------------------------------------

    st.subheader("Execution Command")

    if st.button("🔎 Load command from metadata"):
        cmd = build_command_from_metadata(metadata)

        if cmd:
            st.session_state.run_command = cmd
            st.success("Command loaded from metadata.json")
        else:
            st.error("Missing invocation_general")

    run_command = st.text_area(
        "Docker Command", value=st.session_state.get("run_command", ""), height=120
    )

    # -------------------------------------------------
    # RUN TEST
    # -------------------------------------------------

    if st.button("🚀 Run Test"):
        if not run_command:
            st.error("Provide a command.")
            st.stop()

        cmd = adapt_docker_invocation(run_command)
        docker_cmd = normalize_paths(cmd)

        # st.code(docker_cmd)

        progress_bar = st.progress(0)
        status_text = st.empty()

        log_lines = []

        process = subprocess.Popen(
            docker_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        progress = 0

        for line in iter(process.stdout.readline, ""):
            log_lines.append(line.rstrip())

            progress = min(progress + 1, 100)
            progress_bar.progress(progress)

            status_text.text(line.strip())

        process.wait()

        # -------------------------------------------------
        # RESULT
        # -------------------------------------------------

        if process.returncode == 0:
            st.success("✅ Test completed!")

        else:
            st.error("❌ Test failed")

            with st.expander("📄 Logs"):
                st.code("\n".join(log_lines))

