import time
import streamlit as st
from step6_full_pipeline import (
    get_articles_by_keyword,
    get_top_doctors,
    generate_doctor_summary,
    search_pubmed,
    fetch_article_details,
    parse_articles,
    save_articles_to_db,
    chunk_list,
    EFETCH_BATCH_SIZE,
    signup_user,
    login_user,
)

st.set_page_config(page_title="Healthcare Data Solutions", layout="wide")

# -----------------------------------------------------------------------
# DARK THEME
# Streamlit doesn't have a built-in "dark mode toggle" you can call from
# code -- the clean way to reskin the app is to inject raw CSS using
# st.markdown with unsafe_allow_html=True. This CSS overrides Streamlit's
# default colors, fonts, and card styling app-wide.
# -----------------------------------------------------------------------
st.markdown("""
<style>
    /* Overall app background + text color */
    .stApp {
        background-color: #0e1117;
        color: #e6e6e6;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #131722;
        border-right: 1px solid #262730;
    }

    /* Headings */
    h1, h2, h3, h4 {
        color: #f0f2f6;
        font-weight: 600;
    }

    /* Card containers (st.container(border=True)) */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #171b26;
        border: 1px solid #2a2f3d;
        border-radius: 10px;
    }

    /* Buttons */
    .stButton > button {
        background-color: #2563eb;
        color: white;
        border: none;
        border-radius: 6px;
        font-weight: 500;
    }
    .stButton > button:hover {
        background-color: #1d4ed8;
        color: white;
    }

    /* Text inputs */
    .stTextInput > div > div > input {
        background-color: #1a1e2a;
        color: #e6e6e6;
        border: 1px solid #2a2f3d;
    }

    /* Tabs */
    button[data-baseweb="tab"] {
        color: #9ca3af;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #60a5fa;
    }

    /* Links inside article titles */
    a {
        color: #60a5fa !important;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------
# SESSION STATE SETUP
# Streamlit reruns your ENTIRE script from top to bottom every time the
# user clicks anything. Normal variables would reset every time -- so we
# use st.session_state, a special dictionary that Streamlit keeps alive
# across reruns, to remember "is someone logged in right now?"
# -----------------------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None


def show_login_page():
    st.markdown("<br>", unsafe_allow_html=True)
    st.title("🩺 Healthcare Data Solutions")
    st.caption("Search PubMed research and discover leading doctors by topic. Please log in or create an account to continue.")

    login_tab, signup_tab = st.tabs(["Log In", "Sign Up"])

    with login_tab:
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")

        if st.button("Log In"):
            if login_user(username, password):
                # Update session_state -- this is what "remembers" the login
                # on the NEXT rerun (which happens automatically after this click)
                st.session_state.logged_in = True
                st.session_state.username = username
                st.rerun()  # immediately re-run the script so the gate below lets them through
            else:
                st.error("Invalid username or password.")

    with signup_tab:
        new_username = st.text_input("Choose a username", key="signup_username")
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Choose a password", type="password", key="signup_password")

        if st.button("Sign Up"):
            if not new_username or not new_email or not new_password:
                st.warning("Please fill in all fields.")
            else:
                success, message = signup_user(new_username, new_email, new_password)
                if success:
                    st.success(message + " You can now log in from the Log In tab.")
                else:
                    st.error(message)


# -----------------------------------------------------------------------
# THE GATE: if not logged in, show ONLY the login page and stop here.
# Everything below this block is the real app, and never runs unless
# st.session_state.logged_in is True.
# -----------------------------------------------------------------------
if not st.session_state.logged_in:
    show_login_page()
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("Healthcare Data Solutions")
    st.write(f"Logged in as **{st.session_state.username}**")
    if st.button("Log Out"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.rerun()
    st.divider()
    st.write(
        "Search PubMed for healthcare research articles by keyword "
        "(disease, symptom, or medical domain), and see which doctors "
        "publish most on that topic."
    )
    st.caption("Data source: PubMed (NCBI E-utilities)")

st.title("Search Healthcare Research")

keyword = st.text_input("Enter a keyword (e.g. Diabetes, Cancer, Asthma)")

if st.button("Search"):
    if not keyword.strip():
        st.warning("Please enter a keyword first.")
        st.stop()

    articles = get_articles_by_keyword(keyword)

    if articles:
        st.success(f"Loaded {len(articles)} saved articles for '{keyword}' from the database.")
    else:
        st.info(f"No saved data yet for '{keyword}'. Fetching fresh from PubMed...")

        pmid_list = search_pubmed(keyword)
        if not pmid_list:
            st.error("No results found on PubMed for that keyword.")
            st.stop()

        # Same batching logic as step6_full_pipeline.py's main() -- fetch in
        # chunks instead of one giant request, and show progress as we go.
        all_articles = []
        batches = list(chunk_list(pmid_list, EFETCH_BATCH_SIZE))
        progress_bar = st.progress(0, text="Fetching article details...")

        for batch_number, pmid_batch in enumerate(batches, start=1):
            time.sleep(0.4)
            xml_data = fetch_article_details(pmid_batch)
            if xml_data:
                all_articles.extend(parse_articles(xml_data))
            progress_bar.progress(batch_number / len(batches), text=f"Batch {batch_number}/{len(batches)}")

        progress_bar.empty()  # remove the progress bar once done

        if not all_articles:
            st.error("Failed to fetch article details from PubMed.")
            st.stop()

        save_articles_to_db(all_articles, keyword)
        articles = all_articles
        st.success(f"Fetched and saved {len(articles)} new articles for '{keyword}'.")

    # -----------------------------------------------------------------------
    # Two tabs: Top Doctors (the headline feature) and full Article list
    # -----------------------------------------------------------------------
    tab_doctors, tab_articles = st.tabs(["Top 10 Doctors", f"All Articles ({len(articles)})"])

    with tab_doctors:
        top_doctors = get_top_doctors(keyword, top_n=10)

        if not top_doctors:
            st.write("No author data available for this keyword yet.")
        else:
            st.caption(
                f"Ranked by number of saved '{keyword}' articles each doctor has authored. "
                "Summaries are AI-generated from real article titles (RAG)."
            )
            for rank, (name, count, titles) in enumerate(top_doctors, start=1):
                with st.container(border=True):
                    # A little visual reward for the top 3 -- purely cosmetic,
                    # doesn't change the ranking logic at all.
                    badge = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
                    st.markdown(f"**{badge} &nbsp; {name}** &mdash; {count} article(s)")

                    # This is the RAG step: generate_doctor_summary() sends this
                    # doctor's real titles to Gemini and gets back a grounded
                    # 1-2 sentence explanation, instead of us guessing.
                    # st.spinner shows a small "thinking" indicator while we wait.
                    with st.spinner("Generating summary..."):
                        summary = generate_doctor_summary(name, titles, keyword)
                    st.write(summary)

                    with st.expander("Show article titles"):
                        for t in titles:
                            st.write(f"- {t}")

    with tab_articles:
        for article in articles:
            with st.container(border=True):
                if article["doi"] != "Not Available":
                    doi_url = f"https://doi.org/{article['doi']}"
                    st.markdown(f"#### [{article['title']}]({doi_url})")
                else:
                    st.markdown(f"#### {article['title']}")

                st.write(f"**Authors:** {article['authors']}")
                st.write(f"**Journal:** {article['journal']}  |  **Date:** {article['pub_date']}")

                with st.expander("Show abstract"):
                    st.write(article["abstract"])