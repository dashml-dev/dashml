import streamlit as st
import pandas as pd
import altair as alt
from sqlalchemy import create_engine

@st.cache_data
def load_data():
    try:
        engine = create_engine("postgresql://neondb_owner:npg_fm0ZpyB5CQkT@ep-gentle-glitter-a9duu2r4-pooler.gwc.azure.neon.tech:5432/neondb")
        df = pd.read_sql("SELECT * FROM public.orders", engine)

        # Fetch column types from information_schema for auto type detection
        schema_query = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'orders'
        """
        schema_df = pd.read_sql(schema_query, engine)

        # Build column type mapping: date, number, string
        column_types = {}
        for _, row in schema_df.iterrows():
            col_name = row['column_name']
            data_type = str(row['data_type']).upper()
            if any(dt in data_type for dt in ['DATE', 'TIME', 'TIMESTAMP', 'INTERVAL']):
                column_types[col_name] = 'date'
            elif any(dt in data_type for dt in ['INT', 'FLOAT', 'NUMERIC', 'DECIMAL', 'REAL', 'DOUBLE', 'SERIAL', 'MONEY']):
                column_types[col_name] = 'number'
            else:
                column_types[col_name] = 'string'

        # Cast numeric columns so Altair can handle Decimal/other non-float types
        for col_name, col_type in column_types.items():
            if col_type == 'number' and col_name in df.columns:
                df[col_name] = pd.to_numeric(df[col_name], errors='coerce')

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
        page_title="SQL Definitive - All Chart Types",
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
    st.title("SQL Definitive - All Chart Types")

    df, column_types = load_data()
    if df is None:
        st.error("Failed to load data")
        return

    tab1, tab2, tab3 = st.tabs(["Categorical Charts", "Time Series Charts", "Distribution & Relationships"])

    with tab1:
        st.markdown("*Bar charts and pie charts for categorical data*")
        st.divider()

        _dashboard_filters = {}
        _filtered_df = df
        _mc0, _mc1, _mc2 = st.columns(3)
        with _mc0:
            # Chart: total_revenue_kpi
            _metric_df = df.copy()
            _metric_df["total_amount"] = pd.to_numeric(_metric_df["total_amount"], errors="coerce")
            _metric_val = float(_metric_df["total_amount"].sum())
            if _metric_val is not None and not (isinstance(_metric_val, float) and __import__("math").isnan(_metric_val)):
                _metric_formatted = f"{_metric_val:,.0f}"
            else:
                _metric_formatted = "N/A"
            st.markdown(f'''<div style="background:rgba(255,255,255,0.05);border-radius:8px;padding:16px 20px;text-align:center;">
                <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;opacity:0.6;margin-bottom:8px;">Total Revenue</div>
                <div style="font-size:2rem;font-weight:700;color:#bd93f9;">{_metric_formatted}</div>
            </div>''', unsafe_allow_html=True)
        with _mc1:
            # Chart: total_orders_kpi
            _metric_df = df.copy()
            _metric_df["order_id"] = pd.to_numeric(_metric_df["order_id"], errors="coerce")
            _metric_val = float(len(_metric_df))
            if _metric_val is not None and not (isinstance(_metric_val, float) and __import__("math").isnan(_metric_val)):
                _metric_formatted = f"{_metric_val:,.0f}"
            else:
                _metric_formatted = "N/A"
            st.markdown(f'''<div style="background:rgba(255,255,255,0.05);border-radius:8px;padding:16px 20px;text-align:center;">
                <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;opacity:0.6;margin-bottom:8px;">Total Orders</div>
                <div style="font-size:2rem;font-weight:700;color:#bd93f9;">{_metric_formatted}</div>
            </div>''', unsafe_allow_html=True)
        with _mc2:
            # Chart: avg_order_value_kpi
            _metric_df = df.copy()
            _metric_df["total_amount"] = pd.to_numeric(_metric_df["total_amount"], errors="coerce")
            _metric_val = float(_metric_df["total_amount"].mean())
            if _metric_val is not None and not (isinstance(_metric_val, float) and __import__("math").isnan(_metric_val)):
                _metric_formatted = f"{_metric_val:,.2f}"
            else:
                _metric_formatted = "N/A"
            st.markdown(f'''<div style="background:rgba(255,255,255,0.05);border-radius:8px;padding:16px 20px;text-align:center;">
                <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;opacity:0.6;margin-bottom:8px;">Avg Order Value</div>
                <div style="font-size:2rem;font-weight:700;color:#bd93f9;">{_metric_formatted}</div>
            </div>''', unsafe_allow_html=True)
        st.divider()

        # Chart: bar_sales_by_country
        st.subheader("Total Sales by Country")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("shipping_address_country")
        # Aggregate: sum(total_amount) group by shipping_address_country
        chart_data = chart_df.groupby("shipping_address_country")["total_amount"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["shipping_address_country"] = pd.to_datetime(chart_data["shipping_address_country"])
            chart_data = chart_data.sort_values("shipping_address_country")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("shipping_address_country")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("shipping_address_country")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("shipping_address_country" + x_encoding_suffix, sort=None, title="Shipping Address Country"),
            y=alt.Y("total_amount:Q", title="Total Amount"),
            tooltip=["shipping_address_country", "total_amount"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: pie_orders_by_status
        st.subheader("Orders by Status")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("status")
        # Aggregate: count(order_id) group by status
        chart_data = chart_df.groupby("status")["order_id"].count().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["status"] = pd.to_datetime(chart_data["status"])
            chart_data = chart_data.sort_values("status")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("status")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("status")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Use theme secondary colors for pie chart
        theme_colors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c']
        c = alt.Chart(chart_data).mark_arc().encode(
            theta=alt.Theta("order_id:Q"),
            color=alt.Color("status:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="Status")
            ),
            tooltip=["status", "order_id"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: grouped_bar_country_status
        st.subheader("Orders by Country (Grouped by Status)")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("shipping_address_country")
        # Aggregate: count(order_id) group by shipping_address_country and status
        chart_data = chart_df.groupby(["shipping_address_country", "status"])["order_id"].count().reset_index()
        # Sort by y field (desc)
        chart_data = chart_data.sort_values("order_id", ascending=False)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Grouped bar: group order_id by status
        theme_colors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c']
        c = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X("shipping_address_country" + x_encoding_suffix, sort="-y", title="Shipping Address Country"),
            y=alt.Y("order_id:Q", title="Order Id"),
            color=alt.Color("status:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="Status")
            ),
            xOffset=alt.XOffset("status:N", sort="-y"),
            tooltip=["shipping_address_country", "status", "order_id"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: stacked_bar_payment_status
        st.subheader("Orders by Payment Method (Stacked by Status)")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("payment_method")
        # Aggregate: count(order_id) group by payment_method and status
        chart_data = chart_df.groupby(["payment_method", "status"])["order_id"].count().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["payment_method"] = pd.to_datetime(chart_data["payment_method"])
            chart_data = chart_data.sort_values("payment_method")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("payment_method")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("payment_method")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Stacked bar: stack order_id by status
        theme_colors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c']
        c = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X("payment_method" + x_encoding_suffix, sort=None, title="Payment Method"),
            y=alt.Y("order_id:Q", stack="zero", title="Order Id"),
            color=alt.Color("status:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="Status")
            ),
            tooltip=["payment_method", "status", "order_id"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: geo_sales_by_country
        st.subheader("Sales by Country (Map)")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("shipping_address_country")
        # Aggregate: sum(total_amount) group by shipping_address_country
        chart_data = chart_df.groupby("shipping_address_country")["total_amount"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["shipping_address_country"] = pd.to_datetime(chart_data["shipping_address_country"])
            chart_data = chart_data.sort_values("shipping_address_country")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("shipping_address_country")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("shipping_address_country")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Geo chart: choropleth map colored by total_amount
        # Normalize country names to match topojson properties.name
        geo_data = chart_data.copy()
        geo_enc = detect_geo_encoding(geo_data["shipping_address_country"])
        geo_data["shipping_address_country"] = geo_data["shipping_address_country"].fillna("").apply(lambda v: normalize_country(v, geo_enc))
        # Re-aggregate after normalization (merges entries that map to same country)
        geo_data = geo_data[geo_data["shipping_address_country"] != ""].groupby("shipping_address_country")["total_amount"].sum().reset_index()
    
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
            color=alt.Color("total_amount:Q",
                scale=alt.Scale(scheme="purples"),
                legend=alt.Legend(title="Total Amount")
            ),
            tooltip=["properties.name:N", "total_amount:Q"]
        ).transform_lookup(
            lookup="properties.name",
            from_=alt.LookupData(data=geo_data, key="shipping_address_country", fields=["total_amount"])
        ).project(
            type="naturalEarth1"
        ).properties(
            width=800,
            height=450
        )
        c = background + foreground
        st.altair_chart(c, use_container_width=True, theme="streamlit")

    with tab2:
        st.markdown("*Line and area charts for temporal trends*")
        st.divider()

        _dashboard_filters = {}
        _filtered_df = df
        # Chart: line_orders_over_time
        st.subheader("Orders Over Time")
        chart_df = df
        effective_x_type = "date" if "date" != "None" else column_types.get("order_date")
        # Aggregate: count rows group by order_date
        chart_data = chart_df.groupby("order_date").size().reset_index(name="count")
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["order_date"] = pd.to_datetime(chart_data["order_date"])
            chart_data = chart_data.sort_values("order_date")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("order_date")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("order_date")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_line(color="#bd93f9", point=True).encode(
            x=alt.X("order_date" + x_encoding_suffix, sort=None, title="Order Date"),
            y=alt.Y("count:Q", title="Count"),
            tooltip=["order_date", "count"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: area_revenue_over_time
        st.subheader("Revenue Over Time")
        chart_df = df
        effective_x_type = "date" if "date" != "None" else column_types.get("order_date")
        # Aggregate: sum(total_amount) group by order_date
        chart_data = chart_df.groupby("order_date")["total_amount"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["order_date"] = pd.to_datetime(chart_data["order_date"])
            chart_data = chart_data.sort_values("order_date")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("order_date")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("order_date")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_area(color="#bd93f9", opacity=0.7).encode(
            x=alt.X("order_date" + x_encoding_suffix, sort=None, title="Order Date"),
            y=alt.Y("total_amount:Q", title="Total Amount"),
            tooltip=["order_date", "total_amount"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")

    with tab3:
        st.markdown("*Scatter plots, histograms, box plots, bubble charts, and heatmaps*")
        st.divider()

        _dashboard_filters = {}
        _filtered_df = df
        # Chart: scatter_amount_vs_tax
        st.subheader("Order Amount vs Tax Amount")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("total_amount")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Scatter: raw data points
        c = alt.Chart(chart_df).mark_circle(color="#bd93f9", size=60).encode(
            x=alt.X("total_amount:Q", title="Total Amount"),
            y=alt.Y("tax_amount:Q", title="Tax Amount"),
            tooltip=["total_amount", "tax_amount"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: histogram_order_amounts
        st.subheader("Distribution of Order Amounts")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("total_amount")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Histogram: bin total_amount values into 20 bins
        c = alt.Chart(chart_df).mark_bar(color="#bd93f9").encode(
            x=alt.X("total_amount:Q", bin=alt.Bin(maxbins=20), title="Total Amount"),
            y=alt.Y("count()", title="Count"),
            tooltip=["count()"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: box_amount_by_status
        st.subheader("Order Amount Distribution by Status")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("status")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Box plot: distribution by status
        c = alt.Chart(chart_df).mark_boxplot(color="#bd93f9").encode(
            x=alt.X("status:N", title="Status"),
            y=alt.Y("total_amount:Q", title="Total Amount"),
            tooltip=["status"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: bubble_region_sales
        st.subheader("Sales vs Tax by Region")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("total_amount")
        chart_df["total_amount"] = pd.to_numeric(chart_df["total_amount"], errors="coerce")
        chart_df["tax_amount"] = pd.to_numeric(chart_df["tax_amount"], errors="coerce")
        # Bubble: aggregate total_amount, tax_amount, total_amount group by shipping_address_state
        chart_data = chart_df.groupby("shipping_address_state").agg({"total_amount": "sum", "tax_amount": "sum"}).reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["total_amount"] = pd.to_datetime(chart_data["total_amount"])
            chart_data = chart_data.sort_values("total_amount")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("total_amount")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("total_amount")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Bubble: 4D visualization (group, x, y, size)
        c = alt.Chart(chart_data).mark_circle().encode(
            x=alt.X("total_amount:Q", title="Total Amount"),
            y=alt.Y("tax_amount:Q", title="Tax Amount"),
            size=alt.Size("total_amount:Q", scale=alt.Scale(range=[50, 500]), legend=alt.Legend(title="Total Amount")),
            color=alt.Color("shipping_address_state:N", legend=alt.Legend(title="Shipping Address State")),
            tooltip=["shipping_address_state", "total_amount", "tax_amount", "total_amount"]
        )
        st.altair_chart(c, use_container_width=True, theme="streamlit")
        st.divider()

        # Chart: heatmap_country_status
        st.subheader("Order Count by Country and Status")
        chart_df = df
        effective_x_type = "None" if "None" != "None" else column_types.get("shipping_address_country")
        # Aggregate: count(order_id) group by shipping_address_country
        chart_data = chart_df.groupby("shipping_address_country")["order_id"].count().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["shipping_address_country"] = pd.to_datetime(chart_data["shipping_address_country"])
            chart_data = chart_data.sort_values("shipping_address_country")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("shipping_address_country")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("shipping_address_country")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Heatmap: 2D grid with color intensity
        # Re-aggregate for heatmap (group by both x and y)
        heatmap_data = chart_df.groupby(["shipping_address_country", "status"])["order_id"].count().reset_index()
        # Limit to top categories to prevent unreadable charts
        top_x = heatmap_data.groupby("shipping_address_country")["order_id"].sum().nlargest(15).index
        top_y = heatmap_data.groupby("status")["order_id"].sum().nlargest(15).index
        heatmap_data = heatmap_data[heatmap_data["shipping_address_country"].isin(top_x) & heatmap_data["status"].isin(top_y)]
        c = alt.Chart(heatmap_data).mark_rect().encode(
            x=alt.X("shipping_address_country:N", sort=None, title="Shipping Address Country"),
            y=alt.Y("status:N", title="Status"),
            color=alt.Color("order_id:Q",
                scale=alt.Scale(scheme="purples"),
                legend=alt.Legend(title="Order Id")
            ),
            tooltip=["shipping_address_country", "status", "order_id"]
        ).properties(width=600, height=400)
        st.altair_chart(c, use_container_width=True, theme="streamlit")


if __name__ == "__main__":
    main()