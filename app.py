import streamlit as st
import base64
from pathlib import Path


# --------------------------------------------------
# Page Configuration
# --------------------------------------------------

st.set_page_config(
    page_title="Farmora",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded"
)


# --------------------------------------------------
# Background Image
# --------------------------------------------------

image_path = Path("assets/cornfield.jpg")

if image_path.exists():

    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image:
                linear-gradient(
                    rgba(0, 0, 0, 0.25),
                    rgba(0, 0, 0, 0.50)
                ),
                url("data:image/jpeg;base64,{encoded}");

            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )


# --------------------------------------------------
# Custom CSS
# --------------------------------------------------

st.markdown(
    """
    <style>

    /* Main container */
    .block-container {
        padding-top: 2rem;
    }

    /* Transparent sidebar */
    section[data-testid="stSidebar"] {
        background: rgba(15, 17, 22, 0.50);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
    }

    /* Navigation title */
    [data-testid="stSidebarNav"] {
        padding-top: 60px;
    }

    [data-testid="stSidebarNav"]::before {
        content: "Navigation";
        display: block;
        text-align: center;
        color: white;
        font-size: 23px;
        font-weight: 600;
        margin-bottom: 25px;
    }

    /* Navigation box */
    [data-testid="stSidebarNav"] ul {
        background: rgba(5, 7, 12, 0.92);
        border-radius: 5px;
        padding: 12px 10px;
    }

    /* Navigation items */
    [data-testid="stSidebarNav"] a {
        color: #eeeeee !important;
        border-radius: 6px;
        padding: 10px 15px !important;
        font-size: 16px !important;
    }

    /* Hover */
    [data-testid="stSidebarNav"] a:hover {
        background: rgba(255,255,255,0.08) !important;
        color: white !important;
    }

    /* Active page */
    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background: #ff3b4f !important;
        color: white !important;
        font-weight: 600;
    }

    /* Sidebar footer */
    section[data-testid="stSidebar"]::after {
        content: "Made with ♥ by Chirag";
        position: fixed;
        bottom: 35px;
        left: 28px;
        color: white;
        font-size: 14px;
    }

    /* Hero */
    .hero {
        text-align: center;
        color: white;
        margin-top: 110px;
        text-shadow: 0 2px 8px rgba(0,0,0,0.7);
    }

    .hero h1 {
        font-size: 44px;
        font-weight: 700;
        line-height: 1.25;
    }

    .hero p {
        font-size: 24px;
        font-weight: 600;
        margin-top: 25px;
    }

    /* Glass card */
    .glass-card {
        background: rgba(10, 12, 17, 0.78);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 30px;
        color: white;
        max-width: 900px;
        margin: 70px auto;
    }

    .glass-card h1,
    .glass-card h2,
    .glass-card h3 {
        color: white;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# --------------------------------------------------
# Pages
# --------------------------------------------------

home_page = st.Page(
    "pages/home.py",
    title="Home",
    icon=":material/home:",
    default=True
)

predict_page = st.Page(
    "pages/predict.py",
    title="Predict",
    icon=":material/analytics:"
)

about_page = st.Page(
    "pages/about.py",
    title="About",
    icon=":material/info:"
)

help_page = st.Page(
    "pages/help.py",
    title="Help",
    icon=":material/help:"
)

# Hidden result page
result_page = st.Page(
    "pages/result.py",
    title="Results",
    icon=":material/assessment:",
    visibility="hidden"
)


# --------------------------------------------------
# Navigation
# --------------------------------------------------

pg = st.navigation([
    home_page,
    about_page,
    help_page,
    predict_page,
    result_page
])

pg.run()