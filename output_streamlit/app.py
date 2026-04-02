import streamlit as st
import pandas as pd
import altair as alt

@st.cache_data
def load_data():
    try:
        df = pd.read_csv("C:\Dev\dashml\playground\dashml_new\startup_funding.csv")

        # Infer column types from pandas dtypes for auto type detection
        column_types = {}
        for col in df.columns:
            dtype = str(df[col].dtype)
            if 'datetime' in dtype or 'date' in dtype:
                column_types[col] = 'date'
            elif 'int' in dtype or 'float' in dtype:
                column_types[col] = 'number'
            else:
                # Try to detect date strings
                if df[col].dtype == 'object':
                    try:
                        pd.to_datetime(df[col].dropna().head(10))
                        column_types[col] = 'date'
                    except:
                        column_types[col] = 'string'
                else:
                    column_types[col] = 'string'
        return df, column_types
    except Exception as e:
        return None, None

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
        page_title="Global Startup Funding Dashboard",
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
        /* Card-like chart containers */
        [data-testid="stVerticalBlock"] > div {
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
    st.title("Global Startup Funding Dashboard")

    df, column_types = load_data()
    if df is None:
        st.error("Failed to load data")
        return

    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "By Industry", "Geography", "Deep Dive"])

    with tab1:
        st.markdown("*Key metrics and high-level funding trends*")
        st.divider()

        _dashboard_filters = {}
        _filtered_df = df
        _mc0, _mc1, _mc2 = st.columns(3)
        with _mc0:
            # Chart: metric_total_funding
            _metric_df = df
            _metric_df["funding_amount"] = pd.to_numeric(_metric_df["funding_amount"], errors="coerce")
            _metric_val = float(_metric_df["funding_amount"].sum())
            if _metric_val is not None and not (isinstance(_metric_val, float) and __import__("math").isnan(_metric_val)):
                _metric_formatted = f"{_metric_val:,.1f}" + "M"
            else:
                _metric_formatted = "N/A"
            st.markdown(f'''<div style="background:rgba(255,255,255,0.05);border-radius:8px;padding:16px 20px;text-align:center;">
                <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;opacity:0.6;margin-bottom:8px;">Total Funding ($M)</div>
                <div style="font-size:2rem;font-weight:700;color:#bd93f9;">{_metric_formatted}</div>
            </div>''', unsafe_allow_html=True)
        with _mc1:
            # Chart: metric_deal_count
            _metric_df = df
            _metric_df["funding_amount"] = pd.to_numeric(_metric_df["funding_amount"], errors="coerce")
            _metric_val = float(len(_metric_df))
            if _metric_val is not None and not (isinstance(_metric_val, float) and __import__("math").isnan(_metric_val)):
                _metric_formatted = f"{_metric_val:,.0f}"
            else:
                _metric_formatted = "N/A"
            st.markdown(f'''<div style="background:rgba(255,255,255,0.05);border-radius:8px;padding:16px 20px;text-align:center;">
                <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;opacity:0.6;margin-bottom:8px;">Total Deals</div>
                <div style="font-size:2rem;font-weight:700;color:#bd93f9;">{_metric_formatted}</div>
            </div>''', unsafe_allow_html=True)
        with _mc2:
            # Chart: metric_avg_valuation
            _metric_df = df
            _metric_df["valuation"] = pd.to_numeric(_metric_df["valuation"], errors="coerce")
            _metric_val = float(_metric_df["valuation"].mean())
            if _metric_val is not None and not (isinstance(_metric_val, float) and __import__("math").isnan(_metric_val)):
                _metric_formatted = f"{_metric_val:,.1f}" + "M"
            else:
                _metric_formatted = "N/A"
            st.markdown(f'''<div style="background:rgba(255,255,255,0.05);border-radius:8px;padding:16px 20px;text-align:center;">
                <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;opacity:0.6;margin-bottom:8px;">Avg Valuation ($M)</div>
                <div style="font-size:2rem;font-weight:700;color:#bd93f9;">{_metric_formatted}</div>
            </div>''', unsafe_allow_html=True)
        st.divider()

        # Chart: line_funding_over_time
        st.subheader("Funding Over Time")
        chart_df = df
        effective_x_type = "date" if "date" != "None" else column_types.get("funding_date")
        # Aggregate: sum(funding_amount) group by funding_date
        chart_data = chart_df.groupby("funding_date")["funding_amount"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["funding_date"] = pd.to_datetime(chart_data["funding_date"])
            chart_data = chart_data.sort_values("funding_date")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("funding_date")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("funding_date")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_line(color="#bd93f9", point=True).encode(
            x=alt.X("funding_date" + x_encoding_suffix, sort=None, title="Funding Date"),
            y=alt.Y("funding_amount:Q", title="Funding Amount"),
            tooltip=["funding_date", "funding_amount"]
        )
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: area_deals_over_time
        st.subheader("Deal Count Over Time")
        chart_df = df
        effective_x_type = "date" if "date" != "None" else column_types.get("funding_date")
        # Aggregate: count(funding_amount) group by funding_date
        chart_data = chart_df.groupby("funding_date")["funding_amount"].count().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["funding_date"] = pd.to_datetime(chart_data["funding_date"])
            chart_data = chart_data.sort_values("funding_date")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("funding_date")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("funding_date")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_area(color="#bd93f9", opacity=0.7).encode(
            x=alt.X("funding_date" + x_encoding_suffix, sort=None, title="Funding Date"),
            y=alt.Y("funding_amount:Q", title="Funding Amount"),
            tooltip=["funding_date", "funding_amount"]
        )
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: pie_by_stage
        st.subheader("Deals by Funding Stage")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("stage")
        # Aggregate: count(funding_amount) group by stage
        chart_data = chart_df.groupby("stage")["funding_amount"].count().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["stage"] = pd.to_datetime(chart_data["stage"])
            chart_data = chart_data.sort_values("stage")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("stage")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("stage")
        # Determine Altair encoding type based on effective x_type
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
        st.altair_chart(c, use_container_width=True)

    with tab2:
        st.markdown("*Funding breakdown across industries*")
        st.divider()

        _dashboard_filters = {}
        _filtered_df = df
        # Chart: bar_funding_by_industry
        st.subheader("Total Funding by Industry")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("industry")
        # Aggregate: sum(funding_amount) group by industry
        chart_data = chart_df.groupby("industry")["funding_amount"].sum().reset_index()
        # Sort by y field (asc)
        chart_data = chart_data.sort_values("funding_amount", ascending=True)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("industry" + x_encoding_suffix, sort="y", title="Industry"),
            y=alt.Y("funding_amount:Q", title="Funding Amount"),
            tooltip=["industry", "funding_amount"]
        )
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: stacked_bar_industry_stage
        st.subheader("Industry Funding by Stage")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("industry")
        # Aggregate: sum(funding_amount) group by industry and stage
        chart_data = chart_df.groupby(["industry", "stage"])["funding_amount"].sum().reset_index()
        # Sort by y field (asc)
        chart_data = chart_data.sort_values("funding_amount", ascending=True)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Stacked bar: stack funding_amount by stage
        theme_colors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c']
        c = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X("industry" + x_encoding_suffix, sort="y", title="Industry"),
            y=alt.Y("funding_amount:Q", stack="zero", title="Funding Amount"),
            color=alt.Color("stage:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="Stage")
            ),
            tooltip=["industry", "stage", "funding_amount"]
        )
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: grouped_bar_industry_stage
        st.subheader("Industry Deal Count by Stage")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("industry")
        # Aggregate: count(funding_amount) group by industry and stage
        chart_data = chart_df.groupby(["industry", "stage"])["funding_amount"].count().reset_index()
        # Sort by y field (asc)
        chart_data = chart_data.sort_values("funding_amount", ascending=True)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Grouped bar: group funding_amount by stage
        theme_colors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c']
        c = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X("industry" + x_encoding_suffix, sort="y", title="Industry"),
            y=alt.Y("funding_amount:Q", title="Funding Amount"),
            color=alt.Color("stage:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="Stage")
            ),
            xOffset=alt.XOffset("stage:N", sort="y"),
            tooltip=["industry", "stage", "funding_amount"]
        )
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: heatmap_industry_country
        st.subheader("Funding Heatmap: Industry vs Country")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("industry")
        # Aggregate: sum(funding_amount) group by industry
        chart_data = chart_df.groupby("industry")["funding_amount"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["industry"] = pd.to_datetime(chart_data["industry"])
            chart_data = chart_data.sort_values("industry")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("industry")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("industry")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Heatmap: 2D grid with color intensity
        # Re-aggregate for heatmap (group by both x and y)
        heatmap_data = chart_df.groupby(["industry", "country"])["funding_amount"].sum().reset_index()
        # Limit to top categories to prevent unreadable charts
        top_x = heatmap_data.groupby("industry")["funding_amount"].sum().nlargest(15).index
        top_y = heatmap_data.groupby("country")["funding_amount"].sum().nlargest(15).index
        heatmap_data = heatmap_data[heatmap_data["industry"].isin(top_x) & heatmap_data["country"].isin(top_y)]
        c = alt.Chart(heatmap_data).mark_rect().encode(
            x=alt.X("industry:N", sort=None, title="Industry"),
            y=alt.Y("country:N", title="Country"),
            color=alt.Color("funding_amount:Q",
                scale=alt.Scale(scheme="purples"),
                legend=alt.Legend(title="Funding Amount")
            ),
            tooltip=["industry", "country", "funding_amount"]
        ).properties(width=600, height=400)
        st.altair_chart(c, use_container_width=True)

    with tab3:
        st.markdown("*Where startup funding flows globally*")
        st.divider()

        _dashboard_filters = {}
        _filtered_df = df
        # Chart: geo_funding_by_country
        st.subheader("Total Funding by Country")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("country")
        # Aggregate: sum(funding_amount) group by country
        chart_data = chart_df.groupby("country")["funding_amount"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["country"] = pd.to_datetime(chart_data["country"])
            chart_data = chart_data.sort_values("country")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("country")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("country")
        # Determine Altair encoding type based on effective x_type
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
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: bar_top_countries
        st.subheader("Top 10 Countries by Funding")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("country")
        # Aggregate: sum(funding_amount) group by country
        chart_data = chart_df.groupby("country")["funding_amount"].sum().reset_index()
        # Sort by y field (asc)
        chart_data = chart_data.sort_values("funding_amount", ascending=True)
        # Limit to top 10 rows
        chart_data = chart_data.head(10)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("country" + x_encoding_suffix, sort="y", title="Country"),
            y=alt.Y("funding_amount:Q", title="Funding Amount"),
            tooltip=["country", "funding_amount"]
        )
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: bar_top_cities
        st.subheader("Top 10 Cities by Deal Count")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("city")
        # Aggregate: count(funding_amount) group by city
        chart_data = chart_df.groupby("city")["funding_amount"].count().reset_index()
        # Sort by y field (asc)
        chart_data = chart_data.sort_values("funding_amount", ascending=True)
        # Limit to top 10 rows
        chart_data = chart_data.head(10)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("city" + x_encoding_suffix, sort="y", title="City"),
            y=alt.Y("funding_amount:Q", title="Funding Amount"),
            tooltip=["city", "funding_amount"]
        )
        st.altair_chart(c, use_container_width=True)

    with tab4:
        st.markdown("*Distributions and correlations*")
        st.divider()

        _dashboard_filters = {}
        _filtered_df = df
        # Chart: scatter_funding_vs_valuation
        st.subheader("Funding Amount vs Valuation")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("funding_amount")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Scatter: raw data points
        c = alt.Chart(chart_df).mark_circle(color="#bd93f9", size=60).encode(
            x=alt.X("funding_amount:Q", title="Funding Amount"),
            y=alt.Y("valuation:Q", title="Valuation"),
            tooltip=["funding_amount", "valuation"]
        )
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: histogram_funding
        st.subheader("Distribution of Funding Amounts")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("funding_amount")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Histogram: bin funding_amount values into 30 bins
        c = alt.Chart(chart_df).mark_bar(color="#bd93f9").encode(
            x=alt.X("funding_amount:Q", bin=alt.Bin(maxbins=30), title="Funding Amount"),
            y=alt.Y("count()", title="Count"),
            tooltip=["count()"]
        )
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: box_funding_by_stage
        st.subheader("Funding Distribution by Stage")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("stage")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Box plot: distribution by stage
        c = alt.Chart(chart_df).mark_boxplot(color="#bd93f9").encode(
            x=alt.X("stage:N", title="Stage"),
            y=alt.Y("funding_amount:Q", title="Funding Amount"),
            tooltip=["stage"]
        )
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: bubble_industry
        st.subheader("Industries: Funding vs Valuation (sized by Employees)")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("funding_amount")
        chart_df["funding_amount"] = pd.to_numeric(chart_df["funding_amount"], errors="coerce")
        chart_df["valuation"] = pd.to_numeric(chart_df["valuation"], errors="coerce")
        chart_df["employees"] = pd.to_numeric(chart_df["employees"], errors="coerce")
        # Bubble: aggregate funding_amount, valuation, employees group by industry
        chart_data = chart_df.groupby("industry").agg({"funding_amount": "mean", "valuation": "mean", "employees": "mean"}).reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["funding_amount"] = pd.to_datetime(chart_data["funding_amount"])
            chart_data = chart_data.sort_values("funding_amount")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("funding_amount")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("funding_amount")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Bubble: 4D visualization (group, x, y, size)
        c = alt.Chart(chart_data).mark_circle().encode(
            x=alt.X("funding_amount:Q", title="Funding Amount"),
            y=alt.Y("valuation:Q", title="Valuation"),
            size=alt.Size("employees:Q", scale=alt.Scale(range=[50, 500]), legend=alt.Legend(title="Employees")),
            color=alt.Color("industry:N", legend=alt.Legend(title="Industry")),
            tooltip=["industry", "funding_amount", "valuation", "employees"]
        )
        st.altair_chart(c, use_container_width=True)


if __name__ == "__main__":
    main()