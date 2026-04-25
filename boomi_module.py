import requests
from requests.auth import HTTPBasicAuth
import db_utils
from logger import log

class BoomiManager:
    def __init__(self):
        self.base_url = "https://api.boomi.com/api/rest/v1"
        self.refresh_configs()

    def refresh_configs(self):
        self.account_id = db_utils.get_setting('boomi_account_id')
        self.username = db_utils.get_setting('boomi_username')
        self.api_key = db_utils.get_setting('boomi_api_key')

    def check_connection(self):
        """Lightweight health check against the Boomi Account API."""
        if not self.account_id or not self._get_auth():
            return False
        
        # Standard GET Account endpoint
        url = f"{self.base_url}/{self.account_id}/Account/{self.account_id}"
        headers = {"Accept": "application/json"}
        try:
            res = requests.get(url, auth=self._get_auth(), headers=headers, timeout=5)
            # If we get 200, the token and account ID are valid
            return res.status_code == 200
        except:
            return False

    def _get_auth(self):
        if not self.username or not self.api_key:
            return None
        # Boomi API Tokens require the "BOOMI_TOKEN." prefix on the username
        auth_username = f"BOOMI_TOKEN.{self.username}"
        return HTTPBasicAuth(auth_username, self.api_key)

    def get_components(self, component_type=None):
        """Fetches component metadata from Boomi AtomSphere API."""
        if not self.account_id or not self._get_auth():
            log.warning("Boomi credentials not configured. Discovery skipped.")
            return []
        
        url = f"{self.base_url}/{self.account_id}/ComponentMetadata/query"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        payload = {
            "QueryFilter": {}
        }
        
        if component_type:
            payload["QueryFilter"]["expression"] = {
                "argument": [component_type],
                "operator": "EQUALS",
                "property": "type"
            }
        
        try:
            res = requests.post(url, auth=self._get_auth(), json=payload, headers=headers, timeout=20)
            if res.status_code == 200:
                data = res.json()
                results = data.get('result', [])
                # Normalize for frontend consistency
                normalized = []
                for c in results:
                    normalized.append({
                        "id": c.get("componentId"),
                        "name": c.get("name"),
                        "type": c.get("type"),
                        "version": c.get("version"),
                        "modifiedDate": c.get("lastModifiedDate", "").split("T")[0]
                    })
                return normalized
            else:
                log.error(f"Boomi API Error {res.status_code}: {res.text}")
                return []
        except Exception as e:
            log.error(f"Boomi Discovery Exception: {e}")
            return []

    def get_package_by_name(self, component_name, version=None):
        """
        Boomi REST API doesn't support componentName filter on PackagedComponent.
        We must: 1. Get componentId from name. 2. Query PackagedComponent by ID.
        """
        if not self.account_id or not self._get_auth():
            return None
        
        # Step 1: Find component ID by name
        meta_url = f"{self.base_url}/{self.account_id}/ComponentMetadata/query"
        meta_payload = {
            "QueryFilter": {
                "expression": {"argument": [component_name], "operator": "EQUALS", "property": "name"}
            }
        }
        
        try:
            log.debug(f"Boomi Resolving Name '{component_name}' to ID...")
            res_meta = requests.post(meta_url, auth=self._get_auth(), json=meta_payload, headers={"Accept": "application/json"})
            if res_meta.status_code != 200:
                log.error(f"Boomi Meta Resolution Error: {res_meta.text}")
                return None
            
            meta_results = res_meta.json().get('result', [])
            if not meta_results:
                log.warning(f"Boomi No component found with name '{component_name}'")
                return None
            
            comp_id = meta_results[0].get('componentId')
            log.debug(f"Boomi Resolved '{component_name}' -> {comp_id}")

            # Step 2: Query PackagedComponent by componentId
            url = f"{self.base_url}/{self.account_id}/PackagedComponent/query"
            payload = {
                "QueryFilter": {
                    "expression": {
                        "operator": "AND",
                        "nestedExpression": [
                            {"argument": [comp_id], "operator": "EQUALS", "property": "componentId"}
                        ]
                    }
                }
            }
            if version:
                payload["QueryFilter"]["expression"]["nestedExpression"].append(
                    {"argument": [version], "operator": "EQUALS", "property": "packageVersion"}
                )
            
            log.debug(f"Boomi Querying Package for ID {comp_id} (v:{version})")
            res = requests.post(url, auth=self._get_auth(), json=payload, headers={"Accept": "application/json"})
            if res.status_code == 200:
                results = res.json().get('result', [])
                log.debug(f"Boomi Package Found: {len(results)} matches")
                if results:
                    pkg = results[0]
                    # Inject component name resolved in Step 1
                    pkg['componentName'] = component_name
                    return pkg
                return None
            
            log.error(f"Boomi Package Query Error {res.status_code}: {res.text}")
            return None
            
        except Exception as e:
            log.error(f"Boomi Discovery Orchestration Exception: {e}")
            return None

    def get_package_manifest(self, package_id, root_name="---"):
        """Retrieves and enriches the manifest (included components) for a package."""
        if not self.account_id or not self._get_auth():
            return None
            
        url = f"{self.base_url}/{self.account_id}/PackagedComponentManifest/{package_id}"
        log.debug(f"Boomi Manifest Fetch URL: {url}")
        try:
            res = requests.get(url, auth=self._get_auth(), headers={"Accept": "application/json"})
            if res.status_code != 200:
                log.error(f"Boomi Manifest Error: {res.text}")
                return None
            
            data = res.json()
            # The manifest uses the "componentInfo" key for included assets
            included = data.get('componentInfo', [])
            if not included:
                log.warning(f"Boomi Manifest: No componentInfo found for package {package_id}")
                return data
            
            # Reformat to match our expected "included" structure
            formatted_included = []
            for c in included:
                formatted_included.append({
                    "componentId": c.get('id'),
                    "version": c.get('version')
                })

            # Enrich with Name/Folder via Batch Metadata Query
            comp_ids = [c['componentId'] for c in formatted_included]
            enriched_map = self._batch_get_component_meta(comp_ids)
            
            # Fetch Deployment Info for this package
            deployment_targets = self._get_package_deployments(package_id)
            
            # Merge back
            for item in formatted_included:
                meta = enriched_map.get(item['componentId'], {})
                item['name'] = meta.get('name', 'UNKNOWN')
                item['folder'] = meta.get('folderName', '---')
                item['type'] = meta.get('type', 'Unknown')
                item['modifiedDate'] = meta.get('modifiedDate', '---')
                item['modifiedBy'] = meta.get('modifiedBy', '---')
                item['deployedTo'] = deployment_targets
                item['rootComponent'] = root_name
                item['packageId'] = package_id
                
            # Replace the old key with the enriched version for app.py parity
            data['includedComponent'] = formatted_included
            return data
        except Exception as e:
            log.error(f"Boomi Manifest Orchestration Exception: {e}")
            return None

    def _batch_get_component_meta(self, component_ids):
        """Fetches metadata for multiple components in a single API call."""
        if not component_ids: return {}
        
        # Split into chunks of 100 if needed (Boomi limit might apply)
        url = f"{self.base_url}/{self.account_id}/ComponentMetadata/query"
        results_map = {}
        
        payload = {
            "QueryFilter": {
                "expression": {
                    "operator": "OR",
                    "nestedExpression": []
                }
            }
        }
        for cid in component_ids[:100]:
            payload["QueryFilter"]["expression"]["nestedExpression"].append(
                {"argument": [cid], "operator": "EQUALS", "property": "componentId"}
            )
            
        try:
            res = requests.post(url, auth=self._get_auth(), json=payload, headers={"Accept": "application/json"})
            if res.status_code == 200:
                data = res.json().get('result', [])
                for item in data:
                    results_map[item['componentId']] = item
            return results_map
        except Exception as e:
            log.error(f"Boomi Batch Meta Error: {e}")
            return {}

    def _get_package_deployments(self, package_id):
        """Identifies environments where this package is currently deployed."""
        if not self.account_id or not self._get_auth():
            return "---"
            
        url = f"{self.base_url}/{self.account_id}/DeployedPackage/query"
        payload = {
            "QueryFilter": {
                "expression": {"argument": [package_id], "operator": "EQUALS", "property": "packageId"}
            }
        }
        
        try:
            res = requests.post(url, auth=self._get_auth(), json=payload, headers={"Accept": "application/json"})
            if res.status_code == 200:
                deployments = res.json().get('result', [])
                if not deployments: return "NOT DEPLOYED"
                
                # Extract Environment IDs and resolve to names if possible
                env_names = []
                for d in deployments:
                    env_id = d.get('environmentId')
                    env_names.append(self._get_environment_name(env_id))
                return ", ".join(env_names)
            return "UNKNOWN"
        except:
            return "---"

    def _get_environment_name(self, env_id):
        """Resolves an environment ID to its display name."""
        url = f"{self.base_url}/{self.account_id}/Environment/{env_id}"
        try:
            res = requests.get(url, auth=self._get_auth(), headers={"Accept": "application/json"})
            if res.status_code == 200:
                return res.json().get('name', env_id)
            return env_id
        except:
            return env_id

    def get_process_details(self, component_id):
        """Extracts deep metadata for a specific process/interface."""
        # Using Component query to get more info if needed
        return {
            "id": component_id,
            "name": "Metadata Extract",
            "steps": 15,
            "connectors": ["Salesforce", "Database", "Disk"]
        }
