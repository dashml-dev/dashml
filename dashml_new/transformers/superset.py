"""
Superset Transformer - Directly creates Superset dashboards via REST API
"""
from typing import TYPE_CHECKING, Dict, Any, Optional
from pathlib import Path
import yaml
import json
import time
from .base import Transformer, TransformerError

if TYPE_CHECKING:
    from ..core.types import DashMLSpec, ChartSpec

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
        self.superset_url = superset_url or "http://localhost:8088"
        self.username = username
        self.password = password
        self.access_token = None
        self.csrf_token = None
        self.dataset_id = None
        self.session = None  # Will hold requests.Session for cookie management

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
            raise TransformerError(
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
                raise TransformerError("Authentication failed")

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

            # Create or get dataset
            if not self._create_or_get_dataset(data_path):
                raise TransformerError("Failed to create/find dataset")

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

            if pages:
                for page in pages:
                    page_id = page["id"]
                    print(f"\nProcessing page: {page.get('title', page_id)}")
                    for chart in page.get("charts", []):
                        chart_id = self._create_or_update_chart(
                            f"{page_id}_{chart['id']}",
                            chart,
                            style_config,
                            existing_chart_map
                        )
                        if chart_id:
                            chart_ids.append(chart_id)
            else:
                for chart in charts:
                    chart_id = self._create_or_update_chart(chart["id"], chart, style_config, existing_chart_map)
                    if chart_id:
                        chart_ids.append(chart_id)

            if not chart_ids:
                raise TransformerError("No charts were created successfully")

            # Create or update dashboard
            print("\nCreating/updating dashboard...")
            dashboard_id = self._create_or_update_dashboard(title, chart_ids)

            if not dashboard_id:
                raise TransformerError("Failed to create dashboard")

            dashboard_url = f"{self.superset_url}/superset/dashboard/{dashboard_id}/"
            success_msg = f"\n🎉 Dashboard created successfully!\n\nURL: {dashboard_url}\n"
            print(success_msg)

            return success_msg

        except TransformerError:
            raise
        except Exception as e:
            raise TransformerError(f"Failed to create Superset dashboard: {e}")

    def _authenticate(self) -> bool:
        """Authenticate with Superset and get tokens"""
        login_url = f"{self.superset_url}/api/v1/security/login"
        payload = {
            "username": self.username,
            "password": self.password,
            "provider": "db",
            "refresh": True
        }

        try:
            response = self.session.post(login_url, json=payload)
            response.raise_for_status()
            data = response.json()
            self.access_token = data.get("access_token")

            # Get CSRF token - session will keep the cookie
            csrf_url = f"{self.superset_url}/api/v1/security/csrf_token/"
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
            "Content-Type": "application/json"
        }

    def _create_or_get_dataset(self, csv_path: str) -> bool:
        """Create dataset from CSV or get existing one"""
        dataset_name = Path(csv_path).stem
        search_url = f"{self.superset_url}/api/v1/dataset/"

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
            db_url = f"{self.superset_url}/api/v1/database/"
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
                files = {'file': (Path(csv_path).name, f, 'text/csv')}
                data = {
                    'type': 'csv',  # Required field
                    'table_name': dataset_name,
                    'delimiter': ',',
                    'already_exists': 'replace',
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
                        files = {'file': (Path(csv_path).name, f2, 'text/csv')}
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
                    csrf_url = f"{self.superset_url}/api/v1/security/csrf_token/"
                    csrf_headers = {"Authorization": f"Bearer {self.access_token}"}
                    csrf_response = self.session.get(csrf_url, headers=csrf_headers)
                    if csrf_response.status_code == 200:
                        self.csrf_token = csrf_response.json().get("result")

                    dataset_payload = {
                        "database": database_id,
                        "table_name": dataset_name
                        # Don't specify schema - let it use default
                    }

                    # Add referer header - sometimes required by Superset
                    dataset_headers = self._get_headers()
                    dataset_headers["Referer"] = self.superset_url

                    create_dataset_url = f"{self.superset_url}/api/v1/dataset/"
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
                    time.sleep(5)  # Wait longer for dataset creation

                    # Try to find the dataset multiple times
                    for attempt in range(3):
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

                        if attempt < 2:
                            print(f"  Attempt {attempt + 1}/3: Dataset not found yet, waiting...")
                            time.sleep(3)

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

    def _find_existing_dashboard(self, title: str) -> Optional[int]:
        """Find existing dashboard by title"""
        url = f"{self.superset_url}/api/v1/dashboard/"
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

    def _create_or_update_chart(self, chart_id: str, chart: Dict[str, Any], style_config: Dict[str, Any] = None, existing_chart_map: Dict[str, int] = None) -> Optional[int]:
        """Create or update a chart in Superset"""
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

        # Apply custom color scheme from DashML theme
        if "secondary" in colors and isinstance(colors["secondary"], list):
            # Use custom categorical color scheme
            custom_colors = colors["secondary"]
            # Superset doesn't have a way to define fully custom schemes via API,
            # but we can use the closest built-in or set label colors
            params["color_scheme"] = "lyftColors"  # A colorful scheme
            # Note: Full custom color application would require creating a custom theme in Superset UI
        else:
            params["color_scheme"] = "supersetColors"

        # Add metrics only for chart types that use them
        if chart_type in ["bar", "line", "stacked_bar", "grouped_bar"]:
            # ECharts timeseries configuration
            params["x_axis"] = x
            params["metrics"] = [{"label": y, "expressionType": "SIMPLE", "column": {"column_name": y}, "aggregate": agg.upper()}]

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
            params["bins"] = 25  # Number of bins
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
                    "row_limit": 10000
                }
            else:
                # Scatter uses columns, not metrics
                columns = [x, y]
                query_obj = {
                    "columns": columns,
                    "filters": [],
                    "row_limit": 10000
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
                "row_limit": 10000
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

        try:
            if existing_chart_id:
                # Update existing chart
                url = f"{self.superset_url}/api/v1/chart/{existing_chart_id}"
                response = self.session.put(url, headers=self._get_headers(), json=chart_config)
                response.raise_for_status()
                print(f"✓ Updated chart: {title} (ID: {existing_chart_id})")
                return existing_chart_id
            else:
                # Create new chart
                url = f"{self.superset_url}/api/v1/chart/"
                response = self.session.post(url, headers=self._get_headers(), json=chart_config)
                response.raise_for_status()
                created_chart_id = response.json().get("id")
                print(f"✓ Created chart: {title} (ID: {created_chart_id})")
                return created_chart_id
        except Exception as e:
            action = "update" if existing_chart_id else "create"
            print(f"✗ Failed to {action} chart {title}: {e}")
            return None

    def _create_or_update_dashboard(self, title: str, chart_ids: list) -> Optional[int]:
        """Create dashboard or update existing one"""
        url = f"{self.superset_url}/api/v1/dashboard/"

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
                    dashboard_result = detail_response.json().get("result", {})
                    # Extract chart IDs from position_json (CHART-123 format)
                    position_json_str = dashboard_result.get("position_json", "{}")
                    position_json_data = json.loads(position_json_str)
                    old_chart_ids = []
                    for key, value in position_json_data.items():
                        if key.startswith("CHART-"):
                            # Get the actual chart ID from the meta.chartId field
                            if isinstance(value, dict) and "meta" in value:
                                chart_id = value["meta"].get("chartId")
                                if chart_id:
                                    old_chart_ids.append(chart_id)
                    print(f"  DEBUG: Extracted {len(old_chart_ids)} chart IDs from position_json: {old_chart_ids[:6]}")

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
                        removed_count = 0
                        for chart_id in charts_to_remove:
                            try:
                                delete_url = f"{self.superset_url}/api/v1/chart/{chart_id}"
                                delete_response = self.session.delete(delete_url, headers=self._get_headers())
                                if delete_response.status_code in [200, 204]:
                                    removed_count += 1
                            except Exception:
                                pass  # Continue even if one deletion fails
                        if removed_count > 0:
                            print(f"  ✓ Removed {removed_count} old/duplicate charts")

                # Now associate only the current charts with the dashboard
                for chart_id in chart_ids:
                    chart_url = f"{self.superset_url}/api/v1/chart/{chart_id}"
                    # Get current dashboards for this chart
                    chart_response = self.session.get(chart_url, headers=self._get_headers())
                    if chart_response.status_code == 200:
                        chart_data = chart_response.json().get("result", {})
                        dashboards = chart_data.get("dashboards", [])
                        # Add this dashboard if not already there
                        if existing_dashboard_id not in dashboards:
                            dashboards.append(existing_dashboard_id)
                            self.session.put(chart_url, headers=self._get_headers(), json={"dashboards": dashboards})

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
                        chart_url = f"{self.superset_url}/api/v1/chart/{chart_id}"
                        chart_update = {
                            "dashboards": [dashboard_id]
                        }
                        self.session.put(chart_url, headers=self._get_headers(), json=chart_update)

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
                "text": "Dashboard"
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
                    "width": 6,  # Half width (2 columns)
                    "height": 50,
                    "uuid": str(uuid.uuid4())
                }
            }

        # Now create ROW entries (2 charts per row)
        for i in range(0, len(chart_keys), 2):
            row_id = f"ROW-{uuid.uuid4().hex[:8]}"
            row_ids.append(row_id)

            # Get charts for this row (1 or 2 charts)
            row_charts = chart_keys[i:i+2]

            position[row_id] = {
                "type": "ROW",
                "id": row_id,
                "children": row_charts,
                "meta": {
                    "background": "BACKGROUND_TRANSPARENT"
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
        return {
            "primary": "#20A7C9",
            "secondary": ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'],
            "background": "#FAFAFA",
            "text": "#11181C",
            "card": "#FFFFFF"
        }

    def get_run_command(self, output_path: str) -> str:
        """No run command needed - dashboard is already created"""
        return "Dashboard already created in Superset!"
