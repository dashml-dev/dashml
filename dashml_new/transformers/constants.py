"""
DashML Transformers - Shared Constants

These constants are used across all transformers to ensure consistent behavior.
"""

# Chart type categorization by data requirements
# Charts that need data aggregation (groupby + agg function)
CHARTS_NEED_AGGREGATION = frozenset({
    "bar", "line", "area", "pie", "stacked_bar", "grouped_bar", "bubble", "heatmap", "geo"
})

# Charts that work with raw data points (no aggregation)
# These compute their own statistics (bins for histogram, quartiles for box)
CHARTS_USE_RAW_DATA = frozenset({"histogram", "box", "scatter"})

# Scalar widgets: return a single aggregated value, no x-axis
CHARTS_SCALAR = frozenset({"metric"})

# Default number of bins for histogram charts
DEFAULT_HISTOGRAM_BINS = 20

# Supported filter operators
# Used in chart.filters[].op field
SUPPORTED_FILTER_OPS = frozenset({
    "eq",       # Equal: field == value
    "ne",       # Not equal: field != value
    "gt",       # Greater than: field > value
    "lt",       # Less than: field < value
    "gte",      # Greater than or equal: field >= value
    "lte",      # Less than or equal: field <= value
    "in",       # In list: field in [value1, value2, ...]
    "contains", # Contains substring: value in field (for strings)
    "range",    # Range: field between [low, high] (inclusive)
})

# Supported sort orders
SUPPORTED_SORT_ORDERS = frozenset({"asc", "desc"})

# Default sort order when not specified
DEFAULT_SORT_ORDER = "asc"

# Aggregation methods mapping
# Maps DashML agg names to common implementations
AGG_METHODS = {
    "sum": "sum",
    "mean": "mean",
    "count": "count",
}

# Default primary color (used across transformers)
DEFAULT_PRIMARY_COLOR = "#29b5e8"

# Default secondary colors for categorical data
DEFAULT_SECONDARY_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
]

# Visual design tokens shared across transformers.
# Theme-agnostic UI surface/border/text colors that augment the per-theme
# palette (background, card, primary, text) loaded from .dmls files.
# Kept transformer-side because they encode visual relationships
# (hover surface, soft border, dim foreground, benchmark amber) that the
# user is unlikely to want to override per-spec.
DESIGN_TOKENS = {
    "card_alt":  "#353749",  # inner panel / hover surface
    "line":      "#44475a",  # borders, axis lines
    "line_soft": "#3a3c4e",  # card border, chart grid
    "muted":     "#6272a4",  # axis title text, secondary muted
    "fg_dim":    "#c8cadf",  # dim foreground (tick labels, unit suffix)
    "amber":     "#ffb86c",  # benchmark / reference-line color (dracula orange — more legible than desaturated amber)
    "geo_land":  "#f0f0f5",  # choropleth land fill for countries with no data (light, contrasts dark card bg)
    "geo_border":"#aaaaaa",  # choropleth country borders on light land
    "pie_label": "#1a1b24",  # dark text for inside-pie labels (readable on light purple slices)
}

# Light → dark purple intensity ramp for ordinal categorical encoding
# (used when a bar chart is sorted by y with no explicit group).
PURPLE_RAMP = [
    "#e9d8ff", "#d4b9fb", "#bd93f9",
    "#a378ee", "#8b62d8", "#735ac4",
]

def resolve_metric_format(fmt: str) -> str:
    """Convert human-friendly metric format names to Python/D3 format spec.

    Friendly names:
      "integer"    -> ",.0f"   e.g. 8,235,908
      "decimal"    -> ",.2f"   e.g. 14.82
      "decimal:1"  -> ",.1f"   e.g. 14.8
      "decimal:2"  -> ",.2f"   e.g. 14.82
      "decimal:N"  -> ",.Nf"   N decimal places with thousands separator
    Raw Python/D3 specs (e.g. ",.0f") are passed through unchanged for
    backward compatibility.
    """
    if fmt == "integer":
        return ",.0f"
    if fmt == "decimal":
        return ",.2f"
    if fmt.startswith("decimal:"):
        try:
            n = int(fmt.split(":")[1])
            return f",.{n}f"
        except (IndexError, ValueError):
            pass
    return fmt  # pass-through for raw format specs


