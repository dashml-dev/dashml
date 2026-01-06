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
    from ..core.types import DashMLSpec, ChartSpec

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
DEFAULT_HISTOGRAM_BINS = 25
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

# Chart type categorization by data requirements
CHARTS_NEED_AGGREGATION = {"bar", "line", "area", "pie", "stacked_bar", "grouped_bar"}
CHARTS_USE_RAW_DATA = {"histogram", "scatter"}

# Map DashML chart types to Superset viz types
# Modern Superset uses ECharts-based visualizations
DASHML_TO_SUPERSET_VIZ = {
    "bar": "echarts_timeseries",  # ECharts timeseries with bar transform
    "line": "echarts_timeseries",  # ECharts timeseries with line
    "scatter": "scatter",
    "pie": "pie",
    "area": "echarts_area",
    "histogram": "histogram_v2",  # Modern histogram viz type
    "stacked_bar": "echarts_timeseries",  # ECharts timeseries with stacking
    "grouped_bar": "echarts_timeseries",  # ECharts timeseries with grouping
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
        self.db_config = None  # Database credentials for auto-creating databases

    def set_db_config(self, config: Dict[str, Any]) -> None:
        """Store database configuration for auto-creating databases in Superset"""
        self.db_config = config

    @property
    def name(self) -> str:
        return "superset"

    @property
    def description(self) -> str:
        return "Creates dashboards directly in Apache Superset via REST API"

    def build(self, spec: "DashMLSpec") -> str:
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

            # Load style config (resolve path relative to .dashml file)
            style_path = spec.get("style")
            if style_path:
                source_file = spec.get("_source_file")
                if source_file:
                    dashml_dir = Path(source_file).parent
                    style_path = str(dashml_dir / style_path)
            style_config = self._load_style_config(style_path)

            # Extract spec components
            title = spec.get("title", "DashML Dashboard")
            data_spec = spec["data"]
            data_type = data_spec.get("type", "csv")

            # Create or get dataset based on data type
            if data_type == "csv":
                # CSV datasource - resolve path and upload
                data_path = data_spec["path"]

                # Get the absolute path to the CSV file
                # spec.get("_source_file") contains the path to the .dashml file
                source_file = spec.get("_source_file")
                if source_file:
                    # Resolve data_path relative to the .dashml file location
                    dashml_dir = Path(source_file).parent
                    data_path = str(dashml_dir / data_path)

                # Convert to absolute path
                data_path = str(Path(data_path).resolve())

                # Create or get dataset from CSV
                if not self._create_or_get_dataset_csv(data_path):
                    raise SupersetDatasetError("Failed to create/find CSV dataset")

            elif data_type == "sql":
                # SQL datasource - reference existing table
                # Support both new format (path) and legacy format (schema + table_name)
                if "path" in data_spec:
                    # New format: parse path into schema.table
                    schema, table_name = self._parse_sql_path(data_spec["path"])
                else:
                    # Legacy format: use explicit schema and table_name fields
                    schema = data_spec["schema"]
                    table_name = data_spec["table_name"]

                # Determine database_id: either auto-create from db_config or use from spec
                if self.db_config:
                    # Auto-create/find database using CLI credentials
                    database_id = self._create_or_get_database()
                    if not database_id:
                        raise SupersetDatasetError("Failed to create/find database in Superset")
                elif "database_id" in data_spec:
                    # Use pre-configured database_id from spec
                    database_id = data_spec["database_id"]
                else:
                    raise SupersetDatasetError(
                        "SQL datasource requires either:\n"
                        "  1. database_id in spec (for pre-configured databases), OR\n"
                        "  2. --db-* CLI arguments to auto-create database"
                    )

                # Create or get dataset from SQL table
                if not self._create_or_get_dataset_sql(database_id, schema, table_name):
                    raise SupersetDatasetError("Failed to create/find SQL dataset")

            else:
                raise SupersetDatasetError(f"Unsupported data type: {data_type}")

            # Get charts or pages
            charts = spec.get("charts", [])
            pages = spec.get("pages", [])

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

            if pages:
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
            else:
                for chart in charts:
                    chart_id, label_colors = self._create_or_update_chart(chart["id"], chart, style_config, existing_chart_map)
                    if chart_id:
                        chart_ids.append(chart_id)
                        if label_colors:
                            all_label_colors.update(label_colors)

            if not chart_ids:
                raise SupersetChartError("No charts were created successfully")

            # Create or update dashboard
            print("\nCreating/updating dashboard...")
            dashboard_id = self._create_or_update_dashboard(title, chart_ids)

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
        except Exception:
            pass
        return False

    def _build_api_url(self, endpoint: str, resource_id: str = None) -> str:
        """Build a complete API URL with optional resource ID"""
        if resource_id:
            return f"{self.superset_url}{endpoint}{resource_id}"
        return f"{self.superset_url}{endpoint}"

    def _parse_sql_path(self, path: str) -> tuple:
        """
        Parse SQL path into (schema, table_name) tuple.

        Supports formats:
        - "schema.table" -> ("schema", "table")
        - "[schema].[table]" -> ("schema", "table")
        - "[My Schema].[My Table]" -> ("My Schema", "My Table")
        """
        import re

        # Pattern: [optional brackets]identifier[optional brackets].identifier
        pattern = r'^\[?([^\]\.]+)\]?\.?\[?([^\]]+)\]?$'
        match = re.match(pattern, path)

        if match:
            schema = match.group(1)
            table = match.group(2)
            return (schema.strip(), table.strip())

        raise SupersetDatasetError(f"Invalid SQL path format: {path}")

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
        except Exception:
            pass
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
                    except:
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
                        except:
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
        if not self.db_config:
            return None

        db_type = self.db_config["type"]
        host = self.db_config["host"]
        port = self.db_config["port"]
        database = self.db_config["database"]
        user = self.db_config["user"]
        password = self.db_config["password"]

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
                except:
                    print(f"  Error: {db_response.text[:500]}")
                return None

        except Exception as e:
            print(f"✗ Error creating database: {e}")
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
        except Exception:
            pass
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
        except Exception:
            pass
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
        x = chart["x"]
        y = chart.get("y", "")
        agg = chart.get("agg", "sum")
        group = chart.get("group")
        x_type = chart.get("x_type")  # Optional: "date", "number", "string" for sorting

        viz_type = DASHML_TO_SUPERSET_VIZ.get(chart_type, "dist_bar")

        # Get colors from style config
        if not style_config:
            style_config = {"colors": self._get_default_colors()}
        colors = style_config.get("colors", {})

        # Build params with custom colors from theme
        params = {
            "datasource": f"{self.dataset_id}__table",
            "viz_type": viz_type,
            "adhoc_filters": [],
        }

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
                except Exception:
                    # If we can't get unique values, just use the base color scheme
                    pass

        # Add metrics only for chart types that use them
        if chart_type in ["bar", "line", "stacked_bar", "grouped_bar"]:
            # ECharts timeseries configuration
            params["x_axis"] = x
            params["metrics"] = [{"label": y, "expressionType": "SIMPLE", "column": {"column_name": y}, "aggregate": agg.upper()}]

            # Configure temporal axis if x_type is date
            if x_type == "date":
                params["x_axis_sort_asc"] = True  # Sort ascending for chronological order
                params["x_axis_time_format"] = "%Y-%m-%d"  # ISO date format

            # Set series type based on chart type
            if chart_type == "bar":
                params["seriesType"] = "bar"
            elif chart_type == "line":
                params["seriesType"] = "line"
            elif chart_type in ["stacked_bar", "grouped_bar"]:
                params["seriesType"] = "bar"
                params["groupby"] = [group] if group else []
                # For stacked bar, enable stacking
                if chart_type == "stacked_bar":
                    params["stack"] = True
                    params["show_value"] = False
        elif chart_type == "area":
            # ECharts area uses x_axis and metrics
            params["x_axis"] = x
            params["metrics"] = [{"label": y, "expressionType": "SIMPLE", "column": {"column_name": y}, "aggregate": agg.upper()}]
            # Configure temporal axis if x_type is date
            if x_type == "date":
                params["x_axis_sort_asc"] = True
                params["x_axis_time_format"] = "%Y-%m-%d"
        elif chart_type == "pie":
            params["metrics"] = [{"label": y, "expressionType": "SIMPLE", "column": {"column_name": y}, "aggregate": agg.upper()}]
            params["groupby"] = [x]
            params["metric"] = y
        elif chart_type == "scatter":
            # Scatter uses raw data columns, not aggregated metrics
            params["entity"] = x
            params["all_columns_x"] = [x]
            params["all_columns_y"] = [y]
            # No metrics for scatter - uses raw data!
        elif chart_type == "histogram":
            # Histogram v2 uses different params than legacy histogram
            params["column"] = x  # The column to create histogram from
            params["groupby"] = []  # Optional grouping columns
            params["bins"] = DEFAULT_HISTOGRAM_BINS  # Number of bins
            params["normalized"] = False  # Whether to normalize
            params["cumulative"] = False  # Whether to show cumulative distribution
            # No metrics for histogram!

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
                    "row_limit": RAW_DATA_ROW_LIMIT
                }
            else:
                # Scatter uses columns, not metrics
                columns = [x, y]
                query_obj = {
                    "columns": columns,
                    "filters": [],
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
            else:
                columns = [x]

            query_context_queries.append({
                "columns": columns,
                "metrics": [{"label": y, "expressionType": "SIMPLE",
                            "column": {"column_name": y}, "aggregate": agg.upper()}],
                "filters": [],
                "row_limit": RAW_DATA_ROW_LIMIT
            })

        chart_config = {
            "slice_name": title,
            "viz_type": viz_type,
            "datasource_id": self.dataset_id,
            "datasource_type": "table",
            "params": json.dumps(params),
            "query_context": json.dumps({
                "datasource": {"id": self.dataset_id, "type": "table"},
                "force": False,
                "queries": query_context_queries,
                "result_format": "json",
                "result_type": "full"
            })
        }

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

    def _create_or_update_dashboard(self, title: str, chart_ids: list) -> Optional[int]:
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
            # Update existing
            try:
                detail_url = f"{self.superset_url}/api/v1/dashboard/{existing_dashboard_id}"
                detail_response = self.session.get(detail_url, headers=self._get_headers())
                old_chart_ids = []
                if detail_response.status_code == 200:
                    # Query the chart API to find ALL charts associated with this dashboard
                    # This is more reliable than parsing position_json which may not include all charts
                    try:
                        # Use RISON filter to find charts where dashboard ID matches
                        # Fetch with large page size to get all charts at once
                        filter_params = {"filters": [{"col": "dashboards", "opr": "rel_m_m", "value": existing_dashboard_id}], "page_size": CHART_LIST_PAGE_SIZE}
                        filter_rison = prison.dumps(filter_params) if prison else None

                        if filter_rison:
                            charts_url = f"{self.superset_url}{API_CHART_ENDPOINT}?q={filter_rison}"
                        else:
                            # Fallback without page_size if prison not available
                            charts_url = f"{self.superset_url}{API_CHART_ENDPOINT}"

                        charts_response = self.session.get(charts_url, headers=self._get_headers())

                        if charts_response.status_code == 200:
                            charts_data = charts_response.json()
                            old_chart_ids = [chart["id"] for chart in charts_data.get("result", [])]
                            print(f"  Found {len(old_chart_ids)} existing charts associated with dashboard")
                    except Exception as e:
                        print(f"  Warning: Could not fetch associated charts: {e}")
                        # Fallback to position_json parsing
                        dashboard_result = detail_response.json().get("result", {})
                        position_json_str = dashboard_result.get("position_json", "{}")
                        position_json_data = json.loads(position_json_str)
                        for key, value in position_json_data.items():
                            if key.startswith("CHART-"):
                                if isinstance(value, dict) and "meta" in value:
                                    chart_id = value["meta"].get("chartId")
                                    if chart_id:
                                        old_chart_ids.append(chart_id)

                # Build position_json with NEW chart layout
                position_json = self._build_position_json(chart_ids)

                # Update dashboard with just position_json
                # Charts will be extracted from position_json automatically by Superset
                update_config = {
                    "position_json": json.dumps(position_json)
                }
                update_response = self.session.put(detail_url, headers=self._get_headers(), json=update_config)

                if update_response.status_code not in [200, 201]:
                    print(f"✗ Failed to update dashboard: {update_response.status_code}")
                    try:
                        print(f"  Error: {update_response.json()}")
                    except:
                        print(f"  Error: {update_response.text[:500]}")
                    return None

                # Delete old chart references that are NOT in the new chart_ids list
                # This removes duplicates and charts that are no longer needed
                if old_chart_ids:
                    charts_to_remove = [cid for cid in old_chart_ids if cid not in chart_ids]
                    if charts_to_remove:
                        print(f"  Removing {len(charts_to_remove)} old/duplicate charts...")
                        try:
                            # Use bulk delete with RISON encoding
                            if prison:
                                # Use prison library for RISON encoding
                                rison_encoded = prison.dumps(charts_to_remove)
                            else:
                                # Manual RISON encoding: [1,2,3] -> !(1,2,3)
                                rison_encoded = f"!({','.join(map(str, charts_to_remove))})"

                            delete_url = f"{self.superset_url}{API_CHART_ENDPOINT}?q={rison_encoded}"
                            delete_response = self.session.delete(delete_url, headers=self._get_headers())

                            if delete_response.status_code == 200:
                                print(f"  ✓ Removed {len(charts_to_remove)} old/duplicate charts")
                            else:
                                print(f"  ✗ Bulk delete failed ({delete_response.status_code}), trying individual deletes...")
                                # Fallback to individual deletes
                                removed_count = 0
                                for chart_id in charts_to_remove:
                                    try:
                                        single_delete_url = f"{self.superset_url}{API_CHART_ENDPOINT}{chart_id}"
                                        single_response = self.session.delete(single_delete_url, headers=self._get_headers())
                                        if single_response.status_code in [200, 204]:
                                            removed_count += 1
                                    except Exception:
                                        pass
                                if removed_count > 0:
                                    print(f"  ✓ Removed {removed_count} old/duplicate charts")
                        except Exception as e:
                            print(f"  ✗ Failed to delete old charts: {e}")

                # Now associate only the current charts with the dashboard
                for chart_id in chart_ids:
                    self._associate_chart_with_dashboard(chart_id, existing_dashboard_id)

                print(f"✓ Updated dashboard with {len(chart_ids)} charts")
                return existing_dashboard_id
            except Exception as e:
                print(f"✗ Failed to update dashboard: {e}")
                try:
                    if hasattr(e, 'response') and e.response:
                        print(f"  Error details: {e.response.text[:500]}")
                except:
                    pass
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
                    position_json = self._build_position_json(chart_ids)
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
                        except:
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
                except:
                    pass
                return None

    def _build_position_json(self, chart_ids: list) -> Dict[str, Any]:
        """Build position_json structure for dashboard layout"""
        import uuid

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

        # Create ROWs with charts (2 charts per row)
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
                    "width": DEFAULT_CHART_WIDTH,  # Half width (2 columns)
                    "height": DEFAULT_CHART_HEIGHT,
                    "uuid": str(uuid.uuid4())
                }
            }

        # Now create ROW entries (configurable charts per row)
        for i in range(0, len(chart_keys), CHARTS_PER_ROW):
            row_id = f"ROW-{uuid.uuid4().hex[:8]}"
            row_ids.append(row_id)

            # Get charts for this row (1 or more charts up to CHARTS_PER_ROW)
            row_charts = chart_keys[i:i+CHARTS_PER_ROW]

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
