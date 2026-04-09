"""
Superset Transformer - Directly creates Superset dashboards via REST API
"""
from typing import TYPE_CHECKING, Dict, Any, Optional
from pathlib import Path
import yaml
import json
import time
try:
    import prison
except ImportError:
    prison = None
from .base import Transformer, TransformerError

if TYPE_CHECKING:
    from ..core.types import NormalizedSpec, ChartSpec

# ============================================================
# Custom Exceptions
# ============================================================

class SupersetAuthenticationError(TransformerError):
    """Raised when Superset authentication fails"""
    pass

class SupersetDatasetError(TransformerError):
    """Raised when dataset operations fail"""
    pass

class SupersetChartError(TransformerError):
    """Raised when chart operations fail"""
    pass

class SupersetDashboardError(TransformerError):
    """Raised when dashboard operations fail"""
    pass

# ============================================================
# Configuration Constants
# ============================================================

# API Configuration
DEFAULT_SUPERSET_URL = "http://localhost:8088"
API_LOGIN_ENDPOINT = "/api/v1/security/login"
API_CSRF_ENDPOINT = "/api/v1/security/csrf_token/"
API_DATASET_ENDPOINT = "/api/v1/dataset/"
API_DATABASE_ENDPOINT = "/api/v1/database/"
API_CHART_ENDPOINT = "/api/v1/chart/"
API_DASHBOARD_ENDPOINT = "/api/v1/dashboard/"
API_CHART_DATA_ENDPOINT = "/api/v1/chart/data"
AUTH_PROVIDER = "db"

# Retry & Timeout Settings
DATASET_CREATION_WAIT_SECONDS = 5
RETRY_WAIT_SECONDS = 3
MAX_DATASET_FIND_ATTEMPTS = 3

# Query Limits
UNIQUE_VALUES_ROW_LIMIT = 1000
RAW_DATA_ROW_LIMIT = 10000
CHART_LIST_PAGE_SIZE = 1000

# Layout & Display Settings
CHARTS_PER_ROW = 2
DEFAULT_CHART_WIDTH = 6  # Grid units (out of 12)
DEFAULT_CHART_HEIGHT = 50
DASHBOARD_HEADER_TEXT = "Dashboard"
DASHBOARD_BACKGROUND = "BACKGROUND_TRANSPARENT"

# Chart Configuration
DEFAULT_HISTOGRAM_BINS = 20
DEFAULT_COLOR_SCHEME = "supersetColors"

# CSV Upload Settings
CSV_DELIMITER = ','
CSV_ALREADY_EXISTS_ACTION = 'replace'
CSV_FILE_TYPE = 'csv'
CSV_CONTENT_TYPE = 'text/csv'
JSON_CONTENT_TYPE = "application/json"

# Default Colors
DEFAULT_COLORS = {
    "primary": "#20A7C9",
    "secondary": ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'],
    "background": "#FAFAFA",
    "text": "#11181C",
    "card": "#FFFFFF"
}

# Import shared constants
from .constants import (
    CHARTS_NEED_AGGREGATION,
    CHARTS_USE_RAW_DATA,
    DEFAULT_HISTOGRAM_BINS as SHARED_DEFAULT_HISTOGRAM_BINS,
    DEFAULT_PRIMARY_COLOR,
    DEFAULT_SECONDARY_COLORS,
)

# Map DashML chart types to Superset viz types
# Modern Superset uses ECharts-based visualizations
DASHML_TO_SUPERSET_VIZ = {
    "bar": "echarts_timeseries",  # ECharts timeseries with bar transform
    "line": "echarts_timeseries",  # ECharts timeseries with line
    "scatter": "echarts_timeseries_scatter",  # ECharts scatter (supports any x-axis)
    "bubble": "bubble_v2",  # ECharts bubble chart (scatter with size)
    "heatmap": "heatmap_v2",  # Heatmap (2D grid with color intensity)
    "box": "box_plot",  # Box plot (distribution: min, Q1, median, Q3, max)
    "pie": "pie",
    "area": "echarts_area",
    "histogram": "histogram_v2",  # Modern histogram viz type
    "stacked_bar": "echarts_timeseries",  # ECharts timeseries with stacking
    "grouped_bar": "echarts_timeseries",  # ECharts timeseries with grouping
    "geo": "world_map",  # World map choropleth by country
}