# Dashboard-level filter widget types
SUPPORTED_DASHBOARD_FILTER_TYPES = frozenset({"select", "multiselect"})

# Column types for x_type/y_type hints
COLUMN_TYPES = frozenset({"date", "number", "string"})

# Supported axis scale types
SUPPORTED_SCALE_TYPES = frozenset({"linear", "log"})

# Supported reference line styles
SUPPORTED_REFERENCE_LINE_STYLES = frozenset({"solid", "dashed", "dotted"})

# Default annotation styling
ANNOTATION_DEFAULTS = {
    "font_size": 12,
    "color": "#333333",
}

# Date-related column names (heuristic for auto-detection)
TEMPORAL_FIELD_NAMES = frozenset({
    'date', 'time', 'timestamp', 'datetime',
    'created_at', 'updated_at', 'created', 'updated',
    'order_date', 'ship_date', 'start_date', 'end_date'
})

# ── Plotly colorscale resolution ────────────────────────────────────

PLOTLY_BUILTIN_SCALES = frozenset({
    "blues", "greens", "greys", "reds", "viridis", "cividis",
    "hot", "jet", "ylgnbu", "ylorrd", "rdbu", "bluered",
    "blackbody", "earth", "electric", "picnic", "portland", "rainbow",
})

D3_SEQUENTIAL_SCALES = {
    "purples": [[0, "#fcfbfd"], [0.125, "#efedf5"], [0.25, "#dadaeb"], [0.375, "#bcbddc"],
                [0.5, "#9e9ac8"], [0.625, "#807dba"], [0.75, "#6a51a3"], [0.875, "#54278f"], [1, "#3f007d"]],
    "oranges": [[0, "#fff5eb"], [0.125, "#fee6ce"], [0.25, "#fdd0a2"], [0.375, "#fdae6b"],
                [0.5, "#fd8d3c"], [0.625, "#f16913"], [0.75, "#d94801"], [0.875, "#a63603"], [1, "#7f2704"]],
    "teals":   [[0, "#e0f2f1"], [0.125, "#b2dfdb"], [0.25, "#80cbc4"], [0.375, "#4db6ac"],
                [0.5, "#26a69a"], [0.625, "#009688"], [0.75, "#00796b"], [0.875, "#00695c"], [1, "#004d40"]],
}


def resolve_plotly_colorscale(scheme: str):
    """Resolve a D3/Vega scheme name to a Plotly-compatible colorscale.
    Returns capitalized name for Plotly built-ins, or array for custom schemes."""
    if scheme.lower() in PLOTLY_BUILTIN_SCALES:
        return scheme.capitalize()
    if scheme.lower() in D3_SEQUENTIAL_SCALES:
        return D3_SEQUENTIAL_SCALES[scheme.lower()]
    return "Blues"


# ── Geo chart: country normalization ────────────────────────────────

SUPPORTED_GEO_ENCODINGS = frozenset({"iso2", "iso3", "name"})

