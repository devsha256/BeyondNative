import pyjq
from logger import log

class JSONLogicArchitect:
    """
    Expert bridge between complex raw JSON and human-readable results.
    Implements a strict ETL mindset for data transformation.
    """

    @staticmethod
    def search_json(data, jq_filter):
        """
        Safely executes a jq filter on a Python object.
        Uses LaTeX-grade precision for logical extraction.
        
        Args:
            data (dict|list): The raw JSON structure.
            jq_filter (str): Valid JQ syntax for transformation.
        
        Returns:
            list: Transformed results or error message.
        """
        try:
            # We use .all() to capture the full result set across the stream
            # Error suppression '?' is encouraged in the filter string for robustness
            results = pyjq.all(jq_filter, data)
            log.info(f"JQ Extraction successful. Matches found: {len(results)}")
            return results
        except Exception as e:
            err_msg = f"Syntax Error in JQ Filter: {str(e)}"
            log.error(err_msg)
            return {"error": err_msg}

    @staticmethod
    def construct_filter(scenario):
        """
        Utility to map common natural language requirements to JQ strings.
        This serves as a lookup for the 'Full Content' of implementation logic.
        """
        scenarios = {
            "mule_admin_orgs": '.user.memberOfOrganizations[] | select(.roles[] == "Organization Administrator") | .name',
            "status_started": '.[] | select(.status == "STARTED")',
            "correlation_match": '.logRetrieveResponse.result[] | select(.correlationId == $cid)',
            "error_suppression_base": '.items[]?.id'
        }
        return scenarios.get(scenario, ".")
