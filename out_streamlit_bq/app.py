import streamlit as st
import pandas as pd
import altair as alt
from google.cloud import bigquery

CHART_QUERIES = {
    "total_funding_kpi": """SELECT SUM(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause}""",
    "total_deals_kpi": """SELECT COUNT(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause}""",
    "bar_by_industry": """SELECT industry AS x, SUM(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY industry ORDER BY y DESC""",
    "pie_by_stage": """SELECT stage AS x, COUNT(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY stage ORDER BY x ASC""",
    "line_over_time": """SELECT funding_date AS x, SUM(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY funding_date ORDER BY x ASC""",
    "scatter_funding_vs_valuation": """SELECT funding_amount AS x, valuation AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} AND funding_amount IS NOT NULL AND valuation IS NOT NULL""",
    "geo_by_country": """SELECT country AS x, SUM(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY country ORDER BY x ASC""",
    "top_countries": """SELECT country AS x, SUM(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY country ORDER BY y DESC LIMIT 10""",
}

CHART_STATIC_CONDITIONS = {
    'total_funding_kpi': [],
    'total_deals_kpi': [],
    'bar_by_industry': [],
    'pie_by_stage': [],
    'line_over_time': [],
    'scatter_funding_vs_valuation': [],
    'geo_by_country': [],
    'top_countries': [],
}

ALLOWED_FILTER_FIELDS = frozenset(set())

DERIVED_COLUMN_TYPES = {}

# BigQuery credentials and project are loaded from environment variables
# (DASHML_BQ_PROJECT, DASHML_BQ_CREDENTIALS).
# See SECRETS.md and .env.example next to this file.
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ID = os.environ.get("DASHML_BQ_PROJECT", "big-data-project-sn")