# Single source of truth for country names.
# iso2 → (iso3, topojson_name, plotly_name)
# topojson_name matches world-atlas@2 countries-110m.json properties.name
# plotly_name matches Plotly.js locationmode='country names'
COUNTRY_DATA: dict[str, tuple[str, str, str]] = {
    "AF": ("AFG", "Afghanistan", "Afghanistan"),
    "AL": ("ALB", "Albania", "Albania"),
    "DZ": ("DZA", "Algeria", "Algeria"),
    "AO": ("AGO", "Angola", "Angola"),
    "AR": ("ARG", "Argentina", "Argentina"),
    "AM": ("ARM", "Armenia", "Armenia"),
    "AU": ("AUS", "Australia", "Australia"),
    "AT": ("AUT", "Austria", "Austria"),
    "AZ": ("AZE", "Azerbaijan", "Azerbaijan"),
    "BS": ("BHS", "Bahamas", "Bahamas"),
    "BD": ("BGD", "Bangladesh", "Bangladesh"),
    "BY": ("BLR", "Belarus", "Belarus"),
    "BE": ("BEL", "Belgium", "Belgium"),
    "BZ": ("BLZ", "Belize", "Belize"),
    "BJ": ("BEN", "Benin", "Benin"),
    "BT": ("BTN", "Bhutan", "Bhutan"),
    "BO": ("BOL", "Bolivia", "Bolivia"),
    "BA": ("BIH", "Bosnia and Herz.", "Bosnia and Herzegovina"),
    "BW": ("BWA", "Botswana", "Botswana"),
    "BR": ("BRA", "Brazil", "Brazil"),
    "BN": ("BRN", "Brunei", "Brunei"),
    "BG": ("BGR", "Bulgaria", "Bulgaria"),
    "BF": ("BFA", "Burkina Faso", "Burkina Faso"),
    "BI": ("BDI", "Burundi", "Burundi"),
    "KH": ("KHM", "Cambodia", "Cambodia"),
    "CM": ("CMR", "Cameroon", "Cameroon"),
    "CA": ("CAN", "Canada", "Canada"),
    "CF": ("CAF", "Central African Rep.", "Central African Republic"),
    "TD": ("TCD", "Chad", "Chad"),
    "CL": ("CHL", "Chile", "Chile"),
    "CN": ("CHN", "China", "China"),
    "CO": ("COL", "Colombia", "Colombia"),
    "CG": ("COG", "Congo", "Congo"),
    "CR": ("CRI", "Costa Rica", "Costa Rica"),
    "CI": ("CIV", "Côte d'Ivoire", "Cote d'Ivoire"),
    "HR": ("HRV", "Croatia", "Croatia"),
    "CU": ("CUB", "Cuba", "Cuba"),
    "CY": ("CYP", "Cyprus", "Cyprus"),
    "CZ": ("CZE", "Czechia", "Czech Republic"),
    "CD": ("COD", "Dem. Rep. Congo", "Democratic Republic of the Congo"),
    "DK": ("DNK", "Denmark", "Denmark"),
    "DJ": ("DJI", "Djibouti", "Djibouti"),
    "DO": ("DOM", "Dominican Rep.", "Dominican Republic"),
    "EC": ("ECU", "Ecuador", "Ecuador"),
    "EG": ("EGY", "Egypt", "Egypt"),
    "SV": ("SLV", "El Salvador", "El Salvador"),
    "GQ": ("GNQ", "Eq. Guinea", "Equatorial Guinea"),
    "ER": ("ERI", "Eritrea", "Eritrea"),
    "EE": ("EST", "Estonia", "Estonia"),
    "SZ": ("SWZ", "eSwatini", "Eswatini"),
    "ET": ("ETH", "Ethiopia", "Ethiopia"),
    "FK": ("FLK", "Falkland Is.", "Falkland Islands"),
    "FJ": ("FJI", "Fiji", "Fiji"),
    "FI": ("FIN", "Finland", "Finland"),
    "FR": ("FRA", "France", "France"),
    "GA": ("GAB", "Gabon", "Gabon"),
    "GM": ("GMB", "Gambia", "Gambia"),
    "GE": ("GEO", "Georgia", "Georgia"),
    "DE": ("DEU", "Germany", "Germany"),
    "GH": ("GHA", "Ghana", "Ghana"),
    "GR": ("GRC", "Greece", "Greece"),
    "GL": ("GRL", "Greenland", "Greenland"),
    "GT": ("GTM", "Guatemala", "Guatemala"),
    "GN": ("GIN", "Guinea", "Guinea"),
    "GW": ("GNB", "Guinea-Bissau", "Guinea-Bissau"),
    "GY": ("GUY", "Guyana", "Guyana"),
    "HT": ("HTI", "Haiti", "Haiti"),
    "HN": ("HND", "Honduras", "Honduras"),
    "HU": ("HUN", "Hungary", "Hungary"),
    "IS": ("ISL", "Iceland", "Iceland"),
    "IN": ("IND", "India", "India"),
    "ID": ("IDN", "Indonesia", "Indonesia"),
    "IR": ("IRN", "Iran", "Iran"),
    "IQ": ("IRQ", "Iraq", "Iraq"),
    "IE": ("IRL", "Ireland", "Ireland"),
    "IL": ("ISR", "Israel", "Israel"),
    "IT": ("ITA", "Italy", "Italy"),
    "JM": ("JAM", "Jamaica", "Jamaica"),
    "JP": ("JPN", "Japan", "Japan"),
    "JO": ("JOR", "Jordan", "Jordan"),
    "KZ": ("KAZ", "Kazakhstan", "Kazakhstan"),
    "KE": ("KEN", "Kenya", "Kenya"),
    "KW": ("KWT", "Kuwait", "Kuwait"),
    "KG": ("KGZ", "Kyrgyzstan", "Kyrgyzstan"),
    "LA": ("LAO", "Laos", "Laos"),
    "LV": ("LVA", "Latvia", "Latvia"),
    "LB": ("LBN", "Lebanon", "Lebanon"),
    "LS": ("LSO", "Lesotho", "Lesotho"),
    "LR": ("LBR", "Liberia", "Liberia"),
    "LY": ("LBY", "Libya", "Libya"),
    "LT": ("LTU", "Lithuania", "Lithuania"),
    "LU": ("LUX", "Luxembourg", "Luxembourg"),
    "MK": ("MKD", "Macedonia", "North Macedonia"),
    "MG": ("MDG", "Madagascar", "Madagascar"),
    "MW": ("MWI", "Malawi", "Malawi"),
    "MY": ("MYS", "Malaysia", "Malaysia"),
    "ML": ("MLI", "Mali", "Mali"),
    "MR": ("MRT", "Mauritania", "Mauritania"),
    "MX": ("MEX", "Mexico", "Mexico"),
    "MD": ("MDA", "Moldova", "Moldova"),
    "MN": ("MNG", "Mongolia", "Mongolia"),
    "ME": ("MNE", "Montenegro", "Montenegro"),
    "MA": ("MAR", "Morocco", "Morocco"),
    "MZ": ("MOZ", "Mozambique", "Mozambique"),
    "MM": ("MMR", "Myanmar", "Myanmar"),
    "NA": ("NAM", "Namibia", "Namibia"),
    "NP": ("NPL", "Nepal", "Nepal"),
    "NL": ("NLD", "Netherlands", "Netherlands"),
    "NC": ("NCL", "New Caledonia", "New Caledonia"),
    "NZ": ("NZL", "New Zealand", "New Zealand"),
    "NI": ("NIC", "Nicaragua", "Nicaragua"),
    "NE": ("NER", "Niger", "Niger"),
    "NG": ("NGA", "Nigeria", "Nigeria"),
    "KP": ("PRK", "North Korea", "North Korea"),
    "NO": ("NOR", "Norway", "Norway"),
    "OM": ("OMN", "Oman", "Oman"),
    "PK": ("PAK", "Pakistan", "Pakistan"),
    "PS": ("PSE", "Palestine", "Palestine"),
    "PA": ("PAN", "Panama", "Panama"),
    "PG": ("PNG", "Papua New Guinea", "Papua New Guinea"),
    "PY": ("PRY", "Paraguay", "Paraguay"),
    "PE": ("PER", "Peru", "Peru"),
    "PH": ("PHL", "Philippines", "Philippines"),
    "PL": ("POL", "Poland", "Poland"),
    "PT": ("PRT", "Portugal", "Portugal"),
    "PR": ("PRI", "Puerto Rico", "Puerto Rico"),
    "QA": ("QAT", "Qatar", "Qatar"),
    "RO": ("ROU", "Romania", "Romania"),
    "RU": ("RUS", "Russia", "Russia"),
    "RW": ("RWA", "Rwanda", "Rwanda"),
    "SA": ("SAU", "Saudi Arabia", "Saudi Arabia"),
    "SN": ("SEN", "Senegal", "Senegal"),
    "RS": ("SRB", "Serbia", "Serbia"),
    "SL": ("SLE", "Sierra Leone", "Sierra Leone"),
    "SI": ("SVN", "Slovenia", "Slovenia"),
    "SB": ("SLB", "Solomon Is.", "Solomon Islands"),
    "SO": ("SOM", "Somalia", "Somalia"),
    "ZA": ("ZAF", "South Africa", "South Africa"),
    "KR": ("KOR", "South Korea", "South Korea"),
    "SS": ("SSD", "S. Sudan", "South Sudan"),
    "ES": ("ESP", "Spain", "Spain"),
    "LK": ("LKA", "Sri Lanka", "Sri Lanka"),
    "SD": ("SDN", "Sudan", "Sudan"),
    "SR": ("SUR", "Suriname", "Suriname"),
    "SE": ("SWE", "Sweden", "Sweden"),
    "CH": ("CHE", "Switzerland", "Switzerland"),
    "SY": ("SYR", "Syria", "Syria"),
    "TW": ("TWN", "Taiwan", "Taiwan"),
    "TJ": ("TJK", "Tajikistan", "Tajikistan"),
    "TZ": ("TZA", "Tanzania", "Tanzania"),
    "TH": ("THA", "Thailand", "Thailand"),
    "TL": ("TLS", "Timor-Leste", "Timor-Leste"),
    "TG": ("TGO", "Togo", "Togo"),
    "TT": ("TTO", "Trinidad and Tobago", "Trinidad and Tobago"),
    "TN": ("TUN", "Tunisia", "Tunisia"),
    "TR": ("TUR", "Turkey", "Turkey"),
    "TM": ("TKM", "Turkmenistan", "Turkmenistan"),
    "UG": ("UGA", "Uganda", "Uganda"),
    "UA": ("UKR", "Ukraine", "Ukraine"),
    "AE": ("ARE", "United Arab Emirates", "United Arab Emirates"),
    "GB": ("GBR", "United Kingdom", "United Kingdom"),
    "US": ("USA", "United States of America", "United States"),
    "UY": ("URY", "Uruguay", "Uruguay"),
    "UZ": ("UZB", "Uzbekistan", "Uzbekistan"),
    "VU": ("VUT", "Vanuatu", "Vanuatu"),
    "VE": ("VEN", "Venezuela", "Venezuela"),
    "VN": ("VNM", "Vietnam", "Vietnam"),
    "EH": ("ESH", "W. Sahara", "Western Sahara"),
    "YE": ("YEM", "Yemen", "Yemen"),
    "ZM": ("ZMB", "Zambia", "Zambia"),
    "ZW": ("ZWE", "Zimbabwe", "Zimbabwe"),
    "XK": ("XKX", "Kosovo", "Kosovo"),
}

