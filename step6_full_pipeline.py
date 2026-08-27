import requests
import xml.etree.ElementTree as ET
import time
from google import genai
import mysql.connector

from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("PUBMED_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

RECORDS_PER_FETCH = 350  # how many PMIDs to search for per keyword
EFETCH_BATCH_SIZE = 100  # how many articles to fetch details for per request (PubMed can be unreliable with huge batches)


# ---------------------------------------------------------------------------
# This is Step 2's logic, wrapped in a function + wrapped in try/except.
# Why a function? So "main" (at the bottom) can just say search_pubmed(keyword)
# instead of repeating all this code.
# Why try/except? If your wifi drops, or PubMed's server is down, requests.get()
# will raise an exception and CRASH your program unless we catch it.
# ---------------------------------------------------------------------------
def search_pubmed(keyword):
    """Returns a list of PMIDs matching the keyword. Returns [] on failure."""
    params = {
        "db": "pubmed",
        "term": keyword,
        "retmax": RECORDS_PER_FETCH,
        "retmode": "json",
        "api_key": API_KEY,
    }

    try:
        response = requests.get(ESEARCH_URL, params=params, timeout=15)
        response.raise_for_status()  # turns bad HTTP status codes (404, 500...) into an exception
    except requests.exceptions.RequestException as error:
        # This catches: no internet, timeout, DNS failure, bad status code, etc.
        print(f"[ERROR] Could not reach PubMed search API: {error}")
        return []

    try:
        data = response.json()
        return data["esearchresult"]["idlist"]
    except (KeyError, ValueError) as error:
        # This catches: PubMed replied, but not in the shape we expected
        print(f"[ERROR] Unexpected response format: {error}")
        return []


# ---------------------------------------------------------------------------
# Small reusable helper: splits one big list into smaller chunks.
# e.g. chunk_list([1,2,3,4,5], 2) -> [[1,2], [3,4], [5]]
# We need this because sending 500 PMIDs in a single efetch request is risky
# (huge URL, huge response, higher chance of timeout) -- so we fetch in
# smaller batches instead, one batch at a time.
# ---------------------------------------------------------------------------
def chunk_list(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ---------------------------------------------------------------------------
# This is Step 3's logic. The only change from Step 3: instead of one pmid,
# we join a whole LIST of pmids into one comma-separated string, so PubMed
# sends back all 50 records in a single response.
# ---------------------------------------------------------------------------
def fetch_article_details(pmid_list):
    """Fetches raw XML for a list of PMIDs in one request. Returns None on failure."""
    if not pmid_list:
        return None

    params = {
        "db": "pubmed",
        "id": ",".join(pmid_list),  # e.g. "123,456,789" -- PubMed accepts a batch this way
        "retmode": "xml",
        "api_key": API_KEY,
    }

    try:
        response = requests.get(EFETCH_URL, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        print(f"[ERROR] Could not reach PubMed fetch API: {error}")
        return None

    return response.text


# ---------------------------------------------------------------------------
# This is Steps 4 + 5's logic, but now in a LOOP over every <PubmedArticle>
# tag found in the XML (previously there was only ever one).
# ---------------------------------------------------------------------------
def parse_articles(xml_text):
    """Parses raw XML into a list of article dictionaries."""
    articles = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        print(f"[ERROR] Failed to parse XML: {error}")
        return articles

    # root.findall(".//PubmedArticle") gets EVERY article record in the batch,
    # not just one -- this is the key difference from Steps 4/5.
    for article_node in root.findall(".//PubmedArticle"):
        record = {}

        pmid_el = article_node.find(".//PMID")
        record["pmid"] = pmid_el.text if pmid_el is not None else "Not Available"

        title_el = article_node.find(".//ArticleTitle")
        record["title"] = title_el.text if title_el is not None else "Not Available"

        authors = []
        for author_el in article_node.findall(".//AuthorList/Author"):
            last = author_el.find("LastName")
            fore = author_el.find("ForeName")
            if last is not None:
                name = last.text
                if fore is not None:
                    name += f" {fore.text}"
                authors.append(name)
        record["authors"] = ", ".join(authors) if authors else "Not Available"

        journal_el = article_node.find(".//Journal/Title")
        record["journal"] = journal_el.text if journal_el is not None else "Not Available"

        pub_date_el = article_node.find(".//Journal/JournalIssue/PubDate")
        if pub_date_el is not None:
            year_el = pub_date_el.find("Year")
            month_el = pub_date_el.find("Month")
            medline_el = pub_date_el.find("MedlineDate")
            if year_el is not None:
                pub_date = year_el.text
                if month_el is not None:
                    pub_date += f" {month_el.text}"
            elif medline_el is not None:
                pub_date = medline_el.text
            else:
                pub_date = "Not Available"
        else:
            pub_date = "Not Available"
        record["pub_date"] = pub_date

        abstract_parts = []
        for ab_el in article_node.findall(".//Abstract/AbstractText"):
            text = ab_el.text or ""
            label = ab_el.get("Label")
            abstract_parts.append(f"{label}: {text}" if label else text)
        record["abstract"] = " ".join(abstract_parts) if abstract_parts else "Not Available"

        doi = "Not Available"
        for id_el in article_node.findall(".//ArticleIdList/ArticleId"):
            if id_el.get("IdType") == "doi":
                doi = id_el.text
                break
        record["doi"] = doi

        articles.append(record)

    return articles


def display_articles(articles):
    """Prints all articles neatly, one after another."""
    print(f"\nFound {len(articles)} article(s)\n{'=' * 80}")
    for i, art in enumerate(articles, start=1):
        print(f"\n--- Article {i} ---")
        print(f"PMID    : {art['pmid']}")
        print(f"Title   : {art['title']}")
        print(f"Authors : {art['authors']}")
        print(f"Journal : {art['journal']}")
        print(f"Date    : {art['pub_date']}")
        print(f"DOI     : {art['doi']}")
        abstract = art["abstract"]
        if len(abstract) > 300:
            abstract = abstract[:300] + "..."  # trim long abstracts for readability
        print(f"Abstract: {abstract}")
        print("-" * 80)

def save_articles_to_db(articles, keyword):
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password=MYSQL_PASSWORD,
        database="healthcare_data_solutions"
    )
    cursor = connection.cursor()

    insert_query = """
        INSERT IGNORE INTO articles
        (pmid, title, authors, journal, pub_date, abstract, doi, search_keyword)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    saved_count = 0
    for article in articles:
        values = (
            article["pmid"],
            article["title"],
            article["authors"],
            article["journal"],
            article["pub_date"],
            article["abstract"],
            article["doi"],
            keyword,
        )
        cursor.execute(insert_query, values)
        saved_count += 1

    connection.commit()
    cursor.close()
    connection.close()

    print(f"Saved {saved_count} articles to the database.")


import bcrypt


def signup_user(username, email, password):
    """
    Creates a new user account. Returns (True, "message") on success,
    or (False, "message") if something went wrong (e.g. username taken).
    """
    # bcrypt needs bytes, not a plain string -- .encode() converts str -> bytes.
    # gensalt() creates a random "salt" so identical passwords don't produce
    # identical hashes (an extra layer of protection).
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password=MYSQL_PASSWORD,
        database="healthcare_data_solutions"
    )
    cursor = connection.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (username, email, password_hash.decode()),  # store the hash as a string
        )
        connection.commit()
        return True, "Account created successfully."
    except mysql.connector.errors.IntegrityError:
        # This fires when the UNIQUE constraint on username/email is violated
        return False, "That username or email is already taken."
    finally:
        # finally always runs, whether we succeeded or hit the except block --
        # guarantees we always close the connection, no matter what happened.
        cursor.close()
        connection.close()


def login_user(username, password):
    """
    Checks a username/password against the database.
    Returns True if valid, False otherwise.
    """
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password=MYSQL_PASSWORD,
        database="healthcare_data_solutions"
    )
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()  # None if no matching username found

    cursor.close()
    connection.close()

    if user is None:
        return False  # no such username

    # bcrypt.checkpw compares the plain password against the stored hash --
    # it re-hashes the input internally and checks if it matches, without
    # us ever needing to "un-hash" the stored one (which isn't possible anyway).
    stored_hash = user["password_hash"].encode()
    return bcrypt.checkpw(password.encode(), stored_hash)

def get_articles_by_keyword(keyword):
    """Fetches all previously saved articles for a given keyword from MySQL."""
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password=MYSQL_PASSWORD,
        database="healthcare_data_solutions"
    )
    # dictionary=True makes each row come back as a dict (like {"pmid": ..., "title": ...})
    # instead of a plain tuple -- much easier to work with, especially in Streamlit later.
    cursor = connection.cursor(dictionary=True)

    select_query = "SELECT * FROM articles WHERE search_keyword = %s"
    cursor.execute(select_query, (keyword,))

    results = cursor.fetchall()  # grabs ALL matching rows as a list

    cursor.close()
    connection.close()

    return results

def get_top_doctors(keyword, top_n=10):
    """
    Ranks authors by how many saved articles they appear on for a given keyword.
    Returns a list of (author_name, article_count, [list of article titles]) tuples.
    """
    articles = get_articles_by_keyword(keyword)  # reuse what we already built

    # This dict will map: author_name -> list of article titles they appear in
    author_articles = {}

    for article in articles:
        if article["authors"] == "Not Available":
            continue  # skip articles with no author data

        for author in article["authors"].split(", "):
            if author not in author_articles:
                author_articles[author] = []
            author_articles[author].append(article["title"])

    # Turn the dict into a list of (name, count, titles) so we can sort it
    ranked = []
    for author, titles in author_articles.items():
        ranked.append((author, len(titles), titles))

    # Sort by count, highest first
    ranked.sort(key=lambda entry: entry[1], reverse=True)

    return ranked[:top_n]


# ---------------------------------------------------------------------------
# THE "GENERATION" PART OF RAG.
# We already RETRIEVED real data (this doctor's actual article titles from
# our own database). Now we hand that real data to an AI model and ask it
# to summarize/reason over it -- instead of the AI guessing from nothing.
# ---------------------------------------------------------------------------
def generate_doctor_summary(doctor_name, article_titles, keyword):
    """
    Uses Gemini to write a short 1-2 sentence summary of a doctor's apparent
    research focus, based on their real article titles. Returns a fallback
    message if the AI call fails, so the app never crashes because of this.
    """
    # Join the titles into one block of text to feed the model as context.
    # We cap it at 10 titles -- plenty of signal, keeps the prompt small and fast.
    titles_text = "\n".join(f"- {t}" for t in article_titles[:10])

    prompt = f"""You are helping summarize a doctor's research focus based on real PubMed article titles.

Doctor: {doctor_name}
Search keyword: {keyword}
Article titles by this doctor:
{titles_text}

In 1-2 short sentences, describe what this doctor appears to specialize in in relation to "{keyword}",
based only on the titles above. Be factual and concise. Do not invent details not suggested by the titles."""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.6-flash",  # current fast, free-tier friendly model
            contents=prompt,
        )
        return response.text.strip()
    except Exception as error:
        # If the AI call fails for any reason (rate limit, network, bad key),
        # we don't want that to crash the whole app -- just show a plain fallback.
        print(f"[WARNING] Gemini summary failed for {doctor_name}: {error}")
        return f"{doctor_name} has published {len(article_titles)} article(s) related to '{keyword}'."


# ---------------------------------------------------------------------------
# MAIN: this is the "story" of the program, told using the functions above.
# Notice how readable this is -- each line says WHAT is happening, and the
# HOW is hidden away inside the function. This is why we split into functions.
# ---------------------------------------------------------------------------
def main():
    keyword = input("Enter a healthcare-related keyword: ").strip()
    if not keyword:
        print("[ERROR] No keyword entered.")
        return

    print(f"\nSearching PubMed for '{keyword}' ...")
    pmid_list = search_pubmed(keyword)
    if not pmid_list:
        print("No results found, or the search failed.")
        return

    print(f"Found {len(pmid_list)} PMIDs. Fetching full details in batches of {EFETCH_BATCH_SIZE}...")

    all_articles = []

    # chunk_list splits our big pmid_list into smaller lists we can safely
    # send to efetch one at a time, instead of all 500 in one giant request.
    batches = list(chunk_list(pmid_list, EFETCH_BATCH_SIZE))

    for batch_number, pmid_batch in enumerate(batches, start=1):
        print(f"  Fetching batch {batch_number}/{len(batches)} ({len(pmid_batch)} articles)...")
        time.sleep(0.4)  # small pause between requests, polite to NCBI's servers

        xml_data = fetch_article_details(pmid_batch)
        if not xml_data:
            print(f"  [WARNING] Batch {batch_number} failed, skipping it.")
            continue  # move on to the next batch instead of stopping the whole program

        batch_articles = parse_articles(xml_data)
        all_articles.extend(batch_articles)  # add this batch's articles to our running total

    print(f"\nSuccessfully fetched {len(all_articles)} articles total.")
    display_articles(all_articles)
    save_articles_to_db(all_articles, keyword)


if __name__ == "__main__":
    main()
