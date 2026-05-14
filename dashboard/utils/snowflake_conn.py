import pandas as pd
import snowflake.connector
import streamlit as st


@st.cache_resource
def get_snowflake_conn():
    """One Snowflake connection per Streamlit session. Reads from st.secrets."""
    return snowflake.connector.connect(
        user=st.secrets["snowflake"]["user"],
        password=st.secrets["snowflake"]["password"],
        account=st.secrets["snowflake"]["account"],
        warehouse=st.secrets["snowflake"]["warehouse"],
        database="NYC_311",
        schema="MARTS",
        role=st.secrets["snowflake"]["role"],
    )


@st.cache_data(ttl=3600)
def run_query(sql: str) -> pd.DataFrame:
    conn = get_snowflake_conn()
    df = pd.read_sql(sql, conn)
    # Snowflake returns uppercase column names — lowercase them for consistent
    # access in all dashboard pages (e.g. df["complaint_type"] not df["COMPLAINT_TYPE"])
    df.columns = [c.lower() for c in df.columns]
    return df