# Common name aliases → ISO-2 code
# Subsumes entries from Observable's hardcoded countryNameMap objects
COUNTRY_ALIASES: dict[str, str] = {
    # United States
    "USA": "US", "United States": "US",
    # United Kingdom
    "UK": "GB", "Britain": "GB", "Great Britain": "GB", "England": "GB",
    # Formal / alternate names
    "Russian Federation": "RU",
    "Republic of Korea": "KR", "Korea": "KR", "Korea, Republic of": "KR",
    "DPRK": "KP", "Korea, Democratic People's Republic of": "KP",
    "Iran, Islamic Republic of": "IR", "Islamic Republic of Iran": "IR",
    "Syrian Arab Republic": "SY",
    "Viet Nam": "VN",
    "Lao People's Democratic Republic": "LA",
    "Czech Republic": "CZ",
    "Moldova, Republic of": "MD", "Republic of Moldova": "MD",
    "Taiwan, Province of China": "TW",
    "Ivory Coast": "CI", "Cote d'Ivoire": "CI",
    "Burma": "MM",
    "Swaziland": "SZ",
    "The Bahamas": "BS",
    "North Macedonia": "MK",
    "UAE": "AE",
    "Bosnia and Herzegovina": "BA", "Bosnia": "BA",
    # Full names for TopoJSON abbreviations
    "Democratic Republic of the Congo": "CD", "DRC": "CD", "DR Congo": "CD",
    "Republic of the Congo": "CG", "Congo-Brazzaville": "CG",
    "Dominican Republic": "DO",
    "Central African Republic": "CF",
    "Equatorial Guinea": "GQ",
    "Falkland Islands": "FK",
    "Solomon Islands": "SB",
    "South Sudan": "SS",
    "Western Sahara": "EH",
    # Data quirks (from Observable's second countryNameMap)
    "SPAIN(CANARY IS)": "ES", "SPAIN (CANARY IS)": "ES",
    "UNITED KINGDOM": "GB",
    # Formal long names
    "Venezuela, Bolivarian Republic of": "VE",
    "Bolivia, Plurinational State of": "BO",
    "Tanzania, United Republic of": "TZ", "United Republic of Tanzania": "TZ",
}