class SupersetTransformer(Transformer):
    """
    Directly creates dashboards in Apache Superset via REST API.
    No code generation - executes API calls immediately.
    """

    def __init__(self, superset_url: str = None, username: str = None, password: str = None):
        super().__init__()
        self.superset_url = superset_url or DEFAULT_SUPERSET_URL
        self.username = username
        self.password = password
        self.access_token = None
        self.csrf_token = None
        self.dataset_id = None
        self.session = None  # Will hold requests.Session for cookie management
        self._db_config = None  # Set from spec during build()

    @property
    def name(self) -> str:
        return "superset"

    @property
    def description(self) -> str:
        return "Creates dashboards directly in Apache Superset via REST API"

    def build(self, spec: "NormalizedSpec") -> str:
        """Create dashboard in Superset and return success message"""
        try:
            import requests
            # Create a session to maintain cookies (important for CSRF)
            self.session = requests.Session()
        except ImportError:
            raise TransformerError(
                "requests library required for Superset transformer.\n"
                "Install with: pip install requests"
            )

        if not self.username or not self.password:
            raise SupersetAuthenticationError(
                "Superset credentials required.\n"
                "Use: --superset-user and --superset-password CLI arguments"
            )

        try:
            self.clear_warnings()
            print("\n" + "=" * 60)
            print("DashML → Apache Superset Dashboard Creator")
            print("=" * 60)
            print()

            # Authenticate
            if not self._authenticate():
                raise SupersetAuthenticationError("Authentication failed")

            # Use resolved style from normalizer
            style_config = {"colors": spec["style"]}

            # Store db_config for internal methods that need it
            self._db_config = spec.get("db_config", {})

            # Extract spec components
            title = spec["title"]
            data_spec = spec["data"]
            data_type = data_spec.get("type", "csv")

            # Create or get dataset based on data type
            if data_type == "csv":
                # CSV datasource - use pre-resolved path from normalizer
                data_path = data_spec.get("csv_path") or data_spec["path"]
                data_path = str(Path(data_path).resolve())

                if not self._create_or_get_dataset_csv(data_path):
                    raise SupersetDatasetError("Failed to create/find CSV dataset")

            elif data_type == "sql":
                # Use pre-parsed path components from normalizer
                schema = data_spec["sql_schema"]
                table_name = data_spec["sql_table"]

                # Determine database_id: either auto-create from db_config or use from spec
                if self._db_config:
                    database_id = self._create_or_get_database()
                    if not database_id:
                        raise SupersetDatasetError("Failed to create/find database in Superset")
                elif "database_id" in data_spec:
                    database_id = data_spec["database_id"]
                else:
                    raise SupersetDatasetError(
                        "SQL datasource requires either:\n"
                        "  1. database_id in spec (for pre-configured databases), OR\n"
                        "  2. --db-* CLI arguments to auto-create database"
                    )

                if not self._create_or_get_dataset_sql(database_id, schema, table_name):
                    raise SupersetDatasetError("Failed to create/find SQL dataset")

            elif data_type == "bigquery":
                if not self._db_config:
                    raise SupersetDatasetError(
                        "BigQuery datasource requires --bq-project CLI argument"
                    )

                # Use pre-parsed path components from normalizer
                bq_dataset = data_spec["bq_dataset"]
                table_name = data_spec["bq_table"]

                database_id = self._create_or_get_bigquery_database()
                if not database_id:
                    raise SupersetDatasetError("Failed to create/find BigQuery database in Superset")

                if not self._create_or_get_dataset_sql(database_id, bq_dataset, table_name):
                    raise SupersetDatasetError("Failed to create/find BigQuery dataset")

            else:
                raise SupersetDatasetError(f"Unsupported data type: {data_type}")

            # Always use pages (normalizer guarantees pages[] exists)
            pages = spec["pages"]

            # Get existing charts from dashboard if updating
            existing_chart_map = {}  # Maps chart names to IDs
            existing_dashboard_id = self._find_existing_dashboard(title)
            if existing_dashboard_id:
                detail_url = f"{self.superset_url}/api/v1/dashboard/{existing_dashboard_id}"
                detail_response = self.session.get(detail_url, headers=self._get_headers())
                if detail_response.status_code == 200:
                    old_chart_ids = detail_response.json().get("result", {}).get("charts", [])
                    # Get chart names
                    for chart_id in old_chart_ids:
                        chart_url = f"{self.superset_url}/api/v1/chart/{chart_id}"
                        chart_response = self.session.get(chart_url, headers=self._get_headers())
                        if chart_response.status_code == 200:
                            chart_name = chart_response.json().get("result", {}).get("slice_name")
                            if chart_name:
                                existing_chart_map[chart_name] = chart_id

            # Create or update charts
            print("\nCreating/updating charts...")
            chart_ids = []
            all_label_colors = {}  # Collect all label->color mappings from all charts

            for page in pages:
                page_id = page["id"]
                print(f"\nProcessing page: {page.get('title', page_id)}")
                for chart in page.get("charts", []):
                    chart_id, label_colors = self._create_or_update_chart(
                        f"{page_id}_{chart['id']}",
                        chart,
                        style_config,
                        existing_chart_map
                    )
                    if chart_id:
                        chart_ids.append(chart_id)
                        if label_colors:
                            all_label_colors.update(label_colors)

            if not chart_ids:
                raise SupersetChartError("No charts were created successfully")

            # Create or update dashboard
            print("\nCreating/updating dashboard...")
            # Use layout columns from the first page (Superset has a single flat layout)
            layout_columns = None
            for p in pages:
                lc = p.get("layout", {}).get("columns")
                if lc:
                    layout_columns = lc
                    break
            dashboard_id = self._create_or_update_dashboard(title, chart_ids, charts_per_row=layout_columns)

            if not dashboard_id:
                raise SupersetDashboardError("Failed to create dashboard")

            # Set dashboard colors from theme
            self._set_dashboard_colors(dashboard_id, style_config, all_label_colors)

            dashboard_url = f"{self.superset_url}/superset/dashboard/{dashboard_id}/"
            success_msg = f"\n🎉 Dashboard created successfully!\n\nURL: {dashboard_url}\n"
            print(success_msg)

            return success_msg

        except (SupersetAuthenticationError, SupersetDatasetError, SupersetChartError, SupersetDashboardError):
            # Re-raise our custom exceptions
            raise
        except ImportError as e:
            raise TransformerError(f"Missing required library: {e}")
        except Exception as e:
            raise TransformerError(f"Unexpected error creating Superset dashboard: {e}")

    def _authenticate(self) -> bool:
        """Authenticate with Superset and get tokens"""
        login_url = f"{self.superset_url}{API_LOGIN_ENDPOINT}"
        payload = {
            "username": self.username,
            "password": self.password,
            "provider": AUTH_PROVIDER,
            "refresh": True
        }

        try:
            response = self.session.post(login_url, json=payload)
            response.raise_for_status()
            data = response.json()
            self.access_token = data.get("access_token")

            # Get CSRF token - session will keep the cookie
            csrf_url = f"{self.superset_url}{API_CSRF_ENDPOINT}"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            csrf_response = self.session.get(csrf_url, headers=headers)
            csrf_response.raise_for_status()
            self.csrf_token = csrf_response.json().get("result")

            print(f"✓ Authenticated successfully")
            return True

        except Exception as e:
            print(f"✗ Authentication failed: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with auth token and CSRF"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-CSRFToken": self.csrf_token,
            "Content-Type": JSON_CONTENT_TYPE
        }

    def _refresh_csrf_token(self) -> bool:
        """Refresh CSRF token - useful before POST/PUT requests"""
        try:
            csrf_url = f"{self.superset_url}{API_CSRF_ENDPOINT}"
            csrf_headers = {"Authorization": f"Bearer {self.access_token}"}
            csrf_response = self.session.get(csrf_url, headers=csrf_headers)
            if csrf_response.status_code == 200:
                self.csrf_token = csrf_response.json().get("result")
                return True
        except Exception as e:
            self.warn(f"Failed to refresh CSRF token: {e}")
        return False

    def _build_api_url(self, endpoint: str, resource_id: str = None) -> str:
        """Build a complete API URL with optional resource ID"""
        if resource_id:
            return f"{self.superset_url}{endpoint}{resource_id}"
        return f"{self.superset_url}{endpoint}"

    def _associate_chart_with_dashboard(self, chart_id: int, dashboard_id: int) -> bool:
        """Associate a chart with a dashboard"""
        try:
            chart_url = self._build_api_url(API_CHART_ENDPOINT, chart_id)
            # Get current dashboards for this chart
            chart_response = self.session.get(chart_url, headers=self._get_headers())
            if chart_response.status_code == 200:
                chart_data = chart_response.json().get("result", {})
                dashboards = chart_data.get("dashboards", [])
                # Add this dashboard if not already there
                if dashboard_id not in dashboards:
                    dashboards.append(dashboard_id)
                    update_response = self.session.put(chart_url, headers=self._get_headers(), json={"dashboards": dashboards})
                    return update_response.status_code in [200, 201]
                return True
        except Exception as e:
            self.warn(f"Failed to associate chart {chart_id} with dashboard {dashboard_id}: {e}")
        return False

    def _create_or_get_dataset_csv(self, csv_path: str) -> bool:
        """Create dataset from CSV or get existing one"""
        dataset_name = Path(csv_path).stem
        search_url = f"{self.superset_url}{API_DATASET_ENDPOINT}"

        # Check if dataset already exists
        try:
            response = self.session.get(search_url, headers=self._get_headers())
            if response.status_code == 200:
                datasets = response.json().get("result", [])
                for ds in datasets:
                    if ds.get("table_name") == dataset_name:
                        self.dataset_id = ds.get("id")
                        print(f"✓ Found existing dataset: {dataset_name} (ID: {self.dataset_id})")
                        return True
        except Exception as e:
            print(f"⚠ Warning checking for existing dataset: {e}")

        # Dataset not found, upload CSV
        print(f"Dataset '{dataset_name}' not found. Uploading CSV...")

        if not Path(csv_path).exists():
            print(f"✗ Error: CSV file not found at {csv_path}")
            return False

        try:
            # First, get the database ID (usually 1 for the examples/default database)
            db_url = f"{self.superset_url}{API_DATABASE_ENDPOINT}"
            db_response = self.session.get(db_url, headers=self._get_headers())

            database_id = None
            if db_response.status_code == 200:
                databases = db_response.json().get("result", [])
                if databases:
                    # Use the first available database that allows uploads
                    for db in databases:
                        if db.get("allow_file_upload", False):
                            database_id = db.get("id")
                            print(f"  Found database with upload enabled: {db.get('database_name')} (ID: {database_id})")
                            break

                    if not database_id:
                        print(f"  ✗ No database allows CSV uploads!")
                        print(f"  Available databases:")
                        for db in databases[:5]:
                            print(f"    - {db.get('database_name')} (ID: {db.get('id')}, allow_upload: {db.get('allow_file_upload', False)})")
                        print(f"\n  To enable CSV uploads:")
                        print(f"  1. Go to {self.superset_url}/databaseview/list/")
                        print(f"  2. Edit your database")
                        print(f"  3. Check 'Allow File Upload'")
                        print(f"  4. Save and run this command again")
                        return False

            if not database_id:
                print(f"  ✗ Could not find any database")
                return False

            print(f"  Using database ID: {database_id}")

            with open(csv_path, 'rb') as f:
                files = {'file': (Path(csv_path).name, f, CSV_CONTENT_TYPE)}
                data = {
                    'type': CSV_FILE_TYPE,  # Required field
                    'table_name': dataset_name,
                    'delimiter': CSV_DELIMITER,
                    'already_exists': CSV_ALREADY_EXISTS_ACTION,
                    # Don't specify schema - let it use the default allowed schema
                }

                upload_headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "X-CSRFToken": self.csrf_token
                }

                # Try new unified endpoint first (Superset 5.0+)
                upload_url = f"{self.superset_url}/api/v1/database/{database_id}/upload"
                response = self.session.post(upload_url, headers=upload_headers, files=files, data=data)

                # If 404, try old endpoint (pre-5.0)
                if response.status_code == 404:
                    upload_url = f"{self.superset_url}/api/v1/database/{database_id}/csv_upload"
                    with open(csv_path, 'rb') as f2:
                        files = {'file': (Path(csv_path).name, f2, CSV_CONTENT_TYPE)}
                        response = self.session.post(upload_url, headers=upload_headers, files=files, data=data)

                if response.status_code in [200, 201, 302]:
                    print(f"✓ CSV uploaded successfully")

                    # Check the response for table info
                    try:
                        response_data = response.json()
                        print(f"  Upload response: {response_data}")
                    except Exception:
                        # Response may not be JSON; continue without printing
                        pass

                    # The CSV upload creates a table, but we need to create a dataset from it
                    # Let's try to create the dataset explicitly
                    print(f"  Creating dataset from uploaded table...")

                    # Refresh CSRF token before POST request
                    self._refresh_csrf_token()

                    dataset_payload = {
                        "database": database_id,
                        "table_name": dataset_name
                        # Don't specify schema - let it use default
                    }

                    # Add referer header - sometimes required by Superset
                    dataset_headers = self._get_headers()
                    dataset_headers["Referer"] = self.superset_url

                    create_dataset_url = f"{self.superset_url}{API_DATASET_ENDPOINT}"
                    dataset_response = self.session.post(
                        create_dataset_url,
                        headers=dataset_headers,
                        json=dataset_payload
                    )

                    if dataset_response.status_code in [200, 201]:
                        dataset_data = dataset_response.json()
                        self.dataset_id = dataset_data.get("id")
                        print(f"✓ Dataset created: {dataset_name} (ID: {self.dataset_id})")
                        return True
                    else:
                        print(f"  Dataset creation failed: {dataset_response.status_code}")
                        try:
                            print(f"  Error: {dataset_response.json()}")
                        except Exception:
                            print(f"  Error: {dataset_response.text[:500]}")

                    print(f"  Waiting for dataset to be created...")
                    time.sleep(DATASET_CREATION_WAIT_SECONDS)

                    # Try to find the dataset multiple times
                    for attempt in range(MAX_DATASET_FIND_ATTEMPTS):
                        search_response = self.session.get(search_url, headers=self._get_headers())
                        if search_response.status_code == 200:
                            datasets = search_response.json().get("result", [])

                            # Try exact match first
                            for ds in datasets:
                                if ds.get("table_name") == dataset_name:
                                    self.dataset_id = ds.get("id")
                                    print(f"✓ Dataset found: {dataset_name} (ID: {self.dataset_id})")
                                    return True

                            # Try case-insensitive match
                            for ds in datasets:
                                if ds.get("table_name", "").lower() == dataset_name.lower():
                                    self.dataset_id = ds.get("id")
                                    print(f"✓ Dataset found: {ds.get('table_name')} (ID: {self.dataset_id})")
                                    return True

                            # Try partial match
                            for ds in datasets:
                                if dataset_name.lower() in ds.get("table_name", "").lower():
                                    self.dataset_id = ds.get("id")
                                    print(f"✓ Dataset found: {ds.get('table_name')} (ID: {self.dataset_id})")
                                    return True

                        if attempt < MAX_DATASET_FIND_ATTEMPTS - 1:
                            print(f"  Attempt {attempt + 1}/{MAX_DATASET_FIND_ATTEMPTS}: Dataset not found yet, waiting...")
                            time.sleep(RETRY_WAIT_SECONDS)

                    # Dataset still not found, list available datasets for debugging
                    print(f"⚠ CSV uploaded but dataset '{dataset_name}' not found.")
                    print(f"  Available datasets:")
                    if search_response.status_code == 200:
                        datasets = search_response.json().get("result", [])
                        for ds in datasets[:10]:  # Show first 10
                            print(f"    - {ds.get('table_name')} (ID: {ds.get('id')})")
                    return False
                else:
                    print(f"✗ CSV upload failed: {response.status_code}")
                    print(f"  Response: {response.text[:500]}")
                    return False

        except Exception as e:
            print(f"✗ Error uploading CSV: {e}")
            return False

    def _create_or_get_dataset_sql(self, database_id: int, schema: str, table_name: str) -> bool:
        """Create dataset from existing SQL table or get existing one"""
        search_url = f"{self.superset_url}{API_DATASET_ENDPOINT}"

        # Check if dataset already exists
        try:
            response = self.session.get(search_url, headers=self._get_headers())
            if response.status_code == 200:
                datasets = response.json().get("result", [])
                for ds in datasets:
                    # Match on database_id, schema, and table_name
                    if (ds.get("database", {}).get("id") == database_id and
                        ds.get("schema") == schema and
                        ds.get("table_name") == table_name):
                        self.dataset_id = ds.get("id")
                        print(f"✓ Found existing dataset: {schema}.{table_name} (ID: {self.dataset_id})")
                        return True
        except Exception as e:
            print(f"⚠ Warning checking for existing dataset: {e}")

        # Dataset not found, create from existing SQL table
        print(f"Dataset '{schema}.{table_name}' not found. Creating from existing table...")

        try:
            # Refresh CSRF token before POST request
            self._refresh_csrf_token()

            # Create dataset payload
            dataset_payload = {
                "database": database_id,
                "schema": schema,
                "table_name": table_name
            }

            # Add referer header - sometimes required by Superset
            dataset_headers = self._get_headers()
            dataset_headers["Referer"] = self.superset_url

            create_dataset_url = f"{self.superset_url}{API_DATASET_ENDPOINT}"
            dataset_response = self.session.post(
                create_dataset_url,
                headers=dataset_headers,
                json=dataset_payload
            )

            if dataset_response.status_code in [200, 201]:
                dataset_data = dataset_response.json()
                self.dataset_id = dataset_data.get("id")
                print(f"✓ Dataset created: {schema}.{table_name} (ID: {self.dataset_id})")

                # Trigger metadata refresh to introspect table columns
                print(f"  Fetching table metadata...")
                metadata_url = f"{self.superset_url}{API_DATASET_ENDPOINT}{self.dataset_id}/refresh"
                metadata_response = self.session.put(
                    metadata_url,
                    headers=self._get_headers(),
                    json={"columns": []}
                )

                if metadata_response.status_code in [200, 201]:
                    print(f"✓ Metadata fetched successfully")
                else:
                    print(f"⚠ Metadata fetch returned status {metadata_response.status_code}")

                return True
            else:
                print(f"✗ Dataset creation failed: {dataset_response.status_code}")
                try:
                    error_data = dataset_response.json()
                    print(f"  Error: {error_data}")
                except:
                    print(f"  Error: {dataset_response.text[:500]}")
                return False

        except Exception as e:
            print(f"✗ Error creating SQL dataset: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _create_or_get_database(self) -> Optional[int]:
        """Create or find database connection in Superset using db_config"""
        if not self._db_config:
            return None

        db_type = self._db_config["type"]
        host = self._db_config["host"]
        port = self._db_config["port"]
        database = self._db_config["database"]
        user = self._db_config["user"]
        password = self._db_config["password"]

        # Build SQLAlchemy URI based on database type
        if db_type == "postgresql":
            sqlalchemy_uri = f"postgresql://{user}:{password}@{host}:{port}/{database}"
            backend = "postgresql"
        elif db_type == "mysql":
            sqlalchemy_uri = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
            backend = "mysql"
        elif db_type == "sqlite":
            sqlalchemy_uri = f"sqlite:///{database}"
            backend = "sqlite"
        else:
            print(f"✗ Unsupported database type: {db_type}")
            return None

        # Generate a database name for Superset
        db_name = f"{database}@{host}" if db_type != "sqlite" else database

        # Check if database already exists in Superset
        print(f"Checking for existing database connection: {db_name}")
        search_url = f"{self.superset_url}{API_DATABASE_ENDPOINT}"

        try:
            response = self.session.get(search_url, headers=self._get_headers())
            if response.status_code == 200:
                databases = response.json().get("result", [])
                for db in databases:
                    # Match on database_name and sqlalchemy_uri
                    if db.get("database_name") == db_name:
                        database_id = db.get("id")
                        print(f"✓ Found existing database: {db_name} (ID: {database_id})")
                        return database_id
        except Exception as e:
            print(f"⚠ Warning checking for existing database: {e}")

        # Database not found, create it
        print(f"Database '{db_name}' not found. Creating new database connection...")

        try:
            # Refresh CSRF token before POST request
            self._refresh_csrf_token()

            # Build database payload
            database_payload = {
                "database_name": db_name,
                "sqlalchemy_uri": sqlalchemy_uri,
                "expose_in_sqllab": True,
                "allow_run_async": True,
                "allow_file_upload": True,  # Enable CSV uploads
                "extra": "{}"
            }

            # Add referer header
            db_headers = self._get_headers()
            db_headers["Referer"] = self.superset_url

            create_db_url = f"{self.superset_url}{API_DATABASE_ENDPOINT}"
            db_response = self.session.post(
                create_db_url,
                headers=db_headers,
                json=database_payload
            )

            if db_response.status_code in [200, 201]:
                db_data = db_response.json()
                database_id = db_data.get("id")
                print(f"✓ Database created: {db_name} (ID: {database_id})")
                return database_id
            else:
                print(f"✗ Database creation failed: {db_response.status_code}")
                try:
                    error_data = db_response.json()
                    print(f"  Error: {error_data}")
                except Exception:
                    print(f"  Error: {db_response.text[:500]}")
                return None

        except Exception as e:
            print(f"✗ Error creating database: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _create_or_get_bigquery_database(self) -> Optional[int]:
        """Create or find BigQuery database connection in Superset using db_config"""
        if not self._db_config:
            return None

        project = self._db_config["project"]
        credentials_path = self._db_config.get("credentials_path")

        # Build BigQuery SQLAlchemy URI
        # Format: bigquery://project
        sqlalchemy_uri = f"bigquery://{project}"

        # Load credentials JSON if path provided
        credentials_info = None
        if credentials_path:
            try:
                with open(credentials_path, 'r') as f:
                    credentials_info = json.load(f)
                print(f"✓ Loaded BigQuery credentials from: {credentials_path}")
            except Exception as e:
                print(f"⚠ Warning: Could not load credentials file: {e}")

        # Generate a database name for Superset
        db_name = f"BigQuery ({project})"

        # Check if database already exists in Superset
        print(f"Checking for existing BigQuery connection: {db_name}")
        search_url = f"{self.superset_url}{API_DATABASE_ENDPOINT}"

        try:
            response = self.session.get(search_url, headers=self._get_headers())
            if response.status_code == 200:
                databases = response.json().get("result", [])
                for db in databases:
                    if db.get("database_name") == db_name:
                        database_id = db.get("id")
                        print(f"✓ Found existing BigQuery database: {db_name} (ID: {database_id})")
                        return database_id
        except Exception as e:
            print(f"⚠ Warning checking for existing database: {e}")

        # Database not found, create it
        print(f"BigQuery database '{db_name}' not found. Creating new database connection...")

        try:
            # Refresh CSRF token before POST request
            self._refresh_csrf_token()

            # Build encrypted_extra with credentials_info for BigQuery
            # This passes the service account JSON directly to Superset
            encrypted_extra = {}
            if credentials_info:
                encrypted_extra["credentials_info"] = credentials_info

            # Build database payload for BigQuery
            database_payload = {
                "database_name": db_name,
                "sqlalchemy_uri": sqlalchemy_uri,
                "expose_in_sqllab": True,
                "allow_run_async": True,
                "allow_file_upload": False,  # BigQuery doesn't support CSV uploads via Superset
                "extra": "{}",
                "encrypted_extra": json.dumps(encrypted_extra) if encrypted_extra else "{}"
            }

            # Add referer header
            db_headers = self._get_headers()
            db_headers["Referer"] = self.superset_url

            create_db_url = f"{self.superset_url}{API_DATABASE_ENDPOINT}"
            db_response = self.session.post(
                create_db_url,
                headers=db_headers,
                json=database_payload
            )

            if db_response.status_code in [200, 201]:
                db_data = db_response.json()
                database_id = db_data.get("id")
                print(f"✓ BigQuery database created: {db_name} (ID: {database_id})")
                return database_id
            else:
                print(f"✗ BigQuery database creation failed: {db_response.status_code}")
                try:
                    error_data = db_response.json()
                    print(f"  Error: {error_data}")
                except Exception:
                    print(f"  Error: {db_response.text[:500]}")
                return None

        except Exception as e:
            print(f"✗ Error creating BigQuery database: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_unique_values(self, column: str) -> list:
        """Query the dataset to get unique values for a column"""
        try:
            # Query the dataset via the chart data API
            query_payload = {
                "datasource": {"id": self.dataset_id, "type": "table"},
                "queries": [{
                    "columns": [column],
                    "groupby": [column],
                    "metrics": [],
                    "row_limit": UNIQUE_VALUES_ROW_LIMIT,
                }],
                "result_format": "json",
                "result_type": "full"
            }

            url = f"{self.superset_url}{API_CHART_DATA_ENDPOINT}"
            response = self.session.post(url, headers=self._get_headers(), json=query_payload)

            if response.status_code == 200:
                result = response.json()
                if "result" in result and len(result["result"]) > 0:
                    data = result["result"][0].get("data", [])
                    return [row.get(column) for row in data if row.get(column) is not None]
        except Exception as e:
            self.warn(f"Failed to get unique values for column '{column}': {e}")
        return []

    def _find_existing_dashboard(self, title: str) -> Optional[int]:
        """Find existing dashboard by title"""
        url = f"{self.superset_url}{API_DASHBOARD_ENDPOINT}"
        try:
            response = self.session.get(url, headers=self._get_headers())
            if response.status_code == 200:
                dashboards = response.json().get("result", [])
                for dashboard in dashboards:
                    if dashboard.get("dashboard_title") == title:
                        return dashboard.get("id")
        except Exception as e:
            self.warn(f"Failed to find existing dashboard '{title}': {e}")
        return None

    def _set_dashboard_colors(self, dashboard_id: int, style_config: Dict[str, Any], label_colors: Dict[str, str] = None) -> None:
        """Set dashboard-level color configuration from theme"""
        if not label_colors:
            return

        # shared_label_colors should be a list of LABEL NAMES that are shared across charts
        # NOT a list of hex colors! See: superset-frontend/src/utils/colorScheme.ts:40-49
        shared_labels = list(label_colors.keys())

        # Build color configuration for dashboard
        color_config = {
            "color_scheme": DEFAULT_COLOR_SCHEME,  # Base scheme
            "label_colors": label_colors,  # Forced label-to-color mappings
            "shared_label_colors": shared_labels,  # List of label names shared across charts
            "map_label_colors": label_colors,  # Full label-to-color map
            "color_scheme_domain": shared_labels  # Domain of all labels
        }

        try:
            url = f"{self.superset_url}/api/v1/dashboard/{dashboard_id}/colors"
            response = self.session.put(url, headers=self._get_headers(), json=color_config)

            if response.status_code == 200:
                print(f"✓ Applied theme colors ({len(label_colors)} categories, {len(shared_labels)} shared)")

                # Fetch and display the actual saved metadata
                dash_url = f"{self.superset_url}/api/v1/dashboard/{dashboard_id}"
                dash_response = self.session.get(dash_url, headers=self._get_headers())
                if dash_response.status_code == 200:
                    dash_data = dash_response.json()
                    metadata_str = dash_data.get("result", {}).get("json_metadata", "{}")
                    metadata = json.loads(metadata_str)
                    print(f"\nDashboard metadata (json_metadata):")
                    print(json.dumps(metadata, indent=2))
            else:
                print(f"⚠ Warning: Could not apply dashboard colors ({response.status_code})")
        except Exception as e:
            print(f"⚠ Warning: Could not apply dashboard colors: {e}")

    def _create_or_update_chart(self, chart_id: str, chart: Dict[str, Any], style_config: Dict[str, Any] = None, existing_chart_map: Dict[str, int] = None):
        """Create or update a chart in Superset

        Returns: Tuple of (chart_id, label_colors_dict)
        """
        if existing_chart_map is None:
            existing_chart_map = {}

        chart_type = chart["type"]
        title = chart.get("title", chart_id)

        # Check if chart already exists
        existing_chart_id = existing_chart_map.get(title)
        x = chart.get("x", "")
        y = chart.get("y", "")
        agg = chart.get("agg", "sum")
        # When normalizer moved y→group for count agg, y is empty
        if not y and agg == "count" and chart_type != "metric":
            y = "count"
        # Map DashML agg to Superset aggregate names
        superset_agg = {"sum": "SUM", "mean": "AVG", "count": "COUNT"}.get(agg, "SUM")
        group = chart.get("group")
        x_type = chart.get("x_type")  # Optional: "date", "number", "string" for sorting
        y_type = chart.get("y_type")  # Optional: "number", "string" for casting
        bins = chart.get("bins", DEFAULT_HISTOGRAM_BINS)  # Number of bins for histogram
        filters = chart.get("filters", [])  # Optional: filter conditions
        sort_field = chart.get("sort")  # Optional: "x" or "y"
        sort_order = chart.get("sort_order", "asc")  # Optional: "asc" or "desc"
        limit = chart.get("limit")  # Optional: max rows after aggregation

        viz_type = DASHML_TO_SUPERSET_VIZ.get(chart_type, "dist_bar")
        # Metric charts use big_number_total
        if chart_type == "metric":
            viz_type = "big_number_total"

        # Get colors from style config
        if not style_config:
            style_config = {"colors": self._get_default_colors()}
        colors = style_config.get("colors", {})

        # Build adhoc_filters from DashML filters
        adhoc_filters = []
        for f in filters:
            field = f["field"]
            op = f["op"]
            value = f["value"]

            # Map DashML filter ops to Superset filter operators
            op_map = {
                "eq": "==",
                "ne": "!=",
                "gt": ">",
                "lt": "<",
                "gte": ">=",
                "lte": "<=",
                "in": "IN",
                "contains": "ILIKE",
            }
            superset_op = op_map.get(op, "==")

            # For 'contains', wrap value in wildcards
            if op == "contains":
                value = f"%{value}%"

            adhoc_filter = {
                "expressionType": "SIMPLE",
                "subject": field,
                "operator": superset_op,
                "comparator": value,
                "clause": "WHERE",
                "filterOptionName": f"filter_{field}_{op}"
            }
            adhoc_filters.append(adhoc_filter)

        # Build params with custom colors from theme
        params = {
            "datasource": f"{self.dataset_id}__table",
            "viz_type": viz_type,
            "adhoc_filters": adhoc_filters,
        }

        # Apply row_limit if specified
        if limit:
            params["row_limit"] = limit

        # Apply custom color scheme from DashML theme via label_colors
        params["color_scheme"] = DEFAULT_COLOR_SCHEME  # Use neutral base scheme
        params["label_colors"] = {}

        if "secondary" in colors and isinstance(colors["secondary"], list) and len(colors["secondary"]) > 0:
            custom_colors = colors["secondary"]

            # Determine which column contains the categories we want to color
            category_column = None
            if chart_type == "pie":
                category_column = x  # Pie chart groups by x
            elif chart_type in ["stacked_bar", "grouped_bar"] and group:
                category_column = group  # Stacked/grouped bar uses group column
            elif chart_type in ["bar", "line", "area"] and group:
                category_column = group

            # If we have a category column, query the dataset to get unique values
            if category_column:
                try:
                    unique_values = self._get_unique_values(category_column)
                    if unique_values:
                        # Assign colors from theme to each unique value (cycling if needed)
                        for i, value in enumerate(unique_values):
                            color_index = i % len(custom_colors)
                            color = custom_colors[color_index]
                            params["label_colors"][str(value)] = color
                except Exception as e:
                    # If we can't get unique values, just use the base color scheme
                    self.warn(f"Could not apply custom colors for '{category_column}': {e}")

        # Add metrics only for chart types that use them
        # Build metric label for orderby
        metric_label = f"{agg.lower()}__{y}"

        if chart_type == "metric":
            # Big number total: single aggregate value
            if agg == "count":
                params["metric"] = {
                    "expressionType": "SQL",
                    "label": "COUNT(*)",
                    "sqlExpression": "COUNT(*)",
                }
            else:
                params["metric"] = {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": y},
                    "aggregate": superset_agg,
                    "label": f"{superset_agg}({y})",
                }
        elif chart_type in ["bar", "line", "stacked_bar", "grouped_bar"]:
            # ECharts timeseries configuration
            params["x_axis"] = x
            if agg == "count":
                params["metrics"] = [{"expressionType": "SQL", "label": "COUNT(*)", "sqlExpression": "COUNT(*)"}]
            else:
                params["metrics"] = [{"label": y, "expressionType": "SIMPLE", "column": {"column_name": y}, "aggregate": superset_agg}]

            # Configure temporal axis if x_type is date
            if x_type == "date":
                params["x_axis_sort_asc"] = sort_order == "asc" if sort_field == "x" else True
                params["x_axis_time_format"] = "%Y-%m-%d"  # ISO date format

            # Apply explicit sorting
            if sort_field == "y":
                # Sort by metric value
                params["order_desc"] = sort_order == "desc"
            elif sort_field == "x" and x_type != "date":
                # For non-date x axis, use orderby
                params["orderby"] = [[x, sort_order == "asc"]]
            elif not sort_field and x_type != "date":
                # Default: sort strings alphabetically for consistency across transformers
                params["orderby"] = [[x, True]]  # True = ascending

            # Set series type based on chart type
            if chart_type == "bar":
                params["seriesType"] = "bar"
            elif chart_type == "line":
                params["seriesType"] = "line"
            elif chart_type in ["stacked_bar", "grouped_bar"]:
                params["seriesType"] = "bar"
                params["groupby"] = [group] if group else []
                # Sort grouped/stacked bars by total across all series
                if sort_field == "y":
                    params["x_axis_sort"] = "sum"
                    params["x_axis_sort_asc"] = sort_order == "asc"
                elif sort_field == "x":
                    params["x_axis_sort"] = "name"
                    params["x_axis_sort_asc"] = sort_order == "asc"
                # For stacked bar, enable stacking
                if chart_type == "stacked_bar":
                    params["stack"] = True
                    params["show_value"] = False
        elif chart_type == "area":
            # ECharts area uses x_axis and metrics
            params["x_axis"] = x
            if agg == "count":
                params["metrics"] = [{"expressionType": "SQL", "label": "COUNT(*)", "sqlExpression": "COUNT(*)"}]
            else:
                params["metrics"] = [{"label": y, "expressionType": "SIMPLE", "column": {"column_name": y}, "aggregate": superset_agg}]
            # Configure temporal axis if x_type is date
            if x_type == "date":
                params["x_axis_sort_asc"] = sort_order == "asc" if sort_field == "x" else True
                params["x_axis_time_format"] = "%Y-%m-%d"

            # Apply explicit sorting
            if sort_field == "y":
                params["order_desc"] = sort_order == "desc"
            elif not sort_field and x_type != "date":
                # Default: sort strings alphabetically for consistency across transformers
                params["orderby"] = [[x, True]]
        elif chart_type == "pie":
            # Pie chart uses singular 'metric' param with adhoc metric format
            if superset_agg == "COUNT":
                # Use SQL expression for COUNT
                params["metric"] = {
                    "expressionType": "SQL",
                    "label": f"COUNT({y})",
                    "sqlExpression": f"COUNT({y})"
                }
            else:
                # Use SIMPLE expression for SUM, AVG, etc.
                params["metric"] = {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": y},
                    "aggregate": superset_agg,
                    "label": f"{superset_agg}({y})"
                }
            params["groupby"] = [x]
            # Pie chart sorting
            if sort_field == "y":
                params["sort_by_metric"] = True
                params["order_desc"] = sort_order == "desc"
            else:
                params["sort_by_metric"] = True  # Default sort by metric
        elif chart_type == "scatter":
            # ECharts timeseries scatter - same structure as bar/line
            params["x_axis"] = x
            params["metrics"] = [{"label": y, "expressionType": "SIMPLE", "column": {"column_name": y}, "aggregate": superset_agg if agg else "AVG"}]
            params["seriesType"] = "scatter"

            # Apply sorting for scatter
            if sort_field == "y":
                params["order_desc"] = sort_order == "desc"
            elif sort_field == "x":
                if x_type == "date":
                    params["x_axis_sort_asc"] = sort_order == "asc"
                else:
                    params["orderby"] = [[x, sort_order == "asc"]]
            elif not sort_field and x_type != "date":
                # Default: sort strings alphabetically for consistency across transformers
                params["orderby"] = [[x, True]]
        elif chart_type == "bubble":
            # ECharts bubble_v2 - 4D visualization (entity, x, y, size)
            # Controls: entity (grouping column), x/y/size (metrics), series (optional)
            size_field = chart.get("size", y)  # Default to y if size not specified
            bubble_group = group if group else x  # Use group field as entity
            agg_upper = superset_agg if agg else "SUM"
            x_metric = {"label": f"{agg_upper}({x})", "expressionType": "SIMPLE", "column": {"column_name": x}, "aggregate": agg_upper}
            y_metric = {"label": f"{agg_upper}({y})", "expressionType": "SIMPLE", "column": {"column_name": y}, "aggregate": agg_upper}
            size_metric = {"label": f"{agg_upper}({size_field})", "expressionType": "SIMPLE", "column": {"column_name": size_field}, "aggregate": agg_upper}
            params["entity"] = bubble_group
            params["x"] = x_metric
            params["y"] = y_metric
            params["size"] = size_metric
            params["metrics"] = [x_metric, y_metric, size_metric]
            params["max_bubble_size"] = 25
        elif chart_type == "heatmap":
            # Heatmap v2: 2D grid with color intensity
            # x_axis = x-axis column, groupby = y-axis column, metric = value for color
            heatmap_y = group if group else y
            params["x_axis"] = x
            params["groupby"] = [heatmap_y]  # Y-axis dimension (multi=false but still array)
            # Metric for the value (color intensity)
            if superset_agg == "COUNT":
                params["metric"] = {
                    "expressionType": "SQL",
                    "label": f"COUNT({y})",
                    "sqlExpression": f"COUNT({y})"
                }
            else:
                params["metric"] = {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": y},
                    "aggregate": superset_agg,
                    "label": f"{superset_agg}({y})"
                }
            params["linear_color_scheme"] = colors.get("sequential", "blue_white_yellow")
            params["normalize_across"] = "heatmap"
            # Apply sorting
            if sort_field == "y":
                params["sort_by_metric"] = True
                params["order_desc"] = sort_order == "desc"
        elif chart_type == "box":
            # Box plot: shows distribution (min, Q1, median, Q3, max)
            # x = grouping column, y = values to compute distribution
            # boxplotOperator post-processing needs metrics to know which columns
            # to compute percentile statistics on
            params["groupby"] = [x]  # Group by x to show separate boxes
            params["columns"] = []  # Distribution column provided via metrics
            params["metrics"] = [{
                "label": y,
                "expressionType": "SIMPLE",
                "column": {"column_name": y},
                "aggregate": "AVG"
            }]
            params["whiskerOptions"] = "Tukey"
        elif chart_type == "histogram":
            # Histogram v2 uses different params than legacy histogram
            # NOTE: Superset uses numpy's exact bin calculation (data_range / bins),
            # unlike Plotly/Altair/Observable which use "nice" rounded bin edges.
            # This is a known platform limitation with no API workaround.
            params["column"] = x  # The column to create histogram from
            params["groupby"] = []  # Optional grouping columns
            params["bins"] = bins  # Number of bins from chart spec or default
            params["normalized"] = False  # Whether to normalize
            params["cumulative"] = False  # Whether to show cumulative distribution
            # No metrics for histogram!
        elif chart_type == "geo":
            # World map choropleth
            # x = country column, y = metric column
            # geo_encoding: "iso2", "iso3", or "name" → maps to Superset's country_fieldtype
            geo_encoding = chart.get("geo_encoding", "iso2")
            ENCODING_TO_SUPERSET = {"iso2": "cca2", "iso3": "cca3", "name": "name"}
            params["entity"] = x  # Column containing country names/codes
            params["country_fieldtype"] = ENCODING_TO_SUPERSET.get(geo_encoding, "cca2")
            # Build metric for the value to color by
            if superset_agg == "COUNT":
                params["metric"] = {
                    "expressionType": "SQL",
                    "label": f"COUNT({y})",
                    "sqlExpression": f"COUNT({y})"
                }
            else:
                params["metric"] = {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": y},
                    "aggregate": superset_agg,
                    "label": f"{superset_agg}({y})"
                }
            # Apply sorting
            if sort_field == "y":
                params["sort_by_metric"] = True
                params["order_desc"] = sort_order == "desc"

        # Build query_context
        query_context_queries = []
        if chart_type in CHARTS_USE_RAW_DATA:
            if chart_type == "histogram":
                # Histogram v2 uses a simpler structure
                query_obj = {
                    "columns": [x],
                    "groupby": [],
                    "metrics": [],
                    "filters": [],
                    "orderby": [],
                    "row_limit": RAW_DATA_ROW_LIMIT
                }
                query_context_queries.append(query_obj)
            elif chart_type == "box":
                # Box plot: fetch raw data, let viz compute statistics client-side
                # Superset's box_plot buildQuery sets groupby=[] and puts everything in columns
                query_obj = {
                    "columns": [x, y],
                    "groupby": [],
                    "metrics": [],
                    "filters": [],
                    "orderby": [],
                    "row_limit": RAW_DATA_ROW_LIMIT
                }
                query_context_queries.append(query_obj)
            else:
                # Fallback for other raw data chart types
                query_obj = {
                    "columns": [x, y],
                    "filters": [],
                    "orderby": [],
                    "row_limit": RAW_DATA_ROW_LIMIT
                }
                query_context_queries.append(query_obj)
        else:
            # Other charts use metrics
            # For ECharts charts, columns configuration varies
            columns = []
            if chart_type == "pie":
                # Pie charts need the grouping column (x) in the query
                columns = [x]
            elif chart_type in ["bar", "line", "area"]:
                # ECharts timeseries/area require the X-axis column to be fetched
                columns = [x]
            elif chart_type in ["stacked_bar", "grouped_bar"]:
                # Stacked/grouped bars need both the X-axis and the Grouping column
                columns = [x]
                if group:
                    columns.append(group)
            elif chart_type == "geo":
                # World map needs the country column (x) for grouping
                columns = [x]
            elif chart_type == "bubble":
                # Bubble chart: entity column for grouping, 3 metrics for x/y/size
                columns = [group if group else x]
                size_f = chart.get("size", y)
                agg_up = superset_agg if agg else "SUM"
                # Build deduplicated metrics for query_context
                bubble_metrics = {}
                for col in [x, y, size_f]:
                    label = f"{agg_up}({col})"
                    if label not in bubble_metrics:
                        bubble_metrics[label] = {
                            "label": label,
                            "expressionType": "SIMPLE",
                            "column": {"column_name": col},
                            "aggregate": agg_up
                        }
                query_metrics = list(bubble_metrics.values())
                query_orderby = []
                query_context_queries.append({
                    "columns": columns,
                    "metrics": query_metrics,
                    "filters": [],
                    "orderby": query_orderby,
                    "row_limit": RAW_DATA_ROW_LIMIT
                })
            elif chart_type == "heatmap":
                # Heatmap needs both x and y (group) for the 2D grid
                heatmap_y = group if group else y
                columns = [x, heatmap_y]
            else:
                columns = [x]

            if chart_type != "bubble":
                # Build metrics for query_context (bubble handles its own above)
                # Metric label format: "aggregate__column" (e.g., "sum__total_amount")
                metric_label = f"{agg.lower()}__{y}"
                metric_obj = {
                    "label": metric_label,
                    "expressionType": "SIMPLE",
                    "column": {"column_name": y},
                    "aggregate": superset_agg
                }
                query_metrics = [metric_obj]

                # Orderby uses the metric label string
                query_orderby = [[metric_label, False]]

                query_context_queries.append({
                    "columns": columns,
                    "metrics": query_metrics,
                    "filters": [],
                    "orderby": query_orderby,
                    "row_limit": RAW_DATA_ROW_LIMIT
                })

        chart_config = {
            "slice_name": title,
            "viz_type": viz_type,
            "datasource_id": self.dataset_id,
            "datasource_type": "table",
            "params": json.dumps(params),
        }

        # Skip query_context for pie, box - let Superset's buildQuery handle it
        if chart_type not in ("pie", "box"):
            chart_config["query_context"] = json.dumps({
                "datasource": {"id": self.dataset_id, "type": "table"},
                "force": False,
                "queries": query_context_queries,
                "form_data": params,
                "result_format": "json",
                "result_type": "full"
            })

        # Extract label_colors to return
        chart_label_colors = params.get("label_colors", {})

        try:
            if existing_chart_id:
                # Update existing chart
                url = self._build_api_url(API_CHART_ENDPOINT, existing_chart_id)
                response = self.session.put(url, headers=self._get_headers(), json=chart_config)
                response.raise_for_status()
                print(f"✓ Updated chart: {title} (ID: {existing_chart_id})")
                return existing_chart_id, chart_label_colors
            else:
                # Create new chart
                url = self._build_api_url(API_CHART_ENDPOINT)
                response = self.session.post(url, headers=self._get_headers(), json=chart_config)
                response.raise_for_status()
                created_chart_id = response.json().get("id")
                print(f"✓ Created chart: {title} (ID: {created_chart_id})")
                return created_chart_id, chart_label_colors
        except Exception as e:
            action = "update" if existing_chart_id else "create"
            print(f"✗ Failed to {action} chart {title}: {e}")
            return None, {}

    def _create_or_update_dashboard(self, title: str, chart_ids: list, charts_per_row: int = None) -> Optional[int]:
        """Create dashboard or update existing one"""
        url = f"{self.superset_url}{API_DASHBOARD_ENDPOINT}"

        # Check for existing dashboard
        existing_dashboard_id = None
        try:
            response = self.session.get(url, headers=self._get_headers())
            if response.status_code == 200:
                dashboards = response.json().get("result", [])
                for dashboard in dashboards:
                    if dashboard.get("dashboard_title") == title:
                        existing_dashboard_id = dashboard.get("id")
                        print(f"✓ Found existing dashboard: {title} (ID: {existing_dashboard_id})")
                        break
        except Exception as e:
            print(f"⚠ Warning checking for existing dashboard: {e}")

        if existing_dashboard_id:
            # Keep dashboard, delete all old charts, update with new charts
            try:
                print(f"  Cleaning up old charts from dashboard (ID: {existing_dashboard_id})...")
                detail_url = f"{self.superset_url}/api/v1/dashboard/{existing_dashboard_id}"
                detail_response = self.session.get(detail_url, headers=self._get_headers())

                # Collect ALL old chart IDs from every source
                old_chart_ids_set = set()
                if detail_response.status_code == 200:
                    dashboard_result = detail_response.json().get("result", {})

                    # From position_json
                    try:
                        position_json_str = dashboard_result.get("position_json", "{}")
                        position_json_data = json.loads(position_json_str)
                        for key, value in position_json_data.items():
                            if key.startswith("CHART-"):
                                if isinstance(value, dict) and "meta" in value:
                                    cid = value["meta"].get("chartId")
                                    if cid:
                                        old_chart_ids_set.add(cid)
                    except Exception:
                        pass

                    # From dashboard detail charts field
                    try:
                        for cid in dashboard_result.get("charts", []):
                            if isinstance(cid, int):
                                old_chart_ids_set.add(cid)
                            elif isinstance(cid, dict) and "id" in cid:
                                old_chart_ids_set.add(cid["id"])
                    except Exception:
                        pass

                # From chart API association query
                try:
                    if prison:
                        filter_params = {"filters": [{"col": "dashboards", "opr": "rel_m_m", "value": existing_dashboard_id}], "page_size": CHART_LIST_PAGE_SIZE}
                        charts_url = f"{self.superset_url}{API_CHART_ENDPOINT}?q={prison.dumps(filter_params)}"
                        charts_response = self.session.get(charts_url, headers=self._get_headers())
                        if charts_response.status_code == 200:
                            for chart in charts_response.json().get("result", []):
                                old_chart_ids_set.add(chart["id"])
                except Exception:
                    pass

                # Remove new chart_ids from deletion set (keep them!)
                charts_to_delete = old_chart_ids_set - set(chart_ids)
                if charts_to_delete:
                    print(f"  Deleting {len(charts_to_delete)} old charts...")
                    for cid in charts_to_delete:
                        try:
                            del_url = f"{self.superset_url}{API_CHART_ENDPOINT}{cid}"
                            self.session.delete(del_url, headers=self._get_headers())
                        except Exception:
                            pass
                    print(f"  ✓ Deleted old charts")

                # Update dashboard with new position_json
                position_json = self._build_position_json(chart_ids, charts_per_row=charts_per_row)
                update_config = {
                    "position_json": json.dumps(position_json)
                }
                update_response = self.session.put(detail_url, headers=self._get_headers(), json=update_config)

                if update_response.status_code not in [200, 201]:
                    print(f"✗ Failed to update dashboard: {update_response.status_code}")
                    return None

                # Associate new charts with dashboard (chart-side relationship)
                for cid in chart_ids:
                    self._associate_chart_with_dashboard(cid, existing_dashboard_id)

                print(f"✓ Updated dashboard with {len(chart_ids)} charts")
                return existing_dashboard_id
            except Exception as e:
                print(f"✗ Failed to update dashboard: {e}")
                return None
        else:
            # Create new
            dashboard_config = {
                "dashboard_title": title,
                "slug": None,
                "published": True,
                "position_json": json.dumps({}),
            }

            try:
                response = self.session.post(url, headers=self._get_headers(), json=dashboard_config)
                response.raise_for_status()
                dashboard_id = response.json().get("id")
                print(f"✓ Created dashboard: {title} (ID: {dashboard_id})")

                if chart_ids:
                    update_url = f"{self.superset_url}/api/v1/dashboard/{dashboard_id}"
                    # Build position_json with chart layout
                    position_json = self._build_position_json(chart_ids, charts_per_row=charts_per_row)
                    update_config = {
                        "position_json": json.dumps(position_json)
                    }
                    update_response = self.session.put(update_url, headers=self._get_headers(), json=update_config)

                    # Associate charts from the chart side
                    for chart_id in chart_ids:
                        self._associate_chart_with_dashboard(chart_id, dashboard_id)

                    if update_response.status_code not in [200, 201]:
                        print(f"✗ Failed to add charts: {update_response.status_code}")
                        try:
                            print(f"  Error: {update_response.json()}")
                        except Exception:
                            print(f"  Error: {update_response.text[:500]}")
                        # Don't fail - dashboard is created, just without charts
                        print(f"  Dashboard created but charts not added. You can add them manually.")
                    else:
                        print(f"✓ Added {len(chart_ids)} charts to dashboard")

                return dashboard_id
            except Exception as e:
                print(f"✗ Failed to create dashboard: {e}")
                try:
                    if hasattr(e, 'response') and e.response:
                        print(f"  Error details: {e.response.text[:500]}")
                except Exception:
                    # Suppress secondary errors when printing error details
                    pass
                return None

    def _build_position_json(self, chart_ids: list, charts_per_row: int = None) -> Dict[str, Any]:
        """Build position_json structure for dashboard layout.

        Args:
            chart_ids: List of Superset chart IDs to include.
            charts_per_row: Number of charts per row. When None, falls back
                to the module-level CHARTS_PER_ROW constant.
        """
        import uuid

        effective_charts_per_row = charts_per_row if charts_per_row is not None else CHARTS_PER_ROW
        # Superset uses a 12-unit grid; distribute width evenly across columns
        chart_width = max(1, 12 // effective_charts_per_row)

        position = {}

        # Dashboard metadata
        position["DASHBOARD_VERSION_KEY"] = "v2"

        # Add header
        position["HEADER_ID"] = {
            "type": "HEADER",
            "id": "HEADER_ID",
            "meta": {
                "text": DASHBOARD_HEADER_TEXT
            }
        }

        # Create ROWs with charts
        row_ids = []
        chart_keys = []

        # First create all chart entries
        for chart_id in chart_ids:
            chart_key = f"CHART-{uuid.uuid4().hex[:8]}"
            chart_keys.append(chart_key)

            position[chart_key] = {
                "type": "CHART",
                "id": chart_key,
                "children": [],
                "meta": {
                    "chartId": chart_id,
                    "width": chart_width,
                    "height": DEFAULT_CHART_HEIGHT,
                    "uuid": str(uuid.uuid4())
                }
            }

        # Now create ROW entries (configurable charts per row)
        for i in range(0, len(chart_keys), effective_charts_per_row):
            row_id = f"ROW-{uuid.uuid4().hex[:8]}"
            row_ids.append(row_id)

            # Get charts for this row (1 or more charts up to effective_charts_per_row)
            row_charts = chart_keys[i:i+effective_charts_per_row]

            position[row_id] = {
                "type": "ROW",
                "id": row_id,
                "children": row_charts,
                "meta": {
                    "background": DASHBOARD_BACKGROUND
                }
            }

        # Add GRID container with ROWs
        position["GRID_ID"] = {
            "type": "GRID",
            "id": "GRID_ID",
            "children": row_ids
        }

        # Add root container with GRID as child
        position["ROOT_ID"] = {
            "type": "ROOT",
            "id": "ROOT_ID",
            "children": ["GRID_ID"]
        }

        return position

    def _load_style_config(self, style_path: str = None) -> Dict[str, Any]:
        """Load style configuration from .dmls file"""
        if not style_path:
            return {"colors": self._get_default_colors()}

        try:
            theme_path = Path(style_path)
            if not theme_path.exists():
                self.warn(f"Style file not found: {style_path}, using defaults")
                return {"colors": self._get_default_colors()}

            with open(theme_path, 'r') as f:
                config = yaml.safe_load(f)
                return config if config else {"colors": self._get_default_colors()}

        except Exception as e:
            self.warn(f"Failed to load style: {e}")
            return {"colors": self._get_default_colors()}

    def _get_default_colors(self) -> Dict[str, str]:
        """Get default color scheme"""
        return DEFAULT_COLORS

    def get_run_command(self, output_path: str) -> str:
        """No run command needed - dashboard is already created"""
        return "Dashboard already created in Superset!"