_BQ_CREDENTIALS = os.environ.get("DASHML_BQ_CREDENTIALS")
if _BQ_CREDENTIALS:
    from google.oauth2 import service_account
    _credentials = service_account.Credentials.from_service_account_file(
        _BQ_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    client = bigquery.Client(credentials=_credentials, project=PROJECT_ID)
else:
    client = bigquery.Client(project=PROJECT_ID)

DERIVED_CTE = """"""
DERIVED_FILTER_SOURCE = "`big-data-project-sn.sales.orders`"

@st.cache_data(ttl=300)
def run_query(query_name, filter_clause="1=1"):
    try:
        query = CHART_QUERIES[query_name].format(filter_clause=filter_clause)
        return client.query(query).to_dataframe()
    except Exception as e:
        st.error(f"Query failed: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filter_options(field):
    """Fetch DISTINCT values for a dashboard filter field."""
    try:
        query = DERIVED_CTE + " SELECT DISTINCT " + field + " FROM " + DERIVED_FILTER_SOURCE + " WHERE " + field + " IS NOT NULL ORDER BY 1 LIMIT 500"
        result = client.query(query).to_dataframe()
        return sorted(result.iloc[:, 0].dropna().astype(str).tolist())
    except Exception as e:
        return []

def build_filter_clause(chart_id, dashboard_filters):
    """Build SQL WHERE body from static per-chart conditions + runtime dashboard filters."""
    conditions = ["1=1"]
    conditions.extend(CHART_STATIC_CONDITIONS.get(chart_id, []))
    for field, values in dashboard_filters.items():
        if field not in ALLOWED_FILTER_FIELDS:
            continue
        if not values:
            continue
        escaped = [str(v).replace("'", "''") for v in values]
        if len(escaped) == 1:
            conditions.append(field + " = '" + escaped[0] + "'")
        else:
            in_list = ", ".join("'" + v + "'" for v in escaped)
            conditions.append(field + " IN (" + in_list + ")")
    return " AND ".join(conditions)

@st.cache_data(ttl=3600)
def get_column_types():
    try:
        query = """
            SELECT column_name, data_type
            FROM `big-data-project-sn.sales.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = 'orders'
        """
        results = client.query(query).to_dataframe()
        type_mapping = {}
        for _, row in results.iterrows():
            col_name = row["column_name"]
            data_type = row["data_type"].upper()
            if data_type in ("DATE", "DATETIME", "TIMESTAMP", "TIME"):
                type_mapping[col_name] = "date"
            elif data_type in ("INT64", "FLOAT64", "NUMERIC", "BIGNUMERIC", "INT", "INTEGER",
                             "SMALLINT", "BIGINT", "FLOAT", "DECIMAL", "REAL", "DOUBLE"):
                type_mapping[col_name] = "number"
            else:
                type_mapping[col_name] = "string"
        type_mapping.update(DERIVED_COLUMN_TYPES)
        return type_mapping
    except Exception as e:
        return {}

_ISO2_TO_TOPO = {'AF': 'Afghanistan', 'AL': 'Albania', 'DZ': 'Algeria', 'AO': 'Angola', 'AR': 'Argentina', 'AM': 'Armenia', 'AU': 'Australia', 'AT': 'Austria', 'AZ': 'Azerbaijan', 'BS': 'Bahamas', 'BD': 'Bangladesh', 'BY': 'Belarus', 'BE': 'Belgium', 'BZ': 'Belize', 'BJ': 'Benin', 'BT': 'Bhutan', 'BO': 'Bolivia', 'BA': 'Bosnia and Herz.', 'BW': 'Botswana', 'BR': 'Brazil', 'BN': 'Brunei', 'BG': 'Bulgaria', 'BF': 'Burkina Faso', 'BI': 'Burundi', 'KH': 'Cambodia', 'CM': 'Cameroon', 'CA': 'Canada', 'CF': 'Central African Rep.', 'TD': 'Chad', 'CL': 'Chile', 'CN': 'China', 'CO': 'Colombia', 'CG': 'Congo', 'CR': 'Costa Rica', 'CI': "Côte d'Ivoire", 'HR': 'Croatia', 'CU': 'Cuba', 'CY': 'Cyprus', 'CZ': 'Czechia', 'CD': 'Dem. Rep. Congo', 'DK': 'Denmark', 'DJ': 'Djibouti', 'DO': 'Dominican Rep.', 'EC': 'Ecuador', 'EG': 'Egypt', 'SV': 'El Salvador', 'GQ': 'Eq. Guinea', 'ER': 'Eritrea', 'EE': 'Estonia', 'SZ': 'eSwatini', 'ET': 'Ethiopia', 'FK': 'Falkland Is.', 'FJ': 'Fiji', 'FI': 'Finland', 'FR': 'France', 'GA': 'Gabon', 'GM': 'Gambia', 'GE': 'Georgia', 'DE': 'Germany', 'GH': 'Ghana', 'GR': 'Greece', 'GL': 'Greenland', 'GT': 'Guatemala', 'GN': 'Guinea', 'GW': 'Guinea-Bissau', 'GY': 'Guyana', 'HT': 'Haiti', 'HN': 'Honduras', 'HU': 'Hungary', 'IS': 'Iceland', 'IN': 'India', 'ID': 'Indonesia', 'IR': 'Iran', 'IQ': 'Iraq', 'IE': 'Ireland', 'IL': 'Israel', 'IT': 'Italy', 'JM': 'Jamaica', 'JP': 'Japan', 'JO': 'Jordan', 'KZ': 'Kazakhstan', 'KE': 'Kenya', 'KW': 'Kuwait', 'KG': 'Kyrgyzstan', 'LA': 'Laos', 'LV': 'Latvia', 'LB': 'Lebanon', 'LS': 'Lesotho', 'LR': 'Liberia', 'LY': 'Libya', 'LT': 'Lithuania', 'LU': 'Luxembourg', 'MK': 'Macedonia', 'MG': 'Madagascar', 'MW': 'Malawi', 'MY': 'Malaysia', 'ML': 'Mali', 'MR': 'Mauritania', 'MX': 'Mexico', 'MD': 'Moldova', 'MN': 'Mongolia', 'ME': 'Montenegro', 'MA': 'Morocco', 'MZ': 'Mozambique', 'MM': 'Myanmar', 'NA': 'Namibia', 'NP': 'Nepal', 'NL': 'Netherlands', 'NC': 'New Caledonia', 'NZ': 'New Zealand', 'NI': 'Nicaragua', 'NE': 'Niger', 'NG': 'Nigeria', 'KP': 'North Korea', 'NO': 'Norway', 'OM': 'Oman', 'PK': 'Pakistan', 'PS': 'Palestine', 'PA': 'Panama', 'PG': 'Papua New Guinea', 'PY': 'Paraguay', 'PE': 'Peru', 'PH': 'Philippines', 'PL': 'Poland', 'PT': 'Portugal', 'PR': 'Puerto Rico', 'QA': 'Qatar', 'RO': 'Romania', 'RU': 'Russia', 'RW': 'Rwanda', 'SA': 'Saudi Arabia', 'SN': 'Senegal', 'RS': 'Serbia', 'SL': 'Sierra Leone', 'SI': 'Slovenia', 'SB': 'Solomon Is.', 'SO': 'Somalia', 'ZA': 'South Africa', 'KR': 'South Korea', 'SS': 'S. Sudan', 'ES': 'Spain', 'LK': 'Sri Lanka', 'SD': 'Sudan', 'SR': 'Suriname', 'SE': 'Sweden', 'CH': 'Switzerland', 'SY': 'Syria', 'TW': 'Taiwan', 'TJ': 'Tajikistan', 'TZ': 'Tanzania', 'TH': 'Thailand', 'TL': 'Timor-Leste', 'TG': 'Togo', 'TT': 'Trinidad and Tobago', 'TN': 'Tunisia', 'TR': 'Turkey', 'TM': 'Turkmenistan', 'UG': 'Uganda', 'UA': 'Ukraine', 'AE': 'United Arab Emirates', 'GB': 'United Kingdom', 'US': 'United States of America', 'UY': 'Uruguay', 'UZ': 'Uzbekistan', 'VU': 'Vanuatu', 'VE': 'Venezuela', 'VN': 'Vietnam', 'EH': 'W. Sahara', 'YE': 'Yemen', 'ZM': 'Zambia', 'ZW': 'Zimbabwe', 'XK': 'Kosovo'}
_ISO3_TO_TOPO = {'AFG': 'Afghanistan', 'ALB': 'Albania', 'DZA': 'Algeria', 'AGO': 'Angola', 'ARG': 'Argentina', 'ARM': 'Armenia', 'AUS': 'Australia', 'AUT': 'Austria', 'AZE': 'Azerbaijan', 'BHS': 'Bahamas', 'BGD': 'Bangladesh', 'BLR': 'Belarus', 'BEL': 'Belgium', 'BLZ': 'Belize', 'BEN': 'Benin', 'BTN': 'Bhutan', 'BOL': 'Bolivia', 'BIH': 'Bosnia and Herz.', 'BWA': 'Botswana', 'BRA': 'Brazil', 'BRN': 'Brunei', 'BGR': 'Bulgaria', 'BFA': 'Burkina Faso', 'BDI': 'Burundi', 'KHM': 'Cambodia', 'CMR': 'Cameroon', 'CAN': 'Canada', 'CAF': 'Central African Rep.', 'TCD': 'Chad', 'CHL': 'Chile', 'CHN': 'China', 'COL': 'Colombia', 'COG': 'Congo', 'CRI': 'Costa Rica', 'CIV': "Côte d'Ivoire", 'HRV': 'Croatia', 'CUB': 'Cuba', 'CYP': 'Cyprus', 'CZE': 'Czechia', 'COD': 'Dem. Rep. Congo', 'DNK': 'Denmark', 'DJI': 'Djibouti', 'DOM': 'Dominican Rep.', 'ECU': 'Ecuador', 'EGY': 'Egypt', 'SLV': 'El Salvador', 'GNQ': 'Eq. Guinea', 'ERI': 'Eritrea', 'EST': 'Estonia', 'SWZ': 'eSwatini', 'ETH': 'Ethiopia', 'FLK': 'Falkland Is.', 'FJI': 'Fiji', 'FIN': 'Finland', 'FRA': 'France', 'GAB': 'Gabon', 'GMB': 'Gambia', 'GEO': 'Georgia', 'DEU': 'Germany', 'GHA': 'Ghana', 'GRC': 'Greece', 'GRL': 'Greenland', 'GTM': 'Guatemala', 'GIN': 'Guinea', 'GNB': 'Guinea-Bissau', 'GUY': 'Guyana', 'HTI': 'Haiti', 'HND': 'Honduras', 'HUN': 'Hungary', 'ISL': 'Iceland', 'IND': 'India', 'IDN': 'Indonesia', 'IRN': 'Iran', 'IRQ': 'Iraq', 'IRL': 'Ireland', 'ISR': 'Israel', 'ITA': 'Italy', 'JAM': 'Jamaica', 'JPN': 'Japan', 'JOR': 'Jordan', 'KAZ': 'Kazakhstan', 'KEN': 'Kenya', 'KWT': 'Kuwait', 'KGZ': 'Kyrgyzstan', 'LAO': 'Laos', 'LVA': 'Latvia', 'LBN': 'Lebanon', 'LSO': 'Lesotho', 'LBR': 'Liberia', 'LBY': 'Libya', 'LTU': 'Lithuania', 'LUX': 'Luxembourg', 'MKD': 'Macedonia', 'MDG': 'Madagascar', 'MWI': 'Malawi', 'MYS': 'Malaysia', 'MLI': 'Mali', 'MRT': 'Mauritania', 'MEX': 'Mexico', 'MDA': 'Moldova', 'MNG': 'Mongolia', 'MNE': 'Montenegro', 'MAR': 'Morocco', 'MOZ': 'Mozambique', 'MMR': 'Myanmar', 'NAM': 'Namibia', 'NPL': 'Nepal', 'NLD': 'Netherlands', 'NCL': 'New Caledonia', 'NZL': 'New Zealand', 'NIC': 'Nicaragua', 'NER': 'Niger', 'NGA': 'Nigeria', 'PRK': 'North Korea', 'NOR': 'Norway', 'OMN': 'Oman', 'PAK': 'Pakistan', 'PSE': 'Palestine', 'PAN': 'Panama', 'PNG': 'Papua New Guinea', 'PRY': 'Paraguay', 'PER': 'Peru', 'PHL': 'Philippines', 'POL': 'Poland', 'PRT': 'Portugal', 'PRI': 'Puerto Rico', 'QAT': 'Qatar', 'ROU': 'Romania', 'RUS': 'Russia', 'RWA': 'Rwanda', 'SAU': 'Saudi Arabia', 'SEN': 'Senegal', 'SRB': 'Serbia', 'SLE': 'Sierra Leone', 'SVN': 'Slovenia', 'SLB': 'Solomon Is.', 'SOM': 'Somalia', 'ZAF': 'South Africa', 'KOR': 'South Korea', 'SSD': 'S. Sudan', 'ESP': 'Spain', 'LKA': 'Sri Lanka', 'SDN': 'Sudan', 'SUR': 'Suriname', 'SWE': 'Sweden', 'CHE': 'Switzerland', 'SYR': 'Syria', 'TWN': 'Taiwan', 'TJK': 'Tajikistan', 'TZA': 'Tanzania', 'THA': 'Thailand', 'TLS': 'Timor-Leste', 'TGO': 'Togo', 'TTO': 'Trinidad and Tobago', 'TUN': 'Tunisia', 'TUR': 'Turkey', 'TKM': 'Turkmenistan', 'UGA': 'Uganda', 'UKR': 'Ukraine', 'ARE': 'United Arab Emirates', 'GBR': 'United Kingdom', 'USA': 'United States of America', 'URY': 'Uruguay', 'UZB': 'Uzbekistan', 'VUT': 'Vanuatu', 'VEN': 'Venezuela', 'VNM': 'Vietnam', 'ESH': 'W. Sahara', 'YEM': 'Yemen', 'ZMB': 'Zambia', 'ZWE': 'Zimbabwe', 'XKX': 'Kosovo'}
_ALIAS_TO_TOPO = {'usa': 'United States of America', 'united states': 'United States of America', 'uk': 'United Kingdom', 'britain': 'United Kingdom', 'great britain': 'United Kingdom', 'england': 'United Kingdom', 'russian federation': 'Russia', 'republic of korea': 'South Korea', 'korea': 'South Korea', 'korea, republic of': 'South Korea', 'dprk': 'North Korea', "korea, democratic people's republic of": 'North Korea', 'iran, islamic republic of': 'Iran', 'islamic republic of iran': 'Iran', 'syrian arab republic': 'Syria', 'viet nam': 'Vietnam', "lao people's democratic republic": 'Laos', 'czech republic': 'Czechia', 'moldova, republic of': 'Moldova', 'republic of moldova': 'Moldova', 'taiwan, province of china': 'Taiwan', 'ivory coast': "Côte d'Ivoire", "cote d'ivoire": "Côte d'Ivoire", 'burma': 'Myanmar', 'swaziland': 'eSwatini', 'the bahamas': 'Bahamas', 'north macedonia': 'Macedonia', 'uae': 'United Arab Emirates', 'bosnia and herzegovina': 'Bosnia and Herz.', 'bosnia': 'Bosnia and Herz.', 'democratic republic of the congo': 'Dem. Rep. Congo', 'drc': 'Dem. Rep. Congo', 'dr congo': 'Dem. Rep. Congo', 'republic of the congo': 'Congo', 'congo-brazzaville': 'Congo', 'dominican republic': 'Dominican Rep.', 'central african republic': 'Central African Rep.', 'equatorial guinea': 'Eq. Guinea', 'falkland islands': 'Falkland Is.', 'solomon islands': 'Solomon Is.', 'south sudan': 'S. Sudan', 'western sahara': 'W. Sahara', 'spain(canary is)': 'Spain', 'spain (canary is)': 'Spain', 'united kingdom': 'United Kingdom', 'venezuela, bolivarian republic of': 'Venezuela', 'bolivia, plurinational state of': 'Bolivia', 'tanzania, united republic of': 'Tanzania', 'united republic of tanzania': 'Tanzania'}

def detect_geo_encoding(values):
    """Auto-detect whether values are ISO-2, ISO-3, or country names."""
    sample = [str(v).strip() for v in values.dropna().head(20)]
    if all(len(v) == 2 and v.isalpha() and v.isupper() for v in sample if v):
        return "iso2"
    if all(len(v) == 3 and v.isalpha() and v.isupper() for v in sample if v):
        return "iso3"
    return "name"

def normalize_country(value, encoding):
    """Normalize a country value to its TopoJSON properties.name equivalent."""
    v = str(value).strip()
    if not v:
        return v
    if encoding == "iso2":
        return _ISO2_TO_TOPO.get(v.upper(), v)
    if encoding == "iso3":
        return _ISO3_TO_TOPO.get(v.upper(), v)
    return _ALIAS_TO_TOPO.get(v.lower(), v)

def main():
    st.set_page_config(
        page_title="BigQuery Test - Startup Funding",
        page_icon="📊",
        layout="wide"
    )
    # Apply Custom Styling
    st.markdown("""
        <style>
        .stApp {
            background-color: #282a36;
            color: #f8f8f2;
        }
        h1, h2, h3, p, li, .stMarkdown, .stMetricValue, .stMetricLabel {
            color: #f8f8f2 !important;
        }
        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
            color: #f8f8f2;
        }
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
            border-bottom-color: #bd93f9 !important;
        }
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] [data-testid="stMarkdownContainer"] p {
            color: #bd93f9 !important;
        }
        /* Card-like chart containers — only target elements that hold charts */
        [data-testid="stVerticalBlock"] > div:has([data-testid="stVegaLiteChart"]),
        [data-testid="stVerticalBlock"] > div:has([data-testid="stArrowVegaLiteChart"]) {
            background-color: #313343;
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 0.5rem;
        }
        /* Divider color */
        hr {
            border-color: #f8f8f220 !important;
        }
        </style>
    """, unsafe_allow_html=True)
    st.title("BigQuery Test - Startup Funding")

    column_types = get_column_types()

    tab1, = st.tabs(["Overview"])

    with tab1:
        _dashboard_filters = {}
        _mc0, _mc1 = st.columns(2)
        with _mc0:
            # Chart: total_funding_kpi
            _metric_data = run_query("total_funding_kpi", build_filter_clause("total_funding_kpi", _dashboard_filters))
            _metric_val = float(_metric_data.iloc[0]["y"]) if len(_metric_data) > 0 else None
            if _metric_val is not None and not (isinstance(_metric_val, float) and __import__("math").isnan(_metric_val)):
                _metric_formatted = f"{_metric_val:,.0f}"
            else:
                _metric_formatted = "N/A"
            st.markdown(f'''<div style="background:rgba(255,255,255,0.05);border-radius:8px;padding:16px 20px;text-align:center;">
                <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;opacity:0.6;margin-bottom:8px;">Total Funding</div>
                <div style="font-size:2rem;font-weight:700;color:#bd93f9;">{_metric_formatted}</div>
            </div>''', unsafe_allow_html=True)
        with _mc1:
            # Chart: total_deals_kpi
            _metric_data = run_query("total_deals_kpi", build_filter_clause("total_deals_kpi", _dashboard_filters))
            _metric_val = float(_metric_data.iloc[0]["y"]) if len(_metric_data) > 0 else None
            if _metric_val is not None and not (isinstance(_metric_val, float) and __import__("math").isnan(_metric_val)):
                _metric_formatted = f"{_metric_val:,.0f}"
            else:
                _metric_formatted = "N/A"
            st.markdown(f'''<div style="background:rgba(255,255,255,0.05);border-radius:8px;padding:16px 20px;text-align:center;">
                <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;opacity:0.6;margin-bottom:8px;">Total Deals</div>
                <div style="font-size:2rem;font-weight:700;color:#bd93f9;">{_metric_formatted}</div>
            </div>''', unsafe_allow_html=True)
        st.divider()

        # Chart: bar_by_industry
        st.subheader("Funding by Industry")
        chart_data = run_query("bar_by_industry", build_filter_clause("bar_by_industry", _dashboard_filters))
        chart_data = chart_data.rename(columns={'x': 'industry', 'y': 'funding_amount'})
        chart_data = chart_data.sort_values("funding_amount", ascending=False)
        chart_df = chart_data
        effective_x_type = "None" if "None" != "None" else column_types.get("industry")
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("industry" + x_encoding_suffix, sort=list(chart_data["industry"]), title="Industry"),
            y=alt.Y("funding_amount:Q", title="Funding Amount"),
            tooltip=["industry", "funding_amount"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: pie_by_stage
        st.subheader("Deals by Stage")
        chart_data = run_query("pie_by_stage", build_filter_clause("pie_by_stage", _dashboard_filters))
        chart_data = chart_data.rename(columns={'x': 'stage', 'y': 'funding_amount'})
        chart_df = chart_data
        effective_x_type = "None" if "None" != "None" else column_types.get("stage")
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Use theme secondary colors for pie chart
        theme_colors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c']
        c = alt.Chart(chart_data).mark_arc().encode(
            theta=alt.Theta("funding_amount:Q"),
            color=alt.Color("stage:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="Stage")
            ),
            tooltip=["stage", "funding_amount"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: line_over_time
        st.subheader("Funding Over Time")
        chart_data = run_query("line_over_time", build_filter_clause("line_over_time", _dashboard_filters))
        chart_data = chart_data.rename(columns={'x': 'funding_date', 'y': 'funding_amount'})
        chart_df = chart_data
        effective_x_type = "date" if "date" != "None" else column_types.get("funding_date")
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_line(color="#bd93f9", point=True).encode(
            x=alt.X("funding_date" + x_encoding_suffix, sort=None, title="Funding Date"),
            y=alt.Y("funding_amount:Q", title="Funding Amount"),
            tooltip=["funding_date", "funding_amount"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: scatter_funding_vs_valuation
        st.subheader("Funding vs Valuation")
        chart_data = run_query("scatter_funding_vs_valuation", build_filter_clause("scatter_funding_vs_valuation", _dashboard_filters))
        chart_data = chart_data.rename(columns={'x': 'funding_amount', 'y': 'valuation'})
        chart_df = chart_data
        effective_x_type = "None" if "None" != "None" else column_types.get("funding_amount")
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Scatter: raw data points
        c = alt.Chart(chart_df).mark_circle(color="#bd93f9", size=60).encode(
            x=alt.X("funding_amount:Q", sort=None, title="Funding Amount"),
            y=alt.Y("valuation:Q", title="Valuation"),
            tooltip=["funding_amount", "valuation"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: geo_by_country
        st.subheader("Funding by Country")
        chart_data = run_query("geo_by_country", build_filter_clause("geo_by_country", _dashboard_filters))
        chart_data = chart_data.rename(columns={'x': 'country', 'y': 'funding_amount'})
        chart_df = chart_data
        effective_x_type = "None" if "None" != "None" else column_types.get("country")
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Geo chart: choropleth map colored by funding_amount
        # Normalize country names to match topojson properties.name
        geo_data = chart_data.copy()
        geo_enc = "name"
        geo_data["country"] = geo_data["country"].fillna("").apply(lambda v: normalize_country(v, geo_enc))
        # Re-aggregate after normalization (merges entries that map to same country)
        geo_data = geo_data[geo_data["country"] != ""].groupby("country")["funding_amount"].sum().reset_index()
    
        # Load world countries topojson (has country names in properties.name)
        countries_url = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"
        countries = alt.topo_feature(countries_url, "countries")
    
        # Create choropleth map (two layers: background + data)
        background = alt.Chart(countries).mark_geoshape(
            fill="#e0e0e0",
            stroke="#aaa",
            strokeWidth=0.5
        ).project(
            type="naturalEarth1"
        ).properties(
            width=800,
            height=450
        )
        foreground = alt.Chart(countries).mark_geoshape(
            stroke="#aaa",
            strokeWidth=0.5
        ).encode(
            color=alt.Color("funding_amount:Q",
                scale=alt.Scale(scheme="purples"),
                legend=alt.Legend(title="Funding Amount")
            ),
            tooltip=["properties.name:N", "funding_amount:Q"]
        ).transform_lookup(
            lookup="properties.name",
            from_=alt.LookupData(data=geo_data, key="country", fields=["funding_amount"])
        ).project(
            type="naturalEarth1"
        ).properties(
            width=800,
            height=450
        )
        c = background + foreground
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: top_countries
        st.subheader("Top 10 Countries")
        chart_data = run_query("top_countries", build_filter_clause("top_countries", _dashboard_filters))
        chart_data = chart_data.rename(columns={'x': 'country', 'y': 'funding_amount'})
        chart_data = chart_data.sort_values("funding_amount", ascending=False)
        chart_df = chart_data
        effective_x_type = "None" if "None" != "None" else column_types.get("country")
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("country" + x_encoding_suffix, sort=list(chart_data["country"]), title="Country"),
            y=alt.Y("funding_amount:Q", title="Funding Amount"),
            tooltip=["country", "funding_amount"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")


if __name__ == "__main__":
    main()