# ── Helper builders ─────────────────────────────────────────────────

def build_iso2_to_topojson() -> dict[str, str]:
    """ISO-2 → TopoJSON name."""
    return {iso2: topo for iso2, (_, topo, _) in COUNTRY_DATA.items()}


def build_iso3_to_topojson() -> dict[str, str]:
    """ISO-3 → TopoJSON name."""
    return {iso3: topo for _, (iso3, topo, _) in COUNTRY_DATA.items()}


def build_alias_to_topojson() -> dict[str, str]:
    """Lowercase alias → TopoJSON name.

    Also maps each TopoJSON name's lowercase form to itself so that input
    like "SPAIN", "Spain", or "spain" all normalize to "Spain".
    """
    iso2_to_topo = build_iso2_to_topojson()
    result = {alias.lower(): iso2_to_topo[iso2]
              for alias, iso2 in COUNTRY_ALIASES.items()
              if iso2 in iso2_to_topo}
    # Identity entries: each topojson name maps to itself (case-insensitive)
    for topo_name in iso2_to_topo.values():
        result.setdefault(topo_name.lower(), topo_name)
    return result


def build_iso2_to_plotly() -> dict[str, str]:
    """ISO-2 → Plotly name."""
    return {iso2: plotly for iso2, (_, _, plotly) in COUNTRY_DATA.items()}


def build_iso3_to_plotly() -> dict[str, str]:
    """ISO-3 → Plotly name."""
    return {iso3: plotly for _, (iso3, _, plotly) in COUNTRY_DATA.items()}


def build_alias_to_plotly() -> dict[str, str]:
    """Lowercase alias → Plotly name.

    Also maps each Plotly name's lowercase form to itself so that input
    like "SPAIN", "Spain", or "spain" all normalize to "Spain".
    """
    iso2_to_plotly = build_iso2_to_plotly()
    result = {alias.lower(): iso2_to_plotly[iso2]
              for alias, iso2 in COUNTRY_ALIASES.items()
              if iso2 in iso2_to_plotly}
    for plotly_name in iso2_to_plotly.values():
        result.setdefault(plotly_name.lower(), plotly_name)
    return result


def _dict_to_js(d: dict[str, str], name: str) -> str:
    """Serialize a dict to a JS const declaration."""
    pairs = ", ".join(f'"{k}":"{v}"' for k, v in d.items())
    return f"const {name} = {{{pairs}}};"


def country_mapping_as_js(target: str = "topojson") -> str:
    """Return JS snippet declaring iso2/iso3/alias lookup objects.

    target: "topojson" or "plotly"
    """
    if target == "plotly":
        iso2 = build_iso2_to_plotly()
        iso3 = build_iso3_to_plotly()
        alias = build_alias_to_plotly()
        suffix = "Plotly"
    else:
        iso2 = build_iso2_to_topojson()
        iso3 = build_iso3_to_topojson()
        alias = build_alias_to_topojson()
        suffix = "Topo"
    lines = [
        _dict_to_js(iso2, f"iso2To{suffix}"),
        _dict_to_js(iso3, f"iso3To{suffix}"),
        _dict_to_js(alias, f"aliasTo{suffix}"),
    ]
    return "\n".join(lines)


def country_mapping_as_python() -> str:
    """Return Python snippet declaring iso2/iso3/alias lookup dicts (for Streamlit)."""
    iso2 = build_iso2_to_topojson()
    iso3 = build_iso3_to_topojson()
    alias = build_alias_to_topojson()
    return (
        f"_ISO2_TO_TOPO = {iso2!r}\n"
        f"_ISO3_TO_TOPO = {iso3!r}\n"
        f"_ALIAS_TO_TOPO = {alias!r}"
    )